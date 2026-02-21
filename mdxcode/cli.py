"""MDx Code CLI — The AI Engineering Manager."""

import asyncio
import json
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from . import __version__
from .config import MDX_DIR, load_config

# All other imports (backends, router, review, governance) are lazy —
# imported inside the functions that use them for fast startup.

LAST_TASK_PATH = MDX_DIR / "last_task.json"

console = Console()


class TaskGroup(typer.core.TyperGroup):
    """Custom Click Group that treats unknown commands as task strings."""

    def resolve_command(self, ctx, args):
        """Override to catch unknown commands and treat them as tasks."""
        try:
            return super().resolve_command(ctx, args)
        except click.UsageError:
            # Unknown command — treat the entire args list as a task string
            return "run", args

    def parse_args(self, ctx, args):
        """Ensure unknown args don't cause errors."""
        # If the first arg looks like a task (not a known command, not a flag),
        # wrap it so Click doesn't reject it
        if args and not args[0].startswith("-") and args[0] not in self.commands:
            # Inject "run" as the subcommand, pass everything else as args
            args = ["run"] + args
        return super().parse_args(ctx, args)


app = typer.Typer(
    name="mdx",
    help="MDx Code — The AI Engineering Manager",
    add_completion=False,
    invoke_without_command=True,
    cls=TaskGroup,
)

policy_app = typer.Typer(help="Policy management commands")
app.add_typer(policy_app, name="policy")

hook_app = typer.Typer(help="Git hook management commands")
app.add_typer(hook_app, name="hook")

mcp_app = typer.Typer(help="MCP server management commands")
app.add_typer(mcp_app, name="mcp")


def show_banner(backends: Optional[list] = None) -> None:
    """Display the MDx Code banner."""
    console.print()
    console.print(f"  [bold]MDx Code[/bold] v{__version__}")
    console.print("  [dim]The AI Engineering Manager[/dim]")

    if backends:
        ready = sum(1 for b in backends if b.healthy)
        parts: list[str] = []
        for b in backends:
            mark = "[green]\u2713[/green]" if b.healthy else "[red]\u2717[/red]"
            parts.append(f"{b.name.title()} {mark}")
        console.print()
        console.print(f"  {ready} backend{'s' if ready != 1 else ''} ready: {'  '.join(parts)}")

    console.print()


def _show_routing_line(
    backend_name: str,
    reason: str,
    user_specified: bool = False,
    scores: dict[str, float] | None = None,
    num_backends: int = 0,
) -> None:
    """Show a one-line routing decision with optional score context."""
    from .output.colors import colored_backend

    if user_specified:
        console.print(f"  [dim]\u2192 Using {colored_backend(backend_name)} (user specified)[/dim]")
    else:
        console.print(f"  [dim]\u2192 Routing to {colored_backend(backend_name)} \u2014 {reason}[/dim]")
        # Show score comparison on second dim line
        if scores and len(scores) > 1:
            parts = []
            for name, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
                marker = "\u25cf" if name == backend_name else "\u25cb"
                parts.append(f"{marker} {name.title()} {score:.2f}")
            score_line = "  ".join(parts)
            console.print(f"    [dim]{score_line}[/dim]")


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-V", help="Show version"),
) -> None:
    """MDx Code — The AI Engineering Manager."""
    if version:
        console.print(f"MDx Code v{__version__}")
        raise typer.Exit()

    # If no subcommand is being invoked, show banner + interactive prompt
    if ctx.invoked_subcommand is None:
        from .backends.discovery import discover_backends

        backends = asyncio.run(discover_backends())
        show_banner(backends)

        task_input = console.input("[bold]What do you want to work on?[/bold] \u2192 ")
        if task_input.strip():
            asyncio.run(_execute_task(task_input.strip()))
        raise typer.Exit()


@app.command(hidden=True)
def run(
    ctx: typer.Context,
    task_parts: Optional[list[str]] = typer.Argument(None, help="Task to execute"),
    backend: Optional[str] = typer.Option(
        None, "--backend", "-b", help="Force a specific backend"
    ),
    strategy: Optional[str] = typer.Option(
        None, "--strategy", "-s", help="Routing strategy"
    ),
) -> None:
    """Execute a task (hidden command -- invoked automatically)."""
    if not task_parts:
        # No task provided -- show banner + interactive prompt
        from .backends.discovery import discover_backends

        backends = asyncio.run(discover_backends())
        show_banner(backends)

        task_input = console.input("[bold]What do you want to work on?[/bold] \u2192 ")
        if task_input.strip():
            asyncio.run(_execute_task(task_input.strip()))
        return

    task = " ".join(task_parts)

    # Normalize strategy aliases
    strategy_map = {"cost": "cost_optimized", "quality": "quality_first"}
    resolved_strategy = strategy_map.get(strategy, strategy) if strategy else None

    asyncio.run(
        _execute_task(task, backend_override=backend, strategy_override=resolved_strategy)
    )


