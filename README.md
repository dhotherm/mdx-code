[![CI](https://github.com/dhotherm/mdx-code/actions/workflows/ci.yml/badge.svg)](https://github.com/dhotherm/mdx-code/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests: 430](https://img.shields.io/badge/tests-430-brightgreen.svg)]()
[![Commands: 21](https://img.shields.io/badge/commands-21-blue.svg)]()
[![Overhead: <200ms](https://img.shields.io/badge/overhead-<200ms-green.svg)]()

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

## Why MDx Code Exists

AI coding CLIs are powerful but isolated. Claude Code, Codex CLI, and Gemini CLI each operate as silos — different strengths, different cost profiles, no shared governance. A developer picks one and hopes for the best. There's no routing intelligence, no cross-validation, no audit trail, and no cost visibility across tools.

Enterprises face a harder version of this problem. Regulatory frameworks (SOC 2, HIPAA, OSFI) require auditability. Security-sensitive code needs more than one opinion. Budgets need guardrails. But bolting governance onto each individual CLI doesn't scale — you end up with fragmented policies and no single source of truth.

MDx Code is the missing layer. It doesn't replace your AI coding tools — it orchestrates them. Think of it as the engineering manager that sits between your developers (AI backends) and your organization's policies. It routes tasks to the right model, cross-validates critical code through adversarial review, tracks every action in a chain-hashed audit trail, and gives you a single spending dashboard across all backends. One CLI, multiple brains, full governance.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLI Layer                                │
│  Commands · Flags · Typer/Click · First-run wizard · Banner     │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                      Routing Layer                              │
│  Task categorization · Strategy selection · Backend profiles    │
│  Circuit breakers · Cost estimation · Budget guardrails         │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                     Backend Layer                               │
│  Claude adapter · Codex adapter · Gemini adapter                │
│  Subprocess spawning · Output streaming · Error classification  │
│  Auto-discovery · Health checks · Fallback recovery             │
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                   Governance Layer                              │
│  Policy engine · Compliance matrix · Chain-hashed audit trail   │
│  Adversarial review · Finding consensus · Cost tracking (SQLite)│
└──────────────────────────┬──────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│                      Output Layer                               │
│  Rich streaming · Markdown detection · Footer · Budget display  │
│  NO_COLOR support · Pipe detection · Onboarding tips            │
└─────────────────────────────────────────────────────────────────┘
```

## Commands

| Command | Description |
|---------|-------------|
| `mdx "task"` | Execute via best available backend |
| `mdx "task" --pick` | Interactively pick a backend |
| `mdx "task" --backend claude` | Force a specific backend |
| `mdx "task" --strategy cost` | Override routing strategy |
| `mdx review src/` | Adversarial multi-model review |
| `mdx review --last` | Review last change MDx made |
| `mdx review --diff HEAD~1` | Review a git diff |
| `mdx cost` | Spending dashboard |
| `mdx cost --week` | Weekly cost breakdown |
| `mdx audit` | Audit trail history |
| `mdx audit --verify` | Verify audit chain integrity |
| `mdx audit --stats` | Audit summary statistics |
| `mdx history` | Recent task history |
| `mdx summary` | Today's AI coding summary |
| `mdx setup` | Detect available backends |
| `mdx status` | Backend health and circuit breakers |
| `mdx policy` | View active policies |
| `mdx policy init` | Create starter .mdxpolicy |
| `mdx policy check <files>` | Check files against policies |
| `mdx compliance` | Regulatory compliance matrix |
| `mdx hook install` | Git pre-commit hook |
| `mdx replay` | Replay last task output |
| `mdx undo` | Revert last backend change |
| `mdx mcp status` | MCP server availability |
| `mdx mcp config` | Generate MCP client config |
| `mdx install-completion` | Shell tab-completion |

## How It Works

MDx Code does **not** run its own agent loop. It spawns real AI coding CLIs (`claude`, `codex`, `gemini`) as subprocesses, streams their output in real-time, and wraps everything with orchestration: smart routing, cost tracking, governance policies, and an immutable audit trail.

Every task execution flows through:
1. **Categorize** — Keyword-based task classification (no LLM call)
2. **Route** — Score backends using the selected strategy
3. **Execute** — Spawn the CLI subprocess and stream output
4. **Track** — Record cost (SQLite) and audit entry (chain-hashed JSONL)
5. **Govern** — Evaluate policies and recommend review if triggered

## Key Features

- **Multi-backend routing** — Routes tasks to the best available CLI based on cost, quality, or balanced strategies
- **Adversarial review** — Run code through multiple models and cross-validate findings with consensus scoring
- **Governance policies** — Define per-path rules for review requirements, approval gates, and minimum reviewers
- **Cost tracking** — Token and dollar spend across all backends with savings analysis and budget guardrails
- **Audit trail** — Immutable, chain-hashed JSONL logs with SHA-256 integrity verification
- **Compliance** — Maps features to SOC 2, HIPAA, SOX, and OSFI regulatory frameworks
- **MCP servers** — Expose governance, audit, and cost data to MCP-compatible clients
- **Circuit breakers** — Automatic fallback when a backend is unhealthy (closed → open → half-open)

## Routing Strategies

| Strategy | When to Use | How It Works |
|----------|-------------|--------------|
| `balanced` | Default. Best all-around. | Scores backends on quality × strength / relative cost |
| `quality` | Critical code, security-sensitive | Always picks highest-quality backend |
| `cost` | Bulk tasks, experiments | Picks cheapest available backend |

See [docs/routing.md](docs/routing.md) for details on backend profiles, scoring formulas, and circuit breakers.

## Performance

| Metric | Value |
|--------|-------|
| Cold start | 20ms (20x improvement from lazy imports) |
| Config loading | < 1ms (module-level cache) |
| Routing decision | 0.1ms |
| Total wrapper overhead | < 200ms |

The footer displays before async I/O writes (audit, cost tracking) complete — the user never waits for bookkeeping.

## Governance & Compliance

Define policies in `.mdxpolicy` to enforce review requirements per path:

```yaml
policies:
  - name: auth-critical
    paths: ["src/auth/**", "src/security/**"]
    requires:
      adversarial_review: true
      human_approval: true
    severity: critical
```

MDx Code maps its features to regulatory frameworks:

| Framework | Coverage |
|-----------|----------|
| SOC 2 | Audit trail, access logging, change tracking |
| HIPAA | Audit controls, integrity verification |
| SOX | Approval workflows, immutable records |
| OSFI B-13 | Model provenance, technology risk controls |

Run `mdx compliance` to see the full compliance matrix.

## Configuration

MDx Code supports three levels of configuration:

- **Global** — `~/.mdx/config.yaml` (routing strategy, budgets, display)
- **Project** — `.mdx.yaml` in repo root (overrides global for this project)
- **Governance** — `.mdxpolicy` in repo root (policy rules)

See [docs/configuration.md](docs/configuration.md) for all fields and example configs.

## MCP Integration

MDx Code ships three MCP servers for integration with AI coding tools:

- **Governance server** — Policy checking and compliance data
- **Audit server** — Audit trail access and verification
- **Cost server** — Spending data and budget status

See [docs/mcp-setup.md](docs/mcp-setup.md) for setup instructions.

## Requirements

- Python 3.11+
- At least one AI coding CLI:
  - [Claude Code](https://github.com/anthropics/claude-code)
  - [Codex CLI](https://github.com/openai/codex)
  - [Gemini CLI](https://github.com/google-gemini/gemini-cli)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code style, and PR process.

## Security

See [SECURITY.md](SECURITY.md) for vulnerability reporting and security policy.

## License

[MIT](LICENSE)
