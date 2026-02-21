"""The MDx Code footer displayed after task completion."""

from typing import Optional

from rich.console import Console
from rich.text import Text

console = Console()

REASON_LABELS = {
    "user_specified": "user selected",
    "auto_default": "auto-detected",
    "circuit_breaker_fallback": "fallback (circuit breaker)",
}


def show_footer(
    backend_name: str,
    model: Optional[str],
    duration: float,
    session_id: str,
    cost_usd: Optional[float] = None,
    cost_estimated: bool = False,
    savings: float = 0.0,
    savings_vs: str = "",
    selection_reason: Optional[str] = None,
) -> None:
    """Display the MDx Code footer after task completion."""
    width = min(console.width, 52)
    separator = "\u2500" * width

    console.print()
    console.print(f"[dim]\u2500\u2500\u2500 MDx Code {separator[12:]}[/dim]")

    # Completion line
    model_display = f" ({model})" if model else ""
    reason_display = ""
    if selection_reason:
        label = REASON_LABELS.get(selection_reason, selection_reason)
        reason_display = f" [{label}]"
    console.print(
        f"  [green]\u2713[/green] Completed via {backend_name.title()}{model_display} "
        f"in {duration:.1f}s{reason_display}"
    )

    # Cost line with savings
    if cost_usd is not None:
        est_marker = "~" if cost_estimated else ""
        cost_str = f"  [green]\u2713[/green] Cost: {est_marker}${cost_usd:.4f}"
        if cost_estimated:
            cost_str += " (estimated)"
        if savings > 0 and savings_vs:
            cost_str += f" (saved ${savings:.2f} vs {savings_vs.title()})"
        console.print(cost_str)

    # Audit line
    session_short = session_id[:8] if len(session_id) >= 8 else session_id
    console.print(f"  [green]\u2713[/green] Audit logged (session {session_short}...)")

    # Review hint
    console.print(
        "  [yellow]\u26a1[/yellow] Quick review available: [bold]mdx review --last[/bold]"
    )

    console.print(f"[dim]{separator}[/dim]")
