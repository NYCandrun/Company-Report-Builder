"""The final report's outline, built from the run's own research questions.

The report answers the questions the run asked, so its sections are those
questions in their numbered order, between a fixed opening (the cover and a
portfolio exhibit) and a fixed close (the catalogue, open questions, the
limits of the evidence, and source notes). Its length scales with the number
of questions. When the questions cover customers, clients, accounts, or
engagements, the report carries an exhibit of accounts over time. The cover's
focus line is the scope's own `Focus:` line, or a general one.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from research_control.io import atomic_write_json, utc_now
from research_control.relevance import question_texts

OUTLINE = "tools/lists/report-outline.json"
# Words for the opening summary, open questions, evidence limits, and source notes,
# then for each question's section; the report may run a quarter over or under.
BASE_WORDS = 1_500
WORDS_PER_QUESTION = 450
TOLERANCE = 0.25
FOCUS_LINE = re.compile(r"^\s*(?:\*\*)?Focus:(?:\*\*)?\s*(.+?)\s*$", re.M | re.I)
DEFAULT_FOCUS = "Company research"
ACCOUNT_WORDS = re.compile(r"\b(accounts?|clients?|customers?|engagements?)\b", re.I)


def _title(text: str) -> str:
    return re.sub(r"\s+", " ", text.split(".", 1)[0]).strip()


def build_outline(root: Path) -> dict[str, Any]:
    questions = question_texts(root)
    scope = root / "00-scope.md"
    focus_match = FOCUS_LINE.search(scope.read_text(encoding="utf-8")) if scope.is_file() else None
    sections = [
        {"question": number, "title": _title(text), "words": WORDS_PER_QUESTION}
        for number, text in sorted(questions.items(), key=lambda pair: int(pair[0][1:]))
    ]
    target = BASE_WORDS + WORDS_PER_QUESTION * len(sections)
    accounts = [section["question"] for section, text in zip(sections, (questions[s["question"]] for s in sections))
                if ACCOUNT_WORDS.search(text)]
    return {
        "created": utc_now(),
        "focus": focus_match.group(1).strip() if focus_match else DEFAULT_FOCUS,
        "opening": ["cover", "summary with a portfolio exhibit of what the company offers"],
        "sections": sections,
        "accounts_exhibit": {"include": bool(accounts), "questions": accounts},
        "closing": ["catalogue (four parts)", "open questions and whom to ask", "limits of the evidence", "source notes"],
        "words": {"target": target, "minimum": int(target * (1 - TOLERANCE)), "maximum": int(target * (1 + TOLERANCE))},
    }


def write_report_outline(root: Path) -> dict[str, Any]:
    outline = build_outline(root)
    if not outline["sections"]:
        raise ValueError("00-scope.md lists no numbered research questions to build the report from")
    atomic_write_json(root / OUTLINE, outline)
    return {"sections": len(outline["sections"]), "words": outline["words"], "accounts_exhibit": outline["accounts_exhibit"]["include"]}


def report_words(text: str) -> int:
    """The report's prose words: tables (exhibits) and fact IDs are not counted."""
    text = re.sub(r"\[[A-Z][A-Z0-9-]*-[A-Z]*\d+[a-z]?(?:[,;] ?[A-Z][A-Z0-9-]*-[A-Z]*\d+[a-z]?)*\]", "", text)
    text = re.sub(r"^\s*\|.*$", "", text, flags=re.M)
    return len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'’.-]*", text))
