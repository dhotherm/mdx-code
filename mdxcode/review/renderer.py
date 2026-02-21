"""Beautiful terminal output for adversarial review results."""

import json
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from .consensus import ConfirmedFinding, ConflictFinding, UniqueFinding
from .normalizer import Finding
from .orchestrator import AdversarialReviewResult

console = Console()


def _severity_icon(severity: str) -> str:
    """Return colored icon for severity level."""
    icons = {
        "critical": "[red bold]CRITICAL[/red bold]",
        "high": "[red]HIGH[/red]",
        "medium": "[yellow]MEDIUM[/yellow]",
        "low": "[blue]LOW[/blue]",
    }
    return icons.get(severity, severity.upper())


def _format_line(line: int | tuple[int, int]) -> str:
    """Format a line reference for display."""
    if isinstance(line, tuple):
        return f"{line[0]}-{line[1]}"
    return str(line)


def _format_finding_location(finding: Finding) -> str:
    """Format file:line reference."""
    return f"{finding.file}:{_format_line(finding.line)}"


def _get_backend_display_name(name: str) -> str:
    """Pretty backend name for display."""
    names = {
        "claude": "Claude",
        "codex": "Codex",
        "gemini": "Gemini",
    }
    return names.get(name, name.title())


def _wrap_description(text: str, indent: int = 4, width: int = 60) -> str:
    """Wrap description text with indentation, preserving quotes."""
    prefix = " " * indent
    lines = []
    words = text.split()
    current = prefix

    for word in words:
        if len(current) + len(word) + 1 > width + indent:
            lines.append(current)
            current = prefix + word
        else:
            if current == prefix:
                current += word
            else:
                current += " " + word

    if current.strip():
        lines.append(current)

    return "\n".join(lines)


def render_review(result: AdversarialReviewResult, format: str = "rich") -> Optional[str]:
    """
    Render the review result to terminal.

    Args:
        result: The adversarial review result to render.
        format: "rich" for terminal output, "json" for machine-readable.

    Returns:
        JSON string if format is "json", None otherwise (prints to console).
    """
    if format == "json":
        return _render_json(result)

    _render_rich(result)
    return None


def _render_json(result: AdversarialReviewResult) -> str:
    """Render review result as JSON."""
    data = {
        "target": result.target.description,
        "files_reviewed": result.target.files,
        "backends_used": [br.backend_name for br in result.backend_results],
        "duration_seconds": round(result.total_duration_seconds, 1),
        "total_cost_usd": result.total_cost_usd,
        "confirmed": [
            {
                "file": cf.finding.file,
                "line": _format_line(cf.finding.line),
                "severity": cf.finding.severity,
                "category": cf.finding.category,
                "title": cf.finding.title,
                "description": cf.finding.description,
                "cwe_id": cf.finding.cwe_id,
                "suggestion": cf.finding.suggestion,
                "confirmed_by": cf.confirmed_by,
                "confidence": cf.confidence,
            }
            for cf in result.consensus.confirmed
        ],
        "unique": [
            {
                "file": uf.finding.file,
                "line": _format_line(uf.finding.line),
                "severity": uf.finding.severity,
                "category": uf.finding.category,
                "title": uf.finding.title,
                "description": uf.finding.description,
                "cwe_id": uf.finding.cwe_id,
                "suggestion": uf.finding.suggestion,
                "found_by": uf.found_by,
            }
            for uf in result.consensus.unique
        ],
        "conflicts": [
            {
                "conflict_type": cf.conflict_type,
                "findings": [
                    {
                        "file": f.file,
                        "line": _format_line(f.line),
                        "severity": f.severity,
                        "source_backend": f.source_backend,
                        "title": f.title,
                    }
                    for f in cf.findings
                ],
            }
            for cf in result.consensus.conflicts
        ],
        "summary": {
            "total_findings": (
                len(result.consensus.confirmed)
                + len(result.consensus.unique)
                + len(result.consensus.conflicts)
            ),
            "confirmed": len(result.consensus.confirmed),
            "unique": len(result.consensus.unique),
            "conflicts": len(result.consensus.conflicts),
        },
    }
    return json.dumps(data, indent=2)


def _render_rich(result: AdversarialReviewResult) -> None:
    """Render beautiful terminal output."""
    consensus = result.consensus
    backends_used = [br.backend_name for br in result.backend_results if not br.error]
    n_backends = len(backends_used)

    # Header panel
    backends_display = ", ".join(
        _get_backend_display_name(name) for name in backends_used
    )
    header_lines = [
        "",
        f"  Reviewed: {result.target.description}",
        f"  Backends: {backends_display}",
        f"  Duration: {result.total_duration_seconds:.1f}s (parallel)",
        "",
    ]
    console.print(
        Panel(
            "\n".join(header_lines),
            title="Adversarial Review",
            border_style="bold cyan",
            width=min(console.width, 64),
        )
    )

    # Show errors for backends that failed
    for br in result.backend_results:
        if br.error:
            console.print(
                f"  [red]! {_get_backend_display_name(br.backend_name)} "
                f"failed: {br.error}[/red]"
            )
            console.print()

    total_findings = len(consensus.confirmed) + len(consensus.unique) + len(consensus.conflicts)
    if total_findings == 0:
        console.print("  [green]No issues found.[/green]")
        console.print()
        _render_summary(result)
        return

    separator = "\u2500" * min(console.width - 4, 56)

    # Confirmed findings
    for cf in consensus.confirmed:
        _render_confirmed(cf, n_backends, result)
        console.print(f"  [dim]{separator}[/dim]")
        console.print()

    # Unique findings
    for uf in consensus.unique:
        _render_unique(uf)
        console.print(f"  [dim]{separator}[/dim]")
        console.print()

    # Conflict findings
    for conflict in consensus.conflicts:
        _render_conflict(conflict)
        console.print(f"  [dim]{separator}[/dim]")
        console.print()

    _render_summary(result)


