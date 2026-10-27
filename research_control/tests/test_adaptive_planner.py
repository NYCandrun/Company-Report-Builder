from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from research_control.discovery import DISCOVERY_CHANNELS, DiscoveryEngine
from research_control.automatic import RUNTIME_WORKER
from research_control.cli import _require_discovery_lease
from research_control.dispatch import emit_ready_packets
from research_control.io import atomic_write_json, atomic_write_jsonl, load_jsonl, workflow
from research_control.orchestration import current_phase, initialize, load_state, reopen_phase, save_state
from research_control.planner import RUNTIME_DISCOVERY_CHANNELS, AdaptivePlanner, _batch_id, discovery_task_id
from research_control.runtime import WorkItem
from research_control.provision import provision_run
from research_control.reducers import reduce_capture_parts, reduce_discovery
from research_control.runtime import RuntimeStore
from research_control.routing import model_route
from research_control.triage import add_scope_question, validate_triage


SOURCE_ROOT = Path(__file__).resolve().parents[2]


def copy_template(target: Path) -> None:
    provision_run(SOURCE_ROOT, target)


class AdaptivePlannerTests(unittest.TestCase):
    def test_model_routing_is_advisory_and_capability_dependent(self) -> None:
        economy = model_route(SOURCE_ROOT, "capture")
        strong = model_route(SOURCE_ROOT, "diagram_modeler")
        self.assertTrue(economy["optional"])
        self.assertEqual("advisory_only", economy["enforcement"])
        self.assertEqual("economy", economy["tier"])
        self.assertEqual("frontier", strong["tier"])
        self.assertEqual("strongest_available", strong["model_class"])
        self.assertEqual("strong", model_route(SOURCE_ROOT, "synthesis")["tier"])
        self.assertEqual("use_available_model", strong["fallback"])

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
                task_id = "capture.discover.company-site"
                self.assertEqual("runtime", store.task(task_id)["metadata"]["executor"])
                self.assertEqual([task_id], store.task("capture.discover.sitemaps")["depends_on"])
                self.assertEqual([task_id], store.task("capture.discover.careers")["depends_on"])
                self.assertEqual([], store.task("capture.discover.video")["depends_on"])
                for number in (1, 2):
                    engine.add_candidates(
                        "company_site", [], discovered_from=f"pass-{number}",
                        evidence=f"empty company_site pass {number}",
                    )
                _write_receipt(root, store, "company_site")
                store.claim(RUNTIME_WORKER, task_id=task_id)
                store.start(task_id, RUNTIME_WORKER)
                store.complete(task_id, RUNTIME_WORKER)
                engine.add_candidates(
                    "company_site", ["https://example.com/new-branch"],
                    discovered_from="new sitemap", evidence="new sitemap branch",
                )
                AdaptivePlanner(root, store).reconcile()
                self.assertEqual("ready", store.task(task_id)["state"])
                self.assertIsNone(store.task("capture.reduce-discovery"))

    def test_login_walled_urls_are_leads_and_sufficiency_needs_question_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy_template(root)
            state = initialize(root, "https://example.com")
            with RuntimeStore(root) as store:
                store.initialize(run_id=state["run_id"], company_url=state["company_url"])
                engine = DiscoveryEngine(root, store)
                engine.initialize()
                result = engine.add_candidates(
                    "social", ["https://www.linkedin.com/company/example", "https://example.com/sitemap.xml"],
                    discovered_from="search", evidence="official profile",
                )
                relevance = {store.source(source_id)["canonical_url"]: store.source(source_id)["relevance"] for source_id in result["new_source_ids"]}
                self.assertEqual("lead", relevance["https://www.linkedin.com/company/example"])
                self.assertEqual("inventory", relevance["https://example.com/sitemap.xml"])
                with self.assertRaises(ValueError):
                    engine.close_channel("social", "sufficient", "enough sources")
                closed = engine.close_channel("social", "sufficient", "Q6: official profile admitted; no other account exists")
                self.assertEqual("sufficient", closed["state"])

    def test_grouped_discovery_from_an_older_run_is_kept_until_its_channel_changes(self) -> None:
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
                grouped = ("video", "podcasts", "social")
                receipts = [f"tools/outputs/worker-parts/discovery/{channel}.json" for channel in grouped]
                store.add_task(WorkItem(
                    task_id="capture.discover.media-social", phase="capture", task_type="source_discovery",
                    inputs=[], outputs=receipts, prompt_files=["prompts/phases/discovery.md"],
                    independent=True, exclusive_inputs=False,
                    metadata={"channels": list(grouped), "receipts": receipts, "executor": "agent"},
                ))
                for channel in grouped:
                    for number in (1, 2):
                        engine.add_candidates(channel, [], discovered_from=f"p{number}", evidence=f"{channel} pass {number}")
                    _write_receipt(root, store, channel)
                store.claim("media-worker", task_id="capture.discover.media-social")
                store.start("capture.discover.media-social", "media-worker")
                store.complete("capture.discover.media-social", "media-worker")

                AdaptivePlanner(root, store).reconcile()
                for channel in grouped:
                    self.assertIsNone(store.task(discovery_task_id(channel)))
                self.assertIsNotNone(store.task("capture.discover.careers"))

                with self.assertRaises(ValueError):
                    _require_discovery_lease(store, "video")
                engine.reopen_channel("video", "scope now includes Shorts and leader appearances")
                # An older planner may already have marked the grouped task stale.
                store.mark_stale("capture.discover.media-social", "video channel reopened")
                AdaptivePlanner(root, store).reconcile()
                self.assertEqual("ready", store.task("capture.discover.video")["state"])
                self.assertIsNone(store.task("capture.discover.podcasts"))
                self.assertIsNone(store.task("capture.discover.social"))
                self.assertEqual("superseded", store.task("capture.discover.media-social")["state"])
                packets = [item["task_id"] for item in emit_ready_packets(root, store, "capture")["packets"]]
                self.assertNotIn("capture.discover.media-social", packets)
                store.claim("video-worker", task_id="capture.discover.video")
                store.start("capture.discover.video", "video-worker")
                _require_discovery_lease(store, "video")

    def test_task_count_follows_discovered_corpus_and_content_volume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy_template(root)
            state = initialize(root, "https://example.com")
            state["phases"]["bootstrap"]["status"] = "complete"
            state["phases"]["scope"]["status"] = "complete"
            state["phases"]["capture"]["status"] = "ready"
            save_state(root, state)
            (root / "00-scope.md").write_text("# Scope\n\n## Research questions\n\n- Q1 product.\n- Q2 buyer.\n", encoding="utf-8")

            with RuntimeStore(root) as store:
                store.initialize(run_id=state["run_id"], company_url=state["company_url"])
                engine = DiscoveryEngine(root, store)
                engine.initialize()
                engine.add_candidates(
                    "company_site", ["https://example.com/about", "https://example.com/large"],
                    discovered_from="homepage", evidence="fixture links", record_pass=False,
                )
                first_plan = AdaptivePlanner(root, store).reconcile()
                # Capture starts while discovery is still open: 10 channel tasks + 3 sources.
                self.assertEqual(len(DISCOVERY_CHANNELS) + 3, first_plan["task_count"])
                early_captures = [task for task in store.tasks(phase="capture") if task["task_type"] == "capture"]
                self.assertTrue(all(task["state"] == "ready" and not task["depends_on"] for task in early_captures))
                brand = store.task("final.brand-guide")
                self.assertIsNotNone(brand)
                self.assertTrue(brand["independent"])
                self.assertEqual("early", brand["metadata"]["dispatch"])
                dispatch = emit_ready_packets(root, store, "capture")
                self.assertIn("final.brand-guide", [item["task_id"] for item in dispatch["packets"]])
                self.assertNotIn("capture.discover.company-site", [item["task_id"] for item in dispatch["packets"]])
                self.assertIn("capture.discover.video", [item["task_id"] for item in dispatch["packets"]])

                for channel in DISCOVERY_CHANNELS:
                    for number in (1, 2):
                        engine.add_candidates(
                            channel, [], discovered_from=f"{channel}-pass-{number}",
                            evidence=f"fixture fixed point for {channel}",
                        )
                for channel in DISCOVERY_CHANNELS:
                    task_id = discovery_task_id(channel)
                    _write_receipt(root, store, channel)
                    worker = RUNTIME_WORKER if channel in RUNTIME_DISCOVERY_CHANNELS else f"discover-{channel}"
                    store.claim(worker, task_id=task_id)
                    store.start(task_id, worker)
                    store.complete(task_id, worker)

                AdaptivePlanner(root, store).reconcile()
                reduce_discovery(root, store)
                store.claim(RUNTIME_WORKER, task_id="capture.reduce-discovery")
                store.start("capture.reduce-discovery", RUNTIME_WORKER)
                store.complete("capture.reduce-discovery", RUNTIME_WORKER)

                AdaptivePlanner(root, store).reconcile()
                capture_tasks = [task for task in store.tasks(phase="capture") if task["task_type"] == "capture"]
                self.assertEqual(3, len(capture_tasks))
                self.assertTrue(all(task["metadata"]["executor"] == "runtime" for task in capture_tasks))
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
                    store.claim(RUNTIME_WORKER, task_id=task["task_id"])
                    store.start(task["task_id"], RUNTIME_WORKER)
                    store.complete(task["task_id"], RUNTIME_WORKER)

                AdaptivePlanner(root, store).reconcile()
                # No capture was blocked, so no alternate-copies pass is planned.
                self.assertIsNone(store.task("capture.alternate-copies"))
                self.assertIn("capture.reduce-discovery", store.task("capture.reduce-captures")["depends_on"])
                reduce_capture_parts(root, store)
                store.claim(RUNTIME_WORKER, task_id="capture.reduce-captures")
                store.start("capture.reduce-captures", RUNTIME_WORKER)
                store.complete("capture.reduce-captures", RUNTIME_WORKER)

                state = load_state(root)
                state["phases"]["capture"]["status"] = "complete"
                state["phases"]["facts"]["status"] = "ready"
                save_state(root, state)
                triage_plan = AdaptivePlanner(root, store).reconcile()
                self.assertEqual(["facts.triage"], [task["task_id"] for task in store.tasks(phase="facts")])
                self.assertEqual(1, triage_plan["task_count"])
                small = capture_tasks[0]["metadata"]["source_id"]
                rows = [
                    {"id": task["metadata"]["source_id"], "decision": "include", "questions": ["Q1"], "reason": "fixture"}
                    for task in capture_tasks[1:]
                ] + [{"id": small, "decision": "exclude", "questions": [], "reason": "duplicate of the about page"}]
                atomic_write_jsonl(root / "tools/lists/extraction-triage.jsonl", rows)
                self.assertEqual([], validate_triage(root))
                store.claim("triage-worker", task_id="facts.triage")
                store.start("facts.triage", "triage-worker")
                store.complete("facts.triage", "triage-worker")

                facts_plan = AdaptivePlanner(root, store).reconcile()
                extraction_tasks = [task for task in store.tasks(phase="facts") if task["task_type"] == "extraction"]
                self.assertGreater(len(extraction_tasks), 1)
                # Triage, the batches, and the reducer, which waits on every current batch.
                self.assertEqual(len(extraction_tasks) + 2, facts_plan["task_count"])
                reducer = store.task("facts.reduce-extraction")
                self.assertEqual("planned", reducer["state"])
                self.assertEqual({task["task_id"] for task in extraction_tasks}, set(reducer["depends_on"]))
                self.assertTrue(all(task["metadata"]["estimated_tokens"] <= 90_000 for task in extraction_tasks))
                extracted = {item["source_id"] for task in extraction_tasks for item in task["inputs"]}
                self.assertNotIn(small, extracted)

                # A question added mid-run plans a re-triage of every captured source.
                request = add_scope_question(root, "Q99", "Accounts", "How have accounts moved?", "", "fixture")
                AdaptivePlanner(root, store).reconcile()
                retriage = store.task(f"facts.retriage.{request['id']}")
                self.assertEqual(("retriage", "ready"), (retriage["task_type"], retriage["state"]))


