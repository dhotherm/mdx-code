# MDx Code

**AI-Native Engineering Companion**

Built for builders. Designed for regulated environments.

---

## The Story

I've been thinking about AI-powered development tools for over a year. Then I read an article that broke down Claude Code from first principles and realized something: the core architecture is embarrassingly simple.

```python
while task_not_complete:
    response = ask_llm(conversation)
    if response.wants_tool:
        result = execute_tool(response.tool)
        conversation.append(result)
    if response.done:
        break
```

That's it. AI thinks → acts → observes → repeats.

Everything else is just tooling and governance wrapped around this loop.

So I built my own. Not because Claude Code isn't good... it's excellent. But because I needed something that:

- **Works in regulated environments** → Financial services, healthcare, government
- **Owns the orchestration layer** → Swap models without rewriting everything
- **Respects governance rules** → Audit trails, permission controls, compliance profiles
- **Learns over time** → The security agent gets smarter with use

MDx Code is that tool.

---

## Quick Start

**Option 1: Install directly from GitHub (recommended)**
```bash
pip install git+https://github.com/dhotherm/mdx-code.git
```

**Option 2: Clone and install locally**
```bash
git clone https://github.com/dhotherm/mdx-code.git
cd mdx-code
pip install -e .
```

**Then authenticate and run:**
```bash
# Authenticate with Claude
mdxcode auth claude

# Initialize in your project
cd your-project
mdxcode init

# Run it
mdxcode main "Fix the bug in auth.py"
```

---

## What It Does

**Give it a task. Watch it work.**

```bash
mdxcode "Add input validation to the user registration endpoint"
```

MDx Code will:
1. Read your MDXCODE.md for project context
2. Find the relevant files
3. Understand the existing patterns
4. Make changes incrementally
5. Run tests to verify
6. Log everything for audit

**Scan for vulnerabilities:**

```bash
mdxcode security scan
```

**Auto-fix issues:**

```bash
mdxcode security fix --auto-fix
```

---

## MDXCODE.md

Every project gets a context file. This is how MDx Code understands your project before touching anything.

```markdown
# MDXCODE.md

## Project
- **Name:** Claims Processing API
- **Domain:** Health
- **Team:** Health Platform

## Conventions
- All endpoints require JWT auth
- Use Pydantic for request/response models
- Event sourcing for state changes

## Compliance
- PHI fields use SL-encrypt utility
- Never log PHI in plain text

## Guardrails
- ❌ Never commit directly to main
- ❌ Never modify production configs
- ⚠️ Schema changes require approval
```

Different domains, different rules. The context file captures all of that.

---

## Regulatory Profiles

MDx Code ships with profiles for regulated industries:

| Profile | Description |
|---------|-------------|
| `standard` | Default. Sensible permissions for most projects. |
| `financial_services` | Stricter controls for OSFI/SOX compliance. |
| `healthcare` | HIPAA-aware. Extra protection for PHI. |
| `government` | Maximum restrictions. Minimal auto-approval. |

```bash
mdxcode "Update the API" --profile financial_services
```

---

## Multi-Model Support

Own the orchestration. Swap the models.

```bash
mdxcode "Fix the bug" --model claude    # Default
mdxcode "Fix the bug" --model gpt       # OpenAI
mdxcode "Fix the bug" --model bedrock   # AWS Bedrock
```

Today it's Claude. Tomorrow it could be anything. Your choice.

---

## Security Agent

Not just a linter. An AI that understands context.

```bash
# Scan for vulnerabilities
mdxcode security scan

# Scan specific path
mdxcode security scan --path src/

# Auto-fix what can be fixed
mdxcode security fix --auto-fix

# Teach it new patterns
mdxcode security learn
```

The knowledge base grows as you use it. Every fix teaches it something new.

---

## Audit Trail

Every action. Every decision. Logged.

```bash
~/.mdxcode/audit/2026-01-09_abc123.jsonl
```

```json
{
  "timestamp": "2026-01-09T14:32:15Z",
  "event": "tool_use",
  "tool": "write_file",
  "input": {"path": "src/api.py", "content": "..."},
  "approved_by": "user",
  "session_id": "abc123"
}
```

Essential for compliance. Essential for trust.

---

## Project Structure

```
mdx-code/
├── mdxcode.py          # CLI entry point
├── core/
│   ├── agent_loop.py   # The heart of it
│   ├── context_loader.py
│   └── session.py
├── tools/
│   └── registry.py     # read, write, edit, bash, grep, glob
├── models/
│   ├── router.py       # Multi-model support
│   └── auth.py         # Credential management
├── governance/
│   ├── permissions.py  # What's allowed
│   ├── audit.py        # Logging everything
│   └── security_agent.py
├── knowledge/
│   └── vulnerabilities/
└── examples/
    └── demo_project/
```

---

## Philosophy

**Own the orchestration layer.**

Models will come and go. Vendors will compete on capability and cost. But the orchestration... the context engineering, the governance, the institutional knowledge... that's yours.

**Built for regulated environments.**

This isn't a toy. It's designed for environments where compliance matters, where audit trails are required, where "move fast and break things" gets you fired.

**Learn over time.**

The security agent grows smarter. The patterns library expands. Every project teaches it something new.

---

## Contributing

Found a bug? Want to add a feature? PRs welcome.

The code is intentionally readable. If you can't understand it in an afternoon, I've failed.

---

## License

MIT. Use it. Modify it. Build on it.

---

## Author

Built by MD.

Not because I had to. Because I couldn't stop thinking about it.

---

*"The future of software development is agents that can actually do things. Now we know how they work."*
