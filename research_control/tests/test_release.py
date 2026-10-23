from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from research_control import FAIL, PASS, UNKNOWN
from research_control.gates.release import FINAL_ARTIFACTS, check_release
from research_control.hashing import sha256_file
from research_control.tests.helpers import validation, worker, write_json, write_jsonl


class ReleaseTests(unittest.TestCase):
    def fixture(self, root: Path, include_visual: bool = True) -> Path:
        for relative in FINAL_ARTIFACTS:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"artifact {relative}\n", encoding="utf-8")
        (root / "out").mkdir()
        (root / "out/result.txt").write_text("done", encoding="utf-8")
        write_jsonl(root / "tools/outputs/worker-ledger.jsonl", [worker(root)])
        binding = validation(details={"artifact_hashes": {relative: sha256_file(root / relative) for relative in FINAL_ARTIFACTS}})
        write_json(root / "tools/outputs/validations/artifact-binding.json", binding)
        if include_visual:
            write_json(root / "tools/outputs/validations/visual-records.json", validation())
        gate = validation()
        gate.update({"gate": "final", "phase": "publication_checks", "dependency_gates": []})
        write_json(root / "tools/outputs/gates/final.json", gate)
        document = {
            "schema_version": "1.0.0",
            "global": {"ledger": "tools/outputs/worker-ledger.jsonl", "gate_directory": "tools/outputs/gates", "release_manifest": "07-final-report/release-manifest.json"},
            "phases": [{
                "id": "publication_checks", "depends_on": [], "gate": {"name": "final"},
                "reconciliations": [],
                "validators": ([{"id": "artifact_binding", "report": "tools/outputs/validations/artifact-binding.json"}] +
                               ([{"id": "visual_records", "report": "tools/outputs/validations/visual-records.json"}] if include_visual else [{"id": "visual_records", "report": "tools/outputs/validations/visual-records.json"}])),
            }],
        }
        workflow = root / "WORKFLOW.yaml"
        write_json(workflow, document)
        return workflow

    def test_exact_validated_artifacts_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = self.fixture(root)
            report, _, manifest = check_release(root, workflow)
            self.assertEqual(PASS, report["status"])
            self.assertTrue(manifest.is_file())
            self.assertNotIn("tests", json.loads(manifest.read_text(encoding="utf-8")))

    def test_changed_final_artifact_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = self.fixture(root)
            (root / FINAL_ARTIFACTS[0]).write_text("modified after validation", encoding="utf-8")
            report, _, manifest = check_release(root, workflow)
            self.assertEqual(FAIL, report["status"])
            self.assertFalse(manifest.exists())

    def test_missing_visual_record_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = self.fixture(root, include_visual=False)
            report, _, _ = check_release(root, workflow)
            self.assertEqual(UNKNOWN, report["status"])


if __name__ == "__main__":
    unittest.main()
