"""Tests for the circuit breaker pattern."""

import json
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from mdxcode.backends.circuit_breaker import CircuitBreaker, get_circuit_breaker, reset_circuit_breaker


class TestCircuitBreaker:
    """Tests for the CircuitBreaker class."""

    def test_initially_available(self):
        cb = CircuitBreaker()
        assert cb.is_available("claude") is True
        assert cb.is_open("claude") is False

    def test_available_after_few_failures(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure("claude")
        cb.record_failure("claude")
        assert cb.is_available("claude") is True
        assert cb.get_failure_count("claude") == 2

    def test_circuit_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure("claude")
        cb.record_failure("claude")
        cb.record_failure("claude")
        assert cb.is_open("claude") is True
        assert cb.is_available("claude") is False
        assert cb.get_failure_count("claude") == 3

    def test_success_resets_failures(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure("claude")
        cb.record_failure("claude")
        cb.record_success("claude")
        assert cb.get_failure_count("claude") == 0
        assert cb.is_available("claude") is True

    def test_success_closes_open_circuit(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=300.0)
        for _ in range(3):
            cb.record_failure("claude")
        assert cb.is_open("claude") is True

        cb.record_success("claude")
        assert cb.is_open("claude") is False
        assert cb.is_available("claude") is True

    def test_half_open_after_recovery_timeout(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1.0)
        for _ in range(3):
            cb.record_failure("claude")

        assert cb.is_open("claude") is True
        assert cb.is_half_open("claude") is False

        # Simulate time passing
        cb.circuit_open_since["claude"] = time.monotonic() - 2.0

        assert cb.is_half_open("claude") is True
        assert cb.is_available("claude") is True  # half-open allows one attempt

    def test_failure_after_half_open_stays_open(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=1.0)
        for _ in range(3):
            cb.record_failure("claude")

        # Simulate recovery timeout elapsed
        cb.circuit_open_since["claude"] = time.monotonic() - 2.0
        assert cb.is_half_open("claude") is True

        # Another failure resets the timer
        cb.record_failure("claude")
        assert cb.is_open("claude") is True
        assert cb.time_until_retry("claude") > 0

    def test_independent_backends(self):
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure("codex")

        assert cb.is_open("codex") is True
        assert cb.is_available("claude") is True
        assert cb.is_available("gemini") is True

    def test_time_until_retry(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=300.0)
        for _ in range(3):
            cb.record_failure("claude")

        remaining = cb.time_until_retry("claude")
        assert 299.0 <= remaining <= 300.0

    def test_time_until_retry_no_open_circuit(self):
        cb = CircuitBreaker()
        assert cb.time_until_retry("claude") == 0.0


class TestGlobalCircuitBreaker:
    """Tests for the global singleton circuit breaker."""

    def setup_method(self):
        reset_circuit_breaker()

    def test_singleton(self):
        cb1 = get_circuit_breaker()
        cb2 = get_circuit_breaker()
        assert cb1 is cb2

    def test_reset(self):
        cb1 = get_circuit_breaker()
        cb1.record_failure("claude")
        reset_circuit_breaker()
        cb2 = get_circuit_breaker()
        assert cb2.get_failure_count("claude") == 0

    def teardown_method(self):
        reset_circuit_breaker()


class TestCircuitBreakerPersistence:
    """Tests for circuit breaker disk persistence."""

    def test_saves_state_on_failure(self, tmp_path):
        state_file = tmp_path / "cb_state.json"
        cb = CircuitBreaker(state_file=state_file)
        cb.record_failure("gemini")
        cb.record_failure("gemini")

        assert state_file.exists()
        data = json.loads(state_file.read_text())
        assert "gemini" in data
        assert data["gemini"]["failures"] == 2
        assert data["gemini"]["state"] == "closed"

    def test_saves_open_state(self, tmp_path):
        state_file = tmp_path / "cb_state.json"
        cb = CircuitBreaker(failure_threshold=2, state_file=state_file)
        cb.record_failure("gemini")
        cb.record_failure("gemini")

        data = json.loads(state_file.read_text())
        assert data["gemini"]["state"] == "open"
        assert data["gemini"]["last_failure"] is not None

    def test_loads_state_on_init(self, tmp_path):
        state_file = tmp_path / "cb_state.json"

        # Create and save state
        cb1 = CircuitBreaker(failure_threshold=3, state_file=state_file)
        cb1.record_failure("gemini")
        cb1.record_failure("gemini")

        # New instance should load persisted state
        cb2 = CircuitBreaker(failure_threshold=3, state_file=state_file)
        assert cb2.get_failure_count("gemini") == 2

    def test_loads_open_circuit_across_processes(self, tmp_path):
        state_file = tmp_path / "cb_state.json"

        # Create open circuit
        cb1 = CircuitBreaker(failure_threshold=3, recovery_timeout=300.0, state_file=state_file)
        for _ in range(3):
            cb1.record_failure("gemini")
        assert cb1.is_open("gemini") is True

        # New instance should see open circuit
        cb2 = CircuitBreaker(failure_threshold=3, recovery_timeout=300.0, state_file=state_file)
        assert cb2.is_open("gemini") is True
        assert cb2.get_failure_count("gemini") == 3

    def test_success_clears_persisted_state(self, tmp_path):
        state_file = tmp_path / "cb_state.json"

        cb = CircuitBreaker(failure_threshold=3, state_file=state_file)
        for _ in range(3):
            cb.record_failure("gemini")
        cb.record_success("gemini")

        data = json.loads(state_file.read_text())
        assert "gemini" not in data  # Success with 0 failures removes entry

    def test_corrupted_state_file_handled(self, tmp_path):
        state_file = tmp_path / "cb_state.json"
        state_file.write_text("not valid json {{{")

        # Should not raise, just start fresh
        cb = CircuitBreaker(state_file=state_file)
        assert cb.get_failure_count("gemini") == 0

    def test_no_persistence_without_state_file(self):
        cb = CircuitBreaker()  # No state_file
        cb.record_failure("claude")
        cb.record_failure("claude")
        assert cb.get_failure_count("claude") == 2
        # No file should be created — state_file is None

    def test_expired_circuit_not_loaded_as_open(self, tmp_path):
        state_file = tmp_path / "cb_state.json"

        # Write state with a last_failure far in the past
        from datetime import datetime, timezone, timedelta
        old_time = (datetime.now(timezone.utc) - timedelta(seconds=600)).isoformat()
        data = {
            "gemini": {
                "failures": 3,
                "last_failure": old_time,
                "state": "open",
            }
        }
        state_file.write_text(json.dumps(data))

        # With 300s recovery timeout, 600s ago should be expired
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=300.0, state_file=state_file)
        assert cb.is_open("gemini") is False
        assert cb.get_failure_count("gemini") == 3
