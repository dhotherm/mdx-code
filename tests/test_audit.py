"""Tests for audit trail with chain hashing."""

import json
import pytest
from pathlib import Path

from mdxcode.governance.audit_trail import (
    AuditEntry,
    compute_chain_hash,
    verify_audit_integrity,
    write_audit_entry,
    read_recent_entries,
    read_filtered_entries,
)


@pytest.fixture
def audit_dir(tmp_path):
    """Provide a temporary audit directory."""
    d = tmp_path / "audit"
    d.mkdir()
    return d


class TestChainHash:
    """Tests for chain hash computation."""

    def test_deterministic(self):
        entry = {"entry_id": "abc", "task": "test"}
        h1 = compute_chain_hash(entry, "genesis")
        h2 = compute_chain_hash(entry, "genesis")
        assert h1 == h2

    def test_different_previous_hash_changes_result(self):
        entry = {"entry_id": "abc", "task": "test"}
        h1 = compute_chain_hash(entry, "genesis")
        h2 = compute_chain_hash(entry, "other")
        assert h1 != h2

    def test_ignores_chain_hash_field(self):
        entry_with = {"entry_id": "abc", "task": "test", "chain_hash": "should_be_ignored"}
        entry_without = {"entry_id": "abc", "task": "test"}
        h1 = compute_chain_hash(entry_with, "genesis")
        h2 = compute_chain_hash(entry_without, "genesis")
        assert h1 == h2

    def test_sha256_format(self):
        entry = {"entry_id": "abc"}
        h = compute_chain_hash(entry, "genesis")
        assert len(h) == 64  # SHA-256 hex digest
        assert all(c in "0123456789abcdef" for c in h)


class TestWriteAuditEntry:
    """Tests for writing audit entries."""

    def test_single_entry(self, audit_dir):
        entry = AuditEntry(
            session_id="sess-1",
            task="test task",
            backend="claude",
            status="success",
        )
        filepath = write_audit_entry(entry, audit_dir)

        assert filepath.exists()
        lines = filepath.read_text().strip().splitlines()
        assert len(lines) == 1

        data = json.loads(lines[0])
        assert data["task"] == "test task"
        assert data["backend"] == "claude"
        assert data["chain_hash"] != ""

    def test_multiple_entries_chain(self, audit_dir):
        for i in range(3):
            entry = AuditEntry(
                session_id=f"sess-{i}",
                task=f"task {i}",
                backend="claude",
            )
            write_audit_entry(entry, audit_dir)

        # Find the written file
        files = list(audit_dir.glob("*.jsonl"))
        assert len(files) == 1

        lines = files[0].read_text().strip().splitlines()
        assert len(lines) == 3

        # Each entry should have a different chain hash
        hashes = [json.loads(line)["chain_hash"] for line in lines]
        assert len(set(hashes)) == 3


class TestVerifyIntegrity:
    """Tests for audit chain verification."""

    def test_valid_chain(self, audit_dir):
        for i in range(5):
            entry = AuditEntry(
                session_id=f"sess-{i}",
                task=f"task {i}",
                backend="claude",
            )
            write_audit_entry(entry, audit_dir)

        files = list(audit_dir.glob("*.jsonl"))
        valid, error = verify_audit_integrity(files[0])
        assert valid is True
        assert error is None

    def test_tampered_entry_detected(self, audit_dir):
        for i in range(3):
            entry = AuditEntry(
                session_id=f"sess-{i}",
                task=f"task {i}",
                backend="claude",
            )
            write_audit_entry(entry, audit_dir)

        files = list(audit_dir.glob("*.jsonl"))
        filepath = files[0]

        # Tamper with the second entry
        lines = filepath.read_text().strip().splitlines()
        tampered = json.loads(lines[1])
        tampered["task"] = "TAMPERED TASK"
        lines[1] = json.dumps(tampered)
        filepath.write_text("\n".join(lines) + "\n")

        valid, error = verify_audit_integrity(filepath)
        assert valid is False
        assert "line 2" in error

    def test_empty_file_is_valid(self, audit_dir):
        filepath = audit_dir / "empty.jsonl"
        filepath.write_text("")
        valid, error = verify_audit_integrity(filepath)
        assert valid is True


