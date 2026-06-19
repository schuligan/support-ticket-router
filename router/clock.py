"""Injectable clock so SLA timing is deterministic in tests.

Production code uses ``SystemClock``; tests use ``FixedClock`` to advance time
explicitly instead of relying on wall-clock.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    """Minimal time source."""

    def now(self) -> datetime: ...


class SystemClock:
    """Wall-clock UTC time."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class FixedClock:
    """A controllable clock for deterministic tests."""

    def __init__(self, start: datetime) -> None:
        if start.tzinfo is None:
            start = start.replace(tzinfo=UTC)
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance(self, **kwargs: float) -> None:
        """Advance the clock, e.g. ``clock.advance(minutes=90)``."""
        self._now = self._now + timedelta(**kwargs)

    def set(self, when: datetime) -> None:
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        self._now = when
