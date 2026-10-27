"""Dependency-free publication builder for final Markdown artifacts."""

from __future__ import annotations

import html
import os
import re
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Any

from research_control.hashing import hash_path, hash_patterns, sha256_file
from research_control.diagram_contract import DIAGRAM_SPECS
from research_control.io import atomic_write_json, atomic_write_text, load_json, utc_now


FACT_ID = re.compile(r"(?<![A-Za-z0-9])\[?[A-Z][A-Z0-9-]*-[A-Z]*\d+[a-z]?\]?")
DEFAULT_CSS = """
:root { color-scheme: light; --ink: #17202a; --muted: #5b6573; --accent: #175cd3; --line: #d8dee8; }
* { box-sizing: border-box; }
body { margin: 0; color: var(--ink); background: #f3f5f8; font: 16px/1.55 Arial, Helvetica, sans-serif; }
main { width: min(900px, calc(100% - 40px)); margin: 36px auto; padding: 64px 72px; background: white; box-shadow: 0 8px 30px #17202a18; }
h1 { margin: 0 0 32px; font-size: 38px; line-height: 1.08; letter-spacing: -0.03em; }
h2 { margin-top: 42px; padding-top: 14px; border-top: 2px solid var(--ink); font-size: 24px; }
h3 { margin-top: 28px; font-size: 18px; }
p, li { max-width: 74ch; }
a { color: var(--accent); text-decoration-thickness: 1px; text-underline-offset: 2px; }
table { width: 100%; border-collapse: collapse; margin: 24px 0; font-size: 14px; }
th, td { padding: 9px 10px; border: 1px solid var(--line); text-align: left; vertical-align: top; }
th { background: #f5f7fb; }
blockquote { margin-left: 0; padding-left: 18px; border-left: 3px solid var(--accent); color: var(--muted); }
.architecture-figures { margin-top: 56px; }
.architecture-figures figure { margin: 32px 0; break-inside: avoid; page-break-inside: avoid; }
.architecture-figures svg { display: block; width: 100%; max-width: 165mm; height: auto; margin: 0 auto; }
.architecture-figures figcaption { margin: 10px auto 0; max-width: 165mm; color: var(--muted); font-size: 13px; }
.meta { color: var(--muted); font-size: 13px; text-transform: uppercase; letter-spacing: .08em; }
sup.cn { font-size: .7em; line-height: 0; margin-left: 1px; }
sup.cn a { text-decoration: none; font-weight: 600; }
ol.source-notes { padding-left: 2.4em; font-size: 13px; }
ol.source-notes li { margin: 4px 0; max-width: none; overflow-wrap: anywhere; }
ol.source-notes .grade { display: inline-block; min-width: 1.4em; color: var(--muted); font-weight: 600; }
ol.source-notes .part { font-weight: 600; }
ol.source-notes .back { text-decoration: none; margin-left: 4px; }
sup.cn a:target, ol.source-notes li:target { background: #fff3b0; }
@media print { body { background: white; } main { width: auto; margin: 0; padding: 36pt 42pt; box-shadow: none; } }
""".strip()

RENDER_METADATA = "tools/outputs/render-metadata.json"
REVIEW_SCOPE = "tools/outputs/review-scope.json"


