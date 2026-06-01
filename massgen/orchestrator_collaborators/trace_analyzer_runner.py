"""Auto trace analyzer runner, extracted from Orchestrator.

Owns the background ``execution_trace_analyzer`` pipeline:

    build task -> spawn -> resolve artifact -> copy to memory ->
    build mid-stream injection result

All cross-method calls inside this collaborator route through
``self._orchestrator.<method>(...)`` so that test monkey-patches on the
orchestrator instance (e.g. ``orch._run_trace_analyzer = _fake_run`` in
``test_auto_trace_analysis.py``) take effect, and so that other already-extracted
collaborators (``SubagentLifecycleCoordinator``, ``SubagentToolInjector``) are
reached via their existing orchestrator delegators.
"""

from __future__ import annotations

import asyncio
import copy
import os
import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from massgen.logger_config import logger

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator
    from massgen.subagent.models import SubagentResult


class TraceAnalyzerRunner:
    """Coordinates the background execution-trace-analyzer pipeline."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    # ------------------------------------------------------------------
    # Pure helpers (formatting, frontmatter, memory filenames)
    # ------------------------------------------------------------------
    @staticmethod
    def format_trace_analyzer_for_memory_static(
        trace_result: SubagentResult,
        round_number: int,
    ) -> str | None:
        """Format execution trace analyzer output as a memory block."""
        report_text = trace_result.answer or ""
        if not report_text.strip():
            return None

        frontmatter = "---\n" f"name: execution_trace_round_{round_number}\n" f"description: Process learnings from round {round_number}" " execution trace analysis\n" "tier: short_term\n" "---\n"
        return f"{frontmatter}\n{report_text}"

    @staticmethod
    def strip_memory_frontmatter(content: str) -> str:
        """Return the body of a memory file, dropping YAML frontmatter when present."""
        normalized = content.strip()
        if not normalized.startswith("---"):
            return normalized

        lines = normalized.splitlines()
        if not lines or lines[0].strip() != "---":
            return normalized

        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                body = "\n".join(lines[index + 1 :]).strip()
                return body or normalized

        return normalized

    @staticmethod
    def get_trace_analysis_memory_filename(round_number: int) -> str:
        """Return the canonical short-term memory filename for trace analysis."""
        return f"trace_analysis_round_{round_number}.md"

    # ------------------------------------------------------------------
    # Injection-text builders
    # ------------------------------------------------------------------
    def build_trace_analysis_injection_text(
        self,
        round_number: int,
        content: str,
    ) -> str | None:
        """Build the mid-stream injection payload for trace-analysis guidance."""
        body = self.strip_memory_frontmatter(content)
        if not body:
            return None

        return f"Trace analysis completed for round {round_number - 1}. " f"Apply this execution-process guidance immediately in round {round_number}.\n\n" f"{body}"

    def build_trace_analysis_injection_result(
        self,
        trace_result: SubagentResult,
        round_number: int,
        artifact_path: Path | None,
    ) -> SubagentResult | None:
        """Build the result payload queued for background injection."""
        injection_text: str | None = None

        if artifact_path is not None:
            try:
                artifact_content = artifact_path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning(
                    "[Orchestrator] Failed to read trace analysis artifact for injection %s: %s",
                    artifact_path,
                    exc,
                )
            else:
                injection_text = self.build_trace_analysis_injection_text(
                    round_number,
                    artifact_content,
                )

        if not injection_text and trace_result.answer:
            injection_text = self.build_trace_analysis_injection_text(
                round_number,
                trace_result.answer,
            )

        if not injection_text:
            return None

        return trace_result.__class__(
            subagent_id=trace_result.subagent_id,
            status=trace_result.status,
            success=trace_result.success,
            answer=injection_text,
            workspace_path=trace_result.workspace_path,
            execution_time_seconds=trace_result.execution_time_seconds,
            error=trace_result.error,
            token_usage=copy.deepcopy(trace_result.token_usage),
            log_path=trace_result.log_path,
            completion_percentage=trace_result.completion_percentage,
            warning=trace_result.warning,
        )

    # ------------------------------------------------------------------
    # Artifact path resolution
    # ------------------------------------------------------------------
    @classmethod
    def candidate_trace_analysis_artifact_paths(
        cls,
        workspace_path: str | os.PathLike[str] | None,
        round_number: int,
    ) -> list[Path]:
        """Return likely locations for the analyzer's authoritative memory artifact."""
        if not workspace_path:
            return []

        filename = cls.get_trace_analysis_memory_filename(round_number)
        workspace = Path(workspace_path)
        candidates: list[tuple[int, float, Path]] = []
        seen: set[str] = set()

        def _add(path: Path, priority: int) -> None:
            if not path.exists() or not path.is_file():
                return
            try:
                key = str(path.resolve())
            except OSError:
                key = str(path)
            if key in seen:
                return
            seen.add(key)
            try:
                mtime = path.stat().st_mtime
            except OSError:
                mtime = 0.0
            candidates.append((priority, -mtime, path))

        _add(workspace / "deliverable" / filename, priority=0)
        _add(workspace / filename, priority=5)

        for pattern, priority in (
            (f"agent_*/deliverable/{filename}", 10),
            (f"agent_*/{filename}", 15),
            (f".massgen/sessions/*/turn_*/workspace/deliverable/{filename}", 20),
            (f".massgen/sessions/*/turn_*/workspace/{filename}", 25),
            (f".massgen/massgen_logs/*/turn_*/final/*/workspace/deliverable/{filename}", 30),
            (f".massgen/massgen_logs/*/turn_*/final/*/workspace/{filename}", 35),
        ):
            for candidate in workspace.glob(pattern):
                _add(candidate, priority=priority)

        candidates.sort(key=lambda item: (item[0], item[1], str(item[2])))
        return [path for _, _, path in candidates]

    @classmethod
    def resolve_trace_analysis_artifact_path(
        cls,
        workspace_path: str | os.PathLike[str] | None,
        round_number: int,
    ) -> Path | None:
        """Return the first non-empty trace-analysis artifact with memory frontmatter."""
        for candidate in cls.candidate_trace_analysis_artifact_paths(
            workspace_path=workspace_path,
            round_number=round_number,
        ):
            try:
                content = candidate.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning(
                    "[Orchestrator] Failed to read trace analysis artifact %s: %s",
                    candidate,
                    exc,
                )
                continue

            stripped = content.strip()
            if not stripped:
                logger.warning(
                    "[Orchestrator] Trace analysis artifact is empty at %s",
                    candidate,
                )
                continue
            if not stripped.startswith("---") or "tier: short_term" not in content or "name:" not in content:
                logger.warning(
                    "[Orchestrator] Trace analysis artifact at %s is missing required memory frontmatter",
                    candidate,
                )
                continue
            return candidate

        return None

    # ------------------------------------------------------------------
    # Per-agent trace path lookup
    # ------------------------------------------------------------------
    def get_execution_trace_path_for_agent(self, agent_id: str) -> Path | None:
        """Return the path to the latest execution_trace.md, or None."""
        orch = self._orchestrator
        agent = orch.agents.get(agent_id)
        if not agent:
            return None
        fs_mgr = getattr(
            getattr(agent, "backend", None),
            "filesystem_manager",
            None,
        )
        if not fs_mgr or not fs_mgr.snapshot_storage:
            return None
        trace_path = fs_mgr.snapshot_storage / "execution_trace.md"
        return trace_path if trace_path.exists() else None

    def get_execution_trace_context_path_for_agent(
        self,
        agent_id: str,
        temp_workspace_path: str | os.PathLike[str] | None = None,
    ) -> Path | None:
        """Return a subagent-readable execution trace path for the agent."""
        orch = self._orchestrator
        snapshot_trace = orch._get_execution_trace_path_for_agent(agent_id)
        if not snapshot_trace:
            return None

        temp_roots: list[Path] = []

        if temp_workspace_path:
            temp_roots.append(Path(temp_workspace_path))

        agent = orch.agents.get(agent_id)
        fs_mgr = getattr(
            getattr(agent, "backend", None),
            "filesystem_manager",
            None,
        )
        for candidate_root in (
            getattr(fs_mgr, "agent_temporary_workspace", None),
            getattr(orch, "_agent_temporary_workspace", None),
        ):
            if candidate_root:
                temp_roots.append(Path(candidate_root))

        anon_id = agent_id
        tracker = getattr(orch, "coordination_tracker", None)
        if tracker and hasattr(tracker, "get_reverse_agent_mapping"):
            try:
                anon_id = tracker.get_reverse_agent_mapping().get(agent_id, agent_id)
            except Exception:
                anon_id = agent_id

        seen: set[Path] = set()
        for temp_root in temp_roots:
            try:
                resolved_root = temp_root.resolve()
            except OSError:
                continue
            if resolved_root in seen:
                continue
            seen.add(resolved_root)
            trace_path = resolved_root / anon_id / "execution_trace.md"
            if trace_path.exists():
                return trace_path

        return None

    # ------------------------------------------------------------------
    # Task prompt + memory writers
    # ------------------------------------------------------------------
    def build_trace_analyzer_task(
        self,
        agent_id: str,
        round_number: int,
        trace_path: str,
    ) -> str:
        """Build the task string for the execution_trace_analyzer subagent."""
        orch = self._orchestrator
        original_task = getattr(orch, "_original_task", None) or getattr(orch, "current_task", None) or "Task coordination"
        memory_filename = self.get_trace_analysis_memory_filename(round_number)
        memory_artifact_path = f"deliverable/{memory_filename}"
        frontmatter = "---\n" f"name: execution_trace_round_{round_number}\n" f"description: Process learnings from round {round_number} execution trace analysis\n" "tier: short_term\n" "---"
        return (
            f"Analyze the execution trace from round {round_number - 1} "
            "and extract specific DO/DON'T guidance about the agent's "
            "EXECUTION PROCESS for the next round.\n\n"
            f"ORIGINAL TASK (for context only):\n{original_task}\n\n"
            f"The execution trace file is at: {trace_path}\n"
            "Read it and analyze HOW the agent worked — tool strategy, "
            "wasted effort, wrong assumptions, missing context gathering, "
            "backtracking, scope drift. Do NOT critique the deliverable "
            "quality (that is the round_evaluator's job). Focus on "
            "behavioral patterns that cost time or led the agent in "
            "wrong directions.\n\n"
            "Authoritative output contract:\n"
            f"1. If `deliverable/` does not exist in your workspace, create it.\n"
            f"2. Write the final memory artifact to `{memory_artifact_path}`.\n"
            "3. That file will be copied directly into the parent agent's "
            "`memory/short_term/`, so it must already contain valid YAML "
            "frontmatter exactly like this:\n"
            f"{frontmatter}\n\n"
            "4. After writing the file, keep your answer text brief: say "
            "whether you created the file and state its path. Do not paste "
            "the full report into the answer.\n\n"
            "Criticality rules:\n"
            "- Be skeptical. Bias toward DON'T / CRITICAL ERRORS unless the "
            "trace clearly proves a behavior helped.\n"
            "- Only put an item in `DO` when the trace shows direct evidence "
            "that it worked (for example: successful verification, later reuse "
            "without rollback, or avoided repeated failure).\n"
            "- If an action was merely attempted, completed once without proof, "
            "or only seems plausible, Do NOT promote it to `DO`.\n"
            "- If nothing is confidently confirmed, say so explicitly under "
            "`DO` instead of inventing a positive.\n"
            "- Every item must cite specific trace evidence: tool names, file "
            "paths, repeated commands, or exact error messages.\n\n"
            "Use the DO / DON'T / CRITICAL ERRORS section format from your "
            "instructions inside the artifact."
        )

    def write_trace_analysis_to_memory(
        self,
        agent_id: str,
        round_number: int,
        memory_block: str,
    ) -> None:
        """Write trace analysis to agent's memory/short_term/ directory."""
        orch = self._orchestrator
        agent = orch.agents.get(agent_id)
        if not agent:
            return
        fs_mgr = getattr(getattr(agent, "backend", None), "filesystem_manager", None)
        if not fs_mgr or not fs_mgr.cwd:
            return
        memory_dir = fs_mgr.cwd / "memory" / "short_term"
        try:
            memory_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return
        target = memory_dir / self.get_trace_analysis_memory_filename(round_number)
        try:
            target.write_text(memory_block, encoding="utf-8")
            logger.info(
                "[Orchestrator] Wrote trace analysis to %s for %s",
                target,
                agent_id,
            )
        except OSError as exc:
            logger.warning("[Orchestrator] Failed to write trace analysis memory: %s", exc)

    def copy_trace_analysis_artifact_to_memory(
        self,
        agent_id: str,
        round_number: int,
        source_path: Path,
    ) -> None:
        """Copy the authoritative trace-analysis artifact into short-term memory."""
        orch = self._orchestrator
        agent = orch.agents.get(agent_id)
        if not agent:
            return
        fs_mgr = getattr(getattr(agent, "backend", None), "filesystem_manager", None)
        if not fs_mgr or not fs_mgr.cwd:
            return
        memory_dir = fs_mgr.cwd / "memory" / "short_term"
        try:
            memory_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return

        target = memory_dir / self.get_trace_analysis_memory_filename(round_number)
        try:
            if source_path.resolve() == target.resolve():
                return
        except OSError:
            pass

        try:
            shutil.copy2(source_path, target)
            logger.info(
                "[Orchestrator] Copied trace analysis artifact %s to %s for %s",
                source_path,
                target,
                agent_id,
            )
        except OSError as exc:
            logger.warning("[Orchestrator] Failed to copy trace analysis artifact to memory: %s", exc)

    # ------------------------------------------------------------------
    # Async runner + spawner
    # ------------------------------------------------------------------
    async def run_trace_analyzer(
        self,
        parent_agent_id: str,
        round_number: int,
        trace_path: Path,
    ) -> None:
        """Background worker: spawn trace analyzer and process result."""
        from massgen.subagent.models import SubagentResult

        orch = self._orchestrator
        subagent_id = f"trace_analyzer_{parent_agent_id}_r{round_number}"
        # Default 5 min, capped at half of subsequent_round_timeout_seconds
        trace_timeout = 300
        coord = getattr(orch.config, "coordination_config", None)
        timeout_cfg = getattr(orch.config, "timeout_config", None)
        subsequent_timeout = getattr(timeout_cfg, "subsequent_round_timeout_seconds", None)
        if not subsequent_timeout and coord:
            subsequent_timeout = getattr(coord, "subsequent_round_timeout_seconds", None)
        if subsequent_timeout and subsequent_timeout > 0:
            trace_timeout = min(trace_timeout, int(subsequent_timeout // 2))

        task_payload: dict[str, Any] = {
            "subagent_id": subagent_id,
            "task": orch._build_trace_analyzer_task(
                parent_agent_id,
                round_number,
                str(trace_path),
            ),
            "subagent_type": "execution_trace_analyzer",
            "timeout_seconds": trace_timeout,
            "context_paths": [str(trace_path)],
        }

        tool_call_id = f"trace_analyzer_{parent_agent_id}_r{round_number}" f"_{int(time.time() * 1000)}"
        display_round = orch._get_round_evaluator_display_round(parent_agent_id) if hasattr(orch, "_get_round_evaluator_display_round") else round_number

        # Emit TUI spawn event
        orch._emit_round_evaluator_spawn_event(
            phase="start",
            agent_id=parent_agent_id,
            tool_call_id=tool_call_id,
            round_number=display_round,
            args={"tasks": [task_payload], "background": True},
        )

        started_at = time.time()
        try:
            raw_result = await orch._direct_spawn_subagents(
                parent_agent_id=parent_agent_id,
                tasks=[task_payload],
                refine=False,
            )
        except asyncio.CancelledError:
            elapsed = time.time() - started_at
            orch._emit_round_evaluator_spawn_event(
                phase="complete",
                agent_id=parent_agent_id,
                tool_call_id=tool_call_id,
                round_number=display_round,
                args={"tasks": [task_payload], "background": True},
                result={"success": False, "error": "cancelled"},
                elapsed_seconds=elapsed,
                is_error=True,
                status="cancelled",
            )
            return

        elapsed = time.time() - started_at
        normalized = raw_result if isinstance(raw_result, dict) else {}
        success = bool(normalized.get("success"))

        orch._emit_round_evaluator_spawn_event(
            phase="complete",
            agent_id=parent_agent_id,
            tool_call_id=tool_call_id,
            round_number=display_round,
            args={"tasks": [task_payload], "background": True},
            result=normalized,
            elapsed_seconds=elapsed,
            is_error=not success,
            status="success" if success else "error",
        )

        # Parse result
        results = normalized.get("results")
        if not isinstance(results, list) or not results:
            error = normalized.get("error", "")
            summary = normalized.get("summary", {})
            logger.warning(
                "[Orchestrator] Trace analyzer for %s r%d returned no results "
                "(success=%s, error=%s, summary=%s). "
                "Check that 'execution_trace_analyzer' is in subagent_types "
                "and its SUBAGENT.md is written to the workspace.",
                parent_agent_id,
                round_number,
                success,
                error,
                summary,
            )
            return

        try:
            trace_result = SubagentResult.from_dict(results[0])
        except Exception:
            logger.warning(
                "[Orchestrator] Failed to parse trace analyzer result for %s",
                parent_agent_id,
                exc_info=True,
            )
            return

        artifact_path = orch._resolve_trace_analysis_artifact_path(
            workspace_path=trace_result.workspace_path,
            round_number=round_number,
        )
        if artifact_path:
            orch._copy_trace_analysis_artifact_to_memory(
                parent_agent_id,
                round_number,
                artifact_path,
            )
        else:
            logger.warning(
                "[Orchestrator] Trace analyzer for %s r%d produced no authoritative artifact; " "falling back to answer text for memory persistence",
                parent_agent_id,
                round_number,
            )
            memory_block = orch._format_trace_analyzer_for_memory_static(
                trace_result,
                round_number,
            )
            if memory_block:
                orch._write_trace_analysis_to_memory(
                    parent_agent_id,
                    round_number,
                    memory_block,
                )

        # Enqueue the completed guidance so the running parent can receive it
        # immediately via the existing subagent-completion injection path.
        injection_result = orch._build_trace_analysis_injection_result(
            trace_result,
            round_number,
            artifact_path=artifact_path,
        )
        if injection_result is not None:
            orch._on_background_subagent_complete(
                parent_agent_id,
                subagent_id,
                injection_result,
            )

    async def spawn_trace_analyzer_background(
        self,
        parent_agent_id: str,
    ) -> None:
        """Spawn background trace analyzer for the given agent at round 2+."""
        orch = self._orchestrator
        state = orch.agent_states.get(parent_agent_id)
        restart_count = getattr(state, "restart_count", 0) if state else 0
        round_number = max(1, restart_count + 1)

        snapshot_trace_path = orch._get_execution_trace_path_for_agent(parent_agent_id)
        if not snapshot_trace_path:
            logger.debug(
                "[Orchestrator] No execution trace available for %s, " "skipping trace analyzer",
                parent_agent_id,
            )
            return

        temp_workspace_path = await orch._copy_all_snapshots_to_temp_workspace(parent_agent_id)
        trace_path = orch._get_execution_trace_context_path_for_agent(
            parent_agent_id,
            temp_workspace_path=temp_workspace_path,
        )
        if not trace_path:
            logger.warning(
                "[Orchestrator] Execution trace exists for %s at %s but no " "subagent-readable temp-workspace copy was available; " "skipping trace analyzer",
                parent_agent_id,
                snapshot_trace_path,
            )
            return

        # Pre-flight: verify execution_trace_analyzer type dir exists in the
        # workspace so the spawn doesn't silently produce empty results.
        agent = orch.agents.get(parent_agent_id)
        fs_mgr = getattr(getattr(agent, "backend", None), "filesystem_manager", None)
        if fs_mgr and fs_mgr.cwd:
            type_dir = Path(fs_mgr.cwd) / ".massgen" / "subagent_types" / "execution_trace_analyzer"
            if not type_dir.exists():
                # Write it now — may have been missing from DEFAULT_SUBAGENT_TYPES
                orch._write_subagent_type_dirs(Path(fs_mgr.cwd))
                if not type_dir.exists():
                    logger.warning(
                        "[Orchestrator] execution_trace_analyzer type dir " "not found in workspace for %s — skipping. " "Add 'execution_trace_analyzer' to subagent_types " "in coordination config.",
                        parent_agent_id,
                    )
                    return

        task = asyncio.create_task(
            orch._run_trace_analyzer(
                parent_agent_id,
                round_number,
                trace_path,
            ),
            name=f"trace_analyzer_{parent_agent_id}_r{round_number}",
        )
        orch._background_trace_tasks[parent_agent_id] = task
        logger.info(
            "[Orchestrator] Spawned background trace analyzer for %s r%d",
            parent_agent_id,
            round_number,
        )

    @staticmethod
    def split_combined_spawn_result(
        combined: dict,
        evaluator_subagent_id: str,
        trace_subagent_id: str,
    ) -> tuple[dict, dict]:
        """Split a combined spawn result into separate evaluator and trace dicts.

        When round_evaluator and execution_trace_analyzer are spawned in a
        single ``spawn_subagents`` call the result payload contains entries
        for both. Partition them by ``subagent_id`` so downstream processing
        can handle each independently.
        """
        results = combined.get("results") or []
        eval_results: list[dict] = []
        trace_results: list[dict] = []
        for entry in results:
            sid = entry.get("subagent_id", "")
            if sid == trace_subagent_id:
                trace_results.append(entry)
            else:
                eval_results.append(entry)

        base = {k: v for k, v in combined.items() if k != "results"}
        eval_dict = {**base, "results": eval_results}
        trace_dict = {
            **base,
            "success": bool(trace_results),
            "results": trace_results,
        }
        return eval_dict, trace_dict

    def should_spawn_trace_analyzer(self, agent_id: str) -> bool:
        """Return True if auto_trace_analysis should spawn for this agent."""
        orch = self._orchestrator
        coord = getattr(orch.config, "coordination_config", None)
        if not coord:
            return False
        if not getattr(coord, "auto_trace_analysis", False):
            return False
        # Must be round 2+ (restart_count >= 1)
        state = orch.agent_states.get(agent_id)
        if not state or getattr(state, "restart_count", 0) < 1:
            return False
        # Must not already have an in-flight trace task
        existing = orch._background_trace_tasks.get(agent_id)
        if existing and not existing.done():
            return False
        return True
