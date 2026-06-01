"""Evaluation criteria generation and persistence, extracted from Orchestrator.

This collaborator owns the methods that generate task-specific evaluation
criteria via a pre-collab subagent run, persist them to log, and expose them
for cross-turn persistence. The Orchestrator keeps thin delegator methods so
all existing call sites (including monkeypatches in tests) keep working.

Note on shared state:
    ``self._orchestrator._generated_evaluation_criteria`` is the single source
    of truth. It is also read by :class:`ChecklistGateManager` and
    :class:`CriteriaEvolutionRunner`; this collaborator mutates it on the
    orchestrator so all three observe the live value.

Note on imports:
    Cross-method helpers (e.g. ``get_log_session_dir``) are resolved lazily
    through :mod:`massgen.orchestrator` so test patches at that namespace
    apply -- mirroring the precedent in :class:`PersonaInjector`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from massgen.logger_config import logger

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class EvaluationCriteriaGeneratorCollaborator:
    """Owns evaluation criteria generation, log persistence, and lookup."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    async def generate_and_inject_evaluation_criteria(self) -> None:
        """Generate task-specific evaluation criteria via a pre-collab subagent run."""
        orch = self._orchestrator
        if not hasattr(orch.config, "coordination_config"):
            return
        if not hasattr(orch.config.coordination_config, "evaluation_criteria_generator"):
            return
        if not orch.config.coordination_config.evaluation_criteria_generator.enabled:
            logger.info("[Orchestrator] Evaluation criteria generation disabled in config")
            return
        if orch._evaluation_criteria_generated:
            logger.info("[Orchestrator] Evaluation criteria already generated, skipping")
            return

        logger.info("[Orchestrator] Generating evaluation criteria via subagent")

        display = getattr(orch.coordination_ui, "display", None) if orch.coordination_ui else None
        anchor_agent = next(iter(orch.agents.keys()), None)
        call_id = "criteria_generation_criteria_generation"

        try:
            from massgen.evaluation_criteria_generator import (
                EvaluationCriteriaGenerator,
            )

            ecg = orch.config.coordination_config.evaluation_criteria_generator
            generator = EvaluationCriteriaGenerator()

            has_changedoc = getattr(
                orch.config.coordination_config,
                "enable_changedoc",
                False,
            )

            criteria = await generator.generate_criteria_via_subagent(
                task=orch.current_task or "",
                agent_configs=orch._build_parent_agent_configs(),
                has_changedoc=has_changedoc,
                parent_workspace=orch._get_parent_workspace("massgen_criteria_"),
                log_directory=orch._get_log_directory(),
                orchestrator_id=orch.orchestrator_id,
                min_criteria=ecg.min_criteria,
                max_criteria=ecg.max_criteria,
                on_subagent_started=orch._make_precollab_started_callback(
                    anchor_agent,
                    call_id,
                    display,
                ),
                voting_sensitivity=getattr(orch.config, "voting_sensitivity", None),
                voting_threshold=orch._get_pre_collab_voting_threshold(),
                has_planning_spec_context=bool(orch._plan_session_id),
                fast_iteration_mode=orch._get_fast_iteration_mode(),
            )

            orch._generated_evaluation_criteria = criteria
            orch._evaluation_criteria_generated = True

            # Re-initialize checklist tool now that generated criteria are available.
            orch._init_checklist_tool()
            # Route through orchestrator so monkeypatches of
            # ``_save_evaluation_criteria_to_log`` are honored.
            orch._save_evaluation_criteria_to_log(criteria)

            source = generator.last_generation_source
            logger.info(
                f"[Orchestrator] Generated {len(criteria)} evaluation criteria (source: {source})",
            )

            crit_preview = " | ".join(f"{c.id}: {c.text[:60]}..." if len(c.text) > 60 else f"{c.id}: {c.text}" for c in criteria[:3])
            if source == "subagent":
                orch._notify_precollab_completed(
                    anchor_agent,
                    "criteria_generation",
                    call_id,
                    display,
                    answer_preview=crit_preview or f"{len(criteria)} criteria generated.",
                )
            else:
                # Loud signal: a fallback means domain-specific generation did NOT
                # succeed and the run is using GENERIC criteria, which flattens the
                # evaluation gradient. Make this unmistakable rather than neutral.
                logger.warning(
                    "[Orchestrator] Evaluation criteria FELL BACK to %d generic defaults " "(domain-specific generation did not produce usable criteria; " "output quality may suffer).",
                    len(criteria),
                )
                orch._notify_precollab_completed(
                    anchor_agent,
                    "criteria_generation",
                    call_id,
                    display,
                    answer_preview=f"⚠ Generation failed — using {len(criteria)} GENERIC fallback criteria (quality may suffer).",
                )

        except Exception as e:
            logger.error(f"[Orchestrator] Failed to generate evaluation criteria: {e}")
            logger.warning("[Orchestrator] Continuing without criteria generation")
            orch._evaluation_criteria_generated = True  # Don't retry on failure
            orch._notify_precollab_completed(
                anchor_agent,
                "criteria_generation",
                call_id,
                display,
                status="failed",
                error=str(e),
            )

    def save_evaluation_criteria_to_log(self, criteria: list) -> None:
        """Save generated evaluation criteria to a YAML file in the log directory."""
        try:
            import yaml

            # Lazy lookup so test patches of
            # ``massgen.orchestrator.get_log_session_dir`` apply.
            from massgen import orchestrator as _orch_mod

            log_dir = _orch_mod.get_log_session_dir()
            criteria_file = log_dir / "generated_evaluation_criteria.yaml"
            criteria_data = [{"id": c.id, "text": c.text, "category": c.category, **({"verify_by": c.verify_by} if c.verify_by else {})} for c in criteria]
            with open(criteria_file, "w") as f:
                yaml.dump(criteria_data, f, default_flow_style=False)
            logger.info(f"[Orchestrator] Saved evaluation criteria to {criteria_file}")
        except Exception as e:
            logger.debug(f"[Orchestrator] Failed to save evaluation criteria to log: {e}")

    def get_generated_evaluation_criteria(self) -> list | None:
        """Get the generated evaluation criteria for persistence across turns.

        Returns:
            List of GeneratedCriterion objects, or None if not generated.
        """
        return self._orchestrator._generated_evaluation_criteria
