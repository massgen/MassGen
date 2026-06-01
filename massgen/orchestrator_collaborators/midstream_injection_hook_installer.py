"""Mid-stream injection / hook installer collaborator.

Owns mechanical helpers that manage agent stream lifecycle, restart-pending
state, framework MCP state clearing, plan progress computation, and the
mid-stream tool-result injection payload builder.

NOTE: This is the FIRST slice of a much larger cluster (the orchestrator's
"god-class core"). For safety, only six pure helpers are extracted in this
pass; the remaining hook-installation methods stay on Orchestrator for now
and will be moved in a follow-up. All shared state is touched via the
``self._orchestrator`` back-ref so Orchestrator + sibling collaborators
keep observing consistent state.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from massgen.logger_config import logger

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class MidStreamInjectionHookInstaller:
    """Mid-stream injection helpers + (future) hook installation."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    async def close_agent_stream(
        self,
        agent_id: str,
        active_streams: dict[str, AsyncGenerator],
    ) -> None:
        """Close and remove an agent stream safely."""
        if agent_id in active_streams:
            try:
                await active_streams[agent_id].aclose()
            except Exception:
                pass  # Ignore cleanup errors
            del active_streams[agent_id]

    def check_restart_pending(self, agent_id: str) -> bool:
        """Check if agent should restart and yield restart message if needed. This will always be called when exiting out of _stream_agent_execution()."""
        restart_pending = self._orchestrator.agent_states[agent_id].restart_pending
        return restart_pending

    def should_defer_restart_for_first_answer(self, agent_id: str) -> bool:
        """Check if restart/injection should be deferred for first-answer protection.

        Each agent is guaranteed to complete at least one full round and produce
        an answer before being restarted or injected with other agents' work.
        """
        state = self._orchestrator.agent_states.get(agent_id)
        if state is None:
            return False
        return state.answer is None

    async def clear_framework_mcp_state(self, agent_id: str) -> None:
        """Clear in-memory state of framework MCP servers before agent restart.

        This ensures stateful MCPs like planning don't retain old data across
        answer submissions. Currently clears:
        - Task plans (planning MCP)
        """
        orch = self._orchestrator
        agent = orch.agents.get(agent_id)
        if not agent or not hasattr(agent.backend, "_mcp_client") or not agent.backend._mcp_client:
            return

        # Find the planning MCP tool name for this agent
        planning_tool_name = None
        for tool_name in agent.backend._mcp_functions.keys():
            if "clear_task_plan" in tool_name and orch._planning_server_name(agent_id) in tool_name:
                planning_tool_name = tool_name
                break

        if planning_tool_name:
            try:
                logger.info(
                    f"[Orchestrator] Clearing task plan for {agent_id} via {planning_tool_name}",
                )
                result, _ = await agent.backend._execute_mcp_function_with_retry(
                    planning_tool_name,
                    "{}",  # No arguments needed
                )
                logger.info(
                    f"[Orchestrator] Clear task plan result for {agent_id}: {result}",
                )
            except Exception as e:
                logger.warning(
                    f"[Orchestrator] Failed to clear task plan for {agent_id}: {e}",
                )

    def compute_plan_progress_stats(self, workspace_path: str) -> dict[str, Any] | None:
        """Compute task/requirement progress stats for an agent's workspace.

        Reads the agent's tasks/plan.json or tasks/spec.json and computes how
        many items are completed vs total.  Works in both plan-and-execute mode
        and spec execution mode.
        """
        try:
            workspace = Path(workspace_path)
            tasks_plan = workspace / "tasks" / "plan.json"
            tasks_spec = workspace / "tasks" / "spec.json"

            # Check for plan.json first, then spec.json
            if tasks_plan.exists():
                artifact_file = tasks_plan
                items_key = "tasks"
            elif tasks_spec.exists():
                artifact_file = tasks_spec
                items_key = "requirements"
            else:
                return None

            # Read artifact
            tasks_data = json.loads(artifact_file.read_text())
            tasks = tasks_data.get(items_key, [])
            total_tasks = len(tasks)

            if total_tasks == 0:
                return None

            # Count by status (verified tasks count as completed for progress)
            completed = sum(1 for t in tasks if t.get("status") in ("completed", "verified"))
            in_progress = sum(1 for t in tasks if t.get("status") == "in_progress")
            pending = sum(1 for t in tasks if t.get("status") == "pending")

            return {
                "total": total_tasks,
                "completed": completed,
                "in_progress": in_progress,
                "pending": pending,
                "percent_complete": round(100 * completed / total_tasks, 1) if total_tasks > 0 else 0,
            }
        except Exception as e:
            logger.debug(f"[Orchestrator] Could not compute plan progress: {e}")
            return None

    def build_tool_result_injection(
        self,
        agent_id: str,
        new_answers: dict[str, str],
        existing_answers: dict[str, str] | None = None,
    ) -> str:
        """Build compact injection content for appending to tool results.

        This creates a lighter-weight update message designed to be embedded
        in tool result content rather than sent as a separate user message.
        Used for mid-stream injection of peer updates during agent execution.
        """
        orch = self._orchestrator
        existing_answers = existing_answers or {}

        # Normalize workspace paths for this agent's perspective
        normalized = orch._normalize_workspace_paths_in_answers(
            new_answers,
            viewing_agent_id=agent_id,
        )

        # Get viewing agent's temporary workspace path
        temp_workspace_base = None
        viewing_agent = orch.agents.get(agent_id)
        if viewing_agent and viewing_agent.backend.filesystem_manager:
            temp_workspace_base = str(
                viewing_agent.backend.filesystem_manager.agent_temporary_workspace,
            )

        # Create anonymous mapping (consistent with CURRENT ANSWERS format across all agents)
        agent_mapping = orch.coordination_tracker.get_reverse_agent_mapping()
        context_labels = orch.coordination_tracker.get_agent_context_labels(agent_id)

        # Format answers with workspace paths
        lines = []
        updated_agents = []
        new_agents = []
        updated_header_entries = []
        new_header_entries = []
        transition_lines = []

        for aid, answer in normalized.items():
            anon_id = agent_mapping.get(aid, f"agent_{aid}")
            is_update = aid in existing_answers

            if is_update:
                updated_agents.append(anon_id)
            else:
                new_agents.append(anon_id)

            # Build explicit answer-label transitions so agents can score newest labels.
            latest_revisions = orch.coordination_tracker.answers_by_agent.get(aid, [])
            latest_label = str(getattr(latest_revisions[-1], "label", "")) if latest_revisions else ""
            old_label = ""
            if latest_label and "." in latest_label:
                label_prefix = latest_label.split(".", 1)[0] + "."
                old_label = next((lbl for lbl in context_labels if lbl.startswith(label_prefix)), "")

            if is_update and old_label and latest_label and old_label != latest_label:
                updated_header_entries.append(f"{anon_id} ({old_label} -> {latest_label})")
                transition_lines.append(
                    f"  - {anon_id}: {old_label} -> {latest_label}",
                )
            elif not is_update and latest_label:
                new_header_entries.append(f"{anon_id} ({latest_label})")
                transition_lines.append(
                    f"  - {anon_id}: now available as {latest_label}",
                )
            elif is_update:
                # Fallback if labels are unavailable in edge cases
                updated_header_entries.append(anon_id)
            else:
                new_header_entries.append(anon_id)

            # Truncate long answers for injection context
            truncated = answer[:500] + "..." if len(answer) > 500 else answer

            # Include workspace path for file access
            workspace_path = os.path.join(temp_workspace_base, anon_id) if temp_workspace_base else f"temp_workspaces/{anon_id}"
            lines.append(f"  [{anon_id}] (workspace: {workspace_path}):")

            # Compute and include progress stats if in plan execution mode
            progress = self.compute_plan_progress_stats(workspace_path)
            if progress:
                lines.append(
                    f"    📊 Progress: {progress['completed']}/{progress['total']} tasks completed "
                    f"({progress['percent_complete']}%) | {progress['in_progress']} in progress | {progress['pending']} pending",
                )
                lines.append("    ⚠️  Note: Progress stats are INFORMATIONAL - evaluate the DELIVERABLE quality, not task count")

            lines.append(f"    {truncated}")
            lines.append("")

        # Build header based on what changed
        if updated_agents and new_agents:
            header = f"[UPDATE: {', '.join(new_header_entries)} submitted new answer(s); " f"{', '.join(updated_header_entries)} updated their answer(s)]"
        elif updated_agents:
            header = f"[UPDATE: {', '.join(updated_header_entries)} updated their answer(s)]"
        else:
            header = f"[UPDATE: {', '.join(new_header_entries)} submitted new answer(s)]"

        # Use different framing for decomposition mode vs voting mode
        is_decomposition = getattr(orch.config, "coordination_mode", "voting") == "decomposition"
        is_checklist_mode = getattr(orch.config, "voting_sensitivity", "balanced") == "checklist_gated"

        if is_decomposition:
            injection_parts = [
                "",
                "=" * 60,
                "UPDATE: ANOTHER AGENT SUBMITTED WORK",
                "=" * 60,
                "",
                header,
                "",
                "ANSWER LABEL UPDATES:",
                *(transition_lines or ["  - (no label change details available)"]),
                "",
                *lines,
                "=" * 60,
            ]
            if is_checklist_mode:
                injection_parts.extend(
                    [
                        "CHECKLIST-GATED ACTIONS (REQUIRED):",
                        "=" * 60,
                        "",
                        "1. Read and understand their full work — maintain awareness of the entire project state",
                        "2. Keep ownership-first: spend most effort on your subtask; touch other areas only for adjacent integration",
                        "3. Integrate boundary dependencies (interfaces/contracts/shared assets) without taking over unrelated scopes",
                        "4. Use submit_checklist with the newest labels shown above before deciding to `stop` or continue iterating",
                        "5. If checklist was already accepted this round and this update is new:",
                        "   - Preferred: submit only the injected newest labels (delta recheck)",
                        "   - Also allowed: submit all latest labels in your current context",
                        "6. If submit_checklist returns a validation error, fix payload/report and call submit_checklist again",
                        "7. If checklist returns iterate (new_answer), call draft_approach, implement, then call new_answer",
                        "8. Call `stop` only after the latest checklist result supports stopping and you have no new work to share",
                        "",
                        "DO NOT ignore this update - checklist flow must be re-run on newest labels.",
                        "=" * 60,
                    ],
                )
            else:
                injection_parts.extend(
                    [
                        "RECOMMENDED ACTIONS:",
                        "=" * 60,
                        "",
                        "1. Read and understand their full work — maintain awareness of the entire project state",
                        "2. Keep ownership-first: spend most effort on your subtask; touch other areas only for adjacent integration",
                        "3. Integrate boundary dependencies (interfaces/contracts/shared assets) without taking over unrelated scopes",
                        "4. Continue refining your own work — fix issues, improve quality, incorporate insights",
                        "5. If you submit `new_answer`, include concrete deliverables + validation evidence + integration notes",
                        "6. Call `stop` only when you've reviewed everything and are satisfied — no new work to share",
                        "",
                        "=" * 60,
                    ],
                )
        else:
            injection_parts = [
                "",
                "=" * 60,
                "⚠️  IMPORTANT: NEW ANSWER RECEIVED - ACTION REQUIRED",
                "=" * 60,
                "",
                header,
                "",
                "ANSWER LABEL UPDATES:",
                *(transition_lines or ["  - (no label change details available)"]),
                "",
                *lines,
                "=" * 60,
            ]
            if is_checklist_mode:
                injection_parts.extend(
                    [
                        "CHECKLIST-GATED ACTIONS (REQUIRED):",
                        "=" * 60,
                        "",
                        "1. Add a task: 'Evaluate injected answer label updates and re-run checklist'",
                        "2. Read injected workspace files, then compare to your current work",
                        "3. Use submit_checklist with the newest labels shown above",
                        "4. If checklist was already accepted this round and this update is new:",
                        "   - Preferred: submit only the injected newest labels (delta recheck)",
                        "   - Also allowed: submit all latest labels in your current context",
                        "5. If submit_checklist returns a validation error, fix payload/report and call submit_checklist again",
                        "6. If checklist returns iterate (new_answer), call draft_approach, implement, then call new_answer",
                        "DO NOT ignore this update - checklist flow must be re-run on newest labels.",
                        "=" * 60,
                    ],
                )
            else:
                injection_parts.extend(
                    [
                        "REQUIRED ACTION - You MUST do one of the following:",
                        "=" * 60,
                        "",
                        "1. **ADD A TASK** to your plan: 'Evaluate agent answer(s) and decide next action'",
                        "   - Use update_task_status or create a new task to track this evaluation",
                        "   - Read their workspace files (paths above) to understand their solution",
                        "   - Compare their approach to yours",
                        "",
                        "2. **THEN CHOOSE ONE**:",
                        "   a) VOTE for their answer if it's complete and correct (use vote tool)",
                        "   b) BUILD on their work - improve/extend it and submit YOUR enhanced answer",
                        "   c) MERGE approaches - combine the best parts of their work with yours",
                        "   d) CONTINUE your own approach if you believe it's better",
                        "",
                        "DO NOT ignore this update - you must explicitly evaluate and decide!",
                        "=" * 60,
                    ],
                )

        # Append essential files from injected agents so the receiving agent
        # can evaluate without re-reading from workspace
        essential_files_block = orch._build_essential_files_for_injection(
            agent_id,
            list(new_answers.keys()),
        )
        if essential_files_block:
            injection_parts.extend(["", essential_files_block])

        return "\n".join(injection_parts)
