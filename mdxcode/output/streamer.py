"""Real-time output streaming from backend adapters."""

import sys
import time
from typing import AsyncIterator

from rich.console import Console
from rich.spinner import Spinner

console = Console()


async def stream_output(chunks: AsyncIterator[str]) -> tuple[str, float]:
    """
    Stream output chunks to the terminal in real-time.
    Shows a spinner until the first chunk arrives.

    Returns (full_output, duration_seconds).
    """
    start = time.monotonic()
    captured: list[str] = []
    first_chunk = True

    # Start spinner
    spinner = Spinner("dots", text="[dim] Thinking...[/dim]")

    with console.status(spinner, spinner_style="cyan") as status:
        async for chunk in chunks:
            if first_chunk:
                # Stop the spinner before printing first output
                first_chunk = False
                status.stop()
                console.print()  # Clean line after spinner

            sys.stdout.write(chunk)
            sys.stdout.flush()
            captured.append(chunk)

    # If we never got any output, status context manager handles cleanup

    duration = time.monotonic() - start
    full_output = "".join(captured)
    return full_output, duration
