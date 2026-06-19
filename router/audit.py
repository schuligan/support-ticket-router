"""Append-only audit log.

Every meaningful action (ingest, triage, ticket creation, resolution, handoff,
escalation) appends one JSON line. The log is the system of record for "what
happened and when".
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, action: str, when: datetime, **fields: Any) -> dict[str, Any]:
        entry = {"ts": when.isoformat(), "action": action, **fields}
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        entries: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries
