from __future__ import annotations

import csv
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research_control import PASS
from research_control.checks import check_phase
from research_control.capture import capture_url
from research_control.cli import _refresh_release_evidence
from research_control.diagram_contract import DIAGRAM_CAPTIONS, DIAGRAM_MODEL_JSON, DIAGRAM_MODEL_MARKDOWN, DIAGRAM_SPECS, DIAGRAM_STYLE_MARKDOWN
from research_control.gates.release import check_release
from research_control.io import atomic_write_json, atomic_write_jsonl, atomic_write_text
from research_control.orchestration import (
    current_phase,
    fail_task,
    finish_task,
    initialize,
    load_state,
    next_packets,
    start_task,
)
from research_control.publication import make_pdf, render
from research_control.reporting import make_validation_report


SOURCE_ROOT = Path(__file__).resolve().parents[2]


def copy_template(target: Path) -> None:
    for name in ("README.md", "RESEARCH_CONSTITUTION.md", "WORKFLOW.yaml", "pyproject.toml"):
        shutil.copy2(SOURCE_ROOT / name, target / name)
    for name in ("docs", "prompts", "research_control", "tools"):
        shutil.copytree(SOURCE_ROOT / name, target / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def text(root: Path, relative: str, value: str = "complete\n") -> None:
    atomic_write_text(root / relative, value)


def jsonl(root: Path, relative: str, rows: list[dict]) -> None:
    atomic_write_jsonl(root / relative, rows)


def complete_task(root: Path, task_id: str, worker_id: str, writer) -> None:
    start_task(root, task_id, worker_id)
    writer()
    finish_task(root, task_id)


def static_test_reports(root: Path) -> None:
    for name in ("adaptive_runtime", "data_integrity", "evidence_pipeline", "citation_integrity", "execution_integrity", "release_integrity"):
        report = make_validation_report(
            checker=f"test_suite:{name}",
            checker_version="clean-room-fixture",
            status=PASS,
            expected_count=1,
            checked_count=1,
        )
        atomic_write_json(root / f"tools/outputs/tests/{name}.json", report)


def write_diagram_models(root: Path) -> None:
    entity = {
        "id": "ENT-001",
        "label": "Acme workflow software",
        "entity_type": "product",
        "owner_boundary": "company platform",
        "evidence_class": "D",
        "fact_ids": ["ACME-001"],
        "source_ids": ["SRC-001"],
        "reasoning_note": "",
    }
    models = []
    for spec in DIAGRAM_SPECS:
        models.append({
            "id": spec["id"],
            "title": spec["title"],
            "subtitle": spec["subtitle"],
            "question_answered": spec["subtitle"],
            "main_takeaway": "The evidence establishes one company product.",
            "entity_ids": ["ENT-001"],
            "relationship_ids": [],
            "structure": "A narrow evidence-bounded view.",
            "deliberate_omissions": [],
            "caveats": ["The clean-room fixture contains one fact."],
        })
    atomic_write_json(root / DIAGRAM_MODEL_JSON, {
        "entities": [entity],
        "relationships": [],
        "diagrams": models,
    })
    text(
        root,
        DIAGRAM_MODEL_MARKDOWN,
        "# Diagram models\n\n## Entity registry\n\nENT-001 — Acme workflow software. ACME-001; SRC-001.\n\n"
        "## Relationship registry\n\nNo supported relationship in the one-fact fixture.\n\n"
        "## Model 01\n\nENT-001\n\n## Model 02\n\nENT-001\n\n"
        "## Model 03\n\nENT-001\n\n## Model 04\n\nENT-001\n",
    )


def write_diagram_artifacts(root: Path) -> None:
    text(
        root,
        DIAGRAM_STYLE_MARKDOWN,
        "# Diagram style specification\n\n## Inputs and scope\nPresentation only; not evidence.\n\n"
        "## Semantic mapping\nFill encodes identity.\n\n## Connector channels\nLine pattern, arrowhead, "
        "written edge label, barred endpoint, and boundary annotation remain separate.\n\n"
        "## Typography and spacing\nUse 165 mm width and grayscale-safe spacing.\n\n"
        "## Designed extensions\nNone required.\n",
    )
    captions = ["# Diagram captions", ""]
    for spec in DIAGRAM_SPECS:
        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="165mm" height="90mm" viewBox="0 0 660 360">'
            f'<title>{spec["title"]}</title><desc>{spec["subtitle"]}</desc>'
            '<style>text{font-family:Arial,Helvetica,sans-serif}</style>'
            f'<text x="20" y="30">{spec["title"]}</text>'
            f'<text x="20" y="55">{spec["subtitle"]}</text>'
            '<g data-entity-id="ENT-001"><rect x="20" y="90" width="300" height="80" />'
            '<text x="35" y="135">Acme workflow software</text></g></svg>\n'
        )
        text(root, spec["path"], svg)
        captions.extend([
            f'## {spec["title"]}',
            "",
            spec["subtitle"],
            "",
            "The fixture supports a deliberately narrow view. Reference: ACME-001 / SRC-001.",
            "",
        ])
    text(root, DIAGRAM_CAPTIONS, "\n".join(captions))


