"""Audit MCP server — immutable audit trail via MCP protocol."""

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from mdxcode.config import load_config
from mdxcode.governance.audit_trail import (
    AuditEntry,
    compute_audit_stats,
    read_filtered_entries,
    read_recent_entries,
    verify_audit_integrity,
    write_audit_entry,
)

mcp = FastMCP("mdx-audit")


@mcp.tool()
def log_action(
    task: str,
    backend: str,
    model: str = "",
    files_modified: list[str] = [],
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_usd: float = 0.0,
    duration_seconds: float = 0.0,
) -> dict:
    """Log an action to the MDx audit trail.

    Creates an immutable, chain-hashed audit entry for any AI-assisted action.
    Returns the entry ID and chain hash for verification.

    Args:
        task: Description of the task performed.
        backend: Which AI backend was used (e.g. "claude", "codex", "gemini").
        model: Specific model name if known.
        files_modified: List of files that were modified.
        tokens_in: Input tokens consumed.
        tokens_out: Output tokens generated.
        cost_usd: Cost in USD.
        duration_seconds: How long the action took.
    """
    try:
        entry = AuditEntry(
            session_id=str(uuid.uuid4()),
            task=task,
            backend=backend,
            model=model or None,
            working_directory=str(Path.cwd()),
            duration_seconds=duration_seconds,
            files_modified=files_modified,
            tokens_in=tokens_in or None,
            tokens_out=tokens_out or None,
            cost_usd=cost_usd or None,
            status="success",
        )
        filepath = write_audit_entry(entry)
        return {
            "entry_id": entry.entry_id,
            "chain_hash": entry.chain_hash,
            "filepath": str(filepath),
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def query_audit(
    path: str = "",
    since: str = "",
    limit: int = 20,
) -> dict:
    """Query the MDx audit trail.

    Search and filter audit entries by working directory path and date.
    Returns matching entries sorted chronologically.

    Args:
        path: Filter by working directory containing this substring.
        since: Only entries on or after this date (YYYY-MM-DD format).
        limit: Maximum number of entries to return (default 20).
    """
    try:
        config = load_config()
        audit_dir = Path(config.audit.directory).expanduser()

        has_filters = bool(path or since)
        if has_filters:
            entries = read_filtered_entries(
                audit_dir,
                since=since or None,
                path=path or None,
            )
            entries = entries[-limit:] if len(entries) > limit else entries
        else:
            entries = read_recent_entries(audit_dir, count=limit)

        return {
            "count": len(entries),
            "entries": entries,
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def verify_integrity() -> dict:
    """Verify the integrity of the MDx audit trail.

    Checks chain hash integrity across all audit log files.
    Detects any tampering or corruption in the audit history.
    """
    try:
        config = load_config()
        audit_dir = Path(config.audit.directory).expanduser()

        if not audit_dir.exists():
            return {"valid": True, "files_checked": 0, "note": "No audit directory found."}

        jsonl_files = sorted(audit_dir.glob("*.jsonl"))
        if not jsonl_files:
            return {"valid": True, "files_checked": 0, "note": "No audit files found."}

        results = []
        all_valid = True
        for filepath in jsonl_files:
            valid, error = verify_audit_integrity(filepath)
            results.append({
                "file": filepath.name,
                "valid": valid,
                "error": error,
            })
            if not valid:
                all_valid = False

        return {
            "valid": all_valid,
            "files_checked": len(jsonl_files),
            "results": results,
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def get_stats(days: int = 30) -> dict:
    """Get audit trail statistics.

    Computes summary statistics from recent audit entries including
    action counts, backend usage, policy violations, and total cost.

    Args:
        days: Number of days to include (default 30).
    """
    try:
        config = load_config()
        audit_dir = Path(config.audit.directory).expanduser()

        since_date = (
            datetime.now(timezone.utc)
            .replace(hour=0, minute=0, second=0, microsecond=0)
        )
        # Subtract days manually to avoid import issues
        from datetime import timedelta

        since_date = since_date - timedelta(days=days)
        since_str = since_date.strftime("%Y-%m-%d")

        entries = read_filtered_entries(audit_dir, since=since_str)
        if not entries:
            return {
                "period_days": days,
                "total_actions": 0,
                "note": "No audit entries found for this period.",
            }

        stats = compute_audit_stats(entries)
        stats["period_days"] = days
        return stats
    except Exception as e:
        return {"error": str(e)}


def main():
    """Run the audit MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
