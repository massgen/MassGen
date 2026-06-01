"""Prompt improvement pre-collab pass, extracted from Orchestrator.

This collaborator owns the async ``_improve_and_inject_prompt`` flow that
runs a subagent consensus pass to refine the user task prompt before
collaboration begins. The orchestrator keeps a thin delegator so existing
call sites and test monkeypatches continue to work.

Naming: the class is :class:`PromptImproverCollaborator` to avoid clashing
with :class:`massgen.prompt_improver.PromptImprover`, which is the underlying
engine this collaborator wraps.

Note on shared state:
    Mutations to ``_prompt_improved`` and ``current_task`` are written back
    onto ``self._orchestrator`` so all observers see the live values. This
    collaborator never keeps local copies.

Note on imports:
    ``get_log_session_dir`` is patched at the :mod:`massgen.orchestrator`
    namespace by some tests; this collaborator does not invoke it directly,
    but it follows the same lazy-import precedent for orchestrator helpers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from massgen.logger_config import logger

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class PromptImproverCollaborator:
    """Owns the pre-collab prompt-improvement pass."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    async def improve_and_inject_prompt(self) -> None:
        """Improve the task prompt via a pre-collab subagent consensus run."""
        orch = self._orchestrator
        if not hasattr(orch.config, "coordination_config"):
            return
        if not hasattr(orch.config.coordination_config, "prompt_improver"):
            return
        if not orch.config.coordination_config.prompt_improver.enabled:
            return
        if orch._prompt_improved:
            logger.info("[Orchestrator] Prompt already improved, skipping")
            return

        logger.info("[Orchestrator] Improving prompt via subagent")

        display = getattr(orch.coordination_ui, "display", None) if orch.coordination_ui else None
        anchor_agent = next(iter(orch.agents.keys()), None)
        call_id = "prompt_improvement_prompt_improvement"

        try:
            from massgen.prompt_improver import PromptImprover

            improver = PromptImprover()

            improved = await improver.improve_prompt_via_subagent(
                task=orch.current_task or "",
                agent_configs=orch._build_parent_agent_configs(),
                parent_workspace=orch._get_parent_workspace("massgen_prompt_"),
                log_directory=orch._get_log_directory(),
                orchestrator_id=orch.orchestrator_id,
                on_subagent_started=orch._make_precollab_started_callback(
                    anchor_agent,
                    call_id,
                    display,
                ),
                voting_sensitivity=getattr(orch.config, "voting_sensitivity", None),
                voting_threshold=orch._get_pre_collab_voting_threshold(),
                fast_iteration_mode=orch._get_fast_iteration_mode(),
            )

            orch._prompt_improved = True

            if improved:
                orch.current_task = improved
                logger.info(
                    f"[Orchestrator] Prompt improved ({len(improved)} chars)",
                )
                if display and hasattr(display, "notify_prompt_improved"):
                    try:
                        display.notify_prompt_improved(improved)
                    except Exception:
                        pass
            else:
                logger.info(
                    "[Orchestrator] Prompt improvement returned no result, keeping original",
                )

            orch._notify_precollab_completed(
                anchor_agent,
                "prompt_improvement",
                call_id,
                display,
                answer_preview=(f"Improved prompt ({len(improved)} chars)" if improved else "Using original prompt"),
            )

        except Exception as e:
            logger.error(f"[Orchestrator] Failed to improve prompt: {e}")
            logger.warning("[Orchestrator] Continuing without prompt improvement")
            orch._prompt_improved = True
            orch._notify_precollab_completed(
                anchor_agent,
                "prompt_improvement",
                call_id,
                display,
                status="failed",
                error=str(e),
            )
