# CLAUDE.md — MDx Code v2

## What This Is
MDx Code is the AI Engineering Manager for codebases. It orchestrates
multiple AI coding CLIs (Claude Code, Codex CLI, Gemini CLI) and adds
governance, adversarial review, audit trails, and cost tracking.

## Critical: MDx Code Does NOT Run Its Own Agent Loop
MDx Code delegates to existing CLIs by spawning them as subprocesses.
It wraps them with orchestration. Don't create tools or agent loops.

## Architecture
- `backends/` — Adapters for each CLI (spawn subprocess, stream output)
- `router/` — Smart routing and cost tracking (Session 3)
- `review/` — Adversarial multi-model review (Session 4)
- `governance/` — Policy engine, audit trail, compliance

## Tech Stack
- Python 3.11+, Typer + Rich (CLI), asyncio (subprocesses), Pydantic (models)

## Commands
- `mdx "task"` — Execute via best backend
- `mdx review src/` — Adversarial review (Session 4)
- `mdx cost` — Spending dashboard (Session 3)
- `mdx audit` — Audit history
- `mdx setup` — Show available backends

## Git Workflow
- Work on `v2-dev` branch
- NEVER push directly to `main`
- Human squash merges to main after each session

## Testing
- `pytest tests/` — All tests
- Keep tests fast (mock CLIs, no real API calls for unit tests)

## Style
- Black, 100 char lines
- Type hints on all functions
- Docstrings on public methods
