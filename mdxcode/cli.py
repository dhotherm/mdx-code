"""MDx Code CLI — The AI Engineering Manager."""

import asyncio
import json
import os
import subprocess
import sys
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
from .config import MDX_DIR, load_config, save_config

# All other imports (backends, router, review, governance) are lazy —
# imported inside the functions that use them for fast startup.

LAST_TASK_PATH = MDX_DIR / "last_task.json"

# Check NO_COLOR standard (https://no-color.org)
NO_COLOR = os.environ.get("NO_COLOR") is not None

console = Console(no_color=NO_COLOR)

# Shared task category icons — used in routing line, history, audit, summary
CATEGORY_ICONS: dict[str, str] = {
    "code_review": "\U0001f50d",
    "debugging": "\U0001f41b",
    "code_generation": "\U0001f3d7\ufe0f",
    "documentation": "\U0001f4dd",
    "security": "\U0001f512",
    "refactoring": "\u267b\ufe0f",
    "test_writing": "\U0001f9ea",
    "general": "\U0001f4ac",
}

# Cache for project context (branch, language, file count) — computed once per session
_project_context_cache: str | None = None


def _get_project_context() -> str:
    """Detect project context: git branch, primary language, file count."""
    global _project_context_cache
    if _project_context_cache is not None:
        return _project_context_cache

    parts: list[str] = []

    # Git branch
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            parts.append(result.stdout.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    # Primary language and file count (from git ls-files)
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            files = result.stdout.strip().splitlines()

            ext_count: dict[str, int] = {}
            for f in files:
                ext = Path(f).suffix.lower()
                if ext:
                    ext_count[ext] = ext_count.get(ext, 0) + 1

            EXT_TO_LANG = {
                ".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript",
                ".js": "JavaScript", ".jsx": "JavaScript", ".go": "Go",
                ".rs": "Rust", ".java": "Java", ".kt": "Kotlin",
                ".rb": "Ruby", ".swift": "Swift", ".cs": "C#",
                ".cpp": "C++", ".c": "C", ".php": "PHP",
            }

            lang_count: dict[str, int] = {}
            for ext, count in ext_count.items():
                lang = EXT_TO_LANG.get(ext)
                if lang:
                    lang_count[lang] = lang_count.get(lang, 0) + count

            if lang_count:
                primary = max(lang_count, key=lang_count.get)  # type: ignore[arg-type]
                parts.append(primary)

            if files:
                parts.append(f"{len(files)} files")
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    _project_context_cache = " \u00b7 ".join(parts)
    return _project_context_cache


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
    rich_markup_mode="rich",
    epilog=(
        "[bold]Examples:[/bold]\n"
        '  mdx "fix the login bug"              Smart-route to best backend\n'
        '  mdx "add tests" --backend claude      Force Claude Code\n'
        '  mdx "refactor auth" --strategy cost   Optimize for cost\n'
        '  mdx "task" --pick                     Choose backend interactively'
    ),
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


def show_personalized_banner() -> None:
    """Show a personalized banner for returning users (5+ tasks)."""
    from .router.cost_tracker import get_date_range_for_period, get_total_cost

    config = load_config()

    # Get user's name from git config
    name = ""
    try:
        result = subprocess.run(
            ["git", "config", "user.name"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            full_name = result.stdout.strip()
            name = full_name.split()[0] if full_name else ""
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass

    # Time-aware greeting
    hour = datetime.now().hour
    if hour < 12:
        greeting = "Good morning"
    elif hour < 17:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"

    greeting_str = f"{greeting}, {name}" if name else greeting

    # Get weekly cost
    try:
        since_dt, until_dt = get_date_range_for_period("week")
        week_cost = get_total_cost(since=since_dt, until=until_dt)
    except Exception:
        week_cost = 0.0

    # Get today's tasks from audit
    today_tasks: list[dict] = []
    try:
        from .governance.audit_trail import read_filtered_entries

        audit_dir = Path(config.audit.directory).expanduser()
        today_str = datetime.now().strftime("%Y-%m-%d")
        today_entries = read_filtered_entries(audit_dir, since=today_str)
        today_tasks = [
            e for e in today_entries
            if not e.get("task", "").startswith(("policy_check:", "adversarial_review:"))
        ]
    except Exception:
        pass

    # Get backends
    from .backends.discovery import discover_backends

    backends = asyncio.run(discover_backends())
    ready = sum(1 for b in backends if b.healthy)

    console.print()
    console.print(f"  [bold]MDx Code[/bold] v{__version__}")
    console.print(f"  {greeting_str}. ", end="")

    stats_parts = []
    if today_tasks:
        stats_parts.append(f"{len(today_tasks)} tasks today")
    if week_cost > 0:
        stats_parts.append(f"${week_cost:.4f} this week")
    stats_parts.append(f"{ready} backends active")

    console.print("[dim]" + " · ".join(stats_parts) + "[/dim]")

    # Show recent tasks (last 3)
    if today_tasks:
        console.print()
        console.print("  [dim]Recent:[/dim]")
        for entry in today_tasks[-3:]:
            task = entry.get("task", "?")
            if len(task) > 60:
                task = task[:57] + "..."
            backend_name = entry.get("backend", "?")
            console.print(f"    [dim]·[/dim] \"{task}\" [dim]via {backend_name.title()}[/dim]")

    console.print()


async def _run_first_time_setup() -> None:
    """Interactive first-run setup wizard."""
    from .backends.discovery import KNOWN_CLIS, discover_backends

    console.print()
    console.print("  [bold]Welcome to MDx Code[/bold] — The AI Engineering Manager")
    console.print()
    console.print("  [dim]Let's get you set up. This takes about 30 seconds.[/dim]")
    console.print()

    # Phase 1: Detect backends with live feedback
    console.print("  [bold]Detecting your AI coding tools...[/bold]")
    console.print()

    backends = await discover_backends()
    ready_count = 0

    for b in backends:
        display_name = KNOWN_CLIS.get(b.name, b.name.title())
        if b.healthy:
            auth_str = "authenticated" if b.authenticated else ""
            console.print(f"    [green]✓[/green] {display_name:<16} {b.version:<14} {auth_str}")
            ready_count += 1
        elif b.version != "not installed":
            console.print(f"    [yellow]⚠[/yellow] {display_name:<16} {b.version:<14} not authenticated")
        else:
            console.print(f"    [dim]✗ {display_name:<16} not found[/dim]")

    console.print()
    if ready_count == 0:
        console.print("  [red]No backends detected.[/red] Install at least one:")
        console.print("    npm install -g @anthropic-ai/claude-code")
        console.print("    npm install -g @google/gemini-cli")
        console.print("    npm install -g @openai/codex")
        console.print()
        return

    if ready_count == 1:
        console.print(f"  [green]{ready_count} backend ready.[/green]")
    else:
        console.print(f"  [green]{ready_count} backends ready.[/green] Smart routing is available.")

    console.print()

    # Phase 2: Pick strategy (only if multiple backends)
    config = load_config()

    if ready_count > 1:
        console.print("  [bold]Pick your default routing strategy:[/bold]")
        console.print()
        console.print("    [bold][1][/bold] Balanced         Best quality-per-dollar [green](recommended)[/green]")
        console.print("    [bold][2][/bold] Quality First    Always use the strongest model")
        console.print("    [bold][3][/bold] Cost Optimized   Minimize spend")
        console.print()

        choice = console.input("  Choose [1-3]: ").strip()

        strategy_map = {"1": "balanced", "2": "quality_first", "3": "cost_optimized"}
        config.routing_strategy = strategy_map.get(choice, "balanced")
        console.print()
    else:
        config.routing_strategy = "balanced"

    # Phase 3: Save config
    config.first_run_complete = True
    save_config(config)
    console.print("  [green]✓[/green] Config saved to ~/.mdx/config.yaml")

    # Phase 4: Show essential commands
    console.print()
    console.print("  [bold]You're ready. Here's what MDx Code can do:[/bold]")
    console.print()
    console.print('    [bold]mdx "fix the login bug"[/bold]     Routes to the best backend')
    console.print("    [bold]mdx review src/[/bold]             Multi-model code review")
    console.print("    [bold]mdx cost[/bold]                    See what you're spending")
    console.print("    [bold]mdx undo[/bold]                    Revert the last change")
    console.print()

    # Phase 5: Drop into first task
    console.print("  [dim]Try it now — type a task:[/dim]")
    task_input = console.input("  → ")
    if task_input.strip():
        await _execute_task(task_input.strip())


def _show_routing_line(
    backend_name: str,
    reason: str,
    user_specified: bool = False,
    scores: dict[str, float] | None = None,
    num_backends: int = 0,
    category: str = "general",
) -> None:
    """Show a one-line routing decision with project context and category icon."""
    from .output.colors import colored_backend

    icon = CATEGORY_ICONS.get(category, "\U0001f4ac")
    context = _get_project_context()
    context_str = f"{context} \u2192 " if context else "\u2192 "

    if user_specified:
        console.print(
            f"  [dim]{icon} {context_str}Using {colored_backend(backend_name)} (user specified)[/dim]"
        )
    else:
        console.print(
            f"  [dim]{icon} {context_str}Routing to {colored_backend(backend_name)} \u2014 {reason}[/dim]"
        )
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
    no_color: bool = typer.Option(False, "--no-color", help="Disable colors"),
    no_markdown: bool = typer.Option(False, "--no-markdown", help="Disable markdown rendering"),
) -> None:
    """MDx Code — The AI Engineering Manager."""
    if no_color or NO_COLOR:
        console.no_color = True
    # Store no_markdown in context for streamer
    ctx.ensure_object(dict)
    ctx.obj["no_markdown"] = no_markdown or not sys.stdout.isatty()

    if version:
        console.print(f"MDx Code v{__version__}")
        raise typer.Exit()

    # If no subcommand is being invoked, show banner + interactive prompt
    if ctx.invoked_subcommand is None:
        config = load_config()

        # First-run wizard
        if not config.first_run_complete:
            asyncio.run(_run_first_time_setup())
            raise typer.Exit()

        # Personalized banner for power users (5+ tasks)
        if config.task_count >= 5:
            show_personalized_banner()
        else:
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
    pick: bool = typer.Option(False, "--pick", "-p", help="Interactively pick a backend"),
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
        _execute_task(
            task, backend_override=backend, strategy_override=resolved_strategy, pick=pick,
        )
    )


async def _execute_task(
    task: str,
    backend_override: Optional[str] = None,
    strategy_override: Optional[str] = None,
    pick: bool = False,
) -> None:
    """Execute a task via the best available backend."""
    from .backends.circuit_breaker import get_circuit_breaker
    from .backends.discovery import INSTALL_INSTRUCTIONS, discover_backends, get_best_backend
    from .config import load_project_config
    from .governance.audit_trail import AuditEntry, write_audit_entry
    from .governance.policy_engine import evaluate_policies, load_policy_file
    from .output.footer import show_footer
    from .output.streamer import stream_output
    from .router.cost_tracker import get_date_range_for_period, get_total_cost, record_cost
    from .router.engine import categorize_task
    from .router.profiles import estimate_cost, estimate_tokens_from_chars, get_profiles
    from .router.strategies import route_task

    config = load_config()
    project_config = load_project_config()
    session_id = str(uuid.uuid4())

    # Get available backends list
    all_backends = await discover_backends()
    backends_available = [b.name for b in all_backends if b.healthy]

    # Categorize the task
    category = categorize_task(task)

    # Determine routing strategy (project config overrides global defaults)
    strategy = strategy_override or (
        project_config.strategy if project_config and project_config.strategy else config.routing_strategy
    )

    # Determine which backend to use
    user_specified = backend_override is not None
    routing_reason = ""
    routing_decision = None

    # Project config can set preferred backend
    if not backend_override and project_config and project_config.preferred_backend:
        backend_override = project_config.preferred_backend
        routing_reason = "project config (.mdx.yaml)"

    # Always compute profiles and routable backends (needed for fallback recovery)
    profiles = get_profiles()
    cb = get_circuit_breaker()
    routable_backends = [
        name for name in backends_available
        if name != "opencode" and cb.is_available(name)
    ]

    if user_specified:
        # User explicitly chose — bypass smart routing
        backend, selection_reason = await get_best_backend(backend_override)
        routing_reason = routing_reason or "user specified"
    else:
        # Smart routing: use categorization + strategy
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

    # Interactive backend picker (Feature 3)
    if pick and routing_decision and routing_decision.scores:
        from .output.colors import colored_backend as _cb

        console.print()
        console.print(f"  [bold]Pick a backend for:[/bold] \"{task}\"")
        console.print()

        sorted_backends = sorted(
            routing_decision.scores.items(), key=lambda x: x[1], reverse=True,
        )
        for i, (name, score) in enumerate(sorted_backends, 1):
            rec = " [green](recommended)[/green]" if name == routing_decision.backend_name else ""
            profile = profiles.get(name)
            cost_hint = ""
            if profile:
                avg = (profile.cost_per_1k_tokens["input"] + profile.cost_per_1k_tokens["output"]) / 2
                cost_hint = f"  ~${avg:.3f}/1k tokens"
            console.print(
                f"    [{i}] {_cb(name):<20}  score: {score:.2f}{cost_hint}{rec}"
            )

        console.print()
        choice = console.input(f"  Choose [1-{len(sorted_backends)}]: ").strip()

        try:
            idx = int(choice) - 1
            chosen_name = sorted_backends[idx][0]
            backend, selection_reason = await get_best_backend(chosen_name)
            user_specified = True
            routing_reason = "user picked"
        except (ValueError, IndexError):
            console.print("[dim]Invalid choice. Using recommended backend.[/dim]")

    # Show routing decision
    if config.display.show_routing_reason:
        _show_routing_line(
            backend.name,
            routing_reason,
            user_specified=user_specified,
            scores=routing_decision.scores if routing_decision else None,
            num_backends=len(backends_available),
            category=category.category,
        )

    # Check daily budget before executing (Feature 7)
    effective_budget = (
        (project_config.daily_budget if project_config and project_config.daily_budget else None)
        or config.daily_budget
    )
    daily_spent: float | None = None
    if effective_budget:
        since_dt, until_dt = get_date_range_for_period("today")
        daily_spent = get_total_cost(since=since_dt, until=until_dt)
        pct = (daily_spent / effective_budget) * 100

        if pct >= 100:
            console.print(
                f"  [red]\u26a0 Daily budget exhausted: ${daily_spent:.2f} / ${effective_budget:.2f}[/red]"
            )
            console.print("  [dim]Adjust daily_budget in config or .mdx.yaml to continue.[/dim]")
            raise typer.Exit(1)
        elif pct >= 80:
            console.print(
                f"  [yellow]\u26a0 Daily spend: ${daily_spent:.2f} / ${effective_budget:.2f} ({pct:.0f}%)[/yellow]"
            )

    cwd = Path.cwd()
    cb = get_circuit_breaker()

    # Stream output from backend
    full_output, duration = await stream_output(backend.execute(task, cwd))

    # Smart error detection and recovery (Feature 4)
    if "[MDx Code] Backend error" in full_output or "[MDx Code] Task timed out" in full_output:
        cb.record_failure(backend.name)
        exit_code = 1
        status_val = "error"

        # Classify the error for smart recovery
        output_lower = full_output.lower()
        if any(kw in output_lower for kw in ("rate limit", "429", "too many requests", "quota")):
            error_type = "rate_limit"
        elif any(kw in output_lower for kw in ("auth", "login", "credential", "token expired", "unauthorized")):
            error_type = "auth"
        elif "timed out" in output_lower:
            error_type = "timeout"
        elif any(kw in output_lower for kw in ("connection", "network", "dns", "unreachable")):
            error_type = "network"
        else:
            error_type = None

        # Show actionable guidance
        if error_type == "auth":
            console.print(
                f"  [yellow]\U0001f4a1 Session expired. Run `{backend.cli_command}` to re-authenticate.[/yellow]"
            )
        elif error_type == "timeout":
            console.print("  [yellow]\U0001f4a1 Task timed out. Try breaking it into smaller pieces,[/yellow]")
            console.print("  [yellow]   or use --backend for a faster alternative.[/yellow]")
        elif error_type == "network":
            console.print("  [yellow]\U0001f4a1 Network error. Check your connection and retry.[/yellow]")
        elif error_type == "rate_limit" and not user_specified:
            # Auto-fallback to next best backend
            console.print(
                f"  [yellow]\u26a1 {backend.name.title()} rate limited. Trying next backend...[/yellow]"
            )
            remaining = [n for n in routable_backends if n != backend.name]
            if remaining:
                fallback_decision = route_task(category, remaining, profiles, strategy)
                if fallback_decision:
                    fallback_backend, _ = await get_best_backend(fallback_decision.backend_name)
                    if fallback_backend:
                        _show_routing_line(
                            fallback_backend.name, "auto-fallback (rate limited)",
                            category=category.category,
                        )
                        full_output, duration = await stream_output(
                            fallback_backend.execute(task, cwd)
                        )
                        if "[MDx Code] Backend error" not in full_output:
                            cb.record_success(fallback_backend.name)
                            exit_code = 0
                            status_val = "success"
                            backend = fallback_backend
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

    # Timing intelligence (Feature 8)
    timing_insight = None
    try:
        from .governance.audit_trail import get_average_duration

        avg = get_average_duration(backend=backend.name, task_category=category.category)
        if avg and avg > 0:
            diff_pct = ((avg - duration) / avg) * 100
            if diff_pct > 10:
                timing_insight = f"{diff_pct:.0f}% faster than avg"
            elif diff_pct < -10:
                timing_insight = f"{abs(diff_pct):.0f}% slower than avg"
    except Exception:
        pass

    # Refresh daily spend for footer display
    if effective_budget and daily_spent is not None:
        # Re-query to include the cost we just recorded
        try:
            since_dt, until_dt = get_date_range_for_period("today")
            daily_spent = get_total_cost(since=since_dt, until=until_dt)
        except Exception:
            pass

    # Increment task count for onboarding tips
    if status_val == "success":
        config.task_count = (config.task_count or 0) + 1
        try:
            save_config(config)
        except Exception:
            pass  # Config save should never block the user

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
            timing_insight=timing_insight,
            daily_budget=effective_budget,
            daily_spent=daily_spent,
            task_count=config.task_count,
        )


