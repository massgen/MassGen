"""Per-agent snapshot persistence, extracted from Orchestrator.

Owns the writes that persist an agent's workspace, answer, vote, context, and
execution trace into the log session directory and the agent's
``snapshot_storage``. Also owns the related early-termination and
interrupted-turn partial snapshot paths, plus shared-memory injection and
recording (which run side-by-side with snapshotting at coordination
boundaries).

All shared state is mutated through the orchestrator back-ref
(``self._orchestrator``) so the other collaborators that already write the
same fields (notably :class:`ChecklistGateManager` which reads/writes
``answer_count`` / ``checklist_calls_this_round`` /
``pending_checklist_recheck_labels``) see one consistent live set.

Critical monkeypatch-safety contract:

- Sibling cross-method calls (e.g. ``_save_partial_snapshots_for_early_termination``
  invoking ``_save_agent_snapshot``) route through
  ``self._orchestrator._save_agent_snapshot(...)`` rather than ``self.save_agent_snapshot``
  so tests that monkeypatch ``orch._save_agent_snapshot`` continue to take effect.
- ``_save_agent_snapshot`` preserves its exact signature (keyword args, defaults,
  return value) because tests in ``test_answer_count_increment.py`` and
  ``test_execution_trace_early_end.py`` invoke it directly.
- The answer_count / checklist_calls_this_round / pending_checklist_recheck_labels
  side effect at the END of ``_save_agent_snapshot`` is preserved byte-for-byte
  (with real answer -> resets per-round counters; with None answer -> does NOT reset).
"""

from __future__ import annotations

