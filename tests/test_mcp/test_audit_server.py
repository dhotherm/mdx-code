"""Tests for audit MCP server."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mcp_servers.audit.server import get_stats, log_action, query_audit, verify_integrity


@pytest.fixture
def mock_config():
    """Mock config with temp audit directory."""
    config = MagicMock()
    config.audit.directory = "/tmp/test-audit"
    return config


@pytest.fixture
def sample_entries():
    """Sample audit entries for testing."""
    return [
        {
            "entry_id": "id-1",
            "chain_hash": "hash-1",
            "timestamp": "2025-01-15T10:00:00+00:00",
            "task": "fix bug in auth",
            "backend": "claude",
            "model": "claude-3-opus",
            "working_directory": "/home/project",
            "duration_seconds": 12.5,
            "cost_usd": 0.05,
            "status": "success",
        },
        {
            "entry_id": "id-2",
            "chain_hash": "hash-2",
            "timestamp": "2025-01-15T11:00:00+00:00",
            "task": "adversarial_review: src/",
            "backend": "codex",
            "model": None,
            "working_directory": "/home/project",
            "duration_seconds": 8.0,
            "cost_usd": 0.03,
            "status": "success",
        },
    ]


class TestLogAction:
    """Tests for log_action tool."""

    @patch("mcp_servers.audit.server.write_audit_entry")
    def test_log_basic_action(self, mock_write):
        mock_write.return_value = Path("/tmp/audit/2025-01-15.jsonl")

        result = log_action(task="fix bug", backend="claude")

        assert "entry_id" in result
        assert "chain_hash" in result
        assert "filepath" in result
        mock_write.assert_called_once()

        # Verify the AuditEntry was created correctly
        entry = mock_write.call_args[0][0]
        assert entry.task == "fix bug"
        assert entry.backend == "claude"
        assert entry.status == "success"

    @patch("mcp_servers.audit.server.write_audit_entry")
    def test_log_action_with_all_fields(self, mock_write):
        mock_write.return_value = Path("/tmp/audit/2025-01-15.jsonl")

        result = log_action(
            task="generate code",
            backend="codex",
            model="gpt-4",
            files_modified=["src/main.py", "src/utils.py"],
            tokens_in=1000,
            tokens_out=2000,
            cost_usd=0.05,
            duration_seconds=15.5,
        )

        assert "entry_id" in result
        entry = mock_write.call_args[0][0]
        assert entry.model == "gpt-4"
        assert entry.files_modified == ["src/main.py", "src/utils.py"]
        assert entry.tokens_in == 1000
        assert entry.tokens_out == 2000
        assert entry.cost_usd == 0.05
        assert entry.duration_seconds == 15.5

    @patch("mcp_servers.audit.server.write_audit_entry")
    def test_log_action_empty_optional_fields(self, mock_write):
        mock_write.return_value = Path("/tmp/audit/2025-01-15.jsonl")

        log_action(task="test", backend="gemini", model="", tokens_in=0, cost_usd=0.0)

        entry = mock_write.call_args[0][0]
        assert entry.model is None
        assert entry.tokens_in is None
        assert entry.cost_usd is None

    @patch("mcp_servers.audit.server.write_audit_entry")
    def test_log_action_handles_exception(self, mock_write):
        mock_write.side_effect = OSError("disk full")

        result = log_action(task="test", backend="claude")

        assert "error" in result
        assert "disk full" in result["error"]


class TestQueryAudit:
    """Tests for query_audit tool."""

    @patch("mcp_servers.audit.server.read_recent_entries")
    @patch("mcp_servers.audit.server.load_config")
    def test_query_recent(self, mock_config_fn, mock_recent, mock_config, sample_entries):
        mock_config_fn.return_value = mock_config
        mock_recent.return_value = sample_entries

        result = query_audit()

        assert result["count"] == 2
        assert len(result["entries"]) == 2
        mock_recent.assert_called_once()

    @patch("mcp_servers.audit.server.read_filtered_entries")
    @patch("mcp_servers.audit.server.load_config")
    def test_query_with_since_filter(
        self, mock_config_fn, mock_filtered, mock_config, sample_entries
    ):
        mock_config_fn.return_value = mock_config
        mock_filtered.return_value = sample_entries

        result = query_audit(since="2025-01-15")

        assert result["count"] == 2
        mock_filtered.assert_called_once()
        call_kwargs = mock_filtered.call_args
        assert call_kwargs[1]["since"] == "2025-01-15"

    @patch("mcp_servers.audit.server.read_filtered_entries")
    @patch("mcp_servers.audit.server.load_config")
    def test_query_with_path_filter(
        self, mock_config_fn, mock_filtered, mock_config, sample_entries
    ):
        mock_config_fn.return_value = mock_config
        mock_filtered.return_value = sample_entries

        result = query_audit(path="/home/project")

        mock_filtered.assert_called_once()
        call_kwargs = mock_filtered.call_args
        assert call_kwargs[1]["path"] == "/home/project"

    @patch("mcp_servers.audit.server.read_recent_entries")
    @patch("mcp_servers.audit.server.load_config")
    def test_query_with_limit(self, mock_config_fn, mock_recent, mock_config):
        mock_config_fn.return_value = mock_config
        mock_recent.return_value = [{"entry_id": "1"}]

        result = query_audit(limit=5)

        mock_recent.assert_called_once_with(Path("/tmp/test-audit"), count=5)

    @patch("mcp_servers.audit.server.read_filtered_entries")
    @patch("mcp_servers.audit.server.load_config")
    def test_query_respects_limit_on_filtered(self, mock_config_fn, mock_filtered, mock_config):
        mock_config_fn.return_value = mock_config
        mock_filtered.return_value = [{"id": str(i)} for i in range(50)]

        result = query_audit(since="2025-01-01", limit=10)

        assert result["count"] == 10

    @patch("mcp_servers.audit.server.load_config")
    def test_query_handles_exception(self, mock_config_fn):
        mock_config_fn.side_effect = RuntimeError("config error")

        result = query_audit()

        assert "error" in result


class TestVerifyIntegrity:
    """Tests for verify_integrity tool."""

    @patch("mcp_servers.audit.server.verify_audit_integrity")
    @patch("mcp_servers.audit.server.load_config")
    def test_all_files_valid(self, mock_config_fn, mock_verify, mock_config, tmp_path):
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        (audit_dir / "2025-01-15.jsonl").write_text('{"entry": 1}\n')
        mock_config.audit.directory = str(audit_dir)
        mock_config_fn.return_value = mock_config
        mock_verify.return_value = (True, None)

        result = verify_integrity()

        assert result["valid"] is True
        assert result["files_checked"] == 1

    @patch("mcp_servers.audit.server.verify_audit_integrity")
    @patch("mcp_servers.audit.server.load_config")
    def test_tampered_file_detected(self, mock_config_fn, mock_verify, mock_config, tmp_path):
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        (audit_dir / "2025-01-15.jsonl").write_text('{"entry": 1}\n')
        mock_config.audit.directory = str(audit_dir)
        mock_config_fn.return_value = mock_config
        mock_verify.return_value = (False, "Integrity violation at line 2")

        result = verify_integrity()

        assert result["valid"] is False
        assert result["results"][0]["valid"] is False
        assert "line 2" in result["results"][0]["error"]

    @patch("mcp_servers.audit.server.load_config")
    def test_no_audit_directory(self, mock_config_fn, mock_config, tmp_path):
        mock_config.audit.directory = str(tmp_path / "nonexistent")
        mock_config_fn.return_value = mock_config

        result = verify_integrity()

        assert result["valid"] is True
        assert result["files_checked"] == 0

    @patch("mcp_servers.audit.server.load_config")
    def test_empty_audit_directory(self, mock_config_fn, mock_config, tmp_path):
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        mock_config.audit.directory = str(audit_dir)
        mock_config_fn.return_value = mock_config

        result = verify_integrity()

        assert result["valid"] is True
        assert result["files_checked"] == 0

    @patch("mcp_servers.audit.server.load_config")
    def test_verify_handles_exception(self, mock_config_fn):
        mock_config_fn.side_effect = RuntimeError("fail")

        result = verify_integrity()

        assert "error" in result


class TestGetStats:
    """Tests for get_stats tool."""

    @patch("mcp_servers.audit.server.compute_audit_stats")
    @patch("mcp_servers.audit.server.read_filtered_entries")
    @patch("mcp_servers.audit.server.load_config")
    def test_get_stats_with_entries(self, mock_config_fn, mock_filtered, mock_stats, mock_config):
        mock_config_fn.return_value = mock_config
        mock_filtered.return_value = [{"entry_id": "1"}, {"entry_id": "2"}]
        mock_stats.return_value = {
            "total_actions": 2,
            "tasks": 1,
            "reviews": 1,
            "policy_checks": 0,
            "by_backend": {"claude": 1, "codex": 1},
            "policy_violations": 0,
            "total_cost": 0.08,
        }

        result = get_stats(days=7)

        assert result["total_actions"] == 2
        assert result["period_days"] == 7
        assert result["total_cost"] == 0.08

    @patch("mcp_servers.audit.server.read_filtered_entries")
    @patch("mcp_servers.audit.server.load_config")
    def test_get_stats_no_entries(self, mock_config_fn, mock_filtered, mock_config):
        mock_config_fn.return_value = mock_config
        mock_filtered.return_value = []

        result = get_stats(days=30)

        assert result["total_actions"] == 0
        assert result["period_days"] == 30

    @patch("mcp_servers.audit.server.read_filtered_entries")
    @patch("mcp_servers.audit.server.load_config")
    def test_get_stats_default_days(self, mock_config_fn, mock_filtered, mock_config):
        mock_config_fn.return_value = mock_config
        mock_filtered.return_value = []

        result = get_stats()

        assert result["period_days"] == 30

    @patch("mcp_servers.audit.server.load_config")
    def test_get_stats_handles_exception(self, mock_config_fn):
        mock_config_fn.side_effect = RuntimeError("config fail")

        result = get_stats()

        assert "error" in result