@app.command()
def setup() -> None:
    """Detect and display available backends.

    Examples:
      mdx setup                     Show available backends
    """
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
    """Show backend health and circuit breaker status.

    Examples:
      mdx status                    Check all backend health
    """
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
    """Show spending dashboard.

    Examples:
      mdx cost                      Today's spending
      mdx cost --week               This week's costs
      mdx cost --month              Monthly overview
      mdx cost --since 2025-01-01   Custom date range
    """
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
    """Show recent audit entries with filtering, export, and verification.

    Examples:
      mdx audit                     Show last 10 entries
      mdx audit -n 50               Show last 50 entries
      mdx audit --verify            Verify chain hash integrity
      mdx audit --stats             Show audit statistics
      mdx audit --export csv        Export as CSV
      mdx audit --backend claude    Filter by backend
    """
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
        cat = entry.get("task_category", "general")
        icon = CATEGORY_ICONS.get(cat, "\U0001f4ac")
        task_display = f"{icon} {task}"
        dur = f"{entry.get('duration_seconds', 0):.1f}s"
        status_val = entry.get("status", "?")
        cost_val = entry.get("cost_usd")
        cost_str = f"${cost_val:.4f}" if cost_val else "-"
        status_style = "green" if status_val == "success" else "red"
        reason = entry.get("routing_reason") or entry.get("backend_selection_reason", "")

        table.add_row(
            ts, colored_backend(backend_name), task_display, dur,
            f"[{status_style}]{status_val}[/{status_style}]",
            cost_str, reason,
        )

    console.print(table)
    console.print()


