"""Thin Claude wrapper with a deterministic mock fallback.

When ``ANTHROPIC_API_KEY`` is present, ``call_json`` issues a real structured
request to the Messages API. When it is absent, callers should instead use the
deterministic heuristics in :mod:`router.triage` and :mod:`router.resolve`,
which print the MOCK-mode banner. This module isolates the only place that
imports the ``anthropic`` SDK, so the rest of the system stays import-clean
offline.
"""

from __future__ import annotations

import json
from typing import Any

MOCK_BANNER = "[MOCK MODE — set ANTHROPIC_API_KEY for real LLM]"


class LLMUnavailable(RuntimeError):
    """Raised when a real LLM call is requested but cannot be made."""


def call_json(
    *,
    api_key: str,
    model_id: str,
    system: str,
    user_content: str,
    schema: dict[str, Any],
) -> dict[str, Any]:
    """Call Claude and return a schema-validated JSON object.

    Uses adaptive thinking and structured outputs (``output_config.format``).
    Imports the SDK lazily so the package imports cleanly without it installed.
    """
    try:
        import anthropic
    except ImportError as exc:  # pragma: no cover - exercised only with key set
        raise LLMUnavailable(
            "the 'anthropic' package is not installed; "
            "install it or run without ANTHROPIC_API_KEY for mock mode"
        ) from exc

    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model=model_id,
        max_tokens=1024,
        thinking={"type": "adaptive"},
        system=system,
        messages=[{"role": "user", "content": user_content}],
        output_config={"format": {"type": "json_schema", "schema": schema}},
    )
    text = next(
        (block.text for block in response.content if block.type == "text"), None
    )
    if text is None:  # pragma: no cover - defensive
        raise LLMUnavailable("no text block in Claude response")
    return json.loads(text)
