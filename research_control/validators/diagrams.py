"""Fail-closed validation for architecture models and editable SVG diagrams."""

from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from research_control.diagram_contract import (
    DIAGRAM_CAPTIONS,
    DIAGRAM_MODEL_JSON,
    DIAGRAM_MODEL_MARKDOWN,
    DIAGRAM_SPECS,
    DIAGRAM_STYLE_MARKDOWN,
)
from research_control.brand_contract import BRAND_GUIDE_HTML
from research_control.io import load_json

from .common import report_for


EVIDENCE_CLASSES = {"D", "R", "H", "U"}
DRAWABLE_CLASSES = {"D", "R"}


def _strings(value: Any) -> list[str]:
    return [str(item).strip() for item in value] if isinstance(value, list) else []


def _model_data(root: Path) -> tuple[dict[str, Any] | None, list[str]]:
    path = root / DIAGRAM_MODEL_JSON
    if not path.is_file() or not path.stat().st_size:
        return None, [f"missing or empty model registry: {DIAGRAM_MODEL_JSON}"]
    try:
        value = load_json(path)
    except Exception as error:
        return None, [f"unreadable model registry: {error}"]
    if not isinstance(value, dict):
        return None, ["model registry must be a JSON object"]
    return value, []


def validate_models(
    root: Path,
    known_fact_ids: set[str],
    known_source_ids: set[str],
    verified_fact_ids: set[str] | None = None,
) -> dict[str, Any]:
    patterns = [DIAGRAM_MODEL_MARKDOWN, DIAGRAM_MODEL_JSON, "02-facts/*.md", "01-sources/MANIFEST.csv"]
    data, failures = _model_data(root)
    markdown_path = root / DIAGRAM_MODEL_MARKDOWN
    markdown = markdown_path.read_text(encoding="utf-8", errors="replace") if markdown_path.is_file() else ""
    if not markdown.strip():
        failures.append(f"missing or empty auditable model: {DIAGRAM_MODEL_MARKDOWN}")
    if data is None:
        return report_for(sys.modules[__name__], "diagram_models", root, patterns, 1, 0, failures)

    entities = data.get("entities", [])
    relationships = data.get("relationships", [])
    diagrams = data.get("diagrams", [])
    if not isinstance(entities, list) or not entities:
        failures.append("entity registry must be a nonempty array")
        entities = []
    if not isinstance(relationships, list):
        failures.append("relationship registry must be an array")
        relationships = []
    if not isinstance(diagrams, list):
        failures.append("diagram registry must be an array")
        diagrams = []

    entity_ids: set[str] = set()
    entity_class: dict[str, str] = {}
    relationship_ids: set[str] = set()
    evidence_ids: set[str] = set()

    def check_evidence(record: dict[str, Any], label: str) -> str:
        evidence_class = str(record.get("evidence_class", ""))
        if evidence_class not in EVIDENCE_CLASSES:
            failures.append(f"{label}: invalid evidence class {evidence_class!r}")
        fact_ids = _strings(record.get("fact_ids", []))
        source_ids = _strings(record.get("source_ids", []))
        for fact_id in fact_ids:
            if fact_id not in known_fact_ids:
                failures.append(f"{label}: unknown fact ID {fact_id}")
            elif verified_fact_ids is not None and fact_id not in verified_fact_ids:
                failures.append(f"{label}: fact ID {fact_id} lacks an accepted verification verdict")
        for source_id in source_ids:
            if source_id not in known_source_ids:
                failures.append(f"{label}: unknown source ID {source_id}")
        if evidence_class in DRAWABLE_CLASSES and not (fact_ids or source_ids):
            failures.append(f"{label}: {evidence_class}-class record lacks a fact or source reference")
        if evidence_class in {"R", "H"} and not str(record.get("reasoning_note", "")).strip():
            failures.append(f"{label}: {evidence_class}-class record lacks a reasoning note")
        return evidence_class

    for index, entity in enumerate(entities, 1):
        if not isinstance(entity, dict):
            failures.append(f"entity {index}: must be an object")
            continue
        entity_id = str(entity.get("id", "")).strip()
        if not entity_id:
            failures.append(f"entity {index}: missing stable ID")
            continue
        if entity_id in entity_ids:
            failures.append(f"entity {entity_id}: duplicate stable ID")
        entity_ids.add(entity_id)
        evidence_ids.add(entity_id)
        for field in ("label", "entity_type", "owner_boundary"):
            if not str(entity.get(field, "")).strip():
                failures.append(f"entity {entity_id}: missing {field}")
        entity_class[entity_id] = check_evidence(entity, f"entity {entity_id}")

    relationship_class: dict[str, str] = {}
    for index, relationship in enumerate(relationships, 1):
        if not isinstance(relationship, dict):
            failures.append(f"relationship {index}: must be an object")
            continue
        relationship_id = str(relationship.get("id", "")).strip()
        if not relationship_id:
            failures.append(f"relationship {index}: missing stable ID")
            continue
        if relationship_id in relationship_ids or relationship_id in entity_ids:
            failures.append(f"relationship {relationship_id}: duplicate or colliding stable ID")
        relationship_ids.add(relationship_id)
        evidence_ids.add(relationship_id)
        for endpoint in ("source", "target"):
            value = str(relationship.get(endpoint, "")).strip()
            if value not in entity_ids:
                failures.append(f"relationship {relationship_id}: unknown {endpoint} entity {value!r}")
        for field in ("relationship", "direction", "qualifier", "scope"):
            if not str(relationship.get(field, "")).strip():
                failures.append(f"relationship {relationship_id}: missing {field}")
        relationship_class[relationship_id] = check_evidence(relationship, f"relationship {relationship_id}")

    specs = {spec["id"]: spec for spec in DIAGRAM_SPECS}
    model_ids: set[str] = set()
    for index, diagram in enumerate(diagrams, 1):
        if not isinstance(diagram, dict):
            failures.append(f"diagram {index}: must be an object")
            continue
        diagram_id = str(diagram.get("id", "")).strip()
        if diagram_id in model_ids:
            failures.append(f"diagram {diagram_id}: duplicate model")
        model_ids.add(diagram_id)
        spec = specs.get(diagram_id)
        if not spec:
            failures.append(f"diagram {diagram_id or index}: unexpected diagram ID")
            continue
        if diagram.get("title") != spec["title"]:
            failures.append(f"diagram {diagram_id}: title must be exactly {spec['title']!r}")
        if diagram.get("subtitle") != spec["subtitle"]:
            failures.append(f"diagram {diagram_id}: subtitle must be exactly {spec['subtitle']!r}")
        if diagram.get("question_answered") != spec["subtitle"]:
            failures.append(f"diagram {diagram_id}: question_answered must equal the deterministic subtitle")
        included_entities = _strings(diagram.get("entity_ids", []))
        included_relationships = _strings(diagram.get("relationship_ids", []))
        if not included_entities:
            failures.append(f"diagram {diagram_id}: has no entities")
        for entity_id in included_entities:
            if entity_id not in entity_ids:
                failures.append(f"diagram {diagram_id}: unknown entity {entity_id}")
            elif entity_class.get(entity_id) not in DRAWABLE_CLASSES:
                failures.append(
                    f"diagram {diagram_id}: {entity_class.get(entity_id)}-class entity "
                    f"{entity_id} cannot be drawn as established"
                )
        for relationship_id in included_relationships:
            if relationship_id not in relationship_ids:
                failures.append(f"diagram {diagram_id}: unknown relationship {relationship_id}")
            elif relationship_class.get(relationship_id) not in DRAWABLE_CLASSES:
                failures.append(
                    f"diagram {diagram_id}: {relationship_class.get(relationship_id)}-class relationship "
                    f"{relationship_id} cannot be drawn as established"
                )
        for field in ("question_answered", "main_takeaway", "structure", "deliberate_omissions", "caveats"):
            value = diagram.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                failures.append(f"diagram {diagram_id}: missing {field}")

    missing_models = sorted(set(specs) - model_ids)
    failures.extend(f"missing diagram model: {diagram_id}" for diagram_id in missing_models)
    failures.extend(f"unexpected diagram model: {diagram_id}" for diagram_id in sorted(model_ids - set(specs)))

    if markdown:
        for heading in ("Entity registry", "Relationship registry", "Model 01", "Model 02", "Model 03", "Model 04"):
            if heading.casefold() not in markdown.casefold():
                failures.append(f"diagram-models.md lacks {heading!r}")
        for stable_id in sorted(evidence_ids):
            if stable_id not in markdown:
                failures.append(f"diagram-models.md does not document stable ID {stable_id}")

    expected = len(entities) + len(relationships) + len(DIAGRAM_SPECS)
    return report_for(
        sys.modules[__name__],
        "diagram_models",
        root,
        patterns,
        expected or 1,
        expected,
        failures,
        details={"entities": len(entities), "relationships": len(relationships), "diagrams": len(model_ids)},
    )


