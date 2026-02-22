"""Tests for enhanced audit reporting (filtering, CSV export, stats)."""

import csv
import io
import json
import pytest
from pathlib import Path

from mdxcode.governance.audit_trail import (
    AuditEntry,
    write_audit_entry,
    read_filtered_entries,
    export_entries_csv,
    compute_audit_stats,
)


@pytest.fixture
def audit_dir(tmp_path):
    """Provide a temporary audit directory."""
    d = tmp_path / "audit"
    d.mkdir()
    return d


@pytest.fixture
def populated_audit_dir(audit_dir):
    """Create audit dir with several entries for filtering tests."""
    entries = [
        AuditEntry(
            session_id="s1",
            task="fix bug",
            backend="claude",
            model="claude-4",
            cost_usd=0.05,
            working_directory="/project/src",
            files_modified=["src/main.py"],
            policy_evaluation={"matching_policies": ["infra"], "requires_review": True},
        ),
        AuditEntry(
            session_id="s2",
            task="adversarial_review: src/",
            backend="claude,codex",
            model=None,
            cost_usd=0.12,
            working_directory="/project",
        ),
        AuditEntry(
            session_id="s3",
            task="add feature",
            backend="codex",
            model="codex-mini",
            cost_usd=0.03,
            working_directory="/project/api",
        ),
    ]
    for entry in entries:
        write_audit_entry(entry, audit_dir)
    return audit_dir


class TestReadFilteredEntries:
    """Tests for read_filtered_entries with various filters."""

    def test_no_filters_returns_all(self, populated_audit_dir):
        entries = read_filtered_entries(populated_audit_dir)
        assert len(entries) == 3

    def test_filter_by_backend(self, populated_audit_dir):
        entries = read_filtered_entries(populated_audit_dir, backend="codex")
        assert len(entries) == 1
        assert entries[0]["task"] == "add feature"

    def test_filter_by_entry_type(self, populated_audit_dir):
        entries = read_filtered_entries(populated_audit_dir, entry_type="adversarial_review")
        assert len(entries) == 1
        assert entries[0]["task"].startswith("adversarial_review")

    def test_filter_by_path(self, populated_audit_dir):
        entries = read_filtered_entries(populated_audit_dir, path="/project/src")
        assert len(entries) == 1
        assert entries[0]["task"] == "fix bug"

    def test_filter_by_since_date(self, populated_audit_dir):
        # All entries have today's date, use a future date to get none
        entries = read_filtered_entries(populated_audit_dir, since="2099-01-01")
        assert len(entries) == 0

        # Use a past date to get all
        entries = read_filtered_entries(populated_audit_dir, since="2000-01-01")
        assert len(entries) == 3

    def test_multiple_filters(self, populated_audit_dir):
        entries = read_filtered_entries(populated_audit_dir, backend="claude", path="/project/src")
        assert len(entries) == 1

    def test_empty_audit_dir(self, audit_dir):
        entries = read_filtered_entries(audit_dir)
        assert entries == []


class TestExportCSV:
    """Tests for CSV export format."""

    def test_csv_header(self, populated_audit_dir):
        entries = read_filtered_entries(populated_audit_dir)
        csv_text = export_entries_csv(entries)
        reader = csv.reader(io.StringIO(csv_text))
        header = next(reader)
        assert "timestamp" in header
        assert "backend" in header
        assert "policy_name" in header
        assert "cost_usd" in header

    def test_csv_row_count(self, populated_audit_dir):
        entries = read_filtered_entries(populated_audit_dir)
        csv_text = export_entries_csv(entries)
        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)
        # 1 header + 3 data rows
        assert len(rows) == 4

    def test_csv_entry_type_detection(self, populated_audit_dir):
        entries = read_filtered_entries(populated_audit_dir)
        csv_text = export_entries_csv(entries)
        reader = csv.reader(io.StringIO(csv_text))
        header = next(reader)
        type_idx = header.index("type")
        types = [row[type_idx] for row in reader]
        assert "review" in types
        assert "task" in types

    def test_csv_policy_info(self, populated_audit_dir):
        entries = read_filtered_entries(populated_audit_dir)
        csv_text = export_entries_csv(entries)
        reader = csv.reader(io.StringIO(csv_text))
        header = next(reader)
        policy_idx = header.index("policy_name")
        rows = list(reader)
        # First entry has policy_evaluation
        assert "infra" in rows[0][policy_idx]

    def test_empty_entries(self):
        csv_text = export_entries_csv([])
        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)
        assert len(rows) == 1  # Header only


class TestComputeAuditStats:
    """Tests for audit statistics computation."""

    def test_stats_totals(self, populated_audit_dir):
        entries = read_filtered_entries(populated_audit_dir)
        stats = compute_audit_stats(entries)
        assert stats["total_actions"] == 3
        assert stats["tasks"] == 2
        assert stats["reviews"] == 1

    def test_stats_by_backend(self, populated_audit_dir):
        entries = read_filtered_entries(populated_audit_dir)
        stats = compute_audit_stats(entries)
        assert "claude" in stats["by_backend"]
        assert "codex" in stats["by_backend"]

    def test_stats_policy_violations(self, populated_audit_dir):
        entries = read_filtered_entries(populated_audit_dir)
        stats = compute_audit_stats(entries)
        # Entry 1 has requires_review=True and is not a review
        assert stats["policy_violations"] == 1
        assert stats["policy_checks"] == 1

    def test_stats_total_cost(self, populated_audit_dir):
        entries = read_filtered_entries(populated_audit_dir)
        stats = compute_audit_stats(entries)
        assert stats["total_cost"] == pytest.approx(0.20, abs=0.01)

    def test_stats_empty(self):
        stats = compute_audit_stats([])
        assert stats["total_actions"] == 0
        assert stats["tasks"] == 0
        assert stats["reviews"] == 0
        assert stats["total_cost"] == 0.0
