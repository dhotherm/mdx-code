"""Real-time output streaming from backend adapters."""

import sys
import time
from typing import AsyncIterator

from rich.console import Console

console = Console()


async def stream_output(chunks: AsyncIterator[str]) -> tuple[str, float]:
    """
    Stream output chunks to the terminal in real-time.

    Returns (full_output, duration_seconds).
    """
    start = time.monotonic()
    captured: list[str] = []

    async for chunk in chunks:
        sys.stdout.write(chunk)
        sys.stdout.flush()
        captured.append(chunk)

    duration = time.monotonic() - start
    full_output = "".join(captured)
    return full_output, duration