async def _execute_task(
    task: str,
    backend_override: Optional[str] = None,
    strategy_override: Optional[str] = None,
) -> None:
    """Execute a task via the best available backend."""
    from .backends.circuit_breaker import get_circuit_breaker
    from .backends.discovery import INSTALL_INSTRUCTIONS, discover_backends, get_best_backend
    from .governance.audit_trail import AuditEntry, write_audit_entry
    from .governance.policy_engine import evaluate_policies, load_policy_file
    from .output.footer import show_footer
    from .output.streamer import stream_output
    from .router.cost_tracker import record_cost
    from .router.engine import categorize_task
    from .router.profiles import estimate_cost, estimate_tokens_from_chars, get_profiles
    from .router.strategies import route_task

    config = load_config()
    session_id = str(uuid.uuid4())

    # Get available backends list
    all_backends = await discover_backends()
    backends_available = [b.name for b in all_backends if b.healthy]

    # Categorize the task
    category = categorize_task(task)

    # Determine routing strategy
    strategy = strategy_override or config.routing_strategy

    # Determine which backend to use
    user_specified = backend_override is not None
    routing_reason = ""
    routing_decision = None

    if user_specified:
        # User explicitly chose — bypass smart routing
        backend, selection_reason = await get_best_backend(backend_override)
        routing_reason = "user specified"
    else:
        # Smart routing: use categorization + strategy
        profiles = get_profiles()
        cb = get_circuit_breaker()

        # Filter to backends that are available and not circuit-broken
        routable_backends = [
            name for name in backends_available
            if name != "opencode" and cb.is_available(name)
        ]

        routing_decision = route_task(category, routable_backends, profiles, strategy)

        if routing_decision:
            # Get the actual backend instance
            backend, selection_reason = await get_best_backend(routing_decision.backend_name)
            routing_reason = routing_decision.reason
            selection_reason = f"smart_routed ({strategy})"
        else:
            # Fallback to discovery order
            backend, selection_reason = await get_best_backend(config.default_backend)
            routing_reason = "auto-selected (no routing match)"

    if backend is None:
        if backend_override:
            install_hint = INSTALL_INSTRUCTIONS.get(backend_override, "")
            if backend_override == "opencode":
                console.print(
                    "[red]OpenCode does not support non-interactive execution.[/red]"
                )
                console.print("Use --backend claude, --backend codex, or --backend gemini.")
            else:
                console.print(
                    f"[red]Backend '{backend_override}' is not available.[/red] {install_hint}"
                )
        else:
            console.print(
                "[red]No backend available.[/red] Install Claude Code, Codex CLI, or Gemini CLI."
            )
        console.print("Run [bold]mdx setup[/bold] to check backend status.")
        raise typer.Exit(1)

    # Show routing decision
    if config.display.show_routing_reason:
        _show_routing_line(
            backend.name,
            routing_reason,
            user_specified=user_specified,
            scores=routing_decision.scores if routing_decision else None,
            num_backends=len(backends_available),
        )

    cwd = Path.cwd()
    cb = get_circuit_breaker()

    # Stream output from backend
    full_output, duration = await stream_output(backend.execute(task, cwd))

    # Determine success/failure for circuit breaker
    if "[MDx Code] Backend error" in full_output or "[MDx Code] Task timed out" in full_output:
        cb.record_failure(backend.name)
        exit_code = 1
        status_val = "error"
    else:
        cb.record_success(backend.name)
        exit_code = 0
        status_val = "success"

    # Parse output for metadata
    model, cost, tokens_in, tokens_out = None, None, None, None
    if hasattr(backend, "_parse_json_output"):
        model, cost, tokens_in, tokens_out = backend._parse_json_output(full_output)
    elif hasattr(backend, "_parse_output"):
        model, cost, tokens_in, tokens_out = backend._parse_output(full_output)

    # Estimate cost if not provided by backend
    cost_estimated = False
    if cost is None and full_output:
        profiles = get_profiles()
        if tokens_in is None or tokens_out is None:
            char_count = len(full_output) + len(task)
            est_tokens = estimate_tokens_from_chars(char_count)
            tokens_in = tokens_in or len(task) // 4 or 1
            tokens_out = tokens_out or est_tokens
        cost = estimate_cost(backend.name, tokens_in, tokens_out, profiles)
        cost_estimated = True

    # Calculate alternative costs
    alternative_costs: dict[str, float] = {}
    if tokens_in is not None and tokens_out is not None:
        profiles = get_profiles()
        for alt_name in backends_available:
            if alt_name == backend.name or alt_name == "opencode":
                continue
            alt_cost = estimate_cost(alt_name, tokens_in, tokens_out, profiles)
            if alt_cost > 0:
                alternative_costs[alt_name] = alt_cost

    # Calculate savings
    savings = 0.0
    savings_vs = ""
    if alternative_costs and cost is not None:
        max_alt_name = max(alternative_costs, key=alternative_costs.get)  # type: ignore[arg-type]
        max_alt_cost = alternative_costs[max_alt_name]
        if max_alt_cost > cost:
            savings = round(max_alt_cost - cost, 4)
            savings_vs = max_alt_name

    # Record cost in SQLite
    try:
        record_cost(
            session_id=session_id,
            backend=backend.name,
            model=model,
            task_category=category.category,
            task_summary=task,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost,
            estimated=cost_estimated,
            routing_strategy=strategy,
            alternative_costs=alternative_costs,
        )
    except Exception:
        pass  # Cost tracking should never block the user

    # Write audit entry
    if config.audit.enabled:
        entry = AuditEntry(
            session_id=session_id,
            task=task,
            backend=backend.name,
            model=model,
            working_directory=str(cwd),
            duration_seconds=duration,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost,
            exit_code=exit_code,
            status=status_val,
            backend_selection_reason=selection_reason,
            backends_available=backends_available,
            routing_strategy=strategy,
            routing_reason=routing_reason,
            task_category=category.category,
            cost_estimated=cost_estimated,
            alternative_costs=alternative_costs,
        )
        write_audit_entry(entry)

    # Save last task info for `mdx review --last`
    _save_last_task(task, backend.name, cwd, full_output)

    # Check if there were file changes (for footer display)
    last_task_data = _load_last_task()
    has_file_changes = bool(last_task_data and last_task_data.get("files_modified"))

    # Check if there were file changes (for footer display)
    last_task_data = _load_last_task()
    has_file_changes = bool(last_task_data and last_task_data.get("files_modified"))

    # Policy enforcement (warn only, never block)
    try:
        policy_file = load_policy_file()
        if policy_file:
            modified = last_task_data.get("files_modified", []) if last_task_data else []
            if modified:
                policy_result = evaluate_policies(policy_file, modified)
                if policy_result.matching_policies:
                    policy_eval = {
                        "matching_policies": policy_result.matching_policies,
                        "requires_review": policy_result.requires_review,
                        "requires_approval": policy_result.requires_approval,
                        "min_reviewers": policy_result.min_reviewers,
                    }
                    if policy_result.requires_review:
                        policies_str = ", ".join(policy_result.matching_policies)
                        console.print(
                            f"  [yellow]Policy [{policies_str}]: adversarial review recommended[/yellow]"
                        )
                        console.print("  [dim]Run: mdx review --last[/dim]")
                    if policy_result.requires_approval:
                        console.print(
                            "  [yellow]Policy requires human approval for these files.[/yellow]"
                        )
                        approve = console.input("  Approve? [y/N] ").strip().lower()
                        if approve != "y":
                            console.print("  [dim]Approval deferred.[/dim]")
                    # Update audit entry with policy evaluation
                    if config.audit.enabled:
                        policy_entry = AuditEntry(
                            session_id=session_id,
                            task=f"policy_check: {task}",
                            backend=backend.name,
                            working_directory=str(cwd),
                            files_modified=modified,
                            status="success",
                            policy_evaluation=policy_eval,
                        )
                        write_audit_entry(policy_entry)
    except Exception:
        pass  # Policy enforcement should never block the user

    # Show footer
    if config.display.show_footer:
        show_footer(
            backend_name=backend.name,
            model=model,
            duration=duration,
            session_id=session_id,
            cost_usd=cost,
            cost_estimated=cost_estimated,
            savings=savings,
            savings_vs=savings_vs,
            selection_reason=selection_reason,
            has_file_changes=has_file_changes,
            alternative_costs=alternative_costs,
        )