def _visible_text(root: ET.Element) -> str:
    chunks: list[str] = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] in {"text", "tspan"} and element.text:
            chunks.append(element.text)
    return re.sub(r"\s+", " ", " ".join(chunks)).strip()


def validate_style_spec(root: Path) -> dict[str, Any]:
    patterns = [DIAGRAM_MODEL_JSON, BRAND_GUIDE_HTML, DIAGRAM_STYLE_MARKDOWN]
    failures: list[str] = []
    markdown_path = root / DIAGRAM_STYLE_MARKDOWN
    markdown = markdown_path.read_text(encoding="utf-8", errors="replace") if markdown_path.is_file() else ""
    if not markdown.strip():
        failures.append(f"missing or empty diagram style specification: {DIAGRAM_STYLE_MARKDOWN}")
    else:
        for heading in ("Inputs and scope", "Semantic mapping", "Connector channels", "Typography and spacing", "Designed extensions"):
            if heading.casefold() not in markdown.casefold():
                failures.append(f"diagram-style-spec.md lacks {heading!r}")
        folded = markdown.casefold()
        if "presentation" not in folded or "not evidence" not in folded:
            failures.append("diagram-style-spec.md does not state that brand guidance is presentation-only and not evidence")
        for required in (
            "line pattern", "arrowhead", "written edge label", "barred endpoint",
            "boundary annotation", "fill", "grayscale", "165 mm",
        ):
            if required not in folded:
                failures.append(f"diagram-style-spec.md lacks required visual-channel guidance {required!r}")
    return report_for(sys.modules[__name__], "diagram_style_spec", root, patterns, 1, int(bool(markdown.strip())), failures)


