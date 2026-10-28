"""The final report's outline: a company brief arranged top down, covering every research question.

The research questions are a checklist, not the report's structure: many are
written into the scope by default rather than asked by the user. The report
opens with an executive summary, then moves from broad context to specifics
(the company and its history, its market, what it sells and how it is built,
how it sells, its customers and accounts, its people and organization, its
direction), and closes with the catalog, open questions, the limits of the
evidence, and source notes. Each question is placed in the part it belongs
to, so every one is answered, under plain topical headings. There is no
length target: the report is as long as the evidence needs and no longer. The
cover's focus is the scope's own `Focus:` line, or the whole company.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from research_control.io import atomic_write_json, utc_now
from research_control.relevance import question_texts

OUTLINE = "tools/lists/report-outline.json"
FOCUS_LINE = re.compile(r"^\s*(?:\*\*)?Focus:(?:\*\*)?\s*(.+?)\s*$", re.M | re.I)
DEFAULT_FOCUS = "The whole company"
ACCOUNT_WORDS = re.compile(r"\b(accounts?|clients?|customers?|engagements?)\b", re.I)
# Parts from broad to specific; a question goes to the first part whose words its
# title matches, else to the part its title and text share most words with.
PARTS = (
    ("company", "The company: history, model, scale, and ownership",
     ("history", "founded", "founding", "talent network", "business model", "model", "scale", "financial", "revenue",
      "funding", "investor", "ownership", "acquisition", "acquired")),
    ("market", "Market, positioning, and competitors",
     ("position", "messaging", "competitor", "comparison", "market", "category")),
    ("offering", "What it sells and how it is built",
     ("product", "architecture", "offering", "service", "dependenc", "partner", "platform", "technology", "capabilit")),
    ("commercial", "How it sells: buyers, buying motion, and pricing",
     ("buyer", "buying", "sales", "pricing", "price", "go-to-market", "channel")),
    ("customers", "Customers, accounts, and engagements",
     ("customer", "client", "account", "engagement", "proof", "case stud")),
    ("organization", "People and organization",
     ("people", "organization", "leader", "team", "talent", "hiring", "headcount", "culture")),
    ("direction", "Direction: launches, roadmap, and what is next",
     ("direction", "launch", "roadmap", "plan", "future", "next")),
)


def _title(text: str) -> str:
    return re.sub(r"\s+", " ", text.split(".", 1)[0]).strip()


def _part_for(title: str, text: str) -> str:
    lowered = title.casefold()
    for key, _, words in PARTS:
        if any(word in lowered for word in words):
            return key
    body = text.casefold()
    scores = [(sum(body.count(word) for word in words), -index, key) for index, (key, _, words) in enumerate(PARTS)]
    best = max(scores)
    return best[2] if best[0] else "company"


def build_outline(root: Path) -> dict[str, Any]:
    questions = question_texts(root)
    scope = root / "00-scope.md"
    focus_match = FOCUS_LINE.search(scope.read_text(encoding="utf-8")) if scope.is_file() else None
    ordered = sorted(questions.items(), key=lambda pair: int(pair[0][1:]))
    placed: dict[str, list[dict[str, str]]] = {key: [] for key, _, _ in PARTS}
    for number, text in ordered:
        placed[_part_for(_title(text), text)].append({"question": number, "topic": _title(text)})
    parts = [
        {"part": key, "heading": heading, "covers": placed[key]}
        for key, heading, _ in PARTS if placed[key]
    ]
    accounts = [number for number, text in ordered if ACCOUNT_WORDS.search(text)]
    return {
        "created": utc_now(),
        "focus": focus_match.group(1).strip() if focus_match else DEFAULT_FOCUS,
        "opening": "executive summary",
        "parts": parts,
        "accounts_exhibit": {"include": bool(accounts), "questions": accounts},
        "closing": ["catalog (four parts)", "open questions and whom to ask", "limits of the evidence", "sources"],
    }


def write_report_outline(root: Path) -> dict[str, Any]:
    outline = build_outline(root)
    if not outline["parts"]:
        raise ValueError("00-scope.md lists no numbered research questions to build the report from")
    atomic_write_json(root / OUTLINE, outline)
    return {"parts": [part["part"] for part in outline["parts"]], "accounts_exhibit": outline["accounts_exhibit"]["include"]}
