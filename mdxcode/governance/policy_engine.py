"""Policy engine for MDx Code governance."""

import fnmatch
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field


class PolicyRequirements(BaseModel):
    """What a policy requires."""

    adversarial_review: bool = False
    min_reviewers: int = 1
    human_approval: bool = False


class Policy(BaseModel):
    """A single policy rule."""

    name: str
    description: str = ""
    paths: list[str] = Field(default_factory=list)
    requires: PolicyRequirements = Field(default_factory=PolicyRequirements)
    severity: str = "medium"


class PolicyDefaults(BaseModel):
    """Default policy settings applied when no specific policy matches."""

    adversarial_review: bool = False
    human_approval: bool = False
    severity: str = "low"


class PolicyFile(BaseModel):
    """Top-level .mdxpolicy file structure."""

    version: str = "1.0"
    policies: list[Policy] = Field(default_factory=list)
    defaults: PolicyDefaults = Field(default_factory=PolicyDefaults)


class PolicyResult(BaseModel):
    """Result of evaluating policies against files."""

    allowed: bool = True
    requires_review: bool = False
    requires_approval: bool = False
    min_reviewers: int = 1
    matching_policies: list[str] = Field(default_factory=list)
    blocked_reason: Optional[str] = None


def load_policy_file(path: Optional[Path] = None) -> Optional[PolicyFile]:
    """
    Load and parse a .mdxpolicy YAML file.

    If no path is given, walks up from cwd to find one.
    Returns None if no policy file is found or if parsing fails.
    """
    if path is not None:
        if not path.exists():
            return None
        try:
            raw = yaml.safe_load(path.read_text()) or {}
            return PolicyFile(**raw)
        except (yaml.YAMLError, Exception):
            return None

    # Walk up directories to find .mdxpolicy
    current = Path.cwd()
    for parent in [current, *current.parents]:
        candidate = parent / ".mdxpolicy"
        if candidate.exists():
            try:
                raw = yaml.safe_load(candidate.read_text()) or {}
                return PolicyFile(**raw)
            except (yaml.YAMLError, Exception):
                return None
    return None


def _match_segments(path_parts: list[str], pattern_segments: list[str]) -> bool:
    """
    Recursively match path parts against pattern segments split on **.

    Each segment is a (possibly empty) fixed portion between ** wildcards.
    Empty segments mean ** matched zero or more directories.
    """
    if not pattern_segments:
        return len(path_parts) == 0

    segment = pattern_segments[0]
    remaining_segments = pattern_segments[1:]

    if not segment:
        # Empty segment = ** wildcard: try matching remaining segments
        # starting from every position in path_parts
        if not remaining_segments:
            return True  # Trailing ** matches everything
        for i in range(len(path_parts) + 1):
            if _match_segments(path_parts[i:], remaining_segments):
                return True
        return False

    # Non-empty segment: split into sub-parts and match literally
    seg_parts = segment.split("/")
    if len(seg_parts) > len(path_parts):
        return False

    for sp, pp in zip(seg_parts, path_parts):
        if not fnmatch.fnmatch(pp, sp):
            return False

    return _match_segments(path_parts[len(seg_parts):], remaining_segments)


def _match_path(filepath: str, pattern: str) -> bool:
    """
    Match a filepath against a glob pattern with ** support.

    Uses fnmatch for simple patterns and handles ** by recursively
    matching path segments.
    """
    # Normalize separators
    filepath = filepath.replace("\\", "/")
    pattern = pattern.replace("\\", "/")

    # If pattern has no ** just use fnmatch directly
    if "**" not in pattern:
        return fnmatch.fnmatch(filepath, pattern)

    # Split pattern on ** to get fixed segments between wildcards
    # e.g., "src/**/auth/**" -> ["src/", "/auth/", ""]
    # Insert empty strings between parts to represent ** wildcards
    parts = pattern.split("**")

    segments: list[str] = []
    for i, part in enumerate(parts):
        if i > 0:
            segments.append("")  # ** wildcard between parts
        part = part.strip("/")
        segments.append(part)

    return _match_segments(filepath.split("/"), segments)


def evaluate_policies(policy_file: PolicyFile, files: list[str]) -> PolicyResult:
    """
    Evaluate files against loaded policies.

    Uses strictest-wins: if any matching policy requires review or approval,
    the result requires it. min_reviewers uses the maximum across matches.
    """
    matching: list[str] = []
    requires_review = False
    requires_approval = False
    max_reviewers = 1

    for filepath in files:
        for policy in policy_file.policies:
            for pattern in policy.paths:
                if _match_path(filepath, pattern):
                    if policy.name not in matching:
                        matching.append(policy.name)
                    if policy.requires.adversarial_review:
                        requires_review = True
                    if policy.requires.human_approval:
                        requires_approval = True
                    if policy.requires.min_reviewers > max_reviewers:
                        max_reviewers = policy.requires.min_reviewers
                    break  # One pattern match is enough for this policy

    # Apply defaults if no policies matched
    if not matching:
        requires_review = policy_file.defaults.adversarial_review
        requires_approval = policy_file.defaults.human_approval

    return PolicyResult(
        allowed=True,
        requires_review=requires_review,
        requires_approval=requires_approval,
        min_reviewers=max_reviewers,
        matching_policies=matching,
    )


STARTER_POLICY = """\
# MDx Code Policy File
# See: https://github.com/anthropics/mdx-code
version: "1.0"

defaults:
  adversarial_review: false
  human_approval: false
  severity: low

policies:
  - name: security-critical
    description: Security-sensitive code requires adversarial review
    paths:
      - "src/**/auth/**"
      - "src/**/security/**"
      - "**/*secret*"
      - "**/*credential*"
    requires:
      adversarial_review: true
      min_reviewers: 2
      human_approval: true
    severity: critical

  - name: payment-processing
    description: Payment code requires review and approval
    paths:
      - "src/**/payment*/**"
      - "src/**/billing/**"
      - "src/**/stripe*"
    requires:
      adversarial_review: true
      min_reviewers: 2
      human_approval: true
    severity: critical

  - name: infrastructure
    description: Infrastructure changes need review
    paths:
      - "terraform/**"
      - "k8s/**"
      - "docker-compose*.yml"
      - "Dockerfile*"
      - ".github/workflows/**"
    requires:
      adversarial_review: true
      min_reviewers: 1
    severity: high

  - name: database-migrations
    description: Database changes require approval
    paths:
      - "**/migrations/**"
      - "**/*.sql"
    requires:
      adversarial_review: true
      human_approval: true
    severity: high
"""
