"""Tests for governance MCP server."""

from pathlib import Path
from unittest.mock import patch

import pytest

from mdxcode.governance.policy_engine import (
    Policy,
    PolicyDefaults,
    PolicyFile,
    PolicyRequirements,
    PolicyResult,
)
from mcp_servers.governance.server import check_policy, evaluate_commit, list_policies


@pytest.fixture
def sample_policy_file():
    """A sample PolicyFile for testing."""
    return PolicyFile(
        version="1.0",
        policies=[
            Policy(
                name="security-critical",
                description="Security-sensitive code",
                paths=["src/**/auth/**", "**/*secret*"],
                requires=PolicyRequirements(
                    adversarial_review=True,
                    min_reviewers=2,
                    human_approval=True,
                ),
                severity="critical",
            ),
            Policy(
                name="infrastructure",
                description="Infra changes need review",
                paths=["terraform/**", "Dockerfile*"],
                requires=PolicyRequirements(
                    adversarial_review=True,
                    min_reviewers=1,
                ),
                severity="high",
            ),
        ],
        defaults=PolicyDefaults(
            adversarial_review=False,
            human_approval=False,
            severity="low",
        ),
    )


@pytest.fixture
def security_result():
    """PolicyResult when security-critical policy matches."""
    return PolicyResult(
        allowed=True,
        requires_review=True,
        requires_approval=True,
        min_reviewers=2,
        matching_policies=["security-critical"],
    )


@pytest.fixture
def clean_result():
    """PolicyResult when no policies match."""
    return PolicyResult(
        allowed=True,
        requires_review=False,
        requires_approval=False,
        min_reviewers=1,
        matching_policies=[],
    )


class TestCheckPolicy:
    """Tests for check_policy tool."""

    @patch("mcp_servers.governance.server.evaluate_policies")
    @patch("mcp_servers.governance.server.load_policy_file")
    def test_check_policy_with_match(self, mock_load, mock_eval, sample_policy_file, security_result):
        mock_load.return_value = sample_policy_file
        mock_eval.return_value = security_result

        result = check_policy(files=["src/auth/login.py"])

        assert result["requires_review"] is True
        assert result["requires_approval"] is True
        assert result["min_reviewers"] == 2
        assert "security-critical" in result["matching_policies"]
        mock_load.assert_called_once_with(None)
        mock_eval.assert_called_once_with(sample_policy_file, ["src/auth/login.py"])

    @patch("mcp_servers.governance.server.evaluate_policies")
    @patch("mcp_servers.governance.server.load_policy_file")
    def test_check_policy_no_match(self, mock_load, mock_eval, sample_policy_file, clean_result):
        mock_load.return_value = sample_policy_file
        mock_eval.return_value = clean_result

        result = check_policy(files=["src/utils.py"])

        assert result["requires_review"] is False
        assert result["matching_policies"] == []

    @patch("mcp_servers.governance.server.load_policy_file")
    def test_check_policy_no_policy_file(self, mock_load):
        mock_load.return_value = None

        result = check_policy(files=["src/auth/login.py"])

        assert "error" in result
        assert ".mdxpolicy" in result["error"]

    @patch("mcp_servers.governance.server.evaluate_policies")
    @patch("mcp_servers.governance.server.load_policy_file")
    def test_check_policy_with_custom_path(self, mock_load, mock_eval, sample_policy_file, clean_result):
        mock_load.return_value = sample_policy_file
        mock_eval.return_value = clean_result

        check_policy(files=["test.py"], policy_path="/custom/.mdxpolicy")

        mock_load.assert_called_once_with(Path("/custom/.mdxpolicy"))

    @patch("mcp_servers.governance.server.load_policy_file")
    def test_check_policy_handles_exception(self, mock_load):
        mock_load.side_effect = RuntimeError("disk error")

        result = check_policy(files=["src/auth/login.py"])

        assert "error" in result
        assert "disk error" in result["error"]


