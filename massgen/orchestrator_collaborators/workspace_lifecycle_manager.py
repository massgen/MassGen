"""Workspace lifecycle (clear + memory archive), extracted from Orchestrator.

Filesystem-mutation cluster.  The orchestrator owns the shared mutable
``_pre_populated_workspaces`` attribute; this collaborator only mutates it
back on the orchestrator (so all reads/writes stay on a single owner).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from massgen.logger_config import logger

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class WorkspaceLifecycleManager:
    """Clear agent workspaces between turns and archive memories first."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    def clear_agent_workspaces(self) -> None:
        """Clear all agent workspaces and pre-populate with previous turn's results."""
        orch = self._orchestrator
        previous_turn_workspace = None
        if orch._previous_turns:
            latest_turn = orch._previous_turns[-1]
            previous_turn_workspace = Path(latest_turn["path"])

        for agent_id, agent in orch.agents.items():
            if agent.backend.filesystem_manager:
                workspace_path = agent.backend.filesystem_manager.get_current_workspace()
                if workspace_path and Path(workspace_path).exists():
                    # Archive memories BEFORE clearing workspace
                    self.archive_agent_memories(agent_id, Path(workspace_path))

                    for item in Path(workspace_path).iterdir():
                        if item.name == ".massgen":
                            continue
                        if item.is_symlink():
                            item.unlink()
                        elif item.is_file():
                            item.unlink()
                        elif item.is_dir():
                            shutil.rmtree(item)
                    logger.info(
                        f"[Orchestrator] Cleared workspace for {agent_id}: {workspace_path}",
                    )

                    if orch._pre_populated_workspaces and agent_id in orch._pre_populated_workspaces:
                        source = orch._pre_populated_workspaces[agent_id]
                        if source.exists():
                            logger.info(
                                f"[Orchestrator] Pre-populating {agent_id} workspace " f"with writable copy from cancelled turn: {source}",
                            )
                            for item in source.iterdir():
                                dest = Path(workspace_path) / item.name
                                if item.is_file():
                                    shutil.copy2(item, dest)
                                elif item.is_dir():
                                    shutil.copytree(
                                        item,
                                        dest,
                                        dirs_exist_ok=True,
                                        symlinks=True,
                                        ignore_dangling_symlinks=True,
                                    )
                    elif previous_turn_workspace and previous_turn_workspace.exists():
                        if orch._plan_session_id:
                            logger.info(
                                "[Orchestrator] Plan execution mode: restoring previous chunk " "workspace for %s from %s (plan_session: %s)",
                                agent_id,
                                previous_turn_workspace,
                                orch._plan_session_id,
                            )
                        logger.info(
                            f"[Orchestrator] Pre-populating {agent_id} workspace with writable copy of turn n-1 from {previous_turn_workspace}",
                        )
                        for item in previous_turn_workspace.iterdir():
                            dest = Path(workspace_path) / item.name
                            if item.is_file():
                                shutil.copy2(item, dest)
                            elif item.is_dir():
                                shutil.copytree(
                                    item,
                                    dest,
                                    dirs_exist_ok=True,
                                    symlinks=True,
                                    ignore_dangling_symlinks=True,
                                )
                        logger.info(
                            f"[Orchestrator] Pre-populated {agent_id} workspace with writable copy of turn n-1",
                        )
                    elif orch._plan_session_id:
                        logger.info(
                            "[Orchestrator] Plan execution mode: no previous turn workspace " "available to restore (plan_session: %s)",
                            orch._plan_session_id,
                        )

        # Mutate SHARED-MUTABLE state back on the orchestrator (single owner).
        if orch._pre_populated_workspaces is not None:
            orch._pre_populated_workspaces = None

        # _seed_plan_execution_workspaces STAYS on the orchestrator.
        orch._seed_plan_execution_workspaces(context="workspace_clear")

    def archive_agent_memories(self, agent_id: str, workspace_path: Path) -> None:
        """Archive memories from agent workspace before clearing."""
        orch = self._orchestrator
        memory_dir = workspace_path / "memory"
        if not memory_dir.exists():
            logger.info(
                f"[Orchestrator] No memory directory for {agent_id}, skipping archive",
            )
            return

        answer_num = orch.agent_states[agent_id].answer_count

        if not orch.session_id:
            logger.warning("[Orchestrator] Cannot archive memories: no session_id")
            return

        archive_base = Path(".massgen/sessions") / orch.session_id / "archived_memories"
        archive_path = archive_base / f"{agent_id}_answer_{answer_num}"

        try:
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(
                memory_dir,
                archive_path,
                dirs_exist_ok=True,
                symlinks=True,
                ignore_dangling_symlinks=True,
            )
            self.namespace_verification_memory_files(archive_path, agent_id)
            logger.info(
                f"[Orchestrator] Archived memories for {agent_id} answer {answer_num} to {archive_path}",
            )
        except Exception as e:
            logger.error(
                f"[Orchestrator] Failed to archive memories for {agent_id}: {e}",
            )

    def namespace_verification_memory_files(self, archive_path: Path, agent_id: str) -> None:
        """Namespace verification_latest and essential_files_manifest so per-agent files never collide."""
        orch = self._orchestrator
        token = orch.coordination_tracker.get_path_token(agent_id)
        namespaced_name = f"verification_latest__{token}.md"
        namespaced_manifest = f"essential_files_manifest__{token}.json"
        for tier in ("short_term", "long_term"):
            tier_dir = archive_path / tier
            if not tier_dir.exists():
                continue

            legacy_file = tier_dir / "verification_latest.md"
            if legacy_file.exists():
                namespaced_file = tier_dir / namespaced_name
                if namespaced_file.exists():
                    namespaced_file.unlink()
                legacy_file.rename(namespaced_file)

            manifest_file = tier_dir / "essential_files_manifest.json"
            if manifest_file.exists():
                namespaced_mf = tier_dir / namespaced_manifest
                if namespaced_mf.exists():
                    namespaced_mf.unlink()
                manifest_file.rename(namespaced_mf)
