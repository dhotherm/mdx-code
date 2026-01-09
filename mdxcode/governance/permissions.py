"""
Permissions

This is where governance happens.

Every tool use goes through permission checks:
- Is this action allowed automatically?
- Does it require human approval?
- Is it blocked entirely?

Different regulatory profiles have different rules.
Financial services is stricter than standard.
Healthcare has its own requirements.

The goal: protect against mistakes without being annoying.
Auto-approve the safe stuff. Ask about the risky stuff. Block the dangerous stuff.
"""

import re
from dataclasses import dataclass
from typing import List, Optional

from mdxcode.core.context_loader import MDXCodeContext


@dataclass
class PermissionResult:
    """Result of a permission check."""
    status: str  # "allowed", "requires_approval", "blocked"
    reason: Optional[str] = None


# Patterns that are always blocked, regardless of profile
ALWAYS_BLOCKED = [
    r"rm\s+-rf\s+/",            # rm -rf /
    r"rm\s+-rf\s+~",            # rm -rf ~
    r"rm\s+-rf\s+\*",           # rm -rf *
    r">\s*/dev/sd",             # writing to disk devices
    r"mkfs\.",                  # formatting filesystems
    r"dd\s+if=",                # disk operations
    r":(){:|:&};:",             # fork bomb
    r"chmod\s+-R\s+777",        # world writable everything
    r"curl.*\|\s*bash",         # curl pipe to bash
    r"wget.*\|\s*bash",         # wget pipe to bash
]

# Patterns that require approval in all profiles
REQUIRES_APPROVAL_ALL = [
    r"rm\s+",                   # any rm command
    r"sudo\s+",                 # any sudo command
    r"chmod\s+",                # changing permissions
    r"chown\s+",                # changing ownership
    r"mv\s+",                   # moving files
    r"git\s+push",              # pushing to remote
    r"git\s+commit",            # committing (in some profiles)
    r"npm\s+publish",           # publishing packages
    r"pip\s+install",           # installing packages
]

# Profile-specific rules
PROFILE_RULES = {
    "standard": {
        "auto_approve_tools": ["read_file", "glob", "grep", "list_directory"],
        "auto_approve_commands": [
            r"make\s+test",
            r"make\s+lint",
            r"npm\s+test",
            r"npm\s+run\s+lint",
            r"pytest",
            r"python\s+-m\s+pytest",
            r"cat\s+",
            r"head\s+",
            r"tail\s+",
            r"wc\s+",
            r"ls\s+",
            r"pwd",
            r"echo\s+",
        ],
        "blocked_patterns": [],
    },
    "financial_services": {
        "auto_approve_tools": ["read_file", "glob", "grep", "list_directory"],
        "auto_approve_commands": [
            r"make\s+test",
            r"make\s+lint",
            r"pytest",
            r"cat\s+",
            r"head\s+",
            r"tail\s+",
        ],
        "blocked_patterns": [
            r"DROP\s+TABLE",
            r"DELETE\s+FROM.*WHERE\s+1=1",
            r"TRUNCATE\s+",
            r"curl.*prod",
            r"ssh.*prod",
        ],
        "require_approval_extra": [
            r"write_file.*\.sql",      # SQL files
            r"write_file.*config",     # Config files
            r"write_file.*\.env",      # Environment files
            r"git\s+commit",           # All commits
        ],
    },
    "healthcare": {
        "auto_approve_tools": ["read_file", "glob", "grep", "list_directory"],
        "auto_approve_commands": [
            r"make\s+test",
            r"pytest",
        ],
        "blocked_patterns": [
            r"curl.*patient",
            r"SELECT.*FROM.*patient",
            r"SELECT.*FROM.*medical",
            r"SELECT.*ssn",
            r"SELECT.*dob",
        ],
        "require_approval_extra": [
            r"write_file",             # All writes require approval
            r"run_bash",               # All bash requires approval
        ],
    },
    "government": {
        "auto_approve_tools": ["read_file", "list_directory"],
        "auto_approve_commands": [
            r"make\s+test",
        ],
        "blocked_patterns": [
            r"curl\s+",                # No external calls
            r"wget\s+",                # No external calls
            r"ssh\s+",                 # No remote access
        ],
        "require_approval_extra": [
            r"write_file",
            r"run_bash",
            r"glob",                   # Even search requires approval
            r"grep",
        ],
    },
}