def validate_artifacts(root: Path) -> dict[str, Any]:
    patterns = [DIAGRAM_MODEL_JSON, DIAGRAM_STYLE_MARKDOWN, DIAGRAM_CAPTIONS, *(spec["path"] for spec in DIAGRAM_SPECS)]
    data, failures = _model_data(root)
    captions_path = root / DIAGRAM_CAPTIONS
    captions = captions_path.read_text(encoding="utf-8", errors="replace") if captions_path.is_file() else ""
    if not captions.strip():
        failures.append(f"missing or empty captions: {DIAGRAM_CAPTIONS}")
    diagrams = {
        str(item.get("id")): item
        for item in (data or {}).get("diagrams", [])
        if isinstance(item, dict) and item.get("id")
    }
    entities = {
        str(item.get("id")): item
        for item in (data or {}).get("entities", [])
        if isinstance(item, dict) and item.get("id")
    }
    checked = 0
    for spec in DIAGRAM_SPECS:
        path = root / spec["path"]
        if not path.is_file() or not path.stat().st_size:
            failures.append(f"missing or empty SVG: {spec['path']}")
            continue
        try:
            svg = ET.parse(path).getroot()
        except (ET.ParseError, OSError) as error:
            failures.append(f"{spec['path']}: invalid XML: {error}")
            continue
        checked += 1
        if svg.tag.rsplit("}", 1)[-1] != "svg":
            failures.append(f"{spec['path']}: root element is not svg")
        if svg.get("width") != "165mm":
            failures.append(f"{spec['path']}: width must be exactly 165mm for publication-size review")
        if not svg.get("viewBox"):
            failures.append(f"{spec['path']}: missing viewBox")
        tags = [element.tag.rsplit("}", 1)[-1] for element in svg.iter()]
        prohibited = sorted(set(tags) & {"image", "foreignObject", "script"})
        if prohibited:
            failures.append(f"{spec['path']}: prohibited SVG elements: {', '.join(prohibited)}")
        if "text" not in tags:
            failures.append(f"{spec['path']}: contains no editable text elements")
        children = list(svg)
        child_tags = [item.tag.rsplit("}", 1)[-1] for item in children[:2]]
        if child_tags != ["title", "desc"]:
            failures.append(f"{spec['path']}: first two SVG children must be title then desc for logical reading order")
        elif not (children[0].text or "").strip() or not (children[1].text or "").strip():
            failures.append(f"{spec['path']}: title and desc must be nonempty")
        serialized = ET.tostring(svg, encoding="unicode")
        if "font-family" not in serialized or not re.search(r"(?:sans-serif|serif|monospace|system-ui)", serialized, re.I):
            failures.append(f"{spec['path']}: no dependable font fallback is declared")
        for element in svg.iter():
            for attribute, value in element.attrib.items():
                if attribute.rsplit("}", 1)[-1] == "href" and re.match(r"^(?:https?:)?//", value.strip(), re.I):
                    failures.append(f"{spec['path']}: remote SVG dependency is prohibited")
        if re.search(r"(?:@import|url\(\s*['\"]?(?:https?:)?//)", serialized, re.I):
            failures.append(f"{spec['path']}: remote CSS dependency is prohibited")
        visible = _visible_text(svg)
        for required in (spec["title"], spec["subtitle"]):
            if required not in visible:
                failures.append(f"{spec['path']}: missing deterministic visible text {required!r}")

        represented_entities = {
            value
            for element in svg.iter()
            for value in [element.get("data-entity-id", "").strip()]
            if value
        }
        represented_relationships = {
            value
            for element in svg.iter()
            for value in [element.get("data-relationship-id", "").strip()]
            if value
        }
        model = diagrams.get(spec["id"], {})
        required_entities = set(_strings(model.get("entity_ids", [])))
        required_relationships = set(_strings(model.get("relationship_ids", [])))
        for stable_id in sorted(required_entities - represented_entities):
            failures.append(f"{spec['path']}: entity {stable_id} is not represented by data-entity-id")
        for stable_id in sorted(represented_entities - required_entities):
            failures.append(f"{spec['path']}: data-entity-id {stable_id} is absent from the approved model")
        for stable_id in sorted(required_relationships - represented_relationships):
            failures.append(f"{spec['path']}: relationship {stable_id} is not represented by data-relationship-id")
        for stable_id in sorted(represented_relationships - required_relationships):
            failures.append(f"{spec['path']}: data-relationship-id {stable_id} is absent from the approved model")
        for element in svg.iter():
            entity_id = element.get("data-entity-id", "").strip()
            if entity_id and entity_id in entities:
                label = str(entities[entity_id].get("label", "")).strip()
                if label and label not in _visible_text(element):
                    failures.append(f"{spec['path']}: entity {entity_id} does not visibly retain canonical label {label!r}")

        if captions:
            for required in (spec["title"], spec["subtitle"]):
                if required not in captions:
                    failures.append(f"diagram-captions.md lacks deterministic text {required!r}")

    return report_for(
        sys.modules[__name__],
        "diagram_artifacts",
        root,
        patterns,
        len(DIAGRAM_SPECS),
        checked,
        failures,
    )