@app.command()
def setup() -> None:
    """Detect and display available backends."""
    from .backends.discovery import KNOWN_CLIS, discover_backends

    backends = asyncio.run(discover_backends())

    console.print()
    console.print(f"  [bold]MDx Code[/bold] v{__version__}")
    console.print("  [dim]The AI Engineering Manager[/dim]")
    console.print()

    console.print("  [bold]Backends:[/bold]")

    for b in backends:
        if b.healthy:
            icon = "  [green]\u2705[/green]"
            auth_str = "authenticated" if b.authenticated else ""
            console.print(f"  {icon} {KNOWN_CLIS.get(b.name, b.name.title()):<16} {b.version:<14} {auth_str}")
        elif b.version != "not installed" and b.name == "opencode":
            console.print(
                f"  [yellow]\u26a0\ufe0f[/yellow]  {KNOWN_CLIS.get(b.name, b.name.title()):<16} {b.version:<14} "
                "detected (limited support)"
            )
        elif b.version != "not installed":
            console.print(
                f"  [yellow]\u26a0\ufe0f[/yellow]  {KNOWN_CLIS.get(b.name, b.name.title()):<16} {b.version:<14} "
                "not authenticated"
            )
        else:
            console.print(
                f"  [red]\u274c[/red] {KNOWN_CLIS.get(b.name, b.name.title()):<16} not installed"
            )

    config = load_config()
    console.print()
    console.print(f"  Default backend: {config.default_backend} (auto-detected)")
    console.print(f"  Routing strategy: {config.routing_strategy}")

    ready = sum(1 for b in backends if b.healthy)
    console.print()
    console.print(f"  {ready} backend{'s' if ready != 1 else ''} ready. You can:")
    console.print("    mdx \"task\"                        \u2192 smart-route to best backend")
    console.print("    mdx \"task\" --backend codex       \u2192 force specific backend")
    console.print("    mdx \"task\" --strategy cost        \u2192 cost-optimized routing")
    console.print("    mdx cost                           \u2192 spending dashboard")
    console.print()


