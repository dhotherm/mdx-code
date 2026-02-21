"""Tests for cost tracking with SQLite."""

import json
from datetime import datetime, timedelta, timezone

import pytest

from mdxcode.router.cost_tracker import (
    get_cost_by_backend,
    get_date_range_for_period,
    get_savings,
    get_top_tasks,
    get_total_cost,
    query_costs,
    record_cost,
)


@pytest.fixture
def db_path(tmp_path):
    """Provide a temporary database path."""
    return tmp_path / "test_costs.db"


class TestRecordCost:
    """Tests for recording cost entries."""

    def test_record_basic(self, db_path):
        entry_id = record_cost(
            session_id="sess-1",
            backend="claude",
            cost_usd=0.42,
            db_path=db_path,
        )
        assert entry_id is not None
        assert len(entry_id) == 36  # UUID format

    def test_record_with_all_fields(self, db_path):
        entry_id = record_cost(
            session_id="sess-2",
            backend="codex",
            model="gpt-5.1",
            task_category="test_writing",
            task_summary="Write tests for auth module",
            tokens_in=1500,
            tokens_out=3000,
            cost_usd=0.18,
            estimated=False,
            routing_strategy="balanced",
            alternative_costs={"claude": 0.42, "gemini": 0.08},
            db_path=db_path,
        )

        entries = query_costs(db_path=db_path)
        assert len(entries) == 1
        entry = entries[0]
        assert entry["backend"] == "codex"
        assert entry["model"] == "gpt-5.1"
        assert entry["task_category"] == "test_writing"
        assert entry["tokens_in"] == 1500
        assert entry["tokens_out"] == 3000
        assert entry["cost_usd"] == 0.18
        assert entry["estimated"] is False
        assert entry["routing_strategy"] == "balanced"
        assert entry["alternative_costs"]["claude"] == 0.42
        assert entry["alternative_costs"]["gemini"] == 0.08

    def test_record_estimated_cost(self, db_path):
        record_cost(
            session_id="sess-3",
            backend="gemini",
            cost_usd=0.05,
            estimated=True,
            db_path=db_path,
        )

        entries = query_costs(db_path=db_path)
        assert entries[0]["estimated"] is True

    def test_record_multiple_entries(self, db_path):
        for i in range(5):
            record_cost(
                session_id=f"sess-{i}",
                backend="claude",
                cost_usd=float(i),
                db_path=db_path,
            )

        entries = query_costs(db_path=db_path)
        assert len(entries) == 5

    def test_long_task_summary_truncated(self, db_path):
        long_summary = "x" * 500
        record_cost(
            session_id="sess-long",
            backend="claude",
            task_summary=long_summary,
            db_path=db_path,
        )

        entries = query_costs(db_path=db_path)
        assert len(entries[0]["task_summary"]) <= 200


class TestQueryCosts:
    """Tests for querying cost entries."""

    def test_query_by_date_range(self, db_path):
        # Record some entries
        for i in range(3):
            record_cost(
                session_id=f"sess-{i}",
                backend="claude",
                cost_usd=1.0,
                db_path=db_path,
            )

        now = datetime.now(timezone.utc)
        entries = query_costs(
            since=now - timedelta(hours=1),
            until=now + timedelta(hours=1),
            db_path=db_path,
        )
        assert len(entries) == 3

    def test_query_by_backend(self, db_path):
        record_cost(session_id="s1", backend="claude", cost_usd=1.0, db_path=db_path)
        record_cost(session_id="s2", backend="codex", cost_usd=2.0, db_path=db_path)
        record_cost(session_id="s3", backend="claude", cost_usd=3.0, db_path=db_path)

        entries = query_costs(backend="claude", db_path=db_path)
        assert len(entries) == 2
        assert all(e["backend"] == "claude" for e in entries)

    def test_query_empty_db(self, db_path):
        entries = query_costs(db_path=db_path)
        assert entries == []

    def test_query_returns_descending_order(self, db_path):
        for i in range(3):
            record_cost(
                session_id=f"sess-{i}",
                backend="claude",
                cost_usd=float(i),
                db_path=db_path,
            )

        entries = query_costs(db_path=db_path)
        # Should be descending by timestamp
        assert entries[0]["session_id"] == "sess-2"
        assert entries[-1]["session_id"] == "sess-0"


