"""Consensus engine: compare findings across backends to detect agreement."""

from dataclasses import dataclass, field

from .normalizer import Finding

SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}

# Two findings match if their lines are within this many lines of each other
LINE_PROXIMITY_THRESHOLD = 5


@dataclass
class ConfirmedFinding:
    """Finding confirmed by multiple backends."""

    finding: Finding
    confirmed_by: list[str] = field(default_factory=list)
    confidence: float = 1.0
    all_findings: list[Finding] = field(default_factory=list)


@dataclass
class UniqueFinding:
    """Finding from only one backend."""

    finding: Finding
    found_by: str = ""


@dataclass
class ConflictFinding:
    """Backends disagree on this finding."""

    findings: list[Finding] = field(default_factory=list)
    conflict_type: str = ""


@dataclass
class ConsensusResult:
    """Result of comparing findings across backends."""

    confirmed: list[ConfirmedFinding] = field(default_factory=list)
    unique: list[UniqueFinding] = field(default_factory=list)
    conflicts: list[ConflictFinding] = field(default_factory=list)


def _get_line_center(line: int | tuple[int, int]) -> int:
    """Get the center line number from a line or line range."""
    if isinstance(line, tuple):
        return (line[0] + line[1]) // 2
    return line


def _lines_overlap_or_near(
    line_a: int | tuple[int, int],
    line_b: int | tuple[int, int],
) -> bool:
    """Check if two line references overlap or are within LINE_PROXIMITY_THRESHOLD."""
    # Convert to ranges
    if isinstance(line_a, int):
        a_start, a_end = line_a, line_a
    else:
        a_start, a_end = line_a

    if isinstance(line_b, int):
        b_start, b_end = line_b, line_b
    else:
        b_start, b_end = line_b

    # Check overlap
    if a_start <= b_end and b_start <= a_end:
        return True

    # Check proximity
    gap = min(abs(a_start - b_end), abs(b_start - a_end))
    return gap <= LINE_PROXIMITY_THRESHOLD


def _extract_keywords(text: str) -> set[str]:
    """Extract significant keywords from a title or description for fuzzy matching."""
    stop_words = {
        "the",
        "a",
        "an",
        "is",
        "are",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "with",
        "by",
        "from",
        "not",
        "no",
        "and",
        "or",
        "but",
        "this",
        "that",
        "it",
        "be",
        "has",
        "have",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "use",
        "using",
        "used",
        "code",
        "issue",
        "found",
    }
    words = set(text.lower().split())
    return words - stop_words


def _findings_match(a: Finding, b: Finding) -> bool:
    """
    Determine if two findings refer to the same issue.

    Two findings match if:
    1. Same file AND
    2. Lines overlap or are within 5 lines of each other AND
    3. Same category OR same CWE ID
    """
    # Must be same file
    if a.file != b.file:
        return False

    # Lines must be close
    if not _lines_overlap_or_near(a.line, b.line):
        return False

    # Same category or same CWE
    if a.category == b.category:
        return True

    if a.cwe_id and b.cwe_id and a.cwe_id == b.cwe_id:
        return True

    # Fuzzy: check for significant keyword overlap in titles
    keywords_a = _extract_keywords(a.title)
    keywords_b = _extract_keywords(b.title)
    if keywords_a and keywords_b:
        overlap = keywords_a & keywords_b
        if len(overlap) >= 2:
            return True

    return False


def _higher_severity(sev_a: str, sev_b: str) -> str:
    """Return the more severe of two severity levels."""
    rank_a = SEVERITY_RANK.get(sev_a, 0)
    rank_b = SEVERITY_RANK.get(sev_b, 0)
    return sev_a if rank_a >= rank_b else sev_b


def _merge_confirmed(findings: list[Finding]) -> Finding:
    """
    Create a canonical finding from multiple confirming findings.

    Uses the higher severity and merges descriptions.
    """
    if len(findings) == 1:
        return findings[0]

    # Use the finding with the highest severity as the base
    best = max(findings, key=lambda f: SEVERITY_RANK.get(f.severity, 0))
    merged_severity = best.severity
    for f in findings:
        merged_severity = _higher_severity(merged_severity, f.severity)

    return Finding(
        file=best.file,
        line=best.line,
        severity=merged_severity,
        category=best.category,
        title=best.title,
        description=best.description,
        cwe_id=best.cwe_id or next((f.cwe_id for f in findings if f.cwe_id), None),
        suggestion=best.suggestion or next((f.suggestion for f in findings if f.suggestion), None),
        source_backend=best.source_backend,
        raw_response=best.raw_response,
    )


def build_consensus(
    findings_by_backend: dict[str, list[Finding]],
) -> ConsensusResult:
    """
    Compare findings across backends and build consensus.

    Args:
        findings_by_backend: Mapping of backend name to list of findings.

    Returns:
        ConsensusResult with confirmed, unique, and conflict findings.
    """
    backend_names = list(findings_by_backend.keys())

    if len(backend_names) == 0:
        return ConsensusResult()

    # Single backend: everything is unique
    if len(backend_names) == 1:
        name = backend_names[0]
        return ConsensusResult(
            unique=[UniqueFinding(finding=f, found_by=name) for f in findings_by_backend[name]],
        )

    # Track which findings have been matched
    matched: dict[str, set[int]] = {name: set() for name in backend_names}
    confirmed: list[ConfirmedFinding] = []
    conflicts: list[ConflictFinding] = []

    # Compare each pair of backends
    for i, name_a in enumerate(backend_names):
        for name_b in backend_names[i + 1 :]:
            findings_a = findings_by_backend[name_a]
            findings_b = findings_by_backend[name_b]

            for idx_a, fa in enumerate(findings_a):
                if idx_a in matched[name_a]:
                    continue
                for idx_b, fb in enumerate(findings_b):
                    if idx_b in matched[name_b]:
                        continue
                    if _findings_match(fa, fb):
                        # Check for severity conflicts
                        if fa.severity != fb.severity:
                            severity_diff = abs(
                                SEVERITY_RANK.get(fa.severity, 0)
                                - SEVERITY_RANK.get(fb.severity, 0)
                            )
                            if severity_diff >= 2:
                                # Major severity disagreement → conflict
                                conflicts.append(
                                    ConflictFinding(
                                        findings=[fa, fb],
                                        conflict_type="severity_mismatch",
                                    )
                                )
                                matched[name_a].add(idx_a)
                                matched[name_b].add(idx_b)
                                break

                        # Confirmed match
                        merged = _merge_confirmed([fa, fb])
                        n_backends = len(backend_names)
                        confirmed.append(
                            ConfirmedFinding(
                                finding=merged,
                                confirmed_by=[name_a, name_b],
                                confidence=2.0 / n_backends,
                                all_findings=[fa, fb],
                            )
                        )
                        matched[name_a].add(idx_a)
                        matched[name_b].add(idx_b)
                        break

    # Remaining unmatched findings are unique
    unique: list[UniqueFinding] = []
    for name in backend_names:
        for idx, finding in enumerate(findings_by_backend[name]):
            if idx not in matched[name]:
                unique.append(UniqueFinding(finding=finding, found_by=name))

    return ConsensusResult(
        confirmed=confirmed,
        unique=unique,
        conflicts=conflicts,
    )
