"""Fairness gating, extracted from Orchestrator.

Owns the per-agent log-state dicts (``_fairness_pause_log_reasons`` and
``_fairness_block_log_states``). These attributes are still initialised on the
Orchestrator in ``__init__`` and are mutated through the orchestrator
back-ref so the lazily-constructed collaborator stays consistent with any
direct access that happens before its ``cached_property`` is touched.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from massgen.logger_config import logger

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class FairnessGate:
    """Coordinator for fairness gating + log-state bookkeeping."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    def is_fairness_enabled(self) -> bool:
        return bool(getattr(self._orchestrator.config, "fairness_enabled", True))

    def update_fairness_pause_log_state(
        self,
        agent_id: str,
        is_paused: bool,
        pause_reason: str | None,
    ) -> None:
        orch = self._orchestrator
        if is_paused:
            reason = pause_reason or "waiting for peers"
            if orch._fairness_pause_log_reasons.get(agent_id) == reason:
                return
            orch._fairness_pause_log_reasons[agent_id] = reason
            logger.info(
                f"[Orchestrator] Pausing {agent_id} before round start due to fairness gate: {reason}",
            )
            return

        if agent_id in orch._fairness_pause_log_reasons:
            orch._fairness_pause_log_reasons.pop(agent_id, None)
            logger.info(
                f"[Orchestrator] Fairness gate cleared for {agent_id}; resuming round starts",
            )

    def log_fairness_answer_lead_block(
        self,
        agent_id: str,
        projected_lead: int,
        lead_cap: int,
    ) -> None:
        orch = self._orchestrator
        block_state = (projected_lead, lead_cap)
        if orch._fairness_block_log_states.get(agent_id) == block_state:
            return
        orch._fairness_block_log_states[agent_id] = block_state
        logger.info(
            f"[Orchestrator] Fairness gate blocked new_answer for {agent_id} " f"(projected_lead={projected_lead}, cap={lead_cap})",
        )

    def clear_fairness_answer_lead_block_log(self, agent_id: str) -> None:
        self._orchestrator._fairness_block_log_states.pop(agent_id, None)

    def get_active_fairness_agents(self) -> list[str]:
        active_agents: list[str] = []
        for aid, state in self._orchestrator.agent_states.items():
            if state.is_killed or state.has_voted:
                continue
            active_agents.append(aid)
        return active_agents

    def check_fairness_answer_lead_cap(self, agent_id: str) -> tuple[bool, str | None]:
        orch = self._orchestrator
        if not self.is_fairness_enabled():
            self.clear_fairness_answer_lead_block_log(agent_id)
            return (True, None)

        lead_cap = getattr(orch.config, "fairness_lead_cap_answers", 1)
        if lead_cap is None:
            self.clear_fairness_answer_lead_block_log(agent_id)
            return (True, None)

        active_agents = self.get_active_fairness_agents()
        if agent_id not in active_agents or len(active_agents) <= 1:
            self.clear_fairness_answer_lead_block_log(agent_id)
            return (True, None)

        peer_counts = [orch._get_agent_answer_revision_count(aid) for aid in active_agents if aid != agent_id]
        if not peer_counts:
            self.clear_fairness_answer_lead_block_log(agent_id)
            return (True, None)

        current_count = orch._get_agent_answer_revision_count(agent_id)
        projected_lead = (current_count + 1) - min(peer_counts)

        if projected_lead <= lead_cap:
            self.clear_fairness_answer_lead_block_log(agent_id)
            return (True, None)

        terminal_action = orch._terminal_action_wording()
        error_msg = (
            f"Fairness lead cap reached: submitting another `new_answer` would put you {projected_lead} answer(s) "
            f"ahead of the slowest active peer (cap={lead_cap}). Please wait for peers to catch up or {terminal_action}."
        )
        self.log_fairness_answer_lead_block(
            agent_id,
            projected_lead,
            lead_cap,
        )
        return (False, error_msg)

    def should_pause_agent_for_fairness(self, agent_id: str) -> tuple[bool, str | None]:
        orch = self._orchestrator
        if not self.is_fairness_enabled():
            return (False, None)
        if orch.config.disable_injection:
            return (False, None)

        state = orch.agent_states.get(agent_id)
        if not state or state.has_voted or state.is_killed:
            return (False, None)

        if orch._get_agent_answer_revision_count(agent_id) == 0:
            return (False, None)

        if orch._is_hard_timeout_active(agent_id):
            return (False, None)

        fairness_ok, fairness_error = self.check_fairness_answer_lead_cap(agent_id)
        if fairness_ok:
            return (False, None)
        return (True, fairness_error)
