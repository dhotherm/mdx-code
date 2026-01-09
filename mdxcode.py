#!/usr/bin/env python3
"""
MDx Code - AI-Native Engineering Companion

Built for builders. Designed for regulated environments.
Own the orchestration. Swap the models. Keep the governance.

This is what happens when you realize Claude Code's architecture
is embarrassingly simple... and decide to build your own.

Author: MD
License: MIT
"""

import asyncio
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from core.agent_loop import AgentLoop
from core.context_loader import load_mdxcode_context
from core.session import Session
from governance.audit import AuditLogger
from models.router import ModelRouter

# The CLI app
app = typer.Typer(
    name="mdxcode",
    help="AI-Native Engineering Companion. Built for builders.",
    add_completion=False,
)

console = Console()


def show_banner():
    """Show the MDx Code banner. First impressions matter."""
    banner = Text()
    banner.append("MDx Code\n", style="bold cyan")
    banner.append("AI-Native Engineering Companion\n\n", style="dim")
    banner.append("Built for builders. Designed for regulated environments.\n", style="italic")
    
    console.print(Panel(
        banner,
        border_style="cyan",
        padding=(1, 2),
    ))


@app.command()
def main(
    task: str = typer.Argument(None, help="What do you want to work on?"),
    model: str = typer.Option("claude", "--model", "-m", help="Model to use: claude, gpt, bedrock"),
    profile: str = typer.Option("standard", "--profile", "-p", help="Regulatory profile: standard, financial_services, healthcare"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would happen without executing"),
):
    """
    Run MDx Code on a task.
    
    Examples:
        mdxcode "Fix the bug in auth.py"
        mdxcode "Add tests for the claims module" --model gpt
        mdxcode "Scan for security vulnerabilities" --profile financial_services
    """
    show_banner()
    
    # Load project context if MDXCODE.md exists
    context = load_mdxcode_context()
    if context:
        console.print(f"[dim]Loaded context from MDXCODE.md[/dim]")
        if context.project_name:
            console.print(f"[dim]Project: {context.project_name} ({context.domain})[/dim]")
    
    # If no task provided, enter interactive mode
    if not task:
        console.print("\n[cyan]No task provided. Entering interactive mode...[/cyan]\n")
        task = console.input("[bold]What do you want to work on?[/bold] → ")
        if not task.strip():
            console.print("[dim]Nothing to do. Exiting.[/dim]")
            raise typer.Exit()
    
    # Initialize the session
    session = Session(
        model=model,
        profile=profile,
        context=context,
        verbose=verbose,
        dry_run=dry_run,
    )
    
    # Initialize audit logging
    audit = AuditLogger(session)
    audit.log_session_start(task)
    
    # Initialize model router
    router = ModelRouter(model)
    
    # Initialize and run the agent loop
    # This is where the magic happens.
    # AI thinks → acts → observes → repeats.
    agent = AgentLoop(
        session=session,
        router=router,
        audit=audit,
        console=console,
    )
    
    try:
        asyncio.run(agent.run(task))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted. Saving session state...[/yellow]")
        audit.log_session_end("interrupted")
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        audit.log_session_end("error", str(e))
        raise typer.Exit(1)
    else:
        audit.log_session_end("success")
    
    console.print("\n[dim]Session complete. Audit log saved.[/dim]")


@app.command()
def auth(
    provider: str = typer.Argument(..., help="Provider to authenticate: claude, openai, bedrock"),
):
    """
    Authenticate with an LLM provider.
    
    Examples:
        mdxcode auth claude
        mdxcode auth openai
    """
    from models.auth import authenticate
    
    show_banner()
    console.print(f"\n[cyan]Authenticating with {provider}...[/cyan]\n")
    
    success = asyncio.run(authenticate(provider, console))
    
    if success:
        console.print(f"\n[green]✓ Authenticated with {provider}[/green]")
    else:
        console.print(f"\n[red]✗ Authentication failed[/red]")
        raise typer.Exit(1)


@app.command()
def security(
    action: str = typer.Argument("scan", help="Action: scan, fix, learn"),
    path: str = typer.Option(".", "--path", "-p", help="Path to scan"),
    auto_fix: bool = typer.Option(False, "--auto-fix", help="Automatically apply fixes"),
):
    """
    Security agent for vulnerability scanning and remediation.
    
    Examples:
        mdxcode security scan
        mdxcode security scan --path src/
        mdxcode security fix --auto-fix
    """
    from governance.security_agent import SecurityAgent
    
    show_banner()
    console.print(f"\n[cyan]MDx Code Security Agent[/cyan]\n")
    
    agent = SecurityAgent(console)
    
    if action == "scan":
        asyncio.run(agent.scan(path))
    elif action == "fix":
        asyncio.run(agent.fix(path, auto_fix=auto_fix))
    elif action == "learn":
        asyncio.run(agent.learn())
    else:
        console.print(f"[red]Unknown action: {action}[/red]")
        raise typer.Exit(1)


@app.command()
def init():
    """
    Initialize MDx Code in the current directory.
    
    Creates a starter MDXCODE.md file with sensible defaults.
    """
    show_banner()
    
    mdxcode_path = Path("MDXCODE.md")
    
    if mdxcode_path.exists():
        console.print("[yellow]MDXCODE.md already exists. Skipping.[/yellow]")
        raise typer.Exit()
    
    from core.context_loader import create_starter_mdxcode
    
    create_starter_mdxcode(mdxcode_path)
    console.print("[green]✓ Created MDXCODE.md[/green]")
    console.print("[dim]Edit this file to customize MDx Code for your project.[/dim]")


@app.command()
def status():
    """
    Show current MDx Code status and configuration.
    """
    show_banner()
    
    from core.context_loader import load_mdxcode_context
    from models.auth import get_authenticated_providers
    
    context = load_mdxcode_context()
    providers = get_authenticated_providers()
    
    console.print("\n[bold]Configuration[/bold]")
    console.print(f"  MDXCODE.md: {'[green]Found[/green]' if context else '[yellow]Not found[/yellow]'}")
    if context:
        console.print(f"  Project: {context.project_name or 'Not set'}")
        console.print(f"  Domain: {context.domain or 'Not set'}")
        console.print(f"  Profile: {context.regulatory_profile or 'standard'}")
    
    console.print("\n[bold]Authenticated Providers[/bold]")
    if providers:
        for provider in providers:
            console.print(f"  [green]✓[/green] {provider}")
    else:
        console.print("  [yellow]None. Run 'mdxcode auth <provider>' to authenticate.[/yellow]")


def run():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    run()
