"""Orchestrator: ingest -> triage -> ticket -> auto-resolve/handoff.

This is the heart of the agent. For each inbound message it triages, creates a
ticket, attempts KB-grounded resolution, and either marks the ticket resolved
(with a drafted reply) or hands it off to a human with a reason. Every step is
audited.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .audit import AuditLog
from .clock import Clock
from .config import Config
from .kb import KBArticle
from .models import InboundMessage, Resolution, Ticket, TicketStatus, Triage
from .resolve import resolve_message
from .store import TicketStore
from .triage import triage_message


@dataclass
class ProcessResult:
    """What happened to a single message."""

    message: InboundMessage
    triage: Triage
    resolution: Resolution
    ticket: Ticket
    skipped: bool = False  # True if the message was already ticketed


def process_message(
    msg: InboundMessage,
    *,
    store: TicketStore,
    audit: AuditLog,
    articles: list[KBArticle],
    config: Config,
    clock: Clock,
) -> ProcessResult:
    """Run the full agentic pipeline for one message."""
    now = clock.now()

    triage = triage_message(msg, config)
    audit.record(
        "triage",
        now,
        message_id=msg.id,
        category=triage.category.value,
        priority=triage.priority.value,
        confidence=triage.confidence,
        source=triage.source,
    )

    ticket = _open_ticket(msg, triage, now)
    ticket.id = store.next_id()
    store.add(ticket)
    audit.record(
        "ticket_created",
        now,
        ticket_id=ticket.id,
        message_id=msg.id,
        priority=ticket.priority.value,
        sla_due_at=ticket.sla_due_at.isoformat(),
    )

    resolution = resolve_message(msg, triage, articles, config)
    _apply_resolution(ticket, resolution, now, audit)
    store.update(ticket)

    return ProcessResult(
        message=msg, triage=triage, resolution=resolution, ticket=ticket
    )


def process_all(
    messages: list[InboundMessage],
    *,
    store: TicketStore,
    audit: AuditLog,
    articles: list[KBArticle],
    config: Config,
    clock: Clock,
) -> list[ProcessResult]:
    """Process messages, skipping any whose message_id was already ticketed."""
    results: list[ProcessResult] = []
    for msg in messages:
        if store.has_message(msg.id):
            existing = next(
                t for t in store.all() if t.message_id == msg.id
            )
            results.append(
                ProcessResult(
                    message=msg,
                    triage=_triage_from_ticket(existing),
                    resolution=_resolution_from_ticket(existing),
                    ticket=existing,
                    skipped=True,
                )
            )
            continue
        results.append(
            process_message(
                msg,
                store=store,
                audit=audit,
                articles=articles,
                config=config,
                clock=clock,
            )
        )
    return results


# --- helpers ---------------------------------------------------------------


def _open_ticket(msg: InboundMessage, triage: Triage, now: datetime) -> Ticket:
    return Ticket(
        id="PENDING",  # replaced below once we know the store
        message_id=msg.id,
        channel=msg.channel,
        customer=triage.customer or msg.sender_name,
        sender_email=msg.sender_email,
        subject=msg.subject,
        category=triage.category,
        priority=triage.priority,
        status=TicketStatus.OPEN,
        summary=triage.summary,
        created_at=now,
        sla_due_at=Ticket.sla_due(now, triage.priority),
        history=[{"ts": now.isoformat(), "event": "opened"}],
    )


def _apply_resolution(
    ticket: Ticket, resolution: Resolution, now: datetime, audit: AuditLog
) -> None:
    ticket.kb_article_id = resolution.kb_article_id
    if resolution.resolved:
        ticket.status = TicketStatus.RESOLVED
        ticket.resolved_at = now
        ticket.draft_reply = resolution.draft_reply
        ticket.history.append(
            {
                "ts": now.isoformat(),
                "event": "auto_resolved",
                "kb_article_id": resolution.kb_article_id,
                "confidence": resolution.confidence,
            }
        )
        audit.record(
            "auto_resolved",
            now,
            ticket_id=ticket.id,
            kb_article_id=resolution.kb_article_id,
            confidence=resolution.confidence,
            source=resolution.source,
        )
    else:
        ticket.status = TicketStatus.AWAITING_HUMAN
        ticket.handoff_reason = resolution.handoff_reason
        ticket.history.append(
            {
                "ts": now.isoformat(),
                "event": "handoff",
                "reason": resolution.handoff_reason,
                "confidence": resolution.confidence,
            }
        )
        audit.record(
            "handoff",
            now,
            ticket_id=ticket.id,
            reason=resolution.handoff_reason,
            confidence=resolution.confidence,
            source=resolution.source,
        )


def _triage_from_ticket(ticket: Ticket) -> Triage:
    return Triage(
        category=ticket.category,
        priority=ticket.priority,
        intent="(recorded)",
        customer=ticket.customer,
        product_area="Acme Cloud",
        summary=ticket.summary,
        confidence=0.0,
        source="store",
    )


def _resolution_from_ticket(ticket: Ticket) -> Resolution:
    return Resolution(
        resolved=ticket.status == TicketStatus.RESOLVED,
        confidence=0.0,
        kb_article_id=ticket.kb_article_id,
        draft_reply=ticket.draft_reply,
        handoff_reason=ticket.handoff_reason,
        source="store",
    )
