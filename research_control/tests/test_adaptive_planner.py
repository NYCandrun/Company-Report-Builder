from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from research_control.discovery import DISCOVERY_CHANNELS, DiscoveryEngine
from research_control.io import atomic_write_json, workflow
from research_control.orchestration import initialize, load_state, save_state
from research_control.planner import AdaptivePlanner
from research_control.reducers import reduce_capture_parts, reduce_discovery
from research_control.runtime import RuntimeStore


SOURCE_ROOT = Path(__file__).resolve().parents[2]


def copy_template(target: Path) -> None:
    for name in ("README.md", "RESEARCH_CONSTITUTION.md", "WORKFLOW.yaml", "pyproject.toml"):
        shutil.copy2(SOURCE_ROOT / name, target / name)
    for name in ("docs", "prompts", "research_control", "tools"):
        shutil.copytree(SOURCE_ROOT / name, target / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


class AdaptivePlannerTests(unittest.TestCase):
    def test_brand_input_is_presentation_only_and_no_extra_phase_is_added(self) -> None:
        document = workflow(SOURCE_ROOT / "WORKFLOW.yaml")
        final_tasks = {item["id"]: item for item in document["execution_profiles"]["final"]["tasks"]}
        model_inputs = {item["id"] for item in final_tasks["model-diagrams"]["inputs"]}
        build_inputs = {item["id"] for item in final_tasks["build-diagrams"]["inputs"]}
        self.assertNotIn("brand_guide", model_inputs)
        self.assertIn("brand_guide", build_inputs)
        self.assertNotIn("adapt-diagram-style", final_tasks)
        self.assertIn("07-final-report/diagram-style-spec.md", final_tasks["build-diagrams"]["outputs"])

    def test_new_first_party_branch_reopens_a_saturated_channel(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy_template(root)
            state = initialize(root, "https://example.com")
            state["phases"]["bootstrap"]["status"] = "complete"
            state["phases"]["scope"]["status"] = "complete"
            state["phases"]["capture"]["status"] = "ready"
            save_state(root, state)
            with RuntimeStore(root) as store:
                store.initialize(run_id=state["run_id"], company_url=state["company_url"])
                engine = DiscoveryEngine(root, store)
                AdaptivePlanner(root, store).reconcile()
                for number in (1, 2):
                    engine.add_candidates(
                        "company_site", [], discovered_from=f"pass-{number}",
                        evidence=f"empty company pass {number}",
                    )
                channel = store.discovery_channel("company_site")
                receipt = root / "tools/outputs/worker-parts/discovery/company-site.json"
                atomic_write_json(receipt, {
                    "schema_version": "1.0.0", "channel": "company_site", "status": "saturated",
                    "passes": 2, "new_sources": 0, "evidence": channel["completion_evidence"],
                })
                task_id = "capture.discover.company-site"
                store.claim("company-discovery", task_id=task_id)
                store.start(task_id, "company-discovery")
                store.complete(task_id, "company-discovery")
                engine.add_candidates(
                    "company_site", ["https://example.com/new-branch"],
                    discovered_from="new sitemap", evidence="new sitemap branch",
                )
                AdaptivePlanner(root, store).reconcile()
                self.assertEqual("ready", store.task(task_id)["state"])
                self.assertIsNone(store.task("capture.reduce-discovery"))

    def test_task_count_follows_discovered_corpus_and_content_volume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy_template(root)
            state = initialize(root, "https://example.com")
            state["phases"]["bootstrap"]["status"] = "complete"
            state["phases"]["scope"]["status"] = "complete"
            state["phases"]["capture"]["status"] = "ready"
            save_state(root, state)

            with RuntimeStore(root) as store:
                store.initialize(run_id=state["run_id"], company_url=state["company_url"])
                engine = DiscoveryEngine(root, store)
                engine.initialize()
                engine.add_candidates(
                    "company_site", ["https://example.com/about", "https://example.com/large"],
                    discovered_from="homepage", evidence="fixture links", record_pass=False,
                )
                first_plan = AdaptivePlanner(root, store).reconcile()
                self.assertEqual(len(DISCOVERY_CHANNELS) + 1, first_plan["task_count"])
                brand = store.task("capture.brand-guide")
                self.assertIsNotNone(brand)
                self.assertTrue(brand["independent"])
                self.assertEqual("concurrent_with_discovery_and_capture", brand["metadata"]["schedule"])

                for channel in DISCOVERY_CHANNELS:
                    engine.add_candidates(
                        channel, [], discovered_from=f"{channel}-pass-1",
                        evidence=f"fixture empty pass one for {channel}",
                    )
                    engine.add_candidates(
                        channel, [], discovered_from=f"{channel}-pass-2",
                        evidence=f"fixture fixed point for {channel}",
                    )
                    receipt_path = root / "tools/outputs/worker-parts/discovery" / f"{channel.replace('_', '-')}.json"
                    receipt_path.parent.mkdir(parents=True, exist_ok=True)
                    atomic_write_json(receipt_path, {
                        "schema_version": "1.0.0", "channel": channel, "status": "saturated",
                        "passes": 2, "new_sources": 0, "evidence": f"fixture fixed point for {channel}",
                    })
                    task_id = f"capture.discover.{channel.replace('_', '-')}"
                    worker = f"discover-{channel}"
                    store.claim(worker, task_id=task_id)
                    store.start(task_id, worker)
                    store.complete(task_id, worker)

                AdaptivePlanner(root, store).reconcile()
                reduce_discovery(root, store)
                store.claim("discovery-reducer", task_id="capture.reduce-discovery")
                store.start("capture.reduce-discovery", "discovery-reducer")
                store.complete("capture.reduce-discovery", "discovery-reducer")

                AdaptivePlanner(root, store).reconcile()
                capture_tasks = [task for task in store.tasks(phase="capture") if task["task_type"] == "capture"]
                self.assertEqual(3, len(capture_tasks))
                for index, task in enumerate(capture_tasks):
                    source_id = task["metadata"]["source_id"]
                    content_path = root / "01-sources/captures" / source_id / "content.txt"
                    content_path.parent.mkdir(parents=True, exist_ok=True)
                    body = "large evidence paragraph.\n" * (40_000 if index == 2 else 10)
                    content_path.write_text(body, encoding="utf-8")
                    receipt_path = root / task["metadata"]["receipt"]
                    source = store.source(source_id)
                    atomic_write_json(receipt_path, {
                        "schema_version": "1.0.0", "task_type": "capture", "source_id": source_id,
                        "status": "captured", "canonical_text_ready": True,
                        "local_paths": [str(content_path.relative_to(root))],
                        "content_bytes": len(body), "estimated_tokens": max(1, len(body) // 4),
                        "source": {
                            "id": source_id, "grade": "P", "title": source_id, "publisher": "Example",
                            "url": source["canonical_url"], "date published": "2026-01-01",
                            "date last modified": "", "date captured": "2026-10-23",
                            "local file": str(content_path.relative_to(root)), "method": "fixture", "notes": "",
                        },
                        "disposition": {"input_id": source_id, "disposition": "completed", "reason": "fixture",
                                        "evidence_paths": [str(content_path.relative_to(root))], "output_ids": [source_id]},
                    })
                    worker = f"capture-{index}"
                    store.claim(worker, task_id=task["task_id"])
                    store.start(task["task_id"], worker)
                    store.complete(task["task_id"], worker)

                AdaptivePlanner(root, store).reconcile()
                reduce_capture_parts(root, store)
                store.claim("capture-reducer", task_id="capture.reduce-captures")
                store.start("capture.reduce-captures", "capture-reducer")
                store.complete("capture.reduce-captures", "capture-reducer")

                state = load_state(root)
                state["phases"]["capture"]["status"] = "complete"
                state["phases"]["facts"]["status"] = "ready"
                save_state(root, state)
                facts_plan = AdaptivePlanner(root, store).reconcile()
                extraction_tasks = [task for task in store.tasks(phase="facts") if task["task_type"] == "extraction"]
                self.assertGreater(len(extraction_tasks), 1)
                self.assertEqual(len(extraction_tasks), facts_plan["task_count"])
                self.assertTrue(all(task["metadata"]["estimated_tokens"] <= 90_000 for task in extraction_tasks))


if __name__ == "__main__":
    unittest.main()
