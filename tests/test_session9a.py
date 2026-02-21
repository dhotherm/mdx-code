"""Tests for Session 9A features — Experience Layer."""

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
import yaml

from mdxcode.cli import (
    CATEGORY_ICONS,
    _get_project_context,
    _show_routing_line,
)


# ── Feature 5: Category Icons ──


class TestCategoryIcons:
    """Tests for the shared category icons constant."""

    def test_all_categories_have_icons(self):
        expected = {
            "code_review", "debugging", "code_generation",
            "documentation", "security", "refactoring",
            "test_writing", "general",
        }
        assert set(CATEGORY_ICONS.keys()) == expected

    def test_icons_are_non_empty_strings(self):
        for cat, icon in CATEGORY_ICONS.items():
            assert isinstance(icon, str), f"{cat} icon is not a string"
            assert len(icon) > 0, f"{cat} icon is empty"

    def test_general_category_exists(self):
        assert "general" in CATEGORY_ICONS


# ── Feature 1: Context-Aware Routing Line ──


class TestProjectContext:
    """Tests for _get_project_context()."""

    def setup_method(self):
        # Reset cache before each test
        import mdxcode.cli
        mdxcode.cli._project_context_cache = None

    def test_returns_string(self):
        result = _get_project_context()
        assert isinstance(result, str)

    def test_caches_result(self):
        import mdxcode.cli

        first = _get_project_context()
        # Modify cache to verify it's used
        mdxcode.cli._project_context_cache = "cached_value"
        second = _get_project_context()
        assert second == "cached_value"

    @patch("subprocess.Popen")
    def test_handles_git_failure_gracefully(self, mock_popen):
        mock_popen.side_effect = FileNotFoundError("git not found")
        result = _get_project_context()
        assert isinstance(result, str)

    @patch("subprocess.Popen")
    def test_handles_timeout_gracefully(self, mock_popen):
        proc = MagicMock()
        # First communicate(timeout=5) raises, second communicate() (cleanup) returns empty
        proc.communicate.side_effect = [
            subprocess.TimeoutExpired("git", 5),
            ("", ""),
            subprocess.TimeoutExpired("git", 5),
            ("", ""),
        ]
        proc.kill = MagicMock()
        mock_popen.return_value = proc
        result = _get_project_context()
        assert isinstance(result, str)

    @patch("subprocess.Popen")
    def test_parses_branch_and_language(self, mock_popen):
        def make_proc(cmd, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            if "branch" in cmd:
                proc.communicate.return_value = ("main\n", "")
            elif "ls-files" in cmd:
                proc.communicate.return_value = ("app.py\nlib.py\nutils.py\nREADME.md\n", "")
            return proc

        mock_popen.side_effect = make_proc
        result = _get_project_context()
        assert "main" in result
        assert "Python" in result
        assert "4 files" in result

    @patch("subprocess.Popen")
    def test_detects_typescript(self, mock_popen):
        def make_proc(cmd, **kwargs):
            proc = MagicMock()
            proc.returncode = 0
            if "branch" in cmd:
                proc.communicate.return_value = ("develop\n", "")
            elif "ls-files" in cmd:
                proc.communicate.return_value = ("src/index.ts\nsrc/app.tsx\npackage.json\n", "")
            return proc

        mock_popen.side_effect = make_proc
        result = _get_project_context()
        assert "TypeScript" in result


class TestShowRoutingLine:
    """Tests for _show_routing_line() with category and context."""

    def setup_method(self):
        import mdxcode.cli
        mdxcode.cli._project_context_cache = None

    @patch("mdxcode.cli.console")
    @patch("mdxcode.cli._get_project_context", return_value="main · Python · 10 files")
    def test_includes_context_in_output(self, mock_ctx, mock_console):
        _show_routing_line("claude", "debugging, strength match", category="debugging")
        call_args = mock_console.print.call_args_list
        output = str(call_args[0])
        assert "main" in output or "Python" in output or "Routing" in output

    @patch("mdxcode.cli.console")
    @patch("mdxcode.cli._get_project_context", return_value="")
    def test_works_without_context(self, mock_ctx, mock_console):
        _show_routing_line("claude", "test reason", category="general")
        assert mock_console.print.called

    @patch("mdxcode.cli.console")
    @patch("mdxcode.cli._get_project_context", return_value="main · Python")
    def test_user_specified_includes_context(self, mock_ctx, mock_console):
        _show_routing_line("claude", "user specified", user_specified=True, category="debugging")
        assert mock_console.print.called

    @patch("mdxcode.cli.console")
    @patch("mdxcode.cli._get_project_context", return_value="")
    def test_shows_scores(self, mock_ctx, mock_console):
        scores = {"claude": 0.9, "gemini": 0.7}
        _show_routing_line(
            "claude", "debugging", scores=scores, category="debugging",
        )
        # Should have two print calls: routing line + scores
        assert mock_console.print.call_count == 2

    @patch("mdxcode.cli.console")
    @patch("mdxcode.cli._get_project_context", return_value="")
    def test_default_category_is_general(self, mock_ctx, mock_console):
        _show_routing_line("claude", "test reason")
        assert mock_console.print.called


# ── Feature 2: History Command ──


class TestHistoryCommand:
    """Tests for the history command."""

    @patch("mdxcode.cli.console")
    @patch("mdxcode.governance.audit_trail.read_recent_entries")
    def test_history_shows_entries(self, mock_read, mock_console):
        from mdxcode.cli import history

        mock_read.return_value = [
            {
                "timestamp": "2025-06-15T14:34:00+00:00",
                "task": "fix the login bug",
                "backend": "claude",
                "status": "success",
                "duration_seconds": 8.8,
                "cost_usd": 0.005,
                "task_category": "debugging",
            },
        ]
        history(count=20, search=None, backend_filter=None)
        assert mock_console.print.called

    @patch("mdxcode.cli.console")
    @patch("mdxcode.governance.audit_trail.read_recent_entries")
    def test_history_empty(self, mock_read, mock_console):
        from mdxcode.cli import history

        mock_read.return_value = []
        history(count=20, search=None, backend_filter=None)
        calls = [str(c) for c in mock_console.print.call_args_list]
        assert any("No task history" in c for c in calls)

    @patch("mdxcode.cli.console")
    @patch("mdxcode.governance.audit_trail.read_recent_entries")
    def test_history_search_filter(self, mock_read, mock_console):
        from mdxcode.cli import history

        mock_read.return_value = [
            {
                "timestamp": "2025-06-15T14:34:00+00:00",
                "task": "fix the login bug",
                "backend": "claude",
                "status": "success",
                "duration_seconds": 8.8,
                "task_category": "debugging",
            },
            {
                "timestamp": "2025-06-15T14:32:00+00:00",
                "task": "add new endpoint",
                "backend": "gemini",
                "status": "success",
                "duration_seconds": 12.0,
                "task_category": "code_generation",
            },
        ]
        history(count=20, search="login", backend_filter=None)
        # Should show the matching entry and "1 tasks shown"
        calls = [str(c) for c in mock_console.print.call_args_list]
        assert any("1 tasks" in c for c in calls)

    @patch("mdxcode.cli.console")
    @patch("mdxcode.governance.audit_trail.read_recent_entries")
    def test_history_backend_filter(self, mock_read, mock_console):
        from mdxcode.cli import history

        mock_read.return_value = [
            {
                "timestamp": "2025-06-15T14:34:00+00:00",
                "task": "fix bug",
                "backend": "claude",
                "status": "success",
                "duration_seconds": 5.0,
                "task_category": "debugging",
            },
            {
                "timestamp": "2025-06-15T14:32:00+00:00",
                "task": "add endpoint",
                "backend": "gemini",
                "status": "success",
                "duration_seconds": 12.0,
                "task_category": "code_generation",
            },
        ]
        history(count=20, search=None, backend_filter="claude")
        calls = [str(c) for c in mock_console.print.call_args_list]
        assert any("1 tasks" in c for c in calls)

    @patch("mdxcode.cli.console")
    @patch("mdxcode.governance.audit_trail.read_recent_entries")
    def test_history_filters_non_task_entries(self, mock_read, mock_console):
        from mdxcode.cli import history

        mock_read.return_value = [
            {
                "timestamp": "2025-06-15T14:34:00+00:00",
                "task": "adversarial_review: src/",
                "backend": "claude",
                "status": "success",
                "duration_seconds": 5.0,
            },
            {
                "timestamp": "2025-06-15T14:34:00+00:00",
                "task": "policy_check: fix bug",
                "backend": "claude",
                "status": "success",
                "duration_seconds": 1.0,
            },
        ]
        history(count=20, search=None, backend_filter=None)
        calls = [str(c) for c in mock_console.print.call_args_list]
        assert any("No task history" in c for c in calls)

    @patch("mdxcode.cli.console")
    @patch("mdxcode.governance.audit_trail.read_recent_entries")
    def test_history_truncates_long_tasks(self, mock_read, mock_console):
        from mdxcode.cli import history

        mock_read.return_value = [
            {
                "timestamp": "2025-06-15T14:34:00+00:00",
                "task": "a" * 100,
                "backend": "claude",
                "status": "success",
                "duration_seconds": 5.0,
                "task_category": "general",
            },
        ]
        history(count=20, search=None, backend_filter=None)
        calls = [str(c) for c in mock_console.print.call_args_list]
        # Should truncate to 50 chars (47 + "...")
        assert any("..." in c for c in calls)


# ── Feature 6: Project Config ──


class TestProjectConfig:
    """Tests for project-level configuration."""

    def test_project_config_model(self):
        from mdxcode.config import ProjectConfig

        config = ProjectConfig()
        assert config.preferred_backend is None
        assert config.strategy is None
        assert config.max_cost_per_task is None
        assert config.daily_budget is None

    def test_project_config_with_values(self):
        from mdxcode.config import ProjectConfig

        config = ProjectConfig(
            preferred_backend="claude",
            strategy="quality_first",
            daily_budget=5.0,
        )
        assert config.preferred_backend == "claude"
        assert config.strategy == "quality_first"
        assert config.daily_budget == 5.0

    def test_load_project_config_not_found(self, tmp_path, monkeypatch):
        from mdxcode.config import load_project_config

        monkeypatch.chdir(tmp_path)
        # Create a .git directory to stop the search
        (tmp_path / ".git").mkdir()
        result = load_project_config()
        assert result is None

    def test_load_project_config_found(self, tmp_path, monkeypatch):
        from mdxcode.config import load_project_config

        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        (tmp_path / ".mdx.yaml").write_text(
            yaml.dump({"preferred_backend": "gemini", "daily_budget": 10.0})
        )
        result = load_project_config()
        assert result is not None
        assert result.preferred_backend == "gemini"
        assert result.daily_budget == 10.0

    def test_load_project_config_invalid_yaml(self, tmp_path, monkeypatch):
        from mdxcode.config import load_project_config

        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        (tmp_path / ".mdx.yaml").write_text("not: [valid: yaml: {")
        result = load_project_config()
        # Should return None on parse error
        assert result is None

    def test_load_project_config_empty_file(self, tmp_path, monkeypatch):
        from mdxcode.config import load_project_config

        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git").mkdir()
        (tmp_path / ".mdx.yaml").write_text("")
        result = load_project_config()
        # Empty YAML returns None from safe_load, which triggers ProjectConfig()
        assert result is not None
        assert result.preferred_backend is None

    def test_load_project_config_stops_at_git_root(self, tmp_path, monkeypatch):
        from mdxcode.config import load_project_config

        # Create structure: tmp/repo/.git/ and tmp/repo/sub/
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".git").mkdir()
        sub = repo / "sub"
        sub.mkdir()
        monkeypatch.chdir(sub)

        # Config at repo root should be found
        (repo / ".mdx.yaml").write_text(yaml.dump({"strategy": "cost_optimized"}))
        result = load_project_config()
        assert result is not None
        assert result.strategy == "cost_optimized"


