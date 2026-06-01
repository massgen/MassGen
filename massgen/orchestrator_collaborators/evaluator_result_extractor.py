"""Evaluator result extraction utilities, extracted from Orchestrator.

This collaborator hosts the four ``@staticmethod`` pure utilities that read
``round_evaluator`` log directories, format multi-evaluator result blocks,
and convert evaluator verdicts into task plans.

The collaborator carries no state. Like the other 35 collaborators, its
``__init__`` accepts an orchestrator back-reference (unused) so that the
standard ``cached_property`` wiring pattern in :class:`Orchestrator` works
uniformly. All methods are ``@staticmethod`` so they can be called either
through the collaborator class or as bound delegators on Orchestrator.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import TYPE_CHECKING

from massgen.logger_config import logger
from massgen.subagent.models import RoundEvaluatorResult

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class EvaluatorResultExtractor:
    """Pure helpers for extracting and formatting round-evaluator output."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        # Back-reference kept for consistency with other collaborators; unused.
        self._orchestrator = orchestrator

    @staticmethod
    def extract_all_evaluator_answers(
        log_path: str,
        workspace_path: str,
    ) -> dict[str, str] | None:
        """Read all evaluator agent answers from a round_evaluator's log directory.

        Reads status.json to discover agent IDs and timestamps, then reads
        each agent's answer.txt. Returns anonymized keys like
        ``{"Evaluator A": "...", "Evaluator B": "...", ...}``.

        Returns None if the log directory or status.json doesn't exist.
        """
        log_dir = Path(log_path)

        # log_path may be the base dir or a resolved events.jsonl path.
        # Walk up to find the directory containing full_logs/status.json.
        full_logs = log_dir / "full_logs"
        status_file = full_logs / "status.json"
        if not status_file.exists():
            # Try walking up from resolved path (e.g. .../full_logs/events.jsonl)
            for parent in [log_dir.parent, log_dir.parent.parent]:
                candidate = parent / "full_logs" / "status.json"
                if candidate.exists():
                    full_logs = parent / "full_logs"
                    status_file = candidate
                    break
            else:
                return None

        try:
            status_data = json.loads(status_file.read_text())
        except (json.JSONDecodeError, OSError):
            logger.warning(
                "[Orchestrator] Failed to read round_evaluator status.json from %s",
                status_file,
            )
            return None

        historical_list = status_data.get("historical_workspaces", [])
        if not isinstance(historical_list, list) or not historical_list:
            return None

        answers: dict[str, str] = {}
        anonymous_labels = iter(f"Evaluator {chr(65 + i)}" for i in range(26))

        for ws_info in historical_list:
            if not isinstance(ws_info, dict):
                continue
            agent_id = ws_info.get("agentId", "")
            timestamp = ws_info.get("timestamp", "")
            if not agent_id or not timestamp:
                continue

            # Try full_logs/{agentId}/{timestamp}/answer.txt
            answer_file = full_logs / agent_id / timestamp / "answer.txt"
            if answer_file.exists():
                try:
                    text = answer_file.read_text().strip()
                    if text:
                        label = next(anonymous_labels, f"Evaluator {len(answers)}")
                        answers[label] = text
                except OSError:
                    pass

        return answers if answers else None

    @staticmethod
    def extract_evaluator_workspace_paths(
        log_path: str,
    ) -> list[str]:
        """Return workspace paths for each eval agent in a round_evaluator run.

        Looks for ``full_logs/{agentId}/workspace/`` directories, which are
        the persisted snapshots of each evaluator's workspace.
        """
        log_dir = Path(log_path)

        # Same walk-up logic as extract_all_evaluator_answers
        full_logs = log_dir / "full_logs"
        if not full_logs.is_dir():
            for parent in [log_dir.parent, log_dir.parent.parent]:
                candidate = parent / "full_logs"
                if candidate.is_dir():
                    full_logs = candidate
                    break
            else:
                return []

        paths: list[str] = []
        for child in sorted(full_logs.iterdir()):
            if not child.is_dir():
                continue
            ws = child / "workspace"
            if ws.is_dir():
                paths.append(str(ws))
        return paths

    @staticmethod
    def format_multi_evaluator_result_block(
        all_answers: dict[str, str],
        auto_injected: bool = False,
    ) -> str:
        """Format multiple evaluator critiques as separate tagged blocks.

        Strips verdict_block JSON from each critique before injection so
        the parent reads the prose analysis only.
        """
        n = len(all_answers)

        if auto_injected:
            instructions = (
                "Improvement tasks have been auto-injected into your task plan.\n"
                "Call `get_task_plan` to see them. Implement each task, then call `new_answer`.\n"
                "Do NOT call `submit_checklist` or `draft_approach` — already handled."
            )
        else:
            instructions = (
                "You received independent critiques from multiple evaluators.\n"
                "Synthesize them yourself:\n"
                "1. Read ALL critiques — each evaluator catches different issues.\n"
                "2. For each criterion, adopt the HARSHEST score across evaluators.\n"
                "3. Collect ALL unique concrete findings — even if only one evaluator mentions them.\n"
                "4. When evaluators flag the SAME issue, merge into one finding:\n"
                "   keep the most specific description, harshest severity, and\n"
                "   combine distinct evidence.\n"
                "5. Build one unified improvement plan from the combined findings.\n"
                "6. Save the synthesized diagnostic to your workspace\n"
                "   (e.g., tasks/diagnostic_report.md), then call `submit_checklist`\n"
                "   with that path as report_path.\n"
                "Do NOT discard findings just because other evaluators missed them.\n"
                "Do NOT average scores — use the lowest (harshest) per criterion.\n\n"
                "IMPORTANT: If any critique below is short or references a workspace\n"
                "file (e.g., 'refer to critique_packet.md'), browse that evaluator's\n"
                "workspace to read the full report. You have read-only access to all\n"
                "evaluator workspaces. Do NOT skip a thin answer — the real critique\n"
                "may be in the workspace."
            )

        parts = [
            "============================================================",
            f"ROUND EVALUATOR RESULTS ({n} independent evaluations)",
            "============================================================",
            instructions,
            "",
        ]

        for label, critique_text in all_answers.items():
            # Strip verdict_block from injected text (scores visible in prose)
            clean_text = RoundEvaluatorResult.strip_verdict_block(critique_text)
            parts.append(f'<evaluator_packet evaluator="{label}">')
            parts.append(clean_text)
            parts.append("</evaluator_packet>")
            parts.append("")

        parts.append("============================================================")
        return "\n".join(parts)

    @staticmethod
    def build_task_plan_from_evaluator_verdict(
        evaluator_result: RoundEvaluatorResult,
    ) -> list[dict]:
        """Convert evaluator verdict improvements/preserve into a task_plan.

        Returns a list in the same format as ``evaluate_draft_approach()``
        output, ready for ``_write_inject_file()``.
        """
        if evaluator_result.verdict != "iterate":
            return []

        structured_next_tasks = evaluator_result.normalize_next_tasks_payload(
            evaluator_result.next_tasks,
        )
        if structured_next_tasks:
            task_plan = copy.deepcopy(structured_next_tasks.get("tasks", []))
            if evaluator_result.preserve:
                task_plan.append(
                    {
                        "type": "verify_preserve",
                        "description": ("Verify preserved strengths haven't regressed and that earlier " "correctness fixes still pass after later changes"),
                        "execution": {"mode": "inline"},
                        "items": [
                            {
                                "criterion_id": p.get("criterion_id", ""),
                                "what": p.get("what", ""),
                                "source": p.get("source", ""),
                            }
                            for p in evaluator_result.preserve
                        ],
                    },
                )
            return task_plan

        if not evaluator_result.improvements:
            return []

        task_plan: list[dict] = []

        # Opportunities (explore tasks) come first — they represent independent
        # ideas the evaluator identified that could be a leap forward, not just
        # corrections.  Placing them before improve tasks encourages the parent
        # to consider creative directions before falling back to patching.
        if evaluator_result.opportunities:
            for opp in evaluator_result.opportunities:
                task_plan.append(
                    {
                        "type": "explore",
                        "idea": opp.get("idea", ""),
                        "rationale": opp.get("rationale", ""),
                        "impact": opp.get("impact", "transformative"),
                        "relates_to": opp.get("relates_to", []),
                        "execution": {"mode": "delegate", "subagent_type": "builder"},
                    },
                )

        for imp in evaluator_result.improvements:
            entry: dict = {
                "type": "improve",
                "criterion_id": imp.get("criterion_id", ""),
                "criterion": imp.get("verification", ""),
                "plan": imp.get("plan", ""),
                "impact": imp.get("impact", "incremental"),
                "sources": imp.get("sources", []),
            }
            detail = imp.get("detail", "")
            if detail:
                entry["detail"] = detail
            if entry["impact"] in ("structural", "transformative"):
                entry["execution"] = {"mode": "delegate", "subagent_type": "builder"}
            else:
                entry["execution"] = {"mode": "inline"}
            task_plan.append(entry)

        if evaluator_result.preserve:
            task_plan.append(
                {
                    "type": "verify_preserve",
                    "description": ("Verify preserved strengths haven't regressed and that earlier " "correctness fixes still pass after later changes"),
                    "execution": {"mode": "inline"},
                    "items": [
                        {
                            "criterion_id": p.get("criterion_id", ""),
                            "what": p.get("what", ""),
                            "source": p.get("source", ""),
                        }
                        for p in evaluator_result.preserve
                    ],
                },
            )

        return task_plan