@app.command()
def history(
    count: int = typer.Option(20, "--count", "-n", help="Number of entries"),
    search: Optional[str] = typer.Option(None, "--search", "-s", help="Search tasks"),
    backend_filter: Optional[str] = typer.Option(None, "--backend", "-b", help="Filter by backend"),
) -> None:
    """Show recent task history.

    Examples:
      mdx history                   Show last 20 tasks
      mdx history -n 50             Show last 50 tasks
      mdx history -s "login"        Search for tasks mentioning "login"
      mdx history -b claude         Show only Claude Code tasks
    """
    from .governance.audit_trail import read_recent_entries
    from .output.colors import colored_backend

    entries = read_recent_entries(count=min(count * 2, 100))

    # Filter out non-task entries (policy checks, reviews logged separately)
    entries = [e for e in entries if not e.get("task", "").startswith(("policy_check:", "adversarial_review:"))]

    if search:
        search_lower = search.lower()
        entries = [e for e in entries if search_lower in e.get("task", "").lower()]

    if backend_filter:
        entries = [e for e in entries if e.get("backend") == backend_filter]

    entries = entries[:count]

    if not entries:
        console.print("[dim]No task history found.[/dim]")
        if search:
            console.print(f"[dim]Try a different search term than '{search}'.[/dim]")
        return

    console.print()
    for entry in entries:
        ts = entry.get("timestamp", "")
        task = entry.get("task", "?")
        backend_name = entry.get("backend", "?")
        status_val = entry.get("status", "?")
        duration = entry.get("duration_seconds", 0)
        cost_val = entry.get("cost_usd")
        cat = entry.get("task_category", "general")
        icon = CATEGORY_ICONS.get(cat, "\U0001f4ac")
        status_mark = "[green]\u2713[/green]" if status_val == "success" else "[red]\u2717[/red]"
        cost_str = f"${cost_val:.4f}" if cost_val else ""

        # Truncate task
        if len(task) > 50:
            task = task[:47] + "..."

        # Format time as HH:MM
        time_str = ts[11:16] if ts else ""

        console.print(
            f"  {status_mark} {icon} [dim]{time_str}[/dim]  "
            f"{task:<52} {colored_backend(backend_name):>20}  "
            f"[dim]{duration:.1f}s  {cost_str}[/dim]"
        )

    console.print()
    console.print(f"  [dim]{len(entries)} tasks shown. Use --search to filter.[/dim]")
    console.print()