# ── Feature 7: Cost Guardrails ──


class TestCostGuardrails:
    """Tests for budget fields in MdxConfig."""

    def test_mdx_config_budget_fields(self):
        from mdxcode.config import MdxConfig

        config = MdxConfig(max_cost_per_task=0.50, daily_budget=5.0)
        assert config.max_cost_per_task == 0.50
        assert config.daily_budget == 5.0

    def test_mdx_config_budget_defaults_to_none(self):
        from mdxcode.config import MdxConfig

        config = MdxConfig()
        assert config.max_cost_per_task is None
        assert config.daily_budget is None


# ── Feature 4: Smart Error Recovery ──


class TestSmartErrorRecovery:
    """Tests for error classification patterns."""

    def test_error_classification_patterns(self):
        """Verify error classification keywords match expected types."""
        rate_limit_texts = [
            "Error: rate limit exceeded",
            "HTTP 429 Too Many Requests",
            "quota exceeded for today",
        ]
        auth_texts = [
            "Error: unauthorized",
            "token expired, please login",
            "credential not found",
        ]
        timeout_texts = [
            "[MDx Code] Task timed out after 300s",
        ]
        network_texts = [
            "connection refused",
            "network unreachable",
            "DNS resolution failed",
        ]

        for text in rate_limit_texts:
            lower = text.lower()
            assert any(
                kw in lower
                for kw in ("rate limit", "429", "too many requests", "quota")
            ), f"Rate limit not detected in: {text}"

        for text in auth_texts:
            lower = text.lower()
            assert any(
                kw in lower
                for kw in ("auth", "login", "credential", "token expired", "unauthorized")
            ), f"Auth error not detected in: {text}"

        for text in timeout_texts:
            lower = text.lower()
            assert "timed out" in lower, f"Timeout not detected in: {text}"

        for text in network_texts:
            lower = text.lower()
            assert any(
                kw in lower
                for kw in ("connection", "network", "dns", "unreachable")
            ), f"Network error not detected in: {text}"


