"""Tests for routing strategies."""

import pytest

from mdxcode.router.engine import TaskCategory
from mdxcode.router.profiles import BackendProfile
from mdxcode.router.strategies import (
    RoutingDecision,
    route_balanced,
    route_cost_optimized,
    route_quality_first,
    route_task,
)


@pytest.fixture
def profiles():
    """Standard test profiles with clear cost/quality differentials."""
    return {
        "claude": BackendProfile(
            strengths=["code_review", "security", "refactoring"],
            quality_score=0.95,
            cost_per_1k_tokens={"input": 0.003, "output": 0.015},
        ),
        "codex": BackendProfile(
            strengths=["code_generation", "test_writing", "debugging"],
            quality_score=0.90,
            cost_per_1k_tokens={"input": 0.002, "output": 0.008},
        ),
        "gemini": BackendProfile(
            strengths=["code_generation", "documentation", "general"],
            quality_score=0.88,
            cost_per_1k_tokens={"input": 0.001, "output": 0.004},
        ),
    }


@pytest.fixture
def all_backends():
    return ["claude", "codex", "gemini"]


class TestCostOptimized:
    """Tests for cost_optimized strategy."""

    def test_picks_cheapest_for_general(self, profiles, all_backends):
        cat = TaskCategory(category="general", confidence=0.5)
        result = route_cost_optimized(cat, all_backends, profiles)
        assert result is not None
        assert result.backend_name == "gemini"  # Cheapest overall
        assert result.strategy == "cost_optimized"

    def test_cheapest_wins_over_distant_strength(self, profiles, all_backends):
        """When cost gap is large, cheapest wins even without strength match."""
        cat = TaskCategory(category="code_review", confidence=0.8)
        result = route_cost_optimized(cat, all_backends, profiles)
        assert result is not None
        # Claude has code_review strength, but Gemini is 3.6x cheaper
        # Cost-optimized picks cheapest when gap is large
        assert result.backend_name == "gemini"

    def test_strength_wins_at_similar_cost(self):
        """When costs are similar, strength match tips the balance."""
        similar_profiles = {
            "claude": BackendProfile(
                strengths=["code_review"],
                quality_score=0.95,
                cost_per_1k_tokens={"input": 0.002, "output": 0.006},
            ),
            "codex": BackendProfile(
                strengths=["code_generation"],
                quality_score=0.90,
                cost_per_1k_tokens={"input": 0.002, "output": 0.008},
            ),
        }
        cat = TaskCategory(category="code_review", confidence=0.8)
        result = route_cost_optimized(cat, ["claude", "codex"], similar_profiles)
        assert result is not None
        assert result.backend_name == "claude"

    def test_strength_match_with_cheap_backend(self, profiles, all_backends):
        cat = TaskCategory(category="documentation", confidence=0.7)
        result = route_cost_optimized(cat, all_backends, profiles)
        assert result is not None
        # Gemini is cheapest AND has documentation as strength
        assert result.backend_name == "gemini"

    def test_no_backends_returns_none(self, profiles):
        cat = TaskCategory(category="general", confidence=0.5)
        result = route_cost_optimized(cat, [], profiles)
        assert result is None

    def test_single_backend(self, profiles):
        cat = TaskCategory(category="general", confidence=0.5)
        result = route_cost_optimized(cat, ["claude"], profiles)
        assert result is not None
        assert result.backend_name == "claude"

    def test_scores_populated(self, profiles, all_backends):
        cat = TaskCategory(category="test_writing", confidence=0.8)
        result = route_cost_optimized(cat, all_backends, profiles)
        assert result is not None
        assert len(result.scores) == 3
        for name in all_backends:
            assert name in result.scores


