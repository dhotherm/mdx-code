"""Review orchestrator: coordinates adversarial review across multiple backends."""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from ..backends.base import Backend, TaskResult
from ..backends.discovery import BACKEND_CLASSES, discover_backends
from ..router.profiles import estimate_cost, estimate_tokens_from_chars, get_profiles
from .consensus import ConsensusResult, build_consensus
from .normalizer import Finding, normalize_findings

logger = logging.getLogger(__name__)

# Max chars to send for review (truncate beyond this)
MAX_REVIEW_CHARS = 100_000

DEFAULT_REVIEW_PROMPT = """\
You are performing an independent code review. Analyze the following code for issues.

For each issue found, provide a JSON object with:
- "file": the file path
- "line": the line number (or line range)
- "severity": "critical" | "high" | "medium" | "low"
- "category": "security" | "logic" | "performance" | "quality" | "maintainability"
- "title": short description (one line)
- "description": detailed explanation of the issue
- "cwe_id": CWE ID if this is a security issue (e.g., "CWE-79")
- "suggestion": how to fix it

Respond ONLY with a JSON object: {{"findings": [...]}}

If you find no issues, respond with: {{"findings": []}}

Code to review:
---
{code_content}
---"""


@dataclass
class ReviewTarget:
    """What to review."""

    files: list[str] = field(default_factory=list)
    content: str = ""
    diff: Optional[str] = None
    description: str = ""  # Human-readable description (e.g., "src/auth/")


@dataclass
class BackendReviewResult:
    """Result from a single backend's review."""

    backend_name: str
    findings: list[Finding] = field(default_factory=list)
    raw_output: str = ""
    duration_seconds: float = 0.0
    cost_usd: Optional[float] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    error: Optional[str] = None


@dataclass
class AdversarialReviewResult:
    """Full result of an adversarial review."""

    target: ReviewTarget
    backend_results: list[BackendReviewResult] = field(default_factory=list)
    consensus: ConsensusResult = field(default_factory=ConsensusResult)
    total_duration_seconds: float = 0.0
    total_cost_usd: float = 0.0
    cost_by_backend: dict[str, float] = field(default_factory=dict)


def prepare_target_from_paths(paths: list[str]) -> ReviewTarget:
    """
    Read files/directories and prepare a ReviewTarget.

    For files: reads content directly.
    For directories: reads all supported source files recursively.
    """
    source_extensions = {
        ".py",
        ".js",
        ".ts",
        ".tsx",
        ".jsx",
        ".go",
        ".rs",
        ".java",
        ".rb",
        ".php",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
        ".cs",
        ".swift",
        ".kt",
        ".scala",
        ".sh",
        ".bash",
        ".yaml",
        ".yml",
        ".json",
        ".toml",
        ".sql",
        ".html",
        ".css",
        ".scss",
    }

    files_content: list[str] = []
    file_list: list[str] = []

    for path_str in paths:
        p = Path(path_str)
        if not p.exists():
            logger.warning("Path does not exist: %s", path_str)
            continue

        if p.is_file():
            try:
                content = p.read_text(errors="replace")
                files_content.append(f"### File: {p}\n```\n{content}\n```\n")
                file_list.append(str(p))
            except OSError as e:
                logger.warning("Could not read %s: %s", p, e)
        elif p.is_dir():
            for child in sorted(p.rglob("*")):
                if child.is_file() and child.suffix in source_extensions:
                    try:
                        content = child.read_text(errors="replace")
                        files_content.append(f"### File: {child}\n```\n{content}\n```\n")
                        file_list.append(str(child))
                    except OSError:
                        continue

    combined = "\n".join(files_content)
    if len(combined) > MAX_REVIEW_CHARS:
        combined = combined[:MAX_REVIEW_CHARS] + "\n\n[... truncated due to size ...]"

    description = ", ".join(paths) if len(paths) <= 3 else f"{len(paths)} paths"
    total_lines = sum(c.count("\n") for c in files_content)

    return ReviewTarget(
        files=file_list,
        content=combined,
        description=f"{description} ({len(file_list)} files, {total_lines} lines)",
    )


def prepare_target_from_diff(diff_text: str, diff_ref: str = "") -> ReviewTarget:
    """Prepare a ReviewTarget from a git diff string."""
    if len(diff_text) > MAX_REVIEW_CHARS:
        diff_text = diff_text[:MAX_REVIEW_CHARS] + "\n\n[... truncated due to size ...]"

    # Extract file paths from diff
    files = []
    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            files.append(line[6:])
        elif line.startswith("--- a/"):
            pass  # Skip old file paths

    return ReviewTarget(
        files=files,
        content=diff_text,
        diff=diff_text,
        description=f"diff {diff_ref}" if diff_ref else f"diff ({len(files)} files)",
    )


