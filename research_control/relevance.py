"""How much a piece of source text bears on the research questions, without a model.

Used to choose which slices to extract when a token budget will not cover them
all, and to skip slices that share no terms with the questions a focused
re-extraction is for. The score counts the questions' distinctive words in the
text, damped so long text does not win by length alone.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path

QUESTION_BLOCK = re.compile(r"^\*\*(Q\d+)\.\s+(.+?)\*\*(.*?)(?=^\*\*Q\d+\.|^#|\Z)", re.M | re.S)
WORD = re.compile(r"[a-z][a-z0-9]{3,}")
STOP_WORDS = {
    "what", "which", "where", "when", "does", "have", "with", "from", "that", "this", "their", "there", "they",
    "them", "into", "over", "under", "each", "every", "about", "between", "more", "most", "other", "such", "than",
    "then", "these", "those", "were", "will", "would", "could", "should", "also", "only", "both", "much", "many",
    "evidence", "public", "company", "channels", "including", "whether", "show", "shows",
}


def _stem(word: str) -> str:
    for suffix in ("ings", "ing", "ies", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return word


def question_texts(root: Path) -> dict[str, str]:
    """Each numbered question in `00-scope.md`, title and text."""
    path = root / "00-scope.md"
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    return {match.group(1): f"{match.group(2)} {match.group(3)}" for match in QUESTION_BLOCK.finditer(text)}


def terms(root: Path, questions: list[str] | None = None) -> set[str]:
    texts = question_texts(root)
    chosen = [texts[question] for question in (questions or list(texts)) if question in texts]
    return {_stem(word) for text in chosen for word in WORD.findall(text.casefold()) if word not in STOP_WORDS}


def score(text: str, wanted: set[str]) -> tuple[float, int]:
    """(score, distinct question terms present) for a piece of text."""
    if not wanted:
        return 0.0, 0
    counts = Counter(_stem(word) for word in WORD.findall(text.casefold()))
    hits = [term for term in wanted if counts.get(term)]
    total = sum(math.log1p(counts[term]) for term in hits)
    return total / math.log(sum(counts.values()) + 3), len(hits)
