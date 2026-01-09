"""
Authentication

Getting authenticated with LLM providers.

For Claude, we support:
1. Environment variable (ANTHROPIC_API_KEY)
2. OAuth flow (opens browser, like Claude Code does)
3. Cached credentials from previous auth

The goal: make it as easy as Claude Code.
Run `mdxcode auth claude`, browser opens, you're authenticated.
"""

import json
import os
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console


# Where we store cached credentials
CREDENTIALS_DIR = Path.home() / ".mdxcode"
CREDENTIALS_FILE = CREDENTIALS_DIR / "credentials.json"


def get_cached_credentials(provider: str) -> Optional[Dict[str, Any]]:
    """Get cached credentials for a provider."""
    if not CREDENTIALS_FILE.exists():
        return None
    
    try:
        data = json.loads(CREDENTIALS_FILE.read_text())
        return data.get(provider)
    except Exception:
        return None


def save_credentials(provider: str, credentials: Dict[str, Any]):
    """Save credentials for a provider."""
    CREDENTIALS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Load existing credentials
    existing = {}
    if CREDENTIALS_FILE.exists():
        try:
            existing = json.loads(CREDENTIALS_FILE.read_text())
        except Exception:
            pass
    
    # Update with new credentials
    existing[provider] = credentials
    
    # Save (with restricted permissions)
    CREDENTIALS_FILE.write_text(json.dumps(existing, indent=2))
    CREDENTIALS_FILE.chmod(0o600)  # Owner read/write only


def get_authenticated_providers() -> List[str]:
    """Get list of authenticated providers."""
    providers = []
    
    # Check environment variables
    if os.getenv("ANTHROPIC_API_KEY"):
        providers.append("claude (env)")
    if os.getenv("OPENAI_API_KEY"):
        providers.append("openai (env)")
    if os.getenv("AWS_ACCESS_KEY_ID"):
        providers.append("bedrock (env)")
    
    # Check cached credentials
    if CREDENTIALS_FILE.exists():
        try:
            data = json.loads(CREDENTIALS_FILE.read_text())
            for provider in data:
                if provider not in [p.split(" ")[0] for p in providers]:
                    providers.append(f"{provider} (cached)")
        except Exception:
            pass
    
    return providers


async def authenticate(provider: str, console: Console) -> bool:
    """
    Authenticate with a provider.
    
    For Claude, this opens the browser for OAuth.
    For others, it prompts for API key (for now).
    """
    if provider == "claude":
        return await _authenticate_claude(console)
    elif provider == "openai":
        return await _authenticate_openai(console)
    elif provider == "bedrock":
        return await _authenticate_bedrock(console)
    elif provider == "vertex":
        return await _authenticate_vertex(console)
    else:
        console.print(f"[red]Unknown provider: {provider}[/red]")
        return False


async def _authenticate_claude(console: Console) -> bool:
    """
    Authenticate with Anthropic.
    
    Options:
    1. If ANTHROPIC_API_KEY is set, use that
    2. Otherwise, prompt for API key
    
    (Full OAuth flow would require Anthropic to support it -
    for now we do API key based auth)
    """
    # Check if already authenticated via env
    if os.getenv("ANTHROPIC_API_KEY"):
        console.print("[green]Already authenticated via ANTHROPIC_API_KEY[/green]")
        return True
    
    # Check cached credentials
    cached = get_cached_credentials("claude")
    if cached:
        console.print("[green]Found cached credentials[/green]")
        
        # Verify they still work
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=cached["api_key"])
            # Quick test call
            client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=10,
                messages=[{"role": "user", "content": "Hi"}]
            )
            console.print("[green]Credentials verified[/green]")
            return True
        except Exception as e:
            console.print(f"[yellow]Cached credentials invalid: {e}[/yellow]")
    
    # Prompt for API key
    console.print("\n[bold]Anthropic API Key Authentication[/bold]\n")
    console.print("Get your API key from: https://console.anthropic.com/\n")
    
    api_key = console.input("[bold]Enter your API key:[/bold] ").strip()
    
    if not api_key:
        console.print("[red]No API key provided[/red]")
        return False
    
    # Verify the key works
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=10,
            messages=[{"role": "user", "content": "Hi"}]
        )
    except Exception as e:
        console.print(f"[red]Invalid API key: {e}[/red]")
        return False
    
    # Save credentials
    save_credentials("claude", {"api_key": api_key})
    console.print("[green]Credentials saved[/green]")
    
    return True


async def _authenticate_openai(console: Console) -> bool:
    """Authenticate with OpenAI."""
    # Check if already authenticated via env
    if os.getenv("OPENAI_API_KEY"):
        console.print("[green]Already authenticated via OPENAI_API_KEY[/green]")
        return True
    
    console.print("\n[bold]OpenAI API Key Authentication[/bold]\n")
    console.print("Get your API key from: https://platform.openai.com/api-keys\n")
    
    api_key = console.input("[bold]Enter your API key:[/bold] ").strip()
    
    if not api_key:
        console.print("[red]No API key provided[/red]")
        return False
    
    # Save credentials (we'll verify when actually used)
    save_credentials("openai", {"api_key": api_key})
    console.print("[green]Credentials saved[/green]")
    
    return True


async def _authenticate_bedrock(console: Console) -> bool:
    """Authenticate with AWS Bedrock."""
    console.print("\n[bold]AWS Bedrock Authentication[/bold]\n")
    console.print("Bedrock uses AWS credentials (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)")
    console.print("Configure via: aws configure\n")
    
    if os.getenv("AWS_ACCESS_KEY_ID"):
        console.print("[green]AWS credentials found in environment[/green]")
        return True
    
    console.print("[yellow]No AWS credentials found[/yellow]")
    console.print("Run 'aws configure' to set up credentials")
    return False


async def _authenticate_vertex(console: Console) -> bool:
    """Authenticate with Google Vertex AI."""
    console.print("\n[bold]Google Vertex AI Authentication[/bold]\n")
    console.print("Vertex AI uses Google Cloud credentials")
    console.print("Configure via: gcloud auth application-default login\n")
    
    # Check for application default credentials
    creds_path = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
    if creds_path.exists():
        console.print("[green]Google Cloud credentials found[/green]")
        return True
    
    console.print("[yellow]No Google Cloud credentials found[/yellow]")
    console.print("Run 'gcloud auth application-default login' to set up credentials")
    return False


__all__ = [
    "authenticate",
    "get_cached_credentials",
    "save_credentials",
    "get_authenticated_providers",
]
