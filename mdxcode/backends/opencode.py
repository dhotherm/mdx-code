"""OpenCode backend adapter (limited support — TUI-first design)."""

import asyncio
import shutil
import time
from pathlib import Path
from typing import AsyncIterator

from .base import Backend, BackendInfo, HealthStatus, TaskResult


class OpenCodeBackend(Backend):
    """
    Adapter for OpenCode CLI.

    OpenCode is a Go-based CLI with a TUI-first design. Non-interactive mode
    is not reliably available, so this adapter is detected but execution
    support is limited.
    """

    def __init__(self, timeout: int = 300):
        self._timeout = timeout

    @property
    def name(self) -> str:
        return "opencode"

    @property
    def cli_command(self) -> str:
        return "opencode"

    async def is_available(self) -> bool:
        """Check if opencode CLI is installed and in PATH."""
        return shutil.which(self.cli_command) is not None

    async def get_info(self) -> BackendInfo:
        """Get OpenCode version and status."""
        if not await self.is_available():
            return BackendInfo(
                name=self.name, version="not installed", authenticated=False, healthy=False
            )

        version = await self._get_version()

        return BackendInfo(
            name=self.name,
            version=version,
            authenticated=False,
            healthy=False,
        )

    async def _get_version(self) -> str:
        """Get OpenCode version string."""
        try:
            proc = await asyncio.create_subprocess_exec(
                self.cli_command,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            return stdout.decode().strip() or "unknown"
        except (asyncio.TimeoutError, FileNotFoundError, OSError):
            return "unknown"

    async def execute(self, task: str, cwd: Path) -> AsyncIterator[str]:
        """OpenCode execution is not supported — TUI-first design."""
        yield (
            "\n[MDx Code] OpenCode detected but not supported for non-interactive execution.\n"
            "OpenCode uses a TUI-first design that requires an interactive terminal.\n"
            "Use --backend claude, --backend codex, or --backend gemini instead.\n"
        )

    execute.__doc__ = """OpenCode execution is not supported — TUI-first design."""

    async def execute_and_capture(self, task: str, cwd: Path) -> TaskResult:
        """OpenCode execution is not supported."""
        return TaskResult(
            backend_name=self.name,
            output="[OpenCode does not support non-interactive execution]",
            exit_code=1,
        )

    async def health_check(self) -> HealthStatus:
        """Check if OpenCode CLI is installed."""
        if not await self.is_available():
            return HealthStatus(healthy=False, latency_ms=0, details="not installed")
        try:
            start = time.monotonic()
            proc = await asyncio.create_subprocess_exec(
                self.cli_command,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=10)
            latency = int((time.monotonic() - start) * 1000)
            return HealthStatus(
                healthy=False,
                latency_ms=latency,
                details="detected (limited support — TUI only)",
            )
        except (asyncio.TimeoutError, FileNotFoundError, OSError):
            return HealthStatus(healthy=False, latency_ms=0, details="not responsive")