class TestQualityFirst:
    """Tests for quality_first strategy."""

    def test_picks_highest_quality_for_general(self, profiles, all_backends):
        cat = TaskCategory(category="general", confidence=0.5)
        result = route_quality_first(cat, all_backends, profiles)
        assert result is not None
        # Gemini has "general" as strength, so it gets the +1 bonus
        assert result.backend_name == "gemini"
        assert result.strategy == "quality_first"

    def test_strength_overrides_raw_quality(self, profiles, all_backends):
        cat = TaskCategory(category="test_writing", confidence=0.8)
        result = route_quality_first(cat, all_backends, profiles)
        assert result is not None
        # Codex has test_writing as strength (+1 bonus = 1.90)
        # Claude has higher raw quality (0.95) but no test_writing strength
        assert result.backend_name == "codex"

    def test_quality_for_security(self, profiles, all_backends):
        cat = TaskCategory(category="security", confidence=0.9)
        result = route_quality_first(cat, all_backends, profiles)
        assert result is not None
        # Claude has security as strength
        assert result.backend_name == "claude"

    def test_no_backends_returns_none(self, profiles):
        cat = TaskCategory(category="general", confidence=0.5)
        result = route_quality_first(cat, [], profiles)
        assert result is None

    def test_single_backend(self, profiles):
        cat = TaskCategory(category="security", confidence=0.9)
        result = route_quality_first(cat, ["gemini"], profiles)
        assert result is not None
        assert result.backend_name == "gemini"


class TestBalanced:
    """Tests for balanced strategy."""

    def test_favors_cheap_and_strong(self, profiles, all_backends):
        cat = TaskCategory(category="documentation", confidence=0.7)
        result = route_balanced(cat, all_backends, profiles)
        assert result is not None
        # Gemini is cheapest + has documentation strength → best value
        assert result.backend_name == "gemini"
        assert result.strategy == "balanced"

    def test_cheapest_strength_wins_balanced(self, profiles, all_backends):
        """Balanced picks the best value — cheap + strength."""
        cat = TaskCategory(category="documentation", confidence=0.7)
        result = route_balanced(cat, all_backends, profiles)
        assert result is not None
        # Gemini is cheapest AND has documentation strength
        assert result.backend_name == "gemini"

    def test_strength_wins_at_closer_cost(self):
        """Strength bonus overcomes moderate cost difference."""
        closer_profiles = {
            "claude": BackendProfile(
                strengths=["security"],
                quality_score=0.95,
                cost_per_1k_tokens={"input": 0.002, "output": 0.006},
            ),
            "codex": BackendProfile(
                strengths=["code_generation"],
                quality_score=0.90,
                cost_per_1k_tokens={"input": 0.002, "output": 0.008},
            ),
        }
        cat = TaskCategory(category="security", confidence=0.9)
        result = route_balanced(cat, ["claude", "codex"], closer_profiles)
        assert result is not None
        assert result.backend_name == "claude"

    def test_no_backends_returns_none(self, profiles):
        cat = TaskCategory(category="general", confidence=0.5)
        result = route_balanced(cat, [], profiles)
        assert result is None

    def test_single_backend(self, profiles):
        cat = TaskCategory(category="general", confidence=0.5)
        result = route_balanced(cat, ["codex"], profiles)
        assert result is not None
        assert result.backend_name == "codex"

    def test_scores_populated(self, profiles, all_backends):
        cat = TaskCategory(category="refactoring", confidence=0.8)
        result = route_balanced(cat, all_backends, profiles)
        assert result is not None
        assert len(result.scores) == 3


class TestRouteTask:
    """Tests for the route_task dispatcher."""

    def test_dispatches_cost_optimized(self, profiles, all_backends):
        cat = TaskCategory(category="general", confidence=0.5)
        result = route_task(cat, all_backends, profiles, "cost_optimized")
        assert result is not None
        assert result.strategy == "cost_optimized"

    def test_dispatches_quality_first(self, profiles, all_backends):
        cat = TaskCategory(category="general", confidence=0.5)
        result = route_task(cat, all_backends, profiles, "quality_first")
        assert result is not None
        assert result.strategy == "quality_first"

    def test_dispatches_balanced(self, profiles, all_backends):
        cat = TaskCategory(category="general", confidence=0.5)
        result = route_task(cat, all_backends, profiles, "balanced")
        assert result is not None
        assert result.strategy == "balanced"

    def test_unknown_strategy_raises(self, profiles, all_backends):
        cat = TaskCategory(category="general", confidence=0.5)
        with pytest.raises(ValueError, match="Unknown strategy"):
            route_task(cat, all_backends, profiles, "fastest_ever")

    def test_unknown_backend_in_profiles_skipped(self, profiles):
        cat = TaskCategory(category="general", confidence=0.5)
        result = route_task(cat, ["unknown_backend"], profiles, "balanced")
        assert result is None

    def test_empty_profiles(self, all_backends):
        cat = TaskCategory(category="general", confidence=0.5)
        result = route_task(cat, all_backends, {}, "balanced")
        assert result is None
