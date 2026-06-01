"""Checklist gate management, extracted from Orchestrator.

Owns the full life cycle of the ``submit_checklist`` / ``draft_approach`` MCP
tools and the related per-agent checklist runtime state. All shared state is
mutated through the orchestrator back-ref (``self._orchestrator``) so the
other collaborators that already write the same fields (notably
:class:`PeerAnswerVisibilityTracker` for ``pending_checklist_recheck_labels``
and the bootstrap/decomposition engines for criteria) see one consistent live
set.

Invariants preserved byte-for-byte:

- ``agent_states[*].pending_checklist_recheck_labels`` is a DUAL writer with
  :class:`PeerAnswerVisibilityTracker`. Both writers mutate via
  ``self._orchestrator.agent_states[...]`` (never a local copy).
- ``backend._checklist_state`` / ``_checklist_items`` /
  ``_checklist_specs_path`` are mutated on the live ``agent.backend`` object
  because the running stdio MCP server, the coordination loop, and the peer
  visibility tracker all read these attributes directly.
- The newest-first selection and fairness cap behaviour of mid-stream
  injection are unaffected by this extraction.

Module-level imports of test-patchable symbols are intentionally avoided:
``write_checklist_specs``, ``build_server_config`` and ``create_sdk_mcp_server``
are imported lazily inside the methods that need them, exactly as the original
``Orchestrator`` did, so any test that patches them at
``massgen.orchestrator.<symbol>`` continues to work without changes.
"""