def check_permission(
    tool_name: str,
    tool_input: dict,
    profile: str,
    context: Optional[MDXCodeContext] = None,
) -> PermissionResult:
    """
    Check if a tool use is permitted.
    
    Returns one of:
    - allowed: Go ahead, no questions asked
    - requires_approval: Ask the human first
    - blocked: Nope, not happening
    """
    # Get profile rules
    rules = PROFILE_RULES.get(profile, PROFILE_RULES["standard"])
    
    # For bash commands, check the command content
    if tool_name == "run_bash":
        command = tool_input.get("command", "")
        return _check_bash_permission(command, rules, context)
    
    # For file operations, check the path
    if tool_name in ("write_file", "edit_file"):
        path = tool_input.get("path", "")
        return _check_file_permission(tool_name, path, rules, context)
    
    # For read-only tools, usually auto-approved
    if tool_name in rules.get("auto_approve_tools", []):
        return PermissionResult(status="allowed")
    
    # Check profile-specific extra approval requirements
    for pattern in rules.get("require_approval_extra", []):
        if re.search(pattern, tool_name, re.IGNORECASE):
            return PermissionResult(
                status="requires_approval",
                reason=f"Profile '{profile}' requires approval for this action"
            )
    
    # Default: require approval for unknown tools
    return PermissionResult(
        status="requires_approval",
        reason="Unknown tool - requesting approval"
    )


def _check_bash_permission(
    command: str,
    rules: dict,
    context: Optional[MDXCodeContext],
) -> PermissionResult:
    """Check permission for a bash command."""
    
    # Check always-blocked patterns
    for pattern in ALWAYS_BLOCKED:
        if re.search(pattern, command, re.IGNORECASE):
            return PermissionResult(
                status="blocked",
                reason=f"Command matches blocked pattern: {pattern}"
            )
    
    # Check profile-specific blocked patterns
    for pattern in rules.get("blocked_patterns", []):
        if re.search(pattern, command, re.IGNORECASE):
            return PermissionResult(
                status="blocked",
                reason=f"Command blocked by regulatory profile"
            )
    
    # Check if command is auto-approved
    for pattern in rules.get("auto_approve_commands", []):
        if re.search(pattern, command, re.IGNORECASE):
            return PermissionResult(status="allowed")
    
    # Check patterns that always require approval
    for pattern in REQUIRES_APPROVAL_ALL:
        if re.search(pattern, command, re.IGNORECASE):
            return PermissionResult(
                status="requires_approval",
                reason=f"Command requires approval: matches '{pattern}'"
            )
    
    # Check context guardrails
    if context and context.guardrails:
        # Simple check: if guardrails mention the command, require approval
        if any(word in context.guardrails.lower() for word in command.lower().split()):
            return PermissionResult(
                status="requires_approval",
                reason="Command mentioned in project guardrails"
            )
    
    # Default: require approval for bash commands
    return PermissionResult(
        status="requires_approval",
        reason="Bash commands require approval by default"
    )


def _check_file_permission(
    tool_name: str,
    path: str,
    rules: dict,
    context: Optional[MDXCodeContext],
) -> PermissionResult:
    """Check permission for file operations."""
    
    # Sensitive paths that always require approval
    sensitive_patterns = [
        r"\.env",
        r"secret",
        r"credential",
        r"password",
        r"\.ssh",
        r"\.aws",
        r"config\.ya?ml",
        r"config\.json",
    ]
    
    for pattern in sensitive_patterns:
        if re.search(pattern, path, re.IGNORECASE):
            return PermissionResult(
                status="requires_approval",
                reason=f"Writing to sensitive path: {path}"
            )
    
    # Check profile-specific rules
    for pattern in rules.get("blocked_patterns", []):
        if re.search(pattern, path, re.IGNORECASE):
            return PermissionResult(
                status="blocked",
                reason="Path blocked by regulatory profile"
            )
    
    # Check profile-specific approval requirements
    for pattern in rules.get("require_approval_extra", []):
        if re.search(pattern, f"{tool_name}.*{path}", re.IGNORECASE):
            return PermissionResult(
                status="requires_approval",
                reason=f"Profile requires approval for this operation"
            )
    
    # Auto-approve writes to test files
    if re.search(r"test.*\.py$", path) or re.search(r"\.test\.(js|ts)$", path):
        return PermissionResult(status="allowed")
    
    # Default: require approval for writes
    return PermissionResult(
        status="requires_approval",
        reason="File writes require approval"
    )


__all__ = [
    "PermissionResult",
    "check_permission",
    "PROFILE_RULES",
]
