"""
MDx Code Models

The abstraction layer that makes models interchangeable:
- Router: Unified interface to any LLM
- Auth: Credential management for each provider

Today it's Claude. Tomorrow it could be anything.
That's the point of owning the orchestration.
"""

from mdxcode.models.router import ModelRouter, calculate_cost, MODEL_PRICING
from mdxcode.models.auth import (
    authenticate,
    get_cached_credentials,
    save_credentials,
    get_authenticated_providers,
)

__all__ = [
    "ModelRouter",
    "calculate_cost",
    "MODEL_PRICING",
    "authenticate",
    "get_cached_credentials",
    "save_credentials",
    "get_authenticated_providers",
]
