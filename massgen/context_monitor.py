# -*- coding: utf-8 -*-
"""
Context Window Monitoring Utility

Provides logging and tracking for context window usage during agent execution.
Helps debug memory and token management by showing real-time context usage.
"""

from typing import Any, Dict, List, Optional

from .logger_config import logger
from .token_manager.token_manager import TokenCostCalculator


class ContextWindowMonitor:
    """Monitor and log context window usage during agent execution."""

    def __init__(
        self,
        model_name: str,
        provider: str = "openai",
        trigger_threshold: float = 0.75,
        target_ratio: float = 0.40,
        enabled: bool = True,
    ):
        """
        Initialize context window monitor.

        Args:
            model_name: Name of the model (e.g., "gpt-4o-mini")
            provider: Provider name (e.g., "openai", "anthropic")
            trigger_threshold: Percentage (0-1) at which to warn about context usage
            target_ratio: Target percentage after compression
            enabled: Whether to enable logging
        """
        self.model_name = model_name
        self.provider = provider
        self.trigger_threshold = trigger_threshold
        self.target_ratio = target_ratio
        self.enabled = enabled

        # Get model pricing info to determine context window size
        self.calculator = TokenCostCalculator()
        self.pricing = self.calculator.get_model_pricing(provider, model_name)

        if self.pricing and self.pricing.context_window:
            self.context_window = self.pricing.context_window
        else:
            # Default fallbacks
            self.context_window = 128000  # Common default
            logger.warning(
                f"Could not determine context window for {provider}/{model_name}, " f"using default {self.context_window}",
            )

        # Tracking
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.turn_count = 0

    def log_context_usage(
        self,
        messages: List[Dict[str, Any]],
        turn_number: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Log current context window usage.

        Args:
            messages: Current conversation messages
            turn_number: Optional turn number to display

        Returns:
            Dict with usage stats: {
                "current_tokens": int,
                "max_tokens": int,
                "usage_percent": float,
                "should_compress": bool,
                "target_tokens": int
            }
        """
        if not self.enabled:
            return {}

        # Estimate tokens in current context
        current_tokens = self.calculator.estimate_tokens(messages)
        usage_percent = current_tokens / self.context_window
        should_compress = usage_percent >= self.trigger_threshold
        target_tokens = int(self.context_window * self.target_ratio)

        # Build log message
        turn_str = f" (Turn {turn_number})" if turn_number is not None else ""
        status_emoji = "📊"

        if usage_percent >= self.trigger_threshold:
            status_emoji = "⚠️"
            logger.warning(
                f"{status_emoji} Context Window{turn_str}: " f"{current_tokens:,} / {self.context_window:,} tokens " f"({usage_percent*100:.1f}%) - Approaching limit!",
            )
            logger.warning(
                f"   Compression threshold reached. Target after compression: " f"{target_tokens:,} tokens ({self.target_ratio*100:.0f}%)",
            )
        elif usage_percent >= 0.50:
            logger.info(
                f"{status_emoji} Context Window{turn_str}: " f"{current_tokens:,} / {self.context_window:,} tokens " f"({usage_percent*100:.1f}%)",
            )
        else:
            logger.info(
                f"{status_emoji} Context Window{turn_str}: " f"{current_tokens:,} / {self.context_window:,} tokens " f"({usage_percent*100:.1f}%)",
            )

        return {
            "current_tokens": current_tokens,
            "max_tokens": self.context_window,
            "usage_percent": usage_percent,
            "should_compress": should_compress,
            "target_tokens": target_tokens,
            "trigger_threshold": self.trigger_threshold,
            "target_ratio": self.target_ratio,
        }

    def log_turn_summary(
        self,
        input_tokens: int,
        output_tokens: int,
        turn_number: Optional[int] = None,
    ):
        """
        Log summary for a single turn.

        Args:
            input_tokens: Input tokens for this turn
            output_tokens: Output tokens for this turn
            turn_number: Optional turn number
        """
        if not self.enabled:
            return

        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        self.turn_count += 1

        turn_str = f" {turn_number}" if turn_number is not None else f" {self.turn_count}"

        logger.info(
            f"Turn{turn_str} tokens: {input_tokens:,} input + {output_tokens:,} output = " f"{input_tokens + output_tokens:,} total",
        )

    def log_session_summary(self):
        """Log overall session summary."""
        if not self.enabled or self.turn_count == 0:
            return

        total_tokens = self.total_input_tokens + self.total_output_tokens
        avg_per_turn = total_tokens / self.turn_count if self.turn_count > 0 else 0

        logger.info("=" * 70)
        logger.info("📊 Session Summary:")
        logger.info(f"   Total turns: {self.turn_count}")
        logger.info(f"   Total input tokens: {self.total_input_tokens:,}")
        logger.info(f"   Total output tokens: {self.total_output_tokens:,}")
        logger.info(f"   Total tokens: {total_tokens:,}")
        logger.info(f"   Average per turn: {avg_per_turn:,.0f} tokens")
        logger.info(f"   Context window: {self.context_window:,} tokens")
        logger.info(f"   Peak usage: {(total_tokens/self.context_window)*100:.1f}%")
        logger.info("=" * 70)

    def get_stats(self) -> Dict[str, Any]:
        """Get current monitoring stats."""
        total_tokens = self.total_input_tokens + self.total_output_tokens

        return {
            "turn_count": self.turn_count,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": total_tokens,
            "context_window": self.context_window,
            "avg_tokens_per_turn": total_tokens / self.turn_count if self.turn_count > 0 else 0,
            "peak_usage_percent": total_tokens / self.context_window if self.context_window > 0 else 0,
        }


def create_monitor_from_config(
    config: Dict[str, Any],
    model_name: str,
    provider: str = "openai",
) -> ContextWindowMonitor:
    """
    Create a context window monitor from YAML config.

    Args:
        config: Config dict (should have 'memory' section)
        model_name: Model name
        provider: Provider name

    Returns:
        ContextWindowMonitor instance
    """
    memory_config = config.get("memory", {})
    compression_config = memory_config.get("compression", {})

    trigger_threshold = compression_config.get("trigger_threshold", 0.75)
    target_ratio = compression_config.get("target_ratio", 0.40)
    enabled = memory_config.get("enabled", True)

    return ContextWindowMonitor(
        model_name=model_name,
        provider=provider,
        trigger_threshold=trigger_threshold,
        target_ratio=target_ratio,
        enabled=enabled,
    )
