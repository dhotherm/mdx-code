"""Consistent color scheme for backend display."""

# Backend → Rich color name
BACKEND_COLORS: dict[str, str] = {
    "claude": "blue",
    "codex": "yellow",
    "gemini": "green",
    "opencode": "magenta",
}

# Backend → Rich style string (for inline use)
BACKEND_STYLES: dict[str, str] = {
    "claude": "bold blue",
    "codex": "bold yellow",
    "gemini": "bold green",
    "opencode": "bold magenta",
}


def colored_backend(name: str) -> str:
    """Return a Rich-formatted backend name with its assigned color."""
    color = BACKEND_COLORS.get(name, "white")
    display = name.title()
    return f"[{color}]{display}[/{color}]"
