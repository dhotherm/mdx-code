"""Tests for backend discovery."""

from unittest.mock import AsyncMock, patch

import pytest

from mdxcode.backends.base import BackendInfo
from mdxcode.backends.circuit_breaker import reset_circuit_breaker
from mdxcode.backends.claude import ClaudeBackend
from mdxcode.backends.codex import CodexBackend
from mdxcode.backends.gemini import GeminiBackend
from mdxcode.backends.opencode import OpenCodeBackend
from mdxcode.backends.discovery import (
    discover_backends,
    get_best_backend,
    invalidate_discovery_cache,
)


class TestClaudeBackend:
    """Tests for the Claude Code backend adapter."""

    @pytest.mark.asyncio
    async def test_available_when_in_path(self):
        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            backend = ClaudeBackend()
            assert await backend.is_available() is True

    @pytest.mark.asyncio
    async def test_unavailable_when_not_in_path(self):
        with patch("shutil.which", return_value=None):
            backend = ClaudeBackend()
            assert await backend.is_available() is False

    def test_name(self):
        backend = ClaudeBackend()
        assert backend.name == "claude"

    def test_cli_command(self):
        backend = ClaudeBackend()
        assert backend.cli_command == "claude"

    @pytest.mark.asyncio
    async def test_get_info_not_installed(self):
        with patch("shutil.which", return_value=None):
            backend = ClaudeBackend()
            info = await backend.get_info()
            assert info.name == "claude"
            assert info.healthy is False
            assert info.authenticated is False
            assert info.version == "not installed"

    def test_parse_json_output_valid(self):
        backend = ClaudeBackend()
        output = '{"model": "claude-sonnet-4-5-20250514", "cost_usd": 0.04, "usage": {"input_tokens": 1000, "output_tokens": 500}}'
        model, cost, t_in, t_out = backend._parse_json_output(output)
        assert model == "claude-sonnet-4-5-20250514"
        assert cost == 0.04
        assert t_in == 1000
        assert t_out == 500

    def test_parse_json_output_invalid(self):
        backend = ClaudeBackend()
        model, cost, t_in, t_out = backend._parse_json_output("not json at all")
        assert model is None
        assert cost is None
        assert t_in is None
        assert t_out is None

    def test_parse_json_output_partial(self):
        backend = ClaudeBackend()
        output = '{"model": "claude-sonnet-4-5-20250514"}'
        model, cost, t_in, t_out = backend._parse_json_output(output)
        assert model == "claude-sonnet-4-5-20250514"
        assert cost is None


class TestDiscovery:
    """Tests for backend discovery."""

    def _make_info(self, name, healthy=True):
        return BackendInfo(
            name=name,
            version="1.0.0" if healthy else "not installed",
            authenticated=healthy,
            healthy=healthy,
        )

    @pytest.mark.asyncio
    async def test_discovers_claude(self):
        with (
            patch.object(
                ClaudeBackend,
                "get_info",
                new_callable=AsyncMock,
                return_value=self._make_info("claude"),
            ),
            patch.object(
                CodexBackend,
                "get_info",
                new_callable=AsyncMock,
                return_value=self._make_info("codex", healthy=False),
            ),
            patch.object(
                GeminiBackend,
                "get_info",
                new_callable=AsyncMock,
                return_value=self._make_info("gemini", healthy=False),
            ),
            patch.object(
                OpenCodeBackend,
                "get_info",
                new_callable=AsyncMock,
                return_value=self._make_info("opencode", healthy=False),
            ),
        ):
            backends = await discover_backends(force=True)
            claude_backends = [b for b in backends if b.name == "claude"]
            assert len(claude_backends) == 1
            assert claude_backends[0].healthy is True

    @pytest.mark.asyncio
    async def test_discovers_multiple_backends(self):
        with (
            patch.object(
                ClaudeBackend,
                "get_info",
                new_callable=AsyncMock,
                return_value=self._make_info("claude"),
            ),
            patch.object(
                CodexBackend,
                "get_info",
                new_callable=AsyncMock,
                return_value=self._make_info("codex"),
            ),
            patch.object(
                GeminiBackend,
                "get_info",
                new_callable=AsyncMock,
                return_value=self._make_info("gemini", healthy=False),
            ),
            patch.object(
                OpenCodeBackend,
                "get_info",
                new_callable=AsyncMock,
                return_value=self._make_info("opencode", healthy=False),
            ),
        ):
            backends = await discover_backends(force=True)
            names = [b.name for b in backends]
            assert "claude" in names
            assert "codex" in names
            assert "gemini" in names
            assert "opencode" in names

    @pytest.mark.asyncio
    async def test_no_backends_healthy(self):
        with (
            patch.object(
                ClaudeBackend,
                "get_info",
                new_callable=AsyncMock,
                return_value=self._make_info("claude", healthy=False),
            ),
            patch.object(
                CodexBackend,
                "get_info",
                new_callable=AsyncMock,
                return_value=self._make_info("codex", healthy=False),
            ),
            patch.object(
                GeminiBackend,
                "get_info",
                new_callable=AsyncMock,
                return_value=self._make_info("gemini", healthy=False),
            ),
            patch.object(
                OpenCodeBackend,
                "get_info",
                new_callable=AsyncMock,
                return_value=self._make_info("opencode", healthy=False),
            ),
        ):
            backends = await discover_backends(force=True)
            assert all(not b.healthy for b in backends)


