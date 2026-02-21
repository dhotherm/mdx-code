"""Routing strategies: cost_optimized, quality_first, balanced."""

from dataclasses import dataclass

from .engine import TaskCategory
from .profiles import BackendProfile


@dataclass
class RoutingDecision:
    """Result of a routing strategy."""

    backend_name: str
    reason: str  # Human-readable explanation
    strategy: str  # Which strategy was used
    scores: dict[str, float]  # All backend scores for comparison


# Bonus multiplier when a task matches a backend's strengths
STRENGTH_BONUS = 1.5


def route_cost_optimized(
    category: TaskCategory,
    available_backends: list[str],
    profiles: dict[str, BackendProfile],
) -> RoutingDecision | None:
    """Pick the cheapest backend, favoring those with matching strengths."""
    if not available_backends:
        return None

    scores: dict[str, float] = {}
    for name in available_backends:
        profile = profiles.get(name)
        if profile is None:
            continue

        # Average cost per 1k tokens (rough proxy for overall cost)
        avg_cost = (
            profile.cost_per_1k_tokens["input"] + profile.cost_per_1k_tokens["output"]
        ) / 2.0

        # Lower cost = higher score (invert)
        score = 1.0 / avg_cost if avg_cost > 0 else 0.0

        # Boost if this backend is strong at the task category
        if category.category in profile.strengths:
            score *= STRENGTH_BONUS

        scores[name] = round(score, 4)

    if not scores:
        return None

    best = max(scores, key=scores.get)  # type: ignore[arg-type]
    profile = profiles[best]
    is_strength = category.category in profile.strengths

    # Build reason string
    cheapest = min(
        available_backends,
        key=lambda n: (
            profiles[n].cost_per_1k_tokens["input"] + profiles[n].cost_per_1k_tokens["output"]
        )
        / 2.0
        if n in profiles
        else float("inf"),
    )

    if is_strength and best != cheapest:
        reason = f"{category.category.replace('_', ' ')}, strength match"
    else:
        # Calculate savings vs most expensive
        if len(available_backends) > 1 and best in profiles:
            most_expensive = max(
                available_backends,
                key=lambda n: (
                    profiles[n].cost_per_1k_tokens["input"]
                    + profiles[n].cost_per_1k_tokens["output"]
                )
                / 2.0
                if n in profiles
                else 0.0,
            )
            if most_expensive != best and most_expensive in profiles:
                best_avg = (
                    profiles[best].cost_per_1k_tokens["input"]
                    + profiles[best].cost_per_1k_tokens["output"]
                ) / 2.0
                exp_avg = (
                    profiles[most_expensive].cost_per_1k_tokens["input"]
                    + profiles[most_expensive].cost_per_1k_tokens["output"]
                ) / 2.0
                savings_pct = int((1 - best_avg / exp_avg) * 100) if exp_avg > 0 else 0
                reason = (
                    f"{category.category.replace('_', ' ')}, "
                    f"{savings_pct}% cheaper than {most_expensive.title()}"
                )
            else:
                reason = f"{category.category.replace('_', ' ')}, cost-optimized"
        else:
            reason = f"{category.category.replace('_', ' ')}, cost-optimized"

    return RoutingDecision(
        backend_name=best,
        reason=reason,
        strategy="cost_optimized",
        scores=scores,
    )


def route_quality_first(
    category: TaskCategory,
    available_backends: list[str],
    profiles: dict[str, BackendProfile],
) -> RoutingDecision | None:
    """Pick the highest quality backend, with strength as the tiebreaker."""
    if not available_backends:
        return None

    scores: dict[str, float] = {}
    for name in available_backends:
        profile = profiles.get(name)
        if profile is None:
            continue

        score = profile.quality_score

        # Strength match wins regardless
        if category.category in profile.strengths:
            score += 1.0  # Guarantees strength match wins over raw quality

        scores[name] = round(score, 4)

    if not scores:
        return None

    best = max(scores, key=scores.get)  # type: ignore[arg-type]
    profile = profiles[best]
    is_strength = category.category in profile.strengths

    reason = f"quality-first for {category.category.replace('_', ' ')}"
    if is_strength:
        reason = f"{category.category.replace('_', ' ')}, strength match"

    return RoutingDecision(
        backend_name=best,
        reason=reason,
        strategy="quality_first",
        scores=scores,
    )


def route_balanced(
    category: TaskCategory,
    available_backends: list[str],
    profiles: dict[str, BackendProfile],
) -> RoutingDecision | None:
    """Score: quality_score * strength_bonus / relative_cost. Best overall value."""
    if not available_backends:
        return None

    # Find the cheapest backend's average cost for normalization
    avg_costs = {}
    for name in available_backends:
        profile = profiles.get(name)
        if profile is None:
            continue
        avg_costs[name] = (
            profile.cost_per_1k_tokens["input"] + profile.cost_per_1k_tokens["output"]
        ) / 2.0

    if not avg_costs:
        return None

    min_cost = min(avg_costs.values())

    scores: dict[str, float] = {}
    for name in available_backends:
        profile = profiles.get(name)
        if profile is None or name not in avg_costs:
            continue

        quality = profile.quality_score
        strength_mult = STRENGTH_BONUS if category.category in profile.strengths else 1.0
        relative_cost = avg_costs[name] / min_cost if min_cost > 0 else 1.0

        score = (quality * strength_mult) / relative_cost
        scores[name] = round(score, 4)

    if not scores:
        return None

    best = max(scores, key=scores.get)  # type: ignore[arg-type]
    profile = profiles[best]
    is_strength = category.category in profile.strengths

    reason = f"balanced for {category.category.replace('_', ' ')}"
    if is_strength:
        reason = f"{category.category.replace('_', ' ')}, best value"

    return RoutingDecision(
        backend_name=best,
        reason=reason,
        strategy="balanced",
        scores=scores,
    )


# Strategy dispatch
STRATEGIES = {
    "cost_optimized": route_cost_optimized,
    "quality_first": route_quality_first,
    "balanced": route_balanced,
}


def route_task(
    category: TaskCategory,
    available_backends: list[str],
    profiles: dict[str, BackendProfile],
    strategy: str = "balanced",
) -> RoutingDecision | None:
    """Route a task using the specified strategy."""
    route_fn = STRATEGIES.get(strategy)
    if route_fn is None:
        raise ValueError(f"Unknown strategy: {strategy}. Use: {list(STRATEGIES.keys())}")
    return route_fn(category, available_backends, profiles)
