# CLAUDE.md — MDx Code

## What This Is
MDx Code is the AI Engineering Manager for codebases. It orchestrates
multiple AI coding CLIs (Claude Code, Codex CLI, Gemini CLI) and adds
governance, adversarial review, audit trails, and cost tracking.

## Critical: MDx Code Does NOT Run Its Own Agent Loop
MDx Code delegates to existing CLIs by spawning them as subprocesses.
It wraps them with orchestration. Don't create tools or agent loops.

## Architecture
- `backends/` — Adapters for each CLI (spawn subprocess, stream output)
- `router/` — Smart routing, task categorization, cost tracking
- `review/` — Adversarial multi-model review with consensus
- `governance/` — Policy engine, audit trail, compliance matrix
- `output/` — Rich streaming, footer, color support

See [ARCHITECTURE.md](ARCHITECTURE.md) for full design documentation.

## Quick Install
```bash
curl -fsSL https://raw.githubusercontent.com/dhotherm/mdx-code/main/install.sh | bash
```
First-run wizard guides you through setup automatically.

## Tech Stack
- Python 3.11+, Typer + Rich (CLI), asyncio (subprocesses), Pydantic (models)

## Commands
- `mdx "task"` — Execute via best backend
- `mdx "task" --pick` — Interactively pick a backend
- `mdx review src/` — Adversarial review
- `mdx review --last` — Review last change
- `mdx cost` — Spending dashboard
- `mdx audit` — Audit history
- `mdx history` — Recent task history
- `mdx summary` — Today's AI coding summary
- `mdx setup` — Show available backends
- `mdx status` — Backend health
- `mdx policy` — View active policies
- `mdx policy init` — Create starter .mdxpolicy
- `mdx policy check <files>` — Check files against policies
- `mdx compliance` — Regulatory compliance matrix
- `mdx hook install` — Git pre-commit hook
- `mdx replay` — Replay last task output (no re-execution)
- `mdx undo` — Revert last backend change (with confirmation)
- `mdx mcp status` — MCP server availability
- `mdx mcp config` — Generate MCP client config
- `mdx install-completion` — Shell tab-completion setup

## Testing
- `pytest tests/` — Full test suite (430 tests)
- `python tests/smoke_test.py --fast` — Smoke tests (30 tests)
- Keep tests fast (mock CLIs, no real API calls for unit tests)

## Code Style
- Black, 100 char lines
- Type hints on all functions
- Docstrings on public methods

## Adding a New Backend
1. Create `mdxcode/backends/your_backend.py`, extend `Backend` from `base.py`
2. Implement: `name`, `cli_command`, `is_available()`, `get_info()`, `execute()`, `execute_and_capture()`, `health_check()`
3. Register in `backends/discovery.py` (`BACKEND_CLASSES`, `KNOWN_CLIS`)
4. Add capability profile in `router/profiles.py`
5. Add tests

## Adding a New Command
1. Add command function in `mdxcode/cli.py` with `@app.command()`
2. Follow existing patterns (Rich output, error handling)
3. Add tests
4. Update commands table in README.md

## Performance Budget
- Total wrapper overhead must stay under 200ms
- Cold start: 20ms (lazy imports — don't add module-level heavy imports)
- Routing decision: 0.1ms
- Footer displays before async writes complete