class TestGetBestBackend:
    """Tests for getting the best available backend."""

    def setup_method(self):
        reset_circuit_breaker()

    @pytest.mark.asyncio
    async def test_returns_claude_when_available(self):
        with patch.object(ClaudeBackend, "is_available", new_callable=AsyncMock, return_value=True):
            backend, reason = await get_best_backend("auto")
            assert backend is not None
            assert backend.name == "claude"
            assert reason == "auto_default"

    @pytest.mark.asyncio
    async def test_returns_none_when_unavailable(self):
        with (
            patch.object(ClaudeBackend, "is_available", new_callable=AsyncMock, return_value=False),
            patch.object(CodexBackend, "is_available", new_callable=AsyncMock, return_value=False),
            patch.object(GeminiBackend, "is_available", new_callable=AsyncMock, return_value=False),
        ):
            backend, reason = await get_best_backend("auto")
            assert backend is None

    @pytest.mark.asyncio
    async def test_explicit_claude_preference(self):
        with patch.object(ClaudeBackend, "is_available", new_callable=AsyncMock, return_value=True):
            backend, reason = await get_best_backend("claude")
            assert backend is not None
            assert backend.name == "claude"
            assert reason == "user_specified"

    @pytest.mark.asyncio
    async def test_explicit_codex_preference(self):
        with patch.object(CodexBackend, "is_available", new_callable=AsyncMock, return_value=True):
            backend, reason = await get_best_backend("codex")
            assert backend is not None
            assert backend.name == "codex"
            assert reason == "user_specified"

    @pytest.mark.asyncio
    async def test_explicit_gemini_preference(self):
        with patch.object(GeminiBackend, "is_available", new_callable=AsyncMock, return_value=True):
            backend, reason = await get_best_backend("gemini")
            assert backend is not None
            assert backend.name == "gemini"
            assert reason == "user_specified"

    @pytest.mark.asyncio
    async def test_opencode_not_executable(self):
        with patch.object(
            OpenCodeBackend, "is_available", new_callable=AsyncMock, return_value=True
        ):
            backend, reason = await get_best_backend("opencode")
            assert backend is None
            assert reason == "user_specified"

    @pytest.mark.asyncio
    async def test_fallback_to_codex_when_claude_unavailable(self):
        with (
            patch.object(ClaudeBackend, "is_available", new_callable=AsyncMock, return_value=False),
            patch.object(CodexBackend, "is_available", new_callable=AsyncMock, return_value=True),
        ):
            backend, reason = await get_best_backend("auto")
            assert backend is not None
            assert backend.name == "codex"
            assert reason == "auto_default"

    @pytest.mark.asyncio
    async def test_circuit_breaker_fallback(self):
        from mdxcode.backends.circuit_breaker import get_circuit_breaker

        cb = get_circuit_breaker()
        for _ in range(3):
            cb.record_failure("claude")

        with (
            patch.object(ClaudeBackend, "is_available", new_callable=AsyncMock, return_value=True),
            patch.object(CodexBackend, "is_available", new_callable=AsyncMock, return_value=True),
        ):
            backend, reason = await get_best_backend("auto")
            assert backend is not None
            assert backend.name == "codex"
            assert reason == "circuit_breaker_fallback"

    def teardown_method(self):
        reset_circuit_breaker()
