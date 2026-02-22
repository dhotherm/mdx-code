"""Tests for the consensus engine."""

import pytest

from mdxcode.review.consensus import (
    ConfirmedFinding,
    ConflictFinding,
    ConsensusResult,
    UniqueFinding,
    _findings_match,
    _lines_overlap_or_near,
    build_consensus,
)
from mdxcode.review.normalizer import Finding


def _make_finding(
    file: str = "test.py",
    line: int | tuple[int, int] = 10,
    severity: str = "high",
    category: str = "security",
    title: str = "Test Issue",
    description: str = "A test issue",
    cwe_id: str | None = None,
    source_backend: str = "claude",
) -> Finding:
    return Finding(
        file=file,
        line=line,
        severity=severity,
        category=category,
        title=title,
        description=description,
        cwe_id=cwe_id,
        source_backend=source_backend,
    )


class TestLinesOverlap:
    """Test line proximity detection."""

    def test_same_line(self):
        assert _lines_overlap_or_near(10, 10) is True

    def test_adjacent_lines(self):
        assert _lines_overlap_or_near(10, 11) is True

    def test_within_threshold(self):
        assert _lines_overlap_or_near(10, 15) is True

    def test_beyond_threshold(self):
        assert _lines_overlap_or_near(10, 20) is False

    def test_range_overlap(self):
        assert _lines_overlap_or_near((10, 20), (15, 25)) is True

    def test_range_no_overlap(self):
        assert _lines_overlap_or_near((10, 12), (25, 30)) is False

    def test_range_near(self):
        assert _lines_overlap_or_near((10, 12), (15, 17)) is True

    def test_int_and_range(self):
        assert _lines_overlap_or_near(10, (8, 12)) is True


class TestFindingsMatch:
    """Test finding matching logic."""

    def test_same_file_same_line_same_category(self):
        a = _make_finding(file="a.py", line=10, category="security")
        b = _make_finding(file="a.py", line=10, category="security", source_backend="codex")
        assert _findings_match(a, b) is True

    def test_different_files(self):
        a = _make_finding(file="a.py", line=10)
        b = _make_finding(file="b.py", line=10, source_backend="codex")
        assert _findings_match(a, b) is False

    def test_same_file_far_apart_lines(self):
        a = _make_finding(file="a.py", line=10)
        b = _make_finding(file="a.py", line=50, source_backend="codex")
        assert _findings_match(a, b) is False

    def test_same_cwe_different_category(self):
        a = _make_finding(file="a.py", line=10, category="security", cwe_id="CWE-89")
        b = _make_finding(
            file="a.py", line=12, category="quality", cwe_id="CWE-89", source_backend="codex"
        )
        assert _findings_match(a, b) is True

    def test_fuzzy_matching_by_keywords(self):
        a = _make_finding(
            file="a.py",
            line=10,
            category="security",
            title="SQL injection vulnerability in query",
        )
        b = _make_finding(
            file="a.py",
            line=11,
            category="security",
            title="SQL injection in database query",
            source_backend="codex",
        )
        assert _findings_match(a, b) is True

    def test_within_five_lines(self):
        a = _make_finding(file="a.py", line=10, category="security", cwe_id="CWE-89")
        b = _make_finding(
            file="a.py", line=14, category="security", cwe_id="CWE-89", source_backend="codex"
        )
        assert _findings_match(a, b) is True


