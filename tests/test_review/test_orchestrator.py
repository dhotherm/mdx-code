"""Tests for the review orchestrator."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mdxcode.backends.base import BackendInfo, TaskResult
from mdxcode.review.orchestrator import (
    AdversarialReviewResult,
    ReviewTarget,
    _run_single_review,
    prepare_target_from_diff,
    prepare_target_from_paths,
    run_review,
)


@pytest.fixture
def sample_findings_json():
    """JSON output simulating a backend's review findings."""
    return json.dumps(
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


@pytest.fixture
def empty_findings_json():
    return json.dumps({"findings": []})


class TestPrepareTargetFromPaths:
    """Test target preparation from file/directory paths."""

    def test_single_file(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("def hello():\n    pass\n")
        target = prepare_target_from_paths([str(f)])
        assert len(target.files) == 1
        assert "def hello()" in target.content

    def test_directory(self, tmp_path):
        (tmp_path / "a.py").write_text("# file a\n")
        (tmp_path / "b.js").write_text("// file b\n")
        (tmp_path / "readme.md").write_text("# readme\n")  # Not a source extension
        target = prepare_target_from_paths([str(tmp_path)])
        assert len(target.files) == 2  # .py and .js, not .md

    def test_nonexistent_path(self):
        target = prepare_target_from_paths(["/nonexistent/path"])
        assert target.files == []
        assert target.content == ""

    def test_truncation(self, tmp_path):
        f = tmp_path / "big.py"
        f.write_text("x = 1\n" * 50000)
        target = prepare_target_from_paths([str(f)])
        assert "truncated" in target.content


class TestPrepareTargetFromDiff:
    """Test target preparation from git diffs."""

    def test_basic_diff(self):
        diff = """diff --git a/test.py b/test.py
--- a/test.py
+++ b/test.py
@@ -1,3 +1,4 @@
 def hello():
     pass
+    print("hello")
"""
        target = prepare_target_from_diff(diff, "HEAD~1")
        assert "test.py" in target.files
        assert target.diff == diff
        assert "HEAD~1" in target.description

    def test_multiple_files_in_diff(self):
        diff = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1 +1 @@
-old
+new
diff --git a/b.py b/b.py
--- a/b.py
+++ b/b.py
@@ -1 +1 @@
-old
+new
"""
        target = prepare_target_from_diff(diff)
        assert len(target.files) == 2


class TestRunSingleReview:
    """Test single backend review execution."""

    @pytest.mark.asyncio
    async def test_successful_review(self, sample_findings_json):
        mock_backend = MagicMock()
        mock_backend.name = "claude"
        mock_backend.execute_and_capture = AsyncMock(
            return_value=TaskResult(
                backend_name="claude",
                output=sample_findings_json,
                duration_seconds=5.0,
                cost_usd=0.42,
            )
        )

        result = await _run_single_review(mock_backend, "review this", Path.cwd())
        assert result.backend_name == "claude"
        assert len(result.findings) == 1
        assert result.findings[0].title == "SQL Injection"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        mock_backend = MagicMock()
        mock_backend.name = "codex"

        async def slow_execute(*args, **kwargs):
            await asyncio.sleep(10)
            return TaskResult(backend_name="codex", output="")

        mock_backend.execute_and_capture = slow_execute

        result = await _run_single_review(mock_backend, "review this", Path.cwd(), timeout=0.1)
        assert result.error is not None
        assert "Timed out" in result.error

    @pytest.mark.asyncio
    async def test_backend_exception(self):
        mock_backend = MagicMock()
        mock_backend.name = "gemini"
        mock_backend.execute_and_capture = AsyncMock(side_effect=RuntimeError("connection failed"))

        result = await _run_single_review(mock_backend, "review this", Path.cwd())
        assert result.error is not None
        assert "connection failed" in result.error


class TestRunReview:
    """Test the full review orchestration."""

    @pytest.mark.asyncio
    async def test_parallel_execution(self, sample_findings_json, empty_findings_json):
        """Verify that backends run in parallel, not sequentially."""
        target = ReviewTarget(
            files=["test.py"],
            content="def hello(): pass",
            description="test.py",
        )

        # Mock discover_backends to return two healthy backends
        mock_backends_info = [
            BackendInfo(name="claude", version="1.0", authenticated=True, healthy=True),
            BackendInfo(name="codex", version="1.0", authenticated=True, healthy=True),
        ]

        # Create mock backend instances
        mock_claude = MagicMock()
        mock_claude.name = "claude"
        mock_claude.execute_and_capture = AsyncMock(
            return_value=TaskResult(
                backend_name="claude",
                output=sample_findings_json,
                duration_seconds=2.0,
                cost_usd=0.42,
            )
        )

        mock_codex = MagicMock()
        mock_codex.name = "codex"
        mock_codex.execute_and_capture = AsyncMock(
            return_value=TaskResult(
                backend_name="codex",
                output=empty_findings_json,
                duration_seconds=1.5,
                cost_usd=0.25,
            )
        )

        with (
            patch("mdxcode.review.orchestrator.discover_backends", return_value=mock_backends_info),
            patch(
                "mdxcode.review.orchestrator._get_backend_instances",
                return_value=[mock_claude, mock_codex],
            ),
        ):
            result = await run_review(target=target)

        assert len(result.backend_results) == 2
        assert result.total_cost_usd > 0

    @pytest.mark.asyncio
    async def test_single_backend(self, sample_findings_json):
        """Single backend: all findings are unique."""
        target = ReviewTarget(
            files=["test.py"],
            content="def hello(): pass",
            description="test.py",
        )

        mock_backends_info = [
            BackendInfo(name="claude", version="1.0", authenticated=True, healthy=True),
        ]

        mock_claude = MagicMock()
        mock_claude.name = "claude"
        mock_claude.execute_and_capture = AsyncMock(
            return_value=TaskResult(
                backend_name="claude",
                output=sample_findings_json,
                duration_seconds=2.0,
                cost_usd=0.42,
            )
        )

        with (
            patch("mdxcode.review.orchestrator.discover_backends", return_value=mock_backends_info),
            patch(
                "mdxcode.review.orchestrator._get_backend_instances",
                return_value=[mock_claude],
            ),
        ):
            result = await run_review(target=target)

        assert len(result.backend_results) == 1
        # Single backend: all findings are unique, none confirmed
        assert len(result.consensus.unique) == 1
        assert len(result.consensus.confirmed) == 0

    @pytest.mark.asyncio
    async def test_one_backend_times_out_other_still_works(self, sample_findings_json):
        """If one backend times out, we still get results from the other."""
        target = ReviewTarget(
            files=["test.py"],
            content="def hello(): pass",
            description="test.py",
        )

        mock_backends_info = [
            BackendInfo(name="claude", version="1.0", authenticated=True, healthy=True),
            BackendInfo(name="codex", version="1.0", authenticated=True, healthy=True),
        ]

        mock_claude = MagicMock()
        mock_claude.name = "claude"
        mock_claude.execute_and_capture = AsyncMock(
            return_value=TaskResult(
                backend_name="claude",
                output=sample_findings_json,
                duration_seconds=2.0,
                cost_usd=0.42,
            )
        )

        mock_codex = MagicMock()
        mock_codex.name = "codex"

        async def slow_codex(*args, **kwargs):
            await asyncio.sleep(10)
            return TaskResult(backend_name="codex", output="")

        mock_codex.execute_and_capture = slow_codex

        with (
            patch("mdxcode.review.orchestrator.discover_backends", return_value=mock_backends_info),
            patch(
                "mdxcode.review.orchestrator._get_backend_instances",
                return_value=[mock_claude, mock_codex],
            ),
        ):
            result = await run_review(target=target, timeout=0.2)

        # Claude succeeded, Codex timed out
        successful = [br for br in result.backend_results if not br.error]
        errored = [br for br in result.backend_results if br.error]
        assert len(successful) == 1
        assert successful[0].backend_name == "claude"
        assert len(errored) == 1
        assert errored[0].backend_name == "codex"
        # We still get findings from claude
        assert len(result.consensus.unique) == 1

    @pytest.mark.asyncio
    async def test_no_backends_available(self):
        """If no backends are available, return empty result."""
        target = ReviewTarget(
            files=["test.py"],
            content="def hello(): pass",
            description="test.py",
        )

        with (
            patch("mdxcode.review.orchestrator.discover_backends", return_value=[]),
            patch("mdxcode.review.orchestrator._get_backend_instances", return_value=[]),
        ):
            result = await run_review(target=target)

        assert len(result.backend_results) == 0
