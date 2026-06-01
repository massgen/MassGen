"""Per-agent round timeout math, extracted from Orchestrator.

Pure read-only timeout calculations. Reads agent_states timeout fields,
timeout_config, and coordination_tracker via the orchestrator back-reference.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from massgen.logger_config import logger

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class OrchestratorTimeoutCalculator:
    """Compute round-timeout state and injection-skip decisions for agents."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    def should_skip_injection_due_to_timeout(self, agent_id: str) -> bool:
        """Check if mid-stream injection should be skipped due to approaching timeout.

        If the agent doesn't have enough time remaining before soft timeout to properly
        consider a new answer, it's better to skip injection and let the agent restart
        with fresh context so they get a full round to think.

        Args:
            agent_id: The agent to check

        Returns:
            True if injection should be skipped, False otherwise
        """
        orchestrator = self._orchestrator
        timeout_config = orchestrator.config.timeout_config
        round_start = orchestrator.agent_states[agent_id].round_start_time

        if round_start is None:
            return False

        current_round = orchestrator.coordination_tracker.get_agent_round(agent_id)
        if current_round == 0:
            soft_timeout = timeout_config.initial_round_timeout_seconds
        else:
            soft_timeout = timeout_config.subsequent_round_timeout_seconds

        if soft_timeout is None:
            return False

        elapsed = time.time() - round_start
        min_thinking_time = timeout_config.round_timeout_grace_seconds
        remaining = soft_timeout - elapsed

        if remaining < min_thinking_time:
            logger.info(
                f"[Orchestrator] Skipping mid-stream injection for {agent_id} - " f"only {remaining:.0f}s until soft timeout (need {min_thinking_time}s to think)",
            )
            return True

        return False

    def get_agent_timeout_state(self, agent_id: str) -> dict[str, Any] | None:
        """Get timeout state for display purposes.

        Returns timeout countdown and status information for a specific agent,
        used by TUI and WebUI to show per-agent timeout progress.
        """
        orchestrator = self._orchestrator
        state = orchestrator.agent_states.get(agent_id)
        if not state:
            return None

        timeout_config = orchestrator.config.timeout_config
        round_num = orchestrator.coordination_tracker.get_agent_round(agent_id)

        # Determine active timeout based on round
        if round_num == 0:
            active_timeout = timeout_config.initial_round_timeout_seconds
        else:
            active_timeout = timeout_config.subsequent_round_timeout_seconds

        # Calculate elapsed and remaining
        elapsed: float | None = None
        remaining_soft: float | None = None
        remaining_hard: float | None = None

        if state.round_start_time and active_timeout:
            elapsed = time.time() - state.round_start_time
            remaining_soft = max(0, active_timeout - elapsed)
            grace = timeout_config.round_timeout_grace_seconds or 0
            if state.round_timeout_state and state.round_timeout_state.soft_timeout_fired_at is not None:
                remaining_hard = max(
                    0,
                    grace - (time.time() - state.round_timeout_state.soft_timeout_fired_at),
                )
            else:
                remaining_hard = max(0, active_timeout + grace - elapsed)

        # Get soft timeout fired status from hook
        soft_timeout_fired = False
        wrap_up_requested = False
        if state.round_timeout_hooks:
            post_hook, _ = state.round_timeout_hooks
            # Access the private attribute that tracks if soft timeout fired
            soft_timeout_fired = getattr(post_hook, "_soft_timeout_fired", False)
            wrap_up_requested = soft_timeout_fired or getattr(
                post_hook,
                "_manual_wrap_up_requested",
                False,
            )
        if state.round_timeout_state and state.round_timeout_state.soft_timeout_fired_at is not None:
            soft_timeout_fired = True
            wrap_up_requested = True

        return {
            "round_number": round_num,
            "round_start_time": state.round_start_time,
            "active_timeout": active_timeout,
            "grace_seconds": timeout_config.round_timeout_grace_seconds or 0,
            "elapsed": elapsed,
            "remaining_soft": remaining_soft,
            "remaining_hard": remaining_hard,
            "wrap_up_requested": wrap_up_requested,
            "soft_timeout_fired": soft_timeout_fired,
            "soft_timeout_reason": (state.round_timeout_state.soft_timeout_reason if state.round_timeout_state else None),
            "is_hard_blocked": remaining_hard == 0 if remaining_hard is not None else False,
        }
