# Routing

MDx Code routes tasks to the best available backend using configurable strategies. Routing is deterministic, fast (0.1ms), and requires no LLM calls.

## How Routing Works

When you run `mdx "fix the auth bug"`, three things happen before any backend is called:

1. **Task categorization** — Keywords are matched to determine the task type (debugging, code_generation, security, etc.)
2. **Strategy selection** — CLI flag → project config → global config → default (`balanced`)
3. **Backend scoring** — Each available backend is scored based on the strategy, and the highest-scoring backend is selected

## Task Categories

Tasks are categorized by keyword matching with confidence scoring:

| Category | Example Keywords |
|----------|-----------------|
| `test_writing` | test, coverage, assert, pytest, unittest |
| `code_review` | review, check, audit, lint, examine |
| `security` | security, vulnerability, xss, injection |
| `debugging` | fix, bug, crash, exception, traceback |
| `refactoring` | refactor, optimize, simplify, decouple |
| `documentation` | document, readme, comments, docstring |
| `code_generation` | create, build, implement, generate, scaffold |
| `general` | Fallback when no keywords match |

Categorization uses word boundaries and confidence thresholds (0.3 minimum) to avoid false positives.

## Backend Profiles

Each backend has a capability profile that informs routing:

| Backend | Strengths | Quality Score | Input Cost (per 1K tokens) | Output Cost (per 1K tokens) |
|---------|-----------|---------------|---------------------------|----------------------------|
| Claude | code_review, security, refactoring, documentation | 0.95 | $0.003 | $0.015 |
| Codex | code_generation, test_writing, debugging | 0.90 | $0.002 | $0.008 |
| Gemini | code_generation, documentation, general | 0.88 | $0.001 | $0.004 |

When a task category matches a backend's strength, the backend receives a 1.5x scoring bonus.

## Strategies

### Balanced (Default)

Best all-around choice. Optimizes for value — quality per dollar spent.

**Formula:**
```
score = (quality_score × strength_multiplier) / relative_cost
```

- `relative_cost` is normalized so the cheapest backend = 1.0
- `strength_multiplier` = 1.5 if the task category matches a backend strength, 1.0 otherwise

**When to use:** Most tasks. This is the default for a reason.

**Example:** For a debugging task, Codex (strength match, moderate cost) often scores higher than Claude (no strength match, higher cost) despite Claude's higher quality score.

### Quality First

Always picks the highest-quality backend, regardless of cost.

**Formula:**
```
score = quality_score + 1.0 (if strength match)
```

**When to use:** Critical code, security-sensitive changes, production deployments. When getting it right matters more than cost.

**Example:** For a security review, Claude (quality 0.95 + 1.0 strength bonus = 1.95) always wins.

### Cost Optimized

Picks the cheapest available backend that can handle the task.

**Formula:**
```
score = 1.0 / average_cost × strength_multiplier
```

**When to use:** Bulk operations, experiments, documentation generation, tasks where "good enough" is fine.

**Example:** For documentation tasks, Gemini (cheapest + strength match) is selected.

## Overriding Routing

### Force a specific backend

```bash
mdx "task" --backend claude
mdx "task" --backend codex
```

### Interactive picker

```bash
mdx "task" --pick
```

Shows all available backends with their profiles and lets you choose.

### Force a strategy

```bash
mdx "task" --strategy quality_first
mdx "task" --strategy cost_optimized
```

### Project-level default

```yaml
# .mdx.yaml
preferred_backend: claude    # Always use Claude for this project
strategy: quality_first      # Always use quality strategy
```

## Circuit Breakers

Routing automatically skips backends with open circuit breakers.

| State | Meaning | Behavior |
|-------|---------|----------|
| **Closed** | Healthy | Normal routing |
| **Open** | 3+ recent failures | Skipped by router, auto-retry after 5 minutes |
| **Half-open** | Recovery period elapsed | Allows one test request |

When a backend fails (rate limit, timeout, network error), the circuit breaker records the failure. After 3 failures, the circuit opens and the router automatically falls back to the next best backend.

```bash
# View circuit breaker status
mdx status
```

Circuit breaker state is persisted to `~/.mdx/circuit_breaker.json` and shared across terminal sessions.

## Cost Tracking

Every task execution records cost data to SQLite (`~/.mdx/costs.db`):

- Actual cost (from backend metadata when available)
- Estimated cost (from token count × profile rates when metadata unavailable)
- Alternative costs (what other backends would have charged)
- Routing strategy used

```bash
# Today's spending
mdx cost

# Weekly breakdown
mdx cost --week

# Monthly breakdown
mdx cost --month
```

The cost dashboard shows:
- Total spend by backend
- Savings from routing (actual cost vs most expensive alternative)
- Top tasks by cost
- Budget utilization (if daily_budget is set)

## Budget Guardrails

Set spending limits to prevent runaway costs:

```yaml
# Global: ~/.mdx/config.yaml
max_cost_per_task: 1.00    # Reject tasks estimated to cost more than $1
daily_budget: 20.00        # Warn when daily spend exceeds $20

# Project: .mdx.yaml
max_cost_per_task: 0.50    # Tighter limit for this project
daily_budget: 10.00
```

When a budget limit is hit, MDx Code warns you before proceeding.