def validate_visual_records(root: Path) -> dict[str, Any]:
    path = root / "06-checks/visual-review.json"
    patterns = ["06-checks/visual-review.json", *(spec["path"] for spec in DIAGRAM_SPECS)]
    failures: list[str] = []
    if not path.is_file() or not path.stat().st_size:
        return report_for(
            sys.modules[__name__], "diagram_visual_records", root, patterns,
            len(DIAGRAM_SPECS), 0, failures, ["visual review JSON is missing or empty"],
        )
    try:
        value = load_json(path)
    except Exception as error:
        return report_for(
            sys.modules[__name__], "diagram_visual_records", root, patterns,
            len(DIAGRAM_SPECS), 0, [f"visual review JSON is unreadable: {error}"],
        )
    records = value.get("diagrams", []) if isinstance(value, dict) else []
    by_id: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(records, 1):
        if not isinstance(record, dict):
            failures.append(f"diagram review {index}: must be an object")
            continue
        diagram_id = str(record.get("diagram", ""))
        if diagram_id in by_id:
            failures.append(f"diagram {diagram_id}: reviewed more than once")
        by_id[diagram_id] = record
        if record.get("status") not in {"clean", "issues"}:
            failures.append(f"diagram {diagram_id or index}: invalid review status")
        if record.get("status") == "issues" and not record.get("issues"):
            failures.append(f"diagram {diagram_id or index}: issues status has no issues")
        if record.get("review_width_mm") != 165:
            failures.append(f"diagram {diagram_id or index}: review_width_mm must equal 165")
    expected_ids = {spec["id"] for spec in DIAGRAM_SPECS}
    failures.extend(f"diagram {diagram_id}: no visual-review record" for diagram_id in sorted(expected_ids - set(by_id)))
    failures.extend(f"unexpected diagram visual-review record: {diagram_id}" for diagram_id in sorted(set(by_id) - expected_ids))
    unresolved = sorted(diagram_id for diagram_id, record in by_id.items() if record.get("status") == "issues")
    failures.extend(f"diagram {diagram_id}: unresolved visual issues remain" for diagram_id in unresolved)
    return report_for(
        sys.modules[__name__], "diagram_visual_records", root, patterns,
        len(expected_ids), len(expected_ids & set(by_id)), failures,
    )
