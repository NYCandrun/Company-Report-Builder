"""A resolving deep link for every fact, computed from its quote.

A citation should open the source at the quoted words, not at its top. The
link is found by locating the fact's verbatim quote in the capture extraction
read, then anchoring by what that place is:

- a repository file: the file at the captured commit, at the line
  (`blob/<commit>/<path>#L<n>`, plain view for Markdown);
- a commit in a repository's change history: the line in that commit's diff
  (`commit/<sha>#diff-<sha256(path)>R<n>`);
- unmerged work: the pull request's diff, or the branch compared with the
  default branch;
- a pull request or issue page, or any other web page: a text fragment that
  scrolls to and highlights the quoted words (`#:~:text=`);
- a recording: the timestamp of the quoted passage (YouTube `t=`, a media
  fragment `#t=` for direct audio, or "at hh:mm:ss" for an episode page).

A quote that cannot be found keeps the source URL and is listed in the report.
"""

from __future__ import annotations

import bisect
import csv
import re
from hashlib import sha256
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse

from research_control.io import atomic_write_jsonl, atomic_write_text
from research_control.validators import facts as fact_tables

FACT_LINKS = "tools/outputs/fact-links.jsonl"
LINKS_REPORT = "06-checks/fact-links.md"
ELLIPSIS = re.compile(r"\s*(?:\.\.\.|…|\[\.\.\.\]|\[…\])\s*")
TIMESTAMP = re.compile(r"^\[(\d{1,2}):(\d{2}):(\d{2})\]\s*")
FILE_HEADER = re.compile(
    r"^--- FILE: (.+?)(?: \(PDF, (\d+) pages, as text\))?(?: \((HTML, as text|tests, names only|data sample[^)]*)\))?(?: \(\d+ lines[^)]*\))? ---$"
)
PDF_PAGE = re.compile(r"^--- page (\d+) ---$")
SURVIVED = re.compile(r"^\+\[(\d+) added lines? still in the current file\]$")
COMMIT_HEADER = re.compile(r"^=== COMMIT ([0-9a-f]{7,40}) ")
UNMERGED_HEADER = re.compile(r"^=== UNMERGED: (.+?) \(\d+ commits")
CONVERSATION_HEADER = re.compile(r"^=== (?:PULL REQUEST|ISSUE) #\d+: .* \((https://github\.com/\S+)\) ===$")
HISTORY_LINE = re.compile(r"^\d{4}-\d{2}-\d{2} ([0-9a-f]{7,40}) ")
SECTION_HEADER = re.compile(r"^(?:---|===) ")
DIFF_FILE = re.compile(r"^diff --git a/.+? b/(.+)$")
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)")
AUDIO_SUFFIXES = (".mp3", ".m4a", ".wav", ".ogg", ".opus", ".aac")


