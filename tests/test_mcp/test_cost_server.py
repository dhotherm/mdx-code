"""Tests for cost MCP server."""

from unittest.mock import patch

import pytest

from mcp_servers.cost.server import get_summary, log_cost


class TestLogCost:
    """Tests for log_cost tool."""

    @patch("mcp_servers.cost.server.get_total_cost")
    @patch("mcp_servers.cost.server.get_date_range_for_period")
    @patch("mcp_servers.cost.server.record_cost")
    def test_log_basic_cost(self, mock_record, mock_period, mock_total):
        mock_record.return_value = "entry-123"
        mock_period.return_value = ("2025-01-15T00:00:00", "2025-01-15T23:59:59")
        mock_total.return_value = 1.25

        result = log_cost(backend="claude", cost_usd=0.05)

        assert result["entry_id"] == "entry-123"
        assert result["daily_total"] == 1.25
        mock_record.assert_called_once()

    @patch("mcp_servers.cost.server.get_total_cost")
    @patch("mcp_servers.cost.server.get_date_range_for_period")
    @patch("mcp_servers.cost.server.record_cost")
    def test_log_cost_with_all_fields(self, mock_record, mock_period, mock_total):
        mock_record.return_value = "entry-456"
        mock_period.return_value = ("2025-01-15T00:00:00", "2025-01-15T23:59:59")
        mock_total.return_value = 2.50

        result = log_cost(
            backend="codex",
            model="gpt-4",
            tokens_in=1000,
            tokens_out=2000,
            cost_usd=0.10,
            task_category="code_generation",
        )

        assert result["entry_id"] == "entry-456"
        call_kwargs = mock_record.call_args[1]
        assert call_kwargs["backend"] == "codex"
        assert call_kwargs["model"] == "gpt-4"
        assert call_kwargs["tokens_in"] == 1000
        assert call_kwargs["tokens_out"] == 2000
        assert call_kwargs["cost_usd"] == 0.10
        assert call_kwargs["task_category"] == "code_generation"

    @patch("mcp_servers.cost.server.get_total_cost")
    @patch("mcp_servers.cost.server.get_date_range_for_period")
    @patch("mcp_servers.cost.server.record_cost")
    def test_log_cost_empty_optional_fields(self, mock_record, mock_period, mock_total):
        mock_record.return_value = "entry-789"
        mock_period.return_value = ("2025-01-15T00:00:00", "2025-01-15T23:59:59")
        mock_total.return_value = 0.0

        log_cost(backend="gemini", model="", tokens_in=0, cost_usd=0.0)

        call_kwargs = mock_record.call_args[1]
        assert call_kwargs["model"] is None
        assert call_kwargs["tokens_in"] is None
        assert call_kwargs["cost_usd"] is None

    @patch("mcp_servers.cost.server.record_cost")
    def test_log_cost_handles_exception(self, mock_record):
        mock_record.side_effect = RuntimeError("db error")

        result = log_cost(backend="claude")

        assert "error" in result
        assert "db error" in result["error"]