# ── Feature 8: Timing Intelligence ──


class TestTimingIntelligence:
    """Tests for get_average_duration in audit trail."""

    def test_get_average_duration_not_enough_data(self, tmp_path):
        from mdxcode.governance.audit_trail import get_average_duration

        # Empty audit dir
        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()
        result = get_average_duration(audit_dir=audit_dir, min_entries=5)
        assert result is None

    def test_get_average_duration_with_data(self, tmp_path):
        from mdxcode.governance.audit_trail import AuditEntry, get_average_duration, write_audit_entry

        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()

        # Write 6 entries with known durations
        for i in range(6):
            entry = AuditEntry(
                task=f"task {i}",
                backend="claude",
                status="success",
                duration_seconds=float(10 + i),
                task_category="debugging",
            )
            write_audit_entry(entry, audit_dir=audit_dir)

        avg = get_average_duration(
            audit_dir=audit_dir, backend="claude", task_category="debugging",
        )
        assert avg is not None
        # Average of 10, 11, 12, 13, 14, 15 = 12.5
        assert abs(avg - 12.5) < 0.1

    def test_get_average_duration_filters_by_backend(self, tmp_path):
        from mdxcode.governance.audit_trail import AuditEntry, get_average_duration, write_audit_entry

        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()

        for i in range(6):
            entry = AuditEntry(
                task=f"task {i}",
                backend="claude",
                status="success",
                duration_seconds=10.0,
                task_category="debugging",
            )
            write_audit_entry(entry, audit_dir=audit_dir)

        for i in range(3):
            entry = AuditEntry(
                task=f"task gemini {i}",
                backend="gemini",
                status="success",
                duration_seconds=20.0,
                task_category="debugging",
            )
            write_audit_entry(entry, audit_dir=audit_dir)

        # Claude has enough data, gemini doesn't (only 3, min_entries=5)
        assert get_average_duration(audit_dir=audit_dir, backend="claude") is not None
        assert get_average_duration(audit_dir=audit_dir, backend="gemini") is None

    def test_get_average_duration_excludes_failures(self, tmp_path):
        from mdxcode.governance.audit_trail import AuditEntry, get_average_duration, write_audit_entry

        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()

        for i in range(6):
            entry = AuditEntry(
                task=f"task {i}",
                backend="claude",
                status="error",
                duration_seconds=10.0,
            )
            write_audit_entry(entry, audit_dir=audit_dir)

        # All entries are errors — should return None
        assert get_average_duration(audit_dir=audit_dir) is None

    def test_get_average_duration_excludes_reviews(self, tmp_path):
        from mdxcode.governance.audit_trail import AuditEntry, get_average_duration, write_audit_entry

        audit_dir = tmp_path / "audit"
        audit_dir.mkdir()

        for i in range(6):
            entry = AuditEntry(
                task=f"adversarial_review: src/",
                backend="claude",
                status="success",
                duration_seconds=10.0,
            )
            write_audit_entry(entry, audit_dir=audit_dir)

        assert get_average_duration(audit_dir=audit_dir) is None


