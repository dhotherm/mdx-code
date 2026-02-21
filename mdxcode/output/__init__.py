"""Output handling: streaming, footer display."""

import os

from rich.console import Console

# Single shared console instance — avoid re-initialization per module
_NO_COLOR = os.environ.get("NO_COLOR") is not None
console = Console(no_color=_NO_COLOR)