@app.command()
def summary(
    week: bool = typer.Option(False, "--week", "-w", help="Show weekly summary"),
) -> None:
    """Show your AI coding summary for today.

    Examples:
      mdx summary                   Today's summary
      mdx summary --week            This week's summary
    """
    from .governance.audit_trail import read_filtered_entries
    from .output.colors import colored_backend
    from .router.cost_tracker import get_date_range_for_period, get_savings, get_total_cost

    period = "week" if week else "today"
    since_dt, until_dt = get_date_range_for_period(period)
    period_label = "This Week" if week else "Today"

    # Get entries
    config = load_config()
    audit_dir = Path(config.audit.directory).expanduser()
    entries = read_filtered_entries(audit_dir, since=since_dt.strftime("%Y-%m-%d"))

    # Filter to actual tasks
    tasks = [e for e in entries if not e.get("task", "").startswith(("policy_check:", "adversarial_review:"))]
    reviews = [e for e in entries if e.get("task", "").startswith("adversarial_review:")]

    if not tasks and not reviews:
        console.print(f"[dim]No activity {period_label.lower()}. Run a task to get started.[/dim]")
        return

    # Compute stats
    total_tasks = len(tasks)
    successful = sum(1 for t in tasks if t.get("status") == "success")
    total_duration = sum(t.get("duration_seconds", 0) for t in tasks)
    backends_used = set(t.get("backend", "") for t in tasks if t.get("backend"))
    total_cost = get_total_cost(since=since_dt, until=until_dt)
    total_savings = get_savings(since=since_dt, until=until_dt)

    # Format duration
    minutes = int(total_duration // 60)
    seconds = int(total_duration % 60)

    console.print()
    console.print(f"  [bold]\U0001f4ca {period_label}: Your AI Coding Summary[/bold]")
    console.print()
    console.print(f"  Tasks completed: [bold]{successful}[/bold] / {total_tasks}")
    console.print(f"  Reviews run: [bold]{len(reviews)}[/bold]")
    console.print(f"  Total AI time: [bold]{minutes}m {seconds:02d}s[/bold]")
    console.print(f"  Backends used: {', '.join(colored_backend(b) for b in sorted(backends_used))}")
    console.print(f"  Total cost: [bold]${total_cost:.4f}[/bold]")
    if total_savings > 0:
        console.print(f"  Smart routing saved: [green]${total_savings:.4f}[/green]")
    console.print()

    # Top categories
    cat_count: dict[str, int] = {}
    for t in tasks:
        cat = t.get("task_category", "general")
        cat_count[cat] = cat_count.get(cat, 0) + 1

    if cat_count:
        console.print("  Task breakdown:")
        for cat, cnt in sorted(cat_count.items(), key=lambda x: x[1], reverse=True):
            icon = CATEGORY_ICONS.get(cat, "\U0001f4ac")
            console.print(f"    {icon} {cat.replace('_', ' '):<20} {cnt}")
        console.print()


@app.command(name="install-completion")
def install_completion(
    shell: str = typer.Option("auto", help="Shell: bash, zsh, fish"),
) -> None:
    """Install shell tab-completion for MDx Code.

    Examples:
      mdx install-completion            Auto-detect shell
      mdx install-completion --shell zsh   Force zsh
    """
    if shell == "auto":
        shell = os.environ.get("SHELL", "").split("/")[-1] or "bash"

    completion_script = {
        "zsh": 'eval "$(_MDX_COMPLETE=zsh_source mdx)"',
        "bash": 'eval "$(_MDX_COMPLETE=bash_source mdx)"',
        "fish": "_MDX_COMPLETE=fish_source mdx | source",
    }

    script = completion_script.get(shell)
    if not script:
        console.print(f"[red]Unsupported shell: {shell}. Use bash, zsh, or fish.[/red]")
        raise typer.Exit(1)

    rc_files = {"zsh": "~/.zshrc", "bash": "~/.bashrc", "fish": "~/.config/fish/config.fish"}
    rc_path = Path(rc_files[shell]).expanduser()

    marker = "# MDx Code completion"
    if rc_path.exists() and marker in rc_path.read_text():
        console.print("[green]Completion already installed.[/green]")
        return

    with open(rc_path, "a") as f:
        f.write(f"\n{marker}\n{script}\n")

    console.print(f"[green]\u2713 Completion installed for {shell}.[/green]")
    console.print(f"  Restart your shell or run: [bold]source {rc_files[shell]}[/bold]")


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
    """Replay the last task's output without re-executing.

    Examples:
      mdx replay                    Replay last task output
    """
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
    """Undo the last change made by a backend.

    Examples:
      mdx undo                      Revert last backend change
    """
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
    """Run adversarial multi-model code review.

    Examples:
      mdx review src/auth/          Review a directory
      mdx review --last             Review last MDx change
      mdx review --diff HEAD~1      Review a git diff
      mdx review --staged           Pre-commit review
    """
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
    """Update MDx Code and all installed backends.

    Examples:
      mdx update                    Update all backends
    """
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
    """Check files against active policies.

    Examples:
      mdx policy check src/auth.py          Check a single file
      mdx policy check src/ lib/            Check multiple paths
    """
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
    """Create a starter .mdxpolicy file in the current directory.

    Examples:
      mdx policy init               Create starter .mdxpolicy
    """
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
    """Show regulatory compliance mapping matrix.

    Examples:
      mdx compliance                View all compliance mappings
    """
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
    """Install MDx Code git pre-commit hook.

    Examples:
      mdx hook install              Install pre-commit hook
    """
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
    """Show available MCP servers and their status.

    Examples:
      mdx mcp status                Check MCP server availability
    """
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
    """Generate MCP server configuration for your client.

    Examples:
      mdx mcp config                Generate Claude Code config
      mdx mcp config --client cursor   Config for Cursor
      mdx mcp config --client codex    Config for Codex CLI
    """
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
