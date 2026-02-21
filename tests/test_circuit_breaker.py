"""Tests for the circuit breaker pattern."""

import time
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
