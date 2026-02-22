# Contributing to MDx Code

Thank you for your interest in contributing to MDx Code.

## Development Setup

```bash
# Clone the repo
git clone https://github.com/dhotherm/mdx-code.git
cd mdx-code

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate

# Install in dev mode with all dependencies
pip install -e ".[dev]"

# Verify installation
mdx --version
```

## Running Tests

```bash
# Full test suite (430 tests)
pytest tests/

# Verbose with short tracebacks
pytest tests/ -v --tb=short

# Smoke tests (30 integration tests)
python tests/smoke_test.py --fast

# Single test file
pytest tests/test_router.py -v
```

All tests must pass before submitting a PR. Tests should be fast — mock CLI backends, no real API calls in unit tests.

## Code Style

- **Formatter:** [Black](https://github.com/psf/black), 100-character line length
- **Type hints:** Required on all functions
- **Docstrings:** Required on public methods
- **Python:** 3.11+ features are fine (match statements, `X | Y` unions, etc.)

```bash
# Check formatting
black --check mdxcode/ tests/

# Auto-format
black mdxcode/ tests/

# Type check
mypy mdxcode/ --ignore-missing-imports
```

## Critical Design Constraint

**MDx Code does NOT run its own agent loop.** It delegates to existing AI coding CLIs by spawning them as subprocesses. It wraps them with orchestration (routing, governance, cost tracking, audit). Never create tools, agent loops, or direct AI API calls within MDx Code.

## Project Structure

```
mdxcode/
  cli.py              # All CLI commands (Typer)
  config.py            # Configuration loading (.mdx.yaml, global config)
  backends/            # Adapters for each CLI
    base.py            # Backend abstract base class
    claude.py          # Claude Code adapter
    codex.py           # Codex CLI adapter
    gemini.py          # Gemini CLI adapter
    discovery.py       # Backend auto-detection
    circuit_breaker.py # Resilience pattern
  router/              # Task routing
    engine.py          # Task categorization
    strategies.py      # Routing strategies (balanced, cost, quality)
    profiles.py        # Backend capability profiles
    cost_tracker.py    # SQLite cost tracking
  review/              # Adversarial review
    orchestrator.py    # Multi-backend review coordination
    normalizer.py      # Finding normalization
    consensus.py       # Cross-validation consensus
  governance/          # Enterprise governance
    audit_trail.py     # Chain-hashed JSONL audit
    policy_engine.py   # Policy evaluation
    compliance.py      # Regulatory compliance matrix
  output/              # Output handling
    streamer.py        # Real-time streaming with Rich
    footer.py          # Post-task footer
    colors.py          # Terminal colors
mcp_servers/           # MCP protocol servers
tests/                 # Test suite
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed design documentation.

## Adding a New Backend

1. Create `mdxcode/backends/your_backend.py`
2. Extend `Backend` from `base.py`
3. Implement all abstract methods: `name`, `cli_command`, `is_available()`, `get_info()`, `execute()`, `execute_and_capture()`, `health_check()`
4. Register in `mdxcode/backends/discovery.py` (`BACKEND_CLASSES`, `KNOWN_CLIS`)
5. Add a capability profile in `mdxcode/router/profiles.py`
6. Add tests in `tests/`

## Adding a New Command

1. Add the command function in `mdxcode/cli.py`
2. Use `@app.command()` decorator (follow existing patterns)
3. Use Rich for output formatting
4. Add tests for the new command
5. Update the commands table in `README.md`

## Pull Request Process

1. Branch from `main`
2. Make your changes with tests
3. Ensure all tests pass: `pytest tests/ -v`
4. Ensure formatting passes: `black --check mdxcode/ tests/`
5. Write a clear PR description explaining the what and why
6. One approval required for merge

## Reporting Issues

Use [GitHub Issues](https://github.com/dhotherm/mdx-code/issues). Include:

- MDx Code version (`mdx --version`)
- Python version
- OS
- Steps to reproduce
- Expected vs actual behavior
