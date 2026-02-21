"""Auto-discover installed AI coding CLI backends."""

from typing import Optional

from .base import Backend, BackendInfo
from .circuit_breaker import get_circuit_breaker
from .claude import ClaudeBackend
from .codex import CodexBackend
from .gemini import GeminiBackend
from .opencode import OpenCodeBackend


# Registry of all known backends, in preference order
BACKEND_CLASSES: list[type[Backend]] = [
    ClaudeBackend,
    CodexBackend,
    GeminiBackend,
    OpenCodeBackend,
]

# CLI command -> display name mapping (for reference/display purposes)
KNOWN_CLIS = {
    "claude": "Claude Code",
    "codex": "Codex CLI",
    "gemini": "Gemini CLI",
    "opencode": "OpenCode",
}

# Install instructions per backend
INSTALL_INSTRUCTIONS = {
    "claude": "Install: npm install -g @anthropic-ai/claude-code",
    "codex": "Install: npm install -g @openai/codex",
    "gemini": "Install: npm install -g @google/gemini-cli  (see https://github.com/google-gemini/gemini-cli)",
    "opencode": "Install: go install github.com/opencode-ai/opencode@latest",
}


async def discover_backends() -> list[BackendInfo]:
    """
    Discover all available backends.

    Checks PATH for: claude, codex, gemini, opencode
    For each found, checks version and auth status.
    Returns results sorted by preference: Claude > Codex > Gemini > OpenCode.
    """
    results: list[BackendInfo] = []

    for backend_cls in BACKEND_CLASSES:
        backend = backend_cls()
        info = await backend.get_info()
        results.append(info)

    return results


def _get_backend_instance(name: str) -> Optional[Backend]:
    """Get a backend instance by name."""
    for backend_cls in BACKEND_CLASSES:
        instance = backend_cls()
        if instance.name == name:
            return instance
    return None


async def get_best_backend(
    preference: str = "auto",
    circuit_breaker_check: bool = True,
) -> tuple[Optional[Backend], str]:
    """
    Get the best available backend based on preference.

    Returns (backend, selection_reason) where selection_reason is one of:
    - "user_specified": user explicitly chose this backend
    - "auto_default": auto-selected as first available
    - "circuit_breaker_fallback": preferred backend had open circuit, fell back

    Returns (None, reason) if no backend is available.
    """
    cb = get_circuit_breaker() if circuit_breaker_check else None

    # User explicitly requested a backend
    if preference not in ("auto",):
        backend = _get_backend_instance(preference)
        if backend is None:
            return None, "user_specified"
        if not await backend.is_available():
            return None, "user_specified"
        # OpenCode can't execute
        if preference == "opencode":
            return None, "user_specified"
        if cb and not cb.is_available(preference):
            return None, "circuit_breaker_fallback"
        return backend, "user_specified"

    # Auto mode: try each in preference order (skip opencode — it can't execute)
    fallback_reason = "auto_default"
    for backend_cls in BACKEND_CLASSES:
        backend = backend_cls()
        if backend.name == "opencode":
            continue
        if not await backend.is_available():
            continue
        if cb and not cb.is_available(backend.name):
            fallback_reason = "circuit_breaker_fallback"
            continue
        return backend, fallback_reason

    return None, fallback_reason
