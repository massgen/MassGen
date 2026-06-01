"""Round-evaluator pre-round runner, extracted from Orchestrator.

Owns the orchestrator-managed round_evaluator gate that runs between answer
rounds: building the evaluator task brief, collecting context paths, emitting
spawn events, spawning the evaluator subagent, handling
failure/timeout/degraded paths, and formatting the result for injection into
the parent's next-round context.

All cross-method calls inside this collaborator route through
``self._orchestrator.<method>(...)`` so that test monkeypatches on the
orchestrator instance take effect (e.g.
``test_execution_trace_analyzer.py`` patches
``_emit_round_evaluator_spawn_event`` /
``_get_round_evaluator_context_paths`` / ``_build_round_evaluator_task``,
and ``test_auto_trace_analysis.py`` patches the spawn event emitter).

The pure static formatters (``_format_round_evaluator_result_block_static``
and ``_format_round_evaluator_timeout_block_static``) are re-exposed as
``@staticmethod`` on the Orchestrator class as well, because
``test_round_evaluator_loop.py`` calls them unbound via
``Orchestrator._format_round_evaluator_result_block_static(...)``.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from massgen.events import EventType as StructuredEventType
from massgen.logger_config import logger
from massgen.utils import ActionType

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator
    from massgen.subagent.models import RoundEvaluatorResult, SubagentResult


def _get_event_emitter():
    """Lazy lookup via ``massgen.orchestrator`` so test patches at that path fire.

    Several tests patch ``massgen.orchestrator.get_event_emitter`` and expect
    the patched emitter to receive events emitted from the round-evaluator
    flow. Importing the symbol directly from ``massgen.logger_config`` would
    bypass that patch.
    """
    from massgen import orchestrator as _orch_mod

    return _orch_mod.get_event_emitter()


class RoundEvaluatorRunner:
    """Run the orchestrator-managed round_evaluator gate between answer rounds."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    # ------------------------------------------------------------------
    # CONTEXT.md / task brief / delegate targets / context paths
    # ------------------------------------------------------------------
    def ensure_context_md_for_round_evaluator(
        self,
        workspace_root: Any,
        parent_agent_id: str,
    ) -> None:
        """Write a CONTEXT.md into the parent workspace for the round evaluator."""
        context_path = Path(workspace_root) / "CONTEXT.md"
        if context_path.exists():
            return  # Parent already wrote one — don't overwrite

        task_summary = (self._orchestrator.current_task or "Task coordination")[:2000]
        content = f"# Task Context\n\n## Task\n{task_summary}\n"
        try:
            context_path.write_text(content, encoding="utf-8")
            logger.info(
                f"[Orchestrator] Wrote CONTEXT.md to {workspace_root} for round evaluator",
            )
        except Exception as e:
            logger.warning(f"[Orchestrator] Failed to write CONTEXT.md: {e}")

    def build_round_evaluator_task(
        self,
        parent_agent_id: str,
        answers: dict[str, str],
    ) -> str:
        """Build the orchestrator-owned round_evaluator task brief."""
        orch = self._orchestrator
        criteria_agent_id = parent_agent_id if orch._is_decomposition_mode() else None
        checklist_items, _, verify_by, _, _anti, _score_anchors = orch._resolve_effective_checklist_criteria(criteria_agent_id)

        criteria_lines: list[str] = []
        for idx, item in enumerate(checklist_items or [], start=1):
            criterion_id = f"E{idx}"
            verify_line = ""
            if verify_by and verify_by.get(criterion_id):
                verify_line = f" (verify_by: {verify_by[criterion_id]})"
            criteria_lines.append(f"- {criterion_id}: {item}{verify_line}")
        criteria_block = "\n".join(criteria_lines) if criteria_lines else "- No explicit checklist criteria configured"

        normalized_answers = orch._normalize_workspace_paths_in_answers(
            answers,
            viewing_agent_id=parent_agent_id,
        )
        answer_sections: list[str] = []
        for revision_idx, answering_agent_id in enumerate(sorted(normalized_answers.keys()), start=1):
            label = f"Current answer (revision {revision_idx})" if len(normalized_answers) == 1 else f"Answer revision {revision_idx}"
            answer_sections.append(
                f"## {label}\n\n{normalized_answers[answering_agent_id]}",
            )

        answer_block = "\n\n".join(answer_sections) if answer_sections else "No answers available."
        coord_cfg = getattr(orch.config, "coordination_config", None)
        transformation_pressure = getattr(
            coord_cfg,
            "round_evaluator_transformation_pressure",
            "balanced",
        )
        pressure_lines = [
            "TRANSFORMATION PRESSURE:",
            f"- Current setting: {transformation_pressure}.",
        ]
        if transformation_pressure == "gentle":
            pressure_lines.append(
                "- Exploit the current thesis longer and only escalate to a thesis shift when ceiling evidence is clear.",
            )
        elif transformation_pressure == "aggressive":
            pressure_lines.append(
                "- Search harder for a higher-leverage thesis or frontier move. Incremental-only follow-up or local convergence needs stronger justification.",
            )
        else:
            pressure_lines.append(
                "- Default balance: pursue a stronger thesis once the current line is plateauing, but do not chase novelty for its own sake.",
            )
        pressure_lines.append(
            "- Regardless of pressure, correctness-critical work still comes first and you must resolve your diagnosis into one committed next-round thesis.",
        )
        pressure_block = "\n".join(pressure_lines) + "\n\n"
        delegate_targets = orch._get_parent_round_evaluator_delegate_targets()
        if delegate_targets:
            delegation_block = (
                "PARENT DELEGATION OPTIONS:\n"
                f"- The parent can delegate next-round work to these specialized subagents: {', '.join(delegate_targets)}.\n"
                "- These execution hints are for the parent's next round, not for this evaluator child runtime.\n"
                "- Base `execution` in `next_tasks.json` on what the parent can delegate, not by whether you can spawn subagents inside this evaluator run.\n"
                "- Do not emit `round_evaluator` as a delegate target.\n\n"
            )
        else:
            delegation_block = (
                "PARENT DELEGATION OPTIONS:\n"
                "- No parent-specialized subagents are available for delegation in the next round.\n"
                "- Keep execution hints inline unless the task brief explicitly provides a reusable subagent_id.\n\n"
            )
        evolved_prompt_block = ""
        current_evolved = orch._evolved_prompts.get(parent_agent_id)
        if current_evolved:
            evolved_prompt_block = "PREVIOUS EVOLVED PROMPT (for context — do NOT rewrite from this; " "always rewrite from the ORIGINAL TASK above):\n" f"{current_evolved}\n\n"

        return (
            "Produce one very critical cross-answer critique packet for the parent agent.\n\n"
            f"ORIGINAL TASK:\n{orch._original_task or orch.current_task or 'Task coordination'}\n\n"
            f"{evolved_prompt_block}"
            "EVALUATION CRITERIA:\n"
            f"{criteria_block}\n\n"
            f"{pressure_block}"
            f"{delegation_block}"
            "CANDIDATE ANSWERS:\n"
            f"{answer_block}\n\n"
            "Write the authoritative critique packet to `critique_packet.md`. "
            "Write machine-readable verdict metadata to `verdict.json`. "
            "When iteration is needed, write the implementation handoff to `next_tasks.json`. "
            "Keep your `answer` minimal and do not provide parent workflow recommendations."
        )

    def get_parent_round_evaluator_delegate_targets(self) -> list[str]:
        """Return specialized subagent types the parent can delegate to next round."""
        orch = self._orchestrator
        coord = getattr(orch.config, "coordination_config", None)
        if not coord or not getattr(coord, "enable_subagents", False):
            return []

        from massgen.subagent.type_scanner import DEFAULT_SUBAGENT_TYPES

        active_types = getattr(coord, "subagent_types", None)
        if active_types is None:
            active_types = DEFAULT_SUBAGENT_TYPES

        targets: list[str] = []
        seen: set[str] = set()
        for raw_type in active_types or []:
            type_name = str(raw_type or "").strip()
            if not type_name:
                continue
            lowered = type_name.lower()
            analytical_types = {"round_evaluator", "execution_trace_analyzer"}
            if lowered in analytical_types or lowered in seen:
                continue
            seen.add(lowered)
            targets.append(type_name)
        return targets

    def get_round_evaluator_context_paths(
        self,
        parent_agent_id: str,
        temp_workspace_path: str | None = None,
    ) -> list[str]:
        """Collect explicit read-only context paths for the round_evaluator task."""
        orch = self._orchestrator
        context_paths: list[str] = []
        seen: set[str] = set()

        def _add(path_value: Any) -> None:
            normalized = str(path_value or "").strip()
            if not normalized or normalized in seen:
                return
            resolved = str(Path(normalized).resolve()) if normalized else normalized
            if resolved in seen:
                return
            if not Path(resolved).exists():
                return
            seen.add(resolved)
            context_paths.append(resolved)

        _add(temp_workspace_path)

        agent = orch.agents.get(parent_agent_id)
        filesystem_manager = getattr(getattr(agent, "backend", None), "filesystem_manager", None)
        if filesystem_manager is not None:
            _add(getattr(filesystem_manager, "agent_temporary_workspace", None))
            get_workspace = getattr(filesystem_manager, "get_current_workspace", None)
            if callable(get_workspace):
                try:
                    workspace_path = get_workspace()
                except Exception:
                    workspace_path = None
                _add(workspace_path)
            _add(getattr(filesystem_manager, "cwd", None))

        _add(orch._agent_temporary_workspace)
        return context_paths

    # ------------------------------------------------------------------
    # Event emission
    # ------------------------------------------------------------------
    def emit_round_evaluator_spawn_event(
        self,
        *,
        phase: str,
        agent_id: str,
        tool_call_id: str,
        round_number: int,
        args: dict[str, Any],
        result: dict[str, Any] | None = None,
        elapsed_seconds: float = 0.0,
        is_error: bool = False,
        status: str = "success",
    ) -> None:
        """Emit tool events so programmatic subagent launches reuse the TUI pipeline."""
        orch = self._orchestrator
        emitter = _get_event_emitter()
        if not emitter:
            return

        if phase == "start":
            emitter.emit_raw(
                StructuredEventType.TOOL_START,
                agent_id=agent_id,
                round_number=round_number,
                tool_id=tool_call_id,
                tool_name="spawn_subagents",
                args=args,
                server_name=orch._subagent_server_name(agent_id),
            )
            return

        emitter.emit_raw(
            StructuredEventType.TOOL_COMPLETE,
            agent_id=agent_id,
            round_number=round_number,
            tool_id=tool_call_id,
            tool_name="spawn_subagents",
            result=json.dumps(result or {}, ensure_ascii=False),
            elapsed_seconds=elapsed_seconds,
            status=status,
            is_error=is_error,
        )

    # ------------------------------------------------------------------
    # Result formatting (instance + static)
    # ------------------------------------------------------------------
    def format_round_evaluator_result_block(
        self,
        subagent_id: str,
        result: SubagentResult | RoundEvaluatorResult,
        auto_injected: bool = False,
    ) -> str:
        """Format the blocking round_evaluator result for next-round prompt injection."""
        from massgen.subagent.models import RoundEvaluatorResult

        if isinstance(result, RoundEvaluatorResult):
            evaluator_result = result
        else:
            evaluator_result = RoundEvaluatorResult.from_subagent_result(result)
        return RoundEvaluatorRunner.format_round_evaluator_result_block_static(
            subagent_id=subagent_id,
            evaluator_result=evaluator_result,
            auto_injected=auto_injected,
        )

    @staticmethod
    def _strip_absolute_workspace_paths(text: str) -> str:
        """Replace absolute workspace paths with relative basenames."""
        return re.sub(
            r"/\S*?/(?:workspace|workspaces|subagents)/\S*?/([A-Za-z0-9_.-]+\.(?:md|json|txt|py|png|svg|yaml|yml))\b",
            r"`\1`",
            text,
        )

    @staticmethod
    def format_round_evaluator_result_block_static(
        subagent_id: str,
        evaluator_result: RoundEvaluatorResult,
        auto_injected: bool = False,
    ) -> str:
        """Format the blocking round_evaluator result for next-round prompt injection."""
        status = evaluator_result.status
        packet_text = evaluator_result.clean_packet_text or evaluator_result.packet_text or "(no packet produced)"
        critique_path = evaluator_result.primary_artifact_path or "(missing critique_packet.md path)"
        verdict_path = evaluator_result.verdict_artifact_path or "(missing verdict.json path)"
        next_tasks_path = evaluator_result.next_tasks_artifact_path or "(missing next_tasks.json path)"

        if auto_injected:
            sanitized_packet = RoundEvaluatorRunner._strip_absolute_workspace_paths(packet_text)
            strategy_lines: list[str] = []
            if evaluator_result.next_tasks_objective:
                strategy_lines.append(f"Chosen objective: {evaluator_result.next_tasks_objective}")
            if evaluator_result.next_tasks_primary_strategy:
                strategy_lines.append(f"Chosen strategy: {evaluator_result.next_tasks_primary_strategy}")
            if evaluator_result.next_tasks_why_this_strategy:
                strategy_lines.append(f"Why this strategy: {evaluator_result.next_tasks_why_this_strategy}")
            if evaluator_result.next_tasks_strategy_mode:
                strategy_lines.append(f"Strategy mode: {evaluator_result.next_tasks_strategy_mode}")
            if evaluator_result.next_tasks_incremental_override_reason:
                strategy_lines.append(
                    "Incremental override reason: " + evaluator_result.next_tasks_incremental_override_reason,
                )
            if evaluator_result.next_tasks_deprioritize_or_remove:
                strategy_lines.append(
                    "Deprioritize or remove: " + ", ".join(evaluator_result.next_tasks_deprioritize_or_remove),
                )
            success_contract = evaluator_result.next_tasks_success_contract or {}
            if success_contract:
                outcome_statement = str(success_contract.get("outcome_statement") or "").strip()
                quality_bar = str(success_contract.get("quality_bar") or "").strip()
                fail_if_any = [str(item).strip() for item in success_contract.get("fail_if_any", []) if str(item).strip()]
                required_evidence = [str(item).strip() for item in success_contract.get("required_evidence", []) if str(item).strip()]
                strategy_lines.append("Success contract:")
                if outcome_statement:
                    strategy_lines.append(f"- Outcome: {outcome_statement}")
                if quality_bar:
                    strategy_lines.append(f"- Quality bar: {quality_bar}")
                if fail_if_any:
                    strategy_lines.append(f"- Fail if any: {'; '.join(fail_if_any)}")
                if required_evidence:
                    strategy_lines.append(f"- Required evidence: {'; '.join(required_evidence)}")
            strategy_block = ("\n".join(strategy_lines) + "\n\n") if strategy_lines else ""
            return (
                "============================================================\n"
                f"ROUND EVALUATOR RESULT (status: {status})\n"
                "============================================================\n"
                "The orchestrator ran one blocking `round_evaluator` before this round.\n"
                "The evaluator's tasks have been auto-injected into your task plan.\n\n"
                f'<evaluator_summary subagent_id="{subagent_id}" status="{status}">\n'
                f"{sanitized_packet}\n"
                "</evaluator_summary>\n\n"
                f"{strategy_block}"
                "Workflow:\n"
                "1. Call `get_task_plan` — the evaluator's tasks are already there.\n"
                "2. Reference the authoritative evaluator artifacts when needed:\n"
                f"   - critique_packet.md: {critique_path}\n"
                f"   - verdict.json: {verdict_path}\n"
                f"   - next_tasks.json: {next_tasks_path}\n"
                "3. If the task plan includes correctness-critical tasks or tasks tied to\n"
                "   explicit correctness criteria, do those first.\n"
                "4. Then execute the remaining higher-order work and follow\n"
                "   `implementation_guidance` on each task as written.\n"
                "5. Finish with the final preserve/regression verification so\n"
                "   preserved strengths remain intact and earlier correctness fixes still\n"
                "   pass after later changes.\n"
                "6. If the deliverable is a pure text artifact, put the final\n"
                "   artifact body directly in `new_answer.content`.\n"
                "7. Otherwise, call `new_answer` with your usual concise summary.\n\n"
                "Do NOT call `submit_checklist`.\n"
                "Do NOT call `draft_approach`.\n"
                "Do NOT write a second diagnostic report.\n"
                "Do NOT spawn another `round_evaluator`.\n"
                "============================================================"
            )
        else:
            instructions = (
                "IMPORTANT: This evaluator packet is your sole diagnostic basis for\n"
                f"submit_checklist. Pass this exact path as report_path: {critique_path}\n"
                "Do NOT run a separate self-evaluation or author a second diagnostic\n"
                "report from scratch.\n"
            )

        return (
            "============================================================\n"
            f"ROUND EVALUATOR RESULT (status: {status})\n"
            "============================================================\n"
            "The orchestrator ran one blocking `round_evaluator` before this round.\n\n"
            f"{instructions}\n"
            f'<evaluator_packet subagent_id="{subagent_id}" status="{status}">\n'
            f"{packet_text}\n"
            "</evaluator_packet>\n"
            "============================================================"
        )

    @staticmethod
    def format_round_evaluator_timeout_block_static(
        subagent_id: str,
        error_message: str,
    ) -> str:
        """Format a degraded timeout notice when no evaluator packet was produced."""
        normalized_error = str(error_message or "round_evaluator timed out before producing a packet").strip()
        return (
            "============================================================\n"
            "ROUND EVALUATOR RESULT (status: degraded)\n"
            "============================================================\n"
            "The orchestrator ran one blocking `round_evaluator` before this round,\n"
            "but it timed out before producing `critique_packet.md`.\n\n"
            f'<evaluator_timeout subagent_id="{subagent_id}" status="degraded">\n'
            f"{normalized_error}\n"
            "</evaluator_timeout>\n\n"
            "For this answer set, the orchestrator is degrading to the normal parent-owned checklist flow.\n"
            "Do NOT wait for evaluator artifacts for this revision.\n"
            "You may call `submit_checklist` and `draft_approach` as usual.\n"
            "============================================================"
        )

    # ------------------------------------------------------------------
    # Failure / timeout handlers
    # ------------------------------------------------------------------
    def handle_round_evaluator_gate_failure(
        self,
        *,
        parent_agent_id: str,
        latest_labels: tuple[str, ...],
        display_round: int,
        emitter: Any,
        elapsed_seconds: float,
        failure_payload: dict[str, Any] | None,
    ) -> bool | str:
        """Record a failed evaluator launch and decide whether to retry or abort."""
        orch = self._orchestrator
        failure_key = (parent_agent_id, latest_labels)
        attempt_number = orch._round_evaluator_launch_failures.get(failure_key, 0) + 1
        orch._round_evaluator_launch_failures[failure_key] = attempt_number

        payload = failure_payload if isinstance(failure_payload, dict) else {}
        error_message = str(
            payload.get("error") or payload.get("output") or "round_evaluator gate failed before producing a packet",
        ).strip()

        logger.warning(
            "[Orchestrator] round_evaluator gate failed for %s on attempt %s/%s: %s",
            parent_agent_id,
            attempt_number,
            orch._ROUND_EVALUATOR_MAX_LAUNCH_FAILURES,
            error_message,
        )

        if emitter:
            emitter.emit_raw(
                StructuredEventType.ROUND_EVALUATOR_STAGE_COMPLETE,
                agent_id=parent_agent_id,
                round_number=display_round,
                status="error",
                execution_time_seconds=elapsed_seconds,
                packet_text_length=0,
                error=error_message,
            )

        if attempt_number < orch._ROUND_EVALUATOR_MAX_LAUNCH_FAILURES:
            return False

        terminal_message = "Managed round evaluator failed " f"{attempt_number} time(s) for the current answer set. Last error: {error_message}"
        agent_state = orch.agent_states.get(parent_agent_id)
        if agent_state is not None:
            agent_state.is_killed = True
            agent_state.error_reason = terminal_message
        orch.coordination_tracker.track_agent_action(
            parent_agent_id,
            ActionType.ERROR,
            terminal_message,
        )
        return "terminal_error"

    def handle_round_evaluator_timeout_degraded(
        self,
        *,
        parent_agent_id: str,
        latest_labels: tuple[str, ...],
        display_round: int,
        emitter: Any,
        elapsed_seconds: float,
        first_result: SubagentResult,
        evaluator_result: RoundEvaluatorResult,
    ) -> bool:
        """Allow coordination to continue when the evaluator timed out without a packet."""
        orch = self._orchestrator
        timeout_message = str(
            evaluator_result.error or first_result.error or "round_evaluator timed out before producing a packet",
        ).strip()

        logger.warning(
            "[Orchestrator] round_evaluator timed out for %s without artifacts; degrading to normal checklist flow: %s",
            parent_agent_id,
            timeout_message,
        )

        if emitter:
            emitter.emit_raw(
                StructuredEventType.ROUND_EVALUATOR_STAGE_COMPLETE,
                agent_id=parent_agent_id,
                round_number=display_round,
                status="degraded",
                execution_time_seconds=elapsed_seconds,
                packet_text_length=0,
                error=timeout_message,
            )

        orch._queue_round_start_context_block(
            parent_agent_id,
            RoundEvaluatorRunner.format_round_evaluator_timeout_block_static(
                first_result.subagent_id,
                timeout_message,
            ),
        )
        orch._round_evaluator_launch_failures.pop((parent_agent_id, latest_labels), None)
        orch._round_evaluator_completed_labels[parent_agent_id] = latest_labels
        return True

    # ------------------------------------------------------------------
    # Main entry: pre-round gate
    # ------------------------------------------------------------------
    async def run_round_evaluator_pre_round_if_needed(
        self,
        answers: dict[str, str],
        conversation_context: dict[str, Any] | None = None,
    ) -> bool | str:
        """Run the round_evaluator gate between answer rounds when configured."""
        _ = conversation_context
        orch = self._orchestrator
        if not orch._is_round_evaluator_gate_enabled():
            return True
        if not answers:
            return True
        if len(orch.agents) != 1:
            return True
        if not all(state.answer is not None for state in orch.agent_states.values()):
            return True

        parent_agent_id = next(iter(orch.agents.keys()))
        latest_labels = orch._get_round_evaluator_latest_labels(answers)
        if not latest_labels:
            return True
        if orch._round_evaluator_completed_labels.get(parent_agent_id) == latest_labels:
            return True

        upcoming_round = orch._get_round_evaluator_upcoming_round(parent_agent_id)
        display_round = orch._get_round_evaluator_display_round(parent_agent_id)
        orch._set_round_evaluator_task_mode(parent_agent_id, enabled=False)

        temp_workspace_path = await orch._copy_all_snapshots_to_temp_workspace(parent_agent_id)
        coord_cfg = getattr(orch.config, "coordination_config", None)
        evaluator_refine = bool(coord_cfg and getattr(coord_cfg, "round_evaluator_refine", False))
        spawn_task = orch._build_round_evaluator_task(parent_agent_id, answers)
        spawn_context_paths = orch._get_round_evaluator_context_paths(
            parent_agent_id,
            temp_workspace_path=temp_workspace_path,
        )
        pressure_label = getattr(coord_cfg, "round_evaluator_transformation_pressure", "balanced") or "balanced"
        display_subagent_type = f"round_evaluator·{pressure_label}" if pressure_label != "balanced" else "round_evaluator"
        configured_timeout = getattr(coord_cfg, "subagent_default_timeout", 300) if coord_cfg else 300
        task_payload: dict[str, Any] = {
            "subagent_id": f"round_eval_r{upcoming_round}",
            "task": spawn_task,
            "subagent_type": "round_evaluator",
            "context_paths": spawn_context_paths,
            "timeout_seconds": configured_timeout,
        }
        orch._sync_stdio_checklist_state_from_specs(parent_agent_id)
        consumed_personas = orch._consume_evaluator_personas()
        if consumed_personas:
            task_payload["metadata"] = {"evaluator_personas": consumed_personas}
        spawn_args: dict[str, Any] = {
            "tasks": [task_payload],
            "background": False,
            "refine": evaluator_refine,
        }

        tui_task_payload = {**task_payload, "subagent_type": display_subagent_type}
        tui_spawn_args = {**spawn_args, "tasks": [tui_task_payload]}

        tool_call_id = f"round_evaluator_pre_round_{parent_agent_id}_r{upcoming_round}_{int(time.time() * 1000)}"
        emitter = _get_event_emitter()
        if emitter:
            emitter.emit_raw(
                StructuredEventType.ROUND_EVALUATOR_STAGE_START,
                agent_id=parent_agent_id,
                round_number=display_round,
            )
        orch._emit_round_evaluator_spawn_event(
            phase="start",
            agent_id=parent_agent_id,
            tool_call_id=tool_call_id,
            round_number=display_round,
            args=tui_spawn_args,
        )

        started_at = time.time()
        raw_result = await orch._direct_spawn_subagents(
            parent_agent_id=parent_agent_id,
            tasks=[task_payload],
            refine=evaluator_refine,
        )
        elapsed_seconds = max(0.0, time.time() - started_at)
        normalized_result = raw_result if isinstance(raw_result, dict) else {}
        success = bool(normalized_result.get("success"))
        orch._emit_round_evaluator_spawn_event(
            phase="complete",
            agent_id=parent_agent_id,
            tool_call_id=tool_call_id,
            round_number=display_round,
            args=spawn_args,
            result=normalized_result,
            elapsed_seconds=elapsed_seconds,
            is_error=not success,
            status="success" if success else "error",
        )

        display = getattr(orch.coordination_ui, "display", None) if orch.coordination_ui else None
        if display and hasattr(display, "notify_runtime_subagent_completed"):
            try:
                display.notify_runtime_subagent_completed(
                    agent_id=parent_agent_id,
                    subagent_id=f"round_eval_r{upcoming_round}",
                    call_id=tool_call_id,
                    status="completed" if success else "failed",
                )
            except Exception:
                pass

        from massgen.subagent.models import RoundEvaluatorResult, SubagentResult

        results = normalized_result.get("results")
        first_result: SubagentResult | None = None
        evaluator_result: RoundEvaluatorResult | None = None

        if not success:
            salvaged = False
            if isinstance(results, list) and results:
                try:
                    first_result = SubagentResult.from_dict(results[0])
                    if first_result.answer:
                        logger.info(
                            "[Orchestrator] round_evaluator spawn reported " "failure (status=%s) but first result has a " "recovered answer — using it for %s",
                            first_result.status,
                            parent_agent_id,
                        )
                        salvaged = True
                    else:
                        evaluator_result = RoundEvaluatorResult.from_subagent_result(
                            first_result,
                            elapsed=elapsed_seconds,
                        )
                        if evaluator_result.status == "success" and evaluator_result.packet_text:
                            logger.info(
                                "[Orchestrator] round_evaluator spawn reported failure (status=%s) but authoritative artifacts were recovered for %s",
                                first_result.status,
                                parent_agent_id,
                            )
                            salvaged = True
                        elif first_result.status == "timeout" and evaluator_result.status == "degraded":
                            degraded_ok = orch._handle_round_evaluator_timeout_degraded(
                                parent_agent_id=parent_agent_id,
                                latest_labels=latest_labels,
                                display_round=display_round,
                                emitter=emitter,
                                elapsed_seconds=elapsed_seconds,
                                first_result=first_result,
                                evaluator_result=evaluator_result,
                            )
                            if degraded_ok is True and orch._should_spawn_trace_analyzer(parent_agent_id):
                                await orch._spawn_trace_analyzer_background(parent_agent_id)
                            return degraded_ok
                except Exception:
                    logger.warning(
                        "[Orchestrator] Failed to parse salvage result for %s",
                        parent_agent_id,
                        exc_info=True,
                    )

            if not salvaged:
                return orch._handle_round_evaluator_gate_failure(
                    parent_agent_id=parent_agent_id,
                    latest_labels=latest_labels,
                    display_round=display_round,
                    emitter=emitter,
                    elapsed_seconds=elapsed_seconds,
                    failure_payload=normalized_result,
                )
        if not isinstance(results, list) or not results:
            return orch._handle_round_evaluator_gate_failure(
                parent_agent_id=parent_agent_id,
                latest_labels=latest_labels,
                display_round=display_round,
                emitter=emitter,
                elapsed_seconds=elapsed_seconds,
                failure_payload={
                    "success": False,
                    "operation": "spawn_subagents",
                    "error": "round_evaluator returned no result payloads",
                },
            )

        try:
            first_result = first_result or SubagentResult.from_dict(results[0])
        except Exception as exc:
            return orch._handle_round_evaluator_gate_failure(
                parent_agent_id=parent_agent_id,
                latest_labels=latest_labels,
                display_round=display_round,
                emitter=emitter,
                elapsed_seconds=elapsed_seconds,
                failure_payload={
                    "success": False,
                    "operation": "spawn_subagents",
                    "error": f"Failed to parse round_evaluator result payload: {exc}",
                },
            )

        evaluator_result = evaluator_result or RoundEvaluatorResult.from_subagent_result(
            first_result,
            elapsed=elapsed_seconds,
        )

        if evaluator_result.status != "success" or not evaluator_result.packet_text:
            return orch._handle_round_evaluator_gate_failure(
                parent_agent_id=parent_agent_id,
                latest_labels=latest_labels,
                display_round=display_round,
                emitter=emitter,
                elapsed_seconds=elapsed_seconds,
                failure_payload={
                    "success": False,
                    "operation": "spawn_subagents",
                    "error": evaluator_result.error or "round_evaluator produced no packet",
                },
            )

        auto_injected = False
        if evaluator_result.verdict == "iterate" and evaluator_result.task_plan_source == "next_tasks_artifact":
            task_plan = orch.build_task_plan_from_evaluator_verdict(evaluator_result)
            if task_plan:
                orch._write_planning_injection(parent_agent_id, task_plan)
                auto_injected = True
                logger.info(
                    f"[Orchestrator] Auto-injected {len(task_plan)} tasks from evaluator next_tasks artifact for {parent_agent_id}",
                )
        elif evaluator_result.verdict == "iterate":
            logger.info(
                "[Orchestrator] Evaluator requested iteration for %s without a valid next_tasks.json artifact; using checklist fallback",
                parent_agent_id,
            )
        elif evaluator_result.verdict == "converged":
            logger.info(
                "[Orchestrator] Evaluator verdict: converged for %s",
                parent_agent_id,
            )
        else:
            logger.debug(
                "[Orchestrator] Missing or invalid verdict.json for %s; using checklist fallback",
                parent_agent_id,
            )

        if evaluator_result.evolved_prompt:
            orch._evolved_prompts[parent_agent_id] = evaluator_result.evolved_prompt
            logger.info(
                f"[Orchestrator] Evolved prompt stored for {parent_agent_id} "
                f"({len(evaluator_result.evolved_prompt)} chars, "
                f"rationale: {(evaluator_result.evolved_prompt_rationale or '')[:100]})",
            )
            _display = getattr(orch.coordination_ui, "display", None) if orch.coordination_ui else None
            if _display and hasattr(_display, "notify_prompt_improved"):
                try:
                    _display.notify_prompt_improved(evaluator_result.evolved_prompt)
                except Exception:
                    pass

        orch._set_round_evaluator_task_mode(
            parent_agent_id,
            enabled=auto_injected,
            primary_artifact_path=evaluator_result.primary_artifact_path or "",
            verdict_artifact_path=evaluator_result.verdict_artifact_path or "",
            next_tasks_artifact_path=evaluator_result.next_tasks_artifact_path or "",
            objective=evaluator_result.next_tasks_objective or "",
            primary_strategy=evaluator_result.next_tasks_primary_strategy or "",
            why_this_strategy=evaluator_result.next_tasks_why_this_strategy or "",
            strategy_mode=evaluator_result.next_tasks_strategy_mode or "",
            incremental_override_reason=evaluator_result.next_tasks_incremental_override_reason or "",
            success_contract=evaluator_result.next_tasks_success_contract or {},
            deprioritize_or_remove=evaluator_result.next_tasks_deprioritize_or_remove or [],
        )

        orch._queue_round_start_context_block(
            parent_agent_id,
            orch._format_round_evaluator_result_block(
                first_result.subagent_id,
                evaluator_result,
                auto_injected=auto_injected,
            ),
        )

        if first_result.workspace_path:
            parent_agent = orch.agents.get(parent_agent_id)
            if parent_agent and hasattr(parent_agent, "backend"):
                fs_mgr = getattr(parent_agent.backend, "filesystem_manager", None)
                if fs_mgr:
                    ppm = getattr(fs_mgr, "path_permission_manager", None)
                    if ppm:
                        ppm.add_context_paths([{"path": first_result.workspace_path, "permission": "read"}])
                        logger.info(
                            f"[Orchestrator] Added evaluator workspace as read-only context for {parent_agent_id}: {first_result.workspace_path}",
                        )

        if emitter:
            emitter.emit_raw(
                StructuredEventType.ROUND_EVALUATOR_STAGE_COMPLETE,
                agent_id=parent_agent_id,
                round_number=display_round,
                status=evaluator_result.status,
                execution_time_seconds=elapsed_seconds,
                packet_text_length=len(evaluator_result.packet_text or ""),
            )

        orch._round_evaluator_launch_failures.pop((parent_agent_id, latest_labels), None)
        orch._round_evaluator_completed_labels[parent_agent_id] = latest_labels

        if orch._should_spawn_trace_analyzer(parent_agent_id):
            await orch._spawn_trace_analyzer_background(parent_agent_id)

        return True
