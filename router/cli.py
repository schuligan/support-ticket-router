"""`router` CLI — entrypoint for the support ticket router.

Commands:
    ingest        Load + validate sample fixtures, print a normalized view.
    run           Triage + ticket + auto-resolve/handoff for all messages.
    tickets       List all tickets with status and SLA.
    ticket <id>   Show one ticket in detail (including drafted reply).
    escalations   Run the SLA escalation pass and show escalated tickets.
    audit         Print the append-only audit log.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .audit import AuditLog
from .clock import SystemClock
from .config import SAMPLE_DATA_DIR, load_config
from .escalation import escalate
from .ingest import ingest_files
from .kb import load_kb
from .models import Priority, TicketStatus
from .pipeline import process_all
from .store import TicketStore
from .triage import banner_if_mock

console = Console()

_STATUS_STYLE = {
    TicketStatus.OPEN: "yellow",
    TicketStatus.RESOLVED: "green",
    TicketStatus.AWAITING_HUMAN: "magenta",
    TicketStatus.ESCALATED: "red",
}
_PRIORITY_STYLE = {
    Priority.URGENT: "bold red",
    Priority.HIGH: "red",
    Priority.NORMAL: "yellow",
    Priority.LOW: "dim",
}

_FIXTURES = [SAMPLE_DATA_DIR / "emails.json", SAMPLE_DATA_DIR / "slack.json"]


def _print_mock_banner(config) -> None:
    banner = banner_if_mock(config)
    if banner:
        console.print(f"[dim]{banner}[/dim]")


def _build(args) -> tuple:
    data_dir = Path(args.data_dir) if args.data_dir else None
    config = load_config(data_dir)
    store = TicketStore(config.store_path)
    audit = AuditLog(config.audit_path)
    return config, store, audit


# --- commands ---------------------------------------------------------------


def cmd_ingest(args) -> int:
    config, _, audit = _build(args)
    _print_mock_banner(config)
    messages = ingest_files(_FIXTURES)
    audit.record("ingest", SystemClock().now(), count=len(messages))

    table = Table(title=f"Ingested {len(messages)} messages")
    table.add_column("ID")
    table.add_column("Channel")
    table.add_column("From")
    table.add_column("Subject", overflow="fold")
    for m in messages:
        table.add_row(m.id, m.channel.value, m.sender_email, m.subject)
    console.print(table)
    return 0


def cmd_run(args) -> int:
    config, store, audit = _build(args)
    _print_mock_banner(config)
    messages = ingest_files(_FIXTURES)
    articles = load_kb(config.kb_path)
    results = process_all(
        messages,
        store=store,
        audit=audit,
        articles=articles,
        config=config,
        clock=SystemClock(),
    )

    table = Table(title="Pipeline results")
    table.add_column("Ticket")
    table.add_column("Priority")
    table.add_column("Category")
    table.add_column("Outcome")
    table.add_column("Conf")
    table.add_column("Summary", overflow="fold")
    for r in results:
        outcome = (
            "[green]auto-resolved[/green]"
            if r.resolution.resolved
            else "[magenta]handoff[/magenta]"
        )
        if r.skipped:
            outcome = "[dim]skipped (exists)[/dim]"
        pstyle = _PRIORITY_STYLE.get(r.ticket.priority, "")
        table.add_row(
            r.ticket.id,
            f"[{pstyle}]{r.ticket.priority.value}[/{pstyle}]",
            r.ticket.category.value,
            outcome,
            f"{r.resolution.confidence:.2f}",
            r.triage.summary,
        )
    console.print(table)

    resolved = sum(1 for r in results if r.resolution.resolved and not r.skipped)
    handed = sum(
        1 for r in results if not r.resolution.resolved and not r.skipped
    )
    console.print(
        f"\n[green]{resolved} auto-resolved[/green], "
        f"[magenta]{handed} handed off to a human[/magenta]."
    )
    return 0


def cmd_tickets(args) -> int:
    config, store, _ = _build(args)
    _print_mock_banner(config)
    tickets = store.all()
    if not tickets:
        console.print("[dim]No tickets yet. Run `router run` first.[/dim]")
        return 0

    table = Table(title=f"{len(tickets)} tickets")
    table.add_column("ID")
    table.add_column("Status")
    table.add_column("Priority")
    table.add_column("Customer")
    table.add_column("SLA due (UTC)")
    table.add_column("Summary", overflow="fold")
    for t in tickets:
        sstyle = _STATUS_STYLE.get(t.status, "")
        pstyle = _PRIORITY_STYLE.get(t.priority, "")
        table.add_row(
            t.id,
            f"[{sstyle}]{t.status.value}[/{sstyle}]",
            f"[{pstyle}]{t.priority.value}[/{pstyle}]",
            t.customer,
            t.sla_due_at.strftime("%Y-%m-%d %H:%M"),
            t.summary,
        )
    console.print(table)
    return 0


def cmd_ticket(args) -> int:
    config, store, _ = _build(args)
    _print_mock_banner(config)
    ticket = store.get(args.ticket_id)
    if ticket is None:
        console.print(f"[red]No ticket {args.ticket_id}[/red]")
        return 1

    lines = [
        f"[bold]{ticket.id}[/bold]  ({ticket.status.value})",
        f"Customer : {ticket.customer} <{ticket.sender_email}>",
        f"Channel  : {ticket.channel.value}",
        f"Priority : {ticket.priority.value}   Category: {ticket.category.value}",
        f"Created  : {ticket.created_at.isoformat()}",
        f"SLA due  : {ticket.sla_due_at.isoformat()}",
        f"Summary  : {ticket.summary}",
    ]
    if ticket.kb_article_id:
        lines.append(f"KB match : {ticket.kb_article_id}")
    if ticket.handoff_reason:
        lines.append(f"Handoff  : {ticket.handoff_reason}")
    console.print(Panel("\n".join(lines), title=f"Ticket {ticket.id}"))

    if ticket.draft_reply:
        console.print(Panel(ticket.draft_reply, title="Drafted reply"))
    return 0


def cmd_escalations(args) -> int:
    config, store, audit = _build(args)
    _print_mock_banner(config)
    changed = escalate(store, audit, SystemClock().now())

    escalated = [t for t in store.all() if t.status == TicketStatus.ESCALATED]
    table = Table(title=f"{len(escalated)} escalated tickets")
    table.add_column("ID")
    table.add_column("Priority")
    table.add_column("Overdue")
    table.add_column("Summary", overflow="fold")
    now = SystemClock().now()
    for t in escalated:
        overdue_min = int((now - t.sla_due_at).total_seconds() // 60)
        table.add_row(
            t.id,
            t.priority.value,
            f"{max(overdue_min, 0)}m",
            t.summary,
        )
    console.print(table)
    if changed:
        console.print(
            f"[red]Escalated {len(changed)} newly-breached ticket(s).[/red]"
        )
    else:
        console.print("[dim]No new SLA breaches this pass.[/dim]")
    return 0


def cmd_audit(args) -> int:
    config, _, audit = _build(args)
    _print_mock_banner(config)
    entries = audit.read_all()
    if not entries:
        console.print("[dim]Audit log is empty.[/dim]")
        return 0
    table = Table(title=f"Audit log ({len(entries)} entries)")
    table.add_column("Timestamp")
    table.add_column("Action")
    table.add_column("Details", overflow="fold")
    for e in entries:
        details = ", ".join(
            f"{k}={v}" for k, v in e.items() if k not in ("ts", "action")
        )
        table.add_row(e["ts"], e["action"], details)
    console.print(table)
    return 0


# --- arg parsing ------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="router",
        description="Agentic support ticket router (Acme Cloud demo).",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Directory for ticket store + audit log (default: ./data).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("ingest", help="Load and validate sample fixtures.")
    sub.add_parser("run", help="Triage, ticket, and auto-resolve/handoff.")
    sub.add_parser("tickets", help="List all tickets.")
    p_ticket = sub.add_parser("ticket", help="Show one ticket by id.")
    p_ticket.add_argument("ticket_id", help="Ticket id, e.g. TCK-0001.")
    sub.add_parser("escalations", help="Run SLA escalation pass.")
    sub.add_parser("audit", help="Print the audit log.")
    return parser


_DISPATCH = {
    "ingest": cmd_ingest,
    "run": cmd_run,
    "tickets": cmd_tickets,
    "ticket": cmd_ticket,
    "escalations": cmd_escalations,
    "audit": cmd_audit,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return _DISPATCH[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