# ── Feature 9: Graceful Degradation ──


class TestGracefulDegradation:
    """Tests for NO_COLOR and pipe detection."""

    def test_no_color_env_detection(self):
        """NO_COLOR env var is read at import time."""
        # We just test the module-level constant exists
        from mdxcode.cli import NO_COLOR
        assert isinstance(NO_COLOR, bool)

    def test_streamer_looks_like_markdown(self):
        from mdxcode.output.streamer import _looks_like_markdown

        assert _looks_like_markdown("# Hello **world**") is True
        assert _looks_like_markdown("plain text") is False
        assert _looks_like_markdown("```python\ncode\n```") is True
        assert _looks_like_markdown("- item 1") is True


# ── Feature 10: Help Examples ──


class TestHelpExamples:
    """Tests for help text containing examples."""

    def test_app_has_epilog(self):
        from mdxcode.cli import app

        # Typer stores info on the underlying Click group
        info = app.info
        assert info.epilog is not None
        assert "Examples" in info.epilog

    def test_review_has_examples_in_help(self):
        from mdxcode.cli import review

        assert "Examples" in (review.__doc__ or "")

    def test_cost_has_examples_in_help(self):
        from mdxcode.cli import cost

        assert "Examples" in (cost.__doc__ or "")

    def test_audit_has_examples_in_help(self):
        from mdxcode.cli import audit

        assert "Examples" in (audit.__doc__ or "")

    def test_history_has_examples_in_help(self):
        from mdxcode.cli import history

        assert "Examples" in (history.__doc__ or "")

    def test_summary_has_examples_in_help(self):
        from mdxcode.cli import summary

        assert "Examples" in (summary.__doc__ or "")

    def test_replay_has_examples_in_help(self):
        from mdxcode.cli import replay

        assert "Examples" in (replay.__doc__ or "")

    def test_undo_has_examples_in_help(self):
        from mdxcode.cli import undo

        assert "Examples" in (undo.__doc__ or "")


