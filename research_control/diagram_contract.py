"""Canonical publication contract for the four architecture diagrams."""

from __future__ import annotations

from typing import Final


DIAGRAM_MODEL_MARKDOWN: Final = "07-final-report/diagram-models.md"
DIAGRAM_MODEL_JSON: Final = "tools/outputs/diagram-models.json"
DIAGRAM_STYLE_MARKDOWN: Final = "07-final-report/diagram-style-spec.md"
DIAGRAM_CAPTIONS: Final = "07-final-report/diagram-captions.md"

DIAGRAM_SPECS: Final = (
    {
        "id": "01-product-capability-map",
        "path": "07-final-report/01-product-capability-map.svg",
        "title": "Capability taxonomy / inventory",
        "subtitle": "What does this company offer, and how are its capabilities organized?",
    },
    {
        "id": "02-operating-model",
        "path": "07-final-report/02-operating-model.svg",
        "title": "Operating model / behavior",
        "subtitle": "How does the product turn an input or need into an outcome?",
    },
    {
        "id": "03-enterprise-logical-architecture",
        "path": "07-final-report/03-enterprise-logical-architecture.svg",
        "title": "Enterprise logical architecture / structure",
        "subtitle": "How are the major functional domains organized, and how does the platform relate to its environment?",
    },
    {
        "id": "04-technical-dependency-map",
        "path": "07-final-report/04-technical-dependency-map.svg",
        "title": "Focused technical dependencies / receipts",
        "subtitle": "What consequential technical relationship, limitation, or architectural distinction does the research establish?",
    },
)

DIAGRAM_PATHS: Final = tuple(spec["path"] for spec in DIAGRAM_SPECS)
DIAGRAM_DELIVERABLES: Final = (
    DIAGRAM_MODEL_MARKDOWN,
    DIAGRAM_STYLE_MARKDOWN,
    *DIAGRAM_PATHS,
    DIAGRAM_CAPTIONS,
)
FINAL_ARTIFACTS: Final = (
    "07-final-report/company-brief.pdf",
    "07-final-report/company-brief.html",
    "07-final-report/brand-guide.html",
    "07-final-report/brand-guide.pdf",
    *DIAGRAM_DELIVERABLES,
)
