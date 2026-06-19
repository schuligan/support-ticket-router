"""Agentic auto-resolution against the knowledge base.

Confidence gating decides between two outcomes:

* If a confident KB answer exists (score >= threshold) the agent drafts a reply
  grounded in that article and marks the ticket resolved.
* Otherwise it hands off to a human with an explicit reason.

The mock path scores by keyword overlap; the LLM path asks Claude to pick the
best candidate article and judge whether it actually answers the question.
"""

from __future__ import annotations

from typing import Any

from .config import Config
from .kb import KBArticle, best_match
from .llm import LLMUnavailable, call_json
from .models import InboundMessage, Resolution, Triage

_RESOLVE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "kb_article_id": {"type": "string"},
        "answers_question": {"type": "boolean"},
        "confidence": {"type": "number"},
        "draft_reply": {"type": "string"},
    },
    "required": ["kb_article_id", "answers_question", "confidence", "draft_reply"],
    "additionalProperties": False,
}

_SYSTEM = (
    "You are a support auto-resolution agent for 'Acme Cloud'. Given a customer "
    "message and a set of candidate knowledge-base articles, decide whether one "
    "article confidently answers the question. If so, write a concise, friendly "
    "reply grounded ONLY in that article. If no article truly answers it, set "
    "answers_question to false and confidence low. Return JSON only."
)


def _draft_from_article(msg: InboundMessage, article: KBArticle) -> str:
    return (
        f"Hi {msg.sender_name.split()[0]},\n\n"
        f"Thanks for reaching out. {article.body}\n\n"
        f"If that doesn't resolve it, just reply and a teammate will jump in.\n\n"
        f"— Acme Cloud Support"
    )


def _mock_resolve(
    msg: InboundMessage,
    articles: list[KBArticle],
    threshold: float,
) -> Resolution:
    text = f"{msg.subject}\n{msg.body}"
    article, score = best_match(text, articles)
    if article is not None and score >= threshold:
        return Resolution(
            resolved=True,
            confidence=round(score, 3),
            kb_article_id=article.id,
            draft_reply=_draft_from_article(msg, article),
            handoff_reason=None,
            source="mock",
        )
    reason = (
        "no knowledge-base article matched with sufficient confidence "
        f"(best score {round(score, 3)} < threshold {threshold})"
        if article is not None
        else "no knowledge-base article matched at all"
    )
    return Resolution(
        resolved=False,
        confidence=round(score, 3),
        kb_article_id=article.id if article else None,
        draft_reply=None,
        handoff_reason=reason,
        source="mock",
    )


def _llm_resolve(
    msg: InboundMessage,
    triage: Triage,
    articles: list[KBArticle],
    config: Config,
) -> Resolution:
    catalog = "\n\n".join(
        f"[{a.id}] {a.title}\n{a.body}" for a in articles
    )
    user_content = (
        f"Customer message:\nSubject: {msg.subject}\n{msg.body}\n\n"
        f"Triage summary: {triage.summary}\n\n"
        f"Candidate KB articles:\n{catalog}"
    )
    result = call_json(
        api_key=config.api_key or "",
        model_id=config.model_id,
        system=_SYSTEM,
        user_content=user_content,
        schema=_RESOLVE_SCHEMA,
    )
    confidence = float(result["confidence"])
    answers = bool(result["answers_question"])
    article_id = str(result["kb_article_id"]) or None
    if answers and confidence >= config.auto_resolve_threshold:
        return Resolution(
            resolved=True,
            confidence=round(confidence, 3),
            kb_article_id=article_id,
            draft_reply=str(result["draft_reply"]),
            handoff_reason=None,
            source="llm",
        )
    return Resolution(
        resolved=False,
        confidence=round(confidence, 3),
        kb_article_id=article_id,
        draft_reply=None,
        handoff_reason=(
            "agent judged that no KB article confidently answers the question"
            if not answers
            else f"confidence {round(confidence, 3)} below threshold "
            f"{config.auto_resolve_threshold}"
        ),
        source="llm",
    )


def resolve_message(
    msg: InboundMessage,
    triage: Triage,
    articles: list[KBArticle],
    config: Config,
) -> Resolution:
    """Attempt auto-resolution; fall back to mock on any LLM failure."""
    if config.mock_mode:
        return _mock_resolve(msg, articles, config.auto_resolve_threshold)
    try:
        return _llm_resolve(msg, triage, articles, config)
    except (LLMUnavailable, KeyError, ValueError):
        return _mock_resolve(msg, articles, config.auto_resolve_threshold)