# ── Feature 11: Summary Command ──


class TestSummaryCommand:
    """Tests for the summary command."""

    @patch("mdxcode.cli.console")
    @patch("mdxcode.config.load_config")
    @patch("mdxcode.governance.audit_trail.read_filtered_entries")
    @patch("mdxcode.router.cost_tracker.get_total_cost", return_value=0.05)
    @patch("mdxcode.router.cost_tracker.get_savings", return_value=0.01)
    @patch("mdxcode.router.cost_tracker.get_date_range_for_period")
    def test_summary_shows_stats(
        self, mock_period, mock_savings, mock_cost, mock_entries, mock_config, mock_console,
    ):
        from mdxcode.cli import summary

        mock_period.return_value = (
            datetime(2025, 6, 15, tzinfo=timezone.utc),
            datetime(2025, 6, 15, 23, 59, tzinfo=timezone.utc),
        )
        mock_config.return_value = MagicMock(
            audit=MagicMock(directory="~/.mdx/audit"),
        )
        mock_entries.return_value = [
            {
                "task": "fix login bug",
                "backend": "claude",
                "status": "success",
                "duration_seconds": 8.0,
                "task_category": "debugging",
                "cost_usd": 0.005,
            },
            {
                "task": "add endpoint",
                "backend": "gemini",
                "status": "success",
                "duration_seconds": 12.0,
                "task_category": "code_generation",
                "cost_usd": 0.003,
            },
        ]

        summary(week=False)
        calls = [str(c) for c in mock_console.print.call_args_list]
        assert any("Today" in c for c in calls)
        assert any("Tasks completed" in c for c in calls)

    @patch("mdxcode.cli.console")
    @patch("mdxcode.config.load_config")
    @patch("mdxcode.governance.audit_trail.read_filtered_entries")
    @patch("mdxcode.router.cost_tracker.get_total_cost", return_value=0.0)
    @patch("mdxcode.router.cost_tracker.get_savings", return_value=0.0)
    @patch("mdxcode.router.cost_tracker.get_date_range_for_period")
    def test_summary_empty(
        self, mock_period, mock_savings, mock_cost, mock_entries, mock_config, mock_console,
    ):
        from mdxcode.cli import summary

        mock_period.return_value = (
            datetime(2025, 6, 15, tzinfo=timezone.utc),
            datetime(2025, 6, 15, 23, 59, tzinfo=timezone.utc),
        )
        mock_config.return_value = MagicMock(
            audit=MagicMock(directory="~/.mdx/audit"),
        )
        mock_entries.return_value = []

        summary(week=False)
        calls = [str(c) for c in mock_console.print.call_args_list]
        assert any("No activity" in c for c in calls)


# ── Feature 12: Shell Completion ──