import json
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from massgen.filesystem_manager._snapshot_version_store import SnapshotVersionStore
from massgen.logger_config import get_log_session_dir, logger

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class SnapshotManager:
    """Persists per-agent snapshots, partial snapshots, and shared-memory writes."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    # ------------------------------------------------------------------
    # Shared memory injection / recording
    # ------------------------------------------------------------------

    async def inject_shared_memory_context(
        self,
        messages: list[dict[str, Any]],
        agent_id: str,
    ) -> list[dict[str, Any]]:
        """See Orchestrator._inject_shared_memory_context."""
        orch = self._orchestrator
        if not orch.shared_conversation_memory and not orch.shared_persistent_memory:
            return messages

        memory_context_parts = []

        if orch.shared_conversation_memory:
            try:
                conv_messages = await orch.shared_conversation_memory.get_messages()
                if conv_messages:
                    memory_context_parts.append("=== SHARED CONVERSATION MEMORY ===")
                    for msg in conv_messages[-10:]:
                        role = msg.get("role", "unknown")
                        content = msg.get("content", "")
                        agent_source = msg.get("agent_id", "unknown")
                        memory_context_parts.append(
                            f"[{agent_source}] {role}: {content}",
                        )
            except Exception as e:
                logger.warning(f"Failed to retrieve shared conversation memory: {e}")

        if orch.shared_persistent_memory:
            try:
                user_messages = [msg for msg in messages if msg.get("role") == "user"]
                if user_messages:
                    retrieved = await orch.shared_persistent_memory.retrieve(
                        user_messages,
                    )
                    if retrieved:
                        memory_context_parts.append(
                            "\n=== SHARED PERSISTENT MEMORY ===",
                        )
                        memory_context_parts.append(retrieved)
            except NotImplementedError:
                pass
            except Exception as e:
                logger.warning(f"Failed to retrieve shared persistent memory: {e}")

        if memory_context_parts:
            memory_message = {
                "role": "system",
                "content": ("You have access to shared memory that all agents can see and contribute to.\n" + "\n".join(memory_context_parts)),
            }
            system_count = sum(1 for msg in messages if msg.get("role") == "system")
            modified_messages = messages.copy()
            modified_messages.insert(system_count, memory_message)
            return modified_messages

        return messages

    async def record_to_shared_memory(
        self,
        agent_id: str,
        content: str,
        role: str = "assistant",
    ) -> None:
        """See Orchestrator._record_to_shared_memory."""
        orch = self._orchestrator
        message = {
            "role": role,
            "content": content,
            "agent_id": agent_id,
            "timestamp": time.time(),
        }

        if orch.shared_conversation_memory:
            try:
                await orch.shared_conversation_memory.add(message)
            except Exception as e:
                logger.warning(f"Failed to add to shared conversation memory: {e}")

        if orch.shared_persistent_memory:
            try:
                await orch.shared_persistent_memory.record([message])
            except NotImplementedError:
                pass
            except Exception as e:
                logger.warning(f"Failed to record to shared persistent memory: {e}")

    # ------------------------------------------------------------------
    # Snapshot fan-out for context sharing
    # ------------------------------------------------------------------

    async def copy_all_snapshots_to_temp_workspace(
        self,
        agent_id: str,
    ) -> str | None:
        """See Orchestrator._copy_all_snapshots_to_temp_workspace."""
        orch = self._orchestrator
        agent = orch.agents.get(agent_id)
        if not agent:
            return None

        if not agent.backend.filesystem_manager:
            return None

        agent_mapping = orch.coordination_tracker.get_reverse_agent_mapping()

        all_snapshots = {}
        # Logical (symlink) path per source, kept for stale-path rewriting even
        # though the copy reads from the pinned concrete version.
        logical_paths: dict[str, Path] = {}
        # Pinned immutable versions to release after the copy completes.
        version_store = None
        pinned: list[Path] = []
        if orch._snapshot_storage:
            snapshot_base = Path(orch._snapshot_storage)
            version_store = SnapshotVersionStore.for_base(snapshot_base)
            for source_agent_id in orch.agents.keys():
                # Pin the current immutable version so a concurrent peer
                # save_snapshot (republish) cannot delete it mid-copy (B1 fix).
                concrete = version_store.acquire(source_agent_id)
                if concrete is not None and concrete.is_dir():
                    all_snapshots[source_agent_id] = concrete
                    logical_paths[source_agent_id] = snapshot_base / source_agent_id
                    pinned.append(concrete)

        if orch._step_mode and orch._step_mode.enabled and orch._step_inputs:
            for va_id, va_state in orch._step_inputs.virtual_agents.items():
                if va_id not in all_snapshots and va_state.latest_workspace:
                    va_ws = Path(va_state.latest_workspace)
                    if va_ws.exists() and va_ws.is_dir():
                        all_snapshots[va_id] = va_ws

        try:
            workspace_path = await agent.backend.filesystem_manager.copy_snapshots_to_temp_workspace(
                all_snapshots,
                agent_mapping,
            )

            if workspace_path:
                from massgen.filesystem_manager import replace_stale_paths_in_workspace

                for source_agent_id, snapshot_path in all_snapshots.items():
                    anon_id = agent_mapping.get(source_agent_id, source_agent_id)
                    dest_dir = workspace_path / anon_id
                    if not dest_dir.exists():
                        continue
                    # Rewrite both the concrete version path AND the logical
                    # symlink path, since either may be embedded in copied files.
                    replacements: dict[str, str] = {str(snapshot_path): str(dest_dir)}
                    logical = logical_paths.get(source_agent_id)
                    if logical is not None and str(logical) != str(snapshot_path):
                        replacements[str(logical)] = str(dest_dir)
                    source_agent = orch.agents.get(source_agent_id)
                    if source_agent and source_agent.backend.filesystem_manager:
                        fm = source_agent.backend.filesystem_manager
                        if fm.cwd:
                            replacements[str(fm.cwd)] = str(dest_dir)
                    replace_stale_paths_in_workspace(dest_dir, replacements)
        finally:
            if version_store is not None:
                for concrete in pinned:
                    version_store.release(concrete)

        return str(workspace_path) if workspace_path else None

    # ------------------------------------------------------------------
    # Per-agent snapshot
    # ------------------------------------------------------------------

    async def save_agent_snapshot(
        self,
        agent_id: str,
        answer_content: str = None,
        vote_data: dict[str, Any] = None,
        is_final: bool = False,
        context_data: Any = None,
    ) -> str:
        """See Orchestrator._save_agent_snapshot."""
        orch = self._orchestrator
        logger.info(
            f"[Orchestrator._save_agent_snapshot] Called for agent_id={agent_id}, has_answer={bool(answer_content)}, has_vote={bool(vote_data)}, is_final={is_final}",
        )

        agent = orch.agents.get(agent_id)
        if not agent:
            logger.warning(
                f"[Orchestrator._save_agent_snapshot] Agent {agent_id} not found in agents dict",
            )
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

        if answer_content is not None or is_final:
            try:
                log_session_dir = get_log_session_dir()
                if log_session_dir:
                    if is_final:
                        timestamped_dir = log_session_dir / "final" / agent_id
                    else:
                        timestamped_dir = log_session_dir / agent_id / timestamp
                    timestamped_dir.mkdir(parents=True, exist_ok=True)
                    answer_file = timestamped_dir / "answer.txt"

                    content_to_write = answer_content if answer_content is not None else ""

                    if is_final and content_to_write and agent.backend.filesystem_manager:
                        original_cwd = getattr(agent.backend.filesystem_manager, "cwd", None)
                        if original_cwd:
                            dest_workspace = str(timestamped_dir / "workspace")
                            content_to_write = content_to_write.replace(
                                str(original_cwd),
                                dest_workspace,
                            )
                            resolved_cwd = str(Path(original_cwd).resolve())
                            if resolved_cwd != str(original_cwd):
                                content_to_write = content_to_write.replace(
                                    resolved_cwd,
                                    dest_workspace,
                                )

                    answer_file.write_text(content_to_write)
                    logger.info(
                        f"[Orchestrator._save_agent_snapshot] Saved answer to {answer_file}",
                    )

                    if orch._is_changedoc_enabled() and agent.backend.filesystem_manager:
                        from massgen.changedoc import read_changedoc_from_workspace

                        ws_path = agent.backend.filesystem_manager.cwd
                        if ws_path:
                            changedoc_content = read_changedoc_from_workspace(Path(ws_path))
                            if changedoc_content:
                                agent_num = orch.coordination_tracker._get_agent_number(agent_id)
                                answer_num = len(orch.coordination_tracker.answers_by_agent.get(agent_id, [])) + 1
                                label = f"agent{agent_num}.{answer_num}"
                                changedoc_content = changedoc_content.replace("[SELF]", label)
                                changedoc_file = timestamped_dir / "changedoc.md"
                                changedoc_file.write_text(changedoc_content)
                                logger.info(
                                    "[Orchestrator._save_agent_snapshot] Saved changedoc to %s",
                                    changedoc_file,
                                )

            except Exception as e:
                logger.warning(
                    f"[Orchestrator._save_agent_snapshot] Failed to save answer for {agent_id}: {e}",
                )

        if vote_data:
            try:
                log_session_dir = get_log_session_dir()
                if log_session_dir:
                    timestamped_dir = log_session_dir / agent_id / timestamp
                    timestamped_dir.mkdir(parents=True, exist_ok=True)
                    vote_file = timestamped_dir / "vote.json"

                    current_answers = {aid: state.answer for aid, state in orch.agent_states.items() if state.answer}

                    agent_mapping = orch.coordination_tracker.get_anonymous_agent_mapping()

                    available_answer_labels = []
                    answer_label_to_agent = {}
                    voted_for_label = None
                    voted_for_agent = vote_data.get("agent_id", "unknown")

                    if orch.coordination_tracker:
                        voter_context = orch.coordination_tracker.get_agent_context_labels(agent_id)
                        for label in voter_context:
                            available_answer_labels.append(label)
                            for aid in current_answers.keys():
                                aid_label = orch.coordination_tracker.get_voted_for_label(
                                    agent_id,
                                    aid,
                                )
                                if aid_label == label:
                                    answer_label_to_agent[label] = aid

                        voted_for_label = orch.coordination_tracker.get_voted_for_label(
                            agent_id,
                            voted_for_agent,
                        )

                    comprehensive_vote_data = {
                        "voter_id": agent_id,
                        "voter_anon_id": next(
                            (anon for anon, real in agent_mapping.items() if real == agent_id),
                            agent_id,
                        ),
                        "voted_for": voted_for_agent,
                        "voted_for_label": voted_for_label,
                        "voted_for_anon": next(
                            (anon for anon, real in agent_mapping.items() if real == voted_for_agent),
                            "unknown",
                        ),
                        "reason": vote_data.get("reason", ""),
                        "timestamp": timestamp,
                        "unix_timestamp": time.time(),
                        "iteration": orch.coordination_tracker.current_iteration if orch.coordination_tracker else None,
                        "coordination_round": orch.coordination_tracker.max_round if orch.coordination_tracker else None,
                        "available_options": list(
                            current_answers.keys(),
                        ),
                        "available_options_labels": available_answer_labels,
                        "answer_label_to_agent": answer_label_to_agent,
                        "available_options_anon": [
                            next(
                                (anon for anon, real in agent_mapping.items() if real == aid),
                                aid,
                            )
                            for aid in sorted(current_answers.keys())
                        ],
                        "agent_mapping": agent_mapping,
                        "vote_context": {
                            "total_agents": len(orch.agents),
                            "agents_with_answers": len(current_answers),
                            "current_task": orch.current_task,
                        },
                    }

                    with open(vote_file, "w", encoding="utf-8") as f:
                        json.dump(comprehensive_vote_data, f, indent=2)
                    logger.info(
                        f"[Orchestrator._save_agent_snapshot] Saved comprehensive vote to {vote_file}",
                    )

            except Exception as e:
                logger.error(
                    f"[Orchestrator._save_agent_snapshot] Failed to save vote for {agent_id}: {e}",
                )
                logger.error(
                    f"[Orchestrator._save_agent_snapshot] Traceback: {traceback.format_exc()}",
                )

        if agent.backend.filesystem_manager:
            if vote_data and not answer_content and not is_final:
                logger.info(
                    "[Orchestrator._save_agent_snapshot] Skipping workspace snapshot for vote (preserving previous workspace)",
                )
            else:
                workspace_path = agent.backend.filesystem_manager.get_current_workspace()
                if workspace_path:
                    orch._archive_agent_memories(agent_id, Path(workspace_path))

                logger.info(
                    f"[Orchestrator._save_agent_snapshot] Agent {agent_id} has filesystem_manager, calling save_snapshot with timestamp={timestamp if not is_final else None}",
                )
                await agent.backend.filesystem_manager.save_snapshot(
                    timestamp=timestamp if not is_final else None,
                    is_final=is_final,
                    preserve_existing_snapshot=(answer_content is None and not is_final),
                )

                if not is_final:
                    pending_round_cleanup = agent_id in getattr(
                        orch,
                        "_round_isolation_managers",
                        {},
                    )
                    if pending_round_cleanup:
                        logger.info(
                            f"[Orchestrator._save_agent_snapshot] Deferred workspace clear for {agent_id} " "(pending round isolation cleanup)",
                        )
                    else:
                        agent.backend.filesystem_manager.clear_workspace()
                        logger.info(
                            f"[Orchestrator._save_agent_snapshot] Cleared workspace for {agent_id} after saving snapshot",
                        )
                else:
                    agent.backend.filesystem_manager.restore_from_snapshot_storage()
                    logger.info(
                        f"[Orchestrator._save_agent_snapshot] Restored workspace from snapshot_storage for {agent_id} (final snapshot)",
                    )
        else:
            logger.info(
                f"[Orchestrator._save_agent_snapshot] Agent {agent_id} does not have filesystem_manager",
            )

        if context_data:
            try:
                log_session_dir = get_log_session_dir()
                if log_session_dir:
                    if is_final:
                        timestamped_dir = log_session_dir / "final" / agent_id
                    else:
                        timestamped_dir = log_session_dir / agent_id / timestamp

                    timestamped_dir.mkdir(parents=True, exist_ok=True)
                    context_file = timestamped_dir / "context.txt"

                    if isinstance(context_data, dict):
                        context_file.write_text(
                            json.dumps(context_data, indent=2, default=str),
                        )
                    else:
                        context_file.write_text(str(context_data))

                    logger.info(
                        f"[Orchestrator._save_agent_snapshot] Saved context to {context_file}",
                    )
            except Exception as ce:
                logger.warning(
                    f"[Orchestrator._save_agent_snapshot] Failed to save context for {agent_id}: {ce}",
                )

        try:
            if hasattr(agent.backend, "_save_execution_trace"):
                log_session_dir = get_log_session_dir()
                if log_session_dir:
                    if is_final:
                        timestamped_dir = log_session_dir / "final" / agent_id
                    else:
                        timestamped_dir = log_session_dir / agent_id / timestamp
                    timestamped_dir.mkdir(parents=True, exist_ok=True)
                    agent.backend._save_execution_trace(timestamped_dir)

                if agent.backend.filesystem_manager and agent.backend.filesystem_manager.snapshot_storage:
                    snapshot_storage = agent.backend.filesystem_manager.snapshot_storage
                    snapshot_storage.mkdir(parents=True, exist_ok=True)
                    agent.backend._save_execution_trace(snapshot_storage)
                    logger.debug(
                        f"[Orchestrator._save_agent_snapshot] Saved execution trace to snapshot_storage: {snapshot_storage}",
                    )
        except Exception as te:
            logger.warning(
                f"[Orchestrator._save_agent_snapshot] Failed to save execution trace for {agent_id}: {te}",
            )

        # Increment answer count and reset per-round checklist budget when an
        # actual answer is being saved.  This must live here (not inside
        # _archive_agent_memories) because memory archiving early-returns when
        # the agent has no memory/ directory, which would leave answer_count
        # stuck at 0 and block submit_checklist in subsequent rounds.
        if answer_content is not None and agent_id in orch.agent_states:
            orch.agent_states[agent_id].answer_count += 1
            orch.agent_states[agent_id].checklist_calls_this_round = 0
            orch.agent_states[agent_id].pending_checklist_recheck_labels = set()

        return timestamp if not is_final else "final"

    # ------------------------------------------------------------------
    # Early-termination / interrupted-turn partial snapshots
    # ------------------------------------------------------------------

    async def save_partial_snapshots_for_early_termination(self) -> None:
        """See Orchestrator._save_partial_snapshots_for_early_termination."""
        orch = self._orchestrator
        for agent_id, state in orch.agent_states.items():
            if state.is_killed:
                continue
            try:
                # Route through orchestrator back-ref so test monkeypatches on
                # orch._save_agent_snapshot keep applying.
                await orch._save_agent_snapshot(
                    agent_id=agent_id,
                    answer_content=None,
                    vote_data=None,
                    is_final=False,
                    context_data=orch.get_last_context(agent_id),
                )
            except Exception as e:
                logger.warning(
                    f"[Orchestrator] Failed to save early-termination snapshot for {agent_id}: {e}",
                )

    def save_partial_workspace_snapshots_for_interrupted_turn(
        self,
        *,
        agent_id: str,
        backend: Any,
        timestamp: str,
        log_session_dir: Path | None,
    ) -> None:
        """See Orchestrator._save_partial_workspace_snapshots_for_interrupted_turn."""
        orch = self._orchestrator
        filesystem_manager = getattr(backend, "filesystem_manager", None)
        if not filesystem_manager:
            return

        current_workspace = filesystem_manager.get_current_workspace()
        workspace_path = Path(current_workspace) if current_workspace else None
        if not workspace_path or not workspace_path.exists() or not workspace_path.is_dir():
            return

        snapshot_storage = filesystem_manager.snapshot_storage
        workspace_has_content = orch._has_meaningful_workspace_content(workspace_path)
        snapshot_storage_has_content = orch._has_meaningful_workspace_content(snapshot_storage)
        use_snapshot_storage_for_logs = not workspace_has_content and snapshot_storage_has_content

        if not workspace_has_content and not snapshot_storage_has_content:
            logger.debug(
                f"[Orchestrator] Skipping interrupted-turn workspace snapshot for {agent_id}: no meaningful content",
            )
            return

        if snapshot_storage:
            if snapshot_storage_has_content:
                logger.info(
                    f"[Orchestrator] Preserving existing snapshot for {agent_id} during interrupted turn: " f"{snapshot_storage}",
                )
            elif workspace_has_content:
                # Publish a fresh IMMUTABLE version rather than rmtree+rebuild the
                # public path: under the versioned-snapshot scheme that path is a
                # symlink, and shutil.rmtree(symlink) raises -- which would have
                # silently dropped the interrupted-turn snapshot. See
                # SnapshotVersionStore (B1 race fix).
                store = SnapshotVersionStore.for_base(Path(snapshot_storage).parent)
                copied_count = {"n": 0}

                def _populate_interrupted(version_dir: Path, _src=workspace_path) -> None:
                    copied_count["n"] = orch._copy_workspace_contents(
                        _src,
                        version_dir,
                        replace_destination=False,
                    )

                store.publish_version(Path(snapshot_storage).name, _populate_interrupted)
                logger.info(
                    f"[Orchestrator] Saved interrupted-turn workspace snapshot for {agent_id} to " f"{snapshot_storage} ({copied_count['n']} items)",
                )

        if log_session_dir:
            source_for_logs = snapshot_storage if use_snapshot_storage_for_logs else workspace_path
            if source_for_logs:
                workspace_log_dir = log_session_dir / agent_id / timestamp / "workspace"
                copied = orch._copy_workspace_contents(
                    Path(source_for_logs),
                    workspace_log_dir,
                    replace_destination=False,
                )
                logger.info(
                    f"[Orchestrator] Saved interrupted-turn workspace log for {agent_id} to " f"{workspace_log_dir} ({copied} items)",
                )

    def save_partial_execution_traces_for_interrupted_turn(self) -> None:
        """See Orchestrator._save_partial_execution_traces_for_interrupted_turn."""
        orch = self._orchestrator
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        log_session_dir = get_log_session_dir()

        for agent_id, agent in orch.agents.items():
            backend = getattr(agent, "backend", None)
            if not backend or not hasattr(backend, "_save_execution_trace"):
                continue

            try:
                # Route through orchestrator back-ref so monkeypatches stick.
                orch._save_partial_workspace_snapshots_for_interrupted_turn(
                    agent_id=agent_id,
                    backend=backend,
                    timestamp=timestamp,
                    log_session_dir=log_session_dir,
                )
            except Exception as e:
                logger.warning(
                    f"[Orchestrator] Failed to save interrupted-turn workspace snapshot for {agent_id}: {e}",
                )

            try:
                if log_session_dir:
                    trace_dir = log_session_dir / agent_id / timestamp
                    trace_dir.mkdir(parents=True, exist_ok=True)
                    backend._save_execution_trace(trace_dir)

                if backend.filesystem_manager and backend.filesystem_manager.snapshot_storage:
                    snapshot_storage = backend.filesystem_manager.snapshot_storage
                    snapshot_storage.mkdir(parents=True, exist_ok=True)
                    backend._save_execution_trace(snapshot_storage)
            except Exception as e:
                logger.warning(
                    f"[Orchestrator] Failed to save interrupted-turn trace for {agent_id}: {e}",
                )
