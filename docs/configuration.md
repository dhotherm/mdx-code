# Configuration

MDx Code uses three levels of configuration, from broadest to most specific.

## Global Config: `~/.mdx/config.yaml`

Created automatically on first run. Controls MDx Code behavior across all projects.

```yaml
version: "2.0"
default_backend: auto          # auto | claude | codex | gemini
routing_strategy: balanced     # balanced | cost_optimized | quality_first
max_cost_per_task: null         # Maximum USD per task (null = unlimited)
daily_budget: null              # Daily spending limit in USD (null = unlimited)
first_run_complete: true
task_count: 0

audit:
  enabled: true
  directory: ~/.mdx/audit
  chain_hashing: true

display:
  show_footer: true
  show_routing_reason: true
  verbose: false
  sound: true
```

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `default_backend` | string | `auto` | Backend selection. `auto` uses smart routing. |
| `routing_strategy` | string | `balanced` | Routing strategy: `balanced`, `cost_optimized`, `quality_first` |
| `max_cost_per_task` | float \| null | null | Per-task spending cap in USD |
| `daily_budget` | float \| null | null | Daily spending limit in USD |
| `audit.enabled` | bool | true | Enable audit trail recording |
| `audit.chain_hashing` | bool | true | Enable SHA-256 chain hashing for tamper evidence |
| `display.show_footer` | bool | true | Show post-task footer with cost and audit info |
| `display.show_routing_reason` | bool | true | Show why a backend was selected |
| `display.verbose` | bool | false | Verbose output mode |

## Project Config: `.mdx.yaml`

Place in your project root (next to `.git`). Overrides global config for this project.

```yaml
preferred_backend: claude
strategy: quality_first
max_cost_per_task: 0.50
daily_budget: 10.00
```

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `preferred_backend` | string \| null | null | Force a specific backend for this project |
| `strategy` | string \| null | null | Override routing strategy |
| `max_cost_per_task` | float \| null | null | Per-task cap (overrides global) |
| `daily_budget` | float \| null | null | Daily budget (overrides global) |

MDx Code walks up from the current directory to find `.mdx.yaml`, stopping at `.git` boundaries.

## Governance Policies: `.mdxpolicy`

Place in your project root. Defines governance rules for code changes.

```yaml
version: "1.0"

defaults:
  min_reviewers: 1

policies:
  - name: auth-critical
    description: Authentication code requires adversarial review
    paths:
      - "src/auth/**"
      - "src/security/**"
    requires:
      adversarial_review: true
      min_reviewers: 2
      human_approval: true
    severity: critical

  - name: api-review
    description: API changes need review
    paths:
      - "src/api/**"
      - "routes/**"
    requires:
      adversarial_review: true
    severity: high

  - name: tests-relaxed
    description: Test files have relaxed requirements
    paths:
      - "tests/**"
    requires:
      adversarial_review: false
    severity: low
```

### Policy Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Policy identifier |
| `description` | string | Human-readable description |
| `paths` | list[string] | Glob patterns for matching files |
| `requires.adversarial_review` | bool | Require multi-model review |
| `requires.min_reviewers` | int | Minimum number of reviewing backends |
| `requires.human_approval` | bool | Require human sign-off |
| `severity` | string | `critical`, `high`, `medium`, `low` |

Policies use strictest-wins evaluation: if any matching policy requires review, the result requires review.

### Commands

```bash
# Create a starter .mdxpolicy
mdx policy init

# View active policies
mdx policy

# Check specific files against policies
mdx policy check src/auth/login.py src/api/users.py
```

## Example Configurations

### Solo Developer

```yaml
# ~/.mdx/config.yaml
default_backend: auto
routing_strategy: balanced
daily_budget: 5.00
display:
  show_footer: true
  verbose: false
```

No `.mdxpolicy` needed — governance is optional for solo work.

### Team

```yaml
# .mdx.yaml (in repo)
strategy: balanced
daily_budget: 50.00
max_cost_per_task: 2.00
```

```yaml
# .mdxpolicy (in repo)
version: "1.0"
policies:
  - name: production-code
    paths: ["src/**"]
    requires:
      adversarial_review: true
    severity: high
```

### Enterprise

```yaml
# .mdx.yaml
strategy: quality_first
max_cost_per_task: 5.00
daily_budget: 200.00
```

```yaml
# .mdxpolicy
version: "1.0"
defaults:
  min_reviewers: 2
policies:
  - name: all-code
    paths: ["**/*.py", "**/*.js", "**/*.ts"]
    requires:
      adversarial_review: true
      human_approval: true
      min_reviewers: 2
    severity: critical
```

```bash
# Verify compliance mapping
mdx compliance

# Install pre-commit hook for policy enforcement
mdx hook install
```

## Configuration Precedence

When the same setting exists at multiple levels:

1. CLI flags (`--backend`, `--strategy`) — highest priority
2. Project config (`.mdx.yaml`)
3. Global config (`~/.mdx/config.yaml`)
4. Built-in defaults — lowest priority
