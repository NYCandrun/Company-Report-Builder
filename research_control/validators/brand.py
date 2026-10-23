"""Basic fail-closed checks for the independently built brand guide."""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

from research_control.brand_contract import (
    BRAND_ACCEPTANCE,
    BRAND_ASSET_MANIFEST,
    BRAND_GUIDE_HTML,
    BRAND_GUIDE_PDF,
    BRAND_OBSERVATIONS,
    BRAND_SCREENSHOTS,
    BRAND_SOURCE_MAP,
)
from research_control.io import load_json

from .common import report_for


def _pdf_pages(path: Path) -> int:
    return len(re.findall(rb"/Type\s*/Page\b", path.read_bytes()))


def validate_artifacts(root: Path) -> dict:
    patterns = [
        BRAND_GUIDE_HTML, BRAND_GUIDE_PDF, BRAND_SOURCE_MAP, BRAND_OBSERVATIONS,
        BRAND_ASSET_MANIFEST, BRAND_ACCEPTANCE, f"{BRAND_SCREENSHOTS}/**",
    ]
    failures: list[str] = []
    for relative in (BRAND_SOURCE_MAP, BRAND_OBSERVATIONS, BRAND_ACCEPTANCE):
        path = root / relative
        if not path.is_file() or not path.stat().st_size:
            failures.append(f"missing or empty brand evidence: {relative}")

    manifest_path = root / BRAND_ASSET_MANIFEST
    if not manifest_path.is_file() or not manifest_path.stat().st_size:
        failures.append(f"missing or empty brand asset manifest: {BRAND_ASSET_MANIFEST}")
    else:
        with manifest_path.open(encoding="utf-8-sig", newline="") as handle:
            fields = {str(item).strip().casefold() for item in (csv.DictReader(handle).fieldnames or [])}
        required = {"source url", "type", "usage", "evidence label"}
        if not required.issubset(fields):
            failures.append("brand asset manifest lacks source URL, type, usage, or evidence label columns")

    html_path = root / BRAND_GUIDE_HTML
    html = html_path.read_text(encoding="utf-8", errors="replace") if html_path.is_file() else ""
    if not html.strip():
        failures.append(f"missing or empty brand guide HTML: {BRAND_GUIDE_HTML}")
    else:
        folded = html.casefold()
        for token in ("<!doctype html", "<html", "<style", "editorial diagrams", "designed extension"):
            if token not in folded:
                failures.append(f"brand guide HTML lacks required content {token!r}")

    pdf_path = root / BRAND_GUIDE_PDF
    if not pdf_path.is_file() or not pdf_path.stat().st_size:
        failures.append(f"missing or empty brand guide PDF: {BRAND_GUIDE_PDF}")
    elif not pdf_path.read_bytes().startswith(b"%PDF-") or not _pdf_pages(pdf_path):
        failures.append("brand-guide.pdf is not a readable paged PDF")

    screenshots = [
        path for path in (root / BRAND_SCREENSHOTS).glob("**/*")
        if path.is_file() and path.stat().st_size and path.suffix.casefold() in {".png", ".jpg", ".jpeg", ".webp"}
    ] if (root / BRAND_SCREENSHOTS).is_dir() else []
    if not screenshots:
        failures.append("brand evidence contains no visual-inspection screenshots")

    checked = sum(
        1 for relative in (BRAND_GUIDE_HTML, BRAND_GUIDE_PDF, BRAND_SOURCE_MAP, BRAND_OBSERVATIONS, BRAND_ASSET_MANIFEST, BRAND_ACCEPTANCE)
        if (root / relative).is_file() and (root / relative).stat().st_size
    )
    return report_for(
        sys.modules[__name__], "brand_artifacts", root, patterns, 6, checked, failures,
        details={"screenshots": len(screenshots)},
    )


def validate_visual_records(root: Path) -> dict:
    review_path = root / "06-checks/visual-review.json"
    patterns = ["06-checks/visual-review.json", BRAND_GUIDE_HTML, BRAND_GUIDE_PDF]
    if not review_path.is_file() or not review_path.stat().st_size:
        return report_for(sys.modules[__name__], "brand_visual_records", root, patterns, 3, 0, unknowns=["visual review JSON is missing or empty"])
    failures: list[str] = []
    try:
        value = load_json(review_path)
    except Exception as error:
        return report_for(sys.modules[__name__], "brand_visual_records", root, patterns, 3, 0, failures=[f"visual review JSON is unreadable: {error}"])
    records = value.get("brand_guide", {}) if isinstance(value, dict) else {}
    html_records = records.get("html", []) if isinstance(records, dict) else []
    by_viewport = {str(item.get("viewport")): item for item in html_records if isinstance(item, dict)}
    for viewport in ("desktop", "mobile"):
        if by_viewport.get(viewport, {}).get("status") != "clean":
            failures.append(f"brand guide {viewport} independent visual review is missing or unresolved")
    page_count = _pdf_pages(root / BRAND_GUIDE_PDF) if (root / BRAND_GUIDE_PDF).is_file() else 0
    pdf_records = records.get("pdf_pages", []) if isinstance(records, dict) else []
    pages = {item.get("page") for item in pdf_records if isinstance(item, dict) and item.get("status") == "clean"}
    expected = set(range(1, page_count + 1))
    if pages != expected:
        failures.append(f"brand guide PDF clean-review pages {sorted(pages)} do not match {sorted(expected)}")
    checked = len(set(by_viewport) & {"desktop", "mobile"}) + len(pages & expected)
    return report_for(sys.modules[__name__], "brand_visual_records", root, patterns, 2 + page_count, checked, failures)
