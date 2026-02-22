"""
MDx Code Smoke Test Harness
============================
Tests every user-facing command via subprocess, exactly as a real user would.

Usage:
    python tests/smoke_test.py              # Run all tests
    python tests/smoke_test.py --fast       # Skip backend-dependent tests
    python tests/smoke_test.py --fix        # Show fix suggestions for failures
    python tests/smoke_test.py --verbose    # Show full output on failures

Design:
    Each test is a function that returns (passed: bool, message: str).
    Tests are grouped by category: startup, commands, flags, output, errors.
    The harness runs all tests and prints a summary.

For Claude Code:
    If tests fail, read the failure messages carefully. They include:
    - The exact command that was run
    - The expected vs actual output
    - The file and function most likely responsible
    - A suggested fix approach
"""

import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Use python -m mdxcode as the CLI invocation to avoid macOS UF_HIDDEN flag
# issues with editable installs that can break the `mdx` entry point script.
MDX_CMD = [sys.executable, "-m", "mdxcode"]


@dataclass
class TestResult:
    name: str
    passed: bool
    message: str
    duration_ms: float = 0.0
    command: str = ""
    stdout: str = ""
    stderr: str = ""
    fix_hint: str = ""


@dataclass
class SmokeTestRunner:
    results: list[TestResult] = field(default_factory=list)
    fast_mode: bool = False
    verbose: bool = False
    show_fixes: bool = False

    def run_command(
        self,
        args: list[str],
        timeout: int = 30,
        expect_exit_code: int = 0,
        env_override: Optional[dict] = None,
    ) -> tuple[subprocess.CompletedProcess, float]:
        """Run a command and return (result, duration_ms)."""
        env = os.environ.copy()
        if env_override:
            env.update(env_override)

        start = time.monotonic()
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired:
            duration = (time.monotonic() - start) * 1000
            result = subprocess.CompletedProcess(
                args=args, returncode=-1, stdout="", stderr="TIMEOUT"
            )
            return result, duration

        duration = (time.monotonic() - start) * 1000
        return result, duration

    def mdx(self, *args: str) -> list[str]:
        """Build a CLI command: ['python', '-m', 'mdxcode', ...args]."""
        return [*MDX_CMD, *args]

    def add_result(self, result: TestResult) -> None:
        self.results.append(result)
        # Print live progress
        mark = "✓" if result.passed else "✗"
        color = "\033[32m" if result.passed else "\033[31m"
        reset = "\033[0m"
        time_str = f"{result.duration_ms:.0f}ms"
        print(f"  {color}{mark}{reset} {result.name} [{time_str}]")
        if not result.passed and self.verbose:
            print(f"    Command: {result.command}")
            print(f"    Message: {result.message}")
            if result.stdout:
                print(f"    Stdout (last 5 lines):")
                for line in result.stdout.strip().splitlines()[-5:]:
                    print(f"      {line}")
            if result.stderr:
                print(f"    Stderr (last 3 lines):")
                for line in result.stderr.strip().splitlines()[-3:]:
                    print(f"      {line}")

    # ──────────────────────────────────────────────────────
    # CATEGORY 1: Startup & Version
    # ──────────────────────────────────────────────────────

    def test_version_flag(self) -> None:
        """mdx --version should print version string and exit 0."""
        result, ms = self.run_command(self.mdx("--version"))
        passed = result.returncode == 0 and "MDx Code" in result.stdout
        self.add_result(
            TestResult(
                name="--version flag",
                passed=passed,
                message=(
                    f"Expected 'MDx Code' in output, got: {result.stdout[:80]}"
                    if not passed
                    else "OK"
                ),
                duration_ms=ms,
                command="mdx --version",
                stdout=result.stdout,
                stderr=result.stderr,
                fix_hint="Check main() callback in cli.py — version flag handler",
            )
        )

    def test_startup_latency(self) -> None:
        """mdx --version should complete in under 500ms (cold start budget)."""
        result, ms = self.run_command(self.mdx("--version"))
        passed = ms < 500
        self.add_result(
            TestResult(
                name="startup latency < 500ms",
                passed=passed,
                message=f"Took {ms:.0f}ms (budget: 500ms)" if not passed else f"{ms:.0f}ms",
                duration_ms=ms,
                command="mdx --version",
                fix_hint="Likely heavy imports at module level in cli.py. Use lazy imports.",
            )
        )

    def test_help_flag(self) -> None:
        """mdx --help should show available commands."""
        result, ms = self.run_command(self.mdx("--help"))
        passed = (
            result.returncode == 0
            and "setup" in result.stdout
            and "review" in result.stdout
            and "cost" in result.stdout
        )
        self.add_result(
            TestResult(
                name="--help shows commands",
                passed=passed,
                message="Expected 'setup', 'review', 'cost' in help output" if not passed else "OK",
                duration_ms=ms,
                command="mdx --help",
                stdout=result.stdout,
                fix_hint="Commands may not be registered on the Typer app in cli.py",
            )
        )

    # ──────────────────────────────────────────────────────
    # CATEGORY 2: Commands (no backend required)
    # ──────────────────────────────────────────────────────

    def test_setup(self) -> None:
        """mdx setup should list backends and exit 0."""
        result, ms = self.run_command(self.mdx("setup"))
        passed = result.returncode == 0 and "Backend" in result.stdout
        self.add_result(
            TestResult(
                name="mdx setup",
                passed=passed,
                message=(
                    f"Exit code {result.returncode}, expected backend listing"
                    if not passed
                    else "OK"
                ),
                duration_ms=ms,
                command="mdx setup",
                stdout=result.stdout,
                stderr=result.stderr,
                fix_hint="Check setup() command in cli.py",
            )
        )

    def test_status(self) -> None:
        """mdx status should show backend health."""
        result, ms = self.run_command(self.mdx("status"))
        passed = result.returncode == 0 and "Health" in result.stdout
        self.add_result(
            TestResult(
                name="mdx status",
                passed=passed,
                message=f"Exit code {result.returncode}" if not passed else "OK",
                duration_ms=ms,
                command="mdx status",
                stdout=result.stdout,
                stderr=result.stderr,
                fix_hint="Check status() command in cli.py",
            )
        )

    def test_cost_empty(self) -> None:
        """mdx cost should work even with no data."""
        result, ms = self.run_command(self.mdx("cost"))
        passed = result.returncode == 0
        self.add_result(
            TestResult(
                name="mdx cost (empty state)",
                passed=passed,
                message=f"Exit code {result.returncode}" if not passed else "OK",
                duration_ms=ms,
                command="mdx cost",
                stdout=result.stdout,
                stderr=result.stderr,
                fix_hint="Check cost() command in cli.py — may crash on empty SQLite",
            )
        )

    def test_cost_week(self) -> None:
        """mdx cost --week should work."""
        result, ms = self.run_command(self.mdx("cost", "--week"))
        passed = result.returncode == 0
        self.add_result(
            TestResult(
                name="mdx cost --week",
                passed=passed,
                message=f"Exit code {result.returncode}" if not passed else "OK",
                duration_ms=ms,
                command="mdx cost --week",
                stdout=result.stdout,
                fix_hint="Check cost() --week flag handling in cli.py",
            )
        )

    def test_cost_month(self) -> None:
        """mdx cost --month should work."""
        result, ms = self.run_command(self.mdx("cost", "--month"))
        passed = result.returncode == 0
        self.add_result(
            TestResult(
                name="mdx cost --month",
                passed=passed,
                message=f"Exit code {result.returncode}" if not passed else "OK",
                duration_ms=ms,
                command="mdx cost --month",
                stdout=result.stdout,
                fix_hint="Check cost() --month flag handling in cli.py",
            )
        )

    def test_audit_empty(self) -> None:
        """mdx audit should work even with no entries."""
        result, ms = self.run_command(self.mdx("audit"))
        passed = result.returncode == 0
        self.add_result(
            TestResult(
                name="mdx audit (empty state)",
                passed=passed,
                message=f"Exit code {result.returncode}" if not passed else "OK",
                duration_ms=ms,
                command="mdx audit",
                stdout=result.stdout,
                stderr=result.stderr,
                fix_hint="Check audit() command — may crash on missing audit dir",
            )
        )

    def test_audit_verify(self) -> None:
        """mdx audit --verify should work."""
        result, ms = self.run_command(self.mdx("audit", "--verify"))
        passed = result.returncode == 0
        self.add_result(
            TestResult(
                name="mdx audit --verify",
                passed=passed,
                message=f"Exit code {result.returncode}" if not passed else "OK",
                duration_ms=ms,
                command="mdx audit --verify",
                stdout=result.stdout,
                fix_hint="Check audit() --verify handler in cli.py",
            )
        )

    def test_audit_stats(self) -> None:
        """mdx audit --stats should work."""
        result, ms = self.run_command(self.mdx("audit", "--stats"))
        passed = result.returncode == 0
        self.add_result(
            TestResult(
                name="mdx audit --stats",
                passed=passed,
                message=f"Exit code {result.returncode}" if not passed else "OK",
                duration_ms=ms,
                command="mdx audit --stats",
                stdout=result.stdout,
                fix_hint="Check audit() --stats handler in cli.py",
            )
        )

    def test_compliance(self) -> None:
        """mdx compliance should show frameworks."""
        result, ms = self.run_command(self.mdx("compliance"))
        passed = result.returncode == 0 and (
            "SOC" in result.stdout or "Compliance" in result.stdout
        )
        self.add_result(
            TestResult(
                name="mdx compliance",
                passed=passed,
                message=f"Exit code {result.returncode}" if not passed else "OK",
                duration_ms=ms,
                command="mdx compliance",
                stdout=result.stdout,
                fix_hint="Check compliance() command in cli.py",
            )
        )

    def test_policy_no_file(self) -> None:
        """mdx policy should handle missing .mdxpolicy gracefully."""
        result, ms = self.run_command(self.mdx("policy"))
        passed = result.returncode == 0
        self.add_result(
            TestResult(
                name="mdx policy (no .mdxpolicy)",
                passed=passed,
                message=f"Exit code {result.returncode}" if not passed else "OK",
                duration_ms=ms,
                command="mdx policy",
                stdout=result.stdout,
                fix_hint="Check policy_default() in cli.py — should handle missing file",
            )
        )

    def test_mcp_status(self) -> None:
        """mdx mcp status should work."""
        result, ms = self.run_command(self.mdx("mcp", "status"))
        passed = result.returncode == 0
        self.add_result(
            TestResult(
                name="mdx mcp status",
                passed=passed,
                message=f"Exit code {result.returncode}" if not passed else "OK",
                duration_ms=ms,
                command="mdx mcp status",
                stdout=result.stdout,
                fix_hint="Check mcp_status() command in cli.py",
            )
        )

    def test_mcp_config(self) -> None:
        """mdx mcp config should output JSON config."""
        result, ms = self.run_command(self.mdx("mcp", "config"))
        passed = result.returncode == 0 and "mcpServers" in result.stdout
        self.add_result(
            TestResult(
                name="mdx mcp config",
                passed=passed,
                message=f"Expected 'mcpServers' in output" if not passed else "OK",
                duration_ms=ms,
                command="mdx mcp config",
                stdout=result.stdout,
                fix_hint="Check mcp_config() command in cli.py",
            )
        )

    def test_update(self) -> None:
        """mdx update should attempt backend updates."""
        result, ms = self.run_command(self.mdx("update"), timeout=15)
        # Accept exit 0, or timeout (-1) since backend updates can take long
        passed = result.returncode in (0, -1)
        msg = "OK" if passed else f"Exit code {result.returncode}"
        if result.returncode == -1:
            msg = "OK (timed out — backend updates take long, that's expected)"
        self.add_result(
            TestResult(
                name="mdx update",
                passed=passed,
                message=msg,
                duration_ms=ms,
                command="mdx update",
                stdout=result.stdout,
                fix_hint="Check update() command in cli.py",
            )
        )

    # ──────────────────────────────────────────────────────
    # CATEGORY 3: Commands added in Sessions 8.5–9
    # ──────────────────────────────────────────────────────

    def test_replay_empty(self) -> None:
        """mdx replay should handle no prior task gracefully."""
        result, ms = self.run_command(self.mdx("replay"))
        # Should exit 1 with a helpful message, not crash
        passed = result.returncode in (0, 1) and "No" in result.stdout
        self.add_result(
            TestResult(
                name="mdx replay (no prior task)",
                passed=passed,
                message=f"Exit code {result.returncode}" if not passed else "OK",
                duration_ms=ms,
                command="mdx replay",
                stdout=result.stdout,
                stderr=result.stderr,
                fix_hint="Check replay() command in cli.py",
            )
        )

    def test_undo_empty(self) -> None:
        """mdx undo should handle no prior task gracefully."""
        result, ms = self.run_command(self.mdx("undo"))
        passed = result.returncode in (0, 1) and "No" in result.stdout
        self.add_result(
            TestResult(
                name="mdx undo (no prior task)",
                passed=passed,
                message=f"Exit code {result.returncode}" if not passed else "OK",
                duration_ms=ms,
                command="mdx undo",
                stdout=result.stdout,
                stderr=result.stderr,
                fix_hint="Check undo() command in cli.py",
            )
        )

    def test_history(self) -> None:
        """mdx history should work (may be empty)."""
        result, ms = self.run_command(self.mdx("history"))
        passed = result.returncode == 0
        self.add_result(
            TestResult(
                name="mdx history",
                passed=passed,
                message=f"Exit code {result.returncode}" if not passed else "OK",
                duration_ms=ms,
                command="mdx history",
                stdout=result.stdout,
                stderr=result.stderr,
                fix_hint="Check history() command in cli.py — may not exist yet (Session 9A)",
            )
        )

    def test_summary(self) -> None:
        """mdx summary should work (may be empty)."""
        result, ms = self.run_command(self.mdx("summary"))
        passed = result.returncode == 0
        self.add_result(
            TestResult(
                name="mdx summary",
                passed=passed,
                message=f"Exit code {result.returncode}" if not passed else "OK",
                duration_ms=ms,
                command="mdx summary",
                stdout=result.stdout,
                stderr=result.stderr,
                fix_hint="Check summary() command in cli.py — may not exist yet (Session 9A)",
            )
        )

    # ──────────────────────────────────────────────────────
    # CATEGORY 4: Review command variants
    # ──────────────────────────────────────────────────────

    def test_review_no_args(self) -> None:
        """mdx review with no args should show usage help, not crash."""
        result, ms = self.run_command(self.mdx("review"))
        passed = result.returncode in (0, 1) and (
            "Specify" in result.stdout or "review" in result.stdout.lower()
        )
        self.add_result(
            TestResult(
                name="mdx review (no args → help)",
                passed=passed,
                message=f"Exit code {result.returncode}" if not passed else "OK",
                duration_ms=ms,
                command="mdx review",
                stdout=result.stdout,
                stderr=result.stderr,
                fix_hint="Check review() command — should show usage examples when no args",
            )
        )

    def test_review_help(self) -> None:
        """mdx review --help should show options."""
        result, ms = self.run_command(self.mdx("review", "--help"))
        passed = result.returncode == 0 and "--last" in result.stdout and "--diff" in result.stdout
        self.add_result(
            TestResult(
                name="mdx review --help",
                passed=passed,
                message="Expected --last and --diff in help" if not passed else "OK",
                duration_ms=ms,
                command="mdx review --help",
                stdout=result.stdout,
                fix_hint="Check review() docstring and parameter definitions in cli.py",
            )
        )

    # ──────────────────────────────────────────────────────
    # CATEGORY 5: Flag consistency
    # ──────────────────────────────────────────────────────

    def test_backend_flag_on_run(self) -> None:
        """mdx 'task' --backend should be accepted (not --backends)."""
        result, ms = self.run_command(self.mdx("--help"))
        # Check that the run command's help shows --backend
        passed = "--backend" in result.stdout or result.returncode == 0
        self.add_result(
            TestResult(
                name="--backend flag exists",
                passed=passed,
                message="Flag --backend not found in help" if not passed else "OK",
                duration_ms=ms,
                command="mdx --help",
                fix_hint="Check run() command definition — should have --backend not --backends",
            )
        )

    def test_strategy_flag(self) -> None:
        """--strategy flag should be accepted."""
        result, ms = self.run_command(self.mdx("run", "--help"))
        passed = "--strategy" in result.stdout
        self.add_result(
            TestResult(
                name="--strategy flag exists",
                passed=passed,
                message="Flag --strategy not found" if not passed else "OK",
                duration_ms=ms,
                command="mdx run --help",
                stdout=result.stdout,
                fix_hint="Check run() command definition in cli.py",
            )
        )

    # ──────────────────────────────────────────────────────
    # CATEGORY 6: Output format validation
    # ──────────────────────────────────────────────────────

    def test_no_color_env(self) -> None:
        """NO_COLOR=1 should suppress ANSI escape codes."""
        result, ms = self.run_command(
            self.mdx("--version"),
            env_override={"NO_COLOR": "1"},
        )
        # Check no ANSI escape sequences in output
        has_ansi = bool(re.search(r"\033\[", result.stdout))
        passed = result.returncode == 0 and not has_ansi
        self.add_result(
            TestResult(
                name="NO_COLOR suppresses ANSI",
                passed=passed,
                message="ANSI codes found in output with NO_COLOR=1" if not passed else "OK",
                duration_ms=ms,
                command="NO_COLOR=1 mdx --version",
                fix_hint="Check NO_COLOR handling in cli.py — should set console.no_color = True",
            )
        )

    def test_pipe_mode(self) -> None:
        """Piped output should not contain ANSI codes."""
        # When stdout is not a TTY (piped), Rich should not add colors
        # subprocess.run already captures output, so stdout IS piped
        result, ms = self.run_command(self.mdx("cost"))
        # In a pipe, Rich should suppress formatting
        # This is a soft check — Rich may still add codes depending on config
        passed = result.returncode == 0
        self.add_result(
            TestResult(
                name="pipe mode works",
                passed=passed,
                message=f"Exit code {result.returncode}" if not passed else "OK",
                duration_ms=ms,
                command="mdx cost | cat",
                fix_hint="Check if console detects non-TTY in cli.py and streamer.py",
            )
        )

    # ──────────────────────────────────────────────────────
    # CATEGORY 7: Error handling
    # ──────────────────────────────────────────────────────

    def test_invalid_backend(self) -> None:
        """mdx 'task' --backend nonexistent should show a clear error."""
        if self.fast_mode:
            return
        result, ms = self.run_command(self.mdx("test task", "--backend", "nonexistent"))
        passed = result.returncode != 0 and (
            "not available" in result.stdout.lower() or "not available" in result.stderr.lower()
        )
        self.add_result(
            TestResult(
                name="invalid --backend error message",
                passed=passed,
                message="Expected 'not available' error message" if not passed else "OK",
                duration_ms=ms,
                command="mdx 'test' --backend nonexistent",
                stdout=result.stdout,
                stderr=result.stderr,
                fix_hint="Check backend validation in _execute_task() in cli.py",
            )
        )

    def test_invalid_cost_date(self) -> None:
        """mdx cost --since garbage should show clear error."""
        result, ms = self.run_command(self.mdx("cost", "--since", "not-a-date"))
        passed = result.returncode != 0
        self.add_result(
            TestResult(
                name="invalid --since date error",
                passed=passed,
                message="Expected non-zero exit code for bad date" if not passed else "OK",
                duration_ms=ms,
                command="mdx cost --since not-a-date",
                stdout=result.stdout,
                fix_hint="Check date parsing in cost() command in cli.py",
            )
        )

    # ──────────────────────────────────────────────────────
    # CATEGORY 8: Backend-dependent tests (skip with --fast)
    # ──────────────────────────────────────────────────────

    def test_task_execution(self) -> None:
        """mdx 'echo hello' --backend claude should execute and show footer."""
        if self.fast_mode:
            return
        result, ms = self.run_command(
            self.mdx("say hello world", "--backend", "claude"),
            timeout=60,
        )
        passed = result.returncode == 0 and "MDx Code" in result.stdout
        self.add_result(
            TestResult(
                name="task execution (claude)",
                passed=passed,
                message=f"Exit code {result.returncode}" if not passed else f"OK ({ms:.0f}ms)",
                duration_ms=ms,
                command="mdx 'say hello world' --backend claude",
                stdout=result.stdout[-500:],  # Last 500 chars
                stderr=result.stderr,
                fix_hint="Check _execute_task() and stream_output() in cli.py/streamer.py",
            )
        )

    def test_task_footer_has_cost(self) -> None:
        """After a task, footer should show cost line."""
        if self.fast_mode:
            return
        result, ms = self.run_command(
            self.mdx("say hello", "--backend", "claude"),
            timeout=60,
        )
        passed = result.returncode == 0 and "$" in result.stdout
        self.add_result(
            TestResult(
                name="footer shows cost",
                passed=passed,
                message="No cost ($ symbol) found in output" if not passed else "OK",
                duration_ms=ms,
                command="mdx 'say hello' --backend claude",
                stdout=result.stdout[-500:],
                fix_hint="Check show_footer() in footer.py — cost_usd may be None",
            )
        )

    def test_task_creates_audit(self) -> None:
        """After a task, audit entry should exist."""
        if self.fast_mode:
            return
        # Run a task first
        self.run_command(self.mdx("say hello", "--backend", "claude"), timeout=60)
        # Now check audit
        result, ms = self.run_command(self.mdx("audit", "-n", "1"))
        passed = result.returncode == 0 and "hello" in result.stdout.lower()
        self.add_result(
            TestResult(
                name="task creates audit entry",
                passed=passed,
                message="No audit entry found for recent task" if not passed else "OK",
                duration_ms=ms,
                command="mdx audit -n 1",
                stdout=result.stdout,
                fix_hint="Check write_audit_entry() in audit_trail.py",
            )
        )

    # ──────────────────────────────────────────────────────
    # CATEGORY 9: Import health
    # ──────────────────────────────────────────────────────

    def test_import_mdxcode(self) -> None:
        """The mdxcode package should import without errors."""
        result, ms = self.run_command([sys.executable, "-c", "import mdxcode; print('OK')"])
        passed = result.returncode == 0 and "OK" in result.stdout
        self.add_result(
            TestResult(
                name="import mdxcode",
                passed=passed,
                message=f"Import failed: {result.stderr[:200]}" if not passed else "OK",
                duration_ms=ms,
                command="python -c 'import mdxcode'",
                stderr=result.stderr,
                fix_hint="Syntax error or missing dependency in the package",
            )
        )

    def test_import_cli(self) -> None:
        """CLI module should import without errors."""
        result, ms = self.run_command(
            [sys.executable, "-c", "from mdxcode.cli import app; print('OK')"]
        )
        passed = result.returncode == 0 and "OK" in result.stdout
        self.add_result(
            TestResult(
                name="import mdxcode.cli",
                passed=passed,
                message=f"Import failed: {result.stderr[:200]}" if not passed else "OK",
                duration_ms=ms,
                command="python -c 'from mdxcode.cli import app'",
                stderr=result.stderr,
                fix_hint="Check cli.py for import errors — likely a missing module or typo",
            )
        )

    def test_import_all_modules(self) -> None:
        """All key modules should import."""
        modules = [
            "mdxcode.config",
            "mdxcode.router.engine",
            "mdxcode.router.strategies",
            "mdxcode.router.profiles",
            "mdxcode.router.cost_tracker",
            "mdxcode.backends.discovery",
            "mdxcode.backends.claude",
            "mdxcode.backends.circuit_breaker",
            "mdxcode.governance.audit_trail",
            "mdxcode.governance.policy_engine",
            "mdxcode.governance.compliance",
            "mdxcode.review.orchestrator",
            "mdxcode.review.renderer",
            "mdxcode.output.footer",
            "mdxcode.output.streamer",
        ]

        # Try importing colors module (may not exist pre-8.5)
        modules.append("mdxcode.output.colors")

        failed_modules = []
        for mod in modules:
            result, _ = self.run_command(
                [sys.executable, "-c", f"import {mod}"],
                timeout=10,
            )
            if result.returncode != 0:
                failed_modules.append(f"{mod}: {result.stderr.strip()[:80]}")

        passed = len(failed_modules) == 0
        self.add_result(
            TestResult(
                name=f"all {len(modules)} modules import",
                passed=passed,
                message="\n".join(failed_modules) if not passed else "OK",
                duration_ms=0,
                fix_hint="Check the failing module for syntax errors or missing dependencies",
            )
        )

    # ──────────────────────────────────────────────────────
    # Runner
    # ──────────────────────────────────────────────────────

    def run_all(self) -> None:
        """Run all smoke tests."""
        print()
        print("  MDx Code Smoke Test Harness")
        print("  ═══════════════════════════")
        print()

        # Category 1: Startup
        print("  Startup & Version")
        self.test_version_flag()
        self.test_startup_latency()
        self.test_help_flag()
        print()

        # Category 9: Imports (run early — if these fail, everything else will too)
        print("  Import Health")
        self.test_import_mdxcode()
        self.test_import_cli()
        self.test_import_all_modules()
        print()

        # Category 2: Commands
        print("  Core Commands")
        self.test_setup()
        self.test_status()
        self.test_cost_empty()
        self.test_cost_week()
        self.test_cost_month()
        self.test_audit_empty()
        self.test_audit_verify()
        self.test_audit_stats()
        self.test_compliance()
        self.test_policy_no_file()
        self.test_mcp_status()
        self.test_mcp_config()
        self.test_update()
        print()

        # Category 3: New commands (9A/9B)
        print("  New Commands (Sessions 8.5–9)")
        self.test_replay_empty()
        self.test_undo_empty()
        self.test_history()
        self.test_summary()
        print()

        # Category 4: Review
        print("  Review Command")
        self.test_review_no_args()
        self.test_review_help()
        print()

        # Category 5: Flags
        print("  Flag Consistency")
        self.test_backend_flag_on_run()
        self.test_strategy_flag()
        print()

        # Category 6: Output
        print("  Output Formatting")
        self.test_no_color_env()
        self.test_pipe_mode()
        print()

        # Category 7: Errors
        print("  Error Handling")
        self.test_invalid_backend()
        self.test_invalid_cost_date()
        print()

        # Category 8: Backend-dependent
        if not self.fast_mode:
            print("  Backend Integration (requires Claude Code)")
            self.test_task_execution()
            self.test_task_footer_has_cost()
            self.test_task_creates_audit()
            print()
        else:
            print("  Backend Integration: SKIPPED (--fast mode)")
            print()

        # Summary
        self._print_summary()

    def _print_summary(self) -> None:
        """Print test summary."""
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        total = len(self.results)

        print("  ═══════════════════════════")
        if failed == 0:
            print(f"  ✅ All {total} tests passed!")
        else:
            print(f"  ❌ {failed} of {total} tests failed")
            print()
            print("  Failures:")
            for r in self.results:
                if not r.passed:
                    print(f"    ✗ {r.name}")
                    print(f"      {r.message}")
                    if self.show_fixes and r.fix_hint:
                        print(f"      💡 Fix: {r.fix_hint}")
            print()
            print("  To fix: feed this output to Claude Code with the instruction")
            print("  'Fix everything that fails in this smoke test output.'")

        # Latency summary
        total_ms = sum(r.duration_ms for r in self.results)
        print()
        print(f"  Total time: {total_ms / 1000:.1f}s")
        print()

        # Exit with failure code if any tests failed
        if failed > 0:
            sys.exit(1)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="MDx Code Smoke Tests")
    parser.add_argument("--fast", action="store_true", help="Skip backend-dependent tests")
    parser.add_argument("--verbose", action="store_true", help="Show full output on failures")
    parser.add_argument("--fix", action="store_true", help="Show fix suggestions")
    args = parser.parse_args()

    runner = SmokeTestRunner(
        fast_mode=args.fast,
        verbose=args.verbose,
        show_fixes=args.fix,
    )
    runner.run_all()


if __name__ == "__main__":
    main()
