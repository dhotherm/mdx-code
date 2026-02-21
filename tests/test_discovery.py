"""Tests for backend discovery."""

import shutil
from unittest.mock import AsyncMock, patch

import pytest

from mdxcode.backends.base import BackendInfo
from mdxcode.backends.claude import ClaudeBackend
from mdxcode.backends.discovery import discover_backends, get_best_backend


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

    @pytest.mark.asyncio
    async def test_discovers_claude(self):
        with (
            patch.object(ClaudeBackend, "is_available", new_callable=AsyncMock, return_value=True),
            patch.object(
                ClaudeBackend,
                "get_info",
                new_callable=AsyncMock,
                return_value=BackendInfo(
                    name="claude", version="1.0.0", authenticated=True, healthy=True
                ),
            ),
            patch("shutil.which", return_value=None),
        ):
            backends = await discover_backends()
            claude_backends = [b for b in backends if b.name == "claude"]
            assert len(claude_backends) == 1
            assert claude_backends[0].healthy is True

    @pytest.mark.asyncio
    async def test_discovers_multiple_clis(self):
        def mock_which(name):
            return f"/usr/local/bin/{name}" if name in ("claude", "codex") else None

        with (
            patch.object(ClaudeBackend, "is_available", new_callable=AsyncMock, return_value=True),
            patch.object(
                ClaudeBackend,
                "get_info",
                new_callable=AsyncMock,
                return_value=BackendInfo(
                    name="claude", version="1.0.0", authenticated=True, healthy=True
                ),
            ),
            patch("mdxcode.backends.discovery.shutil.which", side_effect=mock_which),
        ):
            backends = await discover_backends()
            names = [b.name for b in backends]
            assert "claude" in names
            assert "codex" in names

    @pytest.mark.asyncio
    async def test_no_backends_found(self):
        with (
            patch.object(
                ClaudeBackend, "is_available", new_callable=AsyncMock, return_value=False
            ),
            patch.object(
                ClaudeBackend,
                "get_info",
                new_callable=AsyncMock,
                return_value=BackendInfo(
                    name="claude", version="not installed", authenticated=False, healthy=False
                ),
            ),
            patch("mdxcode.backends.discovery.shutil.which", return_value=None),
        ):
            backends = await discover_backends()
            assert all(not b.healthy for b in backends)


class TestGetBestBackend:
    """Tests for getting the best available backend."""

    @pytest.mark.asyncio
    async def test_returns_claude_when_available(self):
        with patch.object(ClaudeBackend, "is_available", new_callable=AsyncMock, return_value=True):
            backend = await get_best_backend("auto")
            assert backend is not None
            assert backend.name == "claude"

    @pytest.mark.asyncio
    async def test_returns_none_when_unavailable(self):
        with patch.object(
            ClaudeBackend, "is_available", new_callable=AsyncMock, return_value=False
        ):
            backend = await get_best_backend("auto")
            assert backend is None

    @pytest.mark.asyncio
    async def test_explicit_claude_preference(self):
        with patch.object(ClaudeBackend, "is_available", new_callable=AsyncMock, return_value=True):
            backend = await get_best_backend("claude")
            assert backend is not None
            assert backend.name == "claude"
