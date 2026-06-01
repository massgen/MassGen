"""Restore orchestrator state from a previous session's log directory.

Extracted from :mod:`massgen.orchestrator`. Owns three methods that read prior
log artifacts and rehydrate the Orchestrator's runtime state:

- :meth:`PreviousLogRestorer.restore_from_previous_log` (async): primary entry
  for the resume-from-log flow. Restores answer snapshots, optional workspace
  contents, evaluation criteria, and personas up to (and including) a target
  round.
- :meth:`PreviousLogRestorer.restore_workspace_from_latest_answer_dir`: used
  in timeout/fallback paths to repopulate the live workspace from the most
  recent per-round answer directory.
- :meth:`PreviousLogRestorer.get_previous_turns_context_paths`: returns the
  Orchestrator's stored list of previous turns (used as context paths in the
  current turn).

All shared state lives on the Orchestrator; every read/write routes through
``self._orchestrator``. Symbols patched at the orchestrator module path
(notably ``get_log_session_dir``) are looked up lazily via
``from massgen import orchestrator as _orch_mod`` so test
``patch("massgen.orchestrator.<sym>")`` hooks keep working.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from massgen.logger_config import logger

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class PreviousLogRestorer:
    """Restore Orchestrator state from a previous session's log directory."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    async def restore_from_previous_log(self, resume_config: dict[str, Any]) -> None:
        """Restore answers, workspaces, and changedocs from a previous log.

        Loads state from a previous run so the orchestrator can resume at a
        later round without re-running earlier rounds.

        Args:
            resume_config: Dict with 'log_path' (str) and 'round' (int).
                          Restores all answer snapshots up to and including
                          the specified round.
        """
        import json as _json

        import yaml as _yaml

        orch = self._orchestrator

        log_path = Path(resume_config["log_path"])
        target_round = resume_config["round"]

        logger.info(
            f"[Orchestrator] Restoring from previous log: {log_path}, " f"resuming after round {target_round}",
        )

        # Load snapshot mappings
        mappings_file = log_path / "snapshot_mappings.json"
        if not mappings_file.exists():
            logger.error(f"[Orchestrator] snapshot_mappings.json not found in {log_path}")
            return

        mappings = _json.loads(mappings_file.read_text())

        # Filter to answer snapshots up to target round
        answer_snapshots = {label: mapping for label, mapping in mappings.items() if mapping.get("type") == "answer" and mapping.get("round", 0) <= target_round}

        if not answer_snapshots:
            logger.warning(
                f"[Orchestrator] No answer snapshots found for round <= {target_round}",
            )
            return

        # Restore each answer in label order (agent1.1, agent1.2, agent2.1, etc.)
        for label in sorted(answer_snapshots.keys()):
            mapping = answer_snapshots[label]
            agent_id = mapping["agent_id"]
            timestamp = mapping["timestamp"]
            snap_dir = log_path / agent_id / timestamp

            # Read answer
            answer_file = snap_dir / "answer.txt"
            if not answer_file.exists():
                logger.warning(f"[Orchestrator] answer.txt not found: {answer_file}")
                continue
            answer_text = answer_file.read_text()

            # Read changedoc if present
            changedoc_file = snap_dir / "changedoc.md"
            changedoc_text = changedoc_file.read_text() if changedoc_file.exists() else None

            # Add answer to coordination tracker
            orch.coordination_tracker.add_agent_answer(
                agent_id,
                answer_text,
                snapshot_timestamp=timestamp,
            )

            # Attach changedoc to the answer
            if changedoc_text:
                answers = orch.coordination_tracker.answers_by_agent.get(agent_id, [])
                if answers:
                    answers[-1].changedoc = changedoc_text

            # Restore workspace if present and agent has filesystem_manager
            workspace_dir = snap_dir / "workspace"
            if workspace_dir.is_dir() and agent_id in orch.agents:
                agent = orch.agents[agent_id]
                fm = getattr(agent.backend, "filesystem_manager", None)
                if fm and hasattr(fm, "cwd") and fm.cwd:
                    dest = Path(fm.cwd)
                    dest.mkdir(parents=True, exist_ok=True)
                    for src_file in workspace_dir.rglob("*"):
                        if src_file.is_file():
                            rel = src_file.relative_to(workspace_dir)
                            dst = dest / rel
                            dst.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(str(src_file), str(dst))
                    # Clear stale task plan so agent starts with a fresh plan
                    stale_plan = dest / "tasks" / "plan.json"
                    try:
                        stale_plan.unlink()
                        logger.info(f"[Orchestrator] Cleared stale task plan from restored workspace for {agent_id}")
                    except FileNotFoundError:
                        pass

            logger.info(
                f"[Orchestrator] Restored {label}: agent={agent_id}, "
                f"round={mapping['round']}, answer_len={len(answer_text)}" + (f", changedoc_len={len(changedoc_text)}" if changedoc_text else ""),
            )

        # Set agent rounds to target_round + 1 (they've completed target_round)
        for agent_id in orch.agents:
            orch.coordination_tracker.set_agent_round(agent_id, target_round + 1)

        # Update agent states so the loop knows these agents have answered
        for agent_id in orch.agents:
            answers = orch.coordination_tracker.answers_by_agent.get(agent_id, [])
            if answers and agent_id in orch.agent_states:
                orch.agent_states[agent_id].answer = answers[-1].content
                orch.agent_states[agent_id].answer_count = len(answers)

        # Load generated evaluation criteria from the log if no inline criteria override
        inline = getattr(
            getattr(orch.config, "coordination_config", None),
            "checklist_criteria_inline",
            None,
        )
        if not inline and orch._generated_evaluation_criteria is None:
            criteria_file = log_path / "generated_evaluation_criteria.yaml"
            if criteria_file.exists():
                try:
                    from massgen.evaluation_criteria_generator import GeneratedCriterion

                    criteria_data = _yaml.safe_load(criteria_file.read_text())
                    _legacy_cat_map = {"must": "standard", "core": "standard", "should": "standard", "could": "stretch"}
                    if isinstance(criteria_data, list):
                        orch._generated_evaluation_criteria = [
                            GeneratedCriterion(
                                id=c.get("id", f"E{i + 1}"),
                                text=c.get("text") or c.get("description") or c.get("name", ""),
                                category=_legacy_cat_map.get(c.get("category", "standard"), c.get("category", "standard")),
                                verify_by=c.get("verify_by") or None,
                                anti_patterns=c.get("anti_patterns") if isinstance(c.get("anti_patterns"), list) else None,
                            )
                            for i, c in enumerate(criteria_data)
                            if c.get("text") or c.get("description") or c.get("name")
                        ]
                        orch._evaluation_criteria_generated = True
                        logger.info(
                            f"[Orchestrator] Loaded {len(orch._generated_evaluation_criteria)} " "evaluation criteria from previous log",
                        )
                except Exception as e:
                    logger.warning(
                        f"[Orchestrator] Failed to load evaluation criteria from log: {e}",
                    )

        # Load generated personas from the log if not already set
        if not orch._generated_personas:
            personas_file = log_path / "generated_personas.yaml"
            if personas_file.exists():
                try:
                    from massgen.persona_generator import GeneratedPersona

                    personas_data = _yaml.safe_load(personas_file.read_text())
                    if isinstance(personas_data, dict):
                        for agent_id, pdata in personas_data.items():
                            orch._generated_personas[agent_id] = GeneratedPersona(
                                agent_id=agent_id,
                                persona_text=pdata.get("persona_text", ""),
                                attributes=pdata.get("attributes", {}),
                            )
                        orch._personas_generated = True
                        logger.info(
                            f"[Orchestrator] Loaded {len(orch._generated_personas)} " "personas from previous log",
                        )
                except Exception as e:
                    logger.warning(
                        f"[Orchestrator] Failed to load personas from log: {e}",
                    )

        logger.info(
            f"[Orchestrator] Resume complete: restored {len(answer_snapshots)} snapshots, " f"agents will start at round {target_round + 1}",
        )

    def restore_workspace_from_latest_answer_dir(self, agent_id: str) -> bool:
        """Restore an agent's workspace from its most recent per-round answer directory.

        Used before final snapshot save in timeout/fallback paths where the live
        workspace has been cleared between rounds and only has scaffolding.

        Returns True if restoration happened, False otherwise.
        """
        # Lazy import so test patches at ``massgen.orchestrator.get_log_session_dir``
        # are honored.
        from massgen import orchestrator as _orch_mod

        orch = self._orchestrator

        agent = orch.agents.get(agent_id)
        if not agent or not agent.backend.filesystem_manager:
            return False

        log_session_dir = _orch_mod.get_log_session_dir()
        if not log_session_dir:
            return False

        agent_log_dir = log_session_dir / agent_id
        if not agent_log_dir.exists():
            return False

        # Find all timestamped answer directories (format: YYYYMMDD_HHMMSS_ffffff)
        # Sort descending to get most recent first
        answer_dirs = sorted(
            [d for d in agent_log_dir.iterdir() if d.is_dir() and d.name != "final" and (d / "workspace").is_dir()],
            key=lambda d: d.name,
            reverse=True,
        )

        if not answer_dirs:
            return False

        latest_workspace = answer_dirs[0] / "workspace"
        workspace_path = Path(agent.backend.filesystem_manager.cwd)

        # Copy items from the latest answer dir into the live workspace
        # (non-overwriting — preserve anything already there)
        items_restored = 0
        for item in latest_workspace.iterdir():
            if item.is_symlink():
                continue
            dest = workspace_path / item.name
            if dest.exists():
                continue
            if item.is_file():
                shutil.copy2(item, dest)
                items_restored += 1
            elif item.is_dir():
                shutil.copytree(
                    item,
                    dest,
                    symlinks=True,
                    ignore_dangling_symlinks=True,
                )
                items_restored += 1

        logger.info(
            f"[Orchestrator] Restored {items_restored} items from latest answer dir " f"{latest_workspace} to workspace for {agent_id}",
        )
        return items_restored > 0

    def get_previous_turns_context_paths(self) -> list[dict[str, Any]]:
        """Return previous turns as context paths for the current turn's agents."""
        return self._orchestrator._previous_turns