class TestReadRecentEntries:
    """Tests for reading recent audit entries."""

    def test_reads_entries(self, audit_dir):
        for i in range(5):
            entry = AuditEntry(
                session_id=f"sess-{i}",
                task=f"task {i}",
                backend="claude",
            )
            write_audit_entry(entry, audit_dir)

        entries = read_recent_entries(audit_dir, count=3)
        assert len(entries) == 3
        # Most recent first
        assert entries[0]["task"] == "task 4"

    def test_empty_dir(self, tmp_path):
        empty_dir = tmp_path / "empty_audit"
        empty_dir.mkdir()
        entries = read_recent_entries(empty_dir)
        assert entries == []

    def test_nonexistent_dir(self, tmp_path):
        entries = read_recent_entries(tmp_path / "nonexistent")
        assert entries == []


class TestPolicyEvaluationField:
    """Tests for backward-compatible policy_evaluation field."""

    def test_default_is_none(self):
        entry = AuditEntry(task="test", backend="claude")
        assert entry.policy_evaluation is None

    def test_set_policy_evaluation(self):
        entry = AuditEntry(
            task="test",
            backend="claude",
            policy_evaluation={
                "matching_policies": ["security-critical"],
                "requires_review": True,
                "requires_approval": True,
            },
        )
        assert entry.policy_evaluation is not None
        assert "security-critical" in entry.policy_evaluation["matching_policies"]
        assert entry.policy_evaluation["requires_review"] is True

    def test_serialization_roundtrip(self, audit_dir):
        entry = AuditEntry(
            session_id="pe-1",
            task="policy test",
            backend="claude",
            policy_evaluation={"matching_policies": ["infra"], "requires_review": True},
        )
        filepath = write_audit_entry(entry, audit_dir)
        data = json.loads(filepath.read_text().strip())
        assert data["policy_evaluation"]["matching_policies"] == ["infra"]

    def test_backward_compat_no_field(self, audit_dir):
        """Entries without policy_evaluation should still work."""
        entry = AuditEntry(session_id="bc-1", task="old task", backend="claude")
        filepath = write_audit_entry(entry, audit_dir)
        data = json.loads(filepath.read_text().strip())
        assert data["policy_evaluation"] is None

        # Should still be readable
        entries = read_recent_entries(audit_dir, count=1)
        assert len(entries) == 1
        assert entries[0]["policy_evaluation"] is None


class TestReadFilteredEntriesIntegration:
    """Integration tests for read_filtered_entries in test_audit.py."""

    def test_filter_by_backend(self, audit_dir):
        for i, backend in enumerate(["claude", "codex", "claude"]):
            entry = AuditEntry(session_id=f"f-{i}", task=f"task {i}", backend=backend)
            write_audit_entry(entry, audit_dir)

        entries = read_filtered_entries(audit_dir, backend="claude")
        assert len(entries) == 2

    def test_filter_by_entry_type(self, audit_dir):
        entry1 = AuditEntry(session_id="r1", task="fix bug", backend="claude")
        entry2 = AuditEntry(
            session_id="r2", task="adversarial_review: src/", backend="codex"
        )
        write_audit_entry(entry1, audit_dir)
        write_audit_entry(entry2, audit_dir)

        entries = read_filtered_entries(audit_dir, entry_type="adversarial_review")
        assert len(entries) == 1
        assert entries[0]["task"].startswith("adversarial_review")

    def test_combined_filters(self, audit_dir):
        entry1 = AuditEntry(
            session_id="c1", task="fix bug", backend="claude",
            working_directory="/home/project",
        )
        entry2 = AuditEntry(
            session_id="c2", task="fix bug", backend="codex",
            working_directory="/home/project",
        )
        write_audit_entry(entry1, audit_dir)
        write_audit_entry(entry2, audit_dir)

        entries = read_filtered_entries(audit_dir, backend="claude", path="/home/project")
        assert len(entries) == 1
        assert entries[0]["backend"] == "claude"
