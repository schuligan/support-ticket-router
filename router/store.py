"""Mock ticket store ("mock Jira") backed by a local JSON file.

Each ticket has an ID, status, and an SLA timer. The store is the durable state
across CLI invocations.
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import Ticket


class TicketStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._tickets: dict[str, Ticket] = {}
        self._counter = 0
        self._load()

    # -- persistence ---------------------------------------------------------

    def _load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        self._counter = data.get("counter", 0)
        for d in data.get("tickets", []):
            ticket = Ticket.from_dict(d)
            self._tickets[ticket.id] = ticket

    def _save(self) -> None:
        data = {
            "counter": self._counter,
            "tickets": [t.to_dict() for t in self._tickets.values()],
        }
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
        tmp.replace(self.path)

    # -- mutations -----------------------------------------------------------

    def next_id(self) -> str:
        self._counter += 1
        return f"TCK-{self._counter:04d}"

    def add(self, ticket: Ticket) -> None:
        self._tickets[ticket.id] = ticket
        self._save()

    def update(self, ticket: Ticket) -> None:
        self._tickets[ticket.id] = ticket
        self._save()

    # -- queries -------------------------------------------------------------

    def get(self, ticket_id: str) -> Ticket | None:
        return self._tickets.get(ticket_id)

    def all(self) -> list[Ticket]:
        return sorted(self._tickets.values(), key=lambda t: t.created_at)

    def has_message(self, message_id: str) -> bool:
        return any(t.message_id == message_id for t in self._tickets.values())