def reader_text(markdown: str) -> str:
    """Remove internal fact IDs while retaining reader-facing source notes."""
    cleaned = FACT_ID.sub("", markdown)
    cleaned = re.sub(r"[ \t]+([,.;:])", r"\1", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned


def _inline(value: str) -> str:
    value = html.escape(value, quote=False)
    value = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", value)
    value = re.sub(r"`([^`]+)`", r"<code>\1</code>", value)
    return value


CITE = "\x00cite{}\x00"
SOURCE_LIST = "\x00sources\x00"


def _with_citations(markdown: str, citation_map: dict[str, Any]) -> tuple[str, dict[str, str]]:
    """Swap each fact-ID group for a marker the HTML replaces with linked superscript numbers,
    and the Sources section's body for a marker the numbered source list replaces."""
    from research_control.citation_build import GROUP, SOURCES_HEADING

    groups: dict[int, list[dict[str, Any]]] = {}
    for citation in citation_map.get("citations", []):
        groups.setdefault(int(citation.get("group", -1)), []).append(citation)
    counter = iter(range(1_000_000))

    def marker(_match: re.Match[str]) -> str:
        return CITE.format(next(counter))

    text = re.sub(r"[ \t]*" + GROUP.pattern, marker, markdown)
    lines, kept, skipping = text.splitlines(), [], False
    for line in lines:
        if SOURCES_HEADING.match(line):
            kept += ["## Sources", "", SOURCE_LIST, ""]
            skipping = True
            continue
        if skipping and re.match(r"^#{1,2}\s", line):
            skipping = False
        if not skipping:
            kept.append(line)
    if SOURCE_LIST not in kept and citation_map.get("notes"):
        kept += ["", "## Sources", "", SOURCE_LIST]
    replacements: dict[str, str] = {}
    first_use: dict[int, str] = {}
    for index, citations in groups.items():
        anchors = []
        for item in citations:
            number = int(item["n"])
            anchor_id = f"cite-{index}-{number}"
            first_use.setdefault(number, anchor_id)
            # The number jumps to the source entry in this document; the exact passage, moment,
            # or line is kept on the anchor (data-link) and listed in that entry.
            anchors.append(
                f'<a id="{anchor_id}" href="#note-{number}" data-cite="{number}" '
                f'data-link="{html.escape(item.get("link") or "")}"'
                + (f' title="{html.escape(item["place"])}"' if item.get("place") else "") + f'>{number}</a>'
            )
        replacements[CITE.format(index)] = f'<sup class="cn">{",".join(anchors)}</sup>'
    items = []
    for note in citation_map.get("notes", []):
        url = str(note.get("url") or "")
        described = ". ".join(html.escape(str(part)) for part in (note.get("title"), note.get("publisher"), note.get("date")) if part)
        shown = re.sub(r"/(blob|commit)/([0-9a-f]{7})[0-9a-f]+", r"/\1/\2", re.sub(r"^https?://(www\.)?", "", url)).rstrip("/")
        link = f' <a href="{html.escape(url)}">{html.escape(shown)}</a>' if url else ""
        # Which part of a repository this entry is, and every timestamp or line the report cites.
        part = f' <span class="part">{html.escape(note["part"][0].upper() + note["part"][1:])}</span>.' if note.get("part") else ""
        places = note.get("places") or []
        cited = (" Cited at " + ", ".join(f'<a href="{html.escape(item["link"])}">{html.escape(item["label"])}</a>'
                                         for item in places) + ".") if places else ""
        back = f' <a class="back" href="#{first_use[int(note["n"])]}" title="Back to the text">↩</a>' if int(note["n"]) in first_use else ""
        items.append(f'<li id="note-{note["n"]}" value="{note["n"]}"><span class="grade">{html.escape(str(note.get("grade") or ""))}</span> '
                     f'{described}.{part}{cited}{link}{back}</li>')
    replacements[f"<p>{SOURCE_LIST}</p>"] = f'<ol class="source-notes">{"".join(items)}</ol>'
    return "\n".join(kept) + ("\n" if markdown.endswith("\n") else ""), replacements


def markdown_to_html(markdown: str, title: str, css: str, citation_map: dict[str, Any] | None = None) -> str:
    replacements: dict[str, str] = {}
    if citation_map:
        markdown, replacements = _with_citations(markdown, citation_map)
    lines = reader_text(markdown).splitlines()
    body: list[str] = []
    paragraph: list[str] = []
    in_list = False
    table: list[list[str]] = []

    def flush_paragraph() -> None:
        nonlocal paragraph
        if paragraph:
            body.append(f"<p>{_inline(' '.join(part.strip() for part in paragraph))}</p>")
            paragraph = []

    def flush_list() -> None:
        nonlocal in_list
        if in_list:
            body.append("</ul>")
            in_list = False

    def flush_table() -> None:
        nonlocal table
        if not table:
            return
        rows = table
        if len(rows) > 1 and all(re.fullmatch(r":?-+:?", cell) for cell in rows[1]):
            header, data = rows[0], rows[2:]
        else:
            header, data = [], rows
        body.append("<table>")
        if header:
            body.append("<thead><tr>" + "".join(f"<th>{_inline(cell)}</th>" for cell in header) + "</tr></thead>")
        body.append("<tbody>")
        for row in data:
            body.append("<tr>" + "".join(f"<td>{_inline(cell)}</td>" for cell in row) + "</tr>")
        body.append("</tbody></table>")
        table = []

    for raw in lines + [""]:
        line = raw.rstrip()
        if line.lstrip().startswith("|") and line.rstrip().endswith("|"):
            flush_paragraph()
            flush_list()
            table.append([cell.strip() for cell in line.strip().strip("|").split("|")])
            continue
        flush_table()
        heading = re.match(r"^(#{1,4})\s+(.*)$", line)
        item = re.match(r"^\s*[-*]\s+(.*)$", line)
        if re.fullmatch(r"\s*(?:-{3,}|\*{3,}|_{3,})\s*", line):
            # A dividing rule (the catalog separates stated items from leads with one).
            flush_paragraph()
            flush_list()
            body.append("<hr>")
            continue
        if heading:
            flush_paragraph()
            flush_list()
            level = len(heading.group(1))
            body.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
        elif item:
            flush_paragraph()
            if not in_list:
                body.append("<ul>")
                in_list = True
            body.append(f"<li>{_inline(item.group(1))}</li>")
        elif not line.strip():
            flush_paragraph()
            flush_list()
        elif line.startswith(">"):
            flush_paragraph()
            flush_list()
            body.append(f"<blockquote>{_inline(line.lstrip('> '))}</blockquote>")
        else:
            paragraph.append(line)
    document = (
        "<!doctype html>\n<html lang=\"en-US\"><head><meta charset=\"utf-8\">"
        f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{html.escape(title)}</title>"
        f"<style>{css}</style></head><body><main><div class=\"meta\">Company research</div>{''.join(body)}</main></body></html>\n"
    )
    for marker, markup in replacements.items():
        document = document.replace(marker, markup)
    return document


def _diagram_gallery(root: Path) -> str:
    available = [(spec, root / spec["path"]) for spec in DIAGRAM_SPECS if (root / spec["path"]).is_file()]
    if not available:
        return ""
    if len(available) != len(DIAGRAM_SPECS):
        missing = [spec["path"] for spec in DIAGRAM_SPECS if not (root / spec["path"]).is_file()]
        raise FileNotFoundError(f"diagram set is incomplete: {', '.join(missing)}")
    figures: list[str] = [
        '<section class="architecture-figures" aria-labelledby="architecture-figures-title">',
        '<h2 id="architecture-figures-title">Architecture diagrams</h2>',
    ]
    for spec, path in available:
        if not path.is_file() or not path.stat().st_size:
            raise FileNotFoundError(f"diagram missing or empty: {spec['path']}")
        svg = path.read_text(encoding="utf-8", errors="strict")
        svg = re.sub(r"^\s*<\?xml[^>]*>\s*", "", svg)
        figures.extend([
            f'<figure data-report-diagram="{html.escape(spec["id"], quote=True)}">',
            svg,
            f'<figcaption><strong>{html.escape(spec["title"])}</strong> - {html.escape(spec["subtitle"])}</figcaption>',
            '</figure>',
        ])
    figures.append('</section>')
    return "".join(figures)


def _plain_lines(markdown: str, width: int = 86) -> list[str]:
    lines: list[str] = []
    for raw in reader_text(markdown).splitlines():
        value = re.sub(r"^#{1,6}\s+", "", raw)
        value = re.sub(r"^\s*[-*]\s+", "• ", value)
        value = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1 (\2)", value)
        value = value.replace("**", "").replace("`", "")
        value = re.sub(r"<[^>]+>", "", value).strip()
        if not value:
            lines.append("")
            continue
        lines.extend(textwrap.wrap(value, width=width, replace_whitespace=False, drop_whitespace=True) or [""])
    return lines


def _pdf_escape(value: str) -> str:
    value = value.encode("latin-1", errors="replace").decode("latin-1")
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(markdown: str, path: Path, lines_per_page: int = 50) -> int:
    lines = _plain_lines(markdown)
    pages = [lines[index:index + lines_per_page] for index in range(0, len(lines), lines_per_page)] or [[]]
    objects: list[bytes] = []
    page_ids: list[int] = []
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(b"")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for page_lines in pages:
        page_id = len(objects) + 1
        content_id = page_id + 1
        page_ids.append(page_id)
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>".encode()
        )
        commands = ["BT", "/F1 10 Tf", "54 738 Td", "13 TL"]
        for line in page_lines:
            commands.append(f"({_pdf_escape(line)}) Tj")
            commands.append("T*")
        commands.append("ET")
        stream = "\n".join(commands).encode("latin-1", errors="replace")
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
    objects[1] = f"<< /Type /Pages /Kids [{' '.join(f'{item} 0 R' for item in page_ids)}] /Count {len(page_ids)} >>".encode()

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode())
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(output))
    return len(pages)


