"""In-process execution of deterministic work items.

Work that needs no judgment, such as crawling the first-party site, capturing
ordinary pages and PDFs, and the single-writer reducers, runs inside
``research_control run`` instead of being dispatched to agent workers. It uses
the same scheduler lease, ledger, output-hash, and receipt contracts as agent
work, under the reserved worker identity ``runtime-executor``.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any, Callable

from research_control.capture import auto_capture_source
from research_control.discovery import DiscoveryEngine
from research_control.io import atomic_write_json, load_json, workflow
from research_control.media import is_media_url
from research_control.provision import engine_fingerprint
from research_control.resources import runtime_limits
from research_control.reducers import reduce_capture_parts, reduce_discovery, reduce_extraction_parts
from research_control.runtime import RuntimeStore


RUNTIME_WORKER = "runtime-executor"


def _write_channel_receipt(root: Path, store: RuntimeStore, channel: str, relative: str) -> None:
    current = store.discovery_channel(channel)
    if not current or current["state"] == "open":
        raise ValueError(f"discovery channel is not terminal: {channel}")
    atomic_write_json(root / relative, {
        "schema_version": "1.0.0",
        "channel": channel,
        "status": current["state"],
        "passes": current["total_passes"],
        "new_sources": current["total_new_sources"],
        "evidence": current["completion_evidence"],
    })


def _first_party_discovery(root: Path, store: RuntimeStore, task: dict[str, Any]) -> dict[str, Any]:
    """Crawl the company host and/or audit its sitemaps, then write channel receipts."""
    channels = task["metadata"]["channels"]
    engine = DiscoveryEngine(root, store)
    engine.initialize()
    result: dict[str, Any] = {}
    if "company_site" in channels:
        result["seeded_sitemaps"] = engine.seed_sitemaps()
        rounds: list[dict[str, Any]] = []
        for _round in range(6):
            while True:
                crawl = engine.crawl_company_site()
                if crawl["status"] in {"saturated", "incomplete", "blocked"}:
                    break
            rounds.append({"crawl": crawl["status"], "fetched": crawl["pages_fetched"]})
            if crawl["status"] != "saturated":
                break
            # Sitemap URLs the link crawl missed feed the next crawl round.
            cached = engine.audit_sitemaps(refetch=False)
            fresh = engine.audit_sitemaps(refetch=True)
            if not cached["new_source_ids"] and not fresh["new_source_ids"]:
                break
        result["rounds"] = rounds
    if "sitemaps" in channels:
        for refetch in (False, True, False, True):
            if (store.discovery_channel("sitemaps") or {}).get("state") != "open":
                break
            engine.audit_sitemaps(refetch=refetch)
        if (store.discovery_channel("sitemaps") or {}).get("state") == "open":
            store.set_discovery_channel(
                "sitemaps", "incomplete", "sitemap audit kept finding new URLs; crawl the new branch first"
            )
    engine.write_catalog()
    for channel, receipt in zip(channels, task["metadata"]["receipts"]):
        _write_channel_receipt(root, store, channel, receipt)
    return result


def _capture(root: Path, store: RuntimeStore, task: dict[str, Any]) -> dict[str, Any]:
    source = store.source(task["metadata"]["source_id"])
    if not source:
        raise KeyError(f"unknown source: {task['metadata']['source_id']}")
    grade = "S" if source["channel"] == "independent_web" else "P"
    media = source["channel"] in {"video", "podcasts"} or is_media_url(source["canonical_url"])
    receipt = auto_capture_source(
        root, url=source["canonical_url"], source_id=source["source_id"], grade=grade, store=store, media=media,
    )
    # Record which policy, prompts, and engine were in force for this capture.
    path = root / task["metadata"]["receipt"]
    stored = load_json(path)
    stored["policy"] = engine_fingerprint(root)
    atomic_write_json(path, stored)
    return receipt


HANDLERS: dict[str, Callable[[Path, RuntimeStore, dict[str, Any]], Any]] = {
    "source_discovery": _first_party_discovery,
    "discovery_reducer": lambda root, store, _task: reduce_discovery(root, store),
    "capture": _capture,
    "capture_reducer": lambda root, store, _task: reduce_capture_parts(root, store),
    "extraction_reducer": lambda root, _store, _task: reduce_extraction_parts(root),
}


class _HostPacer:
    """Keep at least ``interval`` seconds between request starts to one host."""

    def __init__(self, interval: float) -> None:
        self.interval = interval
        self.lock = threading.Lock()
        self.last: dict[str, float] = {}

    def wait(self, host: str) -> None:
        if not host:
            return
        with self.lock:
            now = time.monotonic()
            start = max(now, self.last.get(host, 0.0) + self.interval)
            self.last[host] = start
        if start > now:
            time.sleep(start - now)


def _execute(root: Path, task: dict[str, Any], pacer: _HostPacer) -> Any:
    """Run one handler in a worker thread with its own scheduler connection."""
    if task["task_type"] == "capture":
        pacer.wait(task["host_key"])
    with RuntimeStore(root) as local:
        return HANDLERS[task["task_type"]](root, local, task)


def run_automatic(
    root: Path,
    store: RuntimeStore,
    phases: list[str],
    complete: Callable[[RuntimeStore, dict[str, Any], str], Any],
    replan: Callable[[], Any],
) -> dict[str, Any]:
    """Execute every ready runtime-owned task in ``phases`` until none remain.

    Work runs in a thread pool sized for this host (see ``resources``), with a
    per-host limit and requests to one host paced apart. Leasing, completion,
    and planning stay on this thread's connection; each worker opens its own.
    ``phases`` is the current phase plus the phases before it, so deterministic
    work that went stale after its phase closed is redone automatically.
    """
    limits = runtime_limits()
    global_limit = max(1, limits["workers"])
    host_limit = max(1, limits["per_host"])
    pacer = _HostPacer(limits["host_interval_seconds"])
    executed: list[str] = []
    failed: list[dict[str, str]] = []
    in_flight: dict[Future[Any], dict[str, Any]] = {}
    last_heartbeat = time.monotonic()
    with ThreadPoolExecutor(max_workers=global_limit, thread_name_prefix="runtime") as pool:
        while True:
            store.refresh_ready()
            running = {task["task_id"] for task in in_flight.values()}
            ready = sorted(
                (
                    task for task in store.tasks(states={"ready", "retryable"})
                    if task["metadata"].get("executor") == "runtime"
                    and task["phase"] in phases and task["task_id"] not in running
                ),
                key=lambda task: (task["priority"], task["created_at"], task["task_id"]),
            )
            for task in ready:
                if len(in_flight) >= global_limit:
                    break
                if task["task_type"] not in HANDLERS:
                    raise ValueError(f"{task['task_id']}: no runtime handler for task type {task['task_type']}")
                host = task["host_key"]
                if host and sum(1 for item in in_flight.values() if item["host_key"] == host) >= host_limit:
                    continue
                if not store.claim(RUNTIME_WORKER, task_id=task["task_id"], bypass_limits=True):
                    continue
                store.start(task["task_id"], RUNTIME_WORKER)
                in_flight[pool.submit(_execute, root, task, pacer)] = task
            if not in_flight:
                break
            done, _pending = wait(in_flight, timeout=60, return_when=FIRST_COMPLETED)
            if time.monotonic() - last_heartbeat > 300:
                # Long transcriptions must not lose their lease while they run.
                for task in in_flight.values():
                    store.heartbeat(task["task_id"], RUNTIME_WORKER)
                last_heartbeat = time.monotonic()
            for future in done:
                task = in_flight.pop(future)
                try:
                    future.result()
                    complete(store, store.task(task["task_id"]) or task, RUNTIME_WORKER)
                    executed.append(task["task_id"])
                except Exception as error:  # record the concrete failure; the scheduler decides retry
                    failed.append({"task_id": task["task_id"], "reason": f"{type(error).__name__}: {error}"})
                    current = store.task(task["task_id"])
                    if current and current["state"] in {"leased", "running", "validating"}:
                        store.fail(task["task_id"], RUNTIME_WORKER, f"{type(error).__name__}: {error}")
            if done:
                replan()
    return {"executed": len(executed), "failed": failed}
