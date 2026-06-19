"""Auto-resolution vs handoff, gated on KB match confidence."""

from __future__ import annotations

from router.resolve import resolve_message
from router.triage import triage_message

from .helpers import make_message


def test_auto_resolves_when_kb_matches(config, articles):
    msg = make_message(
        subject="How do I reset my API key?",
        body="I rotated my password but can't find where to regenerate my API key "
        "in settings. Please reset credentials.",
    )
    triage = triage_message(msg, config)
    resolution = resolve_message(msg, triage, articles, config)
    assert resolution.resolved is True
    assert resolution.kb_article_id == "kb-001"
    assert resolution.draft_reply is not None
    assert resolution.handoff_reason is None
    assert resolution.confidence >= config.auto_resolve_threshold


def test_hands_off_when_no_kb_match(config, articles):
    msg = make_message(
        subject="Feature idea: dark mode",
        body="Would love a dark mode option for the dashboard someday.",
    )
    triage = triage_message(msg, config)
    resolution = resolve_message(msg, triage, articles, config)
    assert resolution.resolved is False
    assert resolution.draft_reply is None
    assert resolution.handoff_reason is not None


def test_webhook_401_resolves_to_correct_article(config, articles):
    msg = make_message(
        subject="Webhook integration",
        body="The webhook integration keeps throwing a 401 even though my token "
        "looks correct. The signing secret is set.",
    )
    triage = triage_message(msg, config)
    resolution = resolve_message(msg, triage, articles, config)
    assert resolution.resolved is True
    assert resolution.kb_article_id == "kb-003"