def make_svg_previews(markdown: str, directory: Path, slug: str, lines_per_page: int = 50) -> list[str]:
    lines = _plain_lines(markdown)
    pages = [lines[index:index + lines_per_page] for index in range(0, len(lines), lines_per_page)] or [[]]
    directory.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for page_number, page_lines in enumerate(pages, 1):
        text = [
            '<svg xmlns="http://www.w3.org/2000/svg" width="816" height="1056" viewBox="0 0 816 1056">',
            '<rect width="816" height="1056" fill="white"/>',
            '<g fill="#17202a" font-family="Arial, Helvetica, sans-serif" font-size="13">',
        ]
        for index, line in enumerate(page_lines):
            text.append(f'<text x="72" y="{78 + index * 18}">{html.escape(line)}</text>')
        text.extend(["</g>", f'<text x="744" y="1018" fill="#5b6573" font-size="11">{page_number}</text>', "</svg>"])
        path = directory / f"{slug}-{page_number:03d}.svg"
        atomic_write_text(path, "\n".join(text) + "\n")
        paths.append(str(path))
    return paths


def _pdf_pages(path: Path) -> int:
    return len(re.findall(rb"/Type\s*/Page\b", path.read_bytes()))


def _chromium() -> str | None:
    """A Chromium to print PDFs with: on PATH, in Playwright's browser folders (the cloud
    container keeps one there, off PATH), or in the usual desktop places."""
    candidates = [shutil.which(name) for name in ("chromium", "chromium-browser", "google-chrome", "chrome")]
    for base in (os.environ.get("PLAYWRIGHT_BROWSERS_PATH"), "/opt/pw-browsers", str(Path.home() / ".cache/ms-playwright")):
        if base and Path(base).is_dir():
            candidates += sorted((str(path) for path in Path(base).glob("chromium*/chrome-linux*/chrome")), reverse=True)
            candidates += sorted((str(path) for path in Path(base).glob("chromium*/chrome-mac*/Chromium.app/Contents/MacOS/Chromium")), reverse=True)
    candidates.append("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    return next((candidate for candidate in candidates if candidate and Path(candidate).is_file()), None)


def render_pdf(html_path: Path, markdown: str, pdf_path: Path) -> tuple[str, int]:
    if os.environ.get("RESEARCH_CONTROL_PDF_RENDERER", "").lower() == "stdlib":
        return "stdlib-pdf", make_pdf(reader_text(markdown), pdf_path)

    """Prefer a CSS-capable local renderer, with a deterministic fallback."""
    commands: list[tuple[str, list[str]]] = []
    if executable := shutil.which("weasyprint"):
        commands.append(("weasyprint", [executable, html_path.as_uri(), str(pdf_path)]))
    chrome = _chromium()
    if chrome:
        commands.append(("chromium", [
            chrome,
            "--headless",
            # Chromium refuses to run as root (a container) with its sandbox on.
            *(["--no-sandbox"] if hasattr(os, "geteuid") and os.geteuid() == 0 else []),
            "--disable-gpu",
            "--no-pdf-header-footer",
            f"--print-to-pdf={pdf_path}",
            html_path.as_uri(),
        ]))
    if executable := shutil.which("wkhtmltopdf"):
        commands.append(("wkhtmltopdf", [executable, "--quiet", str(html_path), str(pdf_path)]))
    for name, command in commands:
        try:
            result = subprocess.run(command, text=True, capture_output=True, timeout=90)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0 and pdf_path.is_file() and pdf_path.stat().st_size and pdf_path.read_bytes().startswith(b"%PDF-"):
            pages = _pdf_pages(pdf_path)
            if pages:
                return name, pages
    # No page renderer: the plain-text PDF is a placeholder, and the metadata says so.
    return "stdlib-pdf (no browser renderer found; install Chromium or WeasyPrint)", make_pdf(markdown, pdf_path)


def make_page_previews(pdf_path: Path, markdown: str, directory: Path, slug: str) -> tuple[str, list[str]]:
    directory.mkdir(parents=True, exist_ok=True)
    for old in directory.glob(f"{slug}-*.*"):
        if old.is_file() and old.suffix in {".png", ".svg"}:
            old.unlink()
    if executable := shutil.which("pdftoppm"):
        prefix = directory / slug
        try:
            result = subprocess.run(
                [executable, "-png", "-r", "144", str(pdf_path), str(prefix)],
                text=True,
                capture_output=True,
                timeout=90,
            )
        except (OSError, subprocess.TimeoutExpired):
            result = None
        if result is not None and result.returncode == 0:
            paths = sorted(directory.glob(f"{slug}-*.png"))
            if paths:
                return "png", [str(path) for path in paths]
    return "svg", make_svg_previews(markdown, directory, slug)


def _render_inputs(root: Path, source: Path) -> dict[str, str]:
    patterns = [
        str(source.relative_to(root)),
        "05-synthesis/design/style.css",
        "tools/outputs/citation-map-*.json",
        "research_control/publication.py",
        "research_control/diagram_contract.py",
        *(spec["path"] for spec in DIAGRAM_SPECS),
    ]
    return hash_patterns(root, patterns)


def _prior_document_current(root: Path, record: dict[str, Any], input_hashes: dict[str, str]) -> bool:
    if record.get("input_hashes") != input_hashes:
        return False
    paths_and_hashes = [
        (record.get("html"), record.get("html_sha256")),
        (record.get("pdf"), record.get("pdf_sha256")),
    ]
    paths_and_hashes.extend(
        (relative, digest)
        for relative, digest in record.get("page_hashes", {}).items()
    )
    return bool(paths_and_hashes) and all(
        isinstance(relative, str)
        and isinstance(digest, str)
        and hash_path(root / relative) == digest
        for relative, digest in paths_and_hashes
    )


def _reviewed_hashes(root: Path) -> dict[tuple[str, str], str]:
    path = root / "06-checks/visual-review.json"
    if not path.is_file() or not path.stat().st_size:
        return {}
    try:
        value = load_json(path)
    except Exception:
        return {}
    result: dict[tuple[str, str], str] = {}
    for record in value.get("pages", []):
        if record.get("status") == "clean":
            result[("brief_page", str(record.get("page")))] = str(record.get("artifact_sha256") or "")
    for record in value.get("diagrams", []):
        if record.get("status") == "clean":
            result[("diagram", str(record.get("diagram")))] = str(record.get("artifact_sha256") or "")
    brand = value.get("brand_guide", {})
    for record in brand.get("html", []) if isinstance(brand, dict) else []:
        if record.get("status") == "clean":
            result[("brand_html", str(record.get("viewport")))] = str(record.get("artifact_sha256") or "")
    for record in brand.get("pdf_pages", []) if isinstance(brand, dict) else []:
        if record.get("status") == "clean":
            result[("brand_pdf", str(record.get("page")))] = str(record.get("artifact_sha256") or "")
    return result


def write_review_scope(root: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    """Select visual targets by hash while retaining complete review accounting."""
    prior = _reviewed_hashes(root)
    targets: list[dict[str, Any]] = []
    document = metadata.get("documents", {}).get("company-brief", {})
    for page, relative in enumerate(document.get("page_previews", []), 1):
        digest = hash_path(root / relative)
        targets.append({
            "kind": "brief_page", "id": str(page), "path": relative,
            "artifact_sha256": digest,
            "action": "reuse" if prior.get(("brief_page", str(page))) == digest else "inspect",
        })
    for spec in DIAGRAM_SPECS:
        digest = hash_path(root / spec["path"])
        targets.append({
            "kind": "diagram", "id": spec["id"], "path": spec["path"],
            "artifact_sha256": digest,
            "action": "reuse" if prior.get(("diagram", spec["id"])) == digest else "inspect",
        })
    brand_html = "07-final-report/brand-guide.html"
    html_digest = hash_path(root / brand_html)
    for viewport in ("desktop", "mobile"):
        targets.append({
            "kind": "brand_html", "id": viewport, "path": brand_html,
            "artifact_sha256": html_digest,
            "action": "reuse" if prior.get(("brand_html", viewport)) == html_digest else "inspect",
        })
    brand_pdf = root / "07-final-report/brand-guide.pdf"
    pdf_digest = hash_path(brand_pdf)
    page_count = _pdf_pages(brand_pdf) if brand_pdf.is_file() else 0
    for page in range(1, page_count + 1):
        targets.append({
            "kind": "brand_pdf", "id": str(page),
            "path": str(brand_pdf.relative_to(root)), "artifact_sha256": pdf_digest,
            "action": "reuse" if prior.get(("brand_pdf", str(page))) == pdf_digest else "inspect",
        })
    scope = {
        "schema_version": "1.0.0",
        "rule": "inspect changed hashes; retain prior clean records only when their artifact hash is identical",
        "targets": targets,
        "inspect_count": sum(item["action"] == "inspect" for item in targets),
        "reuse_count": sum(item["action"] == "reuse" for item in targets),
        "created_at": utc_now(),
    }
    atomic_write_json(root / REVIEW_SCOPE, scope)
    return scope


def render(root: Path) -> dict[str, Any]:
    documents = {
        "company-brief": root / "05-synthesis/company-brief.md",
    }
    missing = [str(path.relative_to(root)) for path in documents.values() if not path.is_file() or not path.stat().st_size]
    if missing:
        raise FileNotFoundError(f"final Markdown missing or empty: {', '.join(missing)}")
    css_path = root / "05-synthesis/design/style.css"
    custom_css = css_path.read_text(encoding="utf-8") if css_path.is_file() else ""
    css = DEFAULT_CSS + ("\n" + custom_css if custom_css.strip() else "")
    output_dir = root / "07-final-report"
    preview_dir = root / "tools/outputs/rendered-pages"
    prior_path = root / RENDER_METADATA
    prior = load_json(prior_path) if prior_path.is_file() and prior_path.stat().st_size else {}
    metadata: dict[str, Any] = {
        "schema_version": "2.0.0",
        "renderer": "research_control.publication",
        "rendered_at": utc_now(),
        "documents": {},
        "total_pages": 0,
    }
    for slug, source in documents.items():
        markdown = source.read_text(encoding="utf-8")
        html_path = output_dir / f"{slug}.html"
        pdf_path = output_dir / f"{slug}.pdf"
        input_hashes = _render_inputs(root, source)
        prior_document = prior.get("documents", {}).get(slug, {}) if isinstance(prior, dict) else {}
        if _prior_document_current(root, prior_document, input_hashes):
            record = dict(prior_document)
            record["render_action"] = "reused"
            metadata["documents"][slug] = record
            metadata["total_pages"] += int(record.get("pages", 0))
            continue
        title = "Company brief"
        map_path = root / f"tools/outputs/citation-map-{slug}.json"
        citation_map = load_json(map_path) if map_path.is_file() else None
        document = markdown_to_html(markdown, title, css, citation_map)
        document = document.replace("</main>", _diagram_gallery(root) + "</main>", 1)
        atomic_write_text(html_path, document)
        pdf_renderer, pages = render_pdf(html_path, markdown, pdf_path)
        preview_format, previews = make_page_previews(pdf_path, markdown, preview_dir, slug)
        metadata["documents"][slug] = {
            "source": str(source.relative_to(root)),
            "html": str(html_path.relative_to(root)),
            "pdf": str(pdf_path.relative_to(root)),
            "pages": pages,
            "pdf_renderer": pdf_renderer,
            "preview_format": preview_format,
            "page_previews": [str(Path(item).relative_to(root)) for item in previews],
            "page_hashes": {
                str(Path(item).relative_to(root)): sha256_file(Path(item)) for item in previews
            },
            "html_sha256": sha256_file(html_path),
            "pdf_sha256": sha256_file(pdf_path),
            "input_hashes": input_hashes,
            "render_action": "rebuilt",
        }
        metadata["total_pages"] += pages
    atomic_write_json(root / RENDER_METADATA, metadata)
    metadata["review_scope"] = write_review_scope(root, metadata)
    return metadata