def _render_confirmed(cf: ConfirmedFinding, n_backends: int, result: AdversarialReviewResult) -> None:
    """Render a confirmed finding."""
    backends_str = "/".join(str(n) for n in [n_backends, n_backends])
    console.print()
    console.print(
        f"  [red bold]\U0001f534 CONFIRMED ({len(cf.confirmed_by)}/{n_backends} agree) "
        f"\u2014 HIGH CONFIDENCE[/red bold]"
    )
    console.print()

    f = cf.finding
    console.print(f"    [bold]{_format_finding_location(f)}[/bold]")
    console.print(f"    {f.title}")
    if f.cwe_id:
        # Look up CWE description (simplified)
        console.print(f"    [dim]{f.cwe_id}[/dim]")
    console.print()

    # Show what each backend said
    for af in cf.all_findings:
        name = _get_backend_display_name(af.source_backend)
        desc = af.description
        if len(desc) > 120:
            desc = desc[:117] + "..."
        console.print(f'    [bold]{name}:[/bold] "{desc}"')
    console.print()

    if f.suggestion:
        console.print(f"    [green]Fix:[/green] {f.suggestion}")


def _render_unique(uf: UniqueFinding) -> None:
    """Render a unique finding."""
    console.print()
    backend_display = _get_backend_display_name(uf.found_by)
    console.print(
        f"  [yellow]\U0001f7e1 UNIQUE \u2014 Found by {backend_display} only[/yellow]"
    )
    console.print()

    f = uf.finding
    console.print(f"    [bold]{_format_finding_location(f)}[/bold]")
    console.print(f"    {f.title}")
    if f.cwe_id:
        console.print(f"    [dim]{f.cwe_id}[/dim]")
    console.print()

    desc = f.description
    if len(desc) > 200:
        desc = desc[:197] + "..."
    console.print(f'    "{desc}"')
    console.print()

    if f.suggestion:
        console.print(f"    [green]Fix:[/green] {f.suggestion}")


def _render_conflict(cf: ConflictFinding) -> None:
    """Render a conflict finding."""
    console.print()
    console.print(
        f"  [magenta]\U0001f7e3 CONFLICT \u2014 {cf.conflict_type.replace('_', ' ').title()}[/magenta]"
    )
    console.print()

    for f in cf.findings:
        backend_display = _get_backend_display_name(f.source_backend)
        console.print(
            f"    [bold]{backend_display}:[/bold] "
            f"{_format_finding_location(f)} "
            f"[{_severity_icon(f.severity)}] {f.title}"
        )
    console.print()


def _render_summary(result: AdversarialReviewResult) -> None:
    """Render the summary panel."""
    consensus = result.consensus
    n_confirmed = len(consensus.confirmed)
    n_unique = len(consensus.unique)
    n_conflicts = len(consensus.conflicts)
    total = n_confirmed + n_unique + n_conflicts

    backends_used = [br for br in result.backend_results if not br.error]

    lines = [""]

    if total > 0:
        parts = []
        if n_confirmed:
            parts.append(f"{n_confirmed} confirmed")
        if n_unique:
            parts.append(f"{n_unique} unique")
        if n_conflicts:
            parts.append(f"{n_conflicts} conflicts")
        lines.append(f"  {total} findings: {', '.join(parts)}")
    else:
        lines.append("  No findings.")

    # "Neither model alone found all N" — only if it's true
    if n_confirmed > 0 and n_unique > 0 and len(backends_used) >= 2:
        # Check: did each backend miss at least one finding the other caught?
        backend_names = {br.backend_name for br in backends_used}
        unique_by = {uf.found_by for uf in consensus.unique}
        # If we have unique findings from multiple backends, neither found all
        if len(unique_by) >= 2 or (len(unique_by) == 1 and n_confirmed > 0):
            lines.append(f"  [bold]Neither model alone found all {total}.[/bold]")

    lines.append("")

    # Cost breakdown
    if result.total_cost_usd > 0:
        cost_parts = []
        for br in backends_used:
            name = _get_backend_display_name(br.backend_name)
            c = result.cost_by_backend.get(br.backend_name, 0)
            if c > 0:
                cost_parts.append(f"${c:.2f} {name}")
        cost_detail = " + ".join(cost_parts) if cost_parts else ""
        cost_line = f"  Cost: ${result.total_cost_usd:.2f} total"
        if cost_detail:
            cost_line += f" ({cost_detail})"
        lines.append(cost_line)

    lines.append("")

    console.print(
        Panel(
            "\n".join(lines),
            title="Summary",
            border_style="bold cyan",
            width=min(console.width, 64),
        )
    )

    # Suggest next action for confirmed findings
    if n_confirmed > 0:
        first_confirmed = consensus.confirmed[0].finding
        location = _format_finding_location(first_confirmed)
        console.print()
        console.print(
            f'  [dim]\u2192 Fix confirmed issue? Run:[/dim] '
            f'[bold]mdx "fix {first_confirmed.title.lower()} in {first_confirmed.file}"[/bold]'
        )
        console.print()
