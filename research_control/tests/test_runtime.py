from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from research_control.runtime import RuntimeStore, WorkItem


def item(task_id: str, output: str, **values) -> WorkItem:
    return WorkItem(
        task_id=task_id,
        phase=values.pop("phase", "capture"),
        task_type=values.pop("task_type", "capture"),
        inputs=values.pop("inputs", [{"id": task_id}]),
        outputs=[output],
        prompt_files=["prompt.md"],
        **values,
    )


class RuntimeTests(unittest.TestCase):
    def test_dependencies_host_limits_retry_and_independence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with RuntimeStore(root) as store:
                store.initialize(
                    run_id="run-1", company_url="https://example.com",
                    global_concurrency=4, host_concurrency=1, lease_seconds=60,
                )
                store.add_task(item("capture.a", "parts/a.txt", host_key="example.com", independent=True))
                store.add_task(item(
                    "capture.b", "parts/b.txt", host_key="example.com",
                    independent=True, depends_on=["capture.a"],
                ))
                first = store.claim("worker-a", task_id="capture.a")
                self.assertEqual("leased", first["state"])
                self.assertIsNone(store.claim("worker-b", task_id="capture.b"))
                store.start("capture.a", "worker-a")
                (root / "parts").mkdir(parents=True)
                (root / "parts/a.txt").write_text("a\n", encoding="utf-8")
                store.complete("capture.a", "worker-a", telemetry={"model": "test", "input_tokens": 10})
                second = store.claim("worker-b", task_id="capture.b")
                self.assertIsNotNone(second)
                store.start("capture.b", "worker-b")
                (root / "parts/b.txt").write_text("b\n", encoding="utf-8")
                store.complete("capture.b", "worker-b")

                store.add_task(item("capture.c", "parts/c.txt", independent=True))
                with self.assertRaises(ValueError):
                    store.claim("worker-a", task_id="capture.c")
                store.claim("worker-c", task_id="capture.c")
                recovered = store.recover_expired(now="9999-01-01T00:00:00Z")
                self.assertEqual(["capture.c"], recovered)
                self.assertEqual("retryable", store.task("capture.c")["state"])
                self.assertEqual(1, store.task("capture.c")["attempt_count"])

    def test_changed_output_invalidates_downstream_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with RuntimeStore(root) as store:
                store.initialize(run_id="run-2", company_url="https://example.com")
                store.add_task(item("facts.extract", "parts/extract.txt", phase="facts", task_type="extraction"))
                store.add_task(item(
                    "facts.reduce", "parts/reduce.txt", phase="facts", task_type="extraction_reducer",
                    depends_on=["facts.extract"],
                ))
                (root / "parts").mkdir(parents=True)
                for task_id, worker_id, filename in (
                    ("facts.extract", "extractor", "extract.txt"),
                    ("facts.reduce", "reducer", "reduce.txt"),
                ):
                    store.claim(worker_id, task_id=task_id)
                    store.start(task_id, worker_id)
                    (root / "parts" / filename).write_text(f"{task_id}\n", encoding="utf-8")
                    store.complete(task_id, worker_id)
                (root / "parts/extract.txt").write_text("changed\n", encoding="utf-8")
                stale = store.invalidate_stale()
                self.assertEqual(["facts.extract", "facts.reduce"], stale)
                self.assertEqual("ready", store.task("facts.extract")["state"])
                self.assertEqual("planned", store.task("facts.reduce")["state"])

    def test_requested_rerun_marks_completed_consumers_stale(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with RuntimeStore(root) as store:
                store.initialize(run_id="run-3", company_url="https://example.com")
                store.add_task(item("capture.a", "parts/a.txt"))
                store.add_task(item("capture.reduce", "parts/reduce.txt", depends_on=["capture.a"]))
                (root / "parts").mkdir(parents=True)
                for task_id, filename in (("capture.a", "a.txt"), ("capture.reduce", "reduce.txt")):
                    store.claim("runtime", task_id=task_id)
                    store.start(task_id, "runtime")
                    (root / "parts" / filename).write_text(f"{task_id}\n", encoding="utf-8")
                    store.complete(task_id, "runtime")
                store.mark_stale("capture.a", "retry requested")
                self.assertEqual("ready", store.task("capture.a")["state"])
                self.assertEqual("planned", store.task("capture.reduce")["state"])

    def test_declared_revision_owns_current_shared_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with RuntimeStore(root) as store:
                store.initialize(run_id="run-3", company_url="https://example.com")
                store.add_task(item("synthesis.draft", "shared/report.md", phase="initial_synthesis", task_type="synthesis"))
                store.add_task(item(
                    "synthesis.fix", "shared/report.md", phase="corrected_synthesis", task_type="fixer",
                    depends_on=["synthesis.draft"], output_mode="revise",
                ))
                (root / "shared").mkdir(parents=True)
                store.claim("writer", task_id="synthesis.draft")
                store.start("synthesis.draft", "writer")
                (root / "shared/report.md").write_text("draft\n", encoding="utf-8")
                store.complete("synthesis.draft", "writer")
                store.claim("fixer", task_id="synthesis.fix")
                store.start("synthesis.fix", "fixer")
                (root / "shared/report.md").write_text("revised\n", encoding="utf-8")
                store.complete("synthesis.fix", "fixer")
                self.assertEqual([], store.invalidate_stale())


if __name__ == "__main__":
    unittest.main()
