"""Auto-discover installed AI coding CLI backends."""

import json
import time
from pathlib import Path
from typing import Optional

from .base import Backend, BackendInfo
from .circuit_breaker import get_circuit_breaker
from .claude import ClaudeBackend
from .codex import CodexBackend
from .gemini import GeminiBackend
from .opencode import OpenCodeBackend

from ..config import MDX_DIR


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

# File-based discovery cache — avoids running which + --version on every invocation
BACKEND_CACHE_PATH = MDX_DIR / "backend_cache.json"
CACHE_MAX_AGE_SECONDS = 300  # 5 minutes


async def discover_backends(force: bool = False) -> list[BackendInfo]:
    """
    Discover all available backends with file-based caching.

    Checks PATH for: claude, codex, gemini, opencode
    For each found, checks version and auth status.
    Returns results sorted by preference: Claude > Codex > Gemini > OpenCode.

    Results are cached to disk for 5 minutes. Use force=True to bypass cache
    (e.g., from `mdx setup`).
    """
    if not force:
        cached = _load_discovery_cache()
        if cached is not None:
            return cached

    # Full discovery (subprocess calls for each backend)
    results: list[BackendInfo] = []
    for backend_cls in BACKEND_CLASSES:
        backend = backend_cls()
        info = await backend.get_info()
        results.append(info)

    _save_discovery_cache(results)
    return results


def _load_discovery_cache() -> Optional[list[BackendInfo]]:
    """Load cached discovery results if fresh enough."""
    if not BACKEND_CACHE_PATH.exists():
        return None
    try:
        cache = json.loads(BACKEND_CACHE_PATH.read_text())
        cached_at = cache.get("timestamp", 0)
        if time.time() - cached_at >= CACHE_MAX_AGE_SECONDS:
            return None
        return [BackendInfo(**b) for b in cache["backends"]]
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def invalidate_discovery_cache() -> None:
    """Clear the discovery cache. Used by tests and `mdx setup`."""
    if BACKEND_CACHE_PATH.exists():
        try:
            BACKEND_CACHE_PATH.unlink()
        except OSError:
            pass


def _save_discovery_cache(backends: list[BackendInfo]) -> None:
    """Save discovery results to disk cache."""
    try:
        BACKEND_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        cache = {
            "timestamp": time.time(),
            "backends": [
                b.model_dump() if hasattr(b, "model_dump") else b.__dict__
                for b in backends
            ],
        }
        BACKEND_CACHE_PATH.write_text(json.dumps(cache))
    except Exception:
        pass  # Cache write failure should never block


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
