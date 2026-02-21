"""The MDx Code footer displayed after task completion."""

import sys
from typing import Optional

from . import console
from .colors import colored_backend

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
    has_file_changes: bool = False,
    alternative_costs: dict[str, float] | None = None,
    timing_insight: Optional[str] = None,
    daily_budget: Optional[float] = None,
    daily_spent: Optional[float] = None,
    task_count: int = 0,
) -> None:
    """Display the MDx Code footer after task completion."""
    width = min(console.width, 52)
    separator = "\u2500" * width

    console.print()
    console.print(f"[dim]\u2500\u2500\u2500 MDx Code {separator[12:]}[/dim]")

    # Completion line (with colored backend name and timing insight)
    model_display = f" ({model})" if model else ""
    reason_display = ""
    if selection_reason:
        label = REASON_LABELS.get(selection_reason, selection_reason)
        reason_display = f" [{label}]"
    timing_str = f" ({timing_insight})" if timing_insight else ""
    console.print(
        f"  [green]\u2713[/green] Completed via {colored_backend(backend_name)}{model_display} "
        f"in {duration:.1f}s{timing_str}{reason_display}"
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

        # Cost comparison line (dim, only when alternatives exist)
        if alternative_costs:
            alts = []
            for alt_name, alt_cost in sorted(alternative_costs.items(), key=lambda x: x[1]):
                diff = alt_cost - cost_usd
                if abs(diff) > 0.0001:
                    sign = "+" if diff > 0 else ""
                    alts.append(f"{alt_name.title()} ${alt_cost:.4f} ({sign}${diff:.4f})")
            if alts:
                console.print(f"    [dim]vs. {' \u00b7 '.join(alts)}[/dim]")

    # Audit line (merge with review hint when there are file changes)
    session_short = session_id[:8] if len(session_id) >= 8 else session_id
    if has_file_changes:
        console.print(
            f"  [green]\u2713[/green] Audit: {session_short}... "
            f"\u2192 [bold]mdx review --last[/bold]"
        )
    else:
        console.print(f"  [green]\u2713[/green] Audit logged (session {session_short}...)")

    # Daily budget progress
    if daily_budget and daily_spent is not None:
        pct = (daily_spent / daily_budget) * 100
        console.print(f"    [dim]Daily: ${daily_spent:.2f} / ${daily_budget:.2f} ({pct:.0f}%)[/dim]")

    console.print(f"[dim]{separator}[/dim]")

    # Contextual tips for new users (first 3 tasks)
    _ONBOARDING_TIPS = {
        1: "\U0001f4a1 [dim]Tip: Run [bold]mdx cost[/bold] to see your spending dashboard[/dim]",
        2: "\U0001f4a1 [dim]Tip: Run [bold]mdx review --last[/bold] to get a second opinion on that change[/dim]",
        3: "\U0001f4a1 [dim]Tip: Run [bold]mdx undo[/bold] if you want to revert what just happened[/dim]",
    }

    tip = _ONBOARDING_TIPS.get(task_count)
    if tip:
        console.print()
        console.print(f"  {tip}")

    # Terminal bell for completed tasks (configurable)
    from ..config import load_config

    config = load_config()
    if config.display.sound:
        sys.stdout.write("\a")
        sys.stdout.flush()
