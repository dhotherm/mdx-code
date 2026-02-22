# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 0.2.x   | Yes                |
| < 0.2   | No                 |

## Reporting a Vulnerability

If you discover a security vulnerability in MDx Code, please report it responsibly.

**Preferred:** [GitHub Security Advisories](https://github.com/dhotherm/mdx-code/security/advisories/new)

This allows us to discuss and fix the issue privately before public disclosure.

### What to Include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

### Response Timeline

- **72 hours** — Acknowledgment of your report
- **7 days** — Initial assessment and severity classification
- **30 days** — Target for fix release (critical issues prioritized)

## What Counts as a Security Issue

- Command injection through task strings or config values
- Path traversal in file operations
- Unauthorized access to audit trail or cost data
- Secrets leaked in logs, output, or audit entries
- Vulnerabilities in the install script

## What Does NOT Count

- Security issues in upstream AI CLIs (Claude Code, Codex CLI, Gemini CLI) — report those to their respective maintainers
- AI model outputs that contain insecure code suggestions — this is inherent to AI-assisted development and why MDx Code includes adversarial review
- Feature requests or general bugs — use [GitHub Issues](https://github.com/dhotherm/mdx-code/issues)

## Architecture Note

MDx Code spawns external CLI processes (`claude`, `codex`, `gemini`) as subprocesses. The security of those tools is governed by their respective maintainers. MDx Code's security scope covers the orchestration layer: routing, audit, cost tracking, policy enforcement, and the MCP servers.
