"""
MDx Code Governance

The controls that make this safe for regulated environments:
- Permissions: What's allowed, what needs approval, what's blocked
- Audit: Every action logged for compliance
- Security Agent: AI-powered vulnerability scanning

This is what separates MDx Code from "just another AI tool."
It's built for environments where trust and compliance matter.
"""

from mdxcode.governance.permissions import PermissionResult, check_permission, PROFILE_RULES
from mdxcode.governance.audit import AuditLogger, get_recent_logs, parse_log_file
from mdxcode.governance.security_agent import SecurityAgent, BUILTIN_VULNERABILITY_PATTERNS

__all__ = [
    "PermissionResult",
    "check_permission",
    "PROFILE_RULES",
    "AuditLogger",
    "get_recent_logs",
    "parse_log_file",
    "SecurityAgent",
    "BUILTIN_VULNERABILITY_PATTERNS",
]
