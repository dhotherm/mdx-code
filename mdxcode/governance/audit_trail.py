"""Immutable audit trail with chain hashing."""

import csv
import hashlib
import io
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
    backend_selection_reason: str = ""
    backends_available: list[str] = Field(default_factory=list)
    routing_strategy: Optional[str] = None
    routing_reason: Optional[str] = None
    task_category: Optional[str] = None
    cost_estimated: bool = False
    alternative_costs: dict[str, float] = Field(default_factory=dict)
    policy_evaluation: Optional[dict] = None


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


def _read_all_entries(audit_dir: Path) -> list[dict]:
    """Read all audit entries from all JSONL files in order."""
    entries: list[dict] = []
    if not audit_dir.exists():
        return entries
    for filepath in sorted(audit_dir.glob("*.jsonl")):
        text = filepath.read_text().strip()
        if not text:
            continue
        for line in text.splitlines():
            entries.append(json.loads(line))
    return entries


def read_filtered_entries(
    audit_dir: Optional[Path] = None,
    since: Optional[str] = None,
    entry_type: Optional[str] = None,
    backend: Optional[str] = None,
    path: Optional[str] = None,
) -> list[dict]:
    """
    Read audit entries with optional filters.

    Args:
        audit_dir: Directory containing JSONL audit files.
        since: ISO date string (YYYY-MM-DD) — only entries on or after this date.
        entry_type: Filter by task prefix (e.g., "adversarial_review").
        backend: Filter by backend name.
        path: Filter by working_directory containing this substring.
    """
    if audit_dir is None:
        config = load_config()
        audit_dir = Path(config.audit.directory).expanduser()

    entries = _read_all_entries(audit_dir)
    filtered: list[dict] = []

    for entry in entries:
        if since:
            ts = entry.get("timestamp", "")[:10]
            if ts < since:
                continue
        if entry_type:
            task = entry.get("task", "")
            if not task.startswith(entry_type):
                continue
        if backend:
            if entry.get("backend", "") != backend:
                continue
        if path:
            wd = entry.get("working_directory", "")
            if path not in wd:
                continue
        filtered.append(entry)

    return filtered


def export_entries_csv(entries: list[dict]) -> str:
    """
    Export audit entries as CSV string.

    Columns: timestamp, type, task, backend, model, files_modified,
    policy_name, policy_compliant, review_conducted, findings_count, cost_usd
    """
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "timestamp", "type", "task", "backend", "model", "files_modified",
        "policy_name", "policy_compliant", "review_conducted", "findings_count",
        "cost_usd",
    ])

    for entry in entries:
        task = entry.get("task", "")
        if task.startswith("adversarial_review"):
            entry_type = "review"
        else:
            entry_type = "task"

        policy_eval = entry.get("policy_evaluation") or {}
        policy_names = ";".join(policy_eval.get("matching_policies", []))
        policy_compliant = "yes" if not policy_eval.get("requires_review") else "no"
        if not policy_eval:
            policy_compliant = ""

        files = ";".join(entry.get("files_modified", []))
        review_conducted = "yes" if entry_type == "review" else "no"
        findings_count = policy_eval.get("findings_count", "")

        writer.writerow([
            entry.get("timestamp", ""),
            entry_type,
            task,
            entry.get("backend", ""),
            entry.get("model", ""),
            files,
            policy_names,
            policy_compliant,
            review_conducted,
            findings_count,
            entry.get("cost_usd", ""),
        ])

    return output.getvalue()


def get_average_duration(
    audit_dir: Optional[Path] = None,
    backend: Optional[str] = None,
    task_category: Optional[str] = None,
    min_entries: int = 5,
) -> Optional[float]:
    """Get average duration for similar tasks. Returns None if not enough data."""
    if audit_dir is None:
        config = load_config()
        audit_dir = Path(config.audit.directory).expanduser()

    entries = _read_all_entries(audit_dir)

    # Filter to successful task executions only
    filtered = [
        e for e in entries
        if e.get("status") == "success"
        and not e.get("task", "").startswith(("policy_check:", "adversarial_review:"))
    ]

    if backend:
        filtered = [e for e in filtered if e.get("backend") == backend]
    if task_category:
        filtered = [e for e in filtered if e.get("task_category") == task_category]

    if len(filtered) < min_entries:
        return None

    durations = [e.get("duration_seconds", 0) for e in filtered]
    return sum(durations) / len(durations) if durations else None


def compute_audit_stats(entries: list[dict]) -> dict:
    """
    Compute summary statistics from audit entries.

    Returns dict with: total_actions, tasks, reviews, policy_checks,
    by_backend breakdown, policy_violations, total_cost.
    """
    stats: dict = {
        "total_actions": len(entries),
        "tasks": 0,
        "reviews": 0,
        "policy_checks": 0,
        "by_backend": {},
        "policy_violations": 0,
        "total_cost": 0.0,
    }

    for entry in entries:
        task = entry.get("task", "")
        backend = entry.get("backend", "")
        cost = entry.get("cost_usd") or 0.0

        if task.startswith("adversarial_review"):
            stats["reviews"] += 1
        else:
            stats["tasks"] += 1

        policy_eval = entry.get("policy_evaluation")
        if policy_eval:
            stats["policy_checks"] += 1
            if policy_eval.get("requires_review") and not task.startswith("adversarial_review"):
                stats["policy_violations"] += 1

        # By backend
        if backend:
            for b in backend.split(","):
                b = b.strip()
                if b:
                    stats["by_backend"][b] = stats["by_backend"].get(b, 0) + 1

        stats["total_cost"] += float(cost)

    stats["total_cost"] = round(stats["total_cost"], 4)
    return stats
