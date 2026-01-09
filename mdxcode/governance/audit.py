"""
Audit Logging

Every action. Every decision. Every outcome. Logged.

In regulated environments, you need to prove what happened.
Not just what the code does, but what the AI did.

The audit log captures:
- Every session start/end
- Every tool use (approved, denied, blocked)
- Every completion
- Every error

It's the compliance team's best friend.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from mdxcode.core.session import Session


# Where audit logs live
AUDIT_DIR = Path.home() / ".mdxcode" / "audit"


class AuditLogger:
    """
    Logs everything for compliance and debugging.
    
    Each session gets its own log file.
    Format is JSONL (one JSON object per line) for easy parsing.
    """
    
    def __init__(self, session: Session):
        self.session = session
        self.log_file = self._get_log_file()
        self.entries: List[Dict] = []
    
    def _get_log_file(self) -> Path:
        """Get the log file path for this session."""
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        
        date_str = datetime.now().strftime("%Y-%m-%d")
        return AUDIT_DIR / f"{date_str}_{self.session.session_id}.jsonl"
    
    def _write_entry(self, entry: Dict):
        """Write an entry to the log file."""
        entry["timestamp"] = datetime.now().isoformat()
        entry["session_id"] = self.session.session_id
        
        self.entries.append(entry)
        
        # Append to file
        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")
    
    def log_session_start(self, task: str):
        """Log session start."""
        self._write_entry({
            "event": "session_start",
            "task": task,
            "model": self.session.model,
            "profile": self.session.profile,
            "working_directory": self.session.working_directory,
            "project": self.session.context.project_name if self.session.context else None,
            "domain": self.session.context.domain if self.session.context else None,
        })
    
    def log_session_end(self, status: str, error: Optional[str] = None):
        """Log session end."""
        self._write_entry({
            "event": "session_end",
            "status": status,
            "error": error,
            "summary": self.session.summary(),
        })
    
    def log_tool_use(
        self,
        tool_name: str,
        tool_input: Dict,
        result: str,
        approved_by: str,
    ):
        """Log a tool use."""
        self.session.record_tool_call()
        
        # Truncate large inputs/results for logging
        input_str = json.dumps(tool_input)
        if len(input_str) > 1000:
            input_str = input_str[:1000] + "...(truncated)"
        
        result_str = result
        if len(result_str) > 1000:
            result_str = result_str[:1000] + "...(truncated)"
        
        self._write_entry({
            "event": "tool_use",
            "tool": tool_name,
            "input": input_str,
            "result": result_str,
            "approved_by": approved_by,
        })
    
    def log_tool_blocked(self, tool_name: str, tool_input: Dict, reason: str):
        """Log a blocked tool use."""
        self._write_entry({
            "event": "tool_blocked",
            "tool": tool_name,
            "input": json.dumps(tool_input)[:500],
            "reason": reason,
        })
    
    def log_tool_denied(self, tool_name: str, tool_input: Dict, reason: str):
        """Log a user-denied tool use."""
        self._write_entry({
            "event": "tool_denied",
            "tool": tool_name,
            "input": json.dumps(tool_input)[:500],
            "reason": reason,
        })
    
    def log_completion(self, response: str):
        """Log a completion."""
        response_str = response
        if len(response_str) > 2000:
            response_str = response_str[:2000] + "...(truncated)"
        
        self._write_entry({
            "event": "completion",
            "response": response_str,
        })
    
    def log_warning(self, warning: str):
        """Log a warning."""
        self._write_entry({
            "event": "warning",
            "message": warning,
        })
    
    def log_error(self, error: str):
        """Log an error."""
        self._write_entry({
            "event": "error",
            "message": error,
        })
    
    def get_summary(self) -> Dict:
        """Get a summary of the session for reporting."""
        tool_uses = [e for e in self.entries if e.get("event") == "tool_use"]
        blocked = [e for e in self.entries if e.get("event") == "tool_blocked"]
        denied = [e for e in self.entries if e.get("event") == "tool_denied"]
        
        return {
            "session_id": self.session.session_id,
            "total_entries": len(self.entries),
            "tool_uses": len(tool_uses),
            "blocked_actions": len(blocked),
            "denied_actions": len(denied),
            "log_file": str(self.log_file),
        }


def get_recent_logs(days: int = 7) -> List[Path]:
    """Get log files from the last N days."""
    if not AUDIT_DIR.exists():
        return []
    
    logs = list(AUDIT_DIR.glob("*.jsonl"))
    
    # Filter by date
    cutoff = datetime.now().timestamp() - (days * 24 * 60 * 60)
    recent = [log for log in logs if log.stat().st_mtime > cutoff]
    
    return sorted(recent, reverse=True)


def parse_log_file(path: Path) -> List[Dict]:
    """Parse a log file into entries."""
    entries = []
    with open(path) as f:
        for line in f:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


__all__ = [
    "AuditLogger",
    "get_recent_logs",
    "parse_log_file",
    "AUDIT_DIR",
]
