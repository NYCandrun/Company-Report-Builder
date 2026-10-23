from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from research_control import FAIL, PASS
from research_control.diagram_contract import DIAGRAM_CAPTIONS, DIAGRAM_MODEL_JSON, DIAGRAM_MODEL_MARKDOWN, DIAGRAM_SPECS, DIAGRAM_STYLE_MARKDOWN
from research_control.io import atomic_write_json, atomic_write_text
from research_control.validators import diagrams


def model() -> dict:
    return {
        "entities": [{
            "id": "ENT-001", "label": "Product", "entity_type": "product",
            "owner_boundary": "company platform", "evidence_class": "D",
            "fact_ids": ["ACME-001"], "source_ids": ["SRC-001"],
        }],
        "relationships": [],
        "diagrams": [{
            "id": spec["id"], "title": spec["title"], "subtitle": spec["subtitle"],
            "question_answered": spec["subtitle"], "main_takeaway": "One supported product.",
            "entity_ids": ["ENT-001"], "relationship_ids": [], "structure": "Narrow view.",
            "deliberate_omissions": [], "caveats": ["Fixture evidence is intentionally sparse."],
        } for spec in DIAGRAM_SPECS],
    }


def write_models(root: Path, value: dict) -> None:
    atomic_write_json(root / DIAGRAM_MODEL_JSON, value)
    ids = "\n".join(item["id"] for item in value["entities"] + value["relationships"])
    atomic_write_text(
        root / DIAGRAM_MODEL_MARKDOWN,
        f"# Models\n\n## Entity registry\n{ids}\n\n## Relationship registry\nNone.\n\n"
        "## Model 01\nENT-001\n## Model 02\nENT-001\n## Model 03\nENT-001\n## Model 04\nENT-001\n",
    )


def write_artifacts(root: Path) -> None:
    atomic_write_text(
        root / DIAGRAM_STYLE_MARKDOWN,
        "# Diagram style specification\n\n## Inputs and scope\nPresentation only; not evidence.\n\n"
        "## Semantic mapping\nFill encodes identity.\n\n## Connector channels\nLine pattern, arrowhead, "
        "written edge label, barred endpoint, and boundary annotation remain separate.\n\n"
        "## Typography and spacing\nUse 165 mm width and grayscale-safe spacing.\n\n"
        "## Designed extensions\nNone required.\n",
    )
    captions: list[str] = []
    for spec in DIAGRAM_SPECS:
        atomic_write_text(
            root / spec["path"],
            '<svg xmlns="http://www.w3.org/2000/svg" width="165mm" height="90mm" viewBox="0 0 660 360">'
            f'<title>{spec["title"]}</title><desc>{spec["subtitle"]}</desc>'
            '<style>text{font-family:Arial,Helvetica,sans-serif}</style>'
            f'<text>{spec["title"]}</text><text>{spec["subtitle"]}</text>'
            '<g data-entity-id="ENT-001"><rect width="100" height="50"/><text>Product</text></g></svg>\n',
        )
        captions.extend([spec["title"], spec["subtitle"]])
    atomic_write_text(root / DIAGRAM_CAPTIONS, "\n\n".join(captions) + "\n")


class DiagramValidatorTests(unittest.TestCase):
    def test_valid_models_and_editable_svgs_pass(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_models(root, model())
            write_artifacts(root)
            self.assertEqual(PASS, diagrams.validate_models(root, {"ACME-001"}, {"SRC-001"})["status"])
            self.assertEqual(PASS, diagrams.validate_artifacts(root)["status"])

    def test_noncanonical_title_fails_model_and_svg(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = model()
            value["diagrams"][0]["title"] = "A better marketing headline"
            write_models(root, value)
            write_artifacts(root)
            model_report = diagrams.validate_models(root, {"ACME-001"}, {"SRC-001"})
            self.assertEqual(FAIL, model_report["status"])
            self.assertTrue(any("title must be exactly" in item for item in model_report["failures"]))

            path = root / DIAGRAM_SPECS[0]["path"]
            atomic_write_text(path, path.read_text(encoding="utf-8").replace(
                DIAGRAM_SPECS[0]["title"], "A better marketing headline"
            ))
            artifact_report = diagrams.validate_artifacts(root)
            self.assertEqual(FAIL, artifact_report["status"])
            self.assertTrue(any("deterministic visible text" in item for item in artifact_report["failures"]))

    def test_raster_image_and_wrong_width_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_models(root, model())
            write_artifacts(root)
            path = root / DIAGRAM_SPECS[0]["path"]
            body = path.read_text(encoding="utf-8").replace('width="165mm"', 'width="1200px"')
            body = body.replace("</svg>", '<image href="preview.png"/></svg>')
            atomic_write_text(path, body)
            report = diagrams.validate_artifacts(root)
            self.assertEqual(FAIL, report["status"])
            self.assertTrue(any("width must be exactly 165mm" in item for item in report["failures"]))
            self.assertTrue(any("prohibited SVG elements" in item for item in report["failures"]))


if __name__ == "__main__":
    unittest.main()
