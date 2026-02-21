"""Backend capability profiles for routing decisions."""

from dataclasses import dataclass


@dataclass
class BackendProfile:
    """Capability profile for a backend."""

    strengths: list[str]
    quality_score: float  # 0.0 to 1.0
    cost_per_1k_tokens: dict[str, float]  # {"input": ..., "output": ...}


# Default profiles — users can override via config
DEFAULT_PROFILES: dict[str, BackendProfile] = {
    "claude": BackendProfile(
        strengths=["code_review", "security", "refactoring", "documentation"],
        quality_score=0.95,
        cost_per_1k_tokens={
            "input": 0.003,
            "output": 0.015,
        },
    ),
    "codex": BackendProfile(
        strengths=["code_generation", "test_writing", "debugging"],
        quality_score=0.90,
        cost_per_1k_tokens={
            "input": 0.002,
            "output": 0.008,
        },
    ),
    "gemini": BackendProfile(
        strengths=["code_generation", "documentation", "general"],
        quality_score=0.88,
        cost_per_1k_tokens={
            "input": 0.001,
            "output": 0.004,
        },
    ),
}


def get_profiles() -> dict[str, BackendProfile]:
    """Get backend profiles. Returns defaults for now; config override is future work."""
    return dict(DEFAULT_PROFILES)


def estimate_cost(
    backend_name: str,
    tokens_in: int,
    tokens_out: int,
    profiles: dict[str, BackendProfile] | None = None,
) -> float:
    """Estimate cost in USD for a given token count."""
    if profiles is None:
        profiles = get_profiles()

    profile = profiles.get(backend_name)
    if profile is None:
        return 0.0

    cost_in = (tokens_in / 1000.0) * profile.cost_per_1k_tokens["input"]
    cost_out = (tokens_out / 1000.0) * profile.cost_per_1k_tokens["output"]
    return round(cost_in + cost_out, 6)


def estimate_tokens_from_chars(char_count: int) -> int:
    """Estimate token count from character count (rough: ~4 chars/token)."""
    return max(char_count // 4, 1)
