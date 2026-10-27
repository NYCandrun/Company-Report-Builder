from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from research_control import automatic
from research_control.automatic import RUNTIME_WORKER, run_automatic
from research_control.io import atomic_write_text
from research_control.orchestration import initialize
from research_control.provision import provision_run
from research_control.runtime import RuntimeStore, WorkItem


SOURCE_ROOT = Path(__file__).resolve().parents[2]


class RuntimePoolTests(unittest.TestCase):
    def test_runtime_work_runs_in_parallel_within_host_limits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = provision_run(SOURCE_ROOT, Path(directory) / "run")
            state = initialize(root, "https://example.com")
            lock = threading.Lock()
            active: dict[str, int] = {}
            peaks: dict[str, int] = {}
            overall = {"now": 0, "peak": 0}

            def fake_capture(run_root: Path, _store: RuntimeStore, task: dict) -> None:
                host = task["host_key"]
                with lock:
                    active[host] = active.get(host, 0) + 1
                    peaks[host] = max(peaks.get(host, 0), active[host])
                    overall["now"] += 1
                    overall["peak"] = max(overall["peak"], overall["now"])
                time.sleep(0.2)
                atomic_write_text(run_root / task["outputs"][0], "captured\n")
                with lock:
                    active[host] -= 1
                    overall["now"] -= 1

            with RuntimeStore(root) as store:
                store.initialize(run_id=state["run_id"], company_url=state["company_url"])
                for index in range(8):
                    host = "a.example" if index < 4 else f"host-{index}.example"
                    store.add_task(WorkItem(
                        task_id=f"capture.fake.{index}", phase="capture", task_type="capture",
                        inputs=[], outputs=[f"out/{index}.txt"], prompt_files=["prompts/phases/capture-source.md"],
                        host_key=host, metadata={"executor": "runtime"},
                    ))
                limits = {"workers": 6, "per_host": 2, "host_interval_seconds": 0.0}
                with patch.dict(automatic.HANDLERS, {"capture": fake_capture}), \
                        patch.object(automatic, "runtime_limits", lambda: limits):
                    result = run_automatic(
                        root, store, ["capture"],
                        lambda current, task, worker: current.complete(task["task_id"], worker),
                        lambda: None,
                    )
                self.assertEqual(8, result["executed"])
                self.assertEqual([], result["failed"])
                self.assertTrue(all(task["state"] == "succeeded" for task in store.tasks(phase="capture")))
            self.assertLessEqual(peaks["a.example"], 2)
            self.assertGreater(overall["peak"], 2)
            self.assertLessEqual(overall["peak"], 6)
            self.assertEqual(RUNTIME_WORKER, "runtime-executor")


if __name__ == "__main__":
    unittest.main()