class TestListPolicies:
    """Tests for list_policies tool."""

    @patch("mcp_servers.governance.server.load_policy_file")
    def test_list_policies_success(self, mock_load, sample_policy_file):
        mock_load.return_value = sample_policy_file

        result = list_policies()

        assert result["version"] == "1.0"
        assert len(result["policies"]) == 2
        assert result["policies"][0]["name"] == "security-critical"
        assert result["policies"][0]["severity"] == "critical"
        assert result["policies"][0]["requires"]["adversarial_review"] is True
        assert result["policies"][0]["requires"]["min_reviewers"] == 2
        assert result["defaults"]["adversarial_review"] is False

    @patch("mcp_servers.governance.server.load_policy_file")
    def test_list_policies_no_file(self, mock_load):
        mock_load.return_value = None

        result = list_policies()

        assert "error" in result

    @patch("mcp_servers.governance.server.load_policy_file")
    def test_list_policies_with_custom_path(self, mock_load, sample_policy_file):
        mock_load.return_value = sample_policy_file

        list_policies(policy_path="/my/policies")

        mock_load.assert_called_once_with(Path("/my/policies"))

    @patch("mcp_servers.governance.server.load_policy_file")
    def test_list_policies_includes_all_fields(self, mock_load, sample_policy_file):
        mock_load.return_value = sample_policy_file

        result = list_policies()

        policy = result["policies"][1]
        assert policy["name"] == "infrastructure"
        assert policy["description"] == "Infra changes need review"
        assert "terraform/**" in policy["paths"]
        assert policy["requires"]["human_approval"] is False


class TestEvaluateCommit:
    """Tests for evaluate_commit tool."""

    @patch("mcp_servers.governance.server.evaluate_policies")
    @patch("mcp_servers.governance.server.load_policy_file")
    def test_commit_blocked_by_policy(self, mock_load, mock_eval, sample_policy_file, security_result):
        mock_load.return_value = sample_policy_file
        mock_eval.return_value = security_result

        result = evaluate_commit(staged_files=["src/auth/login.py"])

        assert result["can_commit"] is False
        assert "security-critical" in result["blocking_policies"]
        assert len(result["actions_required"]) > 0

    @patch("mcp_servers.governance.server.evaluate_policies")
    @patch("mcp_servers.governance.server.load_policy_file")
    def test_commit_allowed(self, mock_load, mock_eval, sample_policy_file, clean_result):
        mock_load.return_value = sample_policy_file
        mock_eval.return_value = clean_result

        result = evaluate_commit(staged_files=["src/utils.py"])

        assert result["can_commit"] is True
        assert result["blocking_policies"] == []
        assert result["actions_required"] == []

    @patch("mcp_servers.governance.server.load_policy_file")
    def test_commit_no_policy_file(self, mock_load):
        mock_load.return_value = None

        result = evaluate_commit(staged_files=["any_file.py"])

        assert result["can_commit"] is True
        assert "No .mdxpolicy" in result["note"]

    @patch("mcp_servers.governance.server.evaluate_policies")
    @patch("mcp_servers.governance.server.load_policy_file")
    def test_commit_actions_for_review(self, mock_load, mock_eval, sample_policy_file):
        mock_load.return_value = sample_policy_file
        mock_eval.return_value = PolicyResult(
            requires_review=True,
            requires_approval=False,
            min_reviewers=1,
            matching_policies=["infrastructure"],
        )

        result = evaluate_commit(staged_files=["terraform/main.tf"])

        assert result["can_commit"] is False
        assert any("review" in a.lower() for a in result["actions_required"])
        assert result["requires_review"] is True
        assert result["requires_approval"] is False

    @patch("mcp_servers.governance.server.evaluate_policies")
    @patch("mcp_servers.governance.server.load_policy_file")
    def test_commit_actions_for_multiple_reviewers(self, mock_load, mock_eval, sample_policy_file):
        mock_load.return_value = sample_policy_file
        mock_eval.return_value = PolicyResult(
            requires_review=True,
            requires_approval=True,
            min_reviewers=3,
            matching_policies=["security-critical"],
        )

        result = evaluate_commit(staged_files=["src/auth/secrets.py"])

        assert result["min_reviewers"] == 3
        assert any("3 reviewers" in a for a in result["actions_required"])

    @patch("mcp_servers.governance.server.load_policy_file")
    def test_commit_handles_exception(self, mock_load):
        mock_load.side_effect = RuntimeError("boom")

        result = evaluate_commit(staged_files=["test.py"])

        assert "error" in result
