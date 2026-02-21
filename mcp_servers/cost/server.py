"""Cost MCP server — spending tracking via MCP protocol."""

import uuid

from mcp.server.fastmcp import FastMCP

from mdxcode.router.cost_tracker import (
    get_cost_by_backend,
    get_date_range_for_period,
    get_savings,
    get_top_tasks,
    get_total_cost,
    record_cost,
)

mcp = FastMCP("mdx-cost")


@mcp.tool()
def log_cost(
    backend: str,
    model: str = "",
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_usd: float = 0.0,
    task_category: str = "",
) -> dict:
    """Log a cost entry for an AI operation.

    Records token usage and cost for tracking and optimization.
    Returns the entry ID and current daily total.

    Args:
        backend: Which AI backend was used (e.g. "claude", "codex", "gemini").
        model: Specific model name if known.
        tokens_in: Input tokens consumed.
        tokens_out: Output tokens generated.
        cost_usd: Cost in USD for this operation.
        task_category: Category of the task (e.g. "code_generation", "code_review").
    """
    try:
        session_id = str(uuid.uuid4())
        entry_id = record_cost(
            session_id=session_id,
            backend=backend,
            model=model or None,
            task_category=task_category or None,
            tokens_in=tokens_in or None,
            tokens_out=tokens_out or None,
            cost_usd=cost_usd or None,
        )

        # Get daily total for context
        today_since, today_until = get_date_range_for_period("today")
        daily_total = get_total_cost(since=today_since, until=today_until)

        return {
            "entry_id": entry_id,
            "daily_total": round(daily_total, 4),
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_summary(period: str = "week") -> dict:
    """Get a cost summary for a time period.

    Returns total spending, breakdown by backend, smart routing savings,
    and most expensive tasks.

    Args:
        period: Time period — "today", "week", or "month" (default "week").
    """
    try:
        since, until = get_date_range_for_period(period)

        total = get_total_cost(since=since, until=until)
        by_backend = get_cost_by_backend(since=since, until=until)
        savings = get_savings(since=since, until=until)
        top = get_top_tasks(since=since, until=until, limit=5)

        # Clean up top tasks for serialization
        top_tasks = []
        for entry in top:
            top_tasks.append({
                "task_summary": entry.get("task_summary", ""),
                "backend": entry.get("backend", ""),
                "cost_usd": entry.get("cost_usd", 0),
                "timestamp": entry.get("timestamp", ""),
            })

        return {
            "period": period,
            "total_usd": round(total, 4),
            "by_backend": {k: round(v, 4) for k, v in by_backend.items()},
            "savings_usd": round(savings, 4),
            "top_tasks": top_tasks,
        }
    except ValueError as e:
        return {"error": f"Invalid period: {period}. Use 'today', 'week', or 'month'."}
    except Exception as e:
        return {"error": str(e)}


def main():
    """Run the cost MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