def _normalize(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", text).strip().casefold()


def _segment(quote_text: str) -> str:
    """The longest stretch of a quote between ellipses: the words to look for."""
    parts = [part.strip() for part in ELLIPSIS.split(quote_text or "") if part.strip()]
    return max(parts, key=len) if parts else ""


def _stream(lines: list[str], strip_diff: bool) -> tuple[str, list[int]]:
    """Lines joined as one normalized string, with each line's start offset."""
    pieces: list[str] = []
    starts: list[int] = []
    position = 0
    for line in lines:
        text = TIMESTAMP.sub("", line)
        if strip_diff and text[:1] in "+-" and not text.startswith(("+++", "---")):
            text = text[1:]
        piece = _normalize(text)
        starts.append(position)
        pieces.append(piece)
        position += len(piece) + 1
    return " ".join(pieces), starts


def locate(lines: list[str], quote_text: str, *, strip_diff: bool = False) -> int | None:
    """The index of the line where the quote starts, or None."""
    segment = _normalize(_segment(quote_text))
    if len(segment) < 8:
        return None
    stream, starts = _stream(lines, strip_diff)
    for needle in (segment[:120], segment[:60], segment[:30]):
        found = stream.find(needle)
        if found >= 0:
            return max(bisect.bisect_right(starts, found) - 1, 0)
    return None


def text_fragment(url: str, quote_text: str) -> str:
    words = _segment(quote_text).split()
    if not words:
        return url

    def encode(value: str) -> str:
        return quote(value, safe="").replace("-", "%2D")

    if len(words) > 12:
        fragment = f"{encode(' '.join(words[:6]))},{encode(' '.join(words[-6:]))}"
    else:
        fragment = encode(" ".join(words))
    return f"{url.split('#', 1)[0]}#:~:text={fragment}"


def _seconds_before(lines: list[str], index: int) -> int | None:
    for line in reversed(lines[: index + 1]):
        match = TIMESTAMP.match(line)
        if match:
            hours, minutes, seconds = (int(value) for value in match.groups())
            return hours * 3600 + minutes * 60 + seconds
    return None


def _clock(seconds: int) -> str:
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def _with_query(url: str, **values: str) -> str:
    parsed = urlparse(url)
    query = [(key, value) for key, value in parse_qsl(parsed.query) if key not in values and key != "feature"]
    query += list(values.items())
    return urlunparse(parsed._replace(query=urlencode(query), fragment=""))


def _recording_link(url: str, lines: list[str], index: int) -> tuple[str, str]:
    seconds = _seconds_before(lines, index)
    if seconds is None:
        return url, "recording (no timestamp)"
    host = (urlparse(url).hostname or "").casefold()
    if "youtube.com" in host or host == "youtu.be":
        return _with_query(url, t=f"{seconds}s"), f"at {_clock(seconds)}"
    if urlparse(url).path.casefold().endswith(AUDIO_SUFFIXES):
        return f"{url.split('#', 1)[0]}#t={seconds}", f"at {_clock(seconds)}"
    return url, f"at {_clock(seconds)}"


def _repository_link(lines: list[str], index: int, quote_text: str) -> tuple[str, str] | None:
    """Anchor a quote found at `index` of a repository capture."""
    header = next((line for line in lines[:8] if line.startswith("Repository: ")), "")
    commit_line = next((line for line in lines[:8] if line.startswith("Captured commit: ")), "")
    if not header:
        return None
    repo = header.removeprefix("Repository: ").strip()
    commit = commit_line.removeprefix("Captured commit: ").split()[0] if commit_line else "HEAD"
    base = f"https://github.com/{repo}"
    line = lines[index]
    history = HISTORY_LINE.match(line)
    for back in range(index, -1, -1):
        current = lines[back]
        match = FILE_HEADER.match(current)
        if match and match.group(2):
            # A PDF kept in the repository: its page, from the text's page markers.
            path = match.group(1)
            page = next((PDF_PAGE.match(lines[position]).group(1) for position in range(index, back, -1)
                         if PDF_PAGE.match(lines[position])), "1")
            return f"{base}/blob/{commit}/{quote(path)}", f"{path} page {page} at {commit[:7]}"
        if match and match.group(3):
            # Read as text or sampled: its lines are not the file's lines, so the link is to the file.
            path = match.group(1)
            return f"{base}/blob/{commit}/{quote(path)}", f"{path} ({match.group(3).split(':')[0]}) at {commit[:7]}"
        if match:
            path = match.group(1)
            number = index - back
            plain = "?plain=1" if path.casefold().endswith((".md", ".mdx", ".markdown")) else ""
            return f"{base}/blob/{commit}/{quote(path)}{plain}#L{number}", f"{path} line {number} at {commit[:7]}"
        match = COMMIT_HEADER.match(current)
        if match:
            sha = match.group(1)
            return _diff_anchor(f"{base}/commit/{sha}", lines, back, index, f"commit {sha}")
        match = UNMERGED_HEADER.match(current)
        if match:
            names = [name.strip() for name in match.group(1).split(",")]
            pull = next((re.search(r"#(\d+)", name).group(1) for name in names if name.startswith("pull request #")), None)
            if pull:
                return _diff_anchor(f"{base}/pull/{pull}/files", lines, back, index, f"pull request #{pull} (unmerged)")
            return f"{base}/compare/{quote(names[0])}", f"branch {names[0]} (unmerged)"
        match = CONVERSATION_HEADER.match(current)
        if match:
            return text_fragment(match.group(1), quote_text), match.group(1).rsplit("/", 2)[-2] + " #" + match.group(1).rsplit("/", 1)[-1]
        if current.startswith("--- COMMIT HISTORY") and history:
            return f"{base}/commit/{history.group(1)}", f"commit {history.group(1)}"
        if current.startswith("--- FILE TREE"):
            return f"{base}/tree/{commit}", f"file tree at {commit[:7]}"
    return base, "repository"


def _diff_anchor(url: str, lines: list[str], start: int, index: int, label: str) -> tuple[str, str]:
    """The quoted line inside a diff: GitHub's `#diff-<sha256(path)>R<line>` anchor."""
    path = ""
    new_line: int | None = None
    for position in range(start + 1, index + 1):
        current = lines[position]
        match = DIFF_FILE.match(current)
        if match:
            path, new_line = match.group(1), None
            continue
        match = HUNK.match(current)
        if match:
            new_line = int(match.group(1)) - 1
            continue
        survived = SURVIVED.match(current)
        if new_line is not None and survived:
            # Added lines still in the current file are counted in one marker line.
            new_line += int(survived.group(1))
        elif new_line is not None and not current.startswith("-"):
            new_line += 1
    if not path:
        return url, label
    anchor = f"#diff-{sha256(path.encode('utf-8')).hexdigest()}"
    if new_line:
        anchor += f"R{new_line}"
    return f"{url}{anchor}", f"{label}, {path}" + (f" line {new_line}" if new_line else "")


def _manifest(root: Path) -> dict[str, dict[str, str]]:
    path = root / "01-sources/MANIFEST.csv"
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row.get("id", ""): row for row in csv.DictReader(handle)}


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines() if path.is_file() else []


