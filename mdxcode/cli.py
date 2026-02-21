"""MDx Code CLI — The AI Engineering Manager."""

import asyncio
import uuid
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .backends.discovery import discover_backends, get_best_backend
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
        asyncio.run(_execute_task(task))
        raise typer.Exit()

    # No task, no subcommand — interactive mode
    backends = asyncio.run(discover_backends())
    show_banner(backends)

    task_input = console.input("[bold]What do you want to work on?[/bold] \u2192 ")
    if task_input.strip():
        asyncio.run(_execute_task(task_input.strip()))


async def _execute_task(task: str) -> None:
    """Execute a task via the best available backend."""
    config = load_config()
    session_id = str(uuid.uuid4())

    backend = await get_best_backend(config.default_backend)
    if backend is None:
        console.print(
            "[red]No backend available.[/red] Install Claude Code, Codex CLI, or Gemini CLI."
        )
        console.print("Run [bold]mdx setup[/bold] to check backend status.")
        raise typer.Exit(1)

    cwd = Path.cwd()

    # Stream output from backend
    full_output, duration = await stream_output(backend.execute(task, cwd))

    # Parse output for metadata
    model, cost, tokens_in, tokens_out = backend._parse_json_output(full_output)

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
            exit_code=0,
            status="success",
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
        )


@app.command()
def setup() -> None:
    """Detect and display available backends."""
    backends = asyncio.run(discover_backends())
    show_banner(backends)

    table = Table(title="Backend Status", show_header=True)
    table.add_column("Backend", style="bold")
    table.add_column("Version")
    table.add_column("Authenticated")
    table.add_column("Status")

    for b in backends:
        auth = "[green]\u2713[/green]" if b.authenticated else "[red]\u2717[/red]"
        status = "[green]Ready[/green]" if b.healthy else "[yellow]Unavailable[/yellow]"
        table.add_row(b.name.title(), b.version, auth, status)

    # Show CLIs not detected at all
    known = {"claude", "codex", "gemini"}
    detected = {b.name for b in backends}
    for name in known - detected:
        table.add_row(name.title(), "not found", "[red]\u2717[/red]", "[dim]Not installed[/dim]")

    console.print(table)
    console.print()


@app.command()
def status() -> None:
    """Show current configuration and backend health."""
    config = load_config()
    backends = asyncio.run(discover_backends())
    show_banner(backends)

    console.print("[bold]Configuration[/bold]")
    console.print(f"  Default backend: {config.default_backend}")
    console.print(f"  Routing strategy: {config.routing_strategy}")
    console.print(f"  Audit enabled: {config.audit.enabled}")
    console.print(f"  Chain hashing: {config.audit.chain_hashing}")
    console.print(f"  Audit directory: {config.audit.directory}")
    console.print(f"  Show footer: {config.display.show_footer}")
    console.print(f"  Verbose: {config.display.verbose}")
    console.print()


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

    for entry in entries:
        ts = entry.get("timestamp", "")[:19]
        backend = entry.get("backend", "?")
        task = entry.get("task", "?")
        dur = f"{entry.get('duration_seconds', 0):.1f}s"
        status_val = entry.get("status", "?")
        cost = entry.get("cost_usd")
        cost_str = f"${cost:.4f}" if cost else "-"
        status_style = "green" if status_val == "success" else "red"

        table.add_row(ts, backend, task, dur, f"[{status_style}]{status_val}[/{status_style}]", cost_str)

    console.print(table)
    console.print()