@app.command()
def status() -> None:
    """Show backend health and circuit breaker status."""
    from .backends.circuit_breaker import get_circuit_breaker
    from .backends.discovery import BACKEND_CLASSES, KNOWN_CLIS, discover_backends

    backends = asyncio.run(discover_backends())
    health_results = asyncio.run(_run_health_checks())

    console.print()
    console.print("  [bold]Backend Health:[/bold]")

    cb = get_circuit_breaker()

    for name, hs in health_results.items():
        display_name = KNOWN_CLIS.get(name, name.title())

        if cb.is_open(name):
            failures = cb.get_failure_count(name)
            retry_in = cb.time_until_retry(name)
            minutes = int(retry_in // 60)
            seconds = int(retry_in % 60)
            console.print(
                f"    {display_name:<12} [red]circuit open[/red]   "
                f"({failures} failures, retry in {minutes}m {seconds:02d}s)"
            )
        elif hs.healthy:
            console.print(
                f"    {display_name:<12} [green]healthy[/green]       ({hs.latency_ms}ms)"
            )
        elif hs.details == "not installed":
            console.print(f"    {display_name:<12} [dim]not installed[/dim]")
        else:
            console.print(
                f"    {display_name:<12} [yellow]{hs.details}[/yellow]"
            )

    console.print()


async def _run_health_checks() -> dict:
    """Run health checks on all backends."""
    from .backends.discovery import BACKEND_CLASSES

    results = {}
    for backend_cls in BACKEND_CLASSES:
        backend = backend_cls()
        hs = await backend.health_check()
        results[backend.name] = hs
    return results


@app.command()
def cost(
    week: bool = typer.Option(False, "--week", "-w", help="Show this week's costs"),
    month: bool = typer.Option(False, "--month", "-m", help="Show this month's costs"),
    since: Optional[str] = typer.Option(None, "--since", help="Custom start date (YYYY-MM-DD)"),
) -> None:
    """Show spending dashboard."""
    from .router.cost_tracker import (
        get_cost_by_backend,
        get_date_range_for_period,
        get_savings,
        get_top_tasks,
        get_total_cost,
    )

    # Determine date range
    if since:
        try:
            since_dt = datetime.strptime(since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            console.print("[red]Invalid date format. Use YYYY-MM-DD.[/red]")
            raise typer.Exit(1)
        until_dt = datetime.now(timezone.utc)
        period_label = f"Since {since}"
    elif month:
        since_dt, until_dt = get_date_range_for_period("month")
        period_label = "This Month"
    elif week:
        since_dt, until_dt = get_date_range_for_period("week")
        period_label = "This Week"
    else:
        since_dt, until_dt = get_date_range_for_period("today")
        period_label = "Today"

    total = get_total_cost(since=since_dt, until=until_dt)
    by_backend = get_cost_by_backend(since=since_dt, until=until_dt)
    savings_val = get_savings(since=since_dt, until=until_dt)
    top = get_top_tasks(since=since_dt, until=until_dt, limit=5)

    # Build display
    lines: list[str] = []
    lines.append("")
    lines.append(f"  Total: [bold]${total:.2f}[/bold]")
    lines.append("")

    if by_backend:
        from .output.colors import colored_backend

        lines.append("  By backend:")
        for name, amount in sorted(by_backend.items(), key=lambda x: x[1], reverse=True):
            pct = (amount / total * 100) if total > 0 else 0
            lines.append(
                f"    {colored_backend(name):<22} ${amount:>8.4f} ({pct:>4.0f}%)"
            )
        lines.append("")

    if savings_val > 0:
        lines.append(
            f"  Smart routing saved: [green]${savings_val:.2f}[/green] {period_label.lower()}"
        )
        lines.append("  [dim](vs. using most expensive option every time)[/dim]")
        lines.append("")

    if top:
        lines.append("  Top tasks:")
        for entry in top:
            summary = entry.get("task_summary", "?")
            if len(summary) > 35:
                summary = summary[:32] + "..."
            c = entry.get("cost_usd", 0) or 0
            lines.append(f"    {summary:<38} ${c:.4f}")
        lines.append("")

    if not by_backend and not top:
        lines.append("  [dim]No cost data for this period.[/dim]")
        lines.append("  [dim]Run tasks with mdx to start tracking costs.[/dim]")
        lines.append("")

    content = "\n".join(lines)
    panel = Panel(
        content,
        title=f"Cost Report ({period_label})",
        border_style="blue",
        width=min(console.width, 56),
    )
    console.print(panel)


@app.command()
def audit(
    count: int = typer.Option(10, "--count", "-n", help="Number of entries to show"),
    path: Optional[str] = typer.Option(None, "--path", help="Filter by working directory path"),
    since: Optional[str] = typer.Option(None, "--since", help="Filter entries since date (YYYY-MM-DD)"),
    entry_type: Optional[str] = typer.Option(None, "--type", help="Filter by type (e.g., adversarial_review)"),
    backend_filter: Optional[str] = typer.Option(None, "--backend", help="Filter by backend name"),
    verify: bool = typer.Option(False, "--verify", help="Verify chain hash integrity"),
    export: Optional[str] = typer.Option(None, "--export", help="Export format: csv or json"),
    stats: bool = typer.Option(False, "--stats", help="Show audit statistics"),
) -> None:
    """Show recent audit entries with filtering, export, and verification."""
    from .governance.audit_trail import (
        compute_audit_stats,
        export_entries_csv,
        read_filtered_entries,
        read_recent_entries,
        verify_audit_integrity,
    )

    config = load_config()
    audit_dir = Path(config.audit.directory).expanduser()

    # --verify mode: check integrity of all JSONL files
    if verify:
        if not audit_dir.exists():
            console.print("[dim]No audit directory found.[/dim]")
            return
        jsonl_files = sorted(audit_dir.glob("*.jsonl"))
        if not jsonl_files:
            console.print("[dim]No audit files found.[/dim]")
            return
        console.print()
        console.print("  [bold]Audit Integrity Verification[/bold]")
        console.print()
        all_valid = True
        for filepath in jsonl_files:
            valid, error = verify_audit_integrity(filepath)
            if valid:
                console.print(f"  [green]\u2713[/green] {filepath.name}")
            else:
                console.print(f"  [red]\u2717[/red] {filepath.name}: {error}")
                all_valid = False
        console.print()
        if all_valid:
            console.print("  [green]All audit files verified successfully.[/green]")
        else:
            console.print("  [red]Integrity violations detected![/red]")
        console.print()
        return

    # --stats mode: show summary statistics
    if stats:
        has_filters = any([since, entry_type, backend_filter, path])
        if has_filters:
            entries = read_filtered_entries(
                audit_dir, since=since, entry_type=entry_type,
                backend=backend_filter, path=path,
            )
        else:
            entries = read_filtered_entries(audit_dir)

        if not entries:
            console.print("[dim]No audit entries found.[/dim]")
            return

        s = compute_audit_stats(entries)
        lines: list[str] = []
        lines.append("")
        lines.append(f"  Total actions: [bold]{s['total_actions']}[/bold]")
        lines.append(f"  Tasks: {s['tasks']}    Reviews: {s['reviews']}")
        lines.append(f"  Policy checks: {s['policy_checks']}    Violations: {s['policy_violations']}")
        lines.append(f"  Total cost: [bold]${s['total_cost']:.2f}[/bold]")
        lines.append("")
        if s["by_backend"]:
            lines.append("  By backend:")
            for bname, bcount in sorted(s["by_backend"].items(), key=lambda x: x[1], reverse=True):
                lines.append(f"    {bname:<12} {bcount} actions")
            lines.append("")

        content = "\n".join(lines)
        panel = Panel(content, title="Audit Statistics", border_style="blue", width=min(console.width, 56))
        console.print(panel)
        return

    # --export mode: output CSV or JSON
    if export:
        entries = read_filtered_entries(
            audit_dir, since=since, entry_type=entry_type,
            backend=backend_filter, path=path,
        )
        if export.lower() == "csv":
            csv_text = export_entries_csv(entries)
            console.print(csv_text, end="")
        elif export.lower() == "json":
            console.print(json.dumps(entries, indent=2, default=str))
        else:
            console.print(f"[red]Unknown export format: {export}. Use 'csv' or 'json'.[/red]")
        return

    # Default: show recent entries table (with optional filters)
    has_filters = any([since, entry_type, backend_filter, path])
    if has_filters:
        entries = read_filtered_entries(
            audit_dir, since=since, entry_type=entry_type,
            backend=backend_filter, path=path,
        )
        # Limit to count
        entries = entries[-count:] if len(entries) > count else entries
    else:
        entries = read_recent_entries(count=count)

    if not entries:
        console.print("[dim]No audit entries found.[/dim]")
        console.print("Run a task with [bold]mdx \"your task\"[/bold] to generate audit entries.")
        return

    table = Table(title=f"Recent Audit Entries (last {count})", show_header=True)
    table.add_column("Time", style="dim")
    table.add_column("Backend")
    table.add_column("Task", max_width=40)
    table.add_column("Duration")
    table.add_column("Status")
    table.add_column("Cost")
    table.add_column("Reason", style="dim")

    from .output.colors import colored_backend

    for entry in entries:
        ts = entry.get("timestamp", "")[:19]
        backend_name = entry.get("backend", "?")
        task = entry.get("task", "?")
        dur = f"{entry.get('duration_seconds', 0):.1f}s"
        status_val = entry.get("status", "?")
        cost_val = entry.get("cost_usd")
        cost_str = f"${cost_val:.4f}" if cost_val else "-"
        status_style = "green" if status_val == "success" else "red"
        reason = entry.get("routing_reason") or entry.get("backend_selection_reason", "")

        table.add_row(
            ts, colored_backend(backend_name), task, dur,
            f"[{status_style}]{status_val}[/{status_style}]",
            cost_str, reason,
        )

    console.print(table)
    console.print()


def _save_last_task(task: str, backend_name: str, cwd: Path, output: str = "") -> None:
    """Save last task info for `mdx review --last` and `mdx replay`."""
    try:
        diff = ""
        files_modified: list[str] = []

        # Try multiple diff strategies — backends may or may not auto-commit
        diff_commands = [
            ["git", "diff", "HEAD"],           # Uncommitted changes
            ["git", "diff", "HEAD~1"],          # Last commit (auto-committed by backend)
            ["git", "diff", "--cached"],        # Staged changes
        ]

        for cmd in diff_commands:
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, cwd=str(cwd), timeout=10,
                )
                if result.returncode == 0 and result.stdout.strip():
                    diff = result.stdout
                    # Get file names from this same ref
                    name_cmd = cmd.copy()
                    name_cmd.insert(2, "--name-only")
                    result2 = subprocess.run(
                        name_cmd, capture_output=True, text=True, cwd=str(cwd), timeout=10,
                    )
                    files_modified = [f for f in result2.stdout.strip().splitlines() if f]
                    break
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                continue

        data = {
            "task": task,
            "backend": backend_name,
            "files_modified": files_modified,
            "diff": diff,
            "output": output,
            "working_directory": str(cwd),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        LAST_TASK_PATH.parent.mkdir(parents=True, exist_ok=True)
        LAST_TASK_PATH.write_text(json.dumps(data, indent=2))
    except Exception:
        pass  # Last task tracking should never block the user


def _load_last_task() -> Optional[dict]:
    """Load the last task info for `mdx review --last`."""
    if not LAST_TASK_PATH.exists():
        return None
    try:
        return json.loads(LAST_TASK_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None


@app.command()
def replay() -> None:
    """Replay the last task's output without re-executing."""
    from rich.markdown import Markdown

    from .output.streamer import _looks_like_markdown

    task_data = _load_last_task()
    if not task_data or not task_data.get("output"):
        console.print("[dim]No recent task output to replay.[/dim]")
        console.print("Run a task first: [bold]mdx \"your task\"[/bold]")
        raise typer.Exit(1)

    task = task_data.get("task", "unknown")
    backend = task_data.get("backend", "unknown")
    timestamp = task_data.get("timestamp", "")[:19]

    console.print()
    console.print(f"  [dim]Replaying: \"{task}\" via {backend.title()} at {timestamp}[/dim]")
    console.print()

    output = task_data["output"]
    if _looks_like_markdown(output):
        console.print(Markdown(output.strip()))
    else:
        console.print(output, end="")

    console.print()


@app.command()
def undo() -> None:
    """Undo the last change made by a backend."""
    task_data = _load_last_task()
    if not task_data:
        console.print("[dim]No recent task to undo.[/dim]")
        raise typer.Exit(1)

    task = task_data.get("task", "unknown")
    backend = task_data.get("backend", "unknown")
    files = task_data.get("files_modified", [])
    cwd = task_data.get("working_directory", str(Path.cwd()))

    if not files:
        console.print("[dim]No file changes detected in the last task.[/dim]")
        raise typer.Exit(1)

    console.print()
    console.print(f"  [bold]Undo last task:[/bold] \"{task}\" via {backend.title()}")
    console.print(f"  Files affected: {len(files)}")
    for f in files[:5]:
        console.print(f"    {f}")
    if len(files) > 5:
        console.print(f"    [dim]...and {len(files) - 5} more[/dim]")
    console.print()

    confirm = console.input("  [bold yellow]Revert these changes?[/bold yellow] [y/N] ").strip().lower()
    if confirm != "y":
        console.print("  [dim]Undo cancelled.[/dim]")
        raise typer.Exit(0)

    # Determine undo strategy
    try:
        # Check if there are uncommitted changes (backend didn't auto-commit)
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, cwd=cwd, timeout=10,
        )
        uncommitted = [f for f in result.stdout.strip().splitlines() if f]

        if uncommitted:
            # Uncommitted changes — just git checkout the files
            subprocess.run(
                ["git", "checkout", "HEAD", "--"] + files,
                capture_output=True, text=True, cwd=cwd, timeout=10,
            )
            console.print("  [green]\u2713[/green] Reverted uncommitted changes.")
        else:
            # Changes were committed — revert the last commit
            result = subprocess.run(
                ["git", "revert", "HEAD", "--no-edit"],
                capture_output=True, text=True, cwd=cwd, timeout=30,
            )
            if result.returncode == 0:
                console.print("  [green]\u2713[/green] Reverted last commit.")
            else:
                console.print(f"  [red]\u2717[/red] Git revert failed: {result.stderr.strip()[:80]}")
                console.print("  [dim]Try manually: git revert HEAD[/dim]")
                raise typer.Exit(1)

    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
        console.print(f"  [red]\u2717[/red] Could not undo: {e}")
        raise typer.Exit(1)

    console.print()


def _get_git_diff(diff_ref: str) -> Optional[str]:
    """Run git diff with the given reference and return the output."""
    try:
        result = subprocess.run(
            ["git", "diff", diff_ref],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


@app.command()
def review(
    paths: Optional[list[str]] = typer.Argument(None, help="Files or directories to review"),
    last: bool = typer.Option(False, "--last", help="Review the last change MDx made"),
    diff: Optional[str] = typer.Option(None, "--diff", help="Review a git diff (e.g., HEAD~1, main..feature)"),
    staged: bool = typer.Option(False, "--staged", help="Review staged git changes (for pre-commit)"),
    backend: Optional[str] = typer.Option(
        None, "--backend", "-b", help="Comma-separated backends (e.g., 'claude,codex')"
    ),
    format: str = typer.Option("rich", "--format", "-f", help="Output format: rich or json"),
) -> None:
    """Run adversarial multi-model code review."""
    asyncio.run(_run_review(paths, last, diff, staged, backend, format))


async def _run_review(
    paths: Optional[list[str]],
    last: bool,
    diff_ref: Optional[str],
    staged: bool,
    backend_str: Optional[str],
    format: str,
) -> None:
    """Execute the adversarial review."""
    from .governance.audit_trail import AuditEntry, write_audit_entry
    from .governance.policy_engine import evaluate_policies, load_policy_file
    from .review.orchestrator import prepare_target_from_diff, prepare_target_from_paths, run_review
    from .review.renderer import render_review

    # Parse backend list
    backend_names: Optional[list[str]] = None
    if backend_str:
        backend_names = [b.strip() for b in backend_str.split(",") if b.strip()]

    # Handle --staged: review staged git changes
    if staged:
        try:
            result = subprocess.run(
                ["git", "diff", "--cached"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0 or not result.stdout.strip():
                console.print("[yellow]No staged changes to review.[/yellow]")
                raise typer.Exit(1)
            target = prepare_target_from_diff(result.stdout, diff_ref="staged")
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            console.print("[red]Could not get staged diff. Are you in a git repo?[/red]")
            raise typer.Exit(1)

    # Determine review target
    elif last:
        task_data = _load_last_task()
        if not task_data or not task_data.get("diff"):
            console.print("[yellow]No recent changes to review. Run a task first, then try again.[/yellow]")
            raise typer.Exit(1)
        target = prepare_target_from_diff(task_data["diff"], diff_ref="last task")
        if not target.content.strip():
            console.print("[yellow]No changes detected in last task.[/yellow]")
            raise typer.Exit(1)

    elif diff_ref:
        diff_text = _get_git_diff(diff_ref)
        if not diff_text:
            console.print(f"[red]No diff found for '{diff_ref}'. Check the reference.[/red]")
            raise typer.Exit(1)
        target = prepare_target_from_diff(diff_text, diff_ref=diff_ref)

    elif paths:
        target = prepare_target_from_paths(paths)
        if not target.content.strip():
            console.print("[red]No reviewable content found in the specified paths.[/red]")
            raise typer.Exit(1)

    else:
        console.print("[red]Specify files/directories, --last, or --diff to review.[/red]")
        console.print()
        console.print("  mdx review src/              [dim]# Review a directory[/dim]")
        console.print("  mdx review src/auth/login.py [dim]# Review a specific file[/dim]")
        console.print("  mdx review --last            [dim]# Review last MDx change[/dim]")
        console.print("  mdx review --diff HEAD~1     [dim]# Review a git diff[/dim]")
        raise typer.Exit(1)

    # Show what we're reviewing
    if format != "json":
        console.print()
        console.print(f"  [dim]Reviewing: {target.description}[/dim]")

    # Run the review
    result = await run_review(target=target, backends=backend_names)

    if not result.backend_results:
        console.print("[red]No backends available for review.[/red]")
        console.print("Install at least one backend: Claude Code, Codex CLI, or Gemini CLI.")
        raise typer.Exit(1)

    # Render output
    json_output = render_review(result, format=format)
    if json_output:
        console.print(json_output)

    # Write review audit entry
    config = load_config()
    if config.audit.enabled:
        successful = [br for br in result.backend_results if not br.error]
        findings_per_backend = {br.backend_name: len(br.findings) for br in successful}

        # Evaluate reviewed files against policies
        policy_eval = None
        try:
            policy_file = load_policy_file()
            if policy_file and target.files:
                policy_result = evaluate_policies(policy_file, target.files)
                if policy_result.matching_policies:
                    total_findings = sum(findings_per_backend.values())
                    policy_eval = {
                        "matching_policies": policy_result.matching_policies,
                        "requires_review": policy_result.requires_review,
                        "requires_approval": policy_result.requires_approval,
                        "findings_count": total_findings,
                    }
        except Exception:
            pass

        entry = AuditEntry(
            session_id=str(uuid.uuid4()),
            task=f"adversarial_review: {target.description}",
            backend=",".join(br.backend_name for br in successful),
            working_directory=str(Path.cwd()),
            duration_seconds=result.total_duration_seconds,
            cost_usd=result.total_cost_usd if result.total_cost_usd > 0 else None,
            status="success",
            backend_selection_reason="adversarial_review",
            backends_available=[br.backend_name for br in result.backend_results],
            policy_evaluation=policy_eval,
        )
        write_audit_entry(entry)


@app.command()
def update() -> None:
    """Update MDx Code and all installed backends."""
    import shutil

    console.print()
    console.print("  [bold]Updating MDx Code and backends...[/bold]")
    console.print()

    backend_updates = {
        "claude": ("claude", ["claude", "update"]),
        "codex": ("codex", ["npm", "update", "-g", "@openai/codex"]),
        "gemini": ("gemini", ["npm", "update", "-g", "@google/gemini-cli"]),
    }

    for name, (binary, cmd) in backend_updates.items():
        if shutil.which(binary):
            console.print(f"  Updating {name.title()}...", end=" ")
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=120,
                )
                if result.returncode == 0:
                    console.print("[green]\u2713[/green]")
                else:
                    stderr = result.stderr.strip()[:60] if result.stderr else "unknown error"
                    console.print(f"[yellow]\u26a0 {stderr}[/yellow]")
            except subprocess.TimeoutExpired:
                console.print("[red]\u2717 timed out[/red]")
            except (FileNotFoundError, OSError) as e:
                console.print(f"[red]\u2717 {e}[/red]")
        else:
            console.print(f"  {name.title()}: [dim]not installed[/dim]")

    console.print()
    console.print(f"  MDx Code: v{__version__}")
    console.print()


# --- Policy commands ---


@policy_app.callback(invoke_without_command=True)
def policy_default(ctx: typer.Context) -> None:
    """Show active policies."""
    if ctx.invoked_subcommand is not None:
        return

    from .governance.policy_engine import load_policy_file

    policy_file = load_policy_file()
    if policy_file is None:
        console.print("[dim]No .mdxpolicy file found.[/dim]")
        console.print("Run [bold]mdx policy init[/bold] to create one.")
        return

    lines: list[str] = []
    lines.append("")
    lines.append(f"  Version: {policy_file.version}")
    lines.append(f"  Policies: {len(policy_file.policies)}")
    lines.append("")

    for p in policy_file.policies:
        severity_style = {
            "critical": "red",
            "high": "yellow",
            "medium": "blue",
            "low": "dim",
        }.get(p.severity, "dim")

        reqs: list[str] = []
        if p.requires.adversarial_review:
            reqs.append("review")
        if p.requires.human_approval:
            reqs.append("approval")
        if p.requires.min_reviewers > 1:
            reqs.append(f"{p.requires.min_reviewers} reviewers")
        req_str = ", ".join(reqs) if reqs else "none"

        lines.append(f"  [bold]{p.name}[/bold]  [{severity_style}]{p.severity}[/{severity_style}]")
        if p.description:
            lines.append(f"    {p.description}")
        lines.append(f"    Paths: {len(p.paths)}  Requires: {req_str}")
        lines.append("")

    defaults = policy_file.defaults
    lines.append("  [dim]Defaults:[/dim]")
    lines.append(
        f"    review={defaults.adversarial_review}  "
        f"approval={defaults.human_approval}  "
        f"severity={defaults.severity}"
    )
    lines.append("")

    content = "\n".join(lines)
    panel = Panel(content, title="Active Policies", border_style="green", width=min(console.width, 70))
    console.print(panel)


@policy_app.command("check")
def policy_check(
    files: list[str] = typer.Argument(..., help="Files to check against policies"),
) -> None:
    """Check files against active policies."""
    from .governance.policy_engine import _match_path, evaluate_policies, load_policy_file

    policy_file = load_policy_file()
    if policy_file is None:
        console.print("[dim]No .mdxpolicy file found. Run mdx policy init to create one.[/dim]")
        raise typer.Exit(1)

    result = evaluate_policies(policy_file, files)

    console.print()
    if result.matching_policies:
        console.print(f"  [bold]Matching policies:[/bold] {', '.join(result.matching_policies)}")
        if result.requires_review:
            console.print("  [yellow]Adversarial review required[/yellow]")
        if result.requires_approval:
            console.print("  [yellow]Human approval required[/yellow]")
        if result.min_reviewers > 1:
            console.print(f"  [dim]Minimum reviewers: {result.min_reviewers}[/dim]")
    else:
        console.print("  [green]No policies triggered.[/green] Default rules apply.")
    console.print()

    # Show per-file breakdown
    for filepath in files:
        matched: list[str] = []
        for policy in policy_file.policies:
            for pattern in policy.paths:
                if _match_path(filepath, pattern):
                    matched.append(policy.name)
                    break
        if matched:
            console.print(f"  {filepath}  \u2192  {', '.join(matched)}")
        else:
            console.print(f"  {filepath}  \u2192  [dim]no match[/dim]")
    console.print()


@policy_app.command("init")
def policy_init() -> None:
    """Create a starter .mdxpolicy file in the current directory."""
    from .governance.policy_engine import STARTER_POLICY

    target = Path.cwd() / ".mdxpolicy"
    if target.exists():
        console.print(f"[yellow].mdxpolicy already exists at {target}[/yellow]")
        raise typer.Exit(1)

    target.write_text(STARTER_POLICY)
    console.print(f"[green]Created .mdxpolicy at {target}[/green]")
    console.print("Edit it to match your project's security requirements.")


# --- Compliance command ---


@app.command()
def compliance() -> None:
    """Show regulatory compliance mapping matrix."""
    from .governance.compliance import get_compliance_matrix

    matrix = get_compliance_matrix()

    for framework, features in matrix.items():
        lines: list[str] = []
        lines.append("")
        for feature, description in features.items():
            lines.append(f"  [bold]{feature}[/bold]")
            lines.append(f"    {description}")
            lines.append("")

        display_name = {
            "SOC2": "SOC 2",
            "EU_AI_Act": "EU AI Act",
            "OSFI_B13": "OSFI B-13",
            "OCC_2011_12": "OCC 2011-12",
        }.get(framework, framework)

        content = "\n".join(lines)
        panel = Panel(
            content,
            title=f"Compliance: {display_name}",
            border_style="blue",
            width=min(console.width, 80),
        )
        console.print(panel)


# --- Hook commands ---

HOOK_MARKER = "# MDx Code pre-commit hook"


@hook_app.command("install")
def hook_install() -> None:
    """Install MDx Code git pre-commit hook."""
    git_dir = Path.cwd() / ".git"
    if not git_dir.is_dir():
        console.print("[red]Not a git repository. Run this from a git repo root.[/red]")
        raise typer.Exit(1)

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hooks_dir / "pre-commit"

    if hook_path.exists():
        content = hook_path.read_text()
        if HOOK_MARKER not in content:
            console.print("[yellow]A pre-commit hook already exists (not ours). Aborting.[/yellow]")
            console.print(f"  {hook_path}")
            raise typer.Exit(1)

    hook_content = f"""\
#!/bin/sh
{HOOK_MARKER}
# Installed by: mdx hook install
exec mdx hook check
"""
    hook_path.write_text(hook_content)
    hook_path.chmod(0o755)
    console.print("[green]Pre-commit hook installed.[/green]")
    console.print(f"  {hook_path}")


@hook_app.command("uninstall")
def hook_uninstall() -> None:
    """Remove the MDx Code pre-commit hook."""
    hook_path = Path.cwd() / ".git" / "hooks" / "pre-commit"

    if not hook_path.exists():
        console.print("[dim]No pre-commit hook found.[/dim]")
        return

    content = hook_path.read_text()
    if HOOK_MARKER not in content:
        console.print("[yellow]Pre-commit hook exists but was not installed by MDx. Not removing.[/yellow]")
        return

    hook_path.unlink()
    console.print("[green]Pre-commit hook removed.[/green]")


@hook_app.command("status")
def hook_status() -> None:
    """Check if the MDx pre-commit hook is installed."""
    hook_path = Path.cwd() / ".git" / "hooks" / "pre-commit"

    if not hook_path.exists():
        console.print("  [dim]Pre-commit hook: not installed[/dim]")
        return

    content = hook_path.read_text()
    if HOOK_MARKER in content:
        console.print("  [green]Pre-commit hook: installed (MDx Code)[/green]")
    else:
        console.print("  [yellow]Pre-commit hook: installed (not MDx — foreign hook)[/yellow]")


@hook_app.command("check", hidden=True)
def hook_check() -> None:
    """Check staged files against policies (used by git hook)."""
    from .governance.policy_engine import evaluate_policies, load_policy_file

    # Get staged file list
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True, text=True, timeout=10,
        )
        staged_files = [f for f in result.stdout.strip().splitlines() if f]
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        # Can't get staged files — don't block
        raise typer.Exit(0)

    if not staged_files:
        raise typer.Exit(0)

    policy_file = load_policy_file()
    if policy_file is None:
        raise typer.Exit(0)

    policy_result = evaluate_policies(policy_file, staged_files)

    if policy_result.requires_review:
        policies_str = ", ".join(policy_result.matching_policies)
        console.print(f"[yellow]MDx Policy [{policies_str}]: adversarial review required[/yellow]")
        console.print()
        for f in staged_files:
            console.print(f"  {f}")
        console.print()
        console.print("Run: [bold]mdx review --staged[/bold]")
        console.print("To bypass: [dim]git commit --no-verify[/dim]")
        raise typer.Exit(1)

    raise typer.Exit(0)


# --- MCP commands ---

MCP_SERVERS = {
    "governance": {
        "module": "mcp_servers.governance.server",
        "entry_point": "mdx-governance-server",
        "description": "Policy checking and enforcement",
    },
    "audit": {
        "module": "mcp_servers.audit.server",
        "entry_point": "mdx-audit-server",
        "description": "Immutable audit trail access",
    },
    "cost": {
        "module": "mcp_servers.cost.server",
        "entry_point": "mdx-cost-server",
        "description": "Spending tracking and reporting",
    },
}


@mcp_app.command("status")
def mcp_status() -> None:
    """Show available MCP servers and their status."""
    # Check if mcp package is importable
    mcp_available = False
    try:
        import mcp  # noqa: F401

        mcp_available = True
    except ImportError:
        pass

    console.print()
    console.print("  [bold]MDx Code MCP Servers[/bold]")
    console.print()

    if not mcp_available:
        console.print("  [red]MCP package not installed.[/red]")
        console.print('  Install with: [bold]pip install -e ".[mcp]"[/bold]')
        console.print()
        return

    console.print("  [green]MCP package installed.[/green]")
    console.print()

    for name, info in MCP_SERVERS.items():
        module = info["module"]
        entry = info["entry_point"]
        desc = info["description"]

        # Check if server module is importable
        try:
            __import__(module)
            console.print(f"  [green]\u2713[/green] {name:<14} {desc}")
            console.print(f"    [dim]Run: {entry}[/dim]")
        except ImportError as e:
            console.print(f"  [red]\u2717[/red] {name:<14} {desc}")
            console.print(f"    [dim]Import error: {e}[/dim]")

    console.print()
    console.print("  Configure in your MCP client with: [bold]mdx mcp config[/bold]")
    console.print()


@mcp_app.command("config")
def mcp_config(
    client: str = typer.Option(
        "claude-code",
        "--client",
        "-c",
        help="Target client: claude-code, cursor, or codex",
    ),
) -> None:
    """Generate MCP server configuration for your client."""
    servers_config = {
        "mdx-governance": {
            "command": "mdx-governance-server",
            "args": [],
        },
        "mdx-audit": {
            "command": "mdx-audit-server",
            "args": [],
        },
        "mdx-cost": {
            "command": "mdx-cost-server",
            "args": [],
        },
    }

    console.print()

    if client == "claude-code":
        config = {"mcpServers": servers_config}
        console.print("  [bold]Claude Code[/bold] MCP Configuration")
        console.print()
        console.print("  Add to [bold]~/.claude.json[/bold] (global) or")
        console.print("  [bold].claude/settings.json[/bold] (project-level):")
        console.print()
        console.print(json.dumps(config, indent=2))
        console.print()
        console.print("  [dim]The mcpServers key merges with your existing config.[/dim]")

    elif client == "cursor":
        config = {"mcpServers": servers_config}
        console.print("  [bold]Cursor[/bold] MCP Configuration")
        console.print()
        console.print("  Create or edit [bold].cursor/mcp.json[/bold] in your project root:")
        console.print()
        console.print(json.dumps(config, indent=2))
        console.print()
        console.print("  [dim]Restart Cursor after editing to pick up MCP servers.[/dim]")

    elif client == "codex":
        console.print("  [bold]Codex CLI[/bold] MCP Configuration")
        console.print()
        console.print("  Add to [bold]~/.codex/config.json[/bold] or pass via CLI flags:")
        console.print()
        console.print("  codex --mcp-server mdx-governance-server \\")
        console.print("        --mcp-server mdx-audit-server \\")
        console.print("        --mcp-server mdx-cost-server")
        console.print()
        console.print("  Or in config.json:")
        console.print()
        config = {"mcpServers": servers_config}
        console.print(json.dumps(config, indent=2))

    else:
        console.print(f"  [red]Unknown client: {client}[/red]")
        console.print("  Supported: claude-code, cursor, codex")
        return

    console.print()
    console.print("  [dim]Ensure MDx Code is installed: pip install -e \".[mcp]\"[/dim]")
    console.print()
