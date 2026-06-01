"""Context-path write tracking accessors, extracted from Orchestrator."""

from __future__ import annotations

from typing import TYPE_CHECKING

from massgen.logger_config import logger

if TYPE_CHECKING:
    from massgen.chat_agent import ChatAgent
    from massgen.orchestrator import Orchestrator


class ContextPathWriteTracker:
    """Self-contained accessors over each agent's path_permission_manager (PPM).

    Holds a back-reference to the orchestrator to read ``agents`` and
    ``_selected_agent`` for resolving the relevant PPM.
    """

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    def has_write_context_paths(self, agent: ChatAgent) -> bool:
        """
        Check if agent has any context paths with write permission configured.

        Args:
            agent: The agent to check

        Returns:
            True if agent has write context paths, False otherwise
        """
        if not hasattr(agent, "backend") or not agent.backend:
            return False
        filesystem_manager = getattr(agent.backend, "filesystem_manager", None)
        if not filesystem_manager:
            return False
        ppm = getattr(filesystem_manager, "path_permission_manager", None)
        if not ppm:
            return False
        return any(mp.will_be_writable for mp in ppm.managed_paths if mp.path_type == "context")

    def enable_context_write_access(self, agent: ChatAgent) -> None:
        """
        Enable write access for context paths on the given agent.

        Args:
            agent: The agent to enable write access for
        """
        if not hasattr(agent, "backend") or not agent.backend:
            return
        filesystem_manager = getattr(agent.backend, "filesystem_manager", None)
        if not filesystem_manager:
            return
        ppm = getattr(filesystem_manager, "path_permission_manager", None)
        if not ppm:
            return
        ppm.set_context_write_access_enabled(True)
        logger.info(f"[Orchestrator] Enabled context write access for agent: {agent.agent_id}")

    def get_context_path_writes(self) -> list[str]:
        """
        Get list of files written to context paths by the final agent.

        Returns:
            List of file paths written to context paths
        """
        orchestrator = self._orchestrator
        if not orchestrator._selected_agent:
            return []
        agent = orchestrator.agents.get(orchestrator._selected_agent)
        if not agent or not hasattr(agent, "backend") or not agent.backend:
            return []
        filesystem_manager = getattr(agent.backend, "filesystem_manager", None)
        if not filesystem_manager:
            return []
        ppm = getattr(filesystem_manager, "path_permission_manager", None)
        if not ppm:
            return []
        return ppm.get_context_path_writes()

    def get_context_path_writes_categorized(self) -> dict[str, list[str]]:
        """
        Get categorized lists of new and modified files in context paths.

        Returns:
            Dict with 'new' and 'modified' keys, each containing a list of file paths
        """
        orchestrator = self._orchestrator
        if not orchestrator._selected_agent:
            return {"new": [], "modified": []}
        agent = orchestrator.agents.get(orchestrator._selected_agent)
        if not agent or not hasattr(agent, "backend") or not agent.backend:
            return {"new": [], "modified": []}
        filesystem_manager = getattr(agent.backend, "filesystem_manager", None)
        if not filesystem_manager:
            return {"new": [], "modified": []}
        ppm = getattr(filesystem_manager, "path_permission_manager", None)
        if not ppm:
            return {"new": [], "modified": []}
        return ppm.get_context_path_writes_categorized()

    def clear_context_path_write_tracking(self) -> None:
        """Clear context path write tracking for all agents at the start of each turn."""
        for agent_id, agent in self._orchestrator.agents.items():
            if not hasattr(agent, "backend") or not agent.backend:
                continue
            filesystem_manager = getattr(agent.backend, "filesystem_manager", None)
            if not filesystem_manager:
                continue
            ppm = getattr(filesystem_manager, "path_permission_manager", None)
            if ppm and hasattr(ppm, "clear_context_path_writes"):
                ppm.clear_context_path_writes()
                logger.debug(f"[Orchestrator] Cleared context path write tracking for {agent_id}")
