# MDx Code Architecture

*How it works under the hood.*

---

## The Core Insight

Claude Code's architecture is simple. MDx Code follows the same pattern:

```
┌─────────────────────────────────────────────────────────────────────┐
│                         USER                                         │
│                    "Fix the bug in auth.py"                          │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      CONTEXT LOADER                                  │
│  • Reads MDXCODE.md from project root                                │
│  • Parses project info, conventions, compliance rules                │
│  • Injects context into system prompt                                │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      AGENT LOOP                                      │
│                                                                      │
│  while task_not_complete:                                            │
│      response = model.complete(messages, tools)                      │
│                                                                      │
│      if response.wants_tool:                                         │
│          permission = governance.check(tool, input)                  │
│          if permission.allowed:                                      │
│              result = tools.execute(tool, input)                     │
│              audit.log(tool, input, result)                          │
│          messages.append(result)                                     │
│                                                                      │
│      if response.done:                                               │
│          break                                                       │
│                                                                      │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      RESULT                                          │
│  • Task completed (or max iterations reached)                        │
│  • Full audit trail saved                                            │
│  • Session summary available                                         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Components

### 1. CLI (`mdxcode.py`)

Entry point. Handles:
- Command parsing (typer)
- Banner display
- Initialization
- Routing to appropriate handler

### 2. Core

**agent_loop.py**
- The main while loop
- Sends messages to LLM
- Processes tool use requests
- Checks permissions before execution
- Handles user approval flows

**context_loader.py**
- Reads MDXCODE.md files
- Parses markdown into structured data
- Extracts project info, conventions, guardrails

**session.py**
- Manages session state
- Tracks token usage and cost
- Generates session summaries

### 3. Tools

**registry.py**
- Tool registration and discovery
- Execution routing
- Built-in tools:
  - `read_file`: Read file contents
  - `write_file`: Create/overwrite files
  - `edit_file`: Surgical string replacement
  - `run_bash`: Execute shell commands
  - `glob`: Find files by pattern
  - `grep`: Search file contents
  - `list_directory`: List directory contents

### 4. Models

**router.py**
- Unified interface to multiple LLMs
- Currently supports: Claude
- Planned: OpenAI, AWS Bedrock, Google Vertex

**auth.py**
- Credential management
- Caches credentials in ~/.mdxcode/
- Supports env vars and interactive auth

### 5. Governance

**permissions.py**
- Permission checking for every tool use
- Three outcomes: allowed, requires_approval, blocked
- Regulatory profile-specific rules
- Pattern matching for dangerous commands

**audit.py**
- JSONL logging for every action
- Session start/end
- Tool use (approved, denied, blocked)
- Completions and errors

**security_agent.py**
- Vulnerability scanning
- Pattern-based detection
- Auto-fix capability
- Learning mode for new patterns

---

## Data Flow

### 1. Initialization

```
User runs: mdxcode "Fix the bug"
    │
    ▼
Load MDXCODE.md from current directory
    │
    ▼
Parse into MDXCodeContext
    │
    ▼
Create Session with:
  - model (default: claude)
  - profile (default: standard, or from MDXCODE.md)
  - context
    │
    ▼
Initialize AuditLogger
    │
    ▼
Initialize ModelRouter
    │
    ▼
Create AgentLoop
```

### 2. Agent Loop Iteration

```
Send messages to LLM with:
  - System prompt (includes MDXCODE.md context)
  - Conversation history
  - Tool definitions
    │
    ▼
LLM responds with:
  - Text content, OR
  - Tool use request
    │
    ├─── If text only ───▶ Display response, end loop
    │
    └─── If tool use ───▶ Process tool request
                              │
                              ▼
                         Check permissions
                              │
                         ┌────┴────┐
                         │         │
                    Allowed    Requires     Blocked
                         │     Approval        │
                         │         │           │
                         │    Ask user         │
                         │    ┌───┴───┐        │
                         │    │       │        │
                         │  Approved Denied    │
                         │    │       │        │
                         ▼    ▼       │        │
                    Execute tool      │        │
                         │            │        │
                         ▼            ▼        ▼
                    Log result   Log denied  Log blocked
                         │            │        │
                         └────────────┴────────┘
                                   │
                                   ▼
                         Add result to messages
                                   │
                                   ▼
                         Continue loop
```

### 3. Permission Check

```
check_permission(tool_name, tool_input, profile, context)
    │
    ▼
Check ALWAYS_BLOCKED patterns
    │ (matches) → Return BLOCKED
    │
    ▼
Check profile-specific blocked patterns
    │ (matches) → Return BLOCKED
    │
    ▼
Check auto_approve patterns
    │ (matches) → Return ALLOWED
    │
    ▼
Check requires_approval patterns
    │ (matches) → Return REQUIRES_APPROVAL
    │
    ▼
Default: REQUIRES_APPROVAL
```

---

## Regulatory Profiles

Profiles control what's allowed without asking:

| Profile | Auto-Approve | Requires Approval | Blocked |
|---------|--------------|-------------------|---------|
| `standard` | read, glob, grep, make test | write, bash | rm -rf, sudo |
| `financial_services` | read, glob, grep | most writes, git commit | DROP TABLE, prod access |
| `healthcare` | read only | all writes, all bash | PHI queries |
| `government` | read, list | everything else | external calls |

Profiles are defined in `governance/permissions.py`.

---

## Extension Points

### Adding a New Tool

1. Define tool in `tools/registry.py`:

```python
self.register(Tool(
    name="my_tool",
    description="What it does",
    input_schema={
        "type": "object",
        "properties": {
            "param": {"type": "string", "description": "..."}
        },
        "required": ["param"]
    },
    execute_fn=_my_tool_function,
))
```

2. Implement the function:

```python
def _my_tool_function(param: str) -> str:
    # Do the thing
    return "result"
```

### Adding a New Model Provider

1. Add initialization in `models/router.py`:

```python
def _init_newmodel(self):
    # Initialize client
    self._clients["newmodel"] = NewModelClient()
```

2. Add completion method:

```python
async def _complete_newmodel(self, messages, system, tools, max_tokens):
    # Call the API, return response in standard format
```

### Adding a New Regulatory Profile

1. Add to `PROFILE_RULES` in `governance/permissions.py`:

```python
"new_profile": {
    "auto_approve_tools": [...],
    "auto_approve_commands": [...],
    "blocked_patterns": [...],
    "require_approval_extra": [...],
},
```

### Adding Security Patterns

1. Add to `BUILTIN_VULNERABILITY_PATTERNS` in `governance/security_agent.py`

OR

2. Use `mdxcode security learn` to add patterns interactively

---

## File Locations

| File | Purpose |
|------|---------|
| `~/.mdxcode/credentials.json` | Cached API credentials |
| `~/.mdxcode/audit/*.jsonl` | Audit logs |
| `./MDXCODE.md` | Project context |
| `knowledge/learnings/discovered.jsonl` | Learned security patterns |

---

## Security Considerations

1. **Credentials** are stored with 600 permissions (owner read/write only)
2. **Audit logs** capture everything for compliance review
3. **Permission checks** happen before every tool execution
4. **Blocked patterns** prevent obviously dangerous operations
5. **Profile-specific rules** enforce industry compliance

---

## Performance Notes

- LLM calls are the bottleneck (network latency)
- Tool execution is synchronous but fast
- Audit logging is append-only (minimal overhead)
- Context loading happens once at startup

---

## Future Considerations

1. **Streaming responses** for better UX
2. **Parallel tool execution** where safe
3. **Session persistence** for long-running tasks
4. **Integration with MDx** for advisory → engineering handoff
5. **VS Code extension** for IDE integration
