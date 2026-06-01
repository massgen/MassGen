"""Workspace modal presentation, extracted from Orchestrator.

Single async UI bridge that, in no-git (no-isolation) mode, surfaces the
final-answer modal with the winning agent's workspace tab. Read-only over
orchestrator state; calls back into the orchestrator for the shared helpers
``_resolve_final_workspace_path`` and ``_get_vote_results`` (which remain on
the orchestrator for now and will move under FinalResultReporter).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from massgen.logger_config import logger

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class WorkspaceModalPresenter:
    """Show the final-answer modal with a workspace tab in no-isolation mode."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    async def show_if_needed(self) -> None:
        """Show the final answer modal with workspace tab in no-git (no-isolation) mode.

        Called from _present_final_answer in both the skip-presentation and
        normal-presentation paths.  Must run BEFORE clear_workspace().
        """
        orch = self._orchestrator

        if orch._isolation_manager:
            try:
                active_contexts = [ctx for ctx in orch._isolation_manager.list_contexts() if ctx]
            except Exception as e:
                # Fail closed: if we cannot inspect isolation state, keep existing behavior.
                logger.warning("[Orchestrator] Failed to inspect isolation state: %s", e)
                active_contexts = [object()]

            if active_contexts:
                return

        display = None
        if hasattr(orch, "coordination_ui") and orch.coordination_ui:
            display = getattr(orch.coordination_ui, "display", None)

        if not display or not hasattr(display, "show_final_answer_modal"):
            return

        agent = orch.agents.get(orch._selected_agent)

        # Try final workspace from logs first, fall back to live workspace
        # (live workspace hasn't been cleared yet at this point)
        workspace_path = orch._resolve_final_workspace_path(orch._selected_agent)
        if not workspace_path and agent:
            fm = getattr(getattr(agent, "backend", None), "filesystem_manager", None)
            if fm:
                try:
                    ws = fm.get_current_workspace()
                    if ws and Path(ws).is_dir() and any(Path(ws).iterdir()):
                        workspace_path = str(ws)
                except Exception:
                    pass

        logger.info(
            f"[Orchestrator] No-git workspace modal: workspace_path={workspace_path}, " f"agent={orch._selected_agent}",
        )

        if not workspace_path:
            logger.info(
                "[Orchestrator] No-git workspace path unavailable; " "opening answer-only final modal",
            )

        try:
            model_name = ""
            if agent and hasattr(agent, "backend") and hasattr(agent.backend, "config"):
                model_name = agent.backend.config.get("model", "")

            await display.show_final_answer_modal(
                changes=[],
                answer_content=orch._final_presentation_content or "",
                vote_results=orch._get_vote_results(),
                agent_id=orch._selected_agent or "",
                model_name=model_name,
                workspace_path=workspace_path,
            )
        except Exception as e:
            logger.warning(f"[Orchestrator] Workspace modal failed: {e}")
