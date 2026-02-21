"""Circuit breaker pattern for backend resilience."""

import time
from dataclasses import dataclass, field


@dataclass
class CircuitBreaker:
    """Track backend failures and auto-disable unhealthy backends."""

    failure_threshold: int = 3
    recovery_timeout: float = 300.0  # seconds before trying again

    # Per-backend state
    failure_counts: dict[str, int] = field(default_factory=dict)
    circuit_open_since: dict[str, float] = field(default_factory=dict)

    def record_failure(self, backend_name: str) -> None:
        """Record a backend failure. Opens circuit after threshold reached."""
        self.failure_counts[backend_name] = self.failure_counts.get(backend_name, 0) + 1
        if self.failure_counts[backend_name] >= self.failure_threshold:
            self.circuit_open_since[backend_name] = time.monotonic()

    def record_success(self, backend_name: str) -> None:
        """Record a backend success. Closes circuit and resets failure count."""
        self.failure_counts[backend_name] = 0
        self.circuit_open_since.pop(backend_name, None)

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
    """Get the global circuit breaker instance."""
    global _circuit_breaker
    if _circuit_breaker is None:
        _circuit_breaker = CircuitBreaker()
    return _circuit_breaker


def reset_circuit_breaker() -> None:
    """Reset the global circuit breaker (for testing)."""
    global _circuit_breaker
    _circuit_breaker = None
