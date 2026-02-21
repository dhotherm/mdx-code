# MDx Code v2

**The AI Engineering Manager for your codebase.**

MDx Code orchestrates multiple AI coding CLIs (Claude Code, Codex CLI, Gemini CLI) and adds governance, adversarial review, audit trails, and cost tracking.

## Quick Start

```bash
pip install -e .
mdx setup          # Detect available backends
mdx "fix the bug"  # Delegate to best available backend
```

## Commands

| Command | Description |
|---------|-------------|
| `mdx "task"` | Execute task via best available backend |
| `mdx setup` | Detect and display available backends |
| `mdx status` | Show current config and backend health |
| `mdx audit` | Show recent audit entries |
| `mdx --version` | Version info |

## How It Works

MDx Code does **not** implement its own agent loop. It spawns real AI coding CLIs as subprocesses, streams their output in real-time, and wraps everything with:

- **Governance** — Policy enforcement and permission checks
- **Audit trails** — Immutable, chain-hashed logs of every action
- **Cost tracking** — Token and dollar spend across all backends
- **Adversarial review** — Multi-model code review (coming soon)

## Requirements

- Python 3.11+
- At least one AI coding CLI installed: `claude`, `codex`, or `gemini`

## License

MIT
