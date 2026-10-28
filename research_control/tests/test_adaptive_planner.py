from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research_control import adaptive, verification
from research_control.discovery import DISCOVERY_CHANNELS, DiscoveryEngine
from research_control.automatic import RUNTIME_WORKER
from research_control.cli import _require_discovery_lease
from research_control.dispatch import emit_ready_packets
from research_control.io import atomic_write_json, atomic_write_jsonl, atomic_write_text, load_json, load_jsonl, workflow
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
    def test_source_changes_requeue_verification_in_automatic_run(self) -> None:
        for change in ("context", "delete", "new-transcript", "manifest"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                copy_template(root)
                state = initialize(root, "https://example.com")
                for phase in state["phases"]:
                    if phase == "verification":
                        state["phases"][phase]["status"] = "ready"
                        break
                    state["phases"][phase]["status"] = "complete"
                save_state(root, state)
                atomic_write_text(root / "02-facts/product.md",
                                  "| Fact ID | Claim | Verbatim quote | Source ID | Location | Source date | Grade |\n"
                                  "|---|---|---|---|---|---|---|\n"
                                  "| PRD-001 | Acme builds agents. | We build agents | SRC-A | line 1 | 2026-01-01 | P |\n")
                atomic_write_text(root / "05-synthesis/offering.md", "Acme builds agents [PRD-001].\n")
                manifest = root / "01-sources/MANIFEST.csv"
                manifest_text = ("id,url,grade,local file\n"
                                 "SRC-A,https://example.com,P,01-sources/captures/SRC-A/content.txt\n")
                atomic_write_text(manifest, manifest_text)
                capture = root / "01-sources/captures/SRC-A/content.txt"
                original = "We build agents.\n" + "Background context.\n" * 300
                atomic_write_text(capture, original + "Currently available.\n")

                # Exercise the real planner, scheduler, automatic preparation and reduction.
                # Only the unrelated GitHub phase-archive requirement is stubbed.
                with patch("research_control.adaptive.ensure_conversation_pushed", return_value={"on_remote": True}):
                    initial = adaptive.advance(root)
                    self.assertEqual("work_ready", initial["status"], initial)
                    self.assertEqual(1, initial["automatic"]["executed"])
                    with RuntimeStore(root) as store:
                        shard = next(task for task in store.tasks() if task["task_type"] == "verification")
                        store.claim("verifier", task_id=shard["task_id"])
                        store.start(shard["task_id"], "verifier")
                    atomic_write_jsonl(root / shard["metadata"]["part"], [{
                        "fact_id": "PRD-001", "verdict": "confirmed", "reason": "The quote supports the claim.",
                        "evidence_paths": [str(capture.relative_to(root))],
                    }])
                    adaptive.complete_work(root, shard["task_id"], "verifier")
                    adaptive.advance(root)
                    with RuntimeStore(root) as store:
                        self.assertEqual("succeeded", store.task("verification.reduce-verdicts")["state"])
                    prior_fingerprint = load_json(root / verification.PACKET_INDEX)["facts"]["PRD-001"]["fingerprint"]

                    if change == "context":
                        atomic_write_text(capture, original + "Historical offering; no longer available.\n")
                    elif change == "delete":
                        capture.unlink()
                    elif change == "new-transcript":
                        atomic_write_text(capture.with_name("transcript.txt"), "Only a demo, not a product.\n")
                    else:
                        atomic_write_text(manifest, manifest_text.replace("https://example.com", "https://example.com/archive"))

                    refreshed = adaptive.advance(root)
                    self.assertEqual("work_ready", refreshed["status"], refreshed)
                    self.assertIn("verification.prepare", refreshed["stale"])
                    self.assertIn(shard["task_id"], refreshed["stale"])
                    self.assertIn("verification.reduce-verdicts", refreshed["stale"])
                    self.assertEqual(1, refreshed["automatic"]["executed"])
                    self.assertEqual([], load_jsonl(root / verification.REUSED))
                    self.assertNotEqual(prior_fingerprint, load_json(root / verification.PACKET_INDEX)["facts"]["PRD-001"]["fingerprint"])
                    with RuntimeStore(root) as store:
                        self.assertEqual(2, store.task("verification.prepare")["attempt_count"])
                        self.assertEqual("ready", store.task(shard["task_id"])["state"])
                        self.assertEqual("planned", store.task("verification.reduce-verdicts")["state"])

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
                # An unfinished batch planned before its source was listed again is replaced.
                atomic_write_json(root / "tools/lists/supplement-sources.json", {
                    "sources": {"SRC-2": "again"}, "added_at": {"SRC-2": "2999-01-01T00:00:00Z"},
                })
                kept, uncovered = AdaptivePlanner(root, store)._unchanged_batches([old, stopped])
                self.assertNotIn("facts.extract.stopped", kept)
                self.assertIn("SRC-2", {item["id"] for item in uncovered})
                # A slice the orchestrator deferred drops its pending batch; a finished one stands.
                atomic_write_json(root / "tools/lists/supplement-sources.json", {"sources": {}})
                atomic_write_json(root / "tools/lists/deferred-slices.json", {"slices": {
                    "SRC-2": {"sha256": "old", "reason": "token budget"}, "SRC-1": {"sha256": "old", "reason": "token budget"},
                }})
                kept, uncovered = AdaptivePlanner(root, store)._unchanged_batches([old, stopped])
                self.assertEqual(["facts.extract.done"], kept)
                self.assertEqual(["SRC-2"], [item["id"] for item in uncovered])


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


class SupplementReconcileTests(unittest.TestCase):
    def test_supplement_is_reconciled_per_synthesis_file_from_a_digest(self) -> None:
        from research_control.automatic import HANDLERS
        from research_control.io import atomic_write_text

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy_template(root)
            state = initialize(root, "https://example.com")
            save_state(root, state)
            header = "| Fact ID | Claim | Verbatim quote | Source ID | Location | Source date | Grade | Topics | About | Said by | Notes |\n|---|---|---|---|---|---|---|---|---|---|---|\n"
            atomic_write_text(root / "02-facts/q01-product-architecture.md", header
                + "| PRD-001 | Old fact. | q | SRC-1 | l | 2026-01-01 | P | Q1 | Tribe | Tribe | |\n"
                + "| PRD-002 | Scorer added. | q2 | SRC-1 | l | 2026-05-01 | P | Q1 | Tribe | Tribe | Shipped. |\n")
            atomic_write_text(root / "02-facts/q13-accounts-engagements.md", header
                + "| ACC-001 | Phase 2 pitched. | q3 | SRC-1 | l | 2026-06-01 | I | Q13 | Tribe | Tribe | Relationship basis: Stated |\n")
            atomic_write_text(root / "05-synthesis/product-map.md", "# Product map\n\nA tool [PRD-001].\n")
            atomic_write_json(root / "tools/lists/supplement-sources.json", {"sources": {"SRC-1": "recaptured"}})
            with RuntimeStore(root) as store:
                store.initialize(run_id=state["run_id"], company_url=state["company_url"])
                store.add_task(WorkItem(
                    task_id="initial_synthesis.synthesize", phase="initial_synthesis", task_type="synthesis",
                    inputs=[], outputs=["05-synthesis/product-map.md"], prompt_files=["p.md"],
                ))
                store.claim("w", task_id="initial_synthesis.synthesize")
                store.start("initial_synthesis.synthesize", "w")
                store.complete("initial_synthesis.synthesize", "w")
                created = AdaptivePlanner(root, store)._plan_supplement()
                base = next(task_id for task_id in created if task_id.endswith(".reduce")).removesuffix(".reduce")
                self.assertIn(f"{base}.product-map", created)
                self.assertIn(f"{base}.customers-proof", created)
                self.assertIn(f"{base}.inference-catalogue", created)
                digest = (root / "tools/digests/supplement/product-map.md").read_text(encoding="utf-8")
                self.assertIn("PRD-002 · 2026-05-01 · P · SRC-1 · Tribe · Scorer added. [Shipped]", digest)
                self.assertNotIn("PRD-001", digest)
                self.assertIn("[relationship Stated]", (root / "tools/digests/supplement/customers-proof.md").read_text(encoding="utf-8"))
                # The report is written by the runtime: worker decisions, then the rest left uncited.
                identifier = base.rsplit("-", 1)[1]
                atomic_write_jsonl(root / f"tools/outputs/worker-parts/supplement/{identifier}.product-map.jsonl", [
                    {"fact_id": "PRD-002", "decision": "adds", "passage": "Scorer", "why": "built and shipped"},
                ])
                result = HANDLERS["supplement_reducer"](root, store, store.task(f"{base}.reduce"))
                self.assertEqual({"listed": 2, "cited": 1, "left uncited": 1}, result)
                report = (root / "06-checks/supplement-reconciliation.md").read_text(encoding="utf-8")
                self.assertIn("| PRD-002 | adds |", report)
                self.assertIn("| ACC-001 | left uncited |", report)


class ContentCutTests(unittest.TestCase):
    def test_an_inserted_section_changes_only_the_slices_around_it(self) -> None:
        from research_control.planner import _content_cuts

        sections = [f"--- FILE: src/module_{index}.py (40 lines) ---\n" + f"line {index}\n" * 300 for index in range(200)]
        before = "\n".join(sections)
        after = "\n".join(sections[:100] + ["--- FILE: src/new.py (40 lines) ---\n" + "new\n" * 900] + sections[100:])

        def pieces(text: str) -> list[str]:
            cuts = _content_cuts(text, 20_000, 60_000)
            self.assertEqual((0, len(text)), (cuts[0], cuts[-1]))
            self.assertTrue(all(0 < end - start <= 60_000 for start, end in zip(cuts, cuts[1:])))
            return [text[start:end] for start, end in zip(cuts, cuts[1:])]

        old, new = pieces(before), pieces(after)
        changed = [piece for piece in new if piece not in set(old)]
        # One or two slices hold the insertion; every other slice is byte-identical.
        self.assertLessEqual(len(changed), 2)
        self.assertGreater(len(new), 10)

    def test_a_finished_batch_covers_its_text_wherever_it_now_sits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy_template(root)
            state = initialize(root, "https://example.com")
            save_state(root, state)
            read = {"id": "SRC-1:part-0003", "source_id": "SRC-1", "path": "s/a.txt", "token_start": 100,
                    "token_end": 200, "sha256": "same-text", "cut": "sections"}
            with RuntimeStore(root) as store:
                store.initialize(run_id=state["run_id"], company_url=state["company_url"])
                store.add_task(WorkItem(
                    task_id="facts.extract.done", phase="facts", task_type="extraction", inputs=[read],
                    outputs=["parts/done.jsonl"], prompt_files=["prompts/phases/extraction.md"],
                ))
                store.claim("w", task_id="facts.extract.done")
                store.start("facts.extract.done", "w")
                (root / "parts").mkdir()
                (root / "parts/done.jsonl").write_text("{}\n", encoding="utf-8")
                store.complete("facts.extract.done", "w")
                # A file inserted earlier in the source moved the same text to part 4.
                moved = {**read, "id": "SRC-1:part-0004", "path": "s/b.txt", "token_start": 900, "token_end": 1000}
                fresh = {**read, "id": "SRC-1:part-0003", "path": "s/c.txt", "sha256": "inserted-text"}
                kept, uncovered = AdaptivePlanner(root, store)._unchanged_batches([fresh, moved])
                self.assertEqual(["facts.extract.done"], kept)
                self.assertEqual(["SRC-1:part-0003"], [item["id"] for item in uncovered])
                self.assertEqual("inserted-text", uncovered[0]["sha256"])


class ExtractionRoutingTests(unittest.TestCase):
    def test_code_reads_on_a_balanced_model_and_judgment_sources_on_a_strong_one(self) -> None:
        from research_control.routing import extraction_tier, source_kind

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy_template(root)
            code = "Repository: x/y\n\n--- FILE: app/score.py (3 lines) ---\ndef score(doc):\n    return 0.7\n" * 20
            book = ("Repository: x/y\n\n--- FILE: accounts/book.md (9 lines) ---\n"
                    "| Client | Deal | Budget | Pipeline |\n| Acme | Phase 2 proposal | $5M | renewal meeting |\n") * 20
            self.assertEqual("recording", source_kind("[00:00:01] hello", ["01-sources/captures/S/transcript.txt"]))
            self.assertEqual("page", source_kind("Tribe builds agents for enterprises.", ["content.txt"]))
            self.assertEqual("repository", source_kind(code, ["content.txt"]))
            self.assertEqual("business_records", source_kind(book, ["content.txt"]))
            self.assertEqual(("standard", "strong"), (extraction_tier(root, "repository"), extraction_tier(root, "business_records")))
            route = model_route(root, "extraction", {"model_tier": "standard"})
            self.assertEqual(("standard", "medium"), (route["tier"], route["effort"]))
            self.assertEqual("strong", model_route(root, "extraction")["tier"])


class BudgetAndFocusTests(unittest.TestCase):
    def test_budget_keeps_the_most_relevant_slices_and_focus_skips_unrelated_ones(self) -> None:
        from research_control.io import atomic_write_text
        from research_control.supplement import add_supplement, deferred_slices

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy_template(root)
            state = initialize(root, "https://example.com")
            save_state(root, state)
            atomic_write_text(root / "00-scope.md", "# Scope\n\n**Q1. Pricing and packaging.** What does it charge for workshops?\n\n"
                                                    "**Q2. Accounts and renewals.** Which clients renewed their engagements?\n")
            texts = {
                "SRC-A:part-0001": "Workshop pricing and packaging: workshops charge per seat. " * 40,
                "SRC-B:part-0001": "The clients renewed their engagements; renewals grew. " * 40,
                "SRC-C:part-0001": "def helper(x):\n    return x + 1\n" * 40,
            }
            slices = []
            for identifier, text in texts.items():
                path = f"tools/extracts/slices/{identifier.replace(':', '.')}.txt"
                atomic_write_text(root / path, text)
                slices.append({"id": identifier, "source_id": identifier.split(":")[0], "path": path,
                               "estimated_tokens": 600, "token_start": 0, "token_end": 600, "sha256": identifier})
            with RuntimeStore(root) as store:
                store.initialize(run_id=state["run_id"], company_url=state["company_url"])
                planner = AdaptivePlanner(root, store)
                # Without a budget everything is planned.
                self.assertEqual(3, len(planner._within_budget(slices, [])))
                atomic_write_json(root / "tools/lists/runtime-limits.json", {"extraction_token_budget": 1200})
                planned = planner._within_budget(slices, [])
                self.assertEqual({"SRC-A:part-0001", "SRC-B:part-0001"}, {item["id"] for item in planned})
                self.assertEqual(["SRC-C:part-0001"], [key for key, value in deferred_slices(root).items() if value["by"] == "budget"])
                self.assertIn("deferred 1 slices", (root / "06-checks/extraction-budget.md").read_text(encoding="utf-8"))
                # Raising the budget brings the deferred slice back.
                atomic_write_json(root / "tools/lists/runtime-limits.json", {"extraction_token_budget": 5000})
                self.assertEqual(3, len(planner._within_budget(slices, [])))
                self.assertEqual({}, deferred_slices(root))
                # A source listed again for Q2 reads only slices that bear on Q2, for Q2.
                add_supplement(root, ["SRC-A", "SRC-B"], "Q2 added", focus=["Q2"])
                focused = planner._focus(slices)
                self.assertEqual(["SRC-B:part-0001", "SRC-C:part-0001"], [item["id"] for item in focused])
                self.assertEqual(["Q2"], focused[0]["focus_questions"])
                self.assertNotIn("focus_questions", focused[1])
                self.assertEqual("focus", deferred_slices(root)["SRC-A:part-0001"]["by"])


class WorkerBriefTests(unittest.TestCase):
    def test_every_packet_comes_with_a_brief_the_host_passes_on_unchanged(self) -> None:
        from research_control.dispatch import write_packet
        from research_control.io import atomic_write_text

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy_template(root)
            state = initialize(root, "https://example.com")
            save_state(root, state)
            atomic_write_text(root / "00-scope.md", "# Scope\n\n## Notes for downstream phases\n\n- Treat X as internal tooling.\n")
            with RuntimeStore(root) as store:
                store.initialize(run_id=state["run_id"], company_url=state["company_url"])
                atomic_write_text(root / "tools/extracts/slices/SRC-1.part-0001.txt", "We build agents.\n")
                store.add_task(WorkItem(
                    task_id="facts.extract.abc", phase="facts", task_type="extraction",
                    inputs=[{"id": "SRC-1:part-0001", "path": "tools/extracts/slices/SRC-1.part-0001.txt"},
                            {"id": "facts", "path": "02-facts/*.md"}],
                    outputs=["parts/abc.jsonl"], prompt_files=["prompts/core/runtime.md", "prompts/core/evidence.md",
                                                               "prompts/phases/extraction.md"],
                    metadata={"model_tier": "standard"},
                ))
                entry = write_packet(root, store.task("facts.extract.abc"))
            brief = (root / entry["brief"]).read_text(encoding="utf-8")
            # One file holds the steps, the task's instructions, and what it reads.
            self.assertIn("## The task's instructions", brief)
            # Long material first, then the instructions and how to finish, read last before working.
            self.assertLess(brief.index("=== FILE: tools/extracts/slices/"), brief.index("## The task's instructions"))
            self.assertLess(brief.index("## The task's instructions"), brief.index("## Run notes"))
            self.assertLess(brief.index("## Run notes"), brief.index("work check facts.extract.abc"))
            self.assertIn("=== FILE: tools/extracts/slices/SRC-1.part-0001.txt ===\nWe build agents.", brief)
            self.assertIn("- `02-facts/*.md`", brief)
            # Each task carries only the rules it uses: extraction gets receipts, not browsing or citation meaning.
            self.assertIn("## Fact receipts", brief)
            # American English reaches every worker: the shared rules and the brief's own finishing steps.
            self.assertIn("## American English", brief)
            self.assertIn("Write everything you author in American English", brief)
            self.assertNotIn("## Browsing", brief)
            self.assertNotIn("## Citation meaning", brief)
            self.assertNotIn("<!-- only:", brief)
            # What is not included is named before the instructions, so a worker knows to open it.
            self.assertLess(brief.index("Not included in this file"), brief.index("=== FILE: tools/extracts/slices/"))
            self.assertIn("Open any other file you need to judge well", brief)
            # A brief whose copy of an input went out of date is caught.
            from research_control.dispatch import brief_out_of_date

            self.assertEqual([], brief_out_of_date(root, "facts.extract.abc"))
            atomic_write_text(root / "tools/extracts/slices/SRC-1.part-0001.txt", "We build agents and tools.\n")
            self.assertEqual(["tools/extracts/slices/SRC-1.part-0001.txt"], brief_out_of_date(root, "facts.extract.abc"))
            self.assertEqual("standard", entry["model_route"]["tier"])
            self.assertIn("work claim facts.extract.abc --worker-id w-abc", brief)
            self.assertIn("work check facts.extract.abc", brief)
            self.assertIn("Treat X as internal tooling.", brief)
            self.assertIn("--effort medium", brief)

    def test_every_task_type_gets_the_rules_it_must_apply(self) -> None:
        import json

        from research_control.dispatch import _prompt

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy_template(root)
            document = json.loads((root / "WORKFLOW.yaml").read_text(encoding="utf-8"))
            carriers = {
                task["task_type"] for profile in document["execution_profiles"].values()
                for task in profile.get("tasks", []) if "prompts/core/evidence.md" in task.get("cores", [])
            }
            # Client marks (stated, inferred, lead) apply wherever a client can appear, diagrams included.
            exempt = {"scope", "triage", "capture"}
            for task_type in sorted(carriers - exempt):
                self.assertIn("## Claim discipline", _prompt(root, "prompts/core/evidence.md", task_type), task_type)
            for task_type in ("diagram_builder", "orchestrator_page_review", "brief_writer", "diagram_modeler", "findings"):
                text = _prompt(root, "prompts/core/evidence.md", task_type)
                self.assertIn("## Currency", text, task_type)
                self.assertIn("diagram label", text, task_type)

    def test_the_report_is_planned_from_findings_before_it_is_written(self) -> None:
        import json

        document = json.loads((SOURCE_ROOT / "WORKFLOW.yaml").read_text(encoding="utf-8"))
        final = {task["id"]: task for task in document["execution_profiles"]["final"]["tasks"]}
        findings = final["findings"]
        # The findings step reads the reviewed synthesis and the digests after the outline exists.
        self.assertEqual(("findings", "prompts/phases/findings.md", ["report-outline"], ["05-synthesis/findings.md"]),
                         (findings["task_type"], findings["prompt"], findings["depends_on"], findings["outputs"]))
        self.assertTrue(any(item["path"].startswith("tools/digests/") for item in findings["inputs"]))
        # The writer and the diagram modeler follow its plan, and the report is not done without it.
        self.assertIn("findings", final["write-brief"]["depends_on"])
        self.assertIn("findings", final["model-diagrams"]["depends_on"])
        tiers = document["adaptive_runtime"]["model_routing"]["tiers"]
        self.assertIn("findings", tiers["frontier"]["task_types"])
        gates = [phase["gate"] for phase in document["phases"] if "gate" in phase and "brief_writer" in phase["gate"].get("required_worker_task_types", [])]
        self.assertTrue(gates and all("findings" in gate["required_worker_task_types"] for gate in gates))
        prompt = (SOURCE_ROOT / "prompts/phases/findings.md").read_text(encoding="utf-8")
        for words in ("05-synthesis/findings.md", "report plan", "say once", "describe the same thing"):
            self.assertIn(words, prompt.lower() if words == "say once" else prompt, words)
        writer = (SOURCE_ROOT / "prompts/phases/brief-writing.md").read_text(encoding="utf-8")
        self.assertIn("Read `05-synthesis/findings.md` first", writer)
        self.assertIn("states the thing itself", writer)


class GateRefreshTests(unittest.TestCase):
    def test_only_gates_stale_from_moved_inputs_are_rechecked(self) -> None:
        from unittest import mock

        from research_control import PASS, adaptive

        stale = {"failures": [], "unknowns": ["dependency gate capture: stale input WORKFLOW.yaml"]}
        mixed = {"failures": ["fact_quotes: PRD-1 quote not found"], "unknowns": stale["unknowns"]}
        with mock.patch.object(adaptive, "check_phase", return_value=({"status": PASS}, Path("g.json"))) as check, \
                mock.patch.object(adaptive, "set_phase_result") as record, \
                mock.patch.object(adaptive, "phase_order", return_value=["capture", "facts"]):
            self.assertTrue(adaptive._refresh_dependency_gates(Path("."), stale))
            check.assert_called_once_with(Path("."), "capture", update_state=False)
            record.assert_called_once_with(Path("."), "capture", PASS, "g.json")
            self.assertFalse(adaptive._refresh_dependency_gates(Path("."), mixed))
            self.assertEqual(1, check.call_count)


class AgentGroupTests(unittest.TestCase):
    def test_tasks_reading_the_same_files_share_a_worker_and_reviews_stay_separate(self) -> None:
        from research_control.dispatch import emit_ready_packets

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy_template(root)
            state = initialize(root, "https://example.com")
            save_state(root, state)
            with RuntimeStore(root) as store:
                store.initialize(run_id=state["run_id"], company_url=state["company_url"])
                shared = {"id": "capture", "path": "01-sources/captures/SRC-1/content.txt"}
                for task_id, task_type, inputs in (
                    ("facts.extract.a", "extraction", [shared, {"id": "scope", "path": "00-scope.md"}]),
                    ("facts.extract.b", "extraction", [shared]),
                    ("facts.extract.c", "extraction", [{"id": "other", "path": "01-sources/captures/SRC-2/content.txt"},
                                                       {"id": "scope", "path": "00-scope.md"}]),
                    ("review.technical", "technical_review", [{"id": "s", "path": "05-synthesis/offering.md"}]),
                    ("review.editor", "editor_review", [{"id": "s", "path": "05-synthesis/offering.md"}]),
                ):
                    store.add_task(WorkItem(task_id=task_id, phase="facts", task_type=task_type, inputs=inputs,
                                            outputs=[f"parts/{task_id}.jsonl"], prompt_files=["prompts/core/runtime.md"]))
                result = emit_ready_packets(root, store)
            groups = sorted(sorted(agent["tasks"]) for agent in result["agents"])
            self.assertEqual([["facts.extract.a", "facts.extract.b"], ["facts.extract.c"], ["review.editor"], ["review.technical"]], groups)
            shared_brief = next(agent["brief"] for agent in result["agents"] if len(agent["tasks"]) == 2)
            self.assertIn("read each shared file once", (root / shared_brief).read_text(encoding="utf-8"))


class ProfileDependencyTests(unittest.TestCase):
    def test_a_dependency_added_to_the_profile_after_a_task_finished_does_not_rerun_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            copy_template(root)
            state = initialize(root, "https://example.com")
            save_state(root, state)
            with RuntimeStore(root) as store:
                store.initialize(run_id=state["run_id"], company_url=state["company_url"])
                planner = AdaptivePlanner(root, store)
                for task_id in ("review.editor", "facts.reduce"):
                    store.add_task(WorkItem(task_id=task_id, phase="review", task_type="editor_review", inputs=[],
                                            outputs=[f"{task_id}.md"], prompt_files=["p.md"]))
                    store.claim("w", task_id=task_id, bypass_limits=True)
                    store.start(task_id, "w")
                    (root / f"{task_id}.md").write_text("done\n", encoding="utf-8")
                    store.complete(task_id, "w")
                store.add_task(WorkItem(task_id="review.check", phase="review", task_type="consistency_check",
                                        inputs=[], outputs=["check.md"], prompt_files=["p.md"]))

                def gained(task_id: str) -> WorkItem:
                    return WorkItem(task_id=task_id, phase="review", task_type="editor_review", inputs=[],
                                    outputs=[f"{task_id}.md"], prompt_files=["p.md"], depends_on=["review.check"])

                # The workflow profile gained a check before the reviews: finished reviews stand.
                planner._add(gained("review.editor"), [], from_profile=True)
                self.assertEqual("succeeded", store.task("review.editor")["state"])
                # A reducer that gained a new part to merge reruns once the part is done.
                planner._add(gained("facts.reduce"), [])
                self.assertNotEqual("succeeded", store.task("facts.reduce")["state"])
