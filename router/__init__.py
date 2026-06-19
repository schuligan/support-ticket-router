"""support-ticket-router — agentic support automation.

Ingest inbound messages, auto-triage them, open tickets in a mock store,
attempt KB-grounded auto-resolution, and escalate tickets that breach SLA.

Runs fully offline in a deterministic MOCK mode when no ANTHROPIC_API_KEY is
present; uses the real Claude API when a key is available.
"""

__version__ = "0.1.0"