class BatchIdentityTests(unittest.TestCase):
    def test_rereading_the_same_span_for_changed_text_or_a_new_pass_is_a_new_batch(self) -> None:
        span = {"source_id": "SRC-1", "token_start": 0, "token_end": 100, "sha256": "aaa"}
        first = _batch_id([span])
        self.assertNotEqual(first, _batch_id([{**span, "sha256": "bbb"}]))
        self.assertNotEqual(first, _batch_id([{**span, "pass": "2026-10-27T14:48:19Z"}]))
        self.assertEqual(first, _batch_id([dict(span)]))


class SupplementBatchTests(unittest.TestCase):
    def test_supplement_keeps_finished_batches_and_replaces_unfinished_ones(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy_template(root)
            state = initialize(root, "https://example.com")
            save_state(root, state)
            atomic_write_json(root / "tools/lists/supplement-sources.json", {"sources": {"SRC-1": "recaptured", "SRC-2": "recaptured"}})
            old = {"id": "SRC-1", "source_id": "SRC-1", "path": "s/SRC-1.txt", "token_start": 0, "token_end": 10, "sha256": "old"}
            stopped = {**old, "id": "SRC-2", "source_id": "SRC-2", "path": "s/SRC-2.txt"}
            with RuntimeStore(root) as store:
                store.initialize(run_id=state["run_id"], company_url=state["company_url"])
                for task_id, item in (("facts.extract.done", old), ("facts.extract.stopped", stopped)):
                    store.add_task(WorkItem(
                        task_id=task_id, phase="facts", task_type="extraction", inputs=[item],
                        outputs=[f"parts/{task_id}.jsonl"], prompt_files=["prompts/phases/extraction.md"],
                    ))
                store.claim("w", task_id="facts.extract.done")
                store.start("facts.extract.done", "w")
                (root / "parts").mkdir()
                (root / "parts/facts.extract.done.jsonl").write_text("{}\n", encoding="utf-8")
                store.complete("facts.extract.done", "w")
                slices = [{**old, "sha256": "new"}, {**stopped, "sha256": "new"}]
                kept, uncovered = AdaptivePlanner(root, store)._unchanged_batches(slices)
                # The finished batch's facts stand and the new text is extracted again;
                # the unfinished batch over changed text is not kept.
                self.assertEqual(["facts.extract.done"], kept)
                self.assertEqual({"SRC-1", "SRC-2"}, {item["id"] for item in uncovered})
                # Unchanged text is covered by a finished batch, unless the source was
                # listed again after that batch was planned (a new question or rules).
                unchanged = [old, {**stopped, "sha256": "new"}]
                kept, uncovered = AdaptivePlanner(root, store)._unchanged_batches(unchanged)
                self.assertNotIn("SRC-1", {item["id"] for item in uncovered})
                atomic_write_json(root / "tools/lists/supplement-sources.json", {
                    "sources": {"SRC-1": "again for Q13"}, "added_at": {"SRC-1": "2999-01-01T00:00:00Z"},
                })
                kept, uncovered = AdaptivePlanner(root, store)._unchanged_batches(unchanged)
                self.assertEqual(["facts.extract.done"], kept)
                self.assertIn("SRC-1", {item["id"] for item in uncovered})


class AlternateCopiesTests(unittest.TestCase):
    def test_blocked_captures_get_alternate_passes_before_the_manifest(self) -> None:
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
                    "company_site", ["https://example.com/press"], discovered_from="homepage",
                    evidence="fixture", record_pass=False,
                )
                engine.add_candidates(
                    "video", ["https://www.youtube.com/watch?v=abcdefghijk"], discovered_from="channel",
                    evidence="fixture", record_pass=False,
                )
                AdaptivePlanner(root, store).reconcile()
                for channel in DISCOVERY_CHANNELS:
                    for number in (1, 2):
                        engine.add_candidates(channel, [], discovered_from=f"p{number}", evidence=f"{channel} pass {number}")
                    _write_receipt(root, store, channel)
                    worker = RUNTIME_WORKER if channel in RUNTIME_DISCOVERY_CHANNELS else f"w-{channel}"
                    store.claim(worker, task_id=discovery_task_id(channel))
                    store.start(discovery_task_id(channel), worker)
                    store.complete(discovery_task_id(channel), worker)
                AdaptivePlanner(root, store).reconcile()
                reduce_discovery(root, store)
                store.claim(RUNTIME_WORKER, task_id="capture.reduce-discovery")
                store.start("capture.reduce-discovery", RUNTIME_WORKER)
                store.complete("capture.reduce-discovery", RUNTIME_WORKER)
                captures = [task for task in store.tasks(phase="capture") if task["task_type"] == "capture"]
                video = next(task for task in captures if "youtube" in task["inputs"][0]["url"])

                def finish(task: dict, status: str) -> None:
                    source_id = task["metadata"]["source_id"]
                    directory_path = root / "01-sources/captures" / source_id
                    directory_path.mkdir(parents=True, exist_ok=True)
                    (directory_path / "content.txt").write_text("text\n", encoding="utf-8")
                    atomic_write_json(root / task["metadata"]["receipt"], {
                        "source_id": source_id, "status": status, "reason": "HTTP Error 403: Forbidden",
                        "canonical_text_ready": status == "captured",
                        "local_paths": [str((directory_path / "content.txt").relative_to(root))],
                        "source": {"id": source_id, "grade": "P", "title": "t", "publisher": "p",
                                   "url": store.source(source_id)["canonical_url"], "date published": "",
                                   "date last modified": "", "date captured": "2026-10-27",
                                   "local file": str((directory_path / "content.txt").relative_to(root)),
                                   "method": "fixture", "notes": ""},
                    })
                    store.claim(RUNTIME_WORKER, task_id=task["task_id"])
                    store.start(task["task_id"], RUNTIME_WORKER)
                    store.complete(task["task_id"], RUNTIME_WORKER)

                for task in captures:
                    if task is video:
                        continue
                    url = store.source(task["metadata"]["source_id"])["canonical_url"]
                    finish(task, "blocked" if url.endswith("/press") else "captured")
                AdaptivePlanner(root, store).reconcile()
                # The first pass starts while the video is still transcribing.
                alternates = store.task("capture.alternate-copies")
                self.assertIsNotNone(alternates)
                self.assertIsNone(store.task("capture.reduce-captures"))
                blocked_id = next(
                    task["metadata"]["source_id"] for task in captures
                    if store.source(task["metadata"]["source_id"])["canonical_url"].endswith("/press")
                )
                row = engine.add_alternate(blocked_id, "https://wire.example.org/release", "wire copy of the release")
                self.assertEqual("admitted", row["outcome"])
                # The alternate does not reopen the original's channel.
                self.assertEqual("saturated", store.discovery_channel("company_site")["state"])
                AdaptivePlanner(root, store).reconcile()
                alternate_capture = store.task(f"capture.source.{row['alternate_source_id'].casefold()}")
                self.assertIsNotNone(alternate_capture)
                self.assertEqual("ready", alternate_capture["state"])

                # The video ends blocked after the first pass: a second pass covers it.
                finish(video, "blocked")
                finish(alternate_capture, "captured")
                store.claim("w-alt", task_id="capture.alternate-copies")
                store.start("capture.alternate-copies", "w-alt")
                store.complete("capture.alternate-copies", "w-alt")
                AdaptivePlanner(root, store).reconcile()
                second = store.task("capture.alternate-copies.2")
                self.assertIsNotNone(second)
                listed = [row["source_id"] for row in load_jsonl(root / "tools/lists/blocked-sources-2.jsonl")]
                self.assertEqual([video["metadata"]["source_id"]], listed)
                self.assertIsNone(store.task("capture.reduce-captures"))


    def test_reopening_a_phase_reopens_the_completed_phases_after_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy_template(root)
            state = initialize(root, "https://example.com")
            for phase in ("bootstrap", "scope", "capture", "facts", "initial_synthesis"):
                state["phases"][phase]["status"] = "complete"
            state["phases"]["verification"]["status"] = "ready"
            save_state(root, state)
            reopen_phase(root, "capture", "a recapture was requested")
            phases = load_state(root)["phases"]
            self.assertEqual("ready", phases["capture"]["status"])
            self.assertEqual("pending", phases["facts"]["status"])
            self.assertEqual("pending", phases["initial_synthesis"]["status"])
            self.assertEqual("complete", phases["scope"]["status"])
            self.assertEqual("capture", current_phase(root))
            self.assertIn("later phases reopened: facts, initial_synthesis", (root / "RUN_HISTORY.md").read_text(encoding="utf-8"))

def _write_receipt(root: Path, store: RuntimeStore, channel: str) -> None:
    current = store.discovery_channel(channel)
    atomic_write_json(root / "tools/outputs/worker-parts/discovery" / f"{channel.replace('_', '-')}.json", {
        "schema_version": "1.0.0", "channel": channel, "status": current["state"],
        "passes": current["total_passes"], "new_sources": current["total_new_sources"],
        "evidence": current["completion_evidence"],
    })

if __name__ == "__main__":
    unittest.main()
