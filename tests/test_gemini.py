"""Tests for the Gemini CLI backend adapter."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from mdxcode.backends.gemini import GeminiBackend


class TestGeminiBackend:
    """Tests for the Gemini backend adapter."""

    def test_name(self):
        backend = GeminiBackend()
        assert backend.name == "gemini"

    def test_cli_command(self):
        backend = GeminiBackend()
        assert backend.cli_command == "gemini"

    @pytest.mark.asyncio
    async def test_available_when_in_path(self):
        with patch("shutil.which", return_value="/usr/local/bin/gemini"):
            backend = GeminiBackend()
            assert await backend.is_available() is True

    @pytest.mark.asyncio
    async def test_unavailable_when_not_in_path(self):
        with patch("shutil.which", return_value=None):
            backend = GeminiBackend()
            assert await backend.is_available() is False

    @pytest.mark.asyncio
    async def test_get_info_not_installed(self):
        with patch("shutil.which", return_value=None):
            backend = GeminiBackend()
            info = await backend.get_info()
            assert info.name == "gemini"
            assert info.healthy is False
            assert info.authenticated is False
            assert info.version == "not installed"

    @pytest.mark.asyncio
    async def test_get_info_installed(self):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"1.0.0", b""))
        mock_proc.returncode = 0

        with (
            patch("shutil.which", return_value="/usr/local/bin/gemini"),
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
        ):
            backend = GeminiBackend()
            info = await backend.get_info()
            assert info.name == "gemini"
            assert info.version == "1.0.0"
            assert info.authenticated is True
            assert info.healthy is True


class TestGeminiStreaming:
    """Tests for Gemini output streaming."""

    @pytest.mark.asyncio
    async def test_streams_output(self):
        mock_proc = AsyncMock()
        mock_stdout = AsyncMock()
        lines = [b"Analyzing code...\n", b"Complete.\n", b""]
        mock_stdout.readline = AsyncMock(side_effect=lines)
        mock_proc.stdout = mock_stdout
        mock_proc.stderr = AsyncMock()
        mock_proc.stderr.read = AsyncMock(return_value=b"")
        mock_proc.wait = AsyncMock()
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            backend = GeminiBackend()
            chunks = []
            async for chunk in backend.execute("test task", __import__("pathlib").Path(".")):
                chunks.append(chunk)

            assert len(chunks) == 2
            assert "Analyzing code" in chunks[0]

    @pytest.mark.asyncio
    async def test_timeout_kills_process(self):
        mock_proc = AsyncMock()
        mock_stdout = AsyncMock()
        mock_stdout.readline = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_proc.stdout = mock_stdout
        mock_proc.kill = Mock()
        mock_proc.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            backend = GeminiBackend(timeout=1)
            chunks = []
            async for chunk in backend.execute("test", __import__("pathlib").Path(".")):
                chunks.append(chunk)

            assert any("timed out" in c for c in chunks)
            mock_proc.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_credential_error_detected(self):
        mock_proc = AsyncMock()
        mock_stdout = AsyncMock()
        mock_stdout.readline = AsyncMock(side_effect=[b""])
        mock_proc.stdout = mock_stdout
        mock_proc.stderr = AsyncMock()
        mock_proc.stderr.read = AsyncMock(
            return_value=b"Error: credential not found. Set up Google Cloud credentials."
        )
        mock_proc.wait = AsyncMock()
        mock_proc.returncode = 1

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            backend = GeminiBackend()
            chunks = []
            async for chunk in backend.execute("test", __import__("pathlib").Path(".")):
                chunks.append(chunk)

            assert any("Authentication required" in c for c in chunks)


class TestGeminiParsing:
    """Tests for Gemini output parsing."""

    def test_parse_valid_json(self):
        backend = GeminiBackend()
        output = '{"model": "gemini-2.5-pro", "cost_usd": 0.01, "usage": {"input_tokens": 300, "output_tokens": 100}}'
        model, cost, t_in, t_out = backend._parse_output(output)
        assert model == "gemini-2.5-pro"
        assert cost == 0.01
        assert t_in == 300
        assert t_out == 100

    def test_parse_invalid_json(self):
        backend = GeminiBackend()
        model, cost, t_in, t_out = backend._parse_output("not json")
        assert model is None
        assert cost is None

    def test_parse_partial_json(self):
        backend = GeminiBackend()
        output = '{"model": "gemini-2.5-pro"}'
        model, cost, t_in, t_out = backend._parse_output(output)
        assert model == "gemini-2.5-pro"
        assert cost is None


class TestGeminiHealthCheck:
    """Tests for Gemini health check."""

    @pytest.mark.asyncio
    async def test_healthy_when_responsive(self):
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"1.0.0", b""))
        mock_proc.returncode = 0

        with (
            patch("shutil.which", return_value="/usr/local/bin/gemini"),
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
        ):
            backend = GeminiBackend()
            hs = await backend.health_check()
            assert hs.healthy is True
            assert hs.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_unhealthy_when_not_installed(self):
        with patch("shutil.which", return_value=None):
            backend = GeminiBackend()
            hs = await backend.health_check()
            assert hs.healthy is False
            assert hs.details == "not installed"