class TestGetTotalCost:
    """Tests for total cost calculation."""

    def test_total_cost(self, db_path):
        record_cost(session_id="s1", backend="claude", cost_usd=1.50, db_path=db_path)
        record_cost(session_id="s2", backend="codex", cost_usd=0.75, db_path=db_path)
        record_cost(session_id="s3", backend="gemini", cost_usd=0.25, db_path=db_path)

        total = get_total_cost(db_path=db_path)
        assert total == 2.50

    def test_total_cost_empty(self, db_path):
        total = get_total_cost(db_path=db_path)
        assert total == 0.0

    def test_total_cost_with_null_values(self, db_path):
        record_cost(session_id="s1", backend="claude", cost_usd=1.00, db_path=db_path)
        record_cost(session_id="s2", backend="codex", cost_usd=None, db_path=db_path)

        total = get_total_cost(db_path=db_path)
        assert total == 1.0


class TestGetCostByBackend:
    """Tests for per-backend cost breakdown."""

    def test_breakdown(self, db_path):
        record_cost(session_id="s1", backend="claude", cost_usd=10.0, db_path=db_path)
        record_cost(session_id="s2", backend="codex", cost_usd=3.0, db_path=db_path)
        record_cost(session_id="s3", backend="claude", cost_usd=5.0, db_path=db_path)
        record_cost(session_id="s4", backend="gemini", cost_usd=1.0, db_path=db_path)

        breakdown = get_cost_by_backend(db_path=db_path)
        assert breakdown["claude"] == 15.0
        assert breakdown["codex"] == 3.0
        assert breakdown["gemini"] == 1.0

    def test_empty_breakdown(self, db_path):
        breakdown = get_cost_by_backend(db_path=db_path)
        assert breakdown == {}


class TestGetSavings:
    """Tests for savings calculation."""

    def test_savings_from_alternatives(self, db_path):
        # Used codex at $0.18, but claude would have cost $0.42
        record_cost(
            session_id="s1",
            backend="codex",
            cost_usd=0.18,
            alternative_costs={"claude": 0.42, "gemini": 0.08},
            db_path=db_path,
        )

        savings = get_savings(db_path=db_path)
        assert savings == pytest.approx(0.24, abs=0.01)  # 0.42 - 0.18

    def test_no_savings_when_most_expensive(self, db_path):
        # Used claude at $0.42, alternatives were cheaper
        record_cost(
            session_id="s1",
            backend="claude",
            cost_usd=0.42,
            alternative_costs={"codex": 0.18, "gemini": 0.08},
            db_path=db_path,
        )

        savings = get_savings(db_path=db_path)
        assert savings == 0.0

    def test_savings_accumulated(self, db_path):
        record_cost(
            session_id="s1",
            backend="codex",
            cost_usd=0.10,
            alternative_costs={"claude": 0.40},
            db_path=db_path,
        )
        record_cost(
            session_id="s2",
            backend="gemini",
            cost_usd=0.05,
            alternative_costs={"claude": 0.35},
            db_path=db_path,
        )

        savings = get_savings(db_path=db_path)
        assert savings == pytest.approx(0.60, abs=0.01)  # (0.40-0.10) + (0.35-0.05)

    def test_no_alternatives(self, db_path):
        record_cost(
            session_id="s1",
            backend="claude",
            cost_usd=0.42,
            db_path=db_path,
        )

        savings = get_savings(db_path=db_path)
        assert savings == 0.0


class TestGetTopTasks:
    """Tests for top tasks by cost."""

    def test_top_tasks_sorted_by_cost(self, db_path):
        record_cost(session_id="s1", backend="claude", cost_usd=1.0,
                     task_summary="Small task", db_path=db_path)
        record_cost(session_id="s2", backend="claude", cost_usd=5.0,
                     task_summary="Big task", db_path=db_path)
        record_cost(session_id="s3", backend="claude", cost_usd=3.0,
                     task_summary="Medium task", db_path=db_path)

        top = get_top_tasks(limit=2, db_path=db_path)
        assert len(top) == 2
        assert top[0]["task_summary"] == "Big task"
        assert top[1]["task_summary"] == "Medium task"

    def test_top_tasks_limit(self, db_path):
        for i in range(10):
            record_cost(session_id=f"s{i}", backend="claude",
                         cost_usd=float(i), db_path=db_path)

        top = get_top_tasks(limit=3, db_path=db_path)
        assert len(top) == 3


class TestGetDateRangeForPeriod:
    """Tests for date range helpers."""

    def test_today(self):
        since, until = get_date_range_for_period("today")
        assert since.hour == 0
        assert since.minute == 0
        assert since.second == 0
        assert until > since

    def test_week(self):
        since, until = get_date_range_for_period("week")
        assert since.weekday() == 0  # Monday
        assert until > since

    def test_month(self):
        since, until = get_date_range_for_period("month")
        assert since.day == 1
        assert until > since

    def test_invalid_period(self):
        with pytest.raises(ValueError, match="Unknown period"):
            get_date_range_for_period("year")
