"""Default concurrency for runtime-executed work, derived from the host.

These are starting points, not rules: the orchestrator should tune them (by
environment variable) to whatever is most efficient where the run executes.
The defaults reflect measurements on a 4-core, 16 GB cloud container:

- Page fetches to one host: 4 in flight was 3.4x faster than serial; more added
  per-request latency without throughput.
- Whisper (small.en, int8): one single-threaded job per core transcribed 10.5x
  real time in total, versus 7.4x for two 2-thread jobs and 4.8x for one
  4-thread job. A job on an hour-long recording, with its diarization model,
  used about 3 GB (four used 11.6 GB), and the whole session shares one memory
  limit: four jobs plus side work once exceeded it, so job count is bounded by
  memory too, with 2 GB kept free. Each job now runs in its own process
  (Whisper plus Sortformer peaked at 1.74 GB on ten minutes of audio), so its
  memory is returned when it ends and an out-of-memory job fails alone.
- Headless browser renders: about 0.25 GB each; held to half the cores so they
  do not starve concurrent transcription.

Every value can be overridden with an environment variable.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any


def _available_memory_gb() -> float:
    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 1024 / 1024
    except OSError:
        pass
    return 4.0


def _override(name: str, default: float) -> float:
    value = os.environ.get(name, "").strip()
    return float(value) if value else default


@lru_cache(maxsize=1)
def runtime_limits() -> dict[str, Any]:
    cpus = os.cpu_count() or 2
    memory = _available_memory_gb()
    # About 3.5 GB per long job (four used 11.6 GB), keeping 2 GB for everything else.
    whisper_jobs = int(_override("RESEARCH_CONTROL_WHISPER_JOBS", max(1, min(cpus, int((memory - 2.0) // 3.5)))))
    browser_jobs = int(_override("RESEARCH_CONTROL_BROWSER_JOBS", max(1, min(cpus // 2, int(memory // 0.5)))))
    return {
        "cpus": cpus,
        "available_memory_gb": round(memory, 1),
        "workers": int(_override("RESEARCH_CONTROL_RUNTIME_WORKERS", max(8, cpus * 4))),
        "per_host": int(_override("RESEARCH_CONTROL_PER_HOST", 4)),
        "host_interval_seconds": _override("RESEARCH_CONTROL_HOST_INTERVAL", 0.25),
        "whisper_jobs": whisper_jobs,
        "whisper_threads": max(1, cpus // whisper_jobs),
        "browser_jobs": browser_jobs,
    }
