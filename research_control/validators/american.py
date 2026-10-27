"""American English in authored text: spelling and vocabulary, everywhere a worker writes.

Checks the words a worker writes (claims, notes, reasons, synthesis, reviews,
the report, diagram labels), not the words it quotes. Verbatim quotes, quoted
titles, code, URLs, and names (a capitalized word inside a sentence, such as
"Ministry of Defence" or "Royal London") keep the source's spelling. Everything
else uses American spelling (program, color, organize, center, license as a
noun, modeled) and American vocabulary (job posting, not job advert; fiscal
year, not financial year; the company is, not the company are).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterator

_ISE_STEMS = (
    "organ|reorgan|recogn|real|priorit|optim|custom|standard|maxim|minim|summar|emphas|special|util|final|categor|"
    "character|central|decentral|digit|monet|normal|operational|personal|capital|apolog|author|critic|general|local|"
    "mobil|modern|neutral|visual|synthes|memor|public|social|stabil|sanit|token|vector|container|product|commercial|"
    "industrial|democrat|harmon|incentiv|legitim|jeopard|scrutin|hypothes|theor|global|international|initial|serial|"
    "parallel|human|rational|subsid|fertil|equal|formal|polar|revital|symbol|sympath|trivial|urban|patron|penal|"
    "agon|antagon|crystal|energ|familiar|fantas|galvan|hospital|ideal|immun|item|legal|liberal|mechan|metabol|"
    "miniatur|moral|motor|national|natural|oxid|plagiar|popular|pressur|proselyt|regular|scandal|secular|sensit|"
    "signal|stigmat|terror|tranquil|tyrann|unional|vapor|victim|vocal|westernis|desensit|contextual|conceptual|"
    "operation|productional|commodit|computer|virtual|annual|anonym|automat|bastard|canonical|catechis|"
    "colon|compartmental|deputis|dramat|economis|emphas|epitom|eulog|evangel|extern|feminis|fossil|glamor|"
    "hierarch|homogen|immortal|individual|institutional|internal|journal|lexical|marginal|maxim|metaphor|"
    "mesmer|methodolog|minimal|monopol|ostrac|pasteur|patron|politic|prioritis|rubber|sermon|solemn|"
    "spiritual|summar|tantal|temporal|textual|unionis|vandal|vulgar|weatherpro"
)
SPELLING: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(?:colo|behavio|favo|hono|labo|neighbo|rumo|flavo|harbo|humo|savo|endeavo|armo|odo|parlo|vigo|"
                r"valo|clamo|splendo|fervo|rigo|ardo|cando|demeano|glamo)ur(?:s|ed|ing|ite|ites|itism|able|ably|ful|"
                r"fully|less|er|ers|hood|ly|ism|ist|ists)?\b", re.I), "-or spelling (color, behavior, favorite, labor)"),
    (re.compile(rf"\b(?:{_ISE_STEMS})is(?:e|es|ed|ing|ation|ations|er|ers|able)\b", re.I),
     "-ize spelling (organize, prioritize, optimization)"),
    (re.compile(r"\b(?:analy|paraly|cataly|dialy)s(?:e|ed|ing|er|ers)\b", re.I), "-yze spelling (analyze, analyzed)"),
    (re.compile(r"\b(?:cent|theat|fib|lit|calib|spect|lust|somb|meag|sab|reconnoit|kilomet|centimet|millimet|met|"
                r"manoeuv)re(?:s|d)?\b", re.I), "-er spelling (center, theater, fiber, meter)"),
    (re.compile(r"\b(?:catalog|analog)ue(?:s|d)?\b", re.I), "catalog, analog"),
    (re.compile(r"\b(?:licen|defen|offen|preten)ce(?:s|d)?\b", re.I), "license, defense, offense, pretense"),
    (re.compile(r"\b(?:travel|cancel|model|label|signal|fuel|level|counsel|channel|tunnel|marvel|jewel|dial|duel|"
                r"equal|rival|total|quarrel|shovel|pencil|initial|tranquil|funnel|panel|parcel|program)l(?:ed|ing|er|"
                r"ers)\b", re.I), "single l (modeled, canceled, labeling, traveler)"),
    (re.compile(r"\bprogrammes?\b|\bprogrammed\b(?! (?:in|to|with|using) (?:python|code|java))", re.I), "program"),
    (re.compile(r"\b(?:enrolment|fulfilment|instalment|skilful|wilful|fulfils?)\b", re.I),
     "double l (enrollment, fulfillment, installment, skillful, fulfill)"),
    (re.compile(r"\b(?:judgement|acknowledgement|abridgement)s?\b", re.I), "judgment, acknowledgment"),
    (re.compile(r"\b(?:ageing|artefacts?|cheques?|greys?|aluminium|aeroplanes?|mould(?:s|ed|ing)?|ploughs?|storeys|"
                r"sceptic(?:al|ism|s)?|sulphur|tyres?|kerbs?|draughts?|focuss(?:ed|es|ing)|benefitt(?:ed|ing)|"
                r"paediatric\w*|encyclopaedi\w*|mediaeval|foetus|pyjamas|connexion|practis(?:e|es|ed|ing)|"
                r"defenceless|plagiaris\w*|whisky)\b", re.I),
     "American spelling (aging, artifact, check, gray, mold, skeptical, tire, focused, benefited, practice)"),
)
VOCABULARY: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bjob adverts?\b|\bjob advertisements?\b", re.I), "job posting"),
    (re.compile(r"(?<!job )\badverts?\b", re.I), "ad or posting"),
    (re.compile(r"\bvacanc(?:y|ies)\b", re.I), "opening or open role"),
    (re.compile(r"\bfinancial years?\b", re.I), "fiscal year"),
    (re.compile(r"(?<!staff )(?<!employee )(?<!customer )(?<!talent )(?<!team )\bturnover\b", re.I),
     "revenue (turnover means staff or customer attrition in American English)"),
    (re.compile(r"\b(?:year|month|quarter|week) on (?:year|month|quarter|week)\b", re.I), "year over year"),
    (re.compile(r"\bfortnight(?:s|ly)?\b", re.I), "two weeks"),
    (re.compile(r"\bat (?:the )?weekends?\b", re.I), "on the weekend"),
    (re.compile(r"\bin future(?=[,.;:)]|\s+(?:it|the|we|they|this|that)\b)", re.I), "in the future"),
    (re.compile(r"\bdifferent to\b", re.I), "different from"),
    (re.compile(r"\b(?:whilst|amongst|amidst|learnt|spelt|spoilt|dreamt|leapt)\b", re.I),
     "while, among, amid, learned, spelled"),
    (re.compile(r"\btowards\b", re.I), "toward"),
    (re.compile(r"\bper cent\b", re.I), "percent"),
    (re.compile(r"\bmaths\b", re.I), "math"),
    (re.compile(r"\bmobile phones?\b", re.I), "cellphone"),
    (re.compile(r"\bcurriculum vitae\b", re.I), "résumé"),
    (re.compile(r"\bremit\b", re.I), "scope or mandate"),
    (re.compile(r"\bbespoke\b", re.I), "custom"),
    (re.compile(r"\bon the back of\b", re.I), "following or because of"),
    (re.compile(r"\bat pace\b", re.I), "quickly"),
    (re.compile(r"\bfull stop\b", re.I), "period"),
    (re.compile(r"\b(?:car park|lorr(?:y|ies)|petrol|motorway|postcode)\b", re.I), "American term"),
    (re.compile(r"\bthe (?:team|company|firm|board|government|committee|business|startup|agency|consultancy) "
                r"(?:are|were|have)\b", re.I), "a singular verb (the company is, the team has)"),
    (re.compile(r"\bconsultanc(?:y|ies)\b", re.I), "consulting firm"),
    (re.compile(r"\b(?:headteacher|solicitors?|barristers?|chemist's|high street)\b", re.I), "American term"),
)
CONNECTORS = {"for", "of", "and", "de", "the", "&", "on", "in", "to"}
# Table columns and record fields that hold the source's own words, not the worker's.
QUOTED_COLUMNS = {
    "verbatim quote", "quote", "verbatim", "title", "source title", "said by", "speaker", "location", "url", "deep link",
    "link", "source id", "source", "fact id", "anchor", "publisher", "file", "path", "local file", "method",
}
AUTHORED_FIELDS = {
    "claim", "notes", "note", "reason", "summary", "finding", "description", "recommendation", "recommended_fix",
    "fix", "rationale", "issue", "explanation", "disposition_reason", "question", "answer", "label", "caption",
    "subtitle", "change", "decision_reason", "detail", "why", "corrected_claim",
}


def _shielded(text: str) -> str:
    """The text with quotes, code, URLs, link targets, and fact IDs blanked out (same length)."""
    def blank(match: re.Match[str]) -> str:
        return " " * len(match.group(0))
    for pattern in (r"`[^`]*`", r'"[^"\n]*"', r"“[^”\n]*”", r"\]\([^)]*\)", r"https?://\S+", r"<[^>]+>",
                    r"\b[\w.-]+/[\w./-]+\b", r"\b[\w-]+\.(?:md|jsonl?|csv|py|txt|html|svg|pdf|yaml)\b",
                    r"\b[a-z]+(?:[-_][a-z]+)*[-_](?:catalogue|programme)\b|\b(?:catalogue|programme)[-_][a-z]+\b",
                    r"\b[A-Z][A-Z0-9-]*-[A-Z]*\d+[a-z]?\b"):
        text = re.sub(pattern, blank, text)
    return text


def _is_name(text: str, start: int, end: int) -> bool:
    """A capitalized word inside a sentence, or one that begins a multiword name, is a name."""
    if not text[start].isupper():
        return False
    before = text[:start].rstrip(" \t*_([")
    sentence_start = not before or before[-1] in ".!?:|#-" or re.search(r"(?:^|\s)\d+\.$", before) is not None
    if not sentence_start:
        return True
    # At a sentence start, a name continues in capitals ("Centre for AI Safety", "Programme Board").
    following = re.match(r"\s+([\w&'-]+)(?:\s+([\w&'-]+))?", text[end:])
    if not following:
        return False
    word, after = following.group(1), following.group(2) or ""
    return word[0].isupper() or (word.casefold() in CONNECTORS and after[:1].isupper())


def findings(text: str) -> list[tuple[str, str]]:
    """(word, use instead) for each British spelling or term in authored text."""
    shielded = _shielded(text)
    found: list[tuple[str, str]] = []
    for pattern, advice in SPELLING + VOCABULARY:
        for match in pattern.finditer(shielded):
            if not _is_name(shielded, match.start(), match.end()):
                found.append((text[match.start():match.end()], advice))
    return found


def _markdown_lines(text: str) -> Iterator[tuple[int, str]]:
    """Authored lines of Markdown, with quoted-source table columns and block quotes left out."""
    header: list[str] | None = None
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith(">"):
            continue
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [cell.strip() for cell in re.split(r"(?<!\\)\|", stripped.strip("|"))]
            if all(re.fullmatch(r":?-+:?", cell) for cell in cells if cell):
                continue
            if header is None:
                header = [cell.casefold().strip("* ") for cell in cells]
                yield number, " | ".join(cells)
                continue
            kept = [cell for index, cell in enumerate(cells)
                    if index >= len(header) or header[index] not in QUOTED_COLUMNS]
            yield number, " | ".join(kept)
            continue
        header = None
        yield number, line


def _authored_values(value: Any, key: str = "") -> Iterator[str]:
    if isinstance(value, dict):
        for name, item in value.items():
            yield from _authored_values(item, str(name).casefold())
    elif isinstance(value, list):
        for item in value:
            yield from _authored_values(item, key)
    elif isinstance(value, str) and key in AUTHORED_FIELDS:
        yield value


def check_file(path: Path) -> list[str]:
    """Every British spelling or term in a file's authored text, as `line N: word (use ...)`."""
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8", errors="replace")
    problems: list[str] = []
    suffix = path.suffix.lower()
    if suffix in {".md", ".txt"}:
        lines = list(_markdown_lines(text))
    elif suffix == ".jsonl":
        lines = []
        for number, line in enumerate(text.splitlines(), 1):
            try:
                lines += [(number, value) for value in _authored_values(json.loads(line))]
            except json.JSONDecodeError:
                continue
    elif suffix == ".json":
        try:
            lines = [(0, value) for value in _authored_values(json.loads(text))]
        except json.JSONDecodeError:
            lines = []
    elif suffix in {".svg", ".html"}:
        # Scripts, styles, and quoted copy (block and inline quotes) are not authored text.
        visible = re.sub(r"<(script|style|blockquote|q)\b.*?</\1>", " ", text, flags=re.S | re.I)
        lines = [(0, re.sub(r"<[^>]+>", " ", visible))]
    else:
        return []
    for number, line in lines:
        for word, advice in findings(line):
            where = f"line {number}: " if number else ""
            problems.append(f'{where}"{word}" (use {advice})')
    return problems


def check_paths(root: Path, relatives: list[str], limit: int = 40) -> list[str]:
    problems: list[str] = []
    for relative in relatives:
        for problem in check_file(root / relative):
            problems.append(f"{relative} {problem}")
            if len(problems) >= limit:
                return problems
    return problems
