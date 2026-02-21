"""Immutable audit trail with chain hashing."""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from ..config import load_config


class AuditEntry(BaseModel):
    """A single audit trail entry."""

    entry_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    chain_hash: str = ""
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    session_id: str = ""
    task: str = ""
    backend: str = ""
    model: Optional[str] = None
    working_directory: str = ""
    duration_seconds: float = 0.0
    files_modified: list[str] = Field(default_factory=list)
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    cost_usd: Optional[float] = None
    exit_code: int = 0
    status: str = "success"


def compute_chain_hash(entry_dict: dict, previous_hash: str) -> str:
    """Compute SHA-256 chain hash for audit entry."""
    entry_copy = {k: v for k, v in entry_dict.items() if k != "chain_hash"}
    payload = previous_hash + json.dumps(entry_copy, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def get_last_hash(audit_dir: Path) -> str:
    """Get the chain hash of the most recent audit entry, or 'genesis'."""
    today_file = audit_dir / f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.jsonl"
    if not today_file.exists():
        # Check previous days' files
        jsonl_files = sorted(audit_dir.glob("*.jsonl"))
        if not jsonl_files:
            return "genesis"
        today_file = jsonl_files[-1]

    lines = today_file.read_text().strip().splitlines()
    if not lines:
        return "genesis"

    last_entry = json.loads(lines[-1])
    return last_entry.get("chain_hash", "genesis")


def write_audit_entry(entry: AuditEntry, audit_dir: Optional[Path] = None) -> Path:
    """
    Write an audit entry to the daily JSONL file.

    Returns the path to the audit file.
    """
    if audit_dir is None:
        config = load_config()
        audit_dir = Path(config.audit.directory).expanduser()

    audit_dir.mkdir(parents=True, exist_ok=True)

    # Compute chain hash
    previous_hash = get_last_hash(audit_dir)
    entry_dict = entry.model_dump()
    entry.chain_hash = compute_chain_hash(entry_dict, previous_hash)
    entry_dict["chain_hash"] = entry.chain_hash

    # Write to daily file
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filepath = audit_dir / f"{today}.jsonl"
    with open(filepath, "a") as f:
        f.write(json.dumps(entry_dict, default=str) + "\n")

    return filepath


def verify_audit_integrity(filepath: Path) -> tuple[bool, Optional[str]]:
    """Verify the chain hash integrity of an audit file."""
    previous_hash = "genesis"

    # If there are earlier files in the same directory, chain from the last one
    audit_dir = filepath.parent
    all_files = sorted(audit_dir.glob("*.jsonl"))
    for earlier_file in all_files:
        if earlier_file == filepath:
            break
        lines = earlier_file.read_text().strip().splitlines()
        if lines:
            last_entry = json.loads(lines[-1])
            previous_hash = last_entry.get("chain_hash", previous_hash)

    text = filepath.read_text().strip()
    if not text:
        return True, None

    for line_num, line in enumerate(text.splitlines(), 1):
        entry = json.loads(line)
        expected = compute_chain_hash(entry, previous_hash)
        if entry["chain_hash"] != expected:
            return False, f"Integrity violation at line {line_num}"
        previous_hash = entry["chain_hash"]

    return True, None


def read_recent_entries(audit_dir: Optional[Path] = None, count: int = 10) -> list[dict]:
    """Read the most recent audit entries across all files."""
    if audit_dir is None:
        config = load_config()
        audit_dir = Path(config.audit.directory).expanduser()

    if not audit_dir.exists():
        return []

    entries: list[dict] = []
    for filepath in sorted(audit_dir.glob("*.jsonl"), reverse=True):
        lines = filepath.read_text().strip().splitlines()
        for line in reversed(lines):
            entries.append(json.loads(line))
            if len(entries) >= count:
                return entries

    return entries