def write_brand_guide(root: Path) -> None:
    text(
        root,
        "07-final-report/brand-guide.html",
        "<!doctype html><html lang=\"en-US\"><head><style>body{font-family:Arial,sans-serif}</style></head>"
        "<body><h1>Acme brand guide</h1><h2>Editorial diagrams and architecture graphics</h2>"
        "<p>Designed extension for diagrams.</p></body></html>\n",
    )
    make_pdf("# Acme brand guide\n\nEditorial diagrams and architecture graphics.\n", root / "07-final-report/brand-guide.pdf")
    text(root, "05-synthesis/brand-guide/evidence/source-map.md", "# Source map\n\nhttps://acme.example - primary marketing.\n")
    text(root, "05-synthesis/brand-guide/evidence/design-observations.md", "# Design observations\n\nObserved restrained blue and neutral palette.\n")
    text(root, "05-synthesis/brand-guide/evidence/asset-manifest.csv", "Source URL,Type,Usage,Evidence label,Dimensions,Delivery,Notes\nhttps://acme.example/logo.svg,logo,identity,Observed,unknown,remote,fixture\n")
    text(root, "05-synthesis/brand-guide/evidence/acceptance-check.md", "# Acceptance check\n\nPASS - desktop, mobile, and PDF inspected.\n")
    text(root, "05-synthesis/brand-guide/evidence/screenshots/guide-desktop.png", "fixture image\n")


