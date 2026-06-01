"""Final result reporting helpers, extracted from Orchestrator.

These methods aggregate vote/answer/workspace state into the various
external-facing result dicts and best-effort shutdown snapshots.  They
remain pure read-only over orchestrator state apart from the fallback
``_ensure_final_directory_on_shutdown`` which writes a final/ directory
on the filesystem.

The orchestrator keeps thin delegators so external callers and other
collaborators (WorkspaceModalPresenter, FinalPresentationRunner,
OrchestratorTimeoutFinalizer, IsolatedChangeReviewer) continue to call
``orch._get_vote_results`` / ``orch._resolve_final_workspace_path`` and
the public API methods unchanged.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from massgen.filesystem_manager import has_meaningful_content
from massgen.logger_config import get_log_session_dir, get_log_session_root, logger

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class FinalResultReporter:
    """Aggregate final/partial coordination results for external consumers."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    # ---- Shared helpers (also delegated to by other collaborators) ----

    def resolve_final_workspace_path(self, agent_id: str | None) -> str | None:
        """Resolve the final workspace path from the log directory."""
        if not agent_id:
            return None
        log_dir = get_log_session_dir()
        if not log_dir:
            return None

        log_path = Path(log_dir)
        # Try turn_*/attempt_*/final/agent_*/workspace (most common)
        for turn_dir in sorted(log_path.glob("turn_*"), reverse=True):
            for attempt_dir in sorted(turn_dir.glob("attempt_*"), reverse=True):
                ws = attempt_dir / "final" / agent_id / "workspace"
                if ws.exists() and ws.is_dir():
                    return str(ws)

        # Fallback: direct final/ directory
        ws = log_path / "final" / agent_id / "workspace"
        if ws.exists() and ws.is_dir():
            return str(ws)

        return None

    def get_vote_results(self) -> dict[str, Any]:
        """Get current vote results and statistics."""
        orch = self._orchestrator
        agent_answers = {aid: state.answer for aid, state in orch.agent_states.items() if state.answer}
        votes = {aid: state.votes for aid, state in orch.agent_states.items() if state.votes}

        # Count votes for each agent
        vote_counts: dict[str, int] = {}
        voter_details: dict[str, list[dict[str, Any]]] = {}

        for voter_id, vote_data in votes.items():
            voted_for = vote_data.get("agent_id")
            if voted_for:
                vote_counts[voted_for] = vote_counts.get(voted_for, 0) + 1
                if voted_for not in voter_details:
                    voter_details[voted_for] = []
                voter_details[voted_for].append(
                    {
                        "voter": voter_id,
                        "reason": vote_data.get("reason", "No reason provided"),
                    },
                )

        # Determine winner
        winner = None
        is_tie = False
        if vote_counts:
            max_votes = max(vote_counts.values())
            tied_agents = [agent_id for agent_id, count in vote_counts.items() if count == max_votes]
            is_tie = len(tied_agents) > 1

            # Break ties by agent registration order
            for agent_id in agent_answers.keys():
                if agent_id in tied_agents:
                    winner = agent_id
                    break

            if not winner:
                winner = tied_agents[0] if tied_agents else None

        agent_mapping = orch.coordination_tracker.get_anonymous_agent_mapping()

        return {
            "vote_counts": vote_counts,
            "voter_details": voter_details,
            "winner": winner,
            "is_tie": is_tie,
            "total_votes": len(votes),
            "agents_with_answers": len(agent_answers),
            "agents_voted": len([v for v in votes.values() if v.get("agent_id")]),
            "agent_mapping": agent_mapping,
        }

    def determine_final_agent_from_states(self) -> str | None:
        """Determine final agent based on current agent states."""
        orch = self._orchestrator
        agents_with_answers = {aid: state.answer for aid, state in orch.agent_states.items() if state.answer}

        if not agents_with_answers:
            return None

        latest_agent = None
        latest_ts = -1.0
        for aid in agents_with_answers:
            agent_answers = orch.coordination_tracker.answers_by_agent.get(aid, [])
            if agent_answers:
                last_answer = agent_answers[-1]
                if last_answer.timestamp > latest_ts:
                    latest_ts = last_answer.timestamp
                    latest_agent = aid

        return latest_agent or next(iter(agents_with_answers))

    # ---- Public-API methods (delegated unchanged from Orchestrator) ----

    def get_final_result(self) -> dict[str, Any] | None:
        """Get final result for session persistence."""
        orch = self._orchestrator
        if not orch._selected_agent or not orch._final_presentation_content:
            return None

        workspace_path = None
        log_session_dir = get_log_session_dir()
        if log_session_dir:
            final_workspace = log_session_dir / "final" / orch._selected_agent / "workspace"
            if final_workspace.exists():
                workspace_path = str(final_workspace)
                logger.info(f"[Orchestrator] Using final log workspace for session persistence: {workspace_path}")

        return {
            "final_answer": orch._final_presentation_content,
            "winning_agent_id": orch._selected_agent,
            "workspace_path": workspace_path,
            "winning_agents_history": orch._winning_agents_history.copy(),
        }

    def get_partial_result(self) -> dict[str, Any] | None:
        """Get partial coordination result for interrupted sessions."""
        orch = self._orchestrator
        # Best-effort trace flush
        orch._save_partial_execution_traces_for_interrupted_turn()

        answers: dict[str, Any] = {}
        for agent_id, state in orch.agent_states.items():
            if state.answer:
                answers[agent_id] = {
                    "answer": state.answer,
                    "has_voted": state.has_voted,
                    "votes": state.votes if state.has_voted else None,
                    "answer_count": state.answer_count,
                }

        workspaces = orch.get_all_agent_workspaces()

        def has_files_recursive(directory: Path) -> bool:
            if not directory.is_dir():
                return False
            for item in directory.iterdir():
                if item.is_file():
                    return True
                if item.is_dir() and has_files_recursive(item):
                    return True
            return False

        workspaces_with_content: dict[str, str] = {}
        for agent_id, ws_path in workspaces.items():
            if ws_path and Path(ws_path).exists():
                ws = Path(ws_path)
                if has_files_recursive(ws):
                    workspaces_with_content[agent_id] = ws_path

        if not answers and not workspaces_with_content:
            return None

        active_agents = [state for state in orch.agent_states.values() if not state.is_killed]
        voting_complete = all(state.has_voted for state in active_agents) if active_agents else False

        result: dict[str, Any] = {
            "status": "incomplete",
            "phase": orch.workflow_phase,
            "current_task": orch.current_task,
            "answers": answers,
            "workspaces": workspaces_with_content,
            "selected_agent": orch._selected_agent,
            "voting_complete": voting_complete,
        }

        if orch.coordination_tracker:
            try:
                result["coordination_tracker"] = orch.coordination_tracker.to_dict()
            except Exception:
                pass

        self.ensure_final_directory_on_shutdown(answers, workspaces_with_content)

        return result

    def ensure_final_directory_on_shutdown(
        self,
        answers: dict[str, Any],
        workspaces: dict[str, str],
    ) -> None:
        """Best-effort creation of final/ directory during shutdown."""
        orch = self._orchestrator
        log_session_dir = get_log_session_dir()
        if not log_session_dir:
            return

        selected = orch._selected_agent or self.determine_final_agent_from_states()
        if not selected:
            return

        final_dir = log_session_dir / "final" / selected
        if final_dir.exists():
            return

        agent = orch.agents.get(selected)
        if not agent:
            return
        fm = getattr(agent.backend, "filesystem_manager", None) if hasattr(agent, "backend") else None
        if not fm:
            return

        source: Path | None = None
        snapshot_storage = getattr(fm, "snapshot_storage", None)
        if snapshot_storage and Path(snapshot_storage).exists():
            if has_meaningful_content(Path(snapshot_storage)):
                source = Path(snapshot_storage)
        if source is None:
            ws = fm.get_current_workspace() if hasattr(fm, "get_current_workspace") else getattr(fm, "cwd", None)
            if ws and Path(ws).exists():
                source = Path(ws)
        if source is None:
            return

        try:
            workspace_dest = final_dir / "workspace"
            workspace_dest.mkdir(parents=True, exist_ok=True)
            for item in source.iterdir():
                if item.is_symlink():
                    continue
                if item.is_file():
                    shutil.copy2(item, workspace_dest / item.name)
                elif item.is_dir():
                    shutil.copytree(
                        item,
                        workspace_dest / item.name,
                        symlinks=True,
                        ignore_dangling_symlinks=True,
                    )

            answer_data = answers.get(selected)
            if answer_data and answer_data.get("answer"):
                answer_content = answer_data["answer"]
                dest_workspace = str(final_dir / "workspace")
                original_cwd = getattr(fm, "cwd", None)
                if original_cwd:
                    answer_content = answer_content.replace(
                        str(original_cwd),
                        dest_workspace,
                    )
                    resolved_cwd = str(Path(original_cwd).resolve())
                    if resolved_cwd != str(original_cwd):
                        answer_content = answer_content.replace(
                            resolved_cwd,
                            dest_workspace,
                        )
                if str(source) != dest_workspace:
                    answer_content = answer_content.replace(
                        str(source),
                        dest_workspace,
                    )
                (final_dir / "answer.txt").write_text(answer_content)

            logger.info(
                "[Orchestrator] Created final/ directory on shutdown for %s at %s",
                selected,
                final_dir,
            )
        except Exception as exc:
            logger.warning(
                "[Orchestrator] Failed to create final/ directory on shutdown: %s",
                exc,
            )

    def get_all_agent_workspaces(self) -> dict[str, str | None]:
        """Get workspace paths for all agents."""
        orch = self._orchestrator
        workspaces: dict[str, str | None] = {}
        for agent_id, agent in orch.agents.items():
            if hasattr(agent, "backend") and hasattr(agent.backend, "filesystem_manager"):
                fm = agent.backend.filesystem_manager
                if fm:
                    workspaces[agent_id] = str(fm.get_current_workspace())
                else:
                    workspaces[agent_id] = None
            else:
                workspaces[agent_id] = None
        return workspaces

    def get_coordination_result(self) -> dict[str, Any]:
        """Get comprehensive coordination result for API consumption."""
        orch = self._orchestrator

        log_root = None
        log_session_dir = None
        final_path = None
        try:
            log_root = get_log_session_root()
            log_session_dir = get_log_session_dir()
            final_path = log_session_dir / "final"
        except Exception:
            pass

        answers: list[dict[str, Any]] = []
        if orch.coordination_tracker and orch.coordination_tracker.snapshot_mappings:
            for label, mapping in orch.coordination_tracker.snapshot_mappings.items():
                if mapping.get("type") == "answer":
                    answer_dir = None
                    if log_session_dir and mapping.get("path"):
                        answer_dir = str(log_session_dir / Path(mapping["path"]).parent)

                    agent_id = mapping.get("agent_id")
                    content = None
                    if agent_id and agent_id in orch.agent_states:
                        content = orch.agent_states[agent_id].answer

                    answers.append(
                        {
                            "label": label,
                            "agent_id": agent_id,
                            "answer_path": answer_dir,
                            "content": content,
                        },
                    )

        vote_results = self.get_vote_results()

        total_usage = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        for agent in orch.agents.values():
            backend = getattr(agent, "backend", None)
            if backend and hasattr(backend, "token_usage") and backend.token_usage:
                if hasattr(backend, "finalize_token_tracking"):
                    try:
                        backend.finalize_token_tracking()
                    except Exception:
                        pass
                tu = backend.token_usage
                prompt = tu.input_tokens + tu.cached_input_tokens + tu.cache_creation_tokens
                completion = tu.output_tokens + tu.reasoning_tokens
                total_usage["prompt_tokens"] += prompt
                total_usage["completion_tokens"] += completion
                total_usage["total_tokens"] += prompt + completion

        return {
            "final_answer": orch._final_presentation_content or "",
            "selected_agent": orch._selected_agent,
            "log_directory": str(log_root) if log_root else None,
            "final_answer_path": str(final_path) if final_path else None,
            "answers": answers,
            "vote_results": vote_results,
            "usage": total_usage,
            "is_orchestrator_timeout": orch.is_orchestrator_timeout,
            "timeout_reason": orch.timeout_reason,
        }

    def get_status(self) -> dict[str, Any]:
        """Get current orchestrator status."""
        orch = self._orchestrator
        vote_results = self.get_vote_results()

        return {
            "session_id": orch.session_id,
            "workflow_phase": orch.workflow_phase,
            "current_task": orch.current_task,
            "selected_agent": orch._selected_agent,
            "final_presentation_content": orch._final_presentation_content,
            "vote_results": vote_results,
            "agents": {
                aid: {
                    "agent_status": agent.get_status(),
                    "coordination_state": {
                        "answer": state.answer,
                        "has_voted": state.has_voted,
                    },
                }
                for aid, (agent, state) in zip(
                    orch.agents.keys(),
                    zip(orch.agents.values(), orch.agent_states.values()),
                )
            },
            "conversation_length": len(orch.conversation_history),
        }
