"""Changedoc coordination helpers extracted from :class:`Orchestrator`.

Owns the small predicate/accumulator for per-agent changedocs and the
``_sync_applied_context_files_into_final_artifacts`` file-overlay routine.

The orchestrator keeps thin delegator methods so behavior, signatures, and
critically the test pattern ``orch._is_changedoc_enabled = lambda: ...``
continue to work (the instance attribute shadows the delegator).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from massgen.logger_config import logger

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class ChangedocCoordinator:
    """Collect agent changedocs and overlay applied context files into artifacts."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    def is_changedoc_enabled(self) -> bool:
        """Return True when changedoc decision journal is enabled."""
        coord = getattr(self._orchestrator.config, "coordination_config", None)
        return bool(coord and getattr(coord, "enable_changedoc", True))

    def gather_agent_changedocs(self) -> dict[str, str] | None:
        """Collect latest changedocs from all agents, or None if disabled/empty."""
        # IMPORTANT: call through the orchestrator so test monkeypatches of
        # ``orch._is_changedoc_enabled = lambda: ...`` keep working.
        if not self._orchestrator._is_changedoc_enabled():
            return None
        changedocs: dict[str, str] = {}
        tracker = self._orchestrator.coordination_tracker
        for aid, ans_list in tracker.answers_by_agent.items():
            if ans_list and ans_list[-1].changedoc:
                changedocs[aid] = ans_list[-1].changedoc
        return changedocs or None

    def sync_applied_context_files_into_final_artifacts(
        self,
        agent_id: str,
        target_path: str,
        relative_paths: list[str],
    ) -> None:
        """Mirror approved context-path changes into saved final artifacts.

        Final presentation snapshots the agent workspace before isolated
        context-path changes are reviewed and copied back to the real target.
        After apply, overlay the delivered files into the persisted final
        artifacts so logs and snapshot_storage reflect what actually landed.
        """
        if not relative_paths:
            return

        orchestrator = self._orchestrator
        agent = orchestrator.agents.get(agent_id)
        if not agent or not hasattr(agent, "backend"):
            return

        filesystem_manager = getattr(agent.backend, "filesystem_manager", None)
        if filesystem_manager is None:
            return

        source_root = Path(target_path)
        normalized_rel_paths: list[str] = []
        seen_rel_paths: set[str] = set()
        for rel_path in relative_paths:
            if not isinstance(rel_path, str):
                continue
            normalized = rel_path.replace("\\", "/").strip()
            if not normalized:
                normalized = source_root.name
            rel_obj = Path(normalized)
            if rel_obj.is_absolute() or ".." in rel_obj.parts:
                logger.warning(
                    "[Orchestrator] Skipping unsafe applied context path %r for %s",
                    rel_path,
                    agent_id,
                )
                continue
            rel_key = rel_obj.as_posix()
            if rel_key in seen_rel_paths:
                continue
            seen_rel_paths.add(rel_key)
            normalized_rel_paths.append(rel_key)

        if not normalized_rel_paths:
            return

        destination_roots: list[Path] = []
        # Lazy import so test patches against the orchestrator namespace
        # (``massgen.orchestrator.get_log_session_dir``) still take effect.
        from massgen import orchestrator as _orch_mod

        log_session_dir = _orch_mod.get_log_session_dir()
        if log_session_dir:
            destination_roots.append(Path(log_session_dir) / "final" / agent_id / "workspace")

        snapshot_storage = getattr(filesystem_manager, "snapshot_storage", None)
        if snapshot_storage:
            destination_roots.append(Path(snapshot_storage))

        if not destination_roots:
            return

        copied_count = 0
        removed_count = 0
        for destination_root in destination_roots:
            destination_root.mkdir(parents=True, exist_ok=True)

            for normalized in normalized_rel_paths:
                rel_obj = Path(normalized)
                source_path = source_root if source_root.is_file() else source_root / rel_obj
                destination_path = destination_root / rel_obj

                try:
                    if source_path.exists():
                        destination_path.parent.mkdir(parents=True, exist_ok=True)
                        if source_path.is_file():
                            shutil.copy2(source_path, destination_path)
                        elif source_path.is_dir():
                            shutil.copytree(
                                source_path,
                                destination_path,
                                dirs_exist_ok=True,
                                symlinks=True,
                                ignore_dangling_symlinks=True,
                            )
                        copied_count += 1
                    else:
                        if destination_path.is_file() or destination_path.is_symlink():
                            destination_path.unlink()
                            removed_count += 1
                        elif destination_path.is_dir():
                            shutil.rmtree(destination_path)
                            removed_count += 1
                except Exception as exc:
                    logger.warning(
                        "[Orchestrator] Failed to sync applied context file %s into %s for %s: %s",
                        normalized,
                        destination_root,
                        agent_id,
                        exc,
                    )

        logger.info(
            "[Orchestrator] Synced applied context files into final artifacts for %s: copied=%d removed=%d paths=%s",
            agent_id,
            copied_count,
            removed_count,
            normalized_rel_paths,
        )
