"""Final-presentation streaming + timeout salvage, extracted from Orchestrator.

Owns the public-ish methods ``_present_final_answer``, ``get_final_presentation``,
``_yield_existing_answer_finalization``, ``_handle_orchestrator_timeout``, and
the shared helper ``_determine_final_agent_from_votes``. All four touch shared
Orchestrator state (``_selected_agent``, ``_final_presentation_content``,
``workflow_phase``, ``coordination_tracker``, ``_isolation_*``, etc.) — every
mutation goes through ``self._orchestrator.<field>`` and never a local copy so
collaborators like :class:`FinalResultReporter`, :class:`WorkspaceModalPresenter`,
and :class:`PostEvaluationRunner` observe the live state.

Patchable symbols (``get_event_emitter``, ``get_tracer``, ``set_current_round``,
``clear_current_round``, ``SystemMessageBuilder``, ``log_stream_chunk``,
``get_log_session_dir``, ``logger``) are looked up via the orchestrator module
so test ``patch("massgen.orchestrator.<sym>")`` hooks keep working.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from massgen.backend.base import StreamChunk
from massgen.utils import AgentStatus, CoordinationStage

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class FinalPresentationRunner:
    """Runs final-presentation streaming, timeout salvage, and existing-answer finalization."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    async def yield_existing_answer_finalization(
        self,
        *,
        selected_agent_id: str,
        vote_results: dict[str, Any],
        force_workspace_snapshot: bool = False,
    ) -> AsyncGenerator[StreamChunk]:
        """Finalize by reusing an already-available answer without a presenter pass."""
        from massgen import orchestrator as _orch_mod

        orch = self._orchestrator
        existing_answer = orch.agent_states[selected_agent_id].answer
        if not existing_answer:
            return

        agent = orch.agents.get(selected_agent_id)

        _emitter = _orch_mod.get_event_emitter()
        if _emitter:
            _emitter.emit_winner_selected(
                winner_id=selected_agent_id,
                vote_results=vote_results,
            )
            _emitter.emit_answer_locked(
                agent_id=selected_agent_id,
            )

        _orch_mod.log_stream_chunk(
            "orchestrator",
            "content",
            f"\n{existing_answer}\n",
            selected_agent_id,
        )
        yield StreamChunk(
            type="content",
            content=f"\n{existing_answer}\n",
            source=selected_agent_id,
        )
        orch._final_presentation_content = existing_answer

        if force_workspace_snapshot and agent and hasattr(agent, "backend") and agent.backend:
            filesystem_manager = getattr(agent.backend, "filesystem_manager", None)
            if filesystem_manager:
                await filesystem_manager.save_snapshot(
                    timestamp=None,
                    is_final=True,
                )

        # Restore workspace from latest per-round answer dir before final save.
        orch._restore_workspace_from_latest_answer_dir(selected_agent_id)

        final_context = orch.get_last_context(selected_agent_id)
        await orch._save_agent_snapshot(
            selected_agent_id,
            answer_content=existing_answer,
            is_final=True,
            context_data=final_context,
        )

        orch.coordination_tracker.set_final_answer(
            selected_agent_id,
            existing_answer,
            snapshot_timestamp="final",
        )

        if agent and agent.backend.filesystem_manager:
            agent.backend.filesystem_manager.path_permission_manager.compute_context_path_writes()

        orch.add_to_history("assistant", existing_answer)
        orch.save_coordination_logs()
        orch.workflow_phase = "presenting"
        await orch._show_workspace_modal_if_needed()

        _orch_mod.log_stream_chunk("orchestrator", "done", None, selected_agent_id)
        yield StreamChunk(type="done", source=selected_agent_id)

    async def present_final_answer(self) -> AsyncGenerator[StreamChunk]:
        """Present the final coordinated answer with optional post-evaluation and restart loop."""
        from massgen import orchestrator as _orch_mod

        orch = self._orchestrator

        # Safety-net drain: any criteria emissions written to stdio JSONL after
        # the last _resolve_effective_checklist_criteria call would otherwise be
        # stranded.
        orch._drain_at_session_end()

        # Select the best agent based on current state
        if not orch._selected_agent:
            orch._selected_agent = orch._determine_final_agent_from_states()

        if not orch._selected_agent:
            error_msg = "❌ Unable to provide coordinated answer - no successful agents"
            await orch._save_partial_snapshots_for_early_termination()
            orch.add_to_history("assistant", error_msg)
            _orch_mod.log_stream_chunk("orchestrator", "error", error_msg)
            yield StreamChunk(type="content", content=error_msg)
            orch.workflow_phase = "presenting"
            _orch_mod.log_stream_chunk("orchestrator", "done", None)
            yield StreamChunk(type="done")
            return

        # Get vote results for presentation
        vote_results = orch._get_vote_results()

        _emitter = _orch_mod.get_event_emitter()
        if _emitter:
            _emitter.emit_status(
                "Presenting final coordinated answer",
                level="info",
                agent_id=orch._selected_agent,
            )

        _orch_mod.log_stream_chunk("orchestrator", "content", "## 🎯 Final Coordinated Answer\n")
        yield StreamChunk(
            type="coordination" if orch.trace_classification == "strict" else "content",
            content="## 🎯 Final Coordinated Answer\n",
        )

        _orch_mod.log_stream_chunk(
            "orchestrator",
            "content",
            f"🏆 Selected Agent: {orch._selected_agent}\n",
        )
        yield StreamChunk(
            type="coordination" if orch.trace_classification == "strict" else "content",
            content=f"🏆 Selected Agent: {orch._selected_agent}\n",
        )

        # Check if we should skip final presentation (quick mode - refinement OFF)
        if orch.config.skip_final_presentation:
            agent = orch.agents.get(orch._selected_agent)
            has_write_context_paths = orch._has_write_context_paths(agent) if agent else False
            is_single_agent_mode = orch.config.skip_voting
            final_answer_strategy = orch._get_final_answer_strategy()
            should_skip_presentation = is_single_agent_mode or (final_answer_strategy == "winner_reuse" and not has_write_context_paths)

            if is_single_agent_mode and has_write_context_paths:
                _orch_mod.logger.info(
                    "[skip_final_presentation] Single agent mode with write context paths - writes already enabled at coordination start",
                )

            elif final_answer_strategy == "winner_reuse" and has_write_context_paths:
                _orch_mod.logger.info(
                    "[skip_final_presentation] Multi-agent winner_reuse with write context paths - falling through to final presentation",
                )

            elif final_answer_strategy in {"winner_present", "synthesize"}:
                _orch_mod.logger.info(
                    "[skip_final_presentation] Keeping presenter stage because final_answer_strategy=%s",
                    final_answer_strategy,
                )

            if should_skip_presentation:
                if orch.agent_states[orch._selected_agent].answer:
                    async for chunk in self.yield_existing_answer_finalization(
                        selected_agent_id=orch._selected_agent,
                        vote_results=vote_results,
                        force_workspace_snapshot=is_single_agent_mode,
                    ):
                        yield chunk
                    return
                else:
                    _orch_mod.logger.warning(
                        f"[skip_final_presentation] No existing answer for {orch._selected_agent}, falling back to normal presentation",
                    )

        # Stream the final presentation (with full tool support). Route through
        # the orchestrator delegator so tests that monkeypatch
        # ``orchestrator.get_final_presentation`` are honored.
        presentation_content = ""
        async for chunk in orch.get_final_presentation(
            orch._selected_agent,
            vote_results,
        ):
            if chunk.type == "content" and chunk.content:
                presentation_content += chunk.content
            yield chunk

        # Check if post-evaluation should run
        is_final_attempt = orch.current_attempt >= (orch.max_attempts - 1)
        should_evaluate = orch.max_attempts > 1 and not is_final_attempt

        if should_evaluate:
            final_answer_to_evaluate = orch._final_presentation_content or presentation_content
            async for chunk in orch.post_evaluate_answer(
                orch._selected_agent,
                final_answer_to_evaluate,
            ):
                yield chunk

            if orch._selected_agent:
                selected_agent = orch.agents.get(orch._selected_agent)
                if selected_agent and hasattr(
                    selected_agent.backend,
                    "end_round_tracking",
                ):
                    selected_agent.backend.end_round_tracking("post_evaluation")

        # Show workspace modal in no-git mode (runs before clear_workspace below)
        await orch._show_workspace_modal_if_needed()

        # Review isolated changes if write_mode isolation was enabled
        if orch._isolation_manager:
            selected_agent = orch.agents.get(orch._selected_agent)
            if selected_agent:
                ppm = selected_agent.backend.filesystem_manager.path_permission_manager
                for orig_path, removed_mp in orch._isolation_removed_paths.items():
                    ppm.re_add_context_path(removed_mp)

                async for chunk in orch._review_isolated_changes(
                    agent=selected_agent,
                    isolation_manager=orch._isolation_manager,
                    selected_agent_id=orch._selected_agent,
                ):
                    yield chunk

            if orch._pending_review_rework:
                _orch_mod.logger.info(
                    "[Orchestrator] Review rework requested: %s",
                    orch._pending_review_rework,
                )
            else:
                orch._isolation_manager = None
                orch._isolation_worktree_paths = {}
                orch._isolation_removed_paths = {}

            if orch.restart_pending and orch.current_attempt < (orch.max_attempts - 1):
                restart_banner = f"""

🔄 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   ORCHESTRATION RESTART (Attempt {orch.current_attempt + 2}/{orch.max_attempts})
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

REASON:
{orch.restart_reason}

INSTRUCTIONS FOR NEXT ATTEMPT:
{orch.restart_instructions}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
                _orch_mod.log_stream_chunk("orchestrator", "status", restart_banner)
                yield StreamChunk(
                    type="restart_banner",
                    content=restart_banner,
                    source="orchestrator",
                )

                orch.handle_restart()
                return

        # No restart - emit answer_locked event now that answer is confirmed
        _emitter = _orch_mod.get_event_emitter()
        if _emitter:
            _emitter.emit_answer_locked(agent_id=orch._selected_agent)

        # Clear workspace after submit since orchestration is complete
        if orch._selected_agent:
            agent = orch.agents.get(orch._selected_agent)
            if agent and agent.backend.filesystem_manager:
                agent.backend.filesystem_manager.clear_workspace()
                _orch_mod.logger.info(
                    f"[Orchestrator._present_final_answer] Cleared workspace for {orch._selected_agent} after submit",
                )

        # Add final answer to conversation history
        if orch._final_presentation_content:
            orch.add_to_history("assistant", orch._final_presentation_content)

        orch.workflow_phase = "presenting"
        _orch_mod.log_stream_chunk("orchestrator", "done", None)
        yield StreamChunk(type="done")

    async def handle_orchestrator_timeout(self) -> AsyncGenerator[StreamChunk]:
        """Handle orchestrator timeout by salvaging the best available answer."""
        from massgen import orchestrator as _orch_mod

        orch = self._orchestrator

        available_answers = {aid: state.answer for aid, state in orch.agent_states.items() if state.answer and not state.is_killed}

        current_votes = {aid: state.votes for aid, state in orch.agent_states.items() if state.votes and not state.is_killed}
        selected_agent = None
        selection_reason = "no answers available"

        if available_answers:
            if current_votes:
                selected_agent = self.determine_final_agent_from_votes(
                    current_votes,
                    available_answers,
                )
                selection_reason = "most votes"
            else:
                selected_agent = orch._determine_final_agent_from_states()
                if selected_agent not in available_answers:
                    selected_agent = next(iter(available_answers))
                selection_reason = "latest answer"

        agent_answer_summary = {}
        for aid, state in orch.agent_states.items():
            if state.is_killed:
                continue
            vote_count = 0
            for v in current_votes.values():
                if v.get("agent_id") == aid:
                    vote_count += 1
            agent_answer_summary[aid] = {
                "has_answer": bool(state.answer),
                "vote_count": vote_count,
            }

        _timeout_emitter = _orch_mod.get_event_emitter()
        if _timeout_emitter:
            _timeout_emitter.emit_orchestrator_timeout(
                timeout_reason=orch.timeout_reason or "Unknown",
                available_answers=len(available_answers),
                selected_agent=selected_agent,
                selection_reason=selection_reason,
                agent_answer_summary=agent_answer_summary,
            )

        _orch_mod.log_stream_chunk(
            "orchestrator",
            "content",
            f"\n⚠️ **Orchestrator Timeout**: {orch.timeout_reason}\n",
            orch.orchestrator_id,
        )
        yield StreamChunk(
            type="content",
            content=f"\n⚠️ **Orchestrator Timeout**: {orch.timeout_reason}\n",
            source=orch.orchestrator_id,
        )

        if len(available_answers) == 0:
            await orch._save_partial_snapshots_for_early_termination()
            _orch_mod.log_stream_chunk(
                "orchestrator",
                "error",
                "❌ No answers available from any agents due to timeout. No agents had enough time to provide responses.\n",
                orch.orchestrator_id,
            )
            yield StreamChunk(
                type="content",
                content="❌ No answers available from any agents due to timeout. No agents had enough time to provide responses.\n",
                source=orch.orchestrator_id,
            )
            orch.workflow_phase = "presenting"
            _orch_mod.log_stream_chunk("orchestrator", "done", None)
            yield StreamChunk(type="done")
            return

        orch._selected_agent = selected_agent

        vote_results = orch._get_vote_results()
        _orch_mod.log_stream_chunk(
            "orchestrator",
            "content",
            f"🎯 Using available answer from {orch._selected_agent} (selected despite timeout)\n",
            orch.orchestrator_id,
        )
        yield StreamChunk(
            type="content",
            content=f"🎯 Using available answer from {orch._selected_agent} (selected despite timeout)\n",
            source=orch.orchestrator_id,
        )

        async for chunk in self.yield_existing_answer_finalization(
            selected_agent_id=orch._selected_agent,
            vote_results=vote_results,
        ):
            yield chunk

    @staticmethod
    def determine_final_agent_from_votes(
        votes: dict[str, dict],
        agent_answers: dict[str, str],
    ) -> str:
        """Determine which agent should present the final answer based on votes."""
        if not votes:
            return next(iter(agent_answers)) if agent_answers else None

        vote_counts: dict[str, int] = {}
        for vote_data in votes.values():
            voted_for = vote_data.get("agent_id")
            if voted_for:
                vote_counts[voted_for] = vote_counts.get(voted_for, 0) + 1

        if not vote_counts:
            return next(iter(agent_answers)) if agent_answers else None

        max_votes = max(vote_counts.values())
        tied_agents = [agent_id for agent_id, count in vote_counts.items() if count == max_votes]

        for agent_id in agent_answers.keys():
            if agent_id in tied_agents:
                return agent_id

        return tied_agents[0] if tied_agents else next(iter(agent_answers)) if agent_answers else None

    async def get_final_presentation(
        self,
        selected_agent_id: str,
        vote_results: dict[str, Any],
    ) -> AsyncGenerator[StreamChunk]:
        """Ask the winning agent to present their final answer with voting context."""
        from massgen import orchestrator as _orch_mod

        orch = self._orchestrator

        if orch._presentation_started:
            _orch_mod.logger.warning(
                f"Presentation already started, skipping duplicate call for {selected_agent_id}",
            )
            yield StreamChunk(
                type="status",
                content="Presentation already in progress, skipping duplicate...",
            )
            return
        orch._presentation_started = True

        orch.coordination_tracker.start_final_round(selected_agent_id)

        if selected_agent_id not in orch.agents:
            _orch_mod.log_stream_chunk(
                "orchestrator",
                "error",
                f"Selected agent {selected_agent_id} not found",
            )
            yield StreamChunk(
                type="error",
                error=f"Selected agent {selected_agent_id} not found",
            )
            return

        agent = orch.agents[selected_agent_id]

        tracer = _orch_mod.get_tracer()
        final_round = orch.coordination_tracker.get_agent_round(selected_agent_id)
        backend_name = agent.backend.get_provider_name() if hasattr(agent.backend, "get_provider_name") else "unknown"

        span_attributes = {
            "massgen.agent_id": selected_agent_id,
            "massgen.iteration": orch.coordination_tracker.current_iteration,
            "massgen.round": final_round,
            "massgen.round_type": "presentation",
            "massgen.backend": backend_name,
            "massgen.is_winner": True,
            "massgen.vote_count": vote_results.get("vote_counts", {}).get(
                selected_agent_id,
                0,
            ),
        }

        _presentation_span_cm = tracer.span(
            f"agent.{selected_agent_id}.presentation",
            attributes=span_attributes,
        )
        _presentation_span = _presentation_span_cm.__enter__()

        _orch_mod.set_current_round(final_round, "presentation")

        # Enable write access for final agent on context paths.
        if agent.backend.filesystem_manager:
            agent.backend.filesystem_manager.path_permission_manager.snapshot_writable_context_paths()

            orch._isolation_manager = None
            orch._isolation_worktree_paths = {}
            write_mode = None
            if orch.config.coordination_config:
                write_mode = getattr(orch.config.coordination_config, "write_mode", None)

            _orch_mod.logger.info(f"[Orchestrator] write_mode check: coordination_config={bool(orch.config.coordination_config)}, write_mode={write_mode}")

            if write_mode and write_mode != "legacy":
                from massgen.filesystem_manager import IsolationContextManager

                try:
                    workspace_path = str(agent.backend.filesystem_manager.get_current_workspace())
                    winner_branch = orch._agent_current_branches.get(selected_agent_id)
                    orch._isolation_manager = IsolationContextManager(
                        session_id=orch.session_id,
                        write_mode=write_mode,
                        workspace_path=workspace_path,
                        base_commit=winner_branch,
                        branch_label="presenter",
                    )

                    ppm = agent.backend.filesystem_manager.path_permission_manager
                    orch._isolation_removed_paths = {}
                    _orch_mod.logger.info(f"[Orchestrator] Checking {len(ppm.managed_paths)} managed paths for isolation")
                    for managed_path in list(ppm.managed_paths):
                        _orch_mod.logger.debug(f"[Orchestrator] Checking path: {managed_path.path}, type={managed_path.path_type}, will_be_writable={managed_path.will_be_writable}")
                        if managed_path.path_type == "context" and managed_path.will_be_writable:
                            original_path = str(managed_path.path)
                            isolated_path = orch._isolation_manager.initialize_context(
                                original_path,
                                agent_id=selected_agent_id,
                            )
                            removed_mp = ppm.remove_context_path(original_path)
                            if removed_mp:
                                orch._isolation_removed_paths[original_path] = removed_mp
                            orch._isolation_worktree_paths[isolated_path] = original_path
                            _orch_mod.logger.info(
                                f"[Orchestrator] Isolation: worktree at {isolated_path}, original removed from agent view: {original_path}",
                            )

                except Exception as e:
                    _orch_mod.logger.warning(f"[Orchestrator] Failed to initialize isolated context: {e}, falling back to direct writes")
                    if orch._isolation_removed_paths:
                        ppm = agent.backend.filesystem_manager.path_permission_manager
                        for orig_path, removed_mp in orch._isolation_removed_paths.items():
                            ppm.re_add_context_path(removed_mp)
                        orch._isolation_removed_paths = {}
                    if orch._isolation_manager:
                        try:
                            orch._isolation_manager.cleanup_all()
                        except Exception:
                            pass
                    orch._isolation_manager = None
                    orch._isolation_worktree_paths = {}
                    yield StreamChunk(
                        type="status",
                        content="⚠️  File isolation unavailable — changes will be written directly without review.",
                        source=selected_agent_id,
                    )

            if agent.backend.filesystem_manager.docker_manager:
                skills_directory = None
                massgen_skills = []
                load_previous_session_skills = False
                if orch.config.coordination_config:
                    if orch.config.coordination_config.use_skills:
                        skills_directory = orch.config.coordination_config.skills_directory
                        massgen_skills = orch.config.coordination_config.massgen_skills or []
                        load_previous_session_skills = getattr(
                            orch.config.coordination_config,
                            "load_previous_session_skills",
                            False,
                        )
                extra_mounts = None
                if orch._isolation_worktree_paths:
                    extra_mounts = [(wt_path, wt_path, "rw") for wt_path in orch._isolation_worktree_paths]

                agent.backend.filesystem_manager.recreate_container_for_write_access(
                    skills_directory=skills_directory,
                    massgen_skills=massgen_skills,
                    load_previous_session_skills=load_previous_session_skills,
                    extra_mount_paths=extra_mounts,
                )

            agent.backend.filesystem_manager.path_permission_manager.set_context_write_access_enabled(
                True,
            )

        if hasattr(agent.backend, "set_planning_mode"):
            agent.backend.set_planning_mode(False)
            _orch_mod.logger.info(
                f"[Orchestrator] Backend planning mode DISABLED for final presentation: {selected_agent_id} - MCP tools now allowed",
            )

        temp_workspace_path = await orch._copy_all_snapshots_to_temp_workspace(
            selected_agent_id,
        )
        yield StreamChunk(
            type="debug",
            content=f"Restored workspace context for final presentation: {temp_workspace_path}",
            source=selected_agent_id,
        )

        presentation_strategy = orch._get_final_answer_strategy()

        vote_counts = vote_results.get("vote_counts", {})
        voter_details = vote_results.get("voter_details", {})
        is_tie = vote_results.get("is_tie", False)

        if presentation_strategy == "synthesize" and not vote_counts and not voter_details:
            voting_summary = "No voting round was run. You were selected as the presenter to synthesize the final answer from all completed answers."
        else:
            voting_summary = f"You received {vote_counts.get(selected_agent_id, 0)} vote(s)"
            if voter_details.get(selected_agent_id):
                reasons = [v["reason"] for v in voter_details[selected_agent_id]]
                voting_summary += f" with feedback: {'; '.join(reasons)}"

            if is_tie:
                voting_summary += " (tie-broken by registration order)"

        all_answers = {aid: s.answer for aid, s in orch.agent_states.items() if s.answer}

        normalized_voting_summary = orch._normalize_workspace_paths_in_answers(
            {selected_agent_id: voting_summary},
            selected_agent_id,
        )[selected_agent_id]
        normalized_all_answers = orch._normalize_workspace_paths_in_answers(
            all_answers,
            selected_agent_id,
        )

        is_decomposition = getattr(orch.config, "coordination_mode", "voting") == "decomposition"
        if is_decomposition:
            agent_work_sections = []
            for aid, answer in normalized_all_answers.items():
                subtask = orch._agent_subtasks.get(aid, "No specific subtask assigned")
                stop_summary = orch.agent_states[aid].stop_summary or "No stop summary"
                agent_work_sections.append(
                    f"**{aid}** (subtask: {subtask})\nStop summary: {stop_summary}\nWork: {answer}\n",
                )
            presentation_content = (
                f"ORIGINAL TASK:\n{orch.current_task or 'Task coordination'}\n\n"
                f"AGENT WORK SUMMARIES:\n{''.join(agent_work_sections)}\n\n"
                "Your job is to assemble the final deliverable from the work each agent produced. "
                "Ensure quality, fill any gaps, resolve conflicts, and answer the original query comprehensively."
            )
        else:
            if presentation_strategy == "winner_reuse":
                presentation_strategy = "winner_present"
            _pres_changedocs = orch._gather_agent_changedocs()
            presentation_content = orch.message_templates.build_final_presentation_message(
                original_task=orch.current_task or "Task coordination",
                vote_summary=normalized_voting_summary,
                all_answers=normalized_all_answers,
                selected_agent_id=selected_agent_id,
                agent_changedocs=_pres_changedocs,
                final_answer_strategy=presentation_strategy,
                had_voting=bool(vote_counts),
            )

        if orch._isolation_worktree_paths:
            worktree_instructions = "\n\nPROJECT PATHS:\n"
            for wt_path, orig_path in orch._isolation_worktree_paths.items():
                ctx_info = orch._isolation_manager.get_context_info(orig_path) if orch._isolation_manager else None
                repo_root = ctx_info.get("repo_root") if ctx_info else None
                if repo_root and repo_root != orig_path:
                    relative = os.path.relpath(orig_path, repo_root)
                    target_dir = os.path.join(wt_path, relative)
                    worktree_instructions += f"The project files are at `{target_dir}` (inside worktree at `{wt_path}`). Write all your changes there. Changes will be reviewed before being applied.\n"
                else:
                    worktree_instructions += f"The project is checked out at `{wt_path}`. Write all your changes there. Changes will be reviewed before being applied.\n"

            worktree_instructions += "\n**Scratch Space**: `.massgen_scratch/` inside the checkout is git-excluded and invisible to reviewers.\n"
            _pres_mapping = orch.coordination_tracker.get_reverse_agent_mapping()
            other_branches = {_pres_mapping.get(aid, aid): branch for aid, branch in orch._agent_current_branches.items() if aid != selected_agent_id and branch}
            if other_branches:
                worktree_instructions += "\n**Other agents' code branches** (latest only):\n"
                for label, branch in other_branches.items():
                    worktree_instructions += f"- {label}: `{branch}`\n"
                worktree_instructions += "Use `git diff <branch>` to compare, `git merge <branch>` to incorporate.\n"

            presentation_content += worktree_instructions

        agent.get_configurable_system_message()

        enable_command_execution = False
        docker_mode = False
        enable_sudo = False
        concurrent_tool_execution = False
        if hasattr(agent, "config") and agent.config:
            enable_command_execution = agent.config.backend_params.get(
                "enable_mcp_command_line",
                False,
            )
            docker_mode = agent.config.backend_params.get("command_line_execution_mode", "local") == "docker"
            enable_sudo = agent.config.backend_params.get(
                "command_line_docker_enable_sudo",
                False,
            )
            concurrent_tool_execution = agent.config.backend_params.get(
                "concurrent_tool_execution",
                False,
            )
        elif hasattr(agent, "backend") and hasattr(agent.backend, "backend_params"):
            enable_command_execution = agent.backend.backend_params.get(
                "enable_mcp_command_line",
                False,
            )
            docker_mode = agent.backend.backend_params.get("command_line_execution_mode", "local") == "docker"
            enable_sudo = agent.backend.backend_params.get(
                "command_line_docker_enable_sudo",
                False,
            )
            concurrent_tool_execution = agent.backend.backend_params.get(
                "concurrent_tool_execution",
                False,
            )
        enable_file_generation = False
        if hasattr(agent, "config") and agent.config:
            enable_file_generation = agent.config.backend_params.get(
                "enable_file_generation",
                False,
            )
        elif hasattr(agent, "backend") and hasattr(agent.backend, "backend_params"):
            enable_file_generation = agent.backend.backend_params.get(
                "enable_file_generation",
                False,
            )

        has_irreversible_actions = False
        if agent.backend.filesystem_manager:
            context_paths = agent.backend.filesystem_manager.path_permission_manager.get_context_paths()
            has_irreversible_actions = any(cp.get("permission") == "write" for cp in context_paths)

        _presenter_artifact_type = None
        if orch._plan_session_id:
            try:
                from massgen.plan_storage import PlanSession

                _ps = PlanSession(orch._plan_session_id)
                _pm = _ps.load_metadata()
                _presenter_artifact_type = getattr(_pm, "artifact_type", None)
            except Exception:
                _orch_mod.logger.opt(exception=True).warning(
                    f"[Orchestrator] Could not load artifact_type for presenter agent (plan_session={orch._plan_session_id}); artifact type context will be omitted.",
                )

        base_system_message = orch._get_system_message_builder().build_presentation_message(
            agent=agent,
            all_answers=all_answers,
            previous_turns=orch._previous_turns,
            enable_file_generation=enable_file_generation,
            has_irreversible_actions=has_irreversible_actions,
            enable_command_execution=enable_command_execution,
            docker_mode=docker_mode,
            enable_sudo=enable_sudo,
            concurrent_tool_execution=concurrent_tool_execution,
            agent_mapping=orch.coordination_tracker.get_reverse_agent_mapping(),
            artifact_type=_presenter_artifact_type,
        )

        for aid, _ in orch.agent_states.items():
            if aid != selected_agent_id:
                orch.coordination_tracker.change_status(aid, AgentStatus.COMPLETED)

        orch.coordination_tracker.set_final_agent(
            selected_agent_id,
            voting_summary,
            all_answers,
        )
        log_session_dir = _orch_mod.get_log_session_dir()
        if log_session_dir:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                orch.coordination_tracker.save_status_file,
                log_session_dir,
                orch,
            )

        presentation_messages = [
            {
                "role": "system",
                "content": base_system_message,
            },
            {"role": "user", "content": presentation_content},
        ]

        orch.agent_states[selected_agent_id].last_context = {
            "messages": presentation_messages,
            "is_final": True,
            "vote_summary": voting_summary,
            "all_answers": all_answers,
            "complete_vote_results": vote_results,
            "vote_counts": vote_counts,
            "voter_details": voter_details,
            "all_votes": {aid: state.votes for aid, state in orch.agent_states.items() if state.votes},
        }

        _orch_mod.log_stream_chunk(
            "orchestrator",
            "status",
            f"🎤  [{selected_agent_id}] presenting final answer\n",
        )
        yield StreamChunk(
            type="status",
            content=f"🎤  [{selected_agent_id}] presenting final answer\n",
        )

        answer_labels = {}
        if vote_counts:
            for aid in vote_counts.keys():
                label = orch.coordination_tracker.get_latest_answer_label(aid)
                if label:
                    answer_labels[aid] = label.replace("agent", "A")

        yield StreamChunk(
            type="final_presentation_start",
            content={
                "agent_id": selected_agent_id,
                "vote_counts": vote_counts,
                "answer_labels": answer_labels,
            },
            source=selected_agent_id,
        )

        _fp_emitter = _orch_mod.get_event_emitter()
        if _fp_emitter:
            _fp_emitter.emit_final_presentation_start(
                agent_id=selected_agent_id,
                vote_counts=vote_counts,
                answer_labels=answer_labels,
                is_tie=vote_results.get("is_tie", False) if vote_results else False,
            )

        final_round = orch.coordination_tracker.get_agent_round(selected_agent_id)
        if hasattr(agent.backend, "start_round_tracking"):
            agent.backend.start_round_tracking(
                round_number=final_round,
                round_type="presentation",
                agent_id=selected_agent_id,
            )

        presentation_content = ""
        clean_answer_content = ""
        submitted_answer = None
        final_snapshot_saved = False
        was_cancelled = False

        from massgen.tool.workflow_toolkits import NewAnswerToolkit

        _na_toolkit = NewAnswerToolkit()
        presentation_tools = _na_toolkit.get_tools({"api_format": "chat_completions"})

        try:
            async for chunk in agent.chat(
                presentation_messages,
                presentation_tools,
                reset_chat=True,
                current_stage=CoordinationStage.PRESENTATION,
                orchestrator_turn=orch._current_turn,
                previous_winners=orch._winning_agents_history.copy(),
            ):
                if hasattr(orch, "cancellation_manager") and orch.cancellation_manager and orch.cancellation_manager.is_cancelled:
                    _orch_mod.logger.info(
                        "Cancellation detected during final presentation - stopping streaming",
                    )
                    was_cancelled = True
                    yield StreamChunk(
                        type="cancelled",
                        content="Final presentation cancelled by user",
                        source=selected_agent_id,
                    )
                    break

                chunk_type = orch._get_chunk_type_value(chunk)
                orch.coordination_tracker.start_new_iteration()
                if chunk_type == "content" and chunk.content:
                    presentation_content += chunk.content
                    if not orch._is_tool_related_content(chunk.content):
                        clean_answer_content += chunk.content
                    _orch_mod.log_stream_chunk(
                        "orchestrator",
                        "content",
                        chunk.content,
                        selected_agent_id,
                    )
                    yield StreamChunk(
                        type="content",
                        content=chunk.content,
                        source=selected_agent_id,
                    )
                    if _fp_emitter:
                        _fp_emitter.emit_final_presentation_chunk(
                            agent_id=selected_agent_id,
                            content=chunk.content,
                        )
                elif chunk_type in [
                    "reasoning",
                    "reasoning_done",
                    "reasoning_summary",
                    "reasoning_summary_done",
                ]:
                    if _fp_emitter:
                        is_done = chunk_type in ("reasoning_done", "reasoning_summary_done")
                        reasoning_delta = getattr(chunk, "reasoning_delta", None)
                        reasoning_text = getattr(chunk, "reasoning_text", None)
                        summary_delta = getattr(chunk, "reasoning_summary_delta", None)
                        _thinking_content = reasoning_delta or reasoning_text or summary_delta or ""
                        if _thinking_content or is_done:
                            from massgen.events import EventType

                            _fp_emitter.emit_raw(
                                EventType.THINKING,
                                content=_thinking_content,
                                done=is_done,
                                agent_id=selected_agent_id,
                            )

                    reasoning_chunk = StreamChunk(
                        type=chunk_type,
                        content=chunk.content,
                        source=selected_agent_id,
                        reasoning_delta=getattr(chunk, "reasoning_delta", None),
                        reasoning_text=getattr(chunk, "reasoning_text", None),
                        reasoning_summary_delta=getattr(
                            chunk,
                            "reasoning_summary_delta",
                            None,
                        ),
                        reasoning_summary_text=getattr(
                            chunk,
                            "reasoning_summary_text",
                            None,
                        ),
                        item_id=getattr(chunk, "item_id", None),
                        content_index=getattr(chunk, "content_index", None),
                        summary_index=getattr(chunk, "summary_index", None),
                    )
                    _orch_mod.log_stream_chunk(
                        "orchestrator",
                        chunk.type,
                        chunk.content,
                        selected_agent_id,
                    )
                    yield reasoning_chunk
                elif chunk_type == "backend_status":
                    import json

                    status_json = json.loads(chunk.content)
                    cwd = status_json["cwd"]
                    session_id = status_json["session_id"]
                    content = f"""Final Temp Working directory: {cwd}.
    Final Session ID: {session_id}.
    """

                    _orch_mod.log_stream_chunk(
                        "orchestrator",
                        "content",
                        content,
                        selected_agent_id,
                    )
                    yield StreamChunk(
                        type="content",
                        content=content,
                        source=selected_agent_id,
                    )
                elif chunk_type == "mcp_status":
                    mcp_content = f"🔧 MCP: {chunk.content}"
                    _orch_mod.log_stream_chunk("orchestrator", "mcp_status", chunk.content, selected_agent_id)
                    yield StreamChunk(
                        type="mcp_status",
                        content=mcp_content,
                        source=selected_agent_id,
                        tool_call_id=getattr(chunk, "tool_call_id", None),
                    )
                elif chunk_type == "custom_tool_status":
                    custom_content = f"🔧 Custom Tool: {chunk.content}"
                    _orch_mod.log_stream_chunk("orchestrator", "custom_tool_status", chunk.content, selected_agent_id)
                    yield StreamChunk(
                        type="custom_tool_status",
                        content=custom_content,
                        source=selected_agent_id,
                        tool_call_id=getattr(chunk, "tool_call_id", None),
                    )
                elif chunk_type == "tool_calls":
                    chunk_tool_calls = getattr(chunk, "tool_calls", []) or []
                    for tool_call in chunk_tool_calls:
                        tool_name = agent.backend.extract_tool_name(tool_call)
                        if tool_name == "new_answer":
                            tool_args = agent.backend.extract_tool_arguments(tool_call)
                            if isinstance(tool_args, dict):
                                submitted_answer = orch._coerce_answer_content_to_text(
                                    tool_args.get("content", ""),
                                )
                            elif isinstance(tool_args, str):
                                import json as _json

                                try:
                                    submitted_answer = orch._coerce_answer_content_to_text(
                                        _json.loads(tool_args).get("content", ""),
                                    )
                                except (ValueError, AttributeError):
                                    submitted_answer = orch._coerce_answer_content_to_text(
                                        tool_args,
                                    )
                    yield StreamChunk(
                        type="tool_calls",
                        content=chunk.content,
                        source=selected_agent_id,
                        tool_calls=chunk_tool_calls,
                    )
                elif chunk_type == "hook_execution":
                    _orch_mod.log_stream_chunk(
                        "orchestrator",
                        "hook_execution",
                        str(getattr(chunk, "hook_info", "")),
                        selected_agent_id,
                    )
                    yield StreamChunk(
                        type="hook_execution",
                        content=chunk.content,
                        source=selected_agent_id,
                        hook_info=getattr(chunk, "hook_info", None),
                        tool_call_id=getattr(chunk, "tool_call_id", None),
                    )
                elif chunk_type == "done":
                    if submitted_answer and submitted_answer.strip():
                        final_answer = submitted_answer.strip()
                    elif clean_answer_content.strip():
                        final_answer = clean_answer_content.strip()
                    else:
                        final_answer = orch._coerce_answer_content_to_text(
                            orch.agent_states[selected_agent_id].answer,
                        )
                    final_context = orch.get_last_context(selected_agent_id)
                    await orch._save_agent_snapshot(
                        orch._selected_agent,
                        answer_content=final_answer,
                        is_final=True,
                        context_data=final_context,
                    )

                    orch.coordination_tracker.set_final_answer(
                        selected_agent_id,
                        final_answer,
                        snapshot_timestamp="final",
                    )

                    final_snapshot_saved = True

                    agent = orch.agents.get(orch._selected_agent)
                    if agent and hasattr(agent.backend, "end_round_tracking"):
                        agent.backend.end_round_tracking("presentation")

                    orch.save_coordination_logs()

                    _orch_mod.log_stream_chunk("orchestrator", "done", None, selected_agent_id)
                    yield StreamChunk(type="done", source=selected_agent_id)
                elif chunk_type == "error":
                    _orch_mod.log_stream_chunk(
                        "orchestrator",
                        "error",
                        chunk.error,
                        selected_agent_id,
                    )
                    yield StreamChunk(
                        type="error",
                        error=chunk.error,
                        source=selected_agent_id,
                    )
                else:
                    if hasattr(chunk, "source"):
                        _orch_mod.log_stream_chunk(
                            "orchestrator",
                            chunk_type,
                            getattr(chunk, "content", ""),
                            selected_agent_id,
                        )
                        yield StreamChunk(
                            type=chunk_type,
                            content=getattr(chunk, "content", ""),
                            source=selected_agent_id,
                            **{
                                k: v
                                for k, v in chunk.__dict__.items()
                                if k
                                not in [
                                    "type",
                                    "content",
                                    "source",
                                    "timestamp",
                                    "sequence_number",
                                ]
                            },
                        )
                    else:
                        _orch_mod.log_stream_chunk(
                            "orchestrator",
                            chunk_type,
                            getattr(chunk, "content", ""),
                            selected_agent_id,
                        )
                        yield StreamChunk(
                            type=chunk_type,
                            content=getattr(chunk, "content", ""),
                            source=selected_agent_id,
                            **{
                                k: v
                                for k, v in chunk.__dict__.items()
                                if k
                                not in [
                                    "type",
                                    "content",
                                    "source",
                                    "timestamp",
                                    "sequence_number",
                                ]
                            },
                        )

        finally:
            if not final_snapshot_saved:
                orch._restore_workspace_from_latest_answer_dir(orch._selected_agent)

                final_answer = (
                    clean_answer_content.strip()
                    if clean_answer_content.strip()
                    else orch._coerce_answer_content_to_text(
                        orch.agent_states[selected_agent_id].answer,
                    )
                )
                final_context = orch.get_last_context(selected_agent_id)
                await orch._save_agent_snapshot(
                    orch._selected_agent,
                    answer_content=final_answer,
                    is_final=True,
                    context_data=final_context,
                )

                orch.coordination_tracker.set_final_answer(
                    selected_agent_id,
                    final_answer,
                    snapshot_timestamp="final",
                )

            _display_answer = submitted_answer.strip() if submitted_answer and submitted_answer.strip() else clean_answer_content.strip()
            if _display_answer:
                orch._final_presentation_content = _display_answer

                _fa_emitter = _orch_mod.get_event_emitter()
                if _fa_emitter:
                    _fa_emitter.emit_final_answer(
                        orch._final_presentation_content,
                        agent_id=selected_agent_id,
                    )
            elif not was_cancelled:
                stored_answer = orch.agent_states[selected_agent_id].answer
                if stored_answer:
                    fallback_content = f"\n📋 Using stored answer as final presentation:\n\n{stored_answer}"
                    _orch_mod.log_stream_chunk(
                        "orchestrator",
                        "content",
                        fallback_content,
                        selected_agent_id,
                    )
                    yield StreamChunk(
                        type="content",
                        content=fallback_content,
                        source=selected_agent_id,
                    )
                    orch._final_presentation_content = stored_answer
                else:
                    _orch_mod.log_stream_chunk(
                        "orchestrator",
                        "error",
                        "\n❌ No content generated for final presentation and no stored answer available.",
                        selected_agent_id,
                    )
                    yield StreamChunk(
                        type="content",
                        content="\n❌ No content generated for final presentation and no stored answer available.",
                        source=selected_agent_id,
                    )
            else:
                stored_answer = orch.agent_states[selected_agent_id].answer
                if stored_answer:
                    orch._final_presentation_content = stored_answer

            if _fp_emitter:
                _fp_emitter.emit_final_presentation_end(agent_id=selected_agent_id)

            orch.coordination_tracker.change_status(
                selected_agent_id,
                AgentStatus.COMPLETED,
            )

            if agent.backend.filesystem_manager:
                agent.backend.filesystem_manager.path_permission_manager.compute_context_path_writes()

            if hasattr(agent.backend, "token_usage") and agent.backend.token_usage:
                token_usage = agent.backend.token_usage
                _presentation_span.set_attribute(
                    "massgen.usage.input",
                    token_usage.input_tokens or 0,
                )
                _presentation_span.set_attribute(
                    "massgen.usage.output",
                    token_usage.output_tokens or 0,
                )
                _presentation_span.set_attribute(
                    "massgen.usage.reasoning",
                    token_usage.reasoning_tokens or 0,
                )
                _presentation_span.set_attribute(
                    "massgen.usage.cached_input",
                    token_usage.cached_input_tokens or 0,
                )
                _presentation_span.set_attribute(
                    "massgen.usage.cost",
                    round(token_usage.estimated_cost or 0, 6),
                )

            try:
                _presentation_span_cm.__exit__(None, None, None)
            except ValueError as e:
                if "context" not in str(e).lower() and "detach" not in str(e).lower():
                    _orch_mod.logger.debug(
                        f"Unexpected ValueError closing presentation span: {e}",
                    )

            _orch_mod.clear_current_round()
