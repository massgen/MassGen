"""Per-agent orchestration setup, extracted from Orchestrator.

Owns the body of the (formerly nested) ``_setup_agent_orchestration``
helper and the public ``ensure_workspace_symlinks`` method. All shared
orchestrator state is accessed via a back-ref so the live coordination
loop sees consistent state.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from massgen.logger_config import get_log_session_dir, logger

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class AgentOrchestrationSetup:
    """Per-agent orchestration path setup and workspace symlink management."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    def setup_agent_orchestration(
        self,
        agent_id: str,
        agent: Any,
        skills_directory: Any,
        massgen_skills: Any,
        load_previous_session_skills: bool,
    ) -> None:
        """Setup orchestration paths for a single agent (can run in parallel)."""
        orch = self._orchestrator
        if not agent.backend.filesystem_manager:
            return

        # Add Docker mount for subagent logs directory if needed
        if orch._subagent_logs_dir is not None:
            fm = agent.backend.filesystem_manager
            if hasattr(fm, "docker_manager") and fm.docker_manager is not None:
                resolved = str(orch._subagent_logs_dir.resolve())
                fm.docker_manager.additional_mounts[resolved] = {
                    "bind": resolved,
                    "mode": "rw",
                }
                logger.info(
                    f"[Orchestrator] Added Docker mount for subagent logs: {resolved}",
                )
                # Also mount delegation directory for file-based container-to-host launch
                if orch._delegation_dir is not None:
                    del_resolved = str(orch._delegation_dir.resolve())
                    fm.docker_manager.additional_mounts[del_resolved] = {
                        "bind": del_resolved,
                        "mode": "rw",
                    }
                    logger.info(
                        f"[Orchestrator] Added Docker mount for delegation dir: {del_resolved}",
                    )

        workspace_token = orch.coordination_tracker.get_path_token(agent_id)
        agent.backend.filesystem_manager.setup_orchestration_paths(
            agent_id=agent_id,
            snapshot_storage=orch._snapshot_storage,
            agent_temporary_workspace=orch._agent_temporary_workspace,
            skills_directory=skills_directory,
            massgen_skills=massgen_skills,
            load_previous_session_skills=load_previous_session_skills,
            workspace_token=workspace_token,
        )
        # Setup workspace directories for massgen skills
        if hasattr(orch.config, "coordination_config") and hasattr(
            orch.config.coordination_config,
            "massgen_skills",
        ):
            if orch.config.coordination_config.massgen_skills:
                agent.backend.filesystem_manager.setup_massgen_skill_directories(
                    massgen_skills=orch.config.coordination_config.massgen_skills,
                )
        # Setup memory directories if memory filesystem mode is enabled
        if hasattr(orch.config, "coordination_config") and hasattr(
            orch.config.coordination_config,
            "enable_memory_filesystem_mode",
        ):
            if orch.config.coordination_config.enable_memory_filesystem_mode:
                agent.backend.filesystem_manager.setup_memory_directories()

                # Restore memories from previous turn if available
                if orch._previous_turns:
                    previous_turn = orch._previous_turns[-1]  # Get most recent turn
                    if "log_dir" in previous_turn:
                        prev_log_dir = Path(previous_turn["log_dir"])
                        # Look for final workspace from previous turn
                        prev_final_workspace = prev_log_dir / "final"
                        if prev_final_workspace.exists():
                            # Find the winning agent's workspace from previous turn
                            for agent_dir in prev_final_workspace.iterdir():
                                if agent_dir.is_dir():
                                    prev_workspace = agent_dir / "workspace"
                                    if prev_workspace.exists():
                                        logger.info(
                                            f"[Orchestrator] Restoring memories from previous turn: {prev_workspace}",
                                        )
                                        agent.backend.filesystem_manager.restore_memories_from_previous_turn(
                                            prev_workspace,
                                        )
                                        break  # Only restore from one agent (the winner)

        # Update MCP config with agent_id for Docker mode (must be after setup_orchestration_paths)
        agent.backend.filesystem_manager.update_backend_mcp_config(
            agent.backend.config,
        )

    def ensure_workspace_symlinks(self) -> None:
        """Ensure per-agent workspace symlinks exist in the current attempt log directory.

        In checkpoint solo mode, only creates symlinks for active agents
        (main agent in solo, all agents during checkpoint).
        """
        orch = self._orchestrator
        try:
            log_dir = get_log_session_dir()
            if log_dir:
                for agent_id, agent in orch.agents.items():
                    # Skip inactive agents (e.g., non-main agents in solo mode)
                    if not orch._is_agent_active_in_current_mode(agent_id):
                        continue
                    if not agent.backend.filesystem_manager or not agent.backend.filesystem_manager.cwd:
                        continue
                    agent_log_dir = log_dir / agent_id
                    agent_log_dir.mkdir(parents=True, exist_ok=True)
                    workspace_link = agent_log_dir / "workspace"
                    if workspace_link.exists():
                        continue
                    workspace_link.symlink_to(Path(agent.backend.filesystem_manager.cwd).resolve())
                    logger.info(
                        f"[Orchestrator] Symlinked {workspace_link} → {agent.backend.filesystem_manager.cwd}",
                    )
        except Exception as e:
            logger.debug(f"[Orchestrator] Failed to create workspace symlinks: {e}")
