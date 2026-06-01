"""Agent-startup rate limiting, extracted from Orchestrator.

Owns ``_rate_limits`` and ``_agent_startup_times`` state — kept on the
orchestrator instance so any external/test monkeypatching of those
attributes continues to work — and exposes two methods (``load_from_config``
and ``apply_agent_startup_rate_limit``) that the orchestrator delegates to.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from massgen.configs.rate_limits import get_rate_limit_config
from massgen.logger_config import log_orchestrator_activity, logger

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class RateLimitController:
    """Manage per-model agent-startup rate limits.

    The mutable state (``_rate_limits`` and ``_agent_startup_times``) lives on
    the orchestrator instance, not on this collaborator, so any external code
    or test that reads/patches those attributes on the orchestrator keeps
    working unchanged. All reads/writes go through the back-reference.
    """

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    def load_from_config(self) -> dict[str, dict[str, int]]:
        """
        Load rate limits from centralized configuration file.

        Converts RPM (Requests Per Minute) values from rate_limits.yaml
        into agent startup rate limits for the orchestrator.

        Returns:
            Dictionary mapping model names to rate limit configs:
            {"model-name": {"max_starts": N, "time_window": 60}}
        """
        rate_limits: dict[str, dict[str, int]] = {}

        try:
            config = get_rate_limit_config()

            # Load Gemini models
            gemini_models = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini"]
            for model in gemini_models:
                limits = config.get_limits("gemini", model, use_defaults=True)
                rpm = limits.get("rpm")

                if rpm:
                    # Use RPM directly as max_starts for conservative limiting
                    # For very limited models (rpm <= 2), be extra conservative
                    if rpm <= 2:
                        max_starts = 1  # Very conservative for Pro (actual: 2 RPM)
                    elif rpm <= 10:
                        max_starts = max(1, rpm - 1)  # Conservative buffer
                    else:
                        max_starts = rpm

                    rate_limits[model] = {
                        "max_starts": max_starts,
                        "time_window": 60,  # Always use 60s window (1 minute)
                    }
                    logger.info(
                        f"[Orchestrator] Loaded rate limit for {model}: " f"{max_starts} starts/min (from RPM: {rpm})",
                    )

            # Fallback defaults if config loading failed
            if not rate_limits:
                logger.warning(
                    "[Orchestrator] No rate limits loaded from config, using fallback defaults",
                )
                rate_limits = {
                    "gemini-2.5-flash": {"max_starts": 9, "time_window": 60},
                    "gemini-2.5-pro": {"max_starts": 2, "time_window": 60},
                    "gemini": {"max_starts": 7, "time_window": 60},
                }

        except Exception as e:
            logger.error(f"[Orchestrator] Failed to load rate limits from config: {e}")
            # Fallback to safe defaults
            rate_limits = {
                "gemini-2.5-flash": {"max_starts": 9, "time_window": 60},
                "gemini-2.5-pro": {"max_starts": 2, "time_window": 60},
                "gemini": {"max_starts": 7, "time_window": 60},
            }

        return rate_limits

    async def apply_agent_startup_rate_limit(self, agent_id: str) -> None:
        """
        Apply rate limiting for agent startup based on model.

        Ensures that agents using rate-limited models (like Gemini Flash/Pro)
        don't exceed the allowed startup rate.

        Args:
            agent_id: ID of the agent to start
        """
        orchestrator = self._orchestrator

        # Skip rate limiting if not enabled
        if not orchestrator._enable_rate_limit:
            return

        agent = orchestrator.agents.get(agent_id)
        if not agent or not hasattr(agent, "backend"):
            return

        # Get model name from backend config
        model_key = None
        if hasattr(agent.backend, "config") and isinstance(agent.backend.config, dict):
            model_name = agent.backend.config.get("model", "")
            # Check for specific models first
            if "gemini-2.5-flash" in model_name.lower():
                model_key = "gemini-2.5-flash"
            elif "gemini-2.5-pro" in model_name.lower():
                model_key = "gemini-2.5-pro"
            elif "gemini" in model_name.lower():
                model_key = "gemini"

        # Fallback: try backend type
        if not model_key:
            if hasattr(agent.backend, "get_provider_name"):
                backend_type = agent.backend.get_provider_name()
                if backend_type in orchestrator._rate_limits:
                    model_key = backend_type

        # Check if this model has rate limits
        if not model_key or model_key not in orchestrator._rate_limits:
            return

        rate_limit = orchestrator._rate_limits[model_key]
        max_starts = rate_limit["max_starts"]
        time_window = rate_limit["time_window"]

        # Initialize tracking for this model if needed
        if model_key not in orchestrator._agent_startup_times:
            orchestrator._agent_startup_times[model_key] = []

        current_time = time.time()
        startup_times = orchestrator._agent_startup_times[model_key]

        # Remove timestamps outside the current window
        startup_times[:] = [t for t in startup_times if t > current_time - time_window]

        # If we've hit the limit, wait until the oldest startup falls outside the window
        if len(startup_times) >= max_starts:
            oldest_time = startup_times[0]
            wait_time = (oldest_time + time_window) - current_time

            if wait_time > 0:
                log_orchestrator_activity(
                    orchestrator.orchestrator_id,
                    f"Rate limit reached for {model_key}",
                    {
                        "agent_id": agent_id,
                        "model": model_key,
                        "current_starts": len(startup_times),
                        "max_starts": max_starts,
                        "time_window": time_window,
                        "wait_time": round(wait_time, 2),
                    },
                )
                logger.info(
                    f"[Orchestrator] Rate limit: {len(startup_times)}/{max_starts} {model_key} agents " f"started in {time_window}s window. Waiting {wait_time:.2f}s before starting {agent_id}...",
                )

                await asyncio.sleep(wait_time)

                # After waiting, clean up old timestamps again
                current_time = time.time()
                startup_times[:] = [t for t in startup_times if t > current_time - time_window]

        # Record this startup
        startup_times.append(time.time())

        log_orchestrator_activity(
            orchestrator.orchestrator_id,
            "Agent startup allowed",
            {
                "agent_id": agent_id,
                "model": model_key,
                "current_starts": len(startup_times),
                "max_starts": max_starts,
            },
        )

        # Add mandatory cooldown after startup to prevent burst API calls
        # This gives the backend rate limiter time to properly queue requests
        cooldown_delays = {
            "gemini-2.5-flash": 3.0,  # 3 second cooldown between Flash agent starts
            "gemini-2.5-pro": 10.0,  # 10 second cooldown between Pro agent starts (very limited!)
            "gemini": 5.0,  # 5 second default cooldown
        }

        if model_key in cooldown_delays:
            cooldown = cooldown_delays[model_key]
            logger.info(
                f"[Orchestrator] Applying {cooldown}s cooldown after starting {agent_id} ({model_key})",
            )
            await asyncio.sleep(cooldown)
