"""Abstract base class for backend adapters."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Optional


@dataclass
class BackendInfo:
    """Information about a backend."""

    name: str
    version: str
    authenticated: bool
    healthy: bool


@dataclass
class HealthStatus:
    """Result of a backend health check."""

    healthy: bool
    latency_ms: int
    details: str


@dataclass
class TaskResult:
    """Result of a task execution."""

    backend_name: str
    model_used: Optional[str] = None
    output: str = ""
    files_modified: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    cost_usd: Optional[float] = None
    exit_code: int = 0


class Backend(ABC):
    """Abstract base for backend adapters."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend name (e.g., 'claude', 'codex', 'gemini')."""
        ...

    @property
    @abstractmethod
    def cli_command(self) -> str:
        """The CLI command to check/run (e.g., 'claude', 'codex')."""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the CLI is installed and in PATH."""
        ...

    @abstractmethod
    async def get_info(self) -> BackendInfo:
        """Get backend info including version and auth status."""
        ...

    @abstractmethod
    async def execute(self, task: str, cwd: Path) -> AsyncIterator[str]:
        """
        Execute a task and stream output.

        This is the core method. It MUST:
        1. Spawn the CLI as a subprocess
        2. Yield output chunks as they arrive (for real-time display)
        3. Handle timeouts, crashes, auth failures

        The caller will both display the output AND capture it for audit.
        """
        ...

    @abstractmethod
    async def execute_and_capture(self, task: str, cwd: Path) -> TaskResult:
        """
        Execute a task, stream to terminal, and capture full result.

        Convenience method that calls execute() internally,
        streams to display, and returns the complete TaskResult.
        """
        ...

    @abstractmethod
    async def health_check(self) -> HealthStatus:
        """
        Verify the backend is responsive.

        Lightweight check — verify the CLI responds to a version command,
        not run a full task.
        """
        ...