def deep_link(root: Path, source: dict[str, str], quote_text: str) -> dict[str, Any]:
    url = source.get("url", "")
    directory = root / "01-sources/captures" / source.get("id", "")
    transcript = _read_lines(directory / "transcript.txt")
    if transcript:
        index = locate(transcript, quote_text)
        if index is not None:
            link, anchor = _recording_link(url, transcript, index)
            return {"deep_link": link, "anchor": anchor, "kind": "recording", "located": True}
    content = _read_lines(directory / "content.txt")
    host = (urlparse(url).hostname or "").casefold().removeprefix("www.")
    if host == "github.com" and content and content[0].startswith("Repository: "):
        index = locate(content, quote_text, strip_diff=True)
        if index is not None:
            anchored = _repository_link(content, index, quote_text)
            if anchored:
                return {"deep_link": anchored[0], "anchor": anchored[1], "kind": "repository", "located": True}
        return {"deep_link": url, "anchor": "repository (quote not located)", "kind": "repository", "located": False}
    located = locate(content, quote_text) is not None if content else False
    if urlparse(url).scheme in {"http", "https"} and _segment(quote_text):
        return {"deep_link": text_fragment(url, quote_text), "anchor": "quoted text", "kind": "page", "located": located}
    return {"deep_link": url, "anchor": "source", "kind": "page", "located": located}


def write_fact_links(root: Path) -> dict[str, Any]:
    """Deep links for every filed fact, and a coverage report."""
    manifest = _manifest(root)
    paths = sorted((root / "02-facts").glob("*.md")) + sorted(root.glob("04-competitors/*/02-facts/*.md"))
    rows: list[dict[str, Any]] = []
    for fact in fact_tables.load_fact_tables(paths):
        source_id = str(fact.get("source_id", "")).strip()
        source = manifest.get(source_id, {"id": source_id, "url": ""})
        link = deep_link(root, source, str(fact.get("verbatim_quote", "")))
        rows.append({"fact_id": fact.get("fact_id", ""), "source_id": source_id, "url": source.get("url", ""), **link})
    atomic_write_jsonl(root / FACT_LINKS, rows)
    kinds: dict[str, list[int]] = {}
    for row in rows:
        counts = kinds.setdefault(row["kind"], [0, 0])
        counts[0] += 1
        counts[1] += int(row["located"])
    unlocated = [row for row in rows if not row["located"]]
    lines = [
        "# Fact deep links",
        "",
        "Each fact links to the place its quote sits in the source: a repository file and line at the "
        "captured commit, a line in a commit's or pull request's diff, a recording's timestamp, or a "
        "text fragment that highlights the quoted words on a page.",
        "",
        "| Kind | Facts | Quote located |",
        "|---|---|---|",
        *(f"| {kind} | {total} | {found} |" for kind, (total, found) in sorted(kinds.items())),
        "",
        f"## Quotes not located ({len(unlocated)})",
        "",
        "These keep the source URL (pages keep a text fragment, which still highlights the words when they "
        "appear on the live page).",
        "",
        *(f"- `{row['fact_id']}` ({row['source_id']}): {row['deep_link']}" for row in unlocated[:300]),
    ]
    atomic_write_text(root / LINKS_REPORT, "\n".join(lines) + "\n")
    return {"facts": len(rows), "located": len(rows) - len(unlocated), "by_kind": {kind: total for kind, (total, _) in kinds.items()}}


# A verifier judges a quote from the text around it, not the whole capture: the
# located line with about this many characters of context, the capture's first
# lines (title, repository, speakers), and the section the quote sits in.
EXCERPT_CHARACTERS = 1_600
SECTION_HEADER = re.compile(r"^(--- |=== )")


def source_excerpt(root: Path, source_id: str, quote_text: str) -> dict[str, Any]:
    directory = root / "01-sources/captures" / source_id
    for name, strip_diff in (("transcript.txt", False), ("content.txt", True)):
        lines = _read_lines(directory / name)
        index = locate(lines, quote_text, strip_diff=strip_diff) if lines else None
        if index is None:
            continue
        start, end, size = index, index + 1, len(lines[index])
        while size < EXCERPT_CHARACTERS and (start > 0 or end < len(lines)):
            if start > 0:
                start -= 1
                size += len(lines[start])
            if end < len(lines) and size < EXCERPT_CHARACTERS:
                size += len(lines[end])
                end += 1
        text = "\n".join(lines[start:end])
        if len(text) > EXCERPT_CHARACTERS * 2:
            # One very long line: keep the window around the quote.
            at = max(text.casefold().find(_segment(quote_text)[:40].casefold()), 0)
            text = text[max(at - EXCERPT_CHARACTERS // 2, 0): at + EXCERPT_CHARACTERS]
        section = next((lines[position] for position in range(start - 1, -1, -1) if SECTION_HEADER.match(lines[position])), "")
        return {
            "located": True, "file": f"01-sources/captures/{source_id}/{name}", "line": index + 1,
            "lines": f"{start + 1}-{end}", "head": lines[:6], "section": section[:300], "text": text,
        }
    return {"located": False, "file": "", "note": "quote not found by script; open the capture"}
