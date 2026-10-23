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

from research_control.hashing import sha256_file
from research_control.io import atomic_write_json, atomic_write_text, utc_now


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
.meta { color: var(--muted); font-size: 13px; text-transform: uppercase; letter-spacing: .08em; }
@media print { body { background: white; } main { width: auto; margin: 0; padding: 36pt 42pt; box-shadow: none; } }
""".strip()


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


def markdown_to_html(markdown: str, title: str, css: str) -> str:
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
    return (
        "<!doctype html>\n<html lang=\"en-US\"><head><meta charset=\"utf-8\">"
        f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>{html.escape(title)}</title>"
        f"<style>{css}</style></head><body><main><div class=\"meta\">Company research</div>{''.join(body)}</main></body></html>\n"
    )


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


def render_pdf(html_path: Path, markdown: str, pdf_path: Path) -> tuple[str, int]:
    if os.environ.get("RESEARCH_CONTROL_PDF_RENDERER", "").lower() == "stdlib":
        return "stdlib-pdf", make_pdf(reader_text(markdown), pdf_path)

    """Prefer a CSS-capable local renderer, with a deterministic fallback."""
    commands: list[tuple[str, list[str]]] = []
    if executable := shutil.which("weasyprint"):
        commands.append(("weasyprint", [executable, html_path.as_uri(), str(pdf_path)]))
    chrome = next(
        (
            candidate for candidate in (
                shutil.which("chromium"),
                shutil.which("chromium-browser"),
                shutil.which("google-chrome"),
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            )
            if candidate and Path(candidate).is_file()
        ),
        None,
    )
    if chrome:
        commands.append(("chromium", [
            chrome,
            "--headless",
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
    return "stdlib-pdf", make_pdf(markdown, pdf_path)


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
    metadata: dict[str, Any] = {
        "schema_version": "1.0.0",
        "renderer": "research_control.publication",
        "rendered_at": utc_now(),
        "documents": {},
        "total_pages": 0,
    }
    for slug, source in documents.items():
        markdown = source.read_text(encoding="utf-8")
        html_path = output_dir / f"{slug}.html"
        pdf_path = output_dir / f"{slug}.pdf"
        title = "Company brief"
        atomic_write_text(html_path, markdown_to_html(markdown, title, css))
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
            "html_sha256": sha256_file(html_path),
            "pdf_sha256": sha256_file(pdf_path),
        }
        metadata["total_pages"] += pages
    atomic_write_json(root / "tools/outputs/render-metadata.json", metadata)
    return metadata
