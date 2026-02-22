"""Tests for the Codex CLI backend adapter."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from mdxcode.backends.codex import CodexBackend


class TestCodexBackend:
    """Tests for the Codex backend adapter."""

    def test_name(self):
        backend = CodexBackend()
        assert backend.name == "codex"

    def test_cli_command(self):
        backend = CodexBackend()
        assert backend.cli_command == "codex"

    @pytest.mark.asyncio
    async def test_available_when_in_path(self):
        with patch("shutil.which", return_value="/usr/local/bin/codex"):
            backend = CodexBackend()
            assert await backend.is_available() is True

    @pytest.mark.asyncio
    async def test_unavailable_when_not_in_path(self):
        with patch("shutil.which", return_value=None):
            backend = CodexBackend()
            assert await backend.is_available() is False

    @pytest.mark.asyncio
    async def test_get_info_not_installed(self):
        with patch("shutil.which", return_value=None):
            backend = CodexBackend()
            info = await backend.get_info()
            assert info.name == "codex"
            assert info.healthy is False
            assert info.authenticated is False
            assert info.version == "not installed"

    @pytest.mark.asyncio
    async def test_get_info_installed(self):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"0.9.1", b""))
        mock_proc.returncode = 0

        with (
            patch("shutil.which", return_value="/usr/local/bin/codex"),
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
        ):
            backend = CodexBackend()
            info = await backend.get_info()
            assert info.name == "codex"
            assert info.version == "0.9.1"
            assert info.authenticated is True
            assert info.healthy is True


class TestCodexStreaming:
    """Tests for Codex output streaming."""

    @pytest.mark.asyncio
    async def test_streams_output(self):
        mock_proc = AsyncMock()
        mock_stdout = AsyncMock()
        lines = [b"Processing task...\n", b"Done.\n", b""]
        mock_stdout.readline = AsyncMock(side_effect=lines)
        mock_proc.stdout = mock_stdout
        mock_proc.stderr = AsyncMock()
        mock_proc.stderr.read = AsyncMock(return_value=b"")
        mock_proc.wait = AsyncMock()
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            backend = CodexBackend()
            chunks = []
            async for chunk in backend.execute("test task", __import__("pathlib").Path(".")):
                chunks.append(chunk)

            assert len(chunks) == 2
            assert "Processing task" in chunks[0]

    @pytest.mark.asyncio
    async def test_timeout_kills_process(self):
        mock_proc = AsyncMock()
        mock_stdout = AsyncMock()
        mock_stdout.readline = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_proc.stdout = mock_stdout
        mock_proc.kill = Mock()
        mock_proc.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            backend = CodexBackend(timeout=1)
            chunks = []
            async for chunk in backend.execute("test", __import__("pathlib").Path(".")):
                chunks.append(chunk)

            assert any("timed out" in c for c in chunks)
            mock_proc.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_auth_error_detected(self):
        mock_proc = AsyncMock()
        mock_stdout = AsyncMock()
        mock_stdout.readline = AsyncMock(side_effect=[b""])
        mock_proc.stdout = mock_stdout
        mock_proc.stderr = AsyncMock()
        mock_proc.stderr.read = AsyncMock(
            return_value=b"Error: authentication required. Please login first."
        )
        mock_proc.wait = AsyncMock()
        mock_proc.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            backend = CodexBackend()
            chunks = []
            async for chunk in backend.execute("test", __import__("pathlib").Path(".")):
                chunks.append(chunk)

            assert any("Authentication required" in c for c in chunks)


class TestCodexParsing:
    """Tests for Codex output parsing."""

    def test_parse_valid_json(self):
        backend = CodexBackend()
        output = '{"model": "codex-mini", "cost_usd": 0.02, "usage": {"input_tokens": 500, "output_tokens": 200}}'
        model, cost, t_in, t_out = backend._parse_output(output)
        assert model == "codex-mini"
        assert cost == 0.02
        assert t_in == 500
        assert t_out == 200

    def test_parse_invalid_json(self):
        backend = CodexBackend()
        model, cost, t_in, t_out = backend._parse_output("not json")
        assert model is None
        assert cost is None

    def test_parse_partial_json(self):
        backend = CodexBackend()
        output = '{"model": "codex-mini"}'
        model, cost, t_in, t_out = backend._parse_output(output)
        assert model == "codex-mini"
        assert cost is None


class TestCodexHealthCheck:
    """Tests for Codex health check."""

    @pytest.mark.asyncio
    async def test_healthy_when_responsive(self):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"0.9.1", b""))
        mock_proc.returncode = 0

        with (
            patch("shutil.which", return_value="/usr/local/bin/codex"),
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
        ):
            backend = CodexBackend()
            hs = await backend.health_check()
            assert hs.healthy is True
            assert hs.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_unhealthy_when_not_installed(self):
        with patch("shutil.which", return_value=None):
            backend = CodexBackend()
            hs = await backend.health_check()
            assert hs.healthy is False
            assert hs.details == "not installed"
