"""Synthetic knowledge base loading and keyword scoring.

The KB is a small set of articles. ``best_match`` scores a message against every
article by keyword overlap and returns the strongest match with a normalized
confidence in [0, 1]. This deterministic scorer powers the mock path and also
seeds the candidate set handed to the LLM on the real path.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class KBArticle:
    id: str
    title: str
    keywords: tuple[str, ...]
    category: str
    body: str


def load_kb(path: Path) -> list[KBArticle]:
    with path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    return [
        KBArticle(
            id=a["id"],
            title=a["title"],
            keywords=tuple(k.lower() for k in a["keywords"]),
            category=a["category"],
            body=a["body"],
        )
        for a in raw
    ]


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower())


def score_article(text: str, article: KBArticle) -> float:
    """Fraction of an article's keywords that appear in ``text``."""
    haystack = _normalize(text)
    if not article.keywords:
        return 0.0
    hits = sum(1 for kw in article.keywords if kw in haystack)
    return hits / len(article.keywords)


def best_match(
    text: str, articles: list[KBArticle]
) -> tuple[KBArticle | None, float]:
    """Return the highest-scoring article and its score (0.0 if none match)."""
    best: KBArticle | None = None
    best_score = 0.0
    for article in articles:
        s = score_article(text, article)
        if s > best_score:
            best, best_score = article, s
    return best, best_score
