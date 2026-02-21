# MDx Code

**The AI Engineering Manager for your codebase.**

Orchestrates multiple AI coding CLIs with governance, adversarial review, audit trails, and cost tracking.

## The Hook

Run the same task through two models. Get findings neither would catch alone:

```
$ mdx review src/auth/

  Adversarial Review: src/auth/
  ──────────────────────────────

  Claude found 4 issues    Codex found 3 issues

  Cross-validated: 2 agreed    Unique: 3

  Neither model alone found all 5 real issues.
```

## Quick Install

```bash
curl -fsSL https://raw.githubusercontent.com/dhotherm/mdx-code/main/install.sh | bash
```

First-run wizard guides you through setup automatically.

### Manual Install

```bash
pip install -e .
mdx setup
```

## Commands

| Command | Description |
|---------|-------------|
| `mdx "task"` | Execute via best available backend |
| `mdx review src/` | Adversarial multi-model review |
| `mdx review --last` | Review last change MDx made |
| `mdx review --diff HEAD~1` | Review a git diff |
| `mdx cost` | Spending dashboard |
| `mdx cost --week` | Weekly cost breakdown |
| `mdx audit` | Audit trail history |
| `mdx audit --verify` | Verify audit chain integrity |
| `mdx audit --stats` | Audit summary statistics |
| `mdx setup` | Detect available backends |
| `mdx status` | Backend health and circuit breakers |
| `mdx policy` | View active policies |
| `mdx policy init` | Create starter .mdxpolicy |
| `mdx policy check <files>` | Check files against policies |
| `mdx compliance` | Regulatory compliance matrix |
| `mdx hook install` | Git pre-commit hook |
| `mdx mcp status` | MCP server availability |
| `mdx mcp config` | Generate MCP client config |

## How It Works

MDx Code does **not** run its own agent loop. It spawns real AI coding CLIs (`claude`, `codex`, `gemini`) as subprocesses, streams their output in real-time, and wraps everything with orchestration: smart routing, cost tracking, governance policies, and an immutable audit trail.

## Key Features

- **Multi-backend routing** — Automatically routes tasks to the best available CLI based on cost, quality, or balanced strategies
- **Adversarial review** — Run code through multiple models and cross-validate findings
- **Governance policies** — Define per-path rules for review requirements and approval gates
- **Cost tracking** — Token and dollar spend across all backends with savings analysis
- **Audit trail** — Immutable, chain-hashed JSONL logs of every action
- **MCP servers** — Expose governance, audit, and cost data to MCP-compatible clients
- **Circuit breakers** — Automatic fallback when a backend is unhealthy

## Requirements

- Python 3.11+
- At least one AI coding CLI: [Claude Code](https://github.com/anthropics/claude-code), [Codex CLI](https://github.com/openai/codex), or [Gemini CLI](https://github.com/google-gemini/gemini-cli)

## License

MIT
