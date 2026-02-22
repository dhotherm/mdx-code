"""Circuit breaker pattern for backend resilience."""

import json
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

STATE_FILE = Path.home() / ".mdx" / "circuit_breaker.json"


@dataclass
class CircuitBreaker:
    """Track backend failures and auto-disable unhealthy backends."""

    failure_threshold: int = 3
    recovery_timeout: float = 300.0  # seconds before trying again

    # Path to state file. None disables persistence (for testing).
    state_file: Path | None = None

    # Per-backend state
    failure_counts: dict[str, int] = field(default_factory=dict)
    circuit_open_since: dict[str, float] = field(default_factory=dict)

    # Persisted wall-clock timestamps (ISO format) for cross-process state
    _persisted_open_since: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._load_state()

    def _load_state(self) -> None:
        """Load persisted circuit breaker state from disk."""
        if self.state_file is None:
            return
        try:
            if not self.state_file.exists():
                return
            data = json.loads(self.state_file.read_text())
            now = time.monotonic()
            wall_now = datetime.now(timezone.utc)
            for backend_name, info in data.items():
                failures = info.get("failures", 0)
                state = info.get("state", "closed")
                last_failure_iso = info.get("last_failure")

                self.failure_counts[backend_name] = failures

                if state == "open" and last_failure_iso:
                    # Convert wall-clock timestamp to monotonic offset
                    last_failure_dt = datetime.fromisoformat(last_failure_iso)
                    elapsed_wall = (wall_now - last_failure_dt).total_seconds()
                    if elapsed_wall < self.recovery_timeout:
                        # Circuit is still open — reconstruct monotonic timestamp
                        self.circuit_open_since[backend_name] = now - elapsed_wall
                        self._persisted_open_since[backend_name] = last_failure_iso
                    # else: recovery period already elapsed, leave circuit closed
        except (json.JSONDecodeError, OSError, ValueError, KeyError, TypeError):
            pass  # Corrupted state file — start fresh

    def _save_state(self) -> None:
        """Persist circuit breaker state to disk atomically."""
        if self.state_file is None:
            return
        try:
            data: dict[str, dict] = {}
            all_backends = set(self.failure_counts.keys()) | set(self.circuit_open_since.keys())
            now = time.monotonic()
            wall_now = datetime.now(timezone.utc)

            for backend_name in all_backends:
                failures = self.failure_counts.get(backend_name, 0)
                is_open = backend_name in self.circuit_open_since

                if is_open:
                    elapsed = now - self.circuit_open_since[backend_name]
                    last_failure_wall = wall_now.timestamp() - elapsed
                    last_failure_iso = datetime.fromtimestamp(
                        last_failure_wall, tz=timezone.utc
                    ).isoformat()
                    data[backend_name] = {
                        "failures": failures,
                        "last_failure": last_failure_iso,
                        "state": "open",
                    }
                elif failures > 0:
                    data[backend_name] = {
                        "failures": failures,
                        "last_failure": None,
                        "state": "closed",
                    }

            self.state_file.parent.mkdir(parents=True, exist_ok=True)

            # Atomic write via temp file + rename
            fd, tmp_path = tempfile.mkstemp(dir=str(self.state_file.parent), suffix=".tmp")
            try:
                with open(fd, "w") as f:
                    json.dump(data, f, indent=2)
                Path(tmp_path).replace(self.state_file)
            except Exception:
                Path(tmp_path).unlink(missing_ok=True)
                raise
        except (OSError, TypeError):
            pass  # Persistence should never block the user

    def record_failure(self, backend_name: str) -> None:
        """Record a backend failure. Opens circuit after threshold reached."""
        self.failure_counts[backend_name] = self.failure_counts.get(backend_name, 0) + 1
        if self.failure_counts[backend_name] >= self.failure_threshold:
            self.circuit_open_since[backend_name] = time.monotonic()
        self._save_state()

    def record_success(self, backend_name: str) -> None:
        """Record a backend success. Closes circuit and resets failure count."""
        self.failure_counts[backend_name] = 0
        self.circuit_open_since.pop(backend_name, None)
        self._save_state()

    def is_available(self, backend_name: str) -> bool:
        """Check if a backend is available (circuit not open, or recovery period elapsed)."""
        if backend_name not in self.circuit_open_since:
            return True

        elapsed = time.monotonic() - self.circuit_open_since[backend_name]
        if elapsed >= self.recovery_timeout:
            # Half-open: allow one attempt
            return True

        return False

    def is_half_open(self, backend_name: str) -> bool:
        """Check if a backend is in half-open state (recovery period elapsed but not yet proven)."""
        if backend_name not in self.circuit_open_since:
            return False

        elapsed = time.monotonic() - self.circuit_open_since[backend_name]
        return elapsed >= self.recovery_timeout

    def is_open(self, backend_name: str) -> bool:
        """Check if circuit is open (backend disabled)."""
        if backend_name not in self.circuit_open_since:
            return False

        elapsed = time.monotonic() - self.circuit_open_since[backend_name]
        return elapsed < self.recovery_timeout

    def time_until_retry(self, backend_name: str) -> float:
        """Get seconds until circuit half-opens for a backend. Returns 0 if not open."""
        if backend_name not in self.circuit_open_since:
            return 0.0

        elapsed = time.monotonic() - self.circuit_open_since[backend_name]
        remaining = self.recovery_timeout - elapsed
        return max(0.0, remaining)

    def get_failure_count(self, backend_name: str) -> int:
        """Get the current failure count for a backend."""
        return self.failure_counts.get(backend_name, 0)


# Module-level singleton so circuit state persists within a process
_circuit_breaker: CircuitBreaker | None = None


def get_circuit_breaker() -> CircuitBreaker:
    """Get the global circuit breaker instance (with disk persistence)."""
    global _circuit_breaker
    if _circuit_breaker is None:
        _circuit_breaker = CircuitBreaker(state_file=STATE_FILE)
    return _circuit_breaker


def reset_circuit_breaker() -> None:
    """Reset the global circuit breaker (for testing)."""
    global _circuit_breaker
    if _circuit_breaker is not None and _circuit_breaker.state_file is not None:
        try:
            _circuit_breaker.state_file.unlink(missing_ok=True)
        except OSError:
            pass
    _circuit_breaker = None
