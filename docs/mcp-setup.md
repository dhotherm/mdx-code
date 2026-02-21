# MDx Code MCP Servers — Setup Guide

MDx Code exposes three MCP (Model Context Protocol) servers so any MCP-compatible client can use governance, audit, and cost tracking without installing the full MDx Code CLI.

## Installation

```bash
# Install MDx Code with MCP support
pip install -e ".[mcp]"
```

This installs the `mcp` package and registers three server entry points:

| Server | Entry Point | Description |
|--------|-------------|-------------|
| Governance | `mdx-governance-server` | Policy checking and enforcement |
| Audit | `mdx-audit-server` | Immutable audit trail access |
| Cost | `mdx-cost-server` | Spending tracking and reporting |

## Quick Check

```bash
# Verify servers are available
mdx mcp status

# Generate config for your client
mdx mcp config --client claude-code
```

## Client Configuration

### Claude Code

Add to `~/.claude.json`:

```json
{
  "mcpServers": {
    "mdx-governance": {
      "command": "mdx-governance-server",
      "args": []
    },
    "mdx-audit": {
      "command": "mdx-audit-server",
      "args": []
    },
    "mdx-cost": {
      "command": "mdx-cost-server",
      "args": []
    }
  }
}
```

### Cursor

Add to `.cursor/mcp.json` in your project:

```json
{
  "mcpServers": {
    "mdx-governance": {
      "command": "mdx-governance-server",
      "args": []
    },
    "mdx-audit": {
      "command": "mdx-audit-server",
      "args": []
    },
    "mdx-cost": {
      "command": "mdx-cost-server",
      "args": []
    }
  }
}
```

### Codex CLI

Add to your Codex configuration:

```json
{
  "mcpServers": {
    "mdx-governance": {
      "command": "mdx-governance-server",
      "args": []
    },
    "mdx-audit": {
      "command": "mdx-audit-server",
      "args": []
    },
    "mdx-cost": {
      "command": "mdx-cost-server",
      "args": []
    }
  }
}
```

## Available Tools

### Governance Server (`mdx-governance-server`)

| Tool | Description |
|------|-------------|
| `check_policy` | Check files against `.mdxpolicy` rules |
| `list_policies` | List all active policies and defaults |
| `evaluate_commit` | Evaluate staged files for commit readiness |

### Audit Server (`mdx-audit-server`)

| Tool | Description |
|------|-------------|
| `log_action` | Log an AI-assisted action to the audit trail |
| `query_audit` | Search and filter audit entries |
| `verify_integrity` | Verify chain hash integrity of audit logs |
| `get_stats` | Get audit trail statistics |

### Cost Server (`mdx-cost-server`)

| Tool | Description |
|------|-------------|
| `log_cost` | Record a cost entry for an AI operation |
| `get_summary` | Get spending summary for a time period |

## How It Works

Each MCP server wraps existing MDx Code functions and exposes them over the MCP protocol (JSON-RPC over stdio). The servers:

- Use the same `.mdxpolicy` files, audit trail, and cost database as the CLI
- Return structured JSON responses (dicts auto-serialized by FastMCP)
- Handle errors gracefully (return `{"error": "message"}` instead of crashing)
- Run as separate processes, one per server

## Running Servers Manually

For debugging or testing:

```bash
# Run a server directly
python -m mcp_servers.governance.server
python -m mcp_servers.audit.server
python -m mcp_servers.cost.server
```

## Requirements

- Python 3.11+
- MDx Code installed with `[mcp]` extra
- A `.mdxpolicy` file in your project (for governance tools) — create one with `mdx policy init`
