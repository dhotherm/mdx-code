"""Task categorization engine — keyword-based, no LLM calls."""

import re
from dataclasses import dataclass


@dataclass
class TaskCategory:
    """Result of task categorization."""

    category: str
    confidence: float  # 0.0 to 1.0


# Category definitions: (category_name, keywords, weight_boost)
# Keywords are checked as word boundaries to avoid false matches.
# weight_boost increases confidence when multiple keywords match.
CATEGORY_RULES: list[tuple[str, list[str], float]] = [
    (
        "test_writing",
        [
            "test", "tests", "spec", "specs", "coverage", "assert",
            "unittest", "pytest", "jest", "mocha", "testing",
            "write tests", "add tests", "unit test", "integration test",
            "test cases", "test suite",
        ],
        0.15,
    ),
    (
        "code_review",
        [
            "review", "check", "audit", "inspect", "analyze",
            "code review", "pull request", "pr review", "lint",
            "look at", "examine",
        ],
        0.10,
    ),
    (
        "security",
        [
            "security", "vulnerability", "vulnerabilities", "cve",
            "owasp", "injection", "xss", "csrf", "sql injection",
            "authentication", "authorization", "exploit", "penetration",
            "scan for", "security audit", "secure",
        ],
        0.15,
    ),
    (
        "debugging",
        [
            "fix", "bug", "broken", "failing", "crash",
            "debug", "problem", "not working", "exception",
            "traceback", "stack trace", "segfault", "undefined",
            "TypeError", "ValueError", "KeyError",
            "returns error", "throws error", "500 error", "error on",
        ],
        0.10,
    ),
    (
        "refactoring",
        [
            "refactor", "clean up", "cleanup", "optimize", "simplify",
            "restructure", "reorganize", "improve", "modernize",
            "decouple", "extract", "inline", "rename",
        ],
        0.10,
    ),
    (
        "documentation",
        [
            "document", "documentation", "readme", "comments",
            "explain", "docstring", "docstrings", "jsdoc", "typedoc",
            "api docs", "changelog", "wiki",
        ],
        0.10,
    ),
    (
        "code_generation",
        [
            "create", "build", "implement", "add", "generate",
            "scaffold", "bootstrap", "new feature", "add feature",
            "write", "develop", "make", "set up", "setup",
            "add endpoint", "add page", "add component",
        ],
        0.05,
    ),
]

# Minimum confidence to avoid defaulting to "general"
CONFIDENCE_THRESHOLD = 0.3


def categorize_task(task: str) -> TaskCategory:
    """
    Categorize a task description using keyword matching.

    Fast and deterministic — no LLM calls.
    Returns the best-matching category with confidence score.
    """
    task_lower = task.lower()
    scores: dict[str, float] = {}

    for category, keywords, boost in CATEGORY_RULES:
        match_count = 0
        for keyword in keywords:
            # Use word boundary matching for single words,
            # substring for multi-word phrases
            if " " in keyword:
                if keyword in task_lower:
                    match_count += 1
            else:
                if re.search(rf"\b{re.escape(keyword)}\b", task_lower):
                    match_count += 1

        if match_count > 0:
            # Base confidence from ratio of matched keywords
            base = min(match_count / 3.0, 1.0)  # 3 matches = full confidence
            # Boost for each additional match
            extra = min(match_count - 1, 3) * boost
            scores[category] = min(base + extra, 1.0)

    if not scores:
        return TaskCategory(category="general", confidence=0.5)

    best_category = max(scores, key=scores.get)  # type: ignore[arg-type]
    best_score = scores[best_category]

    if best_score < CONFIDENCE_THRESHOLD:
        return TaskCategory(category="general", confidence=0.5)

    return TaskCategory(category=best_category, confidence=round(best_score, 2))
