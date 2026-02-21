"""MDx Code CLI — The AI Engineering Manager."""

import asyncio
import json
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import __version__
from .backends.circuit_breaker import get_circuit_breaker
from .backends.discovery import (
    BACKEND_CLASSES,
    INSTALL_INSTRUCTIONS,
    KNOWN_CLIS,
    discover_backends,
    get_best_backend,
)
from .config import MDX_DIR, load_config
from .governance.audit_trail import AuditEntry, read_recent_entries, write_audit_entry
from .output.footer import show_footer
from .output.streamer import stream_output
from .review.orchestrator import (
    AdversarialReviewResult,
    prepare_target_from_diff,
    prepare_target_from_paths,
    run_review,
)
from .review.renderer import render_review
from .router.cost_tracker import (
    get_cost_by_backend,
    get_date_range_for_period,
    get_savings,
    get_top_tasks,
    get_total_cost,
    query_costs,
    record_cost,
)
from .router.engine import categorize_task
from .router.profiles import (
    estimate_cost,
    estimate_tokens_from_chars,
    get_profiles,
)
from .router.strategies import route_task

LAST_TASK_PATH = MDX_DIR / "last_task.json"

console = Console()
app = typer.Typer(
    name="mdx",
    help="MDx Code — The AI Engineering Manager",
    add_completion=False,
    invoke_without_command=True,
    context_settings={"allow_extra_args": True, "allow_interspersed_args": False},
)


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
) -> None:
    """Show a one-line routing decision."""
    display_name = KNOWN_CLIS.get(backend_name, backend_name.title())
    if user_specified:
        console.print(f"  [dim]\u2192 Using {display_name} (user specified)[/dim]")
    else:
        console.print(f"  [dim]\u2192 Routing to {display_name} \u2014 {reason}[/dim]")


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-V", help="Show version"),
    backend: Optional[str] = typer.Option(
        None, "--backend", "-b", help="Force a specific backend (claude, codex, gemini)"
    ),
    strategy: Optional[str] = typer.Option(
        None, "--strategy", "-s", help="Routing strategy (cost, quality, balanced)"
    ),
) -> None:
    """MDx Code — The AI Engineering Manager."""
    if version:
        console.print(f"MDx Code v{__version__}")
        raise typer.Exit()

    # If a subcommand is being invoked, let it handle things
    if ctx.invoked_subcommand is not None:
        return

    # Normalize strategy aliases
    strategy_map = {"cost": "cost_optimized", "quality": "quality_first"}
    resolved_strategy = strategy_map.get(strategy, strategy) if strategy else None

    # Check for extra args — these form the task string
    # e.g., mdx "fix the bug" or mdx fix the bug
    if ctx.args:
        task = " ".join(ctx.args)
        asyncio.run(
            _execute_task(task, backend_override=backend, strategy_override=resolved_strategy)
        )
        raise typer.Exit()

    # No task, no subcommand — interactive mode
    backends = asyncio.run(discover_backends())
    show_banner(backends)

    task_input = console.input("[bold]What do you want to work on?[/bold] \u2192 ")
    if task_input.strip():
        asyncio.run(
            _execute_task(
                task_input.strip(),
                backend_override=backend,
                strategy_override=resolved_strategy,
            )
        )


async def _execute_task(
    task: str,
    backend_override: Optional[str] = None,
    strategy_override: Optional[str] = None,
) -> None:
    """Execute a task via the best available backend."""
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
                    f"[red]OpenCode does not support non-interactive execution.[/red]"
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
        _show_routing_line(backend.name, routing_reason, user_specified=user_specified)

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
    _save_last_task(task, backend.name, cwd)

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
        )


@app.command()
def setup() -> None:
    """Detect and display available backends."""
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
    from .backends.base import HealthStatus

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
    savings = get_savings(since=since_dt, until=until_dt)
    top = get_top_tasks(since=since_dt, until=until_dt, limit=5)

    # Build display
    lines: list[str] = []
    lines.append("")
    lines.append(f"  Total: [bold]${total:.2f}[/bold]")
    lines.append("")

    if by_backend:
        lines.append("  By backend:")
        max_cost = max(by_backend.values()) if by_backend else 1
        for name, amount in sorted(by_backend.items(), key=lambda x: x[1], reverse=True):
            pct = (amount / total * 100) if total > 0 else 0
            bar_len = int((amount / max_cost) * 20) if max_cost > 0 else 0
            bar = "\u2588" * bar_len + "\u2591" * (20 - bar_len)
            lines.append(
                f"    {name.title():<10} ${amount:>7.2f} ({pct:>4.0f}%)  {bar}"
            )
        lines.append("")

    if savings > 0:
        lines.append(
            f"  Smart routing saved: [green]${savings:.2f}[/green] {period_label.lower()}"
        )
        lines.append("  [dim](vs. using most expensive option every time)[/dim]")
        lines.append("")

    if top:
        lines.append("  Top tasks:")
        for entry in top:
            summary = entry.get("task_summary", "?")
            if len(summary) > 35:
                summary = summary[:32] + "..."
            ts = entry.get("timestamp", "")[:10]
            c = entry.get("cost_usd", 0) or 0
            lines.append(f"    {summary:<38} ${c:.2f}")
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
def audit(count: int = typer.Option(10, "--count", "-n", help="Number of entries to show")) -> None:
    """Show recent audit entries."""
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

    for entry in entries:
        ts = entry.get("timestamp", "")[:19]
        backend = entry.get("backend", "?")
        task = entry.get("task", "?")
        dur = f"{entry.get('duration_seconds', 0):.1f}s"
        status_val = entry.get("status", "?")
        cost_val = entry.get("cost_usd")
        cost_str = f"${cost_val:.4f}" if cost_val else "-"
        status_style = "green" if status_val == "success" else "red"
        reason = entry.get("routing_reason") or entry.get("backend_selection_reason", "")

        table.add_row(
            ts, backend, task, dur,
            f"[{status_style}]{status_val}[/{status_style}]",
            cost_str, reason,
        )

    console.print(table)
    console.print()


def _save_last_task(task: str, backend_name: str, cwd: Path) -> None:
    """Save last task info for `mdx review --last`."""
    try:
        # Capture git diff of changes made
        diff = ""
        files_modified: list[str] = []
        try:
            result = subprocess.run(
                ["git", "diff", "HEAD"],
                capture_output=True, text=True, cwd=str(cwd), timeout=10,
            )
            diff = result.stdout
            # Also check for untracked files
            result2 = subprocess.run(
                ["git", "diff", "--name-only", "HEAD"],
                capture_output=True, text=True, cwd=str(cwd), timeout=10,
            )
            files_modified = [f for f in result2.stdout.strip().splitlines() if f]
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            pass

        data = {
            "task": task,
            "backend": backend_name,
            "files_modified": files_modified,
            "diff": diff,
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
    backends: Optional[str] = typer.Option(
        None, "--backends", help="Comma-separated backends to use (e.g., 'claude,codex')"
    ),
    format: str = typer.Option("rich", "--format", "-f", help="Output format: rich or json"),
) -> None:
    """Run adversarial multi-model code review."""
    asyncio.run(_run_review(paths, last, diff, backends, format))


async def _run_review(
    paths: Optional[list[str]],
    last: bool,
    diff_ref: Optional[str],
    backends_str: Optional[str],
    format: str,
) -> None:
    """Execute the adversarial review."""
    # Parse backend list
    backend_names: Optional[list[str]] = None
    if backends_str:
        backend_names = [b.strip() for b in backends_str.split(",") if b.strip()]

    # Determine review target
    if last:
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
        )
        write_audit_entry(entry)
