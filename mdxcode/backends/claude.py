"""Claude Code backend adapter."""

import asyncio
import json
import shutil
import time
from pathlib import Path
from typing import AsyncIterator, Optional

from .base import Backend, BackendInfo, HealthStatus, TaskResult


class ClaudeBackend(Backend):
    """Adapter for Claude Code CLI."""

    def __init__(self, timeout: int = 300):
        self._timeout = timeout

    @property
    def name(self) -> str:
        return "claude"

    @property
    def cli_command(self) -> str:
        return "claude"

    async def is_available(self) -> bool:
        """Check if claude CLI is installed and in PATH."""
        return shutil.which(self.cli_command) is not None

    async def get_info(self) -> BackendInfo:
        """Get Claude Code version and auth status."""
        if not await self.is_available():
            return BackendInfo(
                name=self.name, version="not installed", authenticated=False, healthy=False
            )

        version = await self._get_version()
        authenticated = await self._check_auth()

        return BackendInfo(
            name=self.name,
            version=version,
            authenticated=authenticated,
            healthy=authenticated,
        )

    async def _get_version(self) -> str:
        """Get Claude Code version string."""
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

    async def _check_auth(self) -> bool:
        """Check if Claude Code is authenticated."""
        # Claude Code stores auth state internally.
        # A lightweight check: run with --version; if it works, CLI is functional.
        # Full auth check would require attempting a real request.
        # For now, consider it authenticated if the CLI is available and responds.
        try:
            proc = await asyncio.create_subprocess_exec(
                self.cli_command,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            return proc.returncode == 0
        except (asyncio.TimeoutError, FileNotFoundError, OSError):
            return False

    async def execute(self, task: str, cwd: Path) -> AsyncIterator[str]:
        """
        Execute a task via Claude Code and stream output.

        Spawns: claude -p "task"
        Streams stdout line-by-line as it arrives.
        """
        proc = await asyncio.create_subprocess_exec(
            self.cli_command,
            "-p",
            task,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd),
        )

        try:
            assert proc.stdout is not None
            async for line in self._stream_lines(proc.stdout):
                yield line
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            yield "\n[MDx Code] Task timed out after {}s\n".format(self._timeout)
            return

        await proc.wait()

        if proc.returncode != 0 and proc.stderr:
            stderr_output = await proc.stderr.read()
            stderr_text = stderr_output.decode(errors="replace").strip()
            if stderr_text:
                if "auth" in stderr_text.lower() or "login" in stderr_text.lower():
                    yield (
                        "\n[MDx Code] Authentication required. "
                        "Run `claude` directly to authenticate.\n"
                    )
                else:
                    yield f"\n[MDx Code] Backend error (exit {proc.returncode}): {stderr_text}\n"

    # Make execute() return an AsyncIterator properly
    execute.__doc__ = """Execute a task via Claude Code and stream output."""

    async def _stream_lines(self, stream: asyncio.StreamReader) -> AsyncIterator[str]:
        """Read lines from an async stream with timeout."""
        while True:
            try:
                line = await asyncio.wait_for(stream.readline(), timeout=self._timeout)
                if not line:
                    break
                yield line.decode(errors="replace")
            except asyncio.TimeoutError:
                raise

    async def execute_and_capture(self, task: str, cwd: Path) -> TaskResult:
        """Execute task, capture all output, and return structured result."""
        start = time.monotonic()
        chunks: list[str] = []
        exit_code = 0

        proc = await asyncio.create_subprocess_exec(
            self.cli_command,
            "-p",
            task,
            "--output-format",
            "json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd),
        )

        try:
            assert proc.stdout is not None
            stdout_data = await asyncio.wait_for(proc.stdout.read(), timeout=self._timeout)
            chunks.append(stdout_data.decode(errors="replace"))
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            duration = time.monotonic() - start
            return TaskResult(
                backend_name=self.name,
                output="[Timed out after {}s]".format(self._timeout),
                duration_seconds=duration,
                exit_code=-1,
            )

        await proc.wait()
        exit_code = proc.returncode or 0
        duration = time.monotonic() - start
        full_output = "".join(chunks)

        # Try to parse structured JSON output
        model_used, cost, tokens_in, tokens_out = self._parse_json_output(full_output)

        return TaskResult(
            backend_name=self.name,
            model_used=model_used,
            output=full_output,
            duration_seconds=duration,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=cost,
            exit_code=exit_code,
        )

    async def health_check(self) -> HealthStatus:
        """Check if Claude Code CLI responds to a version command."""
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
            if proc.returncode == 0:
                return HealthStatus(healthy=True, latency_ms=latency, details="responsive")
            return HealthStatus(healthy=False, latency_ms=latency, details="non-zero exit")
        except asyncio.TimeoutError:
            return HealthStatus(healthy=False, latency_ms=10000, details="timeout")
        except (FileNotFoundError, OSError) as e:
            return HealthStatus(healthy=False, latency_ms=0, details=str(e))

    def _parse_json_output(
        self, output: str
    ) -> tuple[Optional[str], Optional[float], Optional[int], Optional[int]]:
        """
        Parse Claude Code JSON output for metadata.

        Returns (model, cost_usd, tokens_in, tokens_out).
        Falls back to (None, None, None, None) if parsing fails.
        """
        try:
            data = json.loads(output)
            if isinstance(data, dict):
                model = data.get("model")
                cost = data.get("cost_usd") or data.get("cost")
                usage = data.get("usage", {})
                tokens_in = usage.get("input_tokens") or usage.get("prompt_tokens")
                tokens_out = usage.get("output_tokens") or usage.get("completion_tokens")

                if cost is not None:
                    cost = float(cost)
                if tokens_in is not None:
                    tokens_in = int(tokens_in)
                if tokens_out is not None:
                    tokens_out = int(tokens_out)

                return model, cost, tokens_in, tokens_out
        except (json.JSONDecodeError, ValueError, TypeError, KeyError):
            pass
        return None, None, None, None