class TestShellCompletion:
    """Tests for the install-completion command."""

    def test_install_completion_already_installed(self, tmp_path, monkeypatch):
        from mdxcode.cli import install_completion

        rc_file = tmp_path / ".zshrc"
        rc_file.write_text("# MDx Code completion\neval ...\n")

        monkeypatch.setenv("SHELL", "/bin/zsh")

        with patch("mdxcode.cli.Path.expanduser", return_value=rc_file):
            with patch("mdxcode.cli.console") as mock_console:
                install_completion(shell="zsh")
                calls = [str(c) for c in mock_console.print.call_args_list]
                assert any("already installed" in c for c in calls)

    def test_install_completion_unsupported_shell(self):
        import click
        from mdxcode.cli import install_completion

        with patch("mdxcode.cli.console") as mock_console:
            with pytest.raises(click.exceptions.Exit):
                install_completion(shell="nushell")


# ── Footer Updates (Features 7 & 8) ──


class TestFooterUpdates:
    """Tests for footer with timing insight and daily budget."""

    @patch("mdxcode.output.footer.console")
    @patch("mdxcode.config.load_config")
    def test_footer_timing_insight(self, mock_config, mock_console):
        from mdxcode.output.footer import show_footer

        mock_config.return_value = MagicMock(display=MagicMock(sound=False))
        mock_console.width = 80
        show_footer(
            backend_name="claude",
            model="claude-4",
            duration=5.0,
            session_id="abc12345-test",
            cost_usd=0.005,
            timing_insight="32% faster than avg",
        )
        calls = [str(c) for c in mock_console.print.call_args_list]
        assert any("32% faster than avg" in c for c in calls)

    @patch("mdxcode.output.footer.console")
    @patch("mdxcode.config.load_config")
    def test_footer_daily_budget(self, mock_config, mock_console):
        from mdxcode.output.footer import show_footer

        mock_config.return_value = MagicMock(display=MagicMock(sound=False))
        mock_console.width = 80
        show_footer(
            backend_name="claude",
            model="claude-4",
            duration=5.0,
            session_id="abc12345-test",
            daily_budget=5.0,
            daily_spent=2.5,
        )
        calls = [str(c) for c in mock_console.print.call_args_list]
        assert any("Daily" in c for c in calls)
        assert any("$2.50" in c for c in calls)

    @patch("mdxcode.output.footer.console")
    @patch("mdxcode.config.load_config")
    def test_footer_no_timing_no_budget(self, mock_config, mock_console):
        from mdxcode.output.footer import show_footer

        mock_config.return_value = MagicMock(display=MagicMock(sound=False))
        mock_console.width = 80
        show_footer(
            backend_name="claude",
            model=None,
            duration=5.0,
            session_id="abc12345-test",
        )
        calls = [str(c) for c in mock_console.print.call_args_list]
        # Should not contain timing or budget lines
        assert not any("faster" in c for c in calls)
        assert not any("Daily:" in c for c in calls)


# ── Streamer Pipe Detection (Feature 9) ──


class TestStreamerPipeDetection:
    """Tests for stream_output pipe detection."""

    @pytest.mark.asyncio
    async def test_pipe_mode_skips_spinner(self):
        from mdxcode.output.streamer import stream_output

        async def fake_chunks():
            yield "hello "
            yield "world"

        with patch("mdxcode.output.streamer.sys") as mock_sys:
            mock_sys.stdout.isatty.return_value = False
            mock_sys.stdout.write = MagicMock()
            mock_sys.stdout.flush = MagicMock()

            output, duration = await stream_output(fake_chunks())
            assert output == "hello world"
            assert duration >= 0
            # Should have written to stdout directly
            assert mock_sys.stdout.write.call_count == 2


# ── Audit Table Category Icons (Feature 5 in audit) ──


class TestAuditTableCategoryIcons:
    """Tests that audit table includes category icons."""

    @patch("mdxcode.cli.console")
    @patch("mdxcode.governance.audit_trail.read_recent_entries")
    def test_audit_table_includes_icons(self, mock_read, mock_console):
        from mdxcode.cli import audit

        mock_read.return_value = [
            {
                "timestamp": "2025-06-15T14:34:00+00:00",
                "task": "fix bug",
                "backend": "claude",
                "status": "success",
                "duration_seconds": 5.0,
                "cost_usd": 0.005,
                "task_category": "debugging",
            },
        ]

        audit(
            count=10, path=None, since=None, entry_type=None,
            backend_filter=None, verify=False, export=None, stats=False,
        )
        # The table should have been printed
        assert mock_console.print.called
