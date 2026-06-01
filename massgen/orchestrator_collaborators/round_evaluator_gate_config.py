"""Round-evaluator gate config/helper accessors, extracted from Orchestrator."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class RoundEvaluatorGateConfig:
    """Config/helper accessors for the orchestrator-managed round-evaluator gate.

    Holds a back-reference to the orchestrator. The shared-state attribute
    ``_pending_evaluator_personas`` is ALSO touched by ChecklistGateManager, so
    this collaborator must read/write the orchestrator's attributes directly via
    the back-reference, never a local copy.
    """

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    def is_round_evaluator_gate_enabled(self) -> bool:
        """Return whether the orchestrator should run the round_evaluator gate itself."""
        coord = getattr(self._orchestrator.config, "coordination_config", None)
        return bool(
            coord and getattr(coord, "round_evaluator_before_checklist", False) and getattr(coord, "orchestrator_managed_round_evaluator", False),
        )

    def get_evaluator_team_size(self) -> int:
        """Return the number of evaluator subagents in the shared child team."""
        coord = getattr(self._orchestrator.config, "coordination_config", None)
        sub_orch = getattr(coord, "subagent_orchestrator", None) if coord else None
        if sub_orch is None:
            return 0
        if isinstance(sub_orch, dict):
            agents = sub_orch.get("agents", [])
        else:
            agents = getattr(sub_orch, "agents", None) or []
        return len(agents)

    def validate_evaluator_personas(self, personas: Any) -> str | None:
        """Validate evaluator personas input. Return error string or None if valid."""
        if not isinstance(personas, list):
            return "personas must be a list"
        expected = self.get_evaluator_team_size()
        if len(personas) == 0:
            return f"personas list is empty; expected {expected} persona(s)"
        if len(personas) != expected:
            return f"Expected {expected} persona(s) to match evaluator team size, got {len(personas)}"
        for i, p in enumerate(personas):
            if not isinstance(p, dict):
                return f"Persona at index {i} must be an object with 'label' and 'instructions'"
            if "label" not in p:
                return f"Persona at index {i} is missing required 'label' field"
            if "instructions" not in p:
                return f"Persona at index {i} is missing required 'instructions' field"
            if not str(p.get("label", "")).strip():
                return f"Persona at index {i} has empty label"
            if not str(p.get("instructions", "")).strip():
                return f"Persona at index {i} has empty instructions"
        return None

    def consume_evaluator_personas(self) -> list[dict[str, str]] | None:
        """Consume pending evaluator personas, falling back to last used set.

        Returns the personas to use for the current round evaluator spawn,
        or None if no personas are configured.
        """
        orchestrator = self._orchestrator
        if orchestrator._pending_evaluator_personas is not None:
            consumed = orchestrator._pending_evaluator_personas
            orchestrator._last_evaluator_personas = consumed
            orchestrator._pending_evaluator_personas = None
            return consumed
        if orchestrator._last_evaluator_personas is not None:
            return orchestrator._last_evaluator_personas
        return None

    def get_round_evaluator_latest_labels(self, answers: dict[str, str]) -> tuple[str, ...]:
        """Return the latest answer labels for the current revision set."""
        labels: list[str] = []
        for answering_agent_id in sorted(answers.keys()):
            label = self._orchestrator.coordination_tracker.get_latest_answer_label(answering_agent_id)
            if label:
                labels.append(label)
        return tuple(labels)

    def get_round_evaluator_upcoming_round(self, agent_id: str) -> int:
        """Return the next user-facing round number for programmatic tool events."""
        try:
            restart_count = self._orchestrator.agent_states[agent_id].restart_count
        except Exception:
            restart_count = 0
        try:
            return max(1, int(restart_count) + 1)
        except Exception:
            return 1

    def get_round_evaluator_display_round(self, agent_id: str) -> int:
        """Attach round-evaluator tool cards to the completed parent round they analyze."""
        try:
            return max(1, int(self._orchestrator.coordination_tracker.get_agent_round(agent_id)))
        except Exception:
            return 1
