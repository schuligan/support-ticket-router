"""End-to-end pipeline: ticket creation, resolution/handoff, idempotency."""

from __future__ import annotations

from router.models import TicketStatus
from router.pipeline import process_all, process_message

from .helpers import make_message


def test_ticket_created_with_id_and_sla(config, store, audit, articles, clock):
    msg = make_message(
        subject="How do I reset my API key?",
        body="regenerate api key in settings",
    )
    result = process_message(
        msg, store=store, audit=audit, articles=articles, config=config, clock=clock
    )
    assert result.ticket.id.startswith("TCK-")
    assert result.ticket.sla_due_at > result.ticket.created_at
    assert store.get(result.ticket.id) is not None


def test_resolvable_message_marks_ticket_resolved(
    config, store, audit, articles, clock
):
    msg = make_message(
        subject="Reset API key",
        body="where do I regenerate my api key credentials in settings",
    )
    result = process_message(
        msg, store=store, audit=audit, articles=articles, config=config, clock=clock
    )
    assert result.ticket.status is TicketStatus.RESOLVED
    assert result.ticket.draft_reply is not None


def test_unresolvable_message_awaits_human(
    config, store, audit, articles, clock
):
    msg = make_message(
        subject="Random unrelated question",
        body="What is the airspeed velocity of an unladen swallow?",
    )
    result = process_message(
        msg, store=store, audit=audit, articles=articles, config=config, clock=clock
    )
    assert result.ticket.status is TicketStatus.AWAITING_HUMAN
    assert result.ticket.handoff_reason is not None


def test_idempotent_skip_on_reprocess(config, store, audit, articles, clock):
    msg = make_message()
    process_all(
        [msg], store=store, audit=audit, articles=articles, config=config, clock=clock
    )
    results = process_all(
        [msg], store=store, audit=audit, articles=articles, config=config, clock=clock
    )
    assert results[0].skipped is True
    assert len(store.all()) == 1


def test_audit_appends_entries(config, store, audit, articles, clock):
    msg = make_message(subject="Reset API key", body="regenerate api key settings")
    process_message(
        msg, store=store, audit=audit, articles=articles, config=config, clock=clock
    )
    actions = [e["action"] for e in audit.read_all()]
    assert "triage" in actions
    assert "ticket_created" in actions
    assert any(a in actions for a in ("auto_resolved", "handoff"))
