# Architecture

## Design Philosophy

**Orchestration, not execution.** MDx Code never calls an AI model directly. It spawns real AI coding CLIs as subprocesses, streams their output, and wraps everything with the governance layer that enterprises need: routing, cost tracking, policy enforcement, and an immutable audit trail.

This is a deliberate constraint. AI coding CLIs already handle the hard problems — context management, tool use, code generation. MDx Code handles the problems they don't: which model should handle this task? How much are we spending? Does this change comply with policy? Can we prove what happened?

## System Architecture

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

## Data Flow: Task Execution

What happens when you run `mdx "fix the auth bug"`:

```
1. CLI parses input
   └── TaskGroup treats unrecognized commands as tasks

2. Task categorization (keyword-based, no LLM)
   └── "fix" + "bug" → category: debugging, confidence: 0.8

3. Strategy selection
   └── User flag (--strategy) → project config (.mdx.yaml) → global config → "balanced"

4. Route task
   └── Balanced strategy scores: quality × strength_bonus / relative_cost
   └── Check circuit breakers (skip open backends)
   └── Decision: claude, reason: "highest balanced score for debugging"

5. Budget check
   └── Estimate cost from backend profile
   └── Compare against daily_budget if set

6. Execute via backend
   └── Spawn: claude -p "fix the auth bug"
   └── Stream stdout line-by-line to terminal
   └── Capture full output + metadata (model, tokens, cost)

7. Error handling
   └── Classify: rate_limit / auth / timeout / network
   └── Rate limit → record failure → circuit breaker → auto-fallback
   └── Auth error → display fix instructions → stop

8. Post-execution
   └── Show footer (timing, cost, audit link)
   └── Record cost → SQLite (WAL mode)
   └── Write audit entry → JSONL (chain-hashed)
   └── Evaluate policies → recommend review if triggered
   └── Save last_task.json for replay/undo/review
```

## Data Flow: Adversarial Review

What happens when you run `mdx review src/auth/`:

```
1. Prepare review target
   └── Walk src/auth/, read supported file types
   └── Cap at 100k characters

2. Select review backends
   └── Use all available backends (minimum 2 for adversarial value)
   └── Or user-specified via --backend flag

3. Execute reviews in parallel
   └── Each backend receives the same review prompt
   └── Prompt requests structured JSON: {findings: [{file, line, severity, ...}]}
   └── Stream output, capture results

4. Normalize findings
   └── Extract JSON from markdown fences
   └── Canonicalize severities (critical/high/medium/low)
   └── Parse line numbers (int, string, range formats)

5. Build consensus
   └── Match findings across backends (same file + nearby lines + similar category)
   └── Confirmed: multiple backends agree → high confidence
   └── Unique: single backend only → lower confidence
   └── Conflicts: severity disagreement (≥2 ranks apart)

6. Display results
   └── Confirmed findings (cross-validated)
   └── Unique findings (single-source)
   └── Summary: "Claude found 4, Codex found 3, cross-validated: 2, unique: 3"
```

## Key Design Decisions

### Why subprocess spawning (not SDK integration)

Each AI coding CLI handles its own context management, tool use, file editing, and conversation state. Integrating via SDK would mean reimplementing all of that. Subprocess spawning gives us the full power of each CLI with zero maintenance burden as they evolve. The tradeoff is less structured output — we parse what we can from stdout/stderr and JSON metadata.

### Why JSONL for audit (not SQLite)

The audit trail is append-only and integrity-critical. JSONL gives us:
- Append-only writes (no UPDATE/DELETE risk)
- Line-by-line verification of chain hashes
- Easy export, grep, and external tooling
- Daily file rotation without migration

SQLite is used for cost tracking where we need aggregation queries (sum by backend, filter by date range). Different access patterns, different storage choices.

### Why chain hashing

Each audit entry includes a SHA-256 hash of its contents combined with the previous entry's hash. This creates a tamper-evident chain — modifying or deleting any entry breaks the chain for all subsequent entries. `mdx audit --verify` checks the entire chain. This matters for compliance frameworks (SOC 2, OSFI) that require demonstrable integrity of audit records.

### Why circuit breakers

AI backend APIs fail. Rate limits, auth expiry, service outages. Without circuit breakers, every task would wait for a timeout before falling back. The circuit breaker pattern (closed → open → half-open) provides:
- Fast failure after repeated errors (3 failures → circuit opens)
- Automatic recovery testing (half-open after 5 minutes)
- Cross-process state (persisted to disk)
- Transparent fallback to the next best backend

### Why SQLite for cost tracking

Cost queries need aggregation: "how much did I spend this week, broken down by backend?" JSONL would require reading and summing every line. SQLite with WAL mode gives us indexed queries with concurrent read/write support. The cost database is not integrity-critical the way audit is — it's an analytics store.

## Extension Points

### Adding a new backend

1. Create `mdxcode/backends/your_backend.py`, extend `Backend`
2. Implement: `name`, `cli_command`, `is_available()`, `get_info()`, `execute()`, `execute_and_capture()`, `health_check()`
3. Register in `discovery.py` (`BACKEND_CLASSES` list)
4. Add a capability profile in `router/profiles.py`

### Adding a new routing strategy

1. Add strategy function in `router/strategies.py`
2. Takes: `TaskCategory`, available backends, profiles
3. Returns: `RoutingDecision` with backend name, reason, scores
4. Register in `route_task()` dispatcher

### Adding a new policy type

1. Extend `PolicyRequirements` in `governance/policy_engine.py`
2. Update `evaluate_policies()` to check the new requirement
3. Add handling in the CLI execution flow

### Adding a new compliance framework

1. Add framework mapping in `governance/compliance.py`
2. Map MDx Code features to framework requirements
3. The compliance matrix command picks it up automatically
