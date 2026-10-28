"""Canonical paths for the independently produced brand-guide branch."""

from __future__ import annotations

from typing import Final


BRAND_GUIDE_HTML: Final = "07-final-report/brand-guide.html"
BRAND_GUIDE_PDF: Final = "07-final-report/brand-guide.pdf"
BRAND_EVIDENCE_ROOT: Final = "05-synthesis/brand-guide/evidence"
BRAND_SOURCE_MAP: Final = f"{BRAND_EVIDENCE_ROOT}/source-map.md"
BRAND_OBSERVATIONS: Final = f"{BRAND_EVIDENCE_ROOT}/design-observations.md"
BRAND_ASSET_MANIFEST: Final = f"{BRAND_EVIDENCE_ROOT}/asset-manifest.csv"
BRAND_ACCEPTANCE: Final = f"{BRAND_EVIDENCE_ROOT}/acceptance-check.md"
BRAND_SCREENSHOTS: Final = f"{BRAND_EVIDENCE_ROOT}/screenshots"

BRAND_TASK_OUTPUTS: Final = (
    BRAND_GUIDE_HTML,
    BRAND_GUIDE_PDF,
    BRAND_SOURCE_MAP,
    BRAND_OBSERVATIONS,
    BRAND_ASSET_MANIFEST,
    BRAND_ACCEPTANCE,
    BRAND_SCREENSHOTS,
)
