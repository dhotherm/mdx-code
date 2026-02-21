"""
Session Management

Every MDx Code session has state:
- Which model we're using
- Which regulatory profile we're under
- What context we loaded from MDXCODE.md
- What we've done so far

This module manages that state cleanly.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from mdxcode.core.context_loader import MDXCodeContext


@dataclass
class Session:
    """
    A single MDx Code session.
    
    Sessions are ephemeral by default, but everything gets logged.
    The audit trail is the source of truth for what happened.
    """
    
    # Configuration
    model: str = "claude"
    profile: str = "standard"
    context: Optional[MDXCodeContext] = None
    verbose: bool = False
    dry_run: bool = False
    
    # Session metadata
    session_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    started_at: datetime = field(default_factory=datetime.now)
    working_directory: str = field(default_factory=lambda: str(__import__("pathlib").Path.cwd()))
    
    # Runtime state
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    tool_calls: int = 0
    
    def __post_init__(self):
        """Validate session configuration."""
        valid_models = ["claude", "gpt", "bedrock", "vertex"]
        valid_profiles = ["standard", "financial_services", "healthcare", "government"]
        
        if self.model not in valid_models:
            raise ValueError(f"Invalid model: {self.model}. Must be one of {valid_models}")
        
        if self.profile not in valid_profiles:
            raise ValueError(f"Invalid profile: {self.profile}. Must be one of {valid_profiles}")
    
    def record_usage(self, input_tokens: int, output_tokens: int, cost_usd: float):
        """Record token usage and cost."""
        self.total_tokens += input_tokens + output_tokens
        self.total_cost_usd += cost_usd
    
    def record_tool_call(self):
        """Record a tool call."""
        self.tool_calls += 1
    
    def summary(self) -> dict:
        """Get session summary for logging."""
        return {
            "session_id": self.session_id,
            "model": self.model,
            "profile": self.profile,
            "started_at": self.started_at.isoformat(),
            "working_directory": self.working_directory,
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "tool_calls": self.tool_calls,
            "project": self.context.project_name if self.context else None,
            "domain": self.context.domain if self.context else None,
        }
