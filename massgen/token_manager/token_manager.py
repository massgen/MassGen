# -*- coding: utf-8 -*-
"""
Token and Cost Management Module
Provides unified token estimation and cost calculation for all backends.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

from ..logger_config import logger


@dataclass
class TokenUsage:
    """Token usage and cost tracking."""

    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0.0

    def add(self, other: "TokenUsage"):
        """Add another TokenUsage to this one."""
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.estimated_cost += other.estimated_cost

    def reset(self):
        """Reset all counters to zero."""
        self.input_tokens = 0
        self.output_tokens = 0
        self.estimated_cost = 0.0


@dataclass
class ModelPricing:
    """Pricing information for a model."""

    input_cost_per_1k: float  # Cost per 1000 input tokens
    output_cost_per_1k: float  # Cost per 1000 output tokens
    context_window: Optional[int] = None
    max_output_tokens: Optional[int] = None


class TokenCostCalculator:
    """Unified token estimation and cost calculation."""

    # Default pricing data for various providers and models
    PROVIDER_PRICING: Dict[str, Dict[str, ModelPricing]] = {
        "OpenAI": {
            "gpt-4o": ModelPricing(0.0025, 0.01, 128000, 16384),
            "gpt-4o-mini": ModelPricing(0.00015, 0.0006, 128000, 16384),
            "gpt-4-turbo": ModelPricing(0.01, 0.03, 128000, 4096),
            "gpt-4": ModelPricing(0.03, 0.06, 8192, 8192),
            "gpt-3.5-turbo": ModelPricing(0.0005, 0.0015, 16385, 4096),
            "o1-preview": ModelPricing(0.015, 0.06, 128000, 32768),
            "o1-mini": ModelPricing(0.003, 0.012, 128000, 65536),
            "o3-mini": ModelPricing(0.0011, 0.0044, 200000, 100000),
        },
        "Anthropic": {
            "claude-3-5-sonnet": ModelPricing(0.003, 0.015, 200000, 8192),
            "claude-3-5-haiku": ModelPricing(0.001, 0.005, 200000, 8192),
            "claude-3-opus": ModelPricing(0.015, 0.075, 200000, 4096),
            "claude-3-sonnet": ModelPricing(0.003, 0.015, 200000, 4096),
            "claude-3-haiku": ModelPricing(0.00025, 0.00125, 200000, 4096),
        },
        "Google": {
            "gemini-2.0-flash-exp": ModelPricing(0.0, 0.0, 1048576, 8192),  # Free during experimental
            "gemini-2.0-flash-thinking-exp": ModelPricing(0.0, 0.0, 32767, 8192),
            "gemini-1.5-pro": ModelPricing(0.00125, 0.005, 2097152, 8192),
            "gemini-1.5-flash": ModelPricing(0.000075, 0.0003, 1048576, 8192),
            "gemini-1.5-flash-8b": ModelPricing(0.0000375, 0.00015, 1048576, 8192),
            "gemini-1.0-pro": ModelPricing(0.00025, 0.00125, 32760, 8192),
        },
        "Cerebras": {
            "llama3.3-70b": ModelPricing(0.00035, 0.00035, 128000, 8192),
            "llama3.1-70b": ModelPricing(0.00035, 0.00035, 128000, 8192),
            "llama3.1-8b": ModelPricing(0.00001, 0.00001, 128000, 8192),
        },
        "Together": {
            "meta-llama/Llama-3.3-70B-Instruct-Turbo": ModelPricing(0.00059, 0.00079, 128000, 32768),
            "meta-llama/Llama-3.2-90B-Vision-Instruct-Turbo": ModelPricing(0.00059, 0.00079, 128000, 32768),
            "meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo": ModelPricing(0.00088, 0.00088, 130000, 4096),
            "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo": ModelPricing(0.00018, 0.00018, 131072, 65536),
            "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo": ModelPricing(0.00006, 0.00006, 131072, 16384),
            "Qwen/QwQ-32B-Preview": ModelPricing(0.00015, 0.00015, 32768, 32768),
            "Qwen/Qwen2.5-72B-Instruct-Turbo": ModelPricing(0.00012, 0.00012, 32768, 8192),
            "mistralai/Mixtral-8x22B-Instruct-v0.1": ModelPricing(0.0009, 0.0009, 65536, 65536),
            "deepseek-ai/deepseek-r1-distill-llama-70b": ModelPricing(0.00015, 0.00015, 65536, 8192),
        },
        "Fireworks": {
            "llama-3.3-70b": ModelPricing(0.0002, 0.0002, 128000, 16384),
            "llama-3.1-405b": ModelPricing(0.0009, 0.0009, 131072, 16384),
            "llama-3.1-70b": ModelPricing(0.0002, 0.0002, 131072, 16384),
            "llama-3.1-8b": ModelPricing(0.00002, 0.00002, 131072, 16384),
            "qwen2.5-72b": ModelPricing(0.0002, 0.0002, 32768, 16384),
        },
        "Groq": {
            "llama-3.3-70b-versatile": ModelPricing(0.00059, 0.00079, 128000, 32768),
            "llama-3.1-70b-versatile": ModelPricing(0.00059, 0.00079, 131072, 8000),
            "llama-3.1-8b-instant": ModelPricing(0.00005, 0.00008, 131072, 8000),
            "mixtral-8x7b-32768": ModelPricing(0.00024, 0.00024, 32768, 32768),
        },
        "xAI": {
            "grok-2-latest": ModelPricing(0.005, 0.015, 131072, 131072),
            "grok-2": ModelPricing(0.005, 0.015, 131072, 131072),
            "grok-2-mini": ModelPricing(0.001, 0.003, 131072, 65536),
        },
        "DeepSeek": {
            "deepseek-reasoner": ModelPricing(0.00014, 0.0028, 163840, 8192),
            "deepseek-chat": ModelPricing(0.00014, 0.00028, 64000, 8192),
        },
    }

    def __init__(self):
        """Initialize the calculator with optional tiktoken for accurate estimation."""
        self.tiktoken_encoder = None
        self._try_init_tiktoken()

    def _try_init_tiktoken(self):
        """Try to initialize tiktoken encoder for more accurate token counting."""
        try:
            import tiktoken

            # Use cl100k_base encoder (GPT-4/GPT-3.5-turbo tokenizer)
            self.tiktoken_encoder = tiktoken.get_encoding("cl100k_base")
            logger.debug("Tiktoken encoder initialized for accurate token counting")
        except ImportError:
            logger.debug("Tiktoken not available, using simple estimation")
        except Exception as e:
            logger.warning(f"Failed to initialize tiktoken: {e}")

    def estimate_tokens(self, text: Union[str, List[Dict[str, Any]]], method: str = "auto") -> int:
        """
        Estimate token count for text or messages.

        Args:
            text: Text string or list of message dictionaries
            method: Estimation method ("tiktoken", "simple", "auto")

        Returns:
            Estimated token count
        """
        # Convert messages to text if needed
        if isinstance(text, list):
            text = self._messages_to_text(text)

        if method == "auto":
            # Use tiktoken if available, otherwise simple
            if self.tiktoken_encoder:
                return self.estimate_tokens_tiktoken(text)
            else:
                return self.estimate_tokens_simple(text)
        elif method == "tiktoken":
            return self.estimate_tokens_tiktoken(text)
        else:
            return self.estimate_tokens_simple(text)

    def estimate_tokens_tiktoken(self, text: str) -> int:
        """
        Estimate tokens using tiktoken (OpenAI's tokenizer).
        Most accurate for OpenAI models.

        Args:
            text: Text to estimate

        Returns:
            Token count
        """
        if not self.tiktoken_encoder:
            logger.warning("Tiktoken not available, falling back to simple estimation")
            return self.estimate_tokens_simple(text)

        try:
            tokens = self.tiktoken_encoder.encode(text)
            return len(tokens)
        except Exception as e:
            logger.warning(f"Tiktoken encoding failed: {e}, using simple estimation")
            return self.estimate_tokens_simple(text)

    def estimate_tokens_simple(self, text: str) -> int:
        """
        Simple token estimation based on character/word count.
        Roughly 1 token ≈ 4 characters or 0.75 words.

        Args:
            text: Text to estimate

        Returns:
            Estimated token count
        """
        # Method 1: Character-based (1 token ≈ 4 characters)
        char_estimate = len(text) / 4

        # Method 2: Word-based (1 token ≈ 0.75 words)
        words = text.split()
        word_estimate = len(words) / 0.75

        # Take average of both methods for better accuracy
        estimate = (char_estimate + word_estimate) / 2

        return int(estimate)

    def _messages_to_text(self, messages: List[Dict[str, Any]]) -> str:
        """Convert message list to text for token estimation."""
        text_parts = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            # Handle different content types
            if isinstance(content, str):
                text_parts.append(f"{role}: {content}")
            elif isinstance(content, list):
                # Handle structured content (like Claude's format)
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            text_parts.append(f"{role}: {item.get('text', '')}")
                        elif item.get("type") == "tool_result":
                            text_parts.append(f"tool_result: {item.get('content', '')}")
                    else:
                        text_parts.append(f"{role}: {str(item)}")
            else:
                text_parts.append(f"{role}: {str(content)}")

            # Add tool calls if present
            if "tool_calls" in msg:
                tool_calls = msg["tool_calls"]
                if isinstance(tool_calls, list):
                    for call in tool_calls:
                        text_parts.append(f"tool_call: {str(call)}")

        return "\n".join(text_parts)

    def get_model_pricing(self, provider: str, model: str) -> Optional[ModelPricing]:
        """
        Get pricing information for a specific model.

        Args:
            provider: Provider name (e.g., "OpenAI", "Anthropic")
            model: Model name or identifier

        Returns:
            ModelPricing object or None if not found
        """
        # Normalize provider name
        provider = self._normalize_provider(provider)

        # Get provider pricing data
        provider_models = self.PROVIDER_PRICING.get(provider, {})

        # Try exact match first
        if model in provider_models:
            return provider_models[model]

        # Try to find by partial match
        for model_key, pricing in provider_models.items():
            if model_key.lower() in model.lower() or model.lower() in model_key.lower():
                return pricing

        # Try to infer from model name patterns
        model_lower = model.lower()

        # GPT-4 variants
        if "gpt-4o" in model_lower and "mini" in model_lower:
            return provider_models.get("gpt-4o-mini")
        elif "gpt-4o" in model_lower:
            return provider_models.get("gpt-4o")
        elif "gpt-4" in model_lower and "turbo" in model_lower:
            return provider_models.get("gpt-4-turbo")
        elif "gpt-4" in model_lower:
            return provider_models.get("gpt-4")
        elif "gpt-3.5" in model_lower:
            return provider_models.get("gpt-3.5-turbo")

        # Claude variants
        elif "claude-3-5-sonnet" in model_lower or "claude-3.5-sonnet" in model_lower:
            return provider_models.get("claude-3-5-sonnet")
        elif "claude-3-5-haiku" in model_lower or "claude-3.5-haiku" in model_lower:
            return provider_models.get("claude-3-5-haiku")
        elif "claude-3-opus" in model_lower:
            return provider_models.get("claude-3-opus")
        elif "claude-3-sonnet" in model_lower:
            return provider_models.get("claude-3-sonnet")
        elif "claude-3-haiku" in model_lower:
            return provider_models.get("claude-3-haiku")

        # Gemini variants
        elif "gemini-2" in model_lower and "flash" in model_lower:
            return provider_models.get("gemini-2.0-flash-exp")
        elif "gemini-1.5-pro" in model_lower:
            return provider_models.get("gemini-1.5-pro")
        elif "gemini-1.5-flash" in model_lower:
            return provider_models.get("gemini-1.5-flash")

        logger.debug(f"No pricing found for {provider}/{model}")
        return None

    def _normalize_provider(self, provider: str) -> str:
        """Normalize provider name for lookup."""
        provider_map = {
            "openai": "OpenAI",
            "anthropic": "Anthropic",
            "claude": "Anthropic",
            "google": "Google",
            "gemini": "Google",
            "vertex": "Google",
            "cerebras": "Cerebras",
            "cerebras ai": "Cerebras",
            "together": "Together",
            "together ai": "Together",
            "fireworks": "Fireworks",
            "fireworks ai": "Fireworks",
            "groq": "Groq",
            "xai": "xAI",
            "x.ai": "xAI",
            "grok": "xAI",
            "deepseek": "DeepSeek",
        }

        provider_lower = provider.lower()
        return provider_map.get(provider_lower, provider)

    def calculate_cost(self, input_tokens: int, output_tokens: int, provider: str, model: str) -> float:
        """
        Calculate cost for token usage.

        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            provider: Provider name
            model: Model name

        Returns:
            Estimated cost in USD
        """
        pricing = self.get_model_pricing(provider, model)

        if not pricing:
            logger.debug(f"No pricing for {provider}/{model}, returning 0")
            return 0.0

        # Calculate costs (prices are per 1000 tokens)
        input_cost = (input_tokens / 1000) * pricing.input_cost_per_1k
        output_cost = (output_tokens / 1000) * pricing.output_cost_per_1k

        total_cost = input_cost + output_cost

        logger.debug(
            f"Cost calculation for {provider}/{model}: "
            f"{input_tokens} input @ ${pricing.input_cost_per_1k}/1k = ${input_cost:.4f}, "
            f"{output_tokens} output @ ${pricing.output_cost_per_1k}/1k = ${output_cost:.4f}, "
            f"total = ${total_cost:.4f}",
        )

        return total_cost

    def update_token_usage(self, usage: TokenUsage, messages: List[Dict[str, Any]], response_content: str, provider: str, model: str) -> TokenUsage:
        """
        Update token usage with new conversation turn.

        Args:
            usage: Existing TokenUsage to update
            messages: Input messages
            response_content: Response content
            provider: Provider name
            model: Model name

        Returns:
            Updated TokenUsage object
        """
        # Estimate tokens
        input_tokens = self.estimate_tokens(messages)
        output_tokens = self.estimate_tokens(response_content)

        # Calculate cost
        cost = self.calculate_cost(input_tokens, output_tokens, provider, model)

        # Update usage
        usage.input_tokens += input_tokens
        usage.output_tokens += output_tokens
        usage.estimated_cost += cost

        return usage

    def format_cost(self, cost: float) -> str:
        """Format cost for display."""
        if cost < 0.01:
            return f"${cost:.4f}"
        elif cost < 1.0:
            return f"${cost:.3f}"
        else:
            return f"${cost:.2f}"

    def format_usage_summary(self, usage: TokenUsage) -> str:
        """Format token usage summary for display."""
        return f"Tokens: {usage.input_tokens:,} input, " f"{usage.output_tokens:,} output, " f"Cost: {self.format_cost(usage.estimated_cost)}"