from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from massgen.events import EventType as StructuredEventType
from massgen.logger_config import get_event_emitter, logger

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class ChecklistGateManager:
    """Owns checklist tool registration, state refresh, and convergence detection."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    # ------------------------------------------------------------------
    # Criteria resolution
    # ------------------------------------------------------------------

    def get_decomposition_criteria_for_agent(self, agent_id: str | None) -> list | None:
        """Return decomposition execution criteria for one agent when available."""
        orch = self._orchestrator
        if not agent_id or not orch._is_decomposition_mode():
            return None

        explicit = orch._agent_subtask_criteria.get(agent_id)
        if explicit:
            return explicit

        subtask = orch._agent_subtasks.get(agent_id)
        if not subtask:
            return None

        from massgen.evaluation_criteria_generator import (
            build_decomposition_execution_criteria,
        )

        return build_decomposition_execution_criteria(subtask)

    def get_active_criteria(
        self,
        agent_id: str | None = None,
    ) -> tuple[list[str] | None, dict[str, str] | None, dict[str, str] | None, dict[str, list[str]] | None, dict[str, dict[str, str]] | None]:
        """Return (items, categories, verify_by, anti_patterns, score_anchors) using the criteria priority waterfall.

        Priority: inline > decomposition-agent > generated > preset > None.
        Returns (None, None, None, None, None) when no custom criteria source is configured.
        This is used by both _init_checklist_tool and the system prompt builder
        to ensure criteria are consistent across the checklist MCP tool and
        the system prompt shown to the model.
        """
        orch = self._orchestrator

        def _to_tuple(criteria: list) -> tuple[list[str], dict[str, str], dict[str, str] | None, dict[str, list[str]] | None, dict[str, dict[str, str]] | None]:
            texts = [c.text for c in criteria]
            cats = {c.id: c.category for c in criteria}
            vby = {c.id: c.verify_by for c in criteria if c.verify_by}
            anti = {c.id: c.anti_patterns for c in criteria if getattr(c, "anti_patterns", None)}
            anchors = {c.id: c.score_anchors for c in criteria if getattr(c, "score_anchors", None)}
            return texts, cats, vby or None, anti or None, anchors or None

        inline = getattr(
            getattr(orch.config, "coordination_config", None),
            "checklist_criteria_inline",
            None,
        )
        if inline:
            from massgen.evaluation_criteria_generator import criteria_from_inline

            return _to_tuple(criteria_from_inline(inline))

        decomposition_criteria = self.get_decomposition_criteria_for_agent(agent_id)
        if decomposition_criteria is not None:
            return _to_tuple(decomposition_criteria)

        if orch._generated_evaluation_criteria is not None:
            return _to_tuple(orch._generated_evaluation_criteria)

        preset = getattr(
            getattr(orch.config, "coordination_config", None),
            "checklist_criteria_preset",
            None,
        )
        if preset:
            from massgen.evaluation_criteria_generator import get_criteria_for_preset

            return _to_tuple(get_criteria_for_preset(preset))

        return None, None, None, None, None

    def resolve_effective_checklist_criteria(
        self,
        agent_id: str | None = None,
    ) -> tuple[list[str], dict[str, str], dict[str, str] | None, str, dict[str, list[str]] | None, dict[str, dict[str, str]] | None]:
        """Return checklist criteria with changedoc/generic fallback plus source.

        Returns:
            (items, categories, verify_by, source, anti_patterns, score_anchors)
        """
        orch = self._orchestrator
        orch._drain_pending_criteria_proposals()
        from massgen.bootstrap_criteria import (
            augment_with_accumulator,
            demote_categories,
            find_nondiscriminative_criteria,
            is_bootstrap_mode,
        )

        def _demote_nondiscriminative(cats: dict[str, str]) -> dict[str, str]:
            """In bootstrap mode, soften criteria that didn't discriminate last round.

            Free-pass criteria (every agent scored them near-identically) provide no
            gradient, so they are reclassified to ``stretch`` and stop acting as hard
            gates. A protected floor keeps the gate from being hollowed out. No-op in
            static mode or before any per-agent scores exist.
            """
            if not is_bootstrap_mode(criteria_mode):
                return cats
            scores = getattr(orch, "_last_per_agent_criterion_scores", None)
            if not scores:
                return cats
            stale = find_nondiscriminative_criteria(scores)
            if not stale:
                return cats
            logger.info(
                "[Orchestrator] Demoting non-discriminative criteria to stretch: %s",
                stale,
            )
            return demote_categories(cats, stale)

        from massgen.system_prompt_sections import (
            _CHECKLIST_ITEM_ANTI_PATTERNS,
            _CHECKLIST_ITEM_ANTI_PATTERNS_CHANGEDOC,
            _CHECKLIST_ITEM_CATEGORIES,
            _CHECKLIST_ITEM_CATEGORIES_CHANGEDOC,
            _CHECKLIST_ITEM_SCORE_ANCHORS,
            _CHECKLIST_ITEM_SCORE_ANCHORS_CHANGEDOC,
            _CHECKLIST_ITEMS,
            _CHECKLIST_ITEMS_CHANGEDOC,
        )

        coord = getattr(orch.config, "coordination_config", None)
        criteria_mode = getattr(coord, "criteria_mode", "static")
        accumulator = list(getattr(orch, "_bootstrap_criteria_accumulator", []) or [])
        use_accumulator = is_bootstrap_mode(criteria_mode) and bool(accumulator)

        # Route through the orchestrator delegators so tests that
        # monkeypatch ``orch._get_active_criteria`` /
        # ``orch._get_decomposition_criteria_for_agent`` (e.g.
        # ``test_discriminative_pruning``) are honored. Calling
        # ``self.get_active_criteria(...)`` here would bypass those patches.
        custom_items, item_categories, item_verify_by, item_anti_patterns, item_score_anchors = orch._get_active_criteria(agent_id)
        if custom_items is not None:
            inline = getattr(coord, "checklist_criteria_inline", None)
            if inline:
                source = "inline"
            elif agent_id and orch._get_decomposition_criteria_for_agent(agent_id) is not None:
                source = "decomposition_subtask"
            elif orch._generated_evaluation_criteria is not None:
                source = "generated"
            else:
                source = "preset"
            if use_accumulator:
                items, cats, vby, anti, anchors = augment_with_accumulator(
                    custom_items,
                    item_categories or {},
                    item_verify_by,
                    item_anti_patterns,
                    item_score_anchors,
                    accumulator,
                )
                return items, _demote_nondiscriminative(cats), vby, source, anti, anchors
            return custom_items, _demote_nondiscriminative(item_categories or {}), item_verify_by, source, item_anti_patterns, item_score_anchors

        if use_accumulator:
            # No base source — accumulator stands alone with source label "bootstrap".
            items, cats, vby, anti, anchors = augment_with_accumulator(
                [],
                {},
                None,
                None,
                None,
                accumulator,
            )
            return items, _demote_nondiscriminative(cats), vby, "bootstrap", anti, anchors

        if orch._is_changedoc_enabled():
            return (
                list(_CHECKLIST_ITEMS_CHANGEDOC),
                dict(_CHECKLIST_ITEM_CATEGORIES_CHANGEDOC),
                None,
                "changedoc",
                dict(_CHECKLIST_ITEM_ANTI_PATTERNS_CHANGEDOC),
                dict(_CHECKLIST_ITEM_SCORE_ANCHORS_CHANGEDOC),
            )

        return (
            list(_CHECKLIST_ITEMS),
            dict(_CHECKLIST_ITEM_CATEGORIES),
            None,
            "generic",
            dict(_CHECKLIST_ITEM_ANTI_PATTERNS),
            dict(_CHECKLIST_ITEM_SCORE_ANCHORS),
        )

    # ------------------------------------------------------------------
    # Display push
    # ------------------------------------------------------------------

    def push_cached_criteria_to_display(self, *, force: bool = False) -> None:
        """Push cached evaluation criteria to the active display when available."""
        orch = self._orchestrator
        if getattr(orch, "_criteria_pushed_to_display", False) and not force:
            return

        payload = getattr(orch, "_criteria_display_payload", None)
        if not payload:
            return

        try:
            _emitter = get_event_emitter()
            if _emitter:
                _emitter.emit_raw(
                    StructuredEventType.EVALUATION_CRITERIA_SET,
                    criteria=payload["criteria"],
                    source=payload["source"],
                )
            display = getattr(orch.coordination_ui, "display", None) if orch.coordination_ui else None
            if display and hasattr(display, "set_evaluation_criteria"):
                display.set_evaluation_criteria(payload["criteria"], source=payload["source"])
                orch._criteria_pushed_to_display = True
        except Exception:
            pass  # TUI notification is non-critical

    # ------------------------------------------------------------------
    # Tool initialization
    # ------------------------------------------------------------------

    def init_checklist_tool(self) -> None:
        """Register submit_checklist MCP tool if voting_sensitivity is checklist_gated.

        SDK-capable backends (ClaudeCode) get an in-process SDK MCP server.
        CLI-based backends (Codex) get state stored on the backend; the backend
        writes a stdio MCP server config at execution time when the workspace
        path is known.
        """
        orch = self._orchestrator
        sensitivity = getattr(orch.config, "voting_sensitivity", "")
        if sensitivity != "checklist_gated":
            # bootstrap_inline + non-checklist_gated voting is a misconfiguration:
            # the submit_checklist tool that carries proposed_criteria is never
            # registered, so the emission channel doesn't exist and the feature
            # silently produces zero criteria for the entire session. Refuse to
            # start so the user sees the problem at config-load time, not after
            # a long no-emission run.
            coord = getattr(orch.config, "coordination_config", None)
            if coord is not None and getattr(coord, "criteria_mode", "static") == "bootstrap_inline":
                raise ValueError(
                    "criteria_mode='bootstrap_inline' requires "
                    f"voting_sensitivity='checklist_gated', got {sensitivity!r}. "
                    "The submit_checklist tool that carries proposed_criteria is "
                    "only registered under checklist_gated voting. "
                    "Either set voting_sensitivity to 'checklist_gated' or switch "
                    "criteria_mode to 'bootstrap_subagent' (which uses a "
                    "between-rounds critic instead and does not need the tool).",
                )
            return

        from massgen.system_prompt_sections import ChecklistGate

        tracker = getattr(orch, "coordination_tracker", None)
        display_payload: dict[str, Any] | None = None

        for agent_id, agent in orch.agents.items():
            backend = agent.backend
            criteria_agent_id = agent_id if orch._is_decomposition_mode() else None
            items, item_categories, item_verify_by, criteria_source, _anti, item_score_anchors = self.resolve_effective_checklist_criteria(
                criteria_agent_id,
            )

            logger.info(
                "[Orchestrator._init_checklist_tool] Agent %s criteria source: %s, count: %d",
                agent_id,
                criteria_source,
                len(items),
            )
            for i, item_text in enumerate(items):
                cat = item_categories.get(f"E{i + 1}", "unknown")
                logger.info(
                    "[Orchestrator._init_checklist_tool]   %s E%d (%s): %s",
                    agent_id,
                    i + 1,
                    cat,
                    item_text[:120],
                )

            if display_payload is None:
                criteria_dicts = [
                    {
                        "id": f"E{i + 1}",
                        "text": text,
                        "category": item_categories.get(f"E{i + 1}", "standard"),
                        "verify_by": (item_verify_by or {}).get(f"E{i + 1}"),
                    }
                    for i, text in enumerate(items)
                ]
                display_payload = {
                    "criteria": criteria_dicts,
                    "source": criteria_source,
                }

            # Create mutable state dict — orchestrator updates before each round
            threshold = getattr(orch.config, "voting_threshold", 5) or 5
            total = orch.config.max_new_answers_per_agent or 5
            remaining = total
            gate = ChecklistGate.from_budget(threshold, remaining, total, num_items=len(items))
            # Determine active subagent types for novelty gating
            from massgen.subagent.type_scanner import DEFAULT_SUBAGENT_TYPES

            _active_subagent_types = getattr(
                getattr(orch.config, "coordination_config", None),
                "subagent_types",
                None,
            )
            if _active_subagent_types is None:
                _active_subagent_types = DEFAULT_SUBAGENT_TYPES
            _lowered_types = {t.lower() for t in _active_subagent_types}

            checklist_state = {
                "threshold": threshold,
                "remaining": remaining,
                "total": total,
                "terminate_action": "stop" if orch._is_decomposition_mode() else "vote",
                "iterate_action": "new_answer",
                "decomposition_mode": orch._is_decomposition_mode(),
                "has_existing_answers": False,  # True once any answer exists for this agent
                "require_gap_report": bool(
                    getattr(orch.config, "checklist_require_gap_report", True),
                ),
                "require_diagnostic_report": bool(
                    getattr(orch.config, "checklist_require_gap_report", True),
                ),
                "checklist_first_answer": bool(
                    getattr(orch.config, "checklist_first_answer", False),
                ),
                "max_checklist_calls_per_round": int(
                    getattr(orch.config, "max_checklist_calls_per_round", 1) or 1,
                ),
                "checklist_calls_this_round": 0,
                "checklist_history": [],
                # Needed by checklist server to interpret item semantics.
                "changedoc_mode": orch._is_changedoc_enabled(),
                "workspace_path": getattr(
                    getattr(backend, "filesystem_manager", None),
                    "cwd",
                    None,
                ),
                # Pre-computed so stdio server doesn't need massgen imports
                "required": gate.required_true,
                "cutoff": gate.confidence_cutoff,
                # E-prefix for evaluation items (replaces legacy T-prefix)
                "item_prefix": "E",
                # Latest injected labels that must be re-scored before improvements can be proposed.
                "pending_checklist_recheck_labels": [],
                # Dynamic core/stretch categories for convergence off-ramp
                "item_categories": item_categories,
                "item_verify_by": item_verify_by or {},
                "item_score_anchors": item_score_anchors or {},
                "criteria_source": criteria_source,
                # Discriminative criteria emergence (v0.1.85): exposes
                # proposed_criteria to the stdio submit_checklist schema when
                # bootstrap_inline is active. SDK path uses its own schema branch.
                "criteria_mode": getattr(
                    getattr(orch.config, "coordination_config", None),
                    "criteria_mode",
                    "static",
                ),
                # Novelty subagent guidance only when novelty type is available
                "novelty_subagent_enabled": "novelty" in _lowered_types,
                # Critic subagent guidance only when critic type is available
                "critic_subagent_enabled": "critic" in _lowered_types,
                # Builder subagent guidance only when builder type is available
                "builder_subagent_enabled": "builder" in _lowered_types,
                # Regression guard: agent-initiated blind comparison before committing
                "regression_guard_subagent_enabled": "regression_guard" in _lowered_types,
                # Quality rethinking subagent: per-element craft improvements
                "quality_rethinking_subagent_enabled": "quality_rethinking" in _lowered_types,
                # Planning injection dir for auto-populating task plan from draft_approach
                "planning_injection_dir": str(getattr(orch, "_planning_injection_dirs", {}).get(agent_id, "")),
                # Whether subagents are enabled (for delegation guidance in draft_approach message)
                "subagents_enabled": bool(
                    hasattr(orch.config, "coordination_config") and hasattr(orch.config.coordination_config, "enable_subagents") and orch.config.coordination_config.enable_subagents,
                ),
                # Post-evaluator task mode: once round_evaluator has already
                # injected next tasks, the parent should skip checklist loops.
                "round_evaluator_auto_injected": False,
                "round_evaluator_primary_artifact_path": "",
                "round_evaluator_verdict_artifact_path": "",
                "round_evaluator_next_tasks_artifact_path": "",
                "round_evaluator_objective": "",
                "round_evaluator_primary_strategy": "",
                "round_evaluator_why_this_strategy": "",
                "round_evaluator_strategy_mode": "",
                "round_evaluator_incremental_override_reason": "",
                "round_evaluator_success_contract": {},
                "round_evaluator_deprioritize_or_remove": [],
                "allowed_external_report_paths": [],
                "agent_answer_count": (len(tracker.answers_by_agent.get(agent_id, [])) if tracker is not None and hasattr(tracker, "answers_by_agent") else 0),
                "current_answer_label": (tracker.get_latest_answer_label(agent_id) if tracker is not None else None),
                "enable_quality_rethink_on_iteration": bool(
                    getattr(
                        getattr(orch.config, "coordination_config", None),
                        "enable_quality_rethink_on_iteration",
                        False,
                    ),
                ),
                "enable_novelty_on_iteration": bool(
                    getattr(
                        getattr(orch.config, "coordination_config", None),
                        "enable_novelty_on_iteration",
                        False,
                    ),
                ),
                # Evaluator personas config (opt-in)
                "evaluator_team_size": orch._get_evaluator_team_size(),
                "enable_evaluator_personas": bool(
                    getattr(
                        getattr(orch.config, "coordination_config", None),
                        "enable_evaluator_personas",
                        False,
                    ),
                ),
                # Impact gate config for draft_approach validation
                "improvements": dict(
                    getattr(
                        getattr(orch.config, "coordination_config", None),
                        "improvements",
                        {},
                    )
                    or {},
                ),
            }
            resolved_items = list(items)
            backend._checklist_state = checklist_state
            backend._checklist_items = resolved_items

            if getattr(backend, "supports_sdk_mcp", False):
                # SDK path: in-process MCP server (ClaudeCode)
                self.init_checklist_tool_sdk(
                    agent_id,
                    backend,
                    checklist_state,
                    resolved_items,
                )
            else:
                # Stdio path for backends with standard MCP infrastructure.
                # Write specs and register stdio MCP so the agent gets submit_checklist.
                if hasattr(backend, "mcp_servers"):
                    self.init_checklist_tool_stdio(agent_id, backend, checklist_state, resolved_items)
                else:
                    # Codex-like backends handle their own config writing.
                    logger.info(
                        f"[Orchestrator] Checklist tool for agent {agent_id}: " f"stdio mode (specs written at execution time)",
                    )

        if display_payload:
            orch._criteria_display_payload = display_payload
            self.push_cached_criteria_to_display(force=True)

    def init_checklist_tool_sdk(
        self,
        agent_id,
        backend,
        checklist_state,
        checklist_items,
    ) -> None:
        """Register checklist tool as an in-process SDK MCP server."""
        orch = self._orchestrator
        try:
            from claude_agent_sdk import create_sdk_mcp_server, tool
        except ImportError:
            logger.warning("claude-agent-sdk not available, checklist tool will not be registered")
            return

        from massgen.mcp_tools.checklist_tools_server import (
            build_round_evaluator_task_mode_redirect,
            evaluate_checklist_submission,
            evaluate_draft_approach,
        )

        # Define tool schema — each score entry requires a reasoning string
        # to force the model to justify every item.
        _all_agent_ids = sorted(orch.agents.keys())
        _is_decomposition = orch._is_decomposition_mode()
        _is_multi_agent = len(_all_agent_ids) > 1 and not _is_decomposition
        if _is_multi_agent:
            _num_agents = len(_all_agent_ids)
            _anon_ids = [f"agent{i + 1}" for i in range(_num_agents)]
            _scores_desc = (
                "Your confidence scores with reasoning for each checklist item. "
                f"This session has {_num_agents} agents. "
                "Use per-agent format where keys are the most recent answer label "
                'for each agent (labels look like "agent1.1", "agent2.1", '
                '"agent1.2", etc. — if an agent updated their answer, use the '
                'latest label, e.g., "agent1.2" not "agent1.1"). '
                "Example keys for this session: " + ", ".join(f'"{aid}.1"' for aid in _anon_ids) + ". "
                "Score ALL agents whose answers you have seen. "
                "Each agent entry maps criterion IDs to "
                '{"score": N, "reasoning": "..."} objects.'
            )
        else:
            if _is_decomposition:
                _scores_desc = (
                    "Your confidence scores with reasoning for each checklist item for your current subtask output. "
                    "Use flat format: "
                    '{"E1": {"score": N, "reasoning": "..."}, ...}. '
                    "You may use peer answers as evidence, but score your own current work rather than ranking all agents."
                )
            else:
                _scores_desc = "Your confidence scores with reasoning for each checklist item. " "Use flat format: " '{"E1": {"score": N, "reasoning": "..."}, ...}.'
        input_schema = {
            "type": "object",
            "properties": {
                "scores": {
                    "type": "object",
                    "description": _scores_desc,
                    "additionalProperties": True,
                },
                "report_path": {
                    "type": "string",
                    "description": ("Path to the markdown gap report in the workspace. " "Required when checklist report gating is enabled."),
                },
            },
            "required": ["scores"],
        }
        # Bootstrap criteria emergence (Variant A): expose proposed_criteria so
        # the agent can emit criteria a stronger answer would satisfy. Schema
        # only gains the field in bootstrap_inline mode; static-mode agents see
        # the historical schema unchanged.
        _criteria_mode = getattr(
            getattr(orch.config, "coordination_config", None),
            "criteria_mode",
            "static",
        )
        if _criteria_mode == "bootstrap_inline":
            input_schema["properties"]["proposed_criteria"] = {
                "type": "array",
                "description": (
                    "Optional list of new evaluation criteria a stronger answer would "
                    "satisfy that the current answers do NOT yet satisfy. Each entry: "
                    '{"text": str, "category": "primary"|"standard"|"stretch", '
                    '"anti_patterns": [str, ...]}. Keep short (<=3). Skip when no gap '
                    "is visible."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "category": {"type": "string"},
                        "anti_patterns": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["text"],
                },
            }

        # draft_approach input schema
        propose_schema = {
            "type": "object",
            "properties": {
                "vision": {
                    "type": "string",
                    "description": (
                        "Optional north star: what the ideal output would look " "like, independent of existing answers. Guides execution " "toward excellence rather than incremental fixes."
                    ),
                },
                "plan": {
                    "type": "object",
                    "description": (
                        "Map of criterion ID to list of entries describing what "
                        "to build. Each entry has 'plan' (what to do) and 'sources' "
                        "(which existing answers to draw from, or 'fresh' for new "
                        "ideas). Must cover ALL failing criteria."
                    ),
                    "additionalProperties": {
                        "type": "array",
                        "items": {
                            "oneOf": [
                                {"type": "string"},
                                {
                                    "type": "object",
                                    "properties": {
                                        "plan": {"type": "string"},
                                        "sources": {"type": "array", "items": {"type": "string"}},
                                    },
                                },
                            ],
                        },
                    },
                },
                "preserve": {
                    "type": "object",
                    "description": (
                        "Optional: specific elements from existing answers worth "
                        "bringing forward. Each entry has 'what' (strength to keep) "
                        "and 'source' (which answer). Can be empty when building fresh."
                    ),
                    "additionalProperties": {
                        "oneOf": [
                            {"type": "string"},
                            {
                                "type": "object",
                                "properties": {
                                    "what": {"type": "string"},
                                    "source": {"type": "string"},
                                },
                            },
                        ],
                    },
                },
            },
            "required": ["plan"],
        }

        # Create tool function with closure over mutable state
        state = checklist_state
        items = checklist_items

        # Capture orchestrator ref and agent_id for convergence tracking
        _orchestrator = orch
        _agent_id = agent_id

        # Track last failed criteria for draft_approach validation
        _last_checklist_result: dict[str, Any] = {
            "status": "none",
            "verdict": None,
            "failed_criteria": [],
            "items": [],
            "all_criteria_ids": [],
            "failing_criteria_detail": [],
            "plateaued_criteria": [],
            "checklist_explanation": "",
            "diagnostic_report_path": "",
            "diagnostic_report_artifact_paths": [],
        }

        _base_description = (
            (
                "Submit your checklist evaluation for your current subtask output. "
                'Use flat scores like {"E1": {"score": 8, "reasoning": "..."}, ...}. '
                "Each score entry needs 'score' (0-10) and 'reasoning'. "
                "Use 'report_path' to pass a markdown gap report when required."
            )
            if _is_decomposition
            else (
                "Submit your checklist evaluation. When multiple agents exist, "
                "scores must use per-agent format: "
                '{"agent1.1": {"E1": {"score": 8, "reasoning": "..."}, ...}, '
                '"agent2.1": {...}}. '
                "Each score entry needs 'score' (0-10) and 'reasoning'. "
                "Use 'report_path' to pass a markdown gap report when required."
            )
        )
        if _criteria_mode == "bootstrap_inline":
            _base_description = _base_description + (
                " ALSO emit 'proposed_criteria': a short list (<=3) of criterion "
                'objects {"text": "...", "category": "primary|standard|stretch", '
                '"anti_patterns": ["..."]} describing quality dimensions a stronger '
                "answer would satisfy that the current answers do NOT. These flow "
                "into subsequent rounds' checklist. Skip only when no genuine gap "
                "is visible — at most one round in three should skip entirely."
            )

        @tool(
            name="submit_checklist",
            description=_base_description,
            input_schema=input_schema,
        )
        async def submit_checklist_handler(args, _state=state):
            import json as _json

            agent_state = _orchestrator.agent_states.get(_agent_id)
            max_calls = getattr(_orchestrator.config, "max_checklist_calls_per_round", 1)
            checklist_first_answer = getattr(_orchestrator.config, "checklist_first_answer", False)
            redirect_message = build_round_evaluator_task_mode_redirect(_state)
            if redirect_message:
                return {
                    "content": [{"type": "text", "text": redirect_message}],
                    "isError": True,
                }
            raw_scores = args.get("scores", {})
            submitted_agent_labels = _orchestrator._extract_submitted_agent_labels(raw_scores)
            state_for_eval = _state
            using_recheck_exception = False

            # Block on first answer unless explicitly opted in — no prior answers to compare
            if not checklist_first_answer and agent_state is not None and agent_state.answer_count == 0:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "submit_checklist is not available before your first answer is submitted. "
                                "Build your initial answer, verify it, then call the `new_answer` workflow tool. "
                                "Checklist evaluation begins from round 2."
                            ),
                        },
                    ],
                    "isError": True,
                }

            # Block repeat calls after a new_answer verdict has already been issued this round
            if agent_state is not None and agent_state.checklist_calls_this_round >= max_calls:
                pending_recheck_labels = set(getattr(agent_state, "pending_checklist_recheck_labels", set()) or set())
                if not pending_recheck_labels:
                    blocked_msg = (
                        f"submit_checklist already called {agent_state.checklist_calls_this_round} time(s) "
                        f"this round (max: {max_calls}). You already have your improvement plan. "
                        "Implement your improvements, then verify the integrated result "
                        "(screenshots, file checks, confirming changes landed correctly), "
                        "then call the `new_answer` workflow tool "
                        "to submit your completed work. Do not call `submit_checklist` again."
                    )
                    return {
                        "content": [{"type": "text", "text": blocked_msg}],
                        "isError": True,
                    }

                # Injection exception: allow one post-injection recheck. Prefer delta-only labels,
                # but allow full latest context labels for model robustness.
                using_recheck_exception = True
                available_labels = set(_state.get("available_agent_labels") or [])
                is_decomposition = bool(_state.get("decomposition_mode", False))
                submitted_covers_full = is_decomposition or (bool(submitted_agent_labels) and (not available_labels or available_labels.issubset(submitted_agent_labels)))
                submitted_covers_delta = is_decomposition or (bool(submitted_agent_labels) and pending_recheck_labels.issubset(submitted_agent_labels))
                if submitted_covers_delta and not submitted_covers_full and not is_decomposition:
                    state_for_eval = dict(_state)
                    state_for_eval["available_agent_labels"] = sorted(pending_recheck_labels)

            result = evaluate_checklist_submission(
                scores=raw_scores,
                report_path=args.get("report_path", ""),
                items=items,
                state=state_for_eval,
                checklist_history=agent_state.checklist_history if agent_state else None,
            )
            result_status = str(
                result.get("status", "accepted" if result.get("verdict") else "validation_error"),
            )
            report_data = result.get("report") if isinstance(result.get("report"), dict) else {}
            resolved_path = str(report_data.get("resolved_path") or "")
            fallback_path = str(report_data.get("path") or "")
            _last_checklist_result["status"] = result_status
            _last_checklist_result["verdict"] = result.get("verdict")
            _last_checklist_result["failed_criteria"] = result.get("failed_criteria", [])
            _last_checklist_result["items"] = list(items)
            _last_checklist_result["all_criteria_ids"] = [f"E{i+1}" for i in range(len(items))]
            _last_checklist_result["failing_criteria_detail"] = list(result.get("failing_criteria_detail", []))
            _last_checklist_result["plateaued_criteria"] = list(result.get("plateaued_criteria", []))
            _last_checklist_result["checklist_explanation"] = str(result.get("explanation", ""))
            _last_checklist_result["diagnostic_report_path"] = resolved_path or fallback_path
            _last_checklist_result["diagnostic_report_artifact_paths"] = list(report_data.get("artifact_paths", []))
            # Retain per-agent per-criterion scores for discriminative-power pruning
            # (Pillar 4). Only present when the submission used per-agent scoring.
            _per_agent = result.get("per_agent_scores")
            if isinstance(_per_agent, dict) and _per_agent:
                _orchestrator._last_per_agent_criterion_scores = _per_agent

            # Reflexion gradient (Pillar 5): when the agent will iterate, thread the
            # per-criterion reasoning from this submission into the next round's prompt
            # so the textual "why it failed / how to fix" gradient isn't lost to scores.
            try:
                if result.get("verdict") == _state.get("iterate_action", "new_answer"):
                    from massgen.mcp_tools.checklist_tools_server import (
                        extract_criterion_feedback,
                        format_criterion_feedback_memo,
                    )

                    _memo = format_criterion_feedback_memo(
                        extract_criterion_feedback(raw_scores),
                        failed_ids=result.get("failed_criteria"),
                    )
                    if _memo:
                        _orchestrator._queue_round_start_context_block(_agent_id, _memo)
            except Exception as _memo_err:  # never let feedback threading break the verdict
                logger.debug("[Orchestrator] criterion feedback memo skipped: %s", _memo_err)

            # Only accepted checklist submissions should consume this round's quota.
            # Validation failures (incomplete/malformed payloads or gated rejections)
            # must allow the agent to resubmit within the same round.
            submission_has_validation_error = bool(
                (result_status != "accepted") or result.get("error") or result.get("incomplete_scores") or result.get("report_gate_triggered"),
            )

            # Store accepted checklist results for convergence detection and increment call counter.
            if agent_state is not None and not submission_has_validation_error:
                agent_state.checklist_history.append(
                    {
                        "verdict": result.get("verdict"),
                        "true_count": result.get("true_count"),
                        "total_score": sum(d["score"] for d in result.get("items", [])),
                        "items_detail": result.get("items", []),
                    },
                )
                agent_state.checklist_calls_this_round += 1
                # Bootstrap criteria (Variant A): capture proposed_criteria emitted with this
                # checklist submission. They do not affect the current verdict; they accumulate
                # for merge into subsequent rounds' effective criteria.
                _proposed = args.get("proposed_criteria")
                if isinstance(_proposed, list) and _proposed:
                    _per_agent_cap = int(
                        getattr(
                            getattr(_orchestrator.config, "coordination_config", None),
                            "bootstrap_max_per_agent_per_round",
                            3,
                        ),
                    )
                    _agent_round_proposals = list(agent_state.criteria_proposals)
                    for _entry in _proposed:
                        if not isinstance(_entry, dict):
                            continue
                        _text = (_entry.get("text") or "").strip()
                        if not _text:
                            continue
                        _agent_round_proposals.append(
                            {
                                "text": _text,
                                "category": str(_entry.get("category", "standard")).lower(),
                                "anti_patterns": list(_entry.get("anti_patterns") or []) or None,
                            },
                        )
                    if _per_agent_cap > 0 and len(_agent_round_proposals) > _per_agent_cap:
                        _agent_round_proposals = _agent_round_proposals[-_per_agent_cap:]
                    agent_state.criteria_proposals = _agent_round_proposals
                if getattr(agent_state, "pending_checklist_recheck_labels", set()) and (
                    bool(_state.get("decomposition_mode", False)) or (submitted_agent_labels and getattr(agent_state, "pending_checklist_recheck_labels", set()).issubset(submitted_agent_labels))
                ):
                    setattr(agent_state, "pending_checklist_recheck_labels", set())
                elif using_recheck_exception and getattr(agent_state, "pending_checklist_recheck_labels", set()):
                    setattr(agent_state, "pending_checklist_recheck_labels", set())

            # When verdict is new_answer, append explicit next-step guidance so the agent
            # implements improvements and submits via the workflow tool rather than looping
            # back to submit_checklist.
            iterate_action = _state.get("iterate_action", "new_answer")
            if result_status == "accepted" and result.get("verdict") == iterate_action:
                result = dict(result)
                result["explanation"] = (
                    result.get("explanation", "") + " NEXT: Call `draft_approach` with specific improvements for each " "failing criterion. Then implement your plan and call `new_answer`."
                )

            return {
                "content": [
                    {
                        "type": "text",
                        "text": _json.dumps(result),
                    },
                ],
            }

        @tool(
            name="draft_approach",
            description=(
                "Propose what to build for your next answer. "
                "Must be called after submit_checklist returns an iterate verdict. "
                "Pass 'plan' mapping criterion IDs to lists of entries "
                "with 'plan' (what to do) and 'sources' (which answers to draw "
                "from, or 'fresh' for new ideas). Optionally pass 'preserve' for "
                "elements worth keeping from existing answers."
            ),
            input_schema=propose_schema,
        )
        async def draft_approach_handler(args, _state=state):
            import json as _json

            redirect_message = build_round_evaluator_task_mode_redirect(_state)
            if redirect_message:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": _json.dumps({"valid": False, "error": redirect_message}),
                        },
                    ],
                }
            iterate_action = _state.get("iterate_action", "new_answer")
            last_status = str(_last_checklist_result.get("status", "none"))
            last_verdict = _last_checklist_result.get("verdict")
            agent_state = _orchestrator.agent_states.get(_agent_id)
            if last_status != "accepted":
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": _json.dumps(
                                {
                                    "valid": False,
                                    "error": ("draft_approach is unavailable because your latest " "submit_checklist result was a validation error. " "Fix and resubmit submit_checklist first."),
                                },
                            ),
                        },
                    ],
                }
            if last_verdict != iterate_action:
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": _json.dumps(
                                {
                                    "valid": False,
                                    "error": ("draft_approach is only available after " f"submit_checklist returns an iterate verdict ({iterate_action})."),
                                },
                            ),
                        },
                    ],
                }
            pending_recheck_labels = set(getattr(agent_state, "pending_checklist_recheck_labels", set()) or set())
            if pending_recheck_labels:
                pending_labels_text = ", ".join(sorted(pending_recheck_labels))
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": _json.dumps(
                                {
                                    "valid": False,
                                    "error": (
                                        "draft_approach is unavailable because newer injected answer labels "
                                        f"still require checklist re-evaluation: {pending_labels_text}. "
                                        "Re-run submit_checklist on the newest labels first."
                                    ),
                                },
                            ),
                        },
                    ],
                }

            # Accept both "plan" (new) and "improvements" (legacy fallback)
            improvements = args.get("plan") or args.get("improvements", {})
            preserve = args.get("preserve")
            vision = args.get("vision")
            result = evaluate_draft_approach(
                improvements=improvements,
                failed_criteria=_last_checklist_result["failed_criteria"],
                items=_last_checklist_result["items"] or list(items),
                all_criteria_ids=_last_checklist_result.get("all_criteria_ids"),
                preserve=preserve,
                state=_state,
                latest_evaluation={
                    "failed_criteria": _last_checklist_result.get("failed_criteria", []),
                    "failing_criteria_detail": _last_checklist_result.get("failing_criteria_detail", []),
                    "plateaued_criteria": _last_checklist_result.get("plateaued_criteria", []),
                    "checklist_explanation": _last_checklist_result.get("checklist_explanation", ""),
                    "diagnostic_report_path": _last_checklist_result.get("diagnostic_report_path", ""),
                    "diagnostic_report_artifact_paths": _last_checklist_result.get("diagnostic_report_artifact_paths", []),
                },
                vision=vision,
            )
            if result.get("valid"):
                _orchestrator._write_planning_injection(_agent_id, result["task_plan"])
                result = dict(result)  # Don't mutate original
                task_count = len(result["task_plan"])
                result["message"] = (
                    f"Your task plan has been pre-populated with {task_count} items. "
                    "Call get_task_plan to see the list and start executing. "
                    "Preserve items are guardrails — verify after implementing. "
                    "Do not skip criteria."
                )
                # Append subagent delegation hint if subagents are enabled
                _subagents_enabled = (
                    hasattr(_orchestrator.config, "coordination_config")
                    and hasattr(_orchestrator.config.coordination_config, "enable_subagents")
                    and _orchestrator.config.coordination_config.enable_subagents
                )
                if _subagents_enabled:
                    result["message"] += (
                        " Review the pre-populated plan for subagent delegation"
                        " opportunities. Tasks without mutual dependencies can be"
                        " spawned as parallel background subagents. Mark tasks"
                        " with execution.mode='delegate' plus subagent_type/subagent_id,"
                        " then spawn."
                    )
            return {
                "content": [
                    {
                        "type": "text",
                        "text": _json.dumps(result),
                    },
                ],
            }

        # --- set_evaluator_personas tool (opt-in via enable_evaluator_personas) ---
        _coord_cfg = getattr(orch.config, "coordination_config", None)
        _personas_enabled = bool(
            _coord_cfg and getattr(_coord_cfg, "enable_evaluator_personas", False),
        )

        _personas_tool = None
        if _personas_enabled:
            set_personas_schema = {
                "type": "object",
                "properties": {
                    "personas": {
                        "type": "array",
                        "description": ("List of evaluator personas. Each persona configures " "one evaluator subagent's critique focus for the next round. " "Count must match evaluator team size."),
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {
                                    "type": "string",
                                    "description": "Short descriptive name for this evaluator persona.",
                                },
                                "instructions": {
                                    "type": "string",
                                    "description": "System prompt instructions shaping this evaluator's critique lens.",
                                },
                            },
                            "required": ["label", "instructions"],
                        },
                    },
                },
                "required": ["personas"],
            }

            @tool(
                name="set_evaluator_personas",
                description=(
                    "Configure distinct evaluation lenses for round evaluator subagents. "
                    "Call before new_answer to shape how evaluators critique your next submission. "
                    "Each persona defines a unique focus area for one evaluator."
                ),
                input_schema=set_personas_schema,
            )
            async def _set_evaluator_personas_impl(args):
                import json as _json

                personas = args.get("personas", [])
                error = _orchestrator._validate_evaluator_personas(personas)
                if error:
                    return {
                        "content": [
                            {"type": "text", "text": _json.dumps({"error": error})},
                        ],
                        "isError": True,
                    }
                _orchestrator._pending_evaluator_personas = [{"label": str(p["label"]).strip(), "instructions": str(p["instructions"]).strip()} for p in personas]
                labels = [p["label"] for p in _orchestrator._pending_evaluator_personas]
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": _json.dumps(
                                {
                                    "status": "accepted",
                                    "message": f"Evaluator personas set: {', '.join(labels)}. " "These will be applied to the next round evaluator run.",
                                },
                            ),
                        },
                    ],
                }

            _personas_tool = _set_evaluator_personas_impl

        # Create SDK MCP server with checklist tools
        _checklist_tools = [submit_checklist_handler, draft_approach_handler]
        if _personas_tool is not None:
            _checklist_tools.append(_personas_tool)
        sdk_server = create_sdk_mcp_server(
            name="massgen_checklist",
            version="1.0.0",
            tools=_checklist_tools,
        )

        # Inject into backend's MCP servers
        if not hasattr(backend, "config") or not isinstance(backend.config, dict):
            logger.warning(
                f"Agent {agent_id} backend has no dict config, skipping checklist tool",
            )
            return

        if "mcp_servers" not in backend.config:
            backend.config["mcp_servers"] = {}

        if isinstance(backend.config["mcp_servers"], dict):
            backend.config["mcp_servers"]["massgen_checklist"] = sdk_server
        elif isinstance(backend.config["mcp_servers"], list):
            backend.config["mcp_servers"].append(
                {
                    "name": "massgen_checklist",
                    "__sdk_server__": sdk_server,
                },
            )

        logger.info(
            f"[Orchestrator] Registered submit_checklist SDK MCP tool for agent {agent_id}",
        )

    def init_checklist_tool_stdio(self, agent_id, backend, checklist_state, items):
        """Write checklist specs and add stdio MCP for standard MCP backends."""
        from massgen.mcp_tools.checklist_tools_server import (
            build_server_config as build_checklist_config,
        )
        from massgen.mcp_tools.checklist_tools_server import (
            write_checklist_specs,
        )

        # Write specs to a temp directory (persists for session lifetime)
        specs_dir = Path(tempfile.mkdtemp(prefix=f"massgen_checklist_{agent_id}_"))
        specs_path = specs_dir / "checklist_specs.json"
        write_checklist_specs(items=items, state=checklist_state, output_path=specs_path)

        # Store path so we can re-write on state refresh
        backend._checklist_specs_path = specs_path

        # Add stdio MCP server config (replacing any existing checklist entry)
        checklist_mcp = build_checklist_config(specs_path)
        backend.mcp_servers = [s for s in backend.mcp_servers if not (isinstance(s, dict) and s.get("name") == "massgen_checklist")]
        backend.mcp_servers.append(checklist_mcp)

        logger.info(
            f"[Orchestrator] Registered submit_checklist stdio MCP for agent {agent_id} " f"(specs: {specs_path})",
        )

    # ------------------------------------------------------------------
    # Convergence + state sync
    # ------------------------------------------------------------------

    def detect_convergence(self, agent_id: str) -> tuple:
        """Detect whether an agent is converging (total score plateaued).

        Returns:
            Tuple of (is_converging: bool, consecutive_count: int).
            is_converging is True when 2+ consecutive checklist results show
            no meaningful score improvement (<=1 point gain).
        """
        orch = self._orchestrator
        self.sync_stdio_checklist_state_from_specs(agent_id)
        state = orch.agent_states.get(agent_id)
        if state is None:
            return False, 0
        history = state.checklist_history
        consecutive = 0
        for i in range(len(history) - 1, 0, -1):
            curr = history[i].get("total_score", 0)
            prev = history[i - 1].get("total_score", 0)
            if curr <= prev + 1:
                consecutive += 1
            else:
                break
        return consecutive >= 2, consecutive

    def sync_stdio_checklist_state_from_specs(self, agent_id: str) -> None:
        """Sync accepted stdio checklist progress back into AgentState.

        SDK-backed checklist calls mutate AgentState directly in-process. Stdio
        checklist calls persist their runtime state into the specs JSON, so the
        orchestrator needs to pull that state back in before using helper gates
        like `_has_successful_checklist_submit_this_round`.
        """
        orch = self._orchestrator
        agent = orch.agents.get(agent_id)
        agent_state = orch.agent_states.get(agent_id)
        if not agent or not agent_state:
            return
        if bool(getattr(agent.backend, "supports_sdk_mcp", False)):
            return

        specs_path = getattr(agent.backend, "_checklist_specs_path", None)
        if not specs_path:
            return

        try:
            with open(specs_path, encoding="utf-8") as f:
                specs_payload = json.load(f)
        except Exception:
            return

        persisted_state = specs_payload.get("state") or {}

        persisted_calls = persisted_state.get("checklist_calls_this_round")
        if isinstance(persisted_calls, (int, float)):
            agent_state.checklist_calls_this_round = max(
                agent_state.checklist_calls_this_round,
                int(persisted_calls),
            )

        persisted_history = persisted_state.get("checklist_history")
        if isinstance(persisted_history, list) and len(persisted_history) >= len(agent_state.checklist_history):
            agent_state.checklist_history = list(persisted_history)

        raw_pending = persisted_state.get("pending_checklist_recheck_labels")
        normalized_pending: set[str] = set()
        if isinstance(raw_pending, str):
            label = raw_pending.strip()
            if label:
                normalized_pending.add(label)
        elif isinstance(raw_pending, (list, tuple, set)):
            normalized_pending = {str(label).strip() for label in raw_pending if str(label).strip()}
        agent_state.pending_checklist_recheck_labels = normalized_pending

        # Sync evaluator personas from stdio specs into orchestrator state.
        raw_personas = persisted_state.get("pending_evaluator_personas")
        if isinstance(raw_personas, list) and raw_personas:
            orch._pending_evaluator_personas = raw_personas

    def refresh_checklist_state_for_agent(
        self,
        agent_id: str,
        prefer_local_runtime_state: bool = False,
    ) -> None:
        """Refresh the checklist tool's mutable state dict for an agent.

        Called after mid-stream injection so the submit_checklist tool sees
        up-to-date budget (remaining slots may change when decomposition
        streak is reset) and has_existing_answers.
        """
        orch = self._orchestrator
        agent = orch.agents.get(agent_id)
        if not agent or not hasattr(agent.backend, "_checklist_state"):
            return

        if not prefer_local_runtime_state:
            self.sync_stdio_checklist_state_from_specs(agent_id)

        from massgen.system_prompt_sections import ChecklistGate

        _cl_remaining = max(
            0,
            (orch.config.max_new_answers_per_agent or 5) - orch._get_agent_answer_count_for_limit(agent_id),
        )
        _has_answers = bool(
            orch.coordination_tracker.answers_by_agent.get(agent_id),
        )
        state = agent.backend._checklist_state
        agent_state = orch.agent_states.get(agent_id)
        criteria_agent_id = agent_id if orch._is_decomposition_mode() else None
        active_items, active_categories, active_verify_by, criteria_source, _anti, _score_anchors = self.resolve_effective_checklist_criteria(
            criteria_agent_id,
        )
        current_items = getattr(agent.backend, "_checklist_items", None)
        if isinstance(current_items, list):
            current_items[:] = list(active_items)
        else:
            agent.backend._checklist_items = list(active_items)
        gate = ChecklistGate.from_budget(
            state.get("threshold", 5),
            _cl_remaining,
            state.get("total", 5),
            num_items=len(getattr(agent.backend, "_checklist_items", [])) or 4,
        )
        pending_recheck_labels: list[str] = []
        if bool(getattr(agent.backend, "supports_sdk_mcp", False)):
            sdk_pending = getattr(orch.agent_states.get(agent_id), "pending_checklist_recheck_labels", set()) or set()
            pending_recheck_labels = sorted(
                {str(label).strip() for label in sdk_pending if str(label).strip()},
            )
        else:
            raw_pending: Any = None
            specs_path = getattr(agent.backend, "_checklist_specs_path", None)
            if specs_path:
                try:
                    with open(specs_path, encoding="utf-8") as f:
                        specs_payload = json.load(f)
                    raw_pending = (specs_payload.get("state") or {}).get("pending_checklist_recheck_labels")
                except Exception:
                    raw_pending = None
            if raw_pending is None:
                raw_pending = state.get("pending_checklist_recheck_labels", [])
            if isinstance(raw_pending, str):
                pending_recheck_labels = [raw_pending.strip()] if raw_pending.strip() else []
            elif isinstance(raw_pending, (list, tuple, set)):
                pending_recheck_labels = sorted(
                    {str(label).strip() for label in raw_pending if str(label).strip()},
                )
        agent.backend._checklist_state.update(
            {
                "remaining": _cl_remaining,
                "has_existing_answers": _has_answers,
                "agent_answer_count": len(orch.coordination_tracker.answers_by_agent.get(agent_id, [])),
                "current_answer_label": orch.coordination_tracker.get_latest_answer_label(agent_id),
                "checklist_first_answer": bool(
                    getattr(orch.config, "checklist_first_answer", False),
                ),
                "max_checklist_calls_per_round": int(
                    getattr(orch.config, "max_checklist_calls_per_round", 1) or 1,
                ),
                "checklist_calls_this_round": (agent_state.checklist_calls_this_round if agent_state is not None else 0),
                "checklist_history": (list(agent_state.checklist_history) if agent_state is not None else []),
                "decomposition_mode": orch._is_decomposition_mode(),
                "required": gate.required_true,
                "cutoff": gate.confidence_cutoff,
                "require_gap_report": bool(
                    getattr(orch.config, "checklist_require_gap_report", True),
                ),
                "require_diagnostic_report": bool(
                    getattr(orch.config, "checklist_require_gap_report", True),
                ),
                "changedoc_mode": orch._is_changedoc_enabled(),
                "workspace_path": getattr(
                    getattr(agent.backend, "filesystem_manager", None),
                    "cwd",
                    None,
                ),
                "item_categories": active_categories,
                "item_verify_by": active_verify_by or {},
                "criteria_source": criteria_source,
                # Preserve novelty gating from initial state (config-driven, doesn't change)
                "novelty_subagent_enabled": state.get("novelty_subagent_enabled", False),
                # Preserve critic gating from initial state
                "critic_subagent_enabled": state.get("critic_subagent_enabled", False),
                # Preserve builder gating from initial state
                "builder_subagent_enabled": state.get("builder_subagent_enabled", False),
                # Preserve regression_guard gating from initial state
                "regression_guard_subagent_enabled": state.get("regression_guard_subagent_enabled", False),
                # Preserve quality_rethinking gating from initial state
                "quality_rethinking_subagent_enabled": state.get("quality_rethinking_subagent_enabled", False),
                # Preserve quality-rethinking auto-injection toggle from initial state
                "enable_quality_rethink_on_iteration": state.get("enable_quality_rethink_on_iteration", False),
                # Preserve novelty auto-injection toggle from initial state
                "enable_novelty_on_iteration": state.get("enable_novelty_on_iteration", False),
                # Update available agent labels so checklist enforces complete coverage.
                # Includes labels injected mid-stream (updated by update_agent_context_with_new_answers).
                "available_agent_labels": list(
                    orch.coordination_tracker.get_agent_context_labels(agent_id),
                ),
                "pending_checklist_recheck_labels": pending_recheck_labels,
                "round_evaluator_auto_injected": state.get("round_evaluator_auto_injected", False),
                "round_evaluator_primary_artifact_path": state.get("round_evaluator_primary_artifact_path", ""),
                "round_evaluator_verdict_artifact_path": state.get("round_evaluator_verdict_artifact_path", ""),
                "round_evaluator_next_tasks_artifact_path": state.get("round_evaluator_next_tasks_artifact_path", ""),
                "allowed_external_report_paths": list(state.get("allowed_external_report_paths", []) or []),
            },
        )
        # Re-write specs file for stdio backends so the MCP server sees updated state
        if hasattr(agent.backend, "_checklist_specs_path"):
            from massgen.mcp_tools.checklist_tools_server import write_checklist_specs

            write_checklist_specs(
                items=agent.backend._checklist_items,
                state=agent.backend._checklist_state,
                output_path=agent.backend._checklist_specs_path,
            )

        logger.debug(
            "[Orchestrator] Refreshed checklist state for %s: remaining=%d, has_answers=%s",
            agent_id,
            _cl_remaining,
            _has_answers,
        )

    def set_round_evaluator_task_mode(
        self,
        agent_id: str,
        *,
        enabled: bool,
        primary_artifact_path: str = "",
        verdict_artifact_path: str = "",
        next_tasks_artifact_path: str = "",
        objective: str = "",
        primary_strategy: str = "",
        why_this_strategy: str = "",
        strategy_mode: str = "",
        incremental_override_reason: str = "",
        success_contract: dict[str, Any] | None = None,
        deprioritize_or_remove: list[str] | None = None,
    ) -> None:
        """Persist whether an agent is in post-evaluator task mode."""
        orch = self._orchestrator
        agent = orch.agents.get(agent_id)
        if not agent or not hasattr(agent.backend, "_checklist_state"):
            return

        state = agent.backend._checklist_state
        state["round_evaluator_auto_injected"] = bool(enabled)
        state["round_evaluator_primary_artifact_path"] = primary_artifact_path or ""
        state["round_evaluator_verdict_artifact_path"] = verdict_artifact_path or ""
        state["round_evaluator_next_tasks_artifact_path"] = next_tasks_artifact_path or ""
        state["round_evaluator_objective"] = objective or ""
        state["round_evaluator_primary_strategy"] = primary_strategy or ""
        state["round_evaluator_why_this_strategy"] = why_this_strategy or ""
        state["round_evaluator_strategy_mode"] = strategy_mode or ""
        state["round_evaluator_incremental_override_reason"] = incremental_override_reason or ""
        state["round_evaluator_success_contract"] = copy.deepcopy(success_contract) if isinstance(success_contract, dict) else {}
        state["round_evaluator_deprioritize_or_remove"] = list(deprioritize_or_remove or [])
        state["allowed_external_report_paths"] = [primary_artifact_path] if primary_artifact_path else []

        if hasattr(agent.backend, "_checklist_specs_path"):
            from massgen.mcp_tools.checklist_tools_server import write_checklist_specs

            write_checklist_specs(
                items=getattr(agent.backend, "_checklist_items", []),
                state=state,
                output_path=agent.backend._checklist_specs_path,
            )