class TestGetSummary:
    """Tests for get_summary tool."""

    @patch("mcp_servers.cost.server.get_top_tasks")
    @patch("mcp_servers.cost.server.get_savings")
    @patch("mcp_servers.cost.server.get_cost_by_backend")
    @patch("mcp_servers.cost.server.get_total_cost")
    @patch("mcp_servers.cost.server.get_date_range_for_period")
    def test_get_summary_week(
        self, mock_period, mock_total, mock_by_backend, mock_savings, mock_top
    ):
        mock_period.return_value = ("2025-01-13T00:00:00", "2025-01-15T23:59:59")
        mock_total.return_value = 5.50
        mock_by_backend.return_value = {"claude": 3.00, "codex": 2.50}
        mock_savings.return_value = 1.25
        mock_top.return_value = [
            {
                "task_summary": "fix auth bug",
                "backend": "claude",
                "cost_usd": 0.50,
                "timestamp": "2025-01-15",
            },
        ]

        result = get_summary(period="week")

        assert result["period"] == "week"
        assert result["total_usd"] == 5.5
        assert result["by_backend"]["claude"] == 3.0
        assert result["savings_usd"] == 1.25
        assert len(result["top_tasks"]) == 1

    @patch("mcp_servers.cost.server.get_top_tasks")
    @patch("mcp_servers.cost.server.get_savings")
    @patch("mcp_servers.cost.server.get_cost_by_backend")
    @patch("mcp_servers.cost.server.get_total_cost")
    @patch("mcp_servers.cost.server.get_date_range_for_period")
    def test_get_summary_today(
        self, mock_period, mock_total, mock_by_backend, mock_savings, mock_top
    ):
        mock_period.return_value = ("2025-01-15T00:00:00", "2025-01-15T23:59:59")
        mock_total.return_value = 0.0
        mock_by_backend.return_value = {}
        mock_savings.return_value = 0.0
        mock_top.return_value = []

        result = get_summary(period="today")

        assert result["period"] == "today"
        assert result["total_usd"] == 0.0
        assert result["by_backend"] == {}
        assert result["top_tasks"] == []

    @patch("mcp_servers.cost.server.get_top_tasks")
    @patch("mcp_servers.cost.server.get_savings")
    @patch("mcp_servers.cost.server.get_cost_by_backend")
    @patch("mcp_servers.cost.server.get_total_cost")
    @patch("mcp_servers.cost.server.get_date_range_for_period")
    def test_get_summary_month(
        self, mock_period, mock_total, mock_by_backend, mock_savings, mock_top
    ):
        mock_period.return_value = ("2025-01-01T00:00:00", "2025-01-15T23:59:59")
        mock_total.return_value = 25.0
        mock_by_backend.return_value = {"claude": 15.0, "gemini": 10.0}
        mock_savings.return_value = 5.0
        mock_top.return_value = []

        result = get_summary(period="month")

        assert result["period"] == "month"
        assert result["total_usd"] == 25.0

    @patch("mcp_servers.cost.server.get_date_range_for_period")
    def test_get_summary_invalid_period(self, mock_period):
        mock_period.side_effect = ValueError("Unknown period: yearly")

        result = get_summary(period="yearly")

        assert "error" in result
        assert "Invalid period" in result["error"]

    @patch("mcp_servers.cost.server.get_top_tasks")
    @patch("mcp_servers.cost.server.get_savings")
    @patch("mcp_servers.cost.server.get_cost_by_backend")
    @patch("mcp_servers.cost.server.get_total_cost")
    @patch("mcp_servers.cost.server.get_date_range_for_period")
    def test_get_summary_default_period(
        self, mock_period, mock_total, mock_by_backend, mock_savings, mock_top
    ):
        mock_period.return_value = ("2025-01-13T00:00:00", "2025-01-15T23:59:59")
        mock_total.return_value = 0.0
        mock_by_backend.return_value = {}
        mock_savings.return_value = 0.0
        mock_top.return_value = []

        result = get_summary()

        mock_period.assert_called_once_with("week")

    @patch("mcp_servers.cost.server.get_date_range_for_period")
    def test_get_summary_handles_exception(self, mock_period):
        mock_period.side_effect = RuntimeError("unexpected")

        result = get_summary()

        assert "error" in result

    @patch("mcp_servers.cost.server.get_top_tasks")
    @patch("mcp_servers.cost.server.get_savings")
    @patch("mcp_servers.cost.server.get_cost_by_backend")
    @patch("mcp_servers.cost.server.get_total_cost")
    @patch("mcp_servers.cost.server.get_date_range_for_period")
    def test_get_summary_rounds_values(
        self, mock_period, mock_total, mock_by_backend, mock_savings, mock_top
    ):
        mock_period.return_value = ("2025-01-13T00:00:00", "2025-01-15T23:59:59")
        mock_total.return_value = 1.23456789
        mock_by_backend.return_value = {"claude": 0.987654321}
        mock_savings.return_value = 0.123456789
        mock_top.return_value = []

        result = get_summary()

        assert result["total_usd"] == 1.2346
        assert result["by_backend"]["claude"] == 0.9877
        assert result["savings_usd"] == 0.1235
