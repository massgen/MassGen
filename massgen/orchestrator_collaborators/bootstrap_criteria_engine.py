"""Bootstrap criteria draining/discrimination, extracted from Orchestrator.

All shared accumulator state (``_bootstrap_criteria_accumulator``,
``_bootstrap_round_index``, ``_bootstrap_discriminator_completed_signatures``)
is owned by the orchestrator and only mutated via the orchestrator back-ref so
the not-yet-extracted ChecklistGateManager continues to see a single owner.

Helpers that remain on the orchestrator are invoked through the back-ref:
``_parse_criteria_response`` (we use the canonical implementation in
``massgen.evaluation_criteria_generator`` directly) and the delegator wrappers
the orchestrator keeps for back-compat.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid as _uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from massgen.logger_config import get_log_session_dir, logger

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class BootstrapCriteriaEngine:
    """Drain pending criteria proposals and run the between-rounds discriminator."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    # ---- Public entry points (delegated 1:1 from Orchestrator) ----

    def drain_pending_criteria_proposals(self) -> None:
        orch = self._orchestrator
        coord = getattr(orch.config, "coordination_config", None)
        if coord is None:
            return
        from massgen.bootstrap_criteria import is_bootstrap_mode, merge_proposals

        criteria_mode = getattr(coord, "criteria_mode", "static")
        if not is_bootstrap_mode(criteria_mode):
            return
        cap = int(getattr(coord, "bootstrap_max_total", 30) or 0)
        agent_states = getattr(orch, "agent_states", {}) or {}
        merged_any = False
        for state in agent_states.values():
            pending = getattr(state, "criteria_proposals", None)
            if not pending:
                continue
            before = len(orch._bootstrap_criteria_accumulator)
            orch._bootstrap_criteria_accumulator = merge_proposals(
                orch._bootstrap_criteria_accumulator,
                list(pending),
                cap=cap,
            )
            if len(orch._bootstrap_criteria_accumulator) != before:
                merged_any = True
            state.criteria_proposals = []

        per_agent_cap = int(getattr(coord, "bootstrap_max_per_agent_per_round", 0) or 0)
        agents = getattr(orch, "agents", {}) or {}
        for agent in agents.values():
            backend = getattr(agent, "backend", None)
            specs_path = getattr(backend, "_checklist_specs_path", None)
            if not specs_path:
                continue
            jsonl_path = Path(specs_path).parent / "proposed_criteria.jsonl"
            if not jsonl_path.exists():
                continue
            try:
                drain_path = jsonl_path.with_suffix(
                    jsonl_path.suffix + f".draining.{os.getpid()}.{_uuid.uuid4().hex[:8]}",
                )
                jsonl_path.rename(drain_path)
            except FileNotFoundError:
                continue
            except OSError as exc:
                logger.debug("[bootstrap_criteria] could not rename %s for drain: %s", jsonl_path, exc)
                continue
            harvested: list[dict[str, Any]] = []
            truncated_by_cap = False
            try:
                with drain_path.open(encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(entry, dict):
                            continue
                        if not (entry.get("text") or "").strip():
                            continue
                        if per_agent_cap > 0 and len(harvested) >= per_agent_cap:
                            truncated_by_cap = True
                            break
                        harvested.append(entry)
            except OSError as exc:
                logger.debug("[bootstrap_criteria] failed to read drained file %s: %s", drain_path, exc)
            finally:
                try:
                    drain_path.unlink()
                except OSError:
                    pass
            if truncated_by_cap:
                logger.info(
                    "[bootstrap_criteria] per-agent cap (%d) reached for %s; remaining JSONL entries dropped",
                    per_agent_cap,
                    jsonl_path.parent.name,
                )
            if not harvested:
                continue
            before = len(orch._bootstrap_criteria_accumulator)
            orch._bootstrap_criteria_accumulator = merge_proposals(
                orch._bootstrap_criteria_accumulator,
                harvested,
                cap=cap,
            )
            if len(orch._bootstrap_criteria_accumulator) != before:
                merged_any = True
        if merged_any:
            self.persist_bootstrap_accumulator()

    async def maybe_run_bootstrap_discriminator(self, current_answers: dict[str, str]) -> int:
        orch = self._orchestrator
        coord = getattr(orch.config, "coordination_config", None)
        if coord is None or getattr(coord, "criteria_mode", "static") != "bootstrap_subagent":
            return 0
        if not current_answers:
            return 0
        content_signature = tuple(
            sorted((aid, hashlib.sha1(str(content).encode("utf-8")).hexdigest()[:16]) for aid, content in current_answers.items()),
        )
        seen = getattr(orch, "_bootstrap_discriminator_completed_signatures", None)
        if seen is None:
            seen = set()
            orch._bootstrap_discriminator_completed_signatures = seen
        if content_signature in seen:
            return 0
        seen.add(content_signature)
        return await self.run_bootstrap_discriminator_step()

    async def run_bootstrap_discriminator_step(self) -> int:
        orch = self._orchestrator
        coord = getattr(orch.config, "coordination_config", None)
        if coord is None or getattr(coord, "criteria_mode", "static") != "bootstrap_subagent":
            return 0

        tracker = getattr(orch, "coordination_tracker", None)
        answers_by_agent = getattr(tracker, "answers_by_agent", None) if tracker else None
        if not answers_by_agent:
            return 0
        latest: dict[str, str] = {}
        for aid, ans_list in answers_by_agent.items():
            if not ans_list:
                continue
            last = ans_list[-1]
            content = getattr(last, "content", None) or getattr(last, "answer", None) or ""
            if content:
                latest[aid] = content
        if not latest:
            return 0

        task = getattr(orch, "current_task", "") or ""
        existing_accumulator = list(orch._bootstrap_criteria_accumulator or [])

        prompt_parts: list[str] = [
            "You are a discriminative critic for a multi-agent coordination system.",
            "Your job: emit evaluation criteria the CURRENT ANSWERS fail to satisfy.",
            "",
            f"# Task\n{task}",
            "",
            "# Current Answers",
        ]
        for aid, content in latest.items():
            preview = content if len(content) <= 4000 else content[:4000] + "..."
            prompt_parts.append(f"\n## {aid}\n{preview}")
        if existing_accumulator:
            prompt_parts.append("\n# Criteria already proposed (do not repeat)")
            for entry in existing_accumulator:
                prompt_parts.append(f"- {entry.get('text', '')}")
        prompt_parts.append(
            "\n# Your Output\n"
            'Produce a JSON object: {"aspiration": "<one-sentence vision of an ideal answer>", '
            '"criteria": [{"text": "...", "category": "primary|standard|stretch", '
            '"anti_patterns": ["..."]}, ...]}. '
            "Each criterion must (a) take a position on what 'good' means on a specific "
            "dimension, not a dimension label; (b) describe a quality the current answers "
            "do NOT fully achieve; (c) be reusable for future similar tasks, not specific "
            "to this exact wording. Emit 2-5 criteria.\n\n"
            "Write the JSON to a file called `criteria.json` in your workspace and also "
            "include it verbatim in your final answer text. The orchestrator will pick "
            "up `criteria.json` from your workspace; the inline copy is a fallback.\n\n"
            "Do not run a refinement loop. One pass is enough. Do not call planning, "
            "checklist, or evaluation tools — just analyze the answers and write the JSON.",
        )
        prompt = "\n".join(prompt_parts)

        try:
            from massgen.subagent.manager import SubagentManager
            from massgen.subagent.models import SubagentOrchestratorConfig
        except ImportError as exc:
            logger.warning("[bootstrap_criteria] SubagentManager unavailable: %s", exc)
            return 0

        parent_workspace = "."
        for agent in (orch.agents or {}).values():
            fs = getattr(getattr(agent, "backend", None), "filesystem_manager", None)
            cwd = getattr(fs, "cwd", None) if fs else None
            if cwd:
                parent_workspace = str(cwd)
                break

        discriminator_workspace = parent_workspace
        try:
            discriminator_workspace = os.path.join(parent_workspace, ".bootstrap_discriminator")
            os.makedirs(discriminator_workspace, exist_ok=True)
            context_md_path = os.path.join(discriminator_workspace, "CONTEXT.md")
            with open(context_md_path, "w", encoding="utf-8") as fh:
                fh.write(
                    "# Bootstrap Criteria Discriminator\n\n"
                    f"Task being critiqued:\n{task}\n\n"
                    "Goal: identify quality dimensions the current answers fail to satisfy "
                    "and emit them as JSON proposed_criteria. See the spawn task for the "
                    "exact output schema.\n",
                )
        except OSError as exc:
            logger.warning(
                "[bootstrap_criteria] failed to materialize CONTEXT.md for discriminator: %s",
                exc,
            )
            discriminator_workspace = parent_workspace

        simplified_configs: list[dict[str, Any]] = []
        for aid, agent in (orch.agents or {}).items():
            backend = getattr(agent, "backend", None)
            cfg = getattr(backend, "config", {}) if backend else {}
            backend_cfg = {
                "type": cfg.get("type", "openai") if isinstance(cfg, dict) else "openai",
                "model": cfg.get("model") if isinstance(cfg, dict) else None,
                "enable_mcp_command_line": False,
                "enable_code_based_tools": False,
                "exclude_file_operation_mcps": False,
            }
            simplified_configs.append({"id": f"critic_{aid}", "backend": backend_cfg})
            break
        if not simplified_configs:
            return 0

        display = None
        anchor_agent_id = None
        subagent_id = None
        spawn_call_id = None
        try:
            subagent_config = SubagentOrchestratorConfig(
                enabled=True,
                agents=simplified_configs,
                coordination={
                    "enable_subagents": False,
                    "broadcast": False,
                    "max_new_answers_per_agent": 1,
                    "max_new_answers_global": 1,
                    "voting_threshold": 1,
                    "fast_iteration_mode": True,
                },
            )
            log_dir = None
            try:
                log_dir = get_log_session_dir()
            except Exception:
                pass
            manager = SubagentManager(
                parent_workspace=discriminator_workspace,
                parent_agent_id="bootstrap_discriminator",
                orchestrator_id=getattr(orch, "orchestrator_id", "orchestrator"),
                parent_agent_configs=simplified_configs,
                max_concurrent=1,
                default_timeout=180,
                subagent_orchestrator_config=subagent_config,
                log_directory=str(log_dir) if log_dir else None,
            )
            next_round_idx = int(getattr(orch, "_bootstrap_round_index", 0) or 0) + 1
            orch._bootstrap_round_index = next_round_idx
            subagent_id = f"bootstrap_discriminator_{next_round_idx}"

            display = getattr(getattr(orch, "coordination_ui", None), "display", None)
            anchor_agent_id = next(iter((orch.agents or {}).keys()), None)
            spawn_call_id = subagent_id
            if display and anchor_agent_id and hasattr(display, "notify_runtime_subagent_started"):
                try:
                    display.notify_runtime_subagent_started(
                        agent_id=anchor_agent_id,
                        subagent_id=subagent_id,
                        task=prompt,
                        timeout_seconds=180,
                        call_id=spawn_call_id,
                    )
                except Exception as _exc:
                    logger.debug("[bootstrap_criteria] notify_runtime_subagent_started failed: %s", _exc)

            result = await manager.spawn_subagent(
                task=prompt,
                subagent_id=subagent_id,
                timeout_seconds=180,
                refine=False,
            )
        except Exception as exc:
            logger.warning("[bootstrap_criteria] discriminator spawn failed: %s", exc, exc_info=True)
            if display and anchor_agent_id and hasattr(display, "notify_runtime_subagent_completed"):
                try:
                    display.notify_runtime_subagent_completed(
                        agent_id=anchor_agent_id,
                        subagent_id=subagent_id or "bootstrap_discriminator",
                        call_id=spawn_call_id or "bootstrap_discriminator",
                        status="failed",
                        error=str(exc),
                    )
                except Exception:
                    pass
            return 0

        if not getattr(result, "success", False):
            logger.info(
                "[bootstrap_criteria] discriminator subagent returned success=False; skipping merge",
            )
            if display and anchor_agent_id and hasattr(display, "notify_runtime_subagent_completed"):
                try:
                    display.notify_runtime_subagent_completed(
                        agent_id=anchor_agent_id,
                        subagent_id=subagent_id,
                        call_id=spawn_call_id,
                        status="failed",
                    )
                except Exception:
                    pass
            return 0
        answer_text = getattr(result, "answer", "") or ""

        from massgen.bootstrap_criteria import merge_proposals
        from massgen.evaluation_criteria_generator import _parse_criteria_response

        criteria = []
        artifact_log_dir = str(log_dir) if log_dir else None
        if artifact_log_dir:
            try:
                from massgen.precollab_utils import find_precollab_artifact

                artifact_path = find_precollab_artifact(
                    artifact_log_dir,
                    subagent_id,
                    "criteria.json",
                )
                if artifact_path is not None:
                    artifact_text = artifact_path.read_text(encoding="utf-8")
                    criteria, _aspiration = _parse_criteria_response(
                        artifact_text,
                        min_criteria=1,
                        max_criteria=10,
                    )
                    if criteria:
                        logger.info(
                            "[bootstrap_criteria] discriminator picked up criteria.json (%d criteria)",
                            len(criteria),
                        )
            except Exception as _exc:
                logger.debug("[bootstrap_criteria] criteria.json pickup failed: %s", _exc)

        if not criteria and not answer_text:
            if display and anchor_agent_id and hasattr(display, "notify_runtime_subagent_completed"):
                try:
                    display.notify_runtime_subagent_completed(
                        agent_id=anchor_agent_id,
                        subagent_id=subagent_id,
                        call_id=spawn_call_id,
                        status="completed",
                    )
                except Exception:
                    pass
            return 0

        if not criteria:
            criteria, _aspiration = _parse_criteria_response(answer_text, min_criteria=1, max_criteria=10)
        if not criteria:
            logger.info("[bootstrap_criteria] discriminator returned no parseable criteria")
            if display and anchor_agent_id and hasattr(display, "notify_runtime_subagent_completed"):
                try:
                    display.notify_runtime_subagent_completed(
                        agent_id=anchor_agent_id,
                        subagent_id=subagent_id,
                        call_id=spawn_call_id,
                        status="completed",
                        answer_preview="No parseable criteria returned",
                    )
                except Exception:
                    pass
            return 0
        proposals = [
            {
                "text": c.text,
                "category": c.category,
                "anti_patterns": list(c.anti_patterns) if getattr(c, "anti_patterns", None) else None,
            }
            for c in criteria
        ]
        before = len(orch._bootstrap_criteria_accumulator)
        cap = int(getattr(coord, "bootstrap_max_total", 30) or 0)
        orch._bootstrap_criteria_accumulator = merge_proposals(
            orch._bootstrap_criteria_accumulator,
            proposals,
            cap=cap,
        )
        added = len(orch._bootstrap_criteria_accumulator) - before
        if added > 0:
            self.persist_bootstrap_accumulator()
            logger.info(
                "[bootstrap_criteria] discriminator added %d new criteria (accumulator size: %d)",
                added,
                len(orch._bootstrap_criteria_accumulator),
            )
        if display and anchor_agent_id and hasattr(display, "notify_runtime_subagent_completed"):
            try:
                preview = f"Added {added} new criterion/criteria to accumulator" if added > 0 else "No new criteria"
                display.notify_runtime_subagent_completed(
                    agent_id=anchor_agent_id,
                    subagent_id=subagent_id,
                    call_id=spawn_call_id,
                    status="completed",
                    answer_preview=preview,
                )
            except Exception:
                pass
        return added

    def drain_at_session_end(self) -> None:
        try:
            self.drain_pending_criteria_proposals()
        except Exception as exc:  # pragma: no cover — defensive
            logger.debug("[bootstrap_criteria] session-end drain failed: %s", exc)

    def persist_bootstrap_accumulator(self) -> None:
        orch = self._orchestrator
        try:
            log_dir = get_log_session_dir()
        except Exception:
            log_dir = None
        if not log_dir:
            return
        try:
            out_path = Path(log_dir) / "bootstrap_criteria_accumulator.json"
            payload = {
                "count": len(orch._bootstrap_criteria_accumulator),
                "criteria": list(orch._bootstrap_criteria_accumulator),
            }
            out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as exc:  # pragma: no cover — best-effort logging
            logger.debug("[bootstrap_criteria] failed to persist accumulator: %s", exc)
