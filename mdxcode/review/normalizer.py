"""Normalize findings from different backend outputs into a common format."""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

VALID_SEVERITIES = {"critical", "high", "medium", "low"}
VALID_CATEGORIES = {"security", "logic", "performance", "quality", "maintainability"}


@dataclass
class Finding:
    """Normalized finding from any backend."""

    file: str
    line: int | tuple[int, int]
    severity: str
    category: str
    title: str
    description: str
    cwe_id: Optional[str] = None
    suggestion: Optional[str] = None
    source_backend: str = ""
    raw_response: str = ""


def _extract_json(raw: str) -> Optional[str]:
    """
    Extract JSON from raw output that may contain markdown fences or commentary.

    Handles:
    - Clean JSON
    - JSON wrapped in ```json ... ``` fences
    - JSON with surrounding commentary text
    - Multiple JSON objects (takes the first valid one)
    """
    # Try direct parse first
    stripped = raw.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return stripped

    # Try to extract from markdown code fences
    fence_pattern = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)
    match = fence_pattern.search(raw)
    if match:
        return match.group(1).strip()

    # Try to find a JSON object in the text
    # Look for {"findings": ...}
    brace_start = raw.find("{")
    if brace_start >= 0:
        # Find the matching closing brace
        depth = 0
        for i in range(brace_start, len(raw)):
            if raw[i] == "{":
                depth += 1
            elif raw[i] == "}":
                depth -= 1
                if depth == 0:
                    return raw[brace_start : i + 1]

    return None


def _parse_line(line_val: object) -> int | tuple[int, int]:
    """Parse a line value that might be an int, string, or range."""
    if isinstance(line_val, int):
        return max(1, line_val)
    if isinstance(line_val, list) and len(line_val) == 2:
        return (max(1, int(line_val[0])), max(1, int(line_val[1])))
    if isinstance(line_val, str):
        # Handle "10-20" range format
        if "-" in line_val:
            parts = line_val.split("-", 1)
            try:
                return (max(1, int(parts[0].strip())), max(1, int(parts[1].strip())))
            except (ValueError, IndexError):
                pass
        try:
            return max(1, int(line_val))
        except ValueError:
            pass
    return 1


def _normalize_severity(sev: str) -> str:
    """Normalize severity to one of the valid values."""
    sev_lower = sev.lower().strip()
    if sev_lower in VALID_SEVERITIES:
        return sev_lower
    # Map common aliases
    aliases = {
        "error": "high",
        "warning": "medium",
        "info": "low",
        "warn": "medium",
        "danger": "critical",
        "severe": "critical",
    }
    return aliases.get(sev_lower, "medium")


def _normalize_category(cat: str) -> str:
    """Normalize category to one of the valid values."""
    cat_lower = cat.lower().strip()
    if cat_lower in VALID_CATEGORIES:
        return cat_lower
    # Map common aliases
    aliases = {
        "bug": "logic",
        "error": "logic",
        "style": "quality",
        "code_quality": "quality",
        "code-quality": "quality",
        "perf": "performance",
        "efficiency": "performance",
        "sec": "security",
        "vulnerability": "security",
        "maintenance": "maintainability",
        "readability": "maintainability",
        "complexity": "maintainability",
    }
    return aliases.get(cat_lower, "quality")


def _normalize_cwe(cwe_val: object) -> Optional[str]:
    """Normalize CWE ID to a standard format like 'CWE-89'."""
    if cwe_val is None:
        return None
    cwe_str = str(cwe_val).strip()
    if not cwe_str or cwe_str.lower() in ("none", "n/a", "null", ""):
        return None
    # Already in CWE-NNN format
    if re.match(r"^CWE-\d+$", cwe_str, re.IGNORECASE):
        return cwe_str.upper()
    # Just a number
    if re.match(r"^\d+$", cwe_str):
        return f"CWE-{cwe_str}"
    return cwe_str.upper()


def normalize_findings(raw_output: str, backend_name: str) -> list[Finding]:
    """
    Parse backend output into normalized findings.

    Must handle:
    - Clean JSON response
    - JSON wrapped in ```json code fences
    - JSON with surrounding commentary
    - Partial JSON (best-effort parsing)
    - Complete failure to parse (return empty list, log warning)
    """
    if not raw_output or not raw_output.strip():
        return []

    json_str = _extract_json(raw_output)
    if json_str is None:
        logger.warning("Could not extract JSON from %s output", backend_name)
        return []

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        # Try to fix common JSON issues: trailing commas
        cleaned = re.sub(r",\s*([}\]])", r"\1", json_str)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON from %s output", backend_name)
            return []

    # Extract findings list
    findings_list: list[dict] = []
    if isinstance(data, dict):
        findings_list = data.get("findings", [])
        if not isinstance(findings_list, list):
            findings_list = []
    elif isinstance(data, list):
        findings_list = data
    else:
        return []

    results: list[Finding] = []
    for item in findings_list:
        if not isinstance(item, dict):
            continue

        try:
            finding = Finding(
                file=str(item.get("file", "unknown")),
                line=_parse_line(item.get("line", 1)),
                severity=_normalize_severity(str(item.get("severity", "medium"))),
                category=_normalize_category(str(item.get("category", "quality"))),
                title=str(item.get("title", "Untitled finding")),
                description=str(item.get("description", "")),
                cwe_id=_normalize_cwe(item.get("cwe_id") or item.get("cwe")),
                suggestion=str(item.get("suggestion", "")) or None,
                source_backend=backend_name,
                raw_response=raw_output,
            )
            results.append(finding)
        except (ValueError, TypeError, KeyError) as e:
            logger.warning("Skipping malformed finding from %s: %s", backend_name, e)
            continue

    return results
