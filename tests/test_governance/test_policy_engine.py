"""Tests for the policy engine."""

import pytest
import yaml
from pathlib import Path

from mdxcode.governance.policy_engine import (
    PolicyFile,
    PolicyRequirements,
    Policy,
    PolicyDefaults,
    PolicyResult,
    load_policy_file,
    _match_path,
    evaluate_policies,
    STARTER_POLICY,
)


@pytest.fixture
def policy_dir(tmp_path):
    """Create a temp dir with a .mdxpolicy file."""
    policy = {
        "version": "1.0",
        "defaults": {
            "adversarial_review": False,
            "human_approval": False,
            "severity": "low",
        },
        "policies": [
            {
                "name": "security-critical",
                "description": "Auth code needs review",
                "paths": ["src/**/auth/**", "src/**/security/**"],
                "requires": {
                    "adversarial_review": True,
                    "min_reviewers": 2,
                    "human_approval": True,
                },
                "severity": "critical",
            },
            {
                "name": "infra",
                "description": "Infrastructure changes",
                "paths": ["terraform/**", "Dockerfile*"],
                "requires": {
                    "adversarial_review": True,
                    "min_reviewers": 1,
                },
                "severity": "high",
            },
            {
                "name": "migrations",
                "description": "Database migrations",
                "paths": ["**/*.sql"],
                "requires": {
                    "adversarial_review": True,
                    "human_approval": True,
                },
                "severity": "high",
            },
        ],
    }
    policy_path = tmp_path / ".mdxpolicy"
    policy_path.write_text(yaml.dump(policy))
    return tmp_path


class TestParsePolicyFile:
    """Tests for parsing .mdxpolicy YAML files."""

    def test_parse_valid_policy(self, policy_dir):
        policy_file = load_policy_file(policy_dir / ".mdxpolicy")
        assert policy_file is not None
        assert policy_file.version == "1.0"
        assert len(policy_file.policies) == 3
        assert policy_file.policies[0].name == "security-critical"
        assert policy_file.policies[0].requires.adversarial_review is True
        assert policy_file.policies[0].requires.min_reviewers == 2
        assert policy_file.policies[0].severity == "critical"

    def test_parse_defaults_only(self, tmp_path):
        policy = {
            "version": "1.0",
            "defaults": {
                "adversarial_review": True,
                "human_approval": False,
                "severity": "medium",
            },
            "policies": [],
        }
        path = tmp_path / ".mdxpolicy"
        path.write_text(yaml.dump(policy))

        policy_file = load_policy_file(path)
        assert policy_file is not None
        assert policy_file.defaults.adversarial_review is True
        assert policy_file.defaults.severity == "medium"
        assert len(policy_file.policies) == 0

    def test_parse_missing_file(self, tmp_path):
        result = load_policy_file(tmp_path / "nonexistent" / ".mdxpolicy")
        assert result is None

    def test_parse_invalid_yaml(self, tmp_path):
        path = tmp_path / ".mdxpolicy"
        path.write_text("{{invalid yaml: [broken")
        result = load_policy_file(path)
        assert result is None

    def test_parse_starter_policy(self):
        """The STARTER_POLICY constant should be valid YAML that parses correctly."""
        raw = yaml.safe_load(STARTER_POLICY)
        policy_file = PolicyFile(**raw)
        assert policy_file.version == "1.0"
        assert len(policy_file.policies) >= 3

    def test_walk_up_directories(self, policy_dir, monkeypatch):
        """load_policy_file() with no path should walk up to find .mdxpolicy."""
        subdir = policy_dir / "src" / "auth"
        subdir.mkdir(parents=True)
        monkeypatch.chdir(subdir)

        policy_file = load_policy_file()
        assert policy_file is not None
        assert policy_file.version == "1.0"


