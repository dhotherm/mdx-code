"""
Model Router

The whole point of owning the orchestration layer:
you can swap models without changing anything else.

Today it's Claude. Tomorrow it might be GPT-5.
Next week you might route simple tasks to a cheaper model.

The router handles all of that. Same interface, different backends.
"""

import os
from typing import Any, Dict, List, Optional

import anthropic


class ModelRouter:
    """
    Routes requests to the appropriate LLM backend.
    
    Currently supports:
    - claude: Anthropic's Claude models
    - gpt: OpenAI models (coming soon)
    - bedrock: AWS Bedrock (coming soon)
    - vertex: Google Vertex AI (coming soon)
    
    The interface is the same regardless of backend.
    That's the whole point.
    """
    
    def __init__(self, model: str = "claude"):
        self.model = model
        self._clients: Dict[str, Any] = {}
        
        # Initialize the appropriate client
        if model == "claude":
            self._init_claude()
        elif model == "gpt":
            self._init_openai()
        elif model == "bedrock":
            self._init_bedrock()
        elif model == "vertex":
            self._init_vertex()
        else:
            raise ValueError(f"Unknown model: {model}")
    
    def _init_claude(self):
        """Initialize Anthropic client."""
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            # Check for cached credentials
            from mdxcode.models.auth import get_cached_credentials
            creds = get_cached_credentials("claude")
            if creds:
                api_key = creds.get("api_key")
        
        if not api_key:
            raise ValueError(
                "Anthropic API key not found. "
                "Run 'mdxcode auth claude' or set ANTHROPIC_API_KEY"
            )
        
        self._clients["claude"] = anthropic.Anthropic(api_key=api_key)
        self._model_id = "claude-sonnet-4-20250514"
    
    def _init_openai(self):
        """Initialize OpenAI client."""
        # TODO: Implement OpenAI support
        raise NotImplementedError(
            "OpenAI support coming soon. Use --model claude for now."
        )
    
    def _init_bedrock(self):
        """Initialize AWS Bedrock client."""
        # TODO: Implement Bedrock support
        raise NotImplementedError(
            "AWS Bedrock support coming soon. Use --model claude for now."
        )
    
    def _init_vertex(self):
        """Initialize Google Vertex AI client."""
        # TODO: Implement Vertex support
        raise NotImplementedError(
            "Google Vertex AI support coming soon. Use --model claude for now."
        )
    
    async def complete(
        self,
        messages: List[Dict],
        system: str,
        tools: List[Dict],
        max_tokens: int = 4096,
    ) -> Any:
        """
        Get a completion from the model.
        
        This is the unified interface. Regardless of which model
        you're using, you call this the same way.
        """
        if self.model == "claude":
            return await self._complete_claude(messages, system, tools, max_tokens)
        elif self.model == "gpt":
            return await self._complete_openai(messages, system, tools, max_tokens)
        elif self.model == "bedrock":
            return await self._complete_bedrock(messages, system, tools, max_tokens)
        elif self.model == "vertex":
            return await self._complete_vertex(messages, system, tools, max_tokens)
    
    async def _complete_claude(
        self,
        messages: List[Dict],
        system: str,
        tools: List[Dict],
        max_tokens: int,
    ) -> Any:
        """Get completion from Claude."""
        client = self._clients["claude"]
        
        # Claude's API is synchronous, so we run it in the default executor
        import asyncio
        loop = asyncio.get_event_loop()
        
        response = await loop.run_in_executor(
            None,
            lambda: client.messages.create(
                model=self._model_id,
                max_tokens=max_tokens,
                system=system,
                tools=tools,
                messages=messages,
            )
        )
        
        return response
    
    async def _complete_openai(
        self,
        messages: List[Dict],
        system: str,
        tools: List[Dict],
        max_tokens: int,
    ) -> Any:
        """Get completion from OpenAI."""
        raise NotImplementedError("OpenAI support coming soon")
    
    async def _complete_bedrock(
        self,
        messages: List[Dict],
        system: str,
        tools: List[Dict],
        max_tokens: int,
    ) -> Any:
        """Get completion from AWS Bedrock."""
        raise NotImplementedError("Bedrock support coming soon")
    
    async def _complete_vertex(
        self,
        messages: List[Dict],
        system: str,
        tools: List[Dict],
        max_tokens: int,
    ) -> Any:
        """Get completion from Google Vertex AI."""
        raise NotImplementedError("Vertex AI support coming soon")


# Pricing info for cost tracking
MODEL_PRICING = {
    "claude-sonnet-4-20250514": {
        "input_per_1m": 3.0,
        "output_per_1m": 15.0,
    },
    "claude-opus-4-20250514": {
        "input_per_1m": 15.0,
        "output_per_1m": 75.0,
    },
    "gpt-4o": {
        "input_per_1m": 5.0,
        "output_per_1m": 15.0,
    },
}


def calculate_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate the cost of a completion."""
    if model_id not in MODEL_PRICING:
        return 0.0
    
    pricing = MODEL_PRICING[model_id]
    input_cost = (input_tokens / 1_000_000) * pricing["input_per_1m"]
    output_cost = (output_tokens / 1_000_000) * pricing["output_per_1m"]
    
    return input_cost + output_cost


__all__ = [
    "ModelRouter",
    "calculate_cost",
    "MODEL_PRICING",
]
