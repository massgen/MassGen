"""Read-only run-mode strategy predicates, extracted from Orchestrator."""

from __future__ import annotations

from typing import TYPE_CHECKING

from massgen.logger_config import logger

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class RunModeStrategyResolver:
    """Read-only strategy predicates for the current run.

    Holds a back-reference to the orchestrator and reads from ``config`` and
    ``agents`` only. Performs no mutation. Delegates decomposition-mode checks
    back to the orchestrator so the single source of truth is preserved.
    """

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    def is_round_learning_capture_enabled(self) -> bool:
        """Return whether round-time learning capture should be enabled.

        In ``final_only`` mode, if final presentation is skipped (refinement-off
        flow), we must fall back to round-time capture because there is no later
        presenter stage to write evolving skills or memories.
        """
        config = self._orchestrator.config
        coordination_config = getattr(config, "coordination_config", None)
        learning_capture_mode = getattr(
            coordination_config,
            "learning_capture_mode",
            "round",
        )
        if learning_capture_mode == "round":
            return True
        if learning_capture_mode == "final_only":
            disable_fallback = getattr(
                coordination_config,
                "disable_final_only_round_capture_fallback",
                False,
            )
            if disable_fallback is True:
                return False
            return not self.expects_final_presentation_stage()
        return False

    def get_final_answer_strategy(self) -> str:
        """Return the effective final-answer strategy for the current run."""
        config = self._orchestrator.config
        configured_strategy = getattr(config, "final_answer_strategy", None)
        valid_strategies = {"winner_reuse", "winner_present", "synthesize"}
        if configured_strategy in valid_strategies:
            return configured_strategy
        if configured_strategy is not None:
            logger.warning(
                f"[Orchestrator] Unknown final_answer_strategy={configured_strategy!r}; falling back to legacy behavior",
            )
        if getattr(config, "skip_final_presentation", False):
            return "winner_reuse"
        return "winner_present"

    def expects_final_presentation_stage(self) -> bool:
        """Return whether the current config expects an explicit presenter stage."""
        config = self._orchestrator.config
        if getattr(config, "coordination_mode", "voting") == "decomposition":
            return True
        if not getattr(config, "skip_final_presentation", False):
            return True
        if getattr(config, "skip_voting", False):
            return False
        return self.get_final_answer_strategy() in {"winner_present", "synthesize"}

    def should_skip_vote_rounds_for_synthesize(self) -> bool:
        """Return whether quick multi-agent synthesize runs should skip vote rounds."""
        orchestrator = self._orchestrator
        config = orchestrator.config
        if orchestrator._is_decomposition_mode():
            return False
        if len(orchestrator.agents) <= 1:
            return False
        if self.get_final_answer_strategy() != "synthesize":
            return False
        # Don't skip voting when defer_voting is set — it implies
        # the caller wants a produce-then-vote (ensemble) pattern.
        if getattr(config, "defer_voting_until_all_answered", False):
            return False
        return getattr(config, "max_new_answers_per_agent", None) == 1

    def is_round_verification_capture_enabled(self) -> bool:
        """Return whether round-time verification replay capture should be enabled."""
        if self.is_round_learning_capture_enabled():
            return True

        coordination_config = getattr(self._orchestrator.config, "coordination_config", None)
        learning_capture_mode = getattr(
            coordination_config,
            "learning_capture_mode",
            "round",
        )
        return learning_capture_mode == "verification_and_final_only"
