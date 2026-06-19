# Implementation Plan — support-ticket-router

## Goals

Build a small, correct, fully-runnable agentic support pipeline that demonstrates:

1. **Multi-channel ingest** of synthetic email + Slack messages with validation.
2. **Auto-triage** — classify category, priority, intent; extract structured fields.
3. **Ticketing** in a mock store with IDs, status, and SLA timers.
4. **Confidence-gated auto-resolution** against a knowledge base, with an honest human-handoff fallback.
5. **SLA escalation** with a clear, documented policy.
6. **Offline-first operation** — full functionality and a passing test suite with no API key and no network, plus a real Claude path when a key is present.

Non-goals: real connectors, a real ticketing backend, embedding-based retrieval, sending replies automatically.

---

## Triage design

Triage produces a `Triage` record: `category`, `priority`, `intent`, `customer`, `product_area`, `summary`, `confidence`, `source`.

- **LLM path** — a single `messages.create` call with adaptive thinking and a JSON-schema `output_config.format` that pins the exact output shape. The system prompt frames the agent as an Acme Cloud triage assistant and defines the priority rubric (outage/data-loss → urgent; blocked workflow → high; routine → normal; nice-to-have → low).
- **MOCK path** — deterministic keyword tables produce the same shape. Category is matched first (outage/billing/bug/feature/account/how-to), then priority is derived from category + hint words. "urgent" is matched as a whole word so "not urgent" can't flip a feature request to urgent; low/feature intent is resolved before urgent so a stray substring can't override an explicit nice-to-have.

The LLM path wraps the call in a try/except that falls back to the mock on any failure, so a transient API error degrades to deterministic behavior rather than crashing the pipeline.

---

## KB auto-resolution + confidence gating

The KB is a small JSON set of articles, each with `keywords`, a `category`, and a `body`.

- **Scoring (mock + candidate seeding)** — `score_article` = fraction of an article's keywords present in the normalized message text; `best_match` returns the top article and its score.
- **Gating** — auto-resolve only when the best score (mock) or the model's confidence (LLM) is `>= AUTO_RESOLVE_THRESHOLD` (0.6). The LLM path additionally requires the model to assert `answers_question == true`, and the drafted reply must be grounded only in the chosen article.
- **Handoff** — below threshold (or `answers_question == false`), the ticket becomes `awaiting_human` with an explicit, logged reason that includes the score/threshold. The design bias: prefer an honest handoff over a confident-but-wrong auto-reply.

Threshold rationale: with the synthetic KB, a score of ~0.6 means a solid majority of an article's keywords appear — strong enough to trust an auto-reply, while genuinely unrelated questions (outage, dark-mode request) score 0 and are handed off.

---

## Ticket / SLA model

`Ticket` carries `id` (`TCK-NNNN`), `status` (`open` / `resolved` / `awaiting_human` / `escalated`), `priority`, `created_at`, `sla_due_at`, optional `resolved_at` / `escalated_at`, the KB match, the drafted reply, the handoff reason, and a `history` trail.

- `sla_due_at = created_at + SLA_MINUTES[priority]`.
- `is_breached(now)` is true when a non-resolved, non-escalated ticket is at/past its due time.
- The store is a single JSON file written atomically (temp file + rename), with a monotonic counter for IDs and a `has_message` check for idempotent reprocessing.

**Injectable clock.** All time comes from a `Clock` protocol. Production uses `SystemClock`; tests use `FixedClock`, which can `advance(...)` deterministically. No test relies on wall-clock, so SLA logic is reproducible.

---

## Escalation policy

| Priority | SLA window |
|----------|-----------|
| urgent   | 60 min    |
| high     | 4 h       |
| normal   | 24 h      |
| low      | 72 h      |

`escalate(store, audit, now)` finds breached tickets, flips them to `escalated`, records the overdue minutes in history, and writes an audit entry. Idempotent: already-escalated and resolved tickets are skipped. In a real deployment this runs on a schedule; here it's the `escalations` CLI command.

---

## Audit

Every meaningful action (`ingest`, `triage`, `ticket_created`, `auto_resolved`, `handoff`, `escalate`) appends one JSON line to an append-only log. The log is the system of record and is rendered by the `audit` command.

---

## Trade-offs

- **Keyword scoring vs embeddings** — keyword overlap is deterministic, dependency-free, and good enough for a synthetic KB; it also seeds candidates for the LLM. A real system would use embeddings/RAG. Chose simplicity and testability.
- **Single JSON store vs a database** — keeps the demo zero-setup and inspectable. Atomic writes avoid partial-state corruption. Not concurrent-safe; fine for a single-process demo.
- **Mock fallback inside the LLM path** — keeps the pipeline resilient and CI-friendly, at the cost of occasionally masking an API error as a mock result. The `source` field records which path produced each result.
- **Threshold tuning** — a single global threshold is simple but coarse; per-category thresholds would be the next refinement.
- **Drafts, not sends** — the agent drafts replies and a human approves. Auto-sending is intentionally out of scope (it's the highest-risk action).

---

## Phased plan (how it was built)

1. **Models + clock** — `StrEnum`s, dataclasses, SLA math, injectable clock.
2. **Config + sample data** — env-driven config with mock-mode detection; synthetic email/Slack/KB fixtures.
3. **Ingest** — pydantic validation at the boundary, normalization, fail-fast on bad records.
4. **Triage + resolve** — LLM and mock paths behind one interface; the `llm.py` wrapper isolates the SDK import.
5. **Store + audit + escalation** — durable JSON store, append-only log, SLA pass.
6. **Pipeline + CLI** — orchestrator wiring it together; rich-rendered `router` commands.
7. **Tests** — triage, resolution gating, pipeline outcomes, escalation triggers (FixedClock), idempotency, audit, ingest validation. All offline.
