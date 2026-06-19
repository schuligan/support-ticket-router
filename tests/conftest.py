"""Shared fixtures. Force mock mode and isolate state in a temp dir."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from router.audit import AuditLog
from router.clock import FixedClock
from router.config import load_config
from router.kb import load_kb
from router.store import TicketStore


@pytest.fixture(autouse=True)
def _no_api_key(monkeypatch):
    """Guarantee mock mode + no network for every test."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.fixture
def config(tmp_path: Path):
    return load_config(tmp_path)


@pytest.fixture
def store(config):
    return TicketStore(config.store_path)


@pytest.fixture
def audit(config):
    return AuditLog(config.audit_path)


@pytest.fixture
def articles(config):
    return load_kb(config.kb_path)


@pytest.fixture
def clock():
    return FixedClock(datetime(2026, 6, 18, 9, 0, 0, tzinfo=UTC))