class OperationalRunTests(unittest.TestCase):
    def setUp(self) -> None:
        self._renderer_environment = patch.dict(
            os.environ, {"RESEARCH_CONTROL_PDF_RENDERER": "stdlib"}
        )
        self._renderer_environment.start()

    def tearDown(self) -> None:
        self._renderer_environment.stop()

    def prepared(self, directory: str) -> Path:
        root = Path(directory)
        copy_template(root)
        initialize(root, "https://acme.example")
        static_test_reports(root)
        return root

    def test_init_packet_and_resume(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.prepared(directory)
            report, _ = check_phase(root, "bootstrap", run_tests=False)
            self.assertEqual(PASS, report["status"])
            packet = next_packets(root)
            self.assertEqual("scope", packet["phase"])
            self.assertEqual(["scope.scope"], [item["task_id"] for item in packet["pending"]])
            body = (root / packet["pending"][0]["packet"]).read_text(encoding="utf-8")
            self.assertIn("TASK TYPE: SCOPE", body)
            self.assertNotIn("## 19. Execution integrity", body)

            start_task(root, "scope.scope", "scope-worker")
            resumed = next_packets(root)
            self.assertEqual("scope", resumed["phase"])
            self.assertEqual("scope.scope", resumed["pending"][0]["task_id"])
            same_attempt = start_task(root, "scope.scope", "scope-worker")
            self.assertEqual(1, same_attempt["attempt"])
            fail_task(root, "scope.scope", "simulated interruption")
            retry = start_task(root, "scope.scope", "scope-worker")
            self.assertEqual(2, retry["attempt"])

    def test_dependency_free_renderer_removes_internal_fact_ids(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            text(root, "05-synthesis/company-brief.md", "# Company brief\n\nFocus: Product marketing\n\nA supported claim [ACME-001].\n")
            metadata = render(root)
            self.assertEqual(1, metadata["total_pages"])
            html = (root / "07-final-report/company-brief.html").read_text(encoding="utf-8")
            self.assertNotIn("ACME-001", html)
            self.assertTrue((root / "07-final-report/company-brief.pdf").read_bytes().startswith(b"%PDF-"))
            self.assertTrue(metadata["documents"]["company-brief"]["page_previews"])

    def test_capture_helper_rejects_private_network_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(PermissionError):
                capture_url(Path(directory), url="http://127.0.0.1/private", source_id="SRC-PRIVATE", grade="P")

    def test_clean_room_url_to_release_control_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = self.prepared(directory)
            report, _ = check_phase(root, "bootstrap", run_tests=False)
            self.assertEqual(PASS, report["status"])

            complete_task(
                root,
                "scope.scope",
                "scope-worker",
                lambda: text(
                    root,
                    "00-scope.md",
                    "# Scope\n\nCompany URL: https://acme.example\n\n## Inputs\nNo user inputs.\n\n## Source plan\nFirst-party and third-party evidence.\n\n## Competitors\nComparable workflow products.\n",
                ) or jsonl(root, "tools/outputs/input-classification.jsonl", [{
                    "assignment_id": "scope.scope", "input_id": "__none__", "disposition": "completed_zero",
                    "reason": "no user inputs", "evidence_paths": ["00-scope.md"], "output_ids": [],
                }]),
            )
            report, _ = check_phase(root, "scope", run_tests=False)
            self.assertEqual(PASS, report["status"])

            def write_capture() -> None:
                text(root, "01-sources/captures/SRC-001/content.txt", "Acme provides workflow software for operations teams.\n")
                manifest = root / "01-sources/MANIFEST.csv"
                manifest.parent.mkdir(parents=True, exist_ok=True)
                with manifest.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=[
                        "id", "grade", "title", "publisher", "url", "date published", "date last modified",
                        "date captured", "local file", "method", "notes",
                    ], lineterminator="\n")
                    writer.writeheader()
                    writer.writerow({
                        "id": "SRC-001", "grade": "P", "title": "Acme home", "publisher": "Acme",
                        "url": "https://acme.example", "date published": "2026-01-01", "date last modified": "",
                        "date captured": "2026-10-23", "local file": "01-sources/captures/SRC-001/content.txt",
                        "method": "fixture capture", "notes": "",
                    })
                text(root, "01-sources/publish-dates.csv", "id,date\nSRC-001,2026-01-01\n")
                text(root, "01-sources/BLOCKED.md", "# Blocked\n\nNone.\n")
                text(root, "06-checks/coverage.md", "# Coverage\n\nRequired surfaces covered.\n")
                text(root, "tools/lists/extraction-scope.csv", "SRC-001,all\n")
                jsonl(root, "tools/outputs/capture-dispositions.jsonl", [{
                    "assignment_id": "capture.capture", "input_id": "SRC-001", "disposition": "completed",
                    "reason": "captured", "evidence_paths": ["01-sources/captures/SRC-001/content.txt"],
                    "output_ids": ["SRC-001"],
                }])

            complete_task(root, "capture.capture", "capture-worker", write_capture)
            complete_task(root, "capture.brand-guide", "brand-guide-worker", lambda: write_brand_guide(root))
            report, _ = check_phase(root, "capture", run_tests=False)
            self.assertEqual(PASS, report["status"], report)

            def write_extraction() -> None:
                jsonl(root, "tools/candidates/all.jsonl", [{
                    "candidate_id": "CAND-001", "topic": "product", "claim": "Acme provides workflow software.",
                    "quote": "Acme provides workflow software for operations teams.", "source_id": "SRC-001",
                    "location": "content.txt, sentence 1", "source_date": "2026-01-01", "grade": "P",
                    "about": "Acme", "said_by": "Acme", "notes": "",
                }])
                jsonl(root, "tools/outputs/extraction-dispositions.jsonl", [{
                    "assignment_id": "facts.extract", "input_id": "SRC-001", "disposition": "completed",
                    "reason": "one candidate", "evidence_paths": ["tools/candidates/all.jsonl"],
                    "output_ids": ["CAND-001"],
                }])

            complete_task(root, "facts.extract", "extract-worker", write_extraction)

            def write_facts() -> None:
                text(
                    root,
                    "02-facts/product.md",
                    "# Product facts\n\n"
                    "| Fact ID | Claim | Verbatim quote | Source ID | Location | Source date | Grade | Topics | About | Said by | Verdict |\n"
                    "|---|---|---|---|---|---|---|---|---|---|---|\n"
                    "| ACME-001 | Acme provides workflow software. | Acme provides workflow software for operations teams. | SRC-001 | content.txt, sentence 1 | 2026-01-01 | P | product | Acme | Acme | confirmed |\n",
                )
                jsonl(root, "tools/outputs/filing-dispositions.jsonl", [{
                    "assignment_id": "facts.file-facts", "input_id": "CAND-001", "disposition": "completed",
                    "reason": "filed as product fact", "evidence_paths": ["02-facts/product.md"],
                    "output_ids": ["ACME-001"],
                }])
                text(root, "06-checks/script-audits.md", "# Script audit\n\nAll planted checks detected.\n")
                text(root, "06-checks/duplicate-spot-check.md", "# Duplicate spot check\n\nNo duplicates.\n")
                text(root, "06-checks/filter-spot-check.md", "# Filter spot check\n\nNo misses.\n")

            complete_task(root, "facts.file-facts", "filing-worker", write_facts)
            report, _ = check_phase(root, "facts", run_tests=False)
            self.assertEqual(PASS, report["status"], report)

            synthesis_names = (
                "product-map", "offering", "customers-proof", "competitors", "glossary",
                "messaging-timeline", "organization", "direction", "open-questions",
            )

            def write_synthesis() -> None:
                text(root, "tools/digests/company.md", "# Digest\n\nACME-001\n")
                text(root, "03-timelines/messaging.md", "# Timeline\n\n2026-01-01: Product evidence. ACME-001\n")
                text(root, "tools/outputs/currency.csv", "fact_id,status\nACME-001,current\n")
                for name in synthesis_names:
                    text(root, f"05-synthesis/{name}.md", f"# {name.replace('-', ' ').title()}\n\nAcme provides workflow software. ACME-001\n")
                text(root, "06-checks/currency-review.md", "# Currency review\n\nACME-001 is current as of 2026-01-01.\n")

            complete_task(root, "initial_synthesis.synthesize", "synthesis-worker", write_synthesis)
            report, _ = check_phase(root, "initial_synthesis", run_tests=False)
            self.assertEqual(PASS, report["status"], report)

            def write_verification() -> None:
                text(root, "tools/lists/cited-facts.txt", "ACME-001\n")
                atomic_write_json(root / "tools/outputs/cited-facts/index.json", {"fact_ids": ["ACME-001"]})
                text(root, "06-checks/verification-cited.md", "# Verification\n\nACME-001 confirmed.\n")
                jsonl(root, "tools/outputs/verification-verdicts.jsonl", [{
                    "fact_id": "ACME-001", "verdict": "confirmed", "reason": "exact quote supports claim",
                    "evidence_paths": ["01-sources/captures/SRC-001/content.txt", "02-facts/product.md"],
                }])

            complete_task(root, "verification.verify-cited-facts", "verification-worker", write_verification)
            report, _ = check_phase(root, "verification", run_tests=False)
            self.assertEqual(PASS, report["status"], report)

            def write_corrections() -> None:
                text(root, "06-checks/verification-corrections.md", "# Verification corrections\n\nNo wording change required.\n")
                jsonl(root, "tools/outputs/verification-corrections.jsonl", [{
                    "fact_id": "ACME-001", "disposition": "completed", "reason": "confirmed without correction",
                    "evidence_paths": ["06-checks/verification-cited.md"],
                }])

            complete_task(root, "corrected_synthesis.apply-verification", "verification-fixer", write_corrections)
            report, _ = check_phase(root, "corrected_synthesis", run_tests=False)
            self.assertEqual(PASS, report["status"], report)

            reviews = (
                ("technical", "technical-reviewer", "review-technical", "technical"),
                ("devils-advocate", "challenge-reviewer", "review-devils-advocate", "devils-advocate"),
                ("insider", "insider-reviewer", "review-insider", "insider"),
                ("editor", "editor-reviewer", "review-editor", "editor"),
            )
            for task, worker, basename, review_id in reviews:
                complete_task(
                    root,
                    f"review.{task}",
                    worker,
                    lambda basename=basename, review_id=review_id: (
                        text(root, f"06-checks/{basename}.md", f"# Review\n\n{review_id}: clean.\n"),
                        jsonl(root, f"tools/outputs/review-findings-{review_id}.jsonl", [{"review_id": review_id, "status": "clean"}]),
                    ),
                )

            complete_task(
                root,
                "review.apply-review",
                "review-fixer",
                lambda: (
                    text(root, "06-checks/review-decisions.md", "# Review decisions\n\nNo findings required changes.\n"),
                    jsonl(root, "tools/outputs/review-decisions.jsonl", [{"review_id": "all", "status": "clean"}]),
                ),
            )
            report, _ = check_phase(root, "review", run_tests=False)
            self.assertEqual(PASS, report["status"], report)

            citation_map = {
                "sources": {"SRC-001": {"url": "https://acme.example"}},
                "facts": {"ACME-001": {"source_ids": ["SRC-001"]}},
                "notes": [{"n": 1, "source_id": "SRC-001", "url": "https://acme.example"}],
                "citations": [{"n": 1, "facts": ["ACME-001"]}],
                "markdown_citations": [{"facts": ["ACME-001"]}],
            }

            def write_brief() -> None:
                text(root, "05-synthesis/company-brief.md", "# Company brief\n\nFocus: Product marketing\n\nAcme provides workflow software. ACME-001 [1]\n\n## Sources\n\n1. [Acme home](https://acme.example)\n")
                text(root, "05-synthesis/design-notes.md", "# Design notes\n\nUse a restrained editorial layout.\n")
                text(root, "05-synthesis/design/style.css", "h1 { color: #123b67; }\n")
                atomic_write_json(root / "tools/outputs/citation-map-company-brief.json", citation_map)
                atomic_write_json(root / "tools/outputs/exhibit-map.json", {"elements": [{"element_id": "portfolio", "fact_ids": ["ACME-001"], "evidence_bearing": True}]})

            complete_task(root, "final.write-brief", "brief-writer", write_brief)
            complete_task(root, "final.model-diagrams", "diagram-modeler", lambda: write_diagram_models(root))
            complete_task(root, "final.build-diagrams", "diagram-builder", lambda: write_diagram_artifacts(root))
            complete_task(root, "final.assemble", "assembler", lambda: render(root))
            report, _ = check_phase(root, "final", run_tests=False)
            self.assertEqual(PASS, report["status"], report)

            complete_task(
                root,
                "publication_checks.language",
                "language-reviewer",
                lambda: (
                    text(root, "06-checks/american-english.md", "# American English\n\nUse a company-specific document title.\n"),
                    jsonl(root, "tools/outputs/publication-findings-language.jsonl", [{
                        "finding_id": "PUB-LANG-001",
                        "review_id": "language",
                        "artifact": "07-final-report/company-brief.html",
                        "location": "document heading",
                        "severity": "low",
                        "finding": "The title is generic.",
                        "status": "open",
                    }]),
                ),
            )
            complete_task(
                root,
                "publication_checks.citation-a",
                "citation-reviewer-a",
                lambda: (
                    text(root, "06-checks/citation-claims-a.md", "# Citation claims A\n\nOne checked, zero problems.\n"),
                    text(root, "tools/outputs/citation-check-a.md", "# Citation check A\n\nPASS\n"),
                    jsonl(root, "tools/outputs/publication-findings-citation-a.jsonl", [{"review_id": "citation-a", "status": "clean"}]),
                ),
            )
            complete_task(
                root,
                "publication_checks.citation-b",
                "citation-reviewer-b",
                lambda: (
                    text(root, "06-checks/citation-claims-b.md", "# Citation claims B\n\nOne checked, zero problems.\n"),
                    text(root, "tools/outputs/citation-check-b.md", "# Citation check B\n\nPASS\n"),
                    text(root, "tools/outputs/exhibit-citation-check.md", "# Exhibit citations\n\nPASS\n"),
                    jsonl(root, "tools/outputs/publication-findings-citation-b.jsonl", [{"review_id": "citation-b", "status": "clean"}]),
                ),
            )

            def write_visual() -> None:
                metadata = json.loads((root / "tools/outputs/render-metadata.json").read_text(encoding="utf-8"))
                text(root, "06-checks/visual-review.md", f"# Visual review\n\nReviewed {metadata['total_pages']} pages; all clean.\n")
                atomic_write_json(root / "06-checks/visual-review.json", {
                    "pages": [{"page": page, "status": "clean", "issues": []} for page in range(1, metadata["total_pages"] + 1)],
                    "diagrams": [
                        {"diagram": spec["id"], "review_width_mm": 165, "status": "clean", "issues": []}
                        for spec in DIAGRAM_SPECS
                    ],
                    "brand_guide": {
                        "html": [
                            {"viewport": "desktop", "status": "clean", "issues": []},
                            {"viewport": "mobile", "status": "clean", "issues": []},
                        ],
                        "pdf_pages": [{"page": 1, "status": "clean", "issues": []}],
                    },
                })
                jsonl(root, "tools/outputs/publication-findings-visual.jsonl", [{"review_id": "visual", "status": "clean"}])

            complete_task(root, "publication_checks.visual", "visual-reviewer", write_visual)
            def write_publication_fix() -> None:
                brief_path = root / "05-synthesis/company-brief.md"
                brief = brief_path.read_text(encoding="utf-8").replace(
                    "# Company brief", "# Acme company brief", 1
                )
                atomic_write_text(brief_path, brief)
                text(root, "06-checks/publication-decisions.md", "# Publication decisions\n\nApplied PUB-LANG-001 by making the brief title company-specific.\n")
                jsonl(root, "tools/outputs/publication-decisions.jsonl", [{
                    "finding_id": "PUB-LANG-001",
                    "disposition": "apply",
                    "reason": "A specific title improves reader orientation without changing a claim.",
                    "evidence_paths": ["05-synthesis/company-brief.md", "07-final-report/company-brief.html"],
                }])
                render(root)

            complete_task(
                root,
                "publication_checks.apply-publication-fixes",
                "publication-fixer",
                write_publication_fix,
            )

            # The fixer rebuild invalidates the first review input hashes. The
            # same independent roles must complete a second bounded attempt.
            complete_task(
                root,
                "publication_checks.language",
                "language-reviewer",
                lambda: (
                    text(root, "06-checks/american-english.md", "# American English\n\nFinal artifacts clean.\n"),
                    jsonl(root, "tools/outputs/publication-findings-language.jsonl", [{
                        "finding_id": "PUB-LANG-001",
                        "review_id": "language",
                        "artifact": "07-final-report/company-brief.html",
                        "location": "document heading",
                        "severity": "low",
                        "finding": "The title was generic and is now company-specific.",
                        "status": "closed",
                    }]),
                ),
            )
            complete_task(
                root,
                "publication_checks.citation-a",
                "citation-reviewer-a",
                lambda: (
                    text(root, "06-checks/citation-claims-a.md", "# Citation claims A\n\nFinal artifact checked; zero problems.\n"),
                    text(root, "tools/outputs/citation-check-a.md", "# Citation check A\n\nPASS final\n"),
                    jsonl(root, "tools/outputs/publication-findings-citation-a.jsonl", [{"review_id": "citation-a", "status": "clean"}]),
                ),
            )
            complete_task(
                root,
                "publication_checks.citation-b",
                "citation-reviewer-b",
                lambda: (
                    text(root, "06-checks/citation-claims-b.md", "# Citation claims B\n\nFinal artifact checked; zero problems.\n"),
                    text(root, "tools/outputs/citation-check-b.md", "# Citation check B\n\nPASS final\n"),
                    text(root, "tools/outputs/exhibit-citation-check.md", "# Exhibit citations\n\nPASS final\n"),
                    jsonl(root, "tools/outputs/publication-findings-citation-b.jsonl", [{"review_id": "citation-b", "status": "clean"}]),
                ),
            )
            complete_task(root, "publication_checks.visual", "visual-reviewer", write_visual)
            complete_task(root, "publication_checks.page-acceptance", "orchestrator", lambda: text(root, "06-checks/final-report.md", "# Final report\n\nAll current artifacts and pages reviewed.\n"))
            report, _ = check_phase(root, "publication_checks", run_tests=False)
            self.assertEqual(PASS, report["status"], report)
            self.assertEqual("release_acceptance", current_phase(root))

            _refresh_release_evidence(root)
            release, _validation, manifest = check_release(root)
            self.assertEqual(PASS, release["status"], release)
            self.assertTrue(manifest.is_file())
            self.assertEqual(PASS, json.loads(manifest.read_text(encoding="utf-8"))["status"])
            self.assertEqual("release_acceptance", current_phase(root, load_state(root)))


if __name__ == "__main__":
    unittest.main()
