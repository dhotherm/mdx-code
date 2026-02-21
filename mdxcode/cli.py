"""MDx Code CLI — The AI Engineering Manager."""

import asyncio
import uuid
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .backends.circuit_breaker import get_circuit_breaker
from .backends.discovery import (
    BACKEND_CLASSES,
    INSTALL_INSTRUCTIONS,
    KNOWN_CLIS,
    discover_backends,
    get_best_backend,
)
from .config import load_config
from .governance.audit_trail import AuditEntry, read_recent_entries, write_audit_entry
from .output.footer import show_footer
from .output.streamer import stream_output

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


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-V", help="Show version"),
    backend: Optional[str] = typer.Option(
        None, "--backend", "-b", help="Force a specific backend (claude, codex, gemini)"
    ),
) -> None:
    """MDx Code — The AI Engineering Manager."""
    if version:
        console.print(f"MDx Code v{__version__}")
        raise typer.Exit()

    # If a subcommand is being invoked, let it handle things
    if ctx.invoked_subcommand is not None:
        return

    # Check for extra args — these form the task string
    # e.g., mdx "fix the bug" or mdx fix the bug
    if ctx.args:
        task = " ".join(ctx.args)
        asyncio.run(_execute_task(task, backend_override=backend))
        raise typer.Exit()

    # No task, no subcommand — interactive mode
    backends = asyncio.run(discover_backends())
    show_banner(backends)

    task_input = console.input("[bold]What do you want to work on?[/bold] \u2192 ")
    if task_input.strip():
        asyncio.run(_execute_task(task_input.strip(), backend_override=backend))


async def _execute_task(task: str, backend_override: Optional[str] = None) -> None:
    """Execute a task via the best available backend."""
    config = load_config()
    session_id = str(uuid.uuid4())

    # Determine which backend to use
    preference = backend_override or config.default_backend

    # Get available backends list for audit
    all_backends = await discover_backends()
    backends_available = [b.name for b in all_backends if b.healthy]

    backend, selection_reason = await get_best_backend(preference)

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

    cwd = Path.cwd()
    cb = get_circuit_breaker()

    # Stream output from backend
    full_output, duration = await stream_output(backend.execute(task, cwd))

    # Determine success/failure for circuit breaker
    # Check for MDx Code error markers in output
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
        )
        write_audit_entry(entry)

    # Show footer
    if config.display.show_footer:
        show_footer(
            backend_name=backend.name,
            model=model,
            duration=duration,
            session_id=session_id,
            cost_usd=cost,
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

    ready = sum(1 for b in backends if b.healthy)
    console.print()
    console.print(f"  {ready} backend{'s' if ready != 1 else ''} ready. You can:")
    console.print("    mdx \"task\"                    \u2192 auto-select best backend")
    console.print("    mdx \"task\" --backend codex   \u2192 force specific backend")
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
        cost = entry.get("cost_usd")
        cost_str = f"${cost:.4f}" if cost else "-"
        status_style = "green" if status_val == "success" else "red"
        reason = entry.get("backend_selection_reason", "")

        table.add_row(
            ts, backend, task, dur,
            f"[{status_style}]{status_val}[/{status_style}]",
            cost_str, reason,
        )

    console.print(table)
    console.print()
