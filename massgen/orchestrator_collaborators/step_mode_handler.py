"""Step-mode finalization and status-update helpers, extracted from Orchestrator.

PRESERVE BEHAVIOR EXACTLY. Three call patterns matter:

* ``Orchestrator.finalize_step_mode(orch, log_dir)`` is invoked UNBOUND on a
  ``MagicMock(spec=Orchestrator)`` in
  ``test_answer_path_normalization.py::test_step_mode_normalizes_workspace_in_answer``.
  The delegator on :class:`Orchestrator` therefore calls
  :meth:`StepModeHandler.finalize_step_mode` as a ``@staticmethod`` so the real
  logic runs regardless of whether ``self`` is a real orchestrator or a mock.

* ``orch._resolve_step_mode_workspace(agent_id)`` and
  ``orch._resolve_step_mode_stale_paths(agent_id)`` are invoked on real
  orchestrator instances (see ``test_step_mode.py`` lines 1145/1178/1204/1248
  and 1746). They route through bound delegators that defer to the handler.

* ``_continuous_status_updates`` is an ``async def`` coroutine started as a
  background task by ``_coordinate_agents_with_timeout``.

IMPORT-PATCH SAFETY: ``test_step_mode_normalizes_workspace_in_answer`` patches
``massgen.orchestrator.shutil``. To keep the patch effective after extraction
we resolve ``shutil`` through ``massgen.orchestrator`` instead of importing
``shutil`` directly here.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from massgen.logger_config import logger

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class StepModeHandler:
    """Owns step-mode finalization plus the continuous status-update task."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    @staticmethod
    def finalize_step_mode(self_orch: Orchestrator, log_dir: Path) -> None:
        """Write post-coordination artifacts for step mode runs.

        Mirrors the normal-mode finalization sequence so step-mode log
        directories have the same structure (``final/``, ``status.json``,
        ``coordination_events.json``, metrics) downstream tools expect.

        Implemented as a ``@staticmethod`` so it can be invoked unbound via
        ``Orchestrator.finalize_step_mode(orch, log_dir)`` against either a
        real orchestrator instance or a ``MagicMock(spec=Orchestrator)``.
        """
        # Import here so we resolve `shutil` through the orchestrator module
        # — tests patch ``massgen.orchestrator.shutil`` and we must honor that.
        from massgen import orchestrator as _orch_mod

        action_data = self_orch._step_action_data or {}
        agent_id = action_data.get("agent_id", "")
        action = action_data.get("action", "")
        answer_text = action_data.get("answer_text")
        workspace_path = action_data.get("workspace_path")

        # Write final/ directory for answer actions
        if action == "new_answer" and answer_text is not None:
            final_dir = log_dir / "final" / agent_id
            final_dir.mkdir(parents=True, exist_ok=True)

            # Normalize workspace paths so answer references the adjacent workspace/
            normalized_answer = answer_text
            if workspace_path:
                dest_workspace = str(final_dir / "workspace")
                normalized_answer = normalized_answer.replace(
                    str(workspace_path),
                    dest_workspace,
                )
                resolved_ws = str(Path(workspace_path).resolve())
                if resolved_ws != str(workspace_path):
                    normalized_answer = normalized_answer.replace(
                        resolved_ws,
                        dest_workspace,
                    )

            (final_dir / "answer.txt").write_text(normalized_answer)

            # Copy workspace to final/ if available
            if workspace_path:
                ws_src = Path(workspace_path)
                if ws_src.is_dir():
                    ws_dest = final_dir / "workspace"
                    _orch_mod.shutil.copytree(ws_src, ws_dest, symlinks=True, dirs_exist_ok=True)

            # Record in coordination tracker
            self_orch.coordination_tracker.set_final_answer(
                agent_id,
                answer_text,
                snapshot_timestamp="final",
            )

        # Save coordination logs (status.json, coordination_events.json, metrics)
        self_orch.coordination_tracker._end_session()
        self_orch.coordination_tracker.save_coordination_logs(log_dir)
        self_orch.coordination_tracker.save_status_file(log_dir, orchestrator=self_orch)
        self_orch.save_metrics(log_dir)

    def resolve_step_mode_workspace(self, agent_id: str) -> str | None:
        """Resolve the workspace path for step mode output.

        After ``_save_agent_snapshot`` runs, the agent's cwd is cleared but
        ``snapshot_storage`` has the full copy. Prefer ``snapshot_storage``
        when it has content; fall back to cwd if ``snapshot_storage`` is
        missing. Returns ``None`` when the agent produced no workspace files.
        """
        orch = self._orchestrator
        agent = orch.agents.get(agent_id)
        if not agent or not agent.backend.filesystem_manager:
            return None
        fm = agent.backend.filesystem_manager
        if fm.snapshot_storage and fm.snapshot_storage.is_dir() and any(fm.snapshot_storage.iterdir()):
            return str(fm.snapshot_storage)
        if fm.cwd and Path(fm.cwd).is_dir() and any(Path(fm.cwd).iterdir()):
            return str(fm.cwd)
        return None

    def resolve_step_mode_stale_paths(self, agent_id: str) -> list[str]:
        """Collect workspace paths the agent may have referenced in its answer text.

        These paths (cwd, temp workspace) are ephemeral and won't exist when
        another step mode invocation loads the session directory. They need
        to be replaced with the session dir workspace path by
        ``save_step_mode_output``.

        Args:
            agent_id: The agent whose paths to collect.

        Returns:
            List of stale path strings (may be empty).
        """
        stale: list[str] = []
        orch = self._orchestrator
        agent = orch.agents.get(agent_id)
        if not agent or not agent.backend.filesystem_manager:
            return stale
        fm = agent.backend.filesystem_manager
        if fm.cwd:
            stale.append(str(fm.cwd))
        if fm.agent_temporary_workspace:
            stale.append(str(fm.agent_temporary_workspace))
        return stale

    async def continuous_status_updates(self) -> None:
        """Background task to continuously update status.json during coordination.

        This task runs every 2 seconds to provide real-time status monitoring
        for automation tools and LLM agents.
        """
        # Late import to avoid a circular import at module load time.
        from massgen.logger_config import get_log_session_dir

        orch = self._orchestrator
        try:
            while True:
                # Check for cancellation before sleeping
                if hasattr(orch, "cancellation_manager") and orch.cancellation_manager and orch.cancellation_manager.is_cancelled:
                    logger.info(
                        "Cancellation detected in status update task - stopping",
                    )
                    break

                await asyncio.sleep(2)  # Update every 2 seconds

                # Check for cancellation after sleeping
                if hasattr(orch, "cancellation_manager") and orch.cancellation_manager and orch.cancellation_manager.is_cancelled:
                    logger.info(
                        "Cancellation detected in status update task - stopping",
                    )
                    break

                log_session_dir = get_log_session_dir()
                if log_session_dir:
                    try:
                        # Run synchronous save_status_file in thread pool to avoid blocking event loop
                        # This prevents delays in WebSocket broadcasts and other async operations
                        loop = asyncio.get_running_loop()
                        await loop.run_in_executor(
                            None,  # Use default thread pool executor
                            orch.coordination_tracker.save_status_file,
                            log_session_dir,
                            orch,
                        )
                    except Exception as e:
                        logger.debug(f"Failed to update status file in background: {e}")

                # Update timeout status for each agent in the display
                try:
                    display = None
                    if hasattr(orch, "coordination_ui") and orch.coordination_ui:
                        display = getattr(orch.coordination_ui, "display", None)

                    if display and hasattr(display, "update_timeout_status"):
                        for agent_id in orch.agents.keys():
                            timeout_state = orch.get_agent_timeout_state(agent_id)
                            if timeout_state and timeout_state.get("active_timeout"):
                                display.update_timeout_status(agent_id, timeout_state)
                except Exception as e:
                    logger.warning(f"Failed to update timeout status in display: {e}")
        except asyncio.CancelledError:
            # Task was cancelled, this is expected behavior
            pass
        except Exception as e:
            logger.warning(f"Background status update task encountered error: {e}")
