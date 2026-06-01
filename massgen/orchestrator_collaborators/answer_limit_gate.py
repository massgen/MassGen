"""Answer-count limit gating, extracted from Orchestrator.

Owns the per-agent and global answer-count limit checks plus the
decomposition auto-stop side effect. All shared state (agent_states,
coordination_tracker, config) is reached through the orchestrator
back-reference so any direct ``orch.agent_states[...]`` access elsewhere
(e.g. the streaming loop, FairnessGate, peer answer visibility) stays
consistent.

The thin delegator methods on :class:`massgen.orchestrator.Orchestrator`
preserve the public surface (``_is_vote_only_mode``,
``_apply_decomposition_auto_stop_if_needed``) and the shared helpers
(``_terminal_action_wording``, ``_is_hard_timeout_active``,
``_get_agent_answer_count_for_limit``) that FairnessGate and other
not-yet-extracted collaborators still call through the orchestrator.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from massgen.logger_config import logger
from massgen.utils import AgentStatus

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class AnswerLimitGate:
    """Coordinator for per-agent / global answer-count enforcement."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    # ------------------------------------------------------------------
    # Shared helpers (also called by FairnessGate via orch delegators)
    # ------------------------------------------------------------------
    def terminal_action_wording(self) -> str:
        """Return mode-specific terminal action guidance for error messaging."""
        if self._orchestrator._is_decomposition_mode():
            return "call `stop`"
        return "vote for an existing answer"

    def is_hard_timeout_active(self, agent_id: str) -> bool:
        """Return True when hard timeout is currently active for an agent."""
        orch = self._orchestrator
        state = orch.agent_states.get(agent_id)
        if not state:
            return False

        timeout_config = getattr(orch.config, "timeout_config", None)
        if timeout_config is None:
            return False

        grace_seconds = timeout_config.round_timeout_grace_seconds or 0
        shared_timeout_state = state.round_timeout_state
        if shared_timeout_state and shared_timeout_state.soft_timeout_fired_at is not None:
            return (time.time() - shared_timeout_state.soft_timeout_fired_at) >= grace_seconds

        if state.round_start_time is None:
            return False

        current_round = orch.coordination_tracker.get_agent_round(agent_id)
        if current_round == 0:
            soft_timeout = timeout_config.initial_round_timeout_seconds
        else:
            soft_timeout = timeout_config.subsequent_round_timeout_seconds
        if soft_timeout is None:
            return False

        elapsed = time.time() - state.round_start_time
        return elapsed >= (soft_timeout + grace_seconds)

    def get_agent_answer_count_for_limit(self, agent_id: str) -> int:
        """Get answer count used for per-agent answer limit enforcement."""
        orch = self._orchestrator
        if orch._is_decomposition_mode():
            state = orch.agent_states.get(agent_id)
            if state:
                return state.decomposition_answer_streak
        return len(orch.coordination_tracker.answers_by_agent.get(agent_id, []))

    def get_total_answer_count(self) -> int:
        """Get total number of answer revisions across all agents."""
        return sum(len(answer_revisions) for answer_revisions in self._orchestrator.coordination_tracker.answers_by_agent.values())

    def is_global_answer_limit_reached(self) -> bool:
        """Check whether the optional global answer cap has been reached."""
        global_limit = getattr(self._orchestrator.config, "max_new_answers_global", None)
        if global_limit is None:
            return False
        return self.get_total_answer_count() >= global_limit

    # ------------------------------------------------------------------
    # Primary limit checks
    # ------------------------------------------------------------------
    def check_answer_count_limit(self, agent_id: str) -> tuple[bool, str | None]:
        """Check if agent has reached their answer count limit."""
        orch = self._orchestrator
        is_decomposition = orch._is_decomposition_mode()

        # Enforce optional global cap first.
        if self.is_global_answer_limit_reached():
            total_answer_count = self.get_total_answer_count()
            global_limit = orch.config.max_new_answers_global
            if is_decomposition:
                error_msg = f"The global maximum of {global_limit} new answer(s) has been reached " "across all agents. Please call `stop` to signal you are done."
            else:
                error_msg = f"The global maximum of {global_limit} new answer(s) has been reached " "across all agents. Please vote for the best existing answer using the `vote` tool."
            logger.info(
                "[Orchestrator] Answer rejected: global answer limit reached (%s/%s), attempted by %s",
                total_answer_count,
                global_limit,
                agent_id,
            )
            return (False, error_msg)

        if orch.config.max_new_answers_per_agent is not None:
            answer_count = self.get_agent_answer_count_for_limit(agent_id)

            if answer_count >= orch.config.max_new_answers_per_agent:
                if is_decomposition:
                    error_msg = (
                        f"You've reached the maximum of {orch.config.max_new_answers_per_agent} "
                        "consecutive new answer(s) without seeing external updates. "
                        "Please call `stop` to signal you are done."
                    )
                else:
                    error_msg = f"You've reached the maximum of {orch.config.max_new_answers_per_agent} " "new answer(s). Please vote for the best existing answer using the `vote` tool."
                logger.info(
                    "[Orchestrator] Answer rejected: %s has reached per-agent limit (%s/%s)",
                    agent_id,
                    answer_count,
                    orch.config.max_new_answers_per_agent,
                )
                return (False, error_msg)

        fairness_ok, fairness_error = orch._check_fairness_answer_lead_cap(agent_id)
        if not fairness_ok:
            return (False, fairness_error)

        return (True, None)

    def is_vote_only_mode(self, agent_id: str) -> bool:
        """Check if agent has exhausted their answer limit and must vote (or auto-stop).

        LOAD-BEARING SIDE EFFECT: in decomposition mode, sets has_voted /
        stop_summary / stop_status on agent_states[agent_id] AND calls
        coordination_tracker.add_agent_stop. This is relied on by
        _apply_decomposition_auto_stop_if_needed; preserved byte-for-byte.
        """
        orch = self._orchestrator
        per_agent_limit = orch.config.max_new_answers_per_agent
        answer_count = self.get_agent_answer_count_for_limit(agent_id)
        hit_answer_limit = per_agent_limit is not None and answer_count >= per_agent_limit
        hit_global_limit = self.is_global_answer_limit_reached()

        if not hit_answer_limit and not hit_global_limit:
            return False

        # Decomposition mode: auto-stop the agent instead of switching to vote-only
        if orch._is_decomposition_mode():
            if not orch.agent_states[agent_id].has_voted:
                last_answer = orch.agent_states[agent_id].answer or ""
                if hit_global_limit:
                    total_answers = self.get_total_answer_count()
                    global_limit = orch.config.max_new_answers_global
                    stop_reason = f"reached global answer limit ({total_answers}/{global_limit})"
                else:
                    stop_reason = f"reached per-agent consecutive answer limit ({answer_count}/{per_agent_limit})"
                orch.agent_states[agent_id].has_voted = True
                orch.agent_states[agent_id].stop_summary = f"Auto-stopped: {stop_reason}. Last work: {last_answer[:200]}"
                orch.agent_states[agent_id].stop_status = "complete"
                orch.coordination_tracker.add_agent_stop(
                    agent_id,
                    {"summary": orch.agent_states[agent_id].stop_summary, "status": "complete"},
                )
                logger.info(
                    "[Orchestrator] Auto-stopped agent %s in decomposition mode (%s)",
                    agent_id,
                    stop_reason,
                )
            return False  # Don't switch to vote-only tools, agent is already stopped

        if orch._should_skip_vote_rounds_for_synthesize():
            return False

        # If defer_voting_until_all_answered is enabled, also check that all agents have answered
        # unless global answer cap has already been reached.
        if orch.config.defer_voting_until_all_answered and not hit_global_limit:
            all_answered = all(state.answer is not None for state in orch.agent_states.values())
            if not all_answered:
                return False

        return True

    def apply_decomposition_auto_stop_if_needed(self, agent_id: str) -> bool:
        """Apply decomposition auto-stop gate after refreshing answer visibility."""
        orch = self._orchestrator
        if not orch._is_decomposition_mode():
            return False

        state = orch.agent_states[agent_id]
        orch._sync_decomposition_answer_visibility(agent_id)

        was_voted = state.has_voted
        self.is_vote_only_mode(agent_id)  # applies decomposition auto-stop side effect
        if not was_voted and state.has_voted:
            orch.coordination_tracker.change_status(agent_id, AgentStatus.STOPPED)
            logger.info(
                f"[Orchestrator] Skipping execution for {agent_id} (auto-stopped at answer limit)",
            )

        return state.has_voted

    def is_waiting_for_all_answers(self, agent_id: str) -> bool:
        """Check if agent is waiting for all agents to answer before voting."""
        orch = self._orchestrator
        if not orch.config.defer_voting_until_all_answered and not orch._should_skip_vote_rounds_for_synthesize():
            return False

        if self.is_global_answer_limit_reached():
            return False

        if orch.config.max_new_answers_per_agent is None:
            return False

        answer_count = self.get_agent_answer_count_for_limit(agent_id)
        hit_answer_limit = answer_count >= orch.config.max_new_answers_per_agent

        if not hit_answer_limit:
            return False

        all_answered = all(state.answer is not None or state.is_killed for state in orch.agent_states.values())
        if all_answered:
            return False

        if orch._should_skip_vote_rounds_for_synthesize():
            logger.debug(
                f"[synthesize] {agent_id} waiting for all agents to answer before final presentation",
            )
        else:
            logger.debug(
                f"[defer_voting] {agent_id} waiting for all agents to answer before voting",
            )
        return True
