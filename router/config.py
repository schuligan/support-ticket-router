"""Runtime configuration and path resolution.

Secrets come from the environment only. When ``ANTHROPIC_API_KEY`` is absent the
whole system degrades to a deterministic mock mode so tests and the demo run
offline with zero secrets.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Default model — Anthropic's current flagship. Overridable via MODEL_ID.
DEFAULT_MODEL_ID = "claude-opus-4-8"

# Confidence threshold above which the agent auto-resolves instead of handing
# off to a human. Tuned conservatively: we would rather hand off a resolvable
# ticket than auto-send a wrong answer. A score of ~0.6 means a solid majority
# of an article's keywords appear in the message.
AUTO_RESOLVE_THRESHOLD = 0.6

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PACKAGE_DIR.parent
SAMPLE_DATA_DIR = PROJECT_DIR / "sample_data"


@dataclass(frozen=True)
class Config:
    """Resolved runtime configuration."""

    api_key: str | None
    model_id: str
    store_path: Path
    audit_path: Path
    kb_path: Path
    auto_resolve_threshold: float

    @property
    def mock_mode(self) -> bool:
        return not self.api_key


def load_config(data_dir: Path | None = None) -> Config:
    """Build a :class:`Config` from the environment.

    ``data_dir`` overrides where the ticket store and audit log live (used by
    tests to isolate state in a temp directory).
    """
    base = data_dir if data_dir is not None else PROJECT_DIR / "data"
    base.mkdir(parents=True, exist_ok=True)
    return Config(
        api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
        model_id=os.environ.get("MODEL_ID", DEFAULT_MODEL_ID),
        store_path=base / "tickets.json",
        audit_path=base / "audit.log",
        kb_path=SAMPLE_DATA_DIR / "kb_articles.json",
        auto_resolve_threshold=AUTO_RESOLVE_THRESHOLD,
    )