class TestBuildConsensus:
    """Test consensus building across backends."""

    def test_two_backends_same_issue_confirmed(self):
        findings_by_backend = {
            "claude": [
                _make_finding(file="a.py", line=10, category="security", source_backend="claude")
            ],
            "codex": [
                _make_finding(file="a.py", line=10, category="security", source_backend="codex")
            ],
        }
        result = build_consensus(findings_by_backend)
        assert len(result.confirmed) == 1
        assert len(result.unique) == 0
        assert "claude" in result.confirmed[0].confirmed_by
        assert "codex" in result.confirmed[0].confirmed_by

    def test_two_backends_different_issues_both_unique(self):
        findings_by_backend = {
            "claude": [_make_finding(file="a.py", line=10, source_backend="claude")],
            "codex": [_make_finding(file="b.py", line=50, source_backend="codex")],
        }
        result = build_consensus(findings_by_backend)
        assert len(result.confirmed) == 0
        assert len(result.unique) == 2
        found_by = {uf.found_by for uf in result.unique}
        assert found_by == {"claude", "codex"}

    def test_severity_conflict_major(self):
        """Major severity mismatch (2+ ranks) → conflict."""
        findings_by_backend = {
            "claude": [
                _make_finding(file="a.py", line=10, severity="critical", source_backend="claude")
            ],
            "codex": [_make_finding(file="a.py", line=10, severity="low", source_backend="codex")],
        }
        result = build_consensus(findings_by_backend)
        assert len(result.conflicts) == 1
        assert result.conflicts[0].conflict_type == "severity_mismatch"

    def test_severity_conflict_minor_still_confirms(self):
        """Minor severity difference (1 rank) → confirmed with higher severity."""
        findings_by_backend = {
            "claude": [
                _make_finding(file="a.py", line=10, severity="high", source_backend="claude")
            ],
            "codex": [
                _make_finding(file="a.py", line=10, severity="medium", source_backend="codex")
            ],
        }
        result = build_consensus(findings_by_backend)
        assert len(result.confirmed) == 1
        assert result.confirmed[0].finding.severity == "high"

    def test_fuzzy_same_cwe_within_five_lines(self):
        findings_by_backend = {
            "claude": [
                _make_finding(
                    file="auth.py",
                    line=15,
                    cwe_id="CWE-89",
                    category="security",
                    title="SQL injection",
                    source_backend="claude",
                )
            ],
            "codex": [
                _make_finding(
                    file="auth.py",
                    line=18,
                    cwe_id="CWE-89",
                    category="security",
                    title="Unsanitized query",
                    source_backend="codex",
                )
            ],
        }
        result = build_consensus(findings_by_backend)
        assert len(result.confirmed) == 1
        assert result.confirmed[0].finding.cwe_id == "CWE-89"

    def test_no_findings_clean_result(self):
        findings_by_backend = {
            "claude": [],
            "codex": [],
        }
        result = build_consensus(findings_by_backend)
        assert len(result.confirmed) == 0
        assert len(result.unique) == 0
        assert len(result.conflicts) == 0

    def test_single_backend_all_unique(self):
        findings_by_backend = {
            "claude": [
                _make_finding(file="a.py", line=10, source_backend="claude"),
                _make_finding(file="b.py", line=20, source_backend="claude"),
            ],
        }
        result = build_consensus(findings_by_backend)
        assert len(result.confirmed) == 0
        assert len(result.unique) == 2
        assert all(uf.found_by == "claude" for uf in result.unique)

    def test_empty_backends(self):
        result = build_consensus({})
        assert len(result.confirmed) == 0
        assert len(result.unique) == 0

    def test_confirmed_uses_higher_severity(self):
        findings_by_backend = {
            "claude": [
                _make_finding(file="a.py", line=10, severity="medium", source_backend="claude")
            ],
            "codex": [_make_finding(file="a.py", line=10, severity="high", source_backend="codex")],
        }
        result = build_consensus(findings_by_backend)
        assert len(result.confirmed) == 1
        assert result.confirmed[0].finding.severity == "high"

    def test_mixed_confirmed_and_unique(self):
        """One shared finding + one unique per backend."""
        findings_by_backend = {
            "claude": [
                _make_finding(file="a.py", line=10, title="shared issue", source_backend="claude"),
                _make_finding(file="b.py", line=30, title="claude only", source_backend="claude"),
            ],
            "codex": [
                _make_finding(file="a.py", line=10, title="shared issue", source_backend="codex"),
                _make_finding(file="c.py", line=50, title="codex only", source_backend="codex"),
            ],
        }
        result = build_consensus(findings_by_backend)
        assert len(result.confirmed) == 1
        assert len(result.unique) == 2
        unique_backends = {uf.found_by for uf in result.unique}
        assert unique_backends == {"claude", "codex"}

    def test_confidence_is_ratio(self):
        findings_by_backend = {
            "claude": [_make_finding(file="a.py", line=10, source_backend="claude")],
            "codex": [_make_finding(file="a.py", line=10, source_backend="codex")],
        }
        result = build_consensus(findings_by_backend)
        assert result.confirmed[0].confidence == 1.0  # 2/2
