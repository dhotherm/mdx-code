# Changelog

All notable changes to MDx Code are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-02-21

Complete rewrite. MDx Code is now a multi-backend AI orchestration layer.

### Added
- Multi-backend support: Claude Code, Codex CLI, Gemini CLI, OpenCode
- Smart routing with 3 strategies: balanced, quality, cost
- Adversarial multi-model code review with cross-validation
- Enterprise governance: policy engine, compliance matrix (SOC 2, HIPAA, SOX, OSFI)
- Chain-hashed immutable audit trail (SHA-256, JSONL)
- Cost tracking with SQLite (WAL mode) and budget guardrails
- Circuit breaker pattern for backend resilience (closed/open/half-open)
- 3 MCP servers: audit, cost, governance
- Task replay, undo, and history commands
- Daily/weekly summary with category breakdown
- One-command install script (curl | bash)
- First-run setup wizard with backend auto-detection
- Contextual onboarding tips (tasks 1-3)
- Personalized banner (tasks 5+)
- Interactive backend picker (--pick flag)
- Context-aware routing display (git branch, language, file count)
- Shell tab-completion (bash/zsh/fish)
- Git pre-commit hook for policy enforcement
- Graceful degradation (NO_COLOR, --no-color, --no-markdown, pipe detection)
- Project-level configuration (.mdx.yaml)
- 30 smoke tests + self-healing test harness
- Performance profiling harness

### Performance
- Cold start: 20ms (20x improvement from lazy imports)
- Config loading: < 1ms (30x improvement from module-level cache)
- Routing decision: 0.1ms
- Git operations: parallel via asyncio.gather (4x improvement)
- Footer displays before async I/O writes
- SQLite WAL mode for concurrent reads/writes
- O(1) audit chain-hash verification via seek-from-end
- Shared Rich Console instance across all output modules

### Changed
- Complete architecture rewrite from v1 (single-backend wrapper to multi-backend orchestration)
- CLI framework: custom argparse to Typer + Click
- Entry point: mdxcode to mdx

## [0.1.0] - 2026-01-10

Initial release. Single-backend wrapper for Claude Code.

### Added
- Basic Claude Code integration
- Security scanning command
- Code explanation command
- PyPI package
