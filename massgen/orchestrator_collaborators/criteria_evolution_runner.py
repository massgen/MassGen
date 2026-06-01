"""Criteria evolution runner, extracted from Orchestrator.

Owns the criteria-evolution pipeline:

    bootstrap criteria -> gate decision -> proposal task -> spawn proposers ->
    synthesis task -> spawn synthesizer -> apply evolved criteria -> write memory

All cross-method calls inside this collaborator route through
``self._orchestrator.<method>(...)`` so that test monkey-patches on the
orchestrator instance (e.g. patching ``_direct_spawn_subagents`` or
``_should_evolve_criteria`` in ``test_evolving_criteria.py``) take effect, and
so that already-extracted collaborators (``SubagentToolInjector``,
``ChecklistGateManager``, ``BootstrapCriteriaEngine``) are reached via their
existing orchestrator delegators.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from massgen.events import EventType as StructuredEventType
from massgen.logger_config import get_event_emitter, logger

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class CriteriaEvolutionRunner:
    """Coordinates the multi-round criteria-evolution gate."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------
    def bootstrap_evolution_criteria_from_config(self) -> None:
        """Populate _generated_evaluation_criteria from active criteria.

        Called when evolving_criteria is enabled but the evaluation_criteria_generator
        was not used. Converts inline, preset, or default checklist criteria into
        GeneratedCriterion objects so evolution has something to work with.
        """
        orch = self._orchestrator
        items, cats, verify_by, source, anti_patterns, score_anchors = orch._resolve_effective_checklist_criteria()
        if not items:
            return

        from massgen.evaluation_criteria_generator import GeneratedCriterion

        if cats:
            id_list = list(cats.keys())
        else:
            id_list = [f"E{i + 1}" for i in range(len(items))]

        orch._generated_evaluation_criteria = [
            GeneratedCriterion(
                id=id_list[i] if i < len(id_list) else f"E{i + 1}",
                text=text,
                category=(cats or {}).get(id_list[i] if i < len(id_list) else "", "standard"),
                verify_by=(verify_by or {}).get(id_list[i] if i < len(id_list) else ""),
                anti_patterns=(anti_patterns or {}).get(id_list[i] if i < len(id_list) else ""),
                score_anchors=(score_anchors or {}).get(id_list[i] if i < len(id_list) else ""),
            )
            for i, text in enumerate(items)
        ]

    # ------------------------------------------------------------------
    # Gate decision
    # ------------------------------------------------------------------
    def should_evolve_criteria(self, current_answers: dict[str, str] | None = None) -> bool:
        """Return True if criteria evolution gate should run."""
        orch = self._orchestrator
        coord = getattr(orch.config, "coordination_config", None)
        if not coord or not getattr(coord, "evolving_criteria", False):
            return False
        if not getattr(orch, "_generated_evaluation_criteria", None):
            orch._bootstrap_evolution_criteria_from_config()
        if not getattr(orch, "_generated_evaluation_criteria", None):
            return False
        any_round2 = any(getattr(state, "restart_count", 0) >= 1 for state in orch.agent_states.values())
        if not any_round2:
            return False
        max_evolutions = getattr(coord, "evolving_criteria_max_evolutions", 2)
        if orch._criteria_evolution_count >= max_evolutions:
            return False
        if current_answers is not None:
            label_tuple = tuple(sorted(current_answers.keys()))
            if label_tuple in orch._criteria_evolution_completed_labels:
                return False
        threshold = getattr(coord, "evolving_criteria_score_threshold", 8)
        min_high = getattr(coord, "evolving_criteria_min_high_score_count", 2)
        high_count = 0
        for state in orch.agent_states.values():
            history = getattr(state, "checklist_history", None) or []
            if not history:
                continue
            latest = history[-1]
            items_detail = latest.get("items_detail") or []
            for item in items_detail:
                score = item.get("score") or 0
                if score >= threshold:
                    high_count += 1
            if high_count >= min_high:
                return True
        return False

    # ------------------------------------------------------------------
    # Task builders
    # ------------------------------------------------------------------
    def build_criteria_evolution_proposal_task(
        self,
        agent_id: str,
        evolution_data: dict[str, Any],
    ) -> str:
        """Build the task string for a criteria_evolver subagent."""
        orch = self._orchestrator
        original_task = evolution_data["original_task"]
        evolution_number = evolution_data["evolution_number"]
        criteria = evolution_data["current_criteria"]
        histories = evolution_data["checklist_histories"]
        trace_paths: dict[str, Path | None] = evolution_data["trace_paths"]

        criteria_block = orch._format_criteria_for_prompt(criteria)
        score_table = orch._format_score_history_table(histories)

        trace_lines: list[str] = []
        for aid, tpath in trace_paths.items():
            label = f"Agent {aid}" + (" (YOUR trace)" if aid == agent_id else "")
            if tpath:
                trace_lines.append(f"- {label}: read the file at `{tpath}`")
            else:
                trace_lines.append(f"- {label}: (no trace available for this agent)")
        trace_file_block = "\n".join(trace_lines)

        return (
            f"You are performing criteria evolution #{evolution_number} for a multi-agent task.\n\n"
            f"ORIGINAL TASK:\n{original_task}\n\n"
            f"CURRENT EVALUATION CRITERIA:\n{criteria_block}\n\n"
            f"CHECKLIST SCORE HISTORY (all agents, all rounds):\n{score_table}\n\n"
            "EXECUTION TRACES — read each file below using your file-reading tool:\n"
            f"{trace_file_block}\n\n"
            "Based on the score patterns and execution traces, propose evolved criteria that raise "
            "the bar on dimensions where agents are consistently scoring 8+ out of 10. "
            "Leave criteria that are still discriminating (showing score spread across agents) "
            "unchanged. Output JSON as described in your instructions."
        )

    def build_criteria_evolution_synthesis_task(
        self,
        proposals: list[dict[str, Any]],
        current_criteria: list[Any],
        original_task: str,
    ) -> str:
        """Build the task string for the criteria_evolution_synthesizer subagent."""
        orch = self._orchestrator
        criteria_block = orch._format_criteria_for_prompt(current_criteria)

        proposal_lines: list[str] = []
        for i, prop in enumerate(proposals, start=1):
            prop_json = json.dumps(prop, indent=2)
            proposal_lines.append(f"--- Proposal {i} ---\n{prop_json}")
        all_proposals = "\n\n".join(proposal_lines)

        return (
            f"ORIGINAL TASK:\n{original_task}\n\n"
            f"CURRENT CRITERIA:\n{criteria_block}\n\n"
            f"EVOLUTION PROPOSALS ({len(proposals)} total):\n{all_proposals}\n\n"
            "Synthesize these proposals into a single authoritative evolved criteria set. "
            "Apply the synthesis rules in your instructions and output JSON."
        )

    # ------------------------------------------------------------------
    # Subagent type dirs
    # ------------------------------------------------------------------
    def write_criteria_evolution_subagent_type_dirs(self, ws_root: Path) -> None:
        """Write criteria_evolver and criteria_evolution_synthesizer type dirs."""
        import json as _json

        try:
            from massgen.subagent.type_scanner import scan_subagent_types

            evolution_types = scan_subagent_types(
                allowed_types=["criteria_evolver", "criteria_evolution_synthesizer"],
            )
            if not evolution_types:
                logger.warning(
                    "[Orchestrator] criteria_evolver / criteria_evolution_synthesizer "
                    "SUBAGENT.md files not found — criteria evolution subagents cannot run. "
                    "Check massgen/subagent_types/ for these directories.",
                )
                return
            subagent_types_dir = ws_root / ".massgen" / "subagent_types"
            subagent_types_dir.mkdir(parents=True, exist_ok=True)
            for t in evolution_types:
                type_dir = subagent_types_dir / t.name
                type_dir.mkdir(exist_ok=True)
                frontmatter = f"---\nname: {t.name}\ndescription: {_json.dumps(t.description)}\n"
                if t.expected_input:
                    frontmatter += f"expected_input: {_json.dumps(t.expected_input)}\n"
                frontmatter += "---\n"
                (type_dir / "SUBAGENT.md").write_text(frontmatter + t.system_prompt)
            logger.info(
                "[Orchestrator] Wrote %d criteria evolution type dirs to %s",
                len(evolution_types),
                subagent_types_dir,
            )
        except Exception:
            logger.warning(
                "[Orchestrator] Failed to write criteria evolution subagent type dirs",
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Main entry: full pipeline
    # ------------------------------------------------------------------
    async def run_criteria_evolution_if_needed(
        self,
        answers: dict[str, str],
    ) -> bool:
        """Synchronous gate: evolve criteria between rounds if conditions are met.

        Returns True when ready to proceed.
        """
        orch = self._orchestrator
        if not orch._should_evolve_criteria(current_answers=answers):
            return True

        coord = getattr(orch.config, "coordination_config", None)
        timeout = getattr(coord, "evolving_criteria_timeout", 300)
        label_tuple = tuple(sorted(answers.keys()))

        logger.info(
            "[Orchestrator] Starting criteria evolution #%d for answer labels %s",
            orch._criteria_evolution_count + 1,
            label_tuple,
        )

        evolution_data = orch._collect_evolution_input_data()
        agent_ids = list(orch.agents.keys())

        primary_agent_id = agent_ids[0] if agent_ids else ""

        primary_agent = orch.agents.get(primary_agent_id)
        primary_fs_mgr = getattr(getattr(primary_agent, "backend", None), "filesystem_manager", None)
        if primary_fs_mgr and getattr(primary_fs_mgr, "cwd", None):
            orch._write_criteria_evolution_subagent_type_dirs(Path(primary_fs_mgr.cwd))

        all_trace_paths = [str(p) for p in evolution_data["trace_paths"].values() if p is not None]
        proposal_tasks: list[dict[str, Any]] = []
        for i, agent_id in enumerate(agent_ids):
            subagent_id = f"criteria_evolver_{orch._criteria_evolution_count + 1}_{i}"
            task_str = orch._build_criteria_evolution_proposal_task(agent_id, evolution_data)
            proposal_tasks.append(
                {
                    "subagent_id": subagent_id,
                    "task": task_str,
                    "subagent_type": "criteria_evolver",
                    "timeout_seconds": max(60, timeout // 2),
                    "context_paths": all_trace_paths,
                },
            )

        display = getattr(orch.coordination_ui, "display", None) if getattr(orch, "coordination_ui", None) else None
        evo_num = orch._criteria_evolution_count + 1
        proposal_call_id = f"criteria_evolution_{evo_num}_proposals"
        proposal_task_preview = f"Evolving criteria (v{evo_num}): analyzing score patterns across {len(agent_ids)} agent(s)"

        _proposal_subagent_id = proposal_tasks[0]["subagent_id"] if proposal_tasks else f"criteria_evolver_{evo_num}"
        try:
            _emitter = get_event_emitter()
            if _emitter:
                _emitter.emit_raw(
                    StructuredEventType.PRE_COLLAB_STARTED,
                    agent_id=primary_agent_id,
                    subagent_id=_proposal_subagent_id,
                    task=proposal_task_preview,
                    timeout_seconds=timeout,
                    call_id=proposal_call_id,
                    log_path=None,
                )
            if display and hasattr(display, "notify_runtime_subagent_started"):
                display.notify_runtime_subagent_started(
                    agent_id=primary_agent_id,
                    subagent_id=_proposal_subagent_id,
                    task=proposal_task_preview,
                    timeout_seconds=timeout,
                    call_id=proposal_call_id,
                    status_callback=None,
                    log_path=None,
                )
        except Exception:
            pass

        try:
            raw_proposals = await asyncio.wait_for(
                orch._direct_spawn_subagents(
                    parent_agent_id=primary_agent_id,
                    tasks=proposal_tasks,
                    refine=False,
                ),
                timeout=timeout,
            )
        except TimeoutError:
            logger.warning("[Orchestrator] Criteria evolution proposals timed out; skipping")
            orch._notify_precollab_completed(primary_agent_id, proposal_tasks[0]["subagent_id"] if proposal_tasks else "", proposal_call_id, display, status="timeout", error="timed out")
            orch._criteria_evolution_completed_labels.add(label_tuple)
            return True
        except Exception:
            logger.warning("[Orchestrator] Criteria evolution proposals failed", exc_info=True)
            orch._notify_precollab_completed(primary_agent_id, proposal_tasks[0]["subagent_id"] if proposal_tasks else "", proposal_call_id, display, status="error", error="spawn failed")
            orch._criteria_evolution_completed_labels.add(label_tuple)
            return True

        proposal_dicts: list[dict[str, Any]] = []
        results = (raw_proposals or {}).get("results") or []
        for entry in results:
            parsed = orch._read_evolution_json_from_result(entry)
            if isinstance(parsed, dict):
                proposal_dicts.append(parsed)

        if not proposal_dicts:
            logger.warning("[Orchestrator] No valid criteria evolution proposals; skipping")
            orch._notify_precollab_completed(
                primary_agent_id,
                proposal_tasks[0]["subagent_id"] if proposal_tasks else "",
                proposal_call_id,
                display,
                status="completed",
                answer_preview="No valid proposals",
            )
            orch._criteria_evolution_completed_labels.add(label_tuple)
            return True

        orch._notify_precollab_completed(
            primary_agent_id,
            proposal_tasks[0]["subagent_id"] if proposal_tasks else "",
            proposal_call_id,
            display,
            status="completed",
            answer_preview=f"{len(proposal_dicts)} proposal(s) received",
        )

        synthesis_task_str = orch._build_criteria_evolution_synthesis_task(
            proposal_dicts,
            evolution_data["current_criteria"],
            evolution_data["original_task"],
        )
        synthesis_subagent_id = f"criteria_evolution_synthesizer_{orch._criteria_evolution_count + 1}"
        synthesis_call_id = f"criteria_evolution_{evo_num}_synthesis"
        synthesis_payload: list[dict[str, Any]] = [
            {
                "subagent_id": synthesis_subagent_id,
                "task": synthesis_task_str,
                "subagent_type": "criteria_evolution_synthesizer",
                "timeout_seconds": max(60, timeout // 3),
            },
        ]

        _synth_task_preview = f"Synthesizing {len(proposal_dicts)} evolution proposal(s) into final criteria"
        try:
            _emitter = get_event_emitter()
            if _emitter:
                _emitter.emit_raw(
                    StructuredEventType.PRE_COLLAB_STARTED,
                    agent_id=primary_agent_id,
                    subagent_id=synthesis_subagent_id,
                    task=_synth_task_preview,
                    timeout_seconds=timeout // 2,
                    call_id=synthesis_call_id,
                    log_path=None,
                )
            if display and hasattr(display, "notify_runtime_subagent_started"):
                display.notify_runtime_subagent_started(
                    agent_id=primary_agent_id,
                    subagent_id=synthesis_subagent_id,
                    task=_synth_task_preview,
                    timeout_seconds=timeout // 2,
                    call_id=synthesis_call_id,
                    status_callback=None,
                    log_path=None,
                )
        except Exception:
            pass

        try:
            raw_synthesis = await asyncio.wait_for(
                orch._direct_spawn_subagents(
                    parent_agent_id=primary_agent_id,
                    tasks=synthesis_payload,
                    refine=False,
                ),
                timeout=timeout // 2,
            )
        except TimeoutError:
            logger.warning("[Orchestrator] Criteria evolution synthesis timed out; skipping")
            orch._notify_precollab_completed(primary_agent_id, synthesis_subagent_id, synthesis_call_id, display, status="timeout", error="timed out")
            orch._criteria_evolution_completed_labels.add(label_tuple)
            return True
        except Exception:
            logger.warning("[Orchestrator] Criteria evolution synthesis failed", exc_info=True)
            orch._notify_precollab_completed(primary_agent_id, synthesis_subagent_id, synthesis_call_id, display, status="error", error="spawn failed")
            orch._criteria_evolution_completed_labels.add(label_tuple)
            return True

        synth_results = (raw_synthesis or {}).get("results") or []
        synth_parsed = orch._read_evolution_json_from_result(synth_results[0]) if synth_results else None
        synth_answer = json.dumps(synth_parsed) if synth_parsed else (synth_results[0].get("answer", "") if synth_results else "")

        from massgen.evaluation_criteria_generator import parse_evolution_response

        evolved, summary, is_unchanged = parse_evolution_response(
            synth_answer,
            evolution_data["current_criteria"],
        )

        if is_unchanged:
            logger.info(
                "[Orchestrator] Criteria evolution synthesizer returned UNCHANGED; criteria are still effective",
            )
            orch._notify_precollab_completed(primary_agent_id, synthesis_subagent_id, synthesis_call_id, display, status="completed", answer_preview="Criteria unchanged")
            orch._criteria_evolution_completed_labels.add(label_tuple)
            return True

        if evolved is None:
            logger.warning("[Orchestrator] Failed to parse criteria evolution synthesis result; skipping")
            orch._notify_precollab_completed(primary_agent_id, synthesis_subagent_id, synthesis_call_id, display, status="completed", answer_preview="Parse failed")
            orch._criteria_evolution_completed_labels.add(label_tuple)
            return True

        evolved_count = sum(1 for old_c, new_c in zip(evolution_data["current_criteria"], evolved) if old_c.text != new_c.text)
        orch._notify_precollab_completed(
            primary_agent_id,
            synthesis_subagent_id,
            synthesis_call_id,
            display,
            status="completed",
            answer_preview=f"{evolved_count} criteria evolved",
        )

        old_criteria = list(evolution_data["current_criteria"])
        orch._criteria_evolution_history.append(
            {
                "evolution_number": orch._criteria_evolution_count + 1,
                "old_criteria": [{"id": c.id, "text": c.text} for c in old_criteria],
                "new_criteria": [{"id": c.id, "text": c.text} for c in evolved],
                "summary": summary,
            },
        )
        orch._generated_evaluation_criteria = evolved
        orch._evaluation_criteria_generated = True
        orch._criteria_evolution_count += 1
        orch._criteria_evolution_completed_labels.add(label_tuple)

        try:
            orch._init_checklist_tool()
        except Exception:
            logger.warning("[Orchestrator] Failed to re-init checklist tool after criteria evolution", exc_info=True)

        try:
            _emitter = get_event_emitter()
            evolved_count = sum(1 for old_c, new_c in zip(old_criteria, evolved) if old_c.text != new_c.text)
            if _emitter:
                _emitter.emit_raw(
                    StructuredEventType.EVALUATION_CRITERIA_EVOLVED,
                    evolution_number=orch._criteria_evolution_count,
                    evolved_count=evolved_count,
                    total_count=len(evolved),
                    summary=summary or "",
                )
            evolved_payload = [{"id": c.id, "text": c.text, "category": getattr(c, "category", "standard")} for c in evolved]
            if _emitter:
                _emitter.emit_raw(
                    StructuredEventType.EVALUATION_CRITERIA_SET,
                    criteria=evolved_payload,
                    source=f"evolved_v{orch._criteria_evolution_count}",
                )
            display = getattr(orch.coordination_ui, "display", None) if orch.coordination_ui else None
            if display and hasattr(display, "set_evaluation_criteria"):
                display.set_evaluation_criteria(
                    evolved_payload,
                    source=f"evolved_v{orch._criteria_evolution_count}",
                )
        except Exception:
            pass

        orch._write_criteria_evolution_memory(
            evolution_number=orch._criteria_evolution_count,
            old_criteria=old_criteria,
            new_criteria=evolved,
            summary=summary,
        )

        if summary:
            context_block = (
                f"[CRITERIA EVOLVED — round {orch._criteria_evolution_count}]\n\n"
                f"{summary}\n\n"
                "The evaluation criteria have been updated based on your performance. "
                "Score your next answer against the NEW criteria visible in your checklist tool."
            )
            for agent_id in orch.agents:
                orch._queue_round_start_context_block(agent_id, context_block)

        logger.info(
            "[Orchestrator] Criteria evolved (evolution #%d): %d criteria updated",
            orch._criteria_evolution_count,
            len(evolved),
        )
        return True

    # ------------------------------------------------------------------
    # Memory writer
    # ------------------------------------------------------------------
    def write_criteria_evolution_memory(
        self,
        evolution_number: int,
        old_criteria: list[Any],
        new_criteria: list[Any],
        summary: str | None,
    ) -> None:
        """Write criteria evolution summary to each agent's short-term memory."""
        orch = self._orchestrator
        diff_lines: list[str] = []
        old_by_id = {c.id: c for c in old_criteria}
        for c in new_criteria:
            old = old_by_id.get(c.id)
            if old and old.text != c.text:
                diff_lines.append(f"**{c.id} (evolved)**")
                diff_lines.append(f"  Before: {old.text}")
                diff_lines.append(f"  After:  {c.text}")
            else:
                diff_lines.append(f"**{c.id} (unchanged)** {c.text}")

        diff_block = "\n".join(diff_lines)
        summary_block = summary or "Criteria evolved to raise the bar based on agent score trends."

        memory_block = (
            "---\n"
            f"name: criteria_evolution_{evolution_number}\n"
            f"description: Evaluation criteria evolved in round {evolution_number} — new bar is higher\n"
            "tier: short_term\n"
            "---\n\n"
            f"## Criteria Evolution #{evolution_number}\n\n"
            f"{summary_block}\n\n"
            "### What Changed\n\n"
            f"{diff_block}\n\n"
            "Score your NEXT answer against the NEW criteria above. "
            "The previous scores are no longer the benchmark — the bar has moved."
        )

        for agent_id, agent in orch.agents.items():
            fs_mgr = getattr(getattr(agent, "backend", None), "filesystem_manager", None)
            if not fs_mgr or not getattr(fs_mgr, "cwd", None):
                continue
            memory_dir = fs_mgr.cwd / "memory" / "short_term"
            try:
                memory_dir.mkdir(parents=True, exist_ok=True)
                target = memory_dir / f"criteria_evolution_{evolution_number}.md"
                target.write_text(memory_block, encoding="utf-8")
                logger.info(
                    "[Orchestrator] Wrote criteria evolution memory to %s for %s",
                    target,
                    agent_id,
                )
            except OSError as exc:
                logger.warning(
                    "[Orchestrator] Failed to write criteria evolution memory for %s: %s",
                    agent_id,
                    exc,
                )

    @staticmethod
    def read_evolution_json_from_result(entry: dict[str, Any]) -> dict[str, Any] | None:
        """Read criteria-evolution JSON from a subagent result entry.

        Prefers the workspace file ``deliverable/evolved_criteria.json`` (written
        by the subagent). Falls back to parsing the answer text or fenced JSON.
        """
        import json
        from pathlib import Path

        _FILENAME = "evolved_criteria.json"
        workspace = entry.get("workspace") or ""
        if workspace:
            ws = Path(workspace)
            candidates = [ws / "deliverable" / _FILENAME]
            for pattern in (
                f"agent_*/deliverable/{_FILENAME}",
                f"snapshots/*/*/deliverable/{_FILENAME}",
            ):
                candidates.extend(ws.glob(pattern))
            for candidate in candidates:
                if candidate.exists():
                    try:
                        data = json.loads(candidate.read_text(encoding="utf-8"))
                        if isinstance(data, dict):
                            return data
                    except Exception:
                        pass

        answer_text = entry.get("answer") or ""
        if not answer_text:
            return None
        try:
            parsed = json.loads(answer_text)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, ValueError):
            pass
        for fence in ("```json", "```"):
            start = answer_text.find(fence)
            if start < 0:
                continue
            start += len(fence)
            end = answer_text.find("```", start)
            if end > start:
                try:
                    parsed = json.loads(answer_text[start:end].strip())
                    if isinstance(parsed, dict):
                        return parsed
                except (json.JSONDecodeError, ValueError):
                    pass
        return None