class TestPathMatching:
    """Tests for _match_path glob matching."""

    def test_exact_match(self):
        assert _match_path("src/auth/login.py", "src/auth/login.py") is True

    def test_glob_star(self):
        assert _match_path("src/auth/login.py", "src/auth/*.py") is True
        assert _match_path("src/auth/login.js", "src/auth/*.py") is False

    def test_doublestar_recursive(self):
        assert _match_path("src/auth/login.py", "src/**/login.py") is True
        assert _match_path("src/deep/nested/auth/login.py", "src/**/login.py") is True

    def test_doublestar_prefix(self):
        assert _match_path("src/auth/secrets.py", "src/**/auth/**") is True
        assert _match_path("src/api/handler.py", "src/**/auth/**") is False

    def test_doublestar_suffix_only(self):
        assert _match_path("migrations/001.sql", "**/*.sql") is True
        assert _match_path("src/db/migrations/002.sql", "**/*.sql") is True
        assert _match_path("src/db/main.py", "**/*.sql") is False

    def test_no_match(self):
        assert _match_path("README.md", "src/**/*.py") is False

    def test_dockerfile_pattern(self):
        assert _match_path("Dockerfile", "Dockerfile*") is True
        assert _match_path("Dockerfile.prod", "Dockerfile*") is True

    def test_terraform_recursive(self):
        assert _match_path("terraform/main.tf", "terraform/**") is True
        assert _match_path("terraform/modules/vpc/main.tf", "terraform/**") is True


class TestEvaluatePolicies:
    """Tests for policy evaluation with strictest-wins merging."""

    def test_single_policy_match(self, policy_dir):
        policy_file = load_policy_file(policy_dir / ".mdxpolicy")
        result = evaluate_policies(policy_file, ["src/app/auth/login.py"])

        assert result.requires_review is True
        assert result.requires_approval is True
        assert result.min_reviewers == 2
        assert "security-critical" in result.matching_policies

    def test_no_policy_match_uses_defaults(self, policy_dir):
        policy_file = load_policy_file(policy_dir / ".mdxpolicy")
        result = evaluate_policies(policy_file, ["README.md"])

        assert result.requires_review is False
        assert result.requires_approval is False
        assert result.matching_policies == []

    def test_strictest_wins(self, policy_dir):
        """When multiple policies match, strictest requirements win."""
        policy_file = load_policy_file(policy_dir / ".mdxpolicy")
        # This matches both infra (min_reviewers=1) and we'll add a sql match
        result = evaluate_policies(
            policy_file,
            [
                "terraform/main.tf",
                "migrations/001.sql",
            ],
        )

        assert result.requires_review is True
        assert result.requires_approval is True  # From migrations policy
        assert result.min_reviewers == 1
        assert "infra" in result.matching_policies
        assert "migrations" in result.matching_policies

    def test_multiple_files_multiple_policies(self, policy_dir):
        policy_file = load_policy_file(policy_dir / ".mdxpolicy")
        result = evaluate_policies(
            policy_file,
            [
                "src/app/auth/login.py",
                "terraform/main.tf",
            ],
        )

        assert result.requires_review is True
        assert result.requires_approval is True
        assert result.min_reviewers == 2  # From security-critical
        assert len(result.matching_policies) == 2

    def test_allowed_always_true(self, policy_dir):
        """Policies warn, never block. allowed is always True."""
        policy_file = load_policy_file(policy_dir / ".mdxpolicy")
        result = evaluate_policies(policy_file, ["src/app/auth/login.py"])
        assert result.allowed is True

    def test_defaults_with_review_true(self, tmp_path):
        """When defaults have adversarial_review=True and no policies match."""
        policy = {
            "version": "1.0",
            "defaults": {
                "adversarial_review": True,
                "human_approval": False,
            },
            "policies": [],
        }
        path = tmp_path / ".mdxpolicy"
        path.write_text(yaml.dump(policy))

        policy_file = load_policy_file(path)
        result = evaluate_policies(policy_file, ["any_file.py"])
        assert result.requires_review is True
        assert result.requires_approval is False

    def test_empty_files_list(self, policy_dir):
        policy_file = load_policy_file(policy_dir / ".mdxpolicy")
        result = evaluate_policies(policy_file, [])
        assert result.requires_review is False
        assert result.matching_policies == []
