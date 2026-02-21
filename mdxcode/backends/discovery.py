"""Auto-discover installed AI coding CLI backends."""

import shutil
from typing import Optional

from .base import BackendInfo
from .claude import ClaudeBackend


# Registry of all known backends, in preference order
BACKEND_CLASSES = [
    ClaudeBackend,
    # CodexBackend — Session 2
    # GeminiBackend — Session 2
]

# CLI command -> display name mapping for backends not yet implemented
KNOWN_CLIS = {
    "claude": "Claude Code",
    "codex": "Codex CLI",
    "gemini": "Gemini CLI",
}


async def discover_backends() -> list[BackendInfo]:
    """
    Discover all available backends.

    Checks PATH for: claude, codex, gemini
    For each found, checks version and auth status.
    Returns results sorted by preference: Claude > Codex > Gemini.
    """
    results: list[BackendInfo] = []

    # Check implemented backends
    for backend_cls in BACKEND_CLASSES:
        backend = backend_cls()
        info = await backend.get_info()
        results.append(info)

    # Check for CLIs we know about but haven't implemented yet
    for cli_name, display_name in KNOWN_CLIS.items():
        if any(r.name == cli_name for r in results):
            continue
        if shutil.which(cli_name):
            results.append(
                BackendInfo(
                    name=cli_name,
                    version="detected (adapter not yet implemented)",
                    authenticated=False,
                    healthy=False,
                )
            )

    return results


async def get_best_backend(preference: str = "auto") -> Optional[ClaudeBackend]:
    """
    Get the best available backend based on preference.

    For now, only Claude is implemented. Returns None if unavailable.
    """
    if preference in ("auto", "claude"):
        backend = ClaudeBackend()
        if await backend.is_available():
            return backend
    return None
