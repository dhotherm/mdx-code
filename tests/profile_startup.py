"""
Profile MDx Code startup and execution overhead.

Usage:
    python tests/profile_startup.py              # Full profile
    python tests/profile_startup.py --imports     # Just import timing
    python tests/profile_startup.py --routing     # Just routing timing
"""

import cProfile
import importlib
import os
import pstats
import subprocess
import sys
import time
from io import StringIO
from pathlib import Path


def profile_cold_start():
    """Measure cold start: mdx --version end-to-end."""
    print("\n  Cold Start Profile (mdx --version)")
    print("  " + "─" * 40)

    times = []
    for i in range(5):
        start = time.monotonic()
        result = subprocess.run(
            ["mdx", "--version"],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        )
        elapsed = (time.monotonic() - start) * 1000
        times.append(elapsed)

    avg = sum(times) / len(times)
    p50 = sorted(times)[len(times) // 2]
    p99 = sorted(times)[-1]

    print(f"  Runs: {len(times)}")
    print(f"  Avg:  {avg:.0f}ms")
    print(f"  P50:  {p50:.0f}ms")
    print(f"  P99:  {p99:.0f}ms")
    print(f"  Budget: 80ms")
    status = "✓ PASS" if p50 < 80 else f"✗ OVER by {p50 - 80:.0f}ms"
    print(f"  Status: {status}")


def profile_imports():
    """Measure import time for each module."""
    print("\n  Import Profiling")
    print("  " + "─" * 40)

    modules = [
        ("typer", "typer"),
        ("click", "click"),
        ("rich", "rich"),
        ("rich.console", "rich.console"),
        ("rich.table", "rich.table"),
        ("rich.markdown", "rich.markdown"),
        ("pydantic", "pydantic"),
        ("yaml", "yaml"),
        ("mdxcode", "mdxcode"),
        ("mdxcode.cli", "mdxcode.cli"),
        ("mdxcode.config", "mdxcode.config"),
        ("mdxcode.router.engine", "mdxcode.router.engine"),
        ("mdxcode.router.strategies", "mdxcode.router.strategies"),
        ("mdxcode.router.profiles", "mdxcode.router.profiles"),
        ("mdxcode.backends.discovery", "mdxcode.backends.discovery"),
        ("mdxcode.governance.audit_trail", "mdxcode.governance.audit_trail"),
        ("mdxcode.output.footer", "mdxcode.output.footer"),
        ("mdxcode.output.streamer", "mdxcode.output.streamer"),
    ]

    total = 0
    results = []

    for display_name, module_name in modules:
        # Unload if already loaded
        mods_to_remove = [k for k in sys.modules if k.startswith(module_name.split(".")[0])]

        start = time.monotonic()
        try:
            importlib.import_module(module_name)
            elapsed = (time.monotonic() - start) * 1000
            results.append((display_name, elapsed))
            total += elapsed
        except ImportError as e:
            results.append((display_name, -1))

    # Sort by time descending
    results.sort(key=lambda x: x[1], reverse=True)

    for name, ms in results:
        if ms < 0:
            print(f"    {name:<35} MISSING")
        elif ms > 20:
            print(f"    {name:<35} {ms:>6.1f}ms  ⚠️  SLOW")
        elif ms > 5:
            print(f"    {name:<35} {ms:>6.1f}ms")
        else:
            print(f"    {name:<35} {ms:>6.1f}ms  ✓")

    print(f"\n  Total import time: {total:.0f}ms")
    print(f"  Budget: 80ms")
    note = "(note: cached after first import)" if total > 200 else ""
    print(f"  {note}")


def profile_routing():
    """Measure routing decision time."""
    print("\n  Routing Decision Profile")
    print("  " + "─" * 40)

    # Import routing modules
    from mdxcode.router.engine import categorize_task
    from mdxcode.router.profiles import get_profiles
    from mdxcode.router.strategies import route_task

    tasks = [
        "fix the login bug",
        "add unit tests for the auth module",
        "refactor the database connection pool",
        "review this code for security issues",
        "write documentation for the API",
        "describe this project",
    ]

    profiles = get_profiles()
    backends = ["claude", "gemini", "codex"]

    for task in tasks:
        start = time.monotonic()

        # Full routing pipeline
        category = categorize_task(task)
        decision = route_task(category, backends, profiles, "balanced")

        elapsed = (time.monotonic() - start) * 1000

        backend = decision.backend_name if decision else "none"
        status = "✓" if elapsed < 20 else "⚠️"
        print(f"    {status} {elapsed:>5.1f}ms  {task[:40]:<42} → {backend}")

    print(f"\n  Budget: 20ms per decision")


def profile_io():
    """Measure I/O operations: config load, SQLite, audit."""
    print("\n  I/O Operation Profile")
    print("  " + "─" * 40)

    # Config load
    start = time.monotonic()
    from mdxcode.config import load_config

    config = load_config()
    config_ms = (time.monotonic() - start) * 1000
    print(f"    Config load:        {config_ms:>6.1f}ms")

    # Circuit breaker load
    start = time.monotonic()
    from mdxcode.backends.circuit_breaker import get_circuit_breaker

    cb = get_circuit_breaker()
    cb_ms = (time.monotonic() - start) * 1000
    print(f"    Circuit breaker:    {cb_ms:>6.1f}ms")

    # SQLite cost read
    start = time.monotonic()
    from mdxcode.router.cost_tracker import get_date_range_for_period, get_total_cost

    since, until = get_date_range_for_period("today")
    total = get_total_cost(since=since, until=until)
    cost_ms = (time.monotonic() - start) * 1000
    print(f"    Cost DB read:       {cost_ms:>6.1f}ms")

    # Audit read (recent entries)
    start = time.monotonic()
    from mdxcode.governance.audit_trail import read_recent_entries

    entries = read_recent_entries(count=10)
    audit_ms = (time.monotonic() - start) * 1000
    print(f"    Audit read (10):    {audit_ms:>6.1f}ms")

    total_ms = config_ms + cb_ms + cost_ms + audit_ms
    print(f"\n  Total I/O: {total_ms:.0f}ms")
    print(f"  Budget: 50ms (pre-execution)")


def profile_git_operations():
    """Measure git subprocess calls."""
    print("\n  Git Operation Profile")
    print("  " + "─" * 40)

    git_commands = [
        ("branch --show-current", ["git", "branch", "--show-current"]),
        ("ls-files (file count)", ["git", "ls-files"]),
        ("diff HEAD", ["git", "diff", "HEAD"]),
        ("diff --name-only HEAD", ["git", "diff", "--name-only", "HEAD"]),
    ]

    for label, cmd in git_commands:
        start = time.monotonic()
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            elapsed = (time.monotonic() - start) * 1000
            status = "✓" if elapsed < 30 else "⚠️"
            print(f"    {status} {label:<30} {elapsed:>6.1f}ms")
        except Exception as e:
            print(f"    ✗ {label:<30} ERROR: {e}")


def run_cprofile():
    """Run cProfile on the hot path."""
    print("\n  cProfile: Task Routing Hot Path")
    print("  " + "─" * 40)

    profiler = cProfile.Profile()

    from mdxcode.router.engine import categorize_task
    from mdxcode.router.profiles import get_profiles
    from mdxcode.router.strategies import route_task

    profiles = get_profiles()
    backends = ["claude", "gemini", "codex"]

    profiler.enable()
    for _ in range(100):
        category = categorize_task("fix the authentication bug in login.py")
        route_task(category, backends, profiles, "balanced")
    profiler.disable()

    # Print top 10 by cumulative time
    stream = StringIO()
    stats = pstats.Stats(profiler, stream=stream)
    stats.sort_stats("cumulative")
    stats.print_stats(10)
    print(stream.getvalue())


def main():
    import argparse

    parser = argparse.ArgumentParser(description="MDx Code Performance Profile")
    parser.add_argument("--imports", action="store_true", help="Profile imports only")
    parser.add_argument("--routing", action="store_true", help="Profile routing only")
    parser.add_argument("--io", action="store_true", help="Profile I/O only")
    parser.add_argument("--git", action="store_true", help="Profile git operations only")
    parser.add_argument("--cprofile", action="store_true", help="Run cProfile on hot path")
    args = parser.parse_args()

    print()
    print("  MDx Code Performance Profile")
    print("  ═══════════════════════════════")

    if args.imports:
        profile_imports()
    elif args.routing:
        profile_routing()
    elif args.io:
        profile_io()
    elif args.git:
        profile_git_operations()
    elif args.cprofile:
        run_cprofile()
    else:
        # Run everything
        profile_cold_start()
        profile_imports()
        profile_routing()
        profile_io()
        profile_git_operations()

    print()
    print("  ═══════════════════════════════")
    print("  Done. Fix the ⚠️  items first.")
    print()


if __name__ == "__main__":
    main()
