"""Active-coordination cleanup, extracted from Orchestrator.

Cancels in-flight tasks, closes active streams, and tears down the
SubagentLaunchWatcher. ALL shared coordination dicts (``_active_tasks``,
``_active_streams``, ``_subagent_launch_watcher``) are mutated via the
orchestrator back-ref so the live coordination loop sees consistent state.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from massgen.logger_config import logger
from massgen.utils import ActionType

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class ActiveCoordinationCleanup:
    """Force cleanup of active coordination streams and tasks on timeout."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    async def cleanup(self) -> None:
        orch = self._orchestrator

        # Stop the SubagentLaunchWatcher if running.
        if orch._subagent_launch_watcher is not None:
            try:
                await orch._subagent_launch_watcher.stop()
            except Exception as e:
                logger.warning(f"[Orchestrator] Error stopping SubagentLaunchWatcher: {e}")
            orch._subagent_launch_watcher = None

        # R4: cancel detached background trace-analyzer tasks BEFORE flushing, so a
        # surviving task cannot append a result after the flush into a queue that
        # will never be consumed (and so it doesn't outlive the hard timeout). The
        # task's CancelledError path returns without writing, so awaiting the
        # cancellation fully closes the window.
        if getattr(orch, "_background_trace_tasks", None):
            for _agent_id, trace_task in list(orch._background_trace_tasks.items()):
                if not trace_task.done():
                    trace_task.cancel()
                    try:
                        await trace_task
                    except (asyncio.CancelledError, Exception):
                        pass
            orch._background_trace_tasks.clear()

        # Flush any pending subagent results that weren't delivered.
        orch._flush_pending_subagent_results()

        # Cancel and cleanup active tasks.
        if hasattr(orch, "_active_tasks") and orch._active_tasks:
            for agent_id, agent in orch.agents.items():
                if hasattr(agent, "backend") and hasattr(agent.backend, "interrupt"):
                    try:
                        await agent.backend.interrupt()
                    except Exception:
                        pass
            for agent_id, task in orch._active_tasks.items():
                if not task.done():
                    if not orch.is_orchestrator_timeout:
                        orch.coordination_tracker.track_agent_action(
                            agent_id,
                            ActionType.CANCELLED,
                            "Coordination cleanup",
                        )
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):
                        pass
            orch._active_tasks.clear()

        # Close active streams.
        if hasattr(orch, "_active_streams") and orch._active_streams:
            for agent_id in list(orch._active_streams.keys()):
                await orch._close_agent_stream(agent_id, orch._active_streams)