async def _run_single_review(
    backend: Backend,
    prompt: str,
    cwd: Path,
    timeout: float = 300.0,
) -> BackendReviewResult:
    """Run a review on a single backend and capture the result."""
    start = time.monotonic()
    try:
        result: TaskResult = await asyncio.wait_for(
            backend.execute_and_capture(prompt, cwd),
            timeout=timeout,
        )
        duration = time.monotonic() - start

        findings = normalize_findings(result.output, backend.name)

        return BackendReviewResult(
            backend_name=backend.name,
            findings=findings,
            raw_output=result.output,
            duration_seconds=duration,
            cost_usd=result.cost_usd,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
        )

    except asyncio.TimeoutError:
        duration = time.monotonic() - start
        logger.warning("Backend %s timed out after %.1fs", backend.name, duration)
        return BackendReviewResult(
            backend_name=backend.name,
            duration_seconds=duration,
            error=f"Timed out after {duration:.0f}s",
        )
    except Exception as e:
        duration = time.monotonic() - start
        logger.warning("Backend %s failed: %s", backend.name, e)
        return BackendReviewResult(
            backend_name=backend.name,
            duration_seconds=duration,
            error=str(e),
        )


def _get_backend_instances(backend_names: Optional[list[str]] = None) -> list[Backend]:
    """Get Backend instances, optionally filtered by name."""
    all_instances = [cls() for cls in BACKEND_CLASSES]
    if backend_names is None:
        return [b for b in all_instances if b.name != "opencode"]
    return [b for b in all_instances if b.name in backend_names]


async def run_review(
    target: ReviewTarget,
    backends: Optional[list[str]] = None,
    prompt: str = DEFAULT_REVIEW_PROMPT,
    timeout: float = 300.0,
) -> AdversarialReviewResult:
    """
    Run adversarial review across multiple backends.

    Steps:
    1. Prepare the review prompt with target content
    2. Send SAME content to ALL backends in PARALLEL
    3. Collect and normalize findings
    4. Run consensus detection
    5. Return structured result

    Args:
        target: The code to review.
        backends: List of backend names to use (default: all available).
        prompt: Review prompt template with {code_content} placeholder.
        timeout: Max seconds per backend.

    Returns:
        AdversarialReviewResult with consensus analysis.
    """
    overall_start = time.monotonic()

    # Build the full prompt
    full_prompt = prompt.format(code_content=target.content)

    # Get backend instances
    backend_instances = _get_backend_instances(backends)

    # Filter to available backends
    available_info = await discover_backends()
    available_names = {b.name for b in available_info if b.healthy}
    backend_instances = [b for b in backend_instances if b.name in available_names]

    if not backend_instances:
        return AdversarialReviewResult(
            target=target,
            total_duration_seconds=time.monotonic() - overall_start,
        )

    cwd = Path.cwd()

    # Run ALL backends in PARALLEL
    tasks = [_run_single_review(b, full_prompt, cwd, timeout=timeout) for b in backend_instances]
    backend_results: list[BackendReviewResult] = await asyncio.gather(*tasks)

    # Build consensus from successful results
    findings_by_backend: dict[str, list[Finding]] = {}
    total_cost = 0.0
    cost_by_backend: dict[str, float] = {}

    profiles = get_profiles()

    for br in backend_results:
        if br.error:
            continue
        findings_by_backend[br.backend_name] = br.findings

        # Estimate cost if not provided by backend
        cost = br.cost_usd
        if cost is None and br.raw_output:
            chars = len(br.raw_output) + len(full_prompt)
            est_tokens = estimate_tokens_from_chars(chars)
            tokens_in = br.tokens_in or len(full_prompt) // 4 or 1
            tokens_out = br.tokens_out or est_tokens
            cost = estimate_cost(br.backend_name, tokens_in, tokens_out, profiles)

        if cost:
            total_cost += cost
            cost_by_backend[br.backend_name] = round(cost, 4)

    consensus = build_consensus(findings_by_backend)
    total_duration = time.monotonic() - overall_start

    return AdversarialReviewResult(
        target=target,
        backend_results=backend_results,
        consensus=consensus,
        total_duration_seconds=total_duration,
        total_cost_usd=round(total_cost, 4),
        cost_by_backend=cost_by_backend,
    )
