"""Ingest inbound messages from mock email + Slack JSON fixtures.

Validates each raw record at the boundary with pydantic, then normalizes it to
an :class:`~router.models.InboundMessage`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError, field_validator

from .models import Channel, InboundMessage


class _RawMessage(BaseModel):
    """Validation schema for an inbound fixture record."""

    id: str
    channel: Channel
    sender_name: str
    sender_email: str
    subject: str
    body: str
    received_at: datetime

    @field_validator("body")
    @classmethod
    def _non_empty_body(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("message body must not be empty")
        return v


def _load_raw(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON array of messages")
    return data


def ingest_files(paths: list[Path]) -> list[InboundMessage]:
    """Load and validate messages from one or more fixture files.

    Invalid records raise immediately with a clear, sourced error rather than
    being silently dropped.
    """
    messages: list[InboundMessage] = []
    for path in paths:
        for idx, raw in enumerate(_load_raw(path)):
            try:
                rec = _RawMessage.model_validate(raw)
            except ValidationError as exc:  # fail fast at the boundary
                raise ValueError(
                    f"invalid message at {path.name}[{idx}]: {exc.errors()}"
                ) from exc
            received = rec.received_at
            if received.tzinfo is None:
                received = received.replace(tzinfo=UTC)
            messages.append(
                InboundMessage(
                    id=rec.id,
                    channel=rec.channel,
                    sender_name=rec.sender_name,
                    sender_email=rec.sender_email,
                    subject=rec.subject,
                    body=rec.body,
                    received_at=received,
                )
            )
    messages.sort(key=lambda m: m.received_at)
    return messages
