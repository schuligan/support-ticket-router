"""Test helpers for constructing synthetic inbound messages."""

from __future__ import annotations

from datetime import UTC, datetime

from router.models import Channel, InboundMessage


def make_message(
    *,
    id: str = "msg-1",
    channel: Channel = Channel.EMAIL,
    sender_name: str = "Alex Rivera",
    sender_email: str = "alex@example.com",
    subject: str = "Question",
    body: str = "How do I do the thing?",
    received_at: datetime | None = None,
) -> InboundMessage:
    return InboundMessage(
        id=id,
        channel=channel,
        sender_name=sender_name,
        sender_email=sender_email,
        subject=subject,
        body=body,
        received_at=received_at
        or datetime(2026, 6, 18, 9, 0, 0, tzinfo=UTC),
    )
