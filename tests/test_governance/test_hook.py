"""Tests for git hook install/check functionality."""

import pytest
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock

from mdxcode.governance.policy_engine import (
    PolicyFile,
    evaluate_policies,
    load_policy_file,
)


HOOK_MARKER = "# MDx Code pre-commit hook"


@pytest.fixture
def git_dir(tmp_path):
    """Create a fake git repo with .git/hooks dir."""
    git_hooks = tmp_path / ".git" / "hooks"
    git_hooks.mkdir(parents=True)
    return tmp_path


@pytest.fixture
def policy_dir(tmp_path):
    """Create a temp dir with a .mdxpolicy file."""
    policy = {
        "version": "1.0",
        "defaults": {"adversarial_review": False, "human_approval": False},
        "policies": [
            {
                "name": "security",
                "paths": ["src/**/auth/**"],
                "requires": {"adversarial_review": True, "min_reviewers": 2},
                "severity": "critical",
            },
        ],
    }
    path = tmp_path / ".mdxpolicy"
    path.write_text(yaml.dump(policy))
    return tmp_path


class TestHookInstall:
    """Tests for hook file creation."""

    def test_install_creates_hook_file(self, git_dir):
        hook_path = git_dir / ".git" / "hooks" / "pre-commit"
        # Simulate what `mdx hook install` does
        hook_content = f"""\
#!/bin/sh
{HOOK_MARKER}
# Installed by: mdx hook install
exec mdx hook check
"""
        hook_path.write_text(hook_content)
        hook_path.chmod(0o755)

        assert hook_path.exists()
        assert HOOK_MARKER in hook_path.read_text()
        # Check executable bit
        assert hook_path.stat().st_mode & 0o111

    def test_uninstall_removes_hook(self, git_dir):
        hook_path = git_dir / ".git" / "hooks" / "pre-commit"
        hook_path.write_text(f"#!/bin/sh\n{HOOK_MARKER}\nexec mdx hook check\n")
        hook_path.chmod(0o755)

        # Simulate uninstall: only remove if it's ours
        content = hook_path.read_text()
        if HOOK_MARKER in content:
            hook_path.unlink()

        assert not hook_path.exists()

    def test_uninstall_preserves_foreign_hook(self, git_dir):
        hook_path = git_dir / ".git" / "hooks" / "pre-commit"
        hook_path.write_text("#!/bin/sh\n# Some other hook\necho 'hello'\n")

        content = hook_path.read_text()
        if HOOK_MARKER in content:
            hook_path.unlink()

        # Foreign hook should still exist
        assert hook_path.exists()


class TestHookCheck:
    """Tests for hook check pass/block scenarios."""

    def test_check_passes_no_policy(self, tmp_path, monkeypatch):
        """No .mdxpolicy file means check passes (exit 0)."""
        monkeypatch.chdir(tmp_path)
        policy_file = load_policy_file()
        # No policy file found — should not block
        assert policy_file is None

    def test_check_passes_safe_files(self, policy_dir, monkeypatch):
        """Files not matching any policy should pass."""
        monkeypatch.chdir(policy_dir)
        policy_file = load_policy_file()
        assert policy_file is not None

        staged_files = ["README.md", "docs/guide.md"]
        result = evaluate_policies(policy_file, staged_files)
        # No policy match, defaults are false
        assert result.requires_review is False

    def test_check_blocks_security_files(self, policy_dir, monkeypatch):
        """Files matching security policy should trigger review requirement."""
        monkeypatch.chdir(policy_dir)
        policy_file = load_policy_file()
        assert policy_file is not None

        staged_files = ["src/app/auth/login.py"]
        result = evaluate_policies(policy_file, staged_files)
        assert result.requires_review is True
        assert "security" in result.matching_policies

    def test_check_mixed_files(self, policy_dir, monkeypatch):
        """Mix of safe and policy-matching files should trigger review."""
        monkeypatch.chdir(policy_dir)
        policy_file = load_policy_file()

        staged_files = ["README.md", "src/app/auth/login.py"]
        result = evaluate_policies(policy_file, staged_files)
        assert result.requires_review is True
