"""Tests for the finding normalizer."""

import json

import pytest

from mdxcode.review.normalizer import (
    Finding,
    _extract_json,
    _normalize_cwe,
    _normalize_severity,
    _parse_line,
    normalize_findings,
)


class TestExtractJson:
    """Test JSON extraction from various formats."""

    def test_clean_json(self):
        raw = '{"findings": []}'
        assert _extract_json(raw) == '{"findings": []}'

    def test_json_in_code_fence(self):
        raw = """Here is my analysis:
```json
{"findings": [{"title": "test"}]}
```
That's all."""
        result = _extract_json(raw)
        assert result is not None
        data = json.loads(result)
        assert data["findings"][0]["title"] == "test"

    def test_json_in_plain_fence(self):
        raw = """```
{"findings": []}
```"""
        result = _extract_json(raw)
        assert result is not None
        assert json.loads(result) == {"findings": []}

    def test_json_with_surrounding_text(self):
        raw = """I found several issues:
{"findings": [{"title": "bug"}]}
Hope this helps!"""
        result = _extract_json(raw)
        assert result is not None
        data = json.loads(result)
        assert len(data["findings"]) == 1

    def test_no_json_returns_none(self):
        assert _extract_json("No JSON here, just text.") is None

    def test_empty_string(self):
        assert _extract_json("") is None


class TestParseLine:
    """Test line number parsing."""

    def test_integer(self):
        assert _parse_line(42) == 42

    def test_string_number(self):
        assert _parse_line("42") == 42

    def test_range_list(self):
        assert _parse_line([10, 20]) == (10, 20)

    def test_range_string(self):
        assert _parse_line("10-20") == (10, 20)

    def test_zero_becomes_one(self):
        assert _parse_line(0) == 1

    def test_invalid_returns_one(self):
        assert _parse_line("invalid") == 1


class TestNormalizeSeverity:
    """Test severity normalization."""

    def test_valid_values(self):
        assert _normalize_severity("critical") == "critical"
        assert _normalize_severity("high") == "high"
        assert _normalize_severity("medium") == "medium"
        assert _normalize_severity("low") == "low"

    def test_case_insensitive(self):
        assert _normalize_severity("HIGH") == "high"
        assert _normalize_severity("Critical") == "critical"

    def test_aliases(self):
        assert _normalize_severity("error") == "high"
        assert _normalize_severity("warning") == "medium"
        assert _normalize_severity("info") == "low"

    def test_unknown_defaults_to_medium(self):
        assert _normalize_severity("unknown_value") == "medium"


class TestNormalizeCwe:
    """Test CWE ID normalization."""

    def test_standard_format(self):
        assert _normalize_cwe("CWE-89") == "CWE-89"

    def test_lowercase(self):
        assert _normalize_cwe("cwe-89") == "CWE-89"

    def test_number_only(self):
        assert _normalize_cwe("89") == "CWE-89"

    def test_none_value(self):
        assert _normalize_cwe(None) is None

    def test_empty_string(self):
        assert _normalize_cwe("") is None

    def test_na_string(self):
        assert _normalize_cwe("n/a") is None
        assert _normalize_cwe("None") is None


class TestNormalizeFindings:
    """Test the full normalize_findings function."""

    def test_clean_json(self):
        raw = json.dumps(
            {
                "findings": [
                    {
                        "file": "test.py",
                        "line": 10,
                        "severity": "high",
                        "category": "security",
                        "title": "SQL Injection",
                        "description": "Unsanitized input in query",
                        "cwe_id": "CWE-89",
                        "suggestion": "Use parameterized queries",
                    }
                ]
            }
        )
        findings = normalize_findings(raw, "claude")
        assert len(findings) == 1
        f = findings[0]
        assert f.file == "test.py"
        assert f.line == 10
        assert f.severity == "high"
        assert f.category == "security"
        assert f.title == "SQL Injection"
        assert f.cwe_id == "CWE-89"
        assert f.source_backend == "claude"

    def test_json_in_code_fences(self):
        raw = '```json\n{"findings": [{"file": "a.py", "line": 1, "severity": "low", "category": "quality", "title": "Style issue", "description": "Bad style"}]}\n```'
        findings = normalize_findings(raw, "codex")
        assert len(findings) == 1
        assert findings[0].source_backend == "codex"

    def test_json_with_commentary(self):
        raw = """I analyzed the code and found the following:

{"findings": [{"file": "b.py", "line": 5, "severity": "medium", "category": "logic", "title": "Off by one", "description": "Loop bounds wrong"}]}

Let me know if you need more details."""
        findings = normalize_findings(raw, "gemini")
        assert len(findings) == 1
        assert findings[0].title == "Off by one"

    def test_malformed_json_graceful(self):
        raw = '{"findings": [{"file": "c.py", "line": 1, "severity": "low"'
        findings = normalize_findings(raw, "claude")
        # Should not crash; returns empty list
        assert findings == []

    def test_empty_response(self):
        findings = normalize_findings("", "claude")
        assert findings == []

    def test_none_like_empty(self):
        findings = normalize_findings("   ", "claude")
        assert findings == []

    def test_empty_findings_list(self):
        raw = json.dumps({"findings": []})
        findings = normalize_findings(raw, "claude")
        assert findings == []

    def test_multiple_findings(self):
        raw = json.dumps(
            {
                "findings": [
                    {
                        "file": "a.py",
                        "line": 1,
                        "severity": "high",
                        "category": "security",
                        "title": "Issue 1",
                        "description": "Desc 1",
                    },
                    {
                        "file": "b.py",
                        "line": 2,
                        "severity": "low",
                        "category": "quality",
                        "title": "Issue 2",
                        "description": "Desc 2",
                    },
                ]
            }
        )
        findings = normalize_findings(raw, "claude")
        assert len(findings) == 2

    def test_trailing_comma_json(self):
        raw = '{"findings": [{"file": "a.py", "line": 1, "severity": "high", "category": "security", "title": "Bug", "description": "Desc",}]}'
        findings = normalize_findings(raw, "claude")
        assert len(findings) == 1

    def test_alternative_cwe_field_name(self):
        """Some models use 'cwe' instead of 'cwe_id'."""
        raw = json.dumps(
            {
                "findings": [
                    {
                        "file": "a.py",
                        "line": 1,
                        "severity": "high",
                        "category": "security",
                        "title": "Bug",
                        "description": "Desc",
                        "cwe": "CWE-79",
                    }
                ]
            }
        )
        findings = normalize_findings(raw, "claude")
        assert len(findings) == 1
        assert findings[0].cwe_id == "CWE-79"

    def test_raw_response_preserved(self):
        raw = json.dumps(
            {
                "findings": [
                    {
                        "file": "a.py",
                        "line": 1,
                        "severity": "low",
                        "category": "quality",
                        "title": "T",
                        "description": "D",
                    }
                ]
            }
        )
        findings = normalize_findings(raw, "claude")
        assert findings[0].raw_response == raw

    def test_bare_list_instead_of_object(self):
        """Some models return a bare list instead of {"findings": [...]}."""
        raw = json.dumps(
            [
                {
                    "file": "a.py",
                    "line": 1,
                    "severity": "high",
                    "category": "security",
                    "title": "Bug",
                    "description": "Desc",
                }
            ]
        )
        findings = normalize_findings(raw, "claude")
        assert len(findings) == 1
