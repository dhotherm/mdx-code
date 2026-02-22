"""Real-time output streaming from backend adapters."""

import asyncio
import sys
import time
from typing import AsyncIterator

from rich.markdown import Markdown
from rich.spinner import Spinner

from . import console

# Markers that suggest content is markdown
_MD_MARKERS = ("**", "##", "```", "- ", "* ", "1. ", "> ", "[", "| ")


def _looks_like_markdown(text: str) -> bool:
    """Check if text contains markdown formatting."""
    return any(marker in text for marker in _MD_MARKERS)


async def stream_output(chunks: AsyncIterator[str]) -> tuple[str, float]:
    """
    Stream output from a backend, rendering markdown when detected.

    Shows a spinner with elapsed timer until the first chunk arrives,
    then transitions to "Receiving..." while buffering. After all chunks
    are received, renders the full output as Rich markdown (if detected)
    or as raw text.

    When piping (non-TTY), skips spinner and markdown rendering for
    clean machine-readable output.

    Returns (full_output, duration_seconds).
    """
    start = time.monotonic()
    captured: list[str] = []

    # Raw mode for piped output — no spinner, no markdown
    if not sys.stdout.isatty():
        async for chunk in chunks:
            sys.stdout.write(chunk)
            sys.stdout.flush()
            captured.append(chunk)
        duration = time.monotonic() - start
        return "".join(captured), duration

    first_chunk = True
    receiving = False

    spinner = Spinner("dots", text="[dim] Thinking... 0.0s[/dim]")

    with console.status(spinner, spinner_style="cyan") as status:
        # Background task to update the spinner with elapsed time
        async def update_timer() -> None:
            while True:
                elapsed = time.monotonic() - start
                phase = "Receiving..." if receiving else "Thinking..."
                status.update(Spinner("dots", text=f"[dim] {phase} {elapsed:.1f}s[/dim]"))
                await asyncio.sleep(0.1)

        timer_task = asyncio.create_task(update_timer())

        try:
            async for chunk in chunks:
                if first_chunk:
                    first_chunk = False
                    receiving = True
                captured.append(chunk)
        finally:
            timer_task.cancel()
            try:
                await timer_task
            except asyncio.CancelledError:
                pass

    duration = time.monotonic() - start
    full_output = "".join(captured)

    # Render output
    if full_output.strip():
        if _looks_like_markdown(full_output):
            console.print(Markdown(full_output.strip()))
        else:
            console.print(full_output, end="")

    return full_output, duration
