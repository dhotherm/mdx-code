"""Cost tracking with SQLite storage."""

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from ..config import MDX_DIR


DB_PATH = MDX_DIR / "costs.db"

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS costs (
    id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    session_id TEXT NOT NULL,
    backend TEXT NOT NULL,
    model TEXT,
    task_category TEXT,
    task_summary TEXT,
    tokens_in INTEGER,
    tokens_out INTEGER,
    cost_usd REAL,
    estimated BOOLEAN DEFAULT FALSE,
    routing_strategy TEXT,
    alternative_costs TEXT
);
"""

CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_costs_timestamp ON costs(timestamp);
CREATE INDEX IF NOT EXISTS idx_costs_backend ON costs(backend);
CREATE INDEX IF NOT EXISTS idx_costs_session ON costs(session_id);
"""


def _get_db(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Get a database connection, creating the table if needed."""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute(CREATE_TABLE_SQL)
    for stmt in CREATE_INDEX_SQL.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            conn.execute(stmt)
    conn.commit()
    return conn


def record_cost(
    session_id: str,
    backend: str,
    model: Optional[str] = None,
    task_category: Optional[str] = None,
    task_summary: Optional[str] = None,
    tokens_in: Optional[int] = None,
    tokens_out: Optional[int] = None,
    cost_usd: Optional[float] = None,
    estimated: bool = False,
    routing_strategy: Optional[str] = None,
    alternative_costs: Optional[dict[str, float]] = None,
    db_path: Optional[Path] = None,
) -> str:
    """Record a cost entry. Returns the entry ID."""
    entry_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    alt_costs_json = json.dumps(alternative_costs) if alternative_costs else None

    # Truncate task summary for storage
    if task_summary and len(task_summary) > 200:
        task_summary = task_summary[:197] + "..."

    conn = _get_db(db_path)
    try:
        conn.execute(
            """INSERT INTO costs
               (id, timestamp, session_id, backend, model, task_category,
                task_summary, tokens_in, tokens_out, cost_usd, estimated,
                routing_strategy, alternative_costs)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry_id, timestamp, session_id, backend, model,
                task_category, task_summary, tokens_in, tokens_out,
                cost_usd, estimated, routing_strategy, alt_costs_json,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return entry_id


def query_costs(
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    backend: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Query cost entries by date range and/or backend."""
    conn = _get_db(db_path)
    try:
        query = "SELECT * FROM costs WHERE 1=1"
        params: list = []

        if since:
            query += " AND timestamp >= ?"
            params.append(since.isoformat())
        if until:
            query += " AND timestamp < ?"
            params.append(until.isoformat())
        if backend:
            query += " AND backend = ?"
            params.append(backend)

        query += " ORDER BY timestamp DESC"

        rows = conn.execute(query, params).fetchall()
        results = []
        for row in rows:
            entry = dict(row)
            if entry.get("alternative_costs"):
                entry["alternative_costs"] = json.loads(entry["alternative_costs"])
            else:
                entry["alternative_costs"] = {}
            entry["estimated"] = bool(entry.get("estimated"))
            results.append(entry)
        return results
    finally:
        conn.close()


def get_total_cost(
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    db_path: Optional[Path] = None,
) -> float:
    """Get total spending for a date range."""
    entries = query_costs(since=since, until=until, db_path=db_path)
    return sum(e.get("cost_usd", 0) or 0 for e in entries)


def get_cost_by_backend(
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    db_path: Optional[Path] = None,
) -> dict[str, float]:
    """Get spending breakdown by backend."""
    entries = query_costs(since=since, until=until, db_path=db_path)
    totals: dict[str, float] = {}
    for e in entries:
        name = e.get("backend", "unknown")
        totals[name] = totals.get(name, 0) + (e.get("cost_usd", 0) or 0)
    return totals


def get_savings(
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    db_path: Optional[Path] = None,
) -> float:
    """
    Calculate total savings from smart routing.

    Savings = sum of (max alternative cost - actual cost) for each task.
    """
    entries = query_costs(since=since, until=until, db_path=db_path)
    total_savings = 0.0
    for e in entries:
        actual = e.get("cost_usd", 0) or 0
        alt_costs = e.get("alternative_costs", {}) or {}
        if alt_costs:
            max_alt = max(alt_costs.values())
            if max_alt > actual:
                total_savings += max_alt - actual
    return round(total_savings, 6)


def get_top_tasks(
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    limit: int = 5,
    db_path: Optional[Path] = None,
) -> list[dict]:
    """Get the most expensive tasks in a period."""
    entries = query_costs(since=since, until=until, db_path=db_path)
    # Sort by cost descending
    entries.sort(key=lambda e: e.get("cost_usd", 0) or 0, reverse=True)
    return entries[:limit]


def get_date_range_for_period(period: str) -> tuple[datetime, datetime]:
    """Get (since, until) for a named period: 'today', 'week', 'month'."""
    now = datetime.now(timezone.utc)
    if period == "today":
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        # Start of current week (Monday)
        days_since_monday = now.weekday()
        since = (now - timedelta(days=days_since_monday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    elif period == "month":
        since = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        raise ValueError(f"Unknown period: {period}")

    return since, now
