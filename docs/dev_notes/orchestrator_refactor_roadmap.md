# Orchestrator God-Class Refactor — Collaborator Extraction Roadmap

**Target:** `massgen/orchestrator.py` (21,599 lines, 297 methods, single `Orchestrator` class)
**Style:** Extract collaborators into sibling package `massgen/orchestrator_collaborators/` (NOT a package conversion of orchestrator.py).
**Safety net:** `massgen/tests/test_orchestrator_characterization.py` (35 tests, green on HEAD).

## Hard constraints (learned from first attempt)

1. `massgen/orchestrator.py` MUST stay a single module file — it uses `Path(__file__).parent/'skills'`; converting to a package breaks skill resolution.
2. Public contract importable from `massgen.orchestrator`: `Orchestrator`, `AgentState`, `WORKFLOW_TOOL_NAMES`, `create_orchestrator`. Do NOT add `MassOrchestrator` (lives in `massgen/v1/orchestrator.py`).
3. `SkillsConfigValidator` trap: re-anchor skills path to the `massgen` package root, not the collaborator module's `__file__`.
4. Keep original methods as thin delegators so all call sites keep working.

## Ordered steps (lowest-risk first)

| # | Collaborator | Risk | #Methods | Methods |
|--:|---|---|--:|---|
| 0 | (package conversion — no methods moved) | low | 0 | — |
| 1 | SkillsConfigValidator | low | 1 | _validate_skills_config |
| 2 | NlipRoutingInitializer | low | 1 | _init_nlip_routing |
| 3 | RunModeStrategyResolver | low | 5 | _is_round_learning_capture_enabled, _get_final_answer_strategy, _expects_final_presentation_stage, _should_skip_vote_rounds_for_synthesize, _is_round_verification_capture_enabled |
| 4 | ContextPathWriteTracker | low | 5 | _has_write_context_paths, _enable_context_write_access, get_context_path_writes, get_context_path_writes_categorized, _clear_context_path_write_tracking |
| 5 | RoundEvaluatorGateConfig | low | 7 | _is_round_evaluator_gate_enabled, _get_evaluator_team_size, _validate_evaluator_personas, _consume_evaluator_personas, _get_round_evaluator_latest_labels, _get_round_evaluator_upcoming_round, _get_round_evaluator_display_round |
| 6 | RoundStartContextQueue (folded into RuntimeInputDelivery later) | low | 2 | _queue_round_start_context_block, _consume_round_start_context_block |
| 7 | DspyParaphraseCoordinator | low | 2 | _prepare_paraphrases_for_agents, get_paraphrase_status |
| 8 | AnswerTextNormalizer | low | 5 | _coerce_answer_content_to_text, _normalize_workspace_paths_in_answers, _normalize_workspace_paths_for_comparison, _calculate_jaccard_similarity, _check_answer_novelty |
| 9 | OrchestratorTimeoutCalculator | low | 2 | _should_skip_injection_due_to_timeout, get_agent_timeout_state |
| 10 | FinalResultReporter | medium | 9 | _resolve_final_workspace_path, _get_vote_results, _determine_final_agent_from_states, get_final_result, get_partial_result, _ensure_final_directory_on_shutdown, get_all_agent_workspaces, get_coordination_result, get_status |
| 11 | WorkspaceModalPresenter | low | 1 | _show_workspace_modal_if_needed |
| 12 | WorkspaceLifecycleManager | medium | 3 | _clear_agent_workspaces, _archive_agent_memories, _namespace_verification_memory_files |
| 13 | BootstrapCriteriaEngine | medium | 5 | _drain_pending_criteria_proposals, _maybe_run_bootstrap_discriminator, _run_bootstrap_discriminator_step, _drain_at_session_end, _persist_bootstrap_accumulator |
| 14 | BroadcastToolInitializer | medium | 2 | _init_broadcast_tools, _register_broadcast_custom_tools |
| 15 | CheckpointCoordinator | medium | 7 | _init_checkpoint_tool, _strip_standalone_checkpoint_from_all_agents, _init_standalone_checkpoint_tool, set_main_agent, is_checkpoint_mode, _is_agent_active_in_current_mode, _activate_checkpoint |
| 16 | PlanningToolInjector | medium | 5 | _inject_planning_tools_for_all_agents, _planning_server_name, _inject_planning_tools_for_agent, _create_planning_mcp_config, _write_planning_injection |
| 17 | ActiveCoordinationCleanup | medium | 1 | _cleanup_active_coordination |
| 18 | IsolatedChangeReviewer | medium | 1 | _review_isolated_changes |
| 19 | FairnessGate | medium | 7 | _is_fairness_enabled, _update_fairness_pause_log_state, _log_fairness_answer_lead_block, _clear_fairness_answer_lead_block_log, _get_active_fairness_agents, _check_fairness_answer_lead_cap, _should_pause_agent_for_fairness |
| 20 | SubagentLifecycleCoordinator | medium | 23 | _on_subagent_complete, _on_background_subagent_complete, _schedule_background_wait_interrupt_for_agent, _get_pending_subagent_results_async, _collect_pending_subagent_results_async, _cancel_running_subagents_for_agent, _cancel_running_background_work_for_agent, _get_pending_subagent_results, _try_parse_json_dict_from_text, _extract_text_from_mcp_content_payload, _normalize_subagent_mcp_result, _call_subagent_mcp_tool_async, _is_reconnectable_background_mcp_error, _call_subagent_mcp_tool, _has_subagent_mcp_for_agent, _direct_spawn_subagents, _send_runtime_message_via_direct_inbox_write, _resolve_subagent_parent_workspace, send_runtime_message_to_subagent, continue_subagent_from_tui, _build_tui_continue_status_callback, _share_subagent_message_callback_with_display, _flush_pending_subagent_results |
| 21 | RuntimeInputDelivery | medium | 14 | _build_runtime_user_instructions_context, _insert_runtime_user_instructions_after_original_message, _insert_runtime_context_blocks_after_original_message, _ensure_runtime_human_input_hook_initialized, _ensure_runtime_inbox_poller_initialized, _poll_runtime_inbox, _configure_human_input_hook_callbacks, _maybe_interrupt_background_wait_for_agent, _share_human_input_hook_with_display, request_answer_now, _consume_pending_answer_now_injection, _prime_answer_now_hook_payload, _queue_round_start_context_block, _consume_round_start_context_block |
| 22 | PeerAnswerVisibilityTracker | high | 13 | _get_agent_answer_revision_count, _get_answer_revision_counts, _get_current_answers_snapshot, _sync_decomposition_answer_visibility, _mark_seen_answer_revisions, _get_latest_answer_revision_timestamp, _get_unseen_answer_update_candidates, _get_unseen_source_agent_ids, _has_unseen_answer_updates, _select_midstream_answer_updates, _extract_submitted_agent_labels, _mark_pending_checklist_recheck_labels, _register_injected_answer_updates |
| 23 | ChecklistGateManager | high | 11 | _get_decomposition_criteria_for_agent, _get_active_criteria, _resolve_effective_checklist_criteria, _push_cached_criteria_to_display, _init_checklist_tool, _init_checklist_tool_sdk, _init_checklist_tool_stdio, _detect_convergence, _sync_stdio_checklist_state_from_specs, _refresh_checklist_state_for_agent, _set_round_evaluator_task_mode |
| 24 | AnswerLimitGate | high | 9 | _terminal_action_wording, _is_hard_timeout_active, _get_agent_answer_count_for_limit, _get_total_answer_count, _is_global_answer_limit_reached, _check_answer_count_limit, _is_vote_only_mode, _apply_decomposition_auto_stop_if_needed, _is_waiting_for_all_answers |
| 25 | SubagentToolInjector | high | 8 | _subagent_server_name, _inject_subagent_tools_for_all_agents, _inject_subagent_tools_for_agent, setup_subagent_spawn_callbacks, _setup_subagent_spawn_callback, _write_subagent_type_dirs, _build_parent_coordination_config_for_subagents, _create_subagent_mcp_config |
| 26 | PostEvaluationRunner | high | 2 | post_evaluate_answer, handle_restart |
| 27 | AgentOrchestrationSetup | high | 2 | __init__ per-agent setup block + _setup_agent_orchestration nested fn (595-797), ensure_workspace_symlinks |
| 28 | FinalPresentationRunner | high | 5 | _yield_existing_answer_finalization, _present_final_answer, _determine_final_agent_from_votes, get_final_presentation, _handle_orchestrator_timeout |
| 29 | MidStreamInjectionHookInstaller | high | 18 | _close_agent_stream, _check_restart_pending, _should_defer_restart_for_first_answer, _clear_framework_mcp_state, _compute_plan_progress_stats, _build_tool_result_injection, _build_essential_files_for_injection, _setup_hook_manager_for_agent, _setup_codex_mcp_hooks, _setup_codex_hybrid_hooks, _collect_round_timeout_runtime_sections, _flush_codex_hook_payloads, _backend_supports_midstream_hook_injection, _poll_no_hook_background_tool_updates, _collect_no_hook_runtime_fallback_sections, _prepare_no_hook_midstream_enforcement, _register_round_timeout_hooks, _setup_native_hooks_for_agent |

## Do-not-extract notes

- `CoordinationModePredicates` — shared read-only config view; keep as-is, do not class-ify.
- `MiscPublicApiAndLifecycle` — not a real cluster; leave on Orchestrator.

## Status

- [x] Steps 1-4 (SkillsConfigValidator, NlipRoutingInitializer, RunModeStrategyResolver, ContextPathWriteTracker) — **DONE & verified green**. orchestrator.py 21,599 → 21,394.
- [x] Steps 5-9 (RoundEvaluatorGateConfig, RoundStartContextQueue, DspyParaphraseCoordinator, AnswerTextNormalizer, OrchestratorTimeoutCalculator) — **DONE & verified green**. orchestrator.py → 21,001 (−598 cumulative). Two regressions caught & fixed: (a) `__new__`-bypass test broke because collaborators were eager `__init__` attrs → converted all 9 to lazy `functools.cached_property` accessors; (b) `test_evaluator_personas.py` mocked stub bypassed delegators → wired a real `RoundEvaluatorGateConfig(stub)` into the test fixture. Both fixes covered by new regression tests in characterization suite.
- [x] Steps 10-14 (WorkspaceModalPresenter, FinalResultReporter, WorkspaceLifecycleManager, BroadcastToolInitializer, BootstrapCriteriaEngine) — **DONE & verified green**. orchestrator.py → 19,762 (−1,837 cumulative). Two regressions caught & fixed: (a) `test_orchestrator_unit.py` patched `massgen.orchestrator.get_log_session_dir` but `FinalResultReporter` imports it from `massgen.logger_config` directly → updated 3 patch targets to `massgen.orchestrator_collaborators.final_result_reporter.get_log_session_dir`; (b) `test_essential_files_manifest.py` used the same `MagicMock`-stub pattern as evaluator_personas → wired real `WorkspaceLifecycleManager(stub)` into the fixture.
- [x] Steps 15-19 (IsolatedChangeReviewer, ActiveCoordinationCleanup, CheckpointCoordinator, FairnessGate, PlanningToolInjector) — **DONE & verified green**. orchestrator.py → 18,699 (−2,900 cumulative; 20 collaborator modules). No tracked-test regressions this batch (PlanningToolInjector preemptively uses a lazy `massgen.orchestrator.get_log_session_dir` lookup so existing patch targets keep working). Also deleted dead no-op shim `_cleanup_background_shells_for_agent` and its sole caller.
- [x] Steps 20-21 (RuntimeInputDelivery-12 methods, SubagentLifecycleCoordinator-23 methods) — **DONE & verified green**. orchestrator.py → 17,462 (−4,137 cumulative = 19% reduction; 22 collaborator modules). 5 monkeypatch-bypass regressions caught & fixed: tests patching `orchestrator._<method>` whose call site moved into a collaborator (`self.<method>` inside the collaborator bypasses the patched delegator). Fix: repoint patches to `orchestrator._subagent_lifecycle_coordinator.<no_underscore_name>`. Plus 1 pure-helper fix: `_insert_runtime_context_blocks_after_original_message` was called via `Orchestrator._insert_...(None, ...)` — kept the orchestrator delegator as a regular method that ignores self, and made the collaborator method `@staticmethod`.
- [x] Steps 22 (AnswerLimitGate-9 methods) + 25 (SubagentToolInjector-8 methods) — **DONE & verified green**. orchestrator.py → 16,752. Load-bearing `_is_vote_only_mode` decomposition side effect preserved byte-for-byte.
- [x] Step 26 (PostEvaluationRunner-2 methods) — **DONE & verified green**. orchestrator.py → 16,323. `handle_restart` rebuilds `coordination_tracker` + resets `agent_states` via back-ref so already-extracted collaborators see the new state.
- [x] Step 28 (FinalPresentationRunner-5 methods, 1302 lines) — **DONE & verified green**. orchestrator.py → 15,021. 1 regression fixed: inner `self.get_final_presentation(...)` bypassed test monkeypatches on `orchestrator.get_final_presentation` → repointed to `orch.get_final_presentation(...)`.
- [x] Step 23 (PeerAnswerVisibilityTracker-13 methods) — **DONE & verified green** (first batch with zero verifier issues). orchestrator.py → 14,866. Dual-writer field `pending_checklist_recheck_labels` mutated via orch back-ref so ChecklistGateManager later sees the same live set.
- [x] Step 24 (ChecklistGateManager-11 methods, 1252 lines) — **DONE & verified green** (largest single extraction; 219 tests passed across checklist/criteria/round_evaluator suites). 1 regression fixed: collaborator's `resolve_effective_checklist_criteria` called `self.get_active_criteria(...)` directly → bypassed test monkeypatches on `orchestrator._get_active_criteria` → repointed to `orch._get_active_criteria(...)`.
- [x] Step 29 (MidStreamInjectionHookInstaller — partial: 6 of 18 pure helpers extracted, 310 lines). The 12 hook-installation methods with duplicated callback closures across 3 backend paths (`_setup_hook_manager_for_agent`, `_setup_codex_mcp_hooks`, `_setup_codex_hybrid_hooks`, `_setup_native_hooks_for_agent`, `_register_round_timeout_hooks`, etc.) remain on Orchestrator — they need a callback-unification pass first (behavior-changing, out of scope for pure extraction).
- [ ] Step 27 (AgentOrchestrationSetup-2 methods) skipped: lives inline in `__init__` as a nested function + loop; "extraction" requires `__init__`-rewiring not just method-relocation — different kind of refactor.

## Release status — SHIPPED (50% milestone)

**orchestrator.py: 21,599 → 10,741 lines (−10,858, 50% reduction)** with **33 collaborator modules** in `massgen/orchestrator_collaborators/`
**textual_terminal_display.py: 14,580 → 14,287** (+ 3 sibling display modules)

Zero breaking changes verified — full tracked unit suite green except 1 pre-existing TUI snapshot failure (confirmed identical on HEAD). Ruff clean across all changed/new files. All public contracts preserved.

### Bonus extractions beyond the original 29-step plan

After completing the original plan, identified and extracted 4 more cohesive clusters discovered by re-analyzing the residual large methods:

- `TraceAnalyzerRunner` (11 methods, 459 lines) — execution-trace analysis pipeline
- `CriteriaEvolutionRunner` (7 methods, 498 lines) — round-by-round criteria evolution
- `SnapshotManager` (7 methods, 541 lines) — workspace + shared-memory snapshotting
- `RoundEvaluatorRunner` (11 methods + 1 helper, 655 lines) — round-evaluator execution
- `MetricsReporter` (3 PUBLIC methods, 410 lines) — `save_metrics`, `save_coordination_logs`, `_collect_subagent_costs`

## Follow-up release work

- **AgentOrchestrationSetup**: hoist the inline per-agent setup function out of `__init__` first (a small structural refactor), THEN extract as a collaborator.
- **MidStreamInjectionHookInstaller remaining 12 methods**: unify the duplicated `get_injection_content` closures across the 3 backend paths (behavior-changing, needs its own validation), THEN extract.
- These are not blocking — Orchestrator is now 38% smaller and the remaining bulk is the 4 hook-install paths + the streaming-loop core.

## Lessons learned (apply going forward)

- **`__new__`-bypass safety**: any new collaborator MUST be exposed via `functools.cached_property`, not eager `__init__` assignment, so tests using `Orchestrator.__new__(Orchestrator)` still work.
- **`MagicMock(spec=Orchestrator)` stub tests**: when a delegator now routes through `self._<collaborator>`, the stub returns an auto-mock collaborator → no-op. Fix by wiring a real collaborator (with back-ref to the stub) into the test fixture.
- **Monkeypatch-bypass**: tests that `monkeypatch.setattr(orch, "_<method>", fake)` only patch the orchestrator's delegator. If a sibling collaborator method calls `self.<method>` internally, the patch doesn't fire. Fix: repoint the patch to `orch._<collaborator>.<no_underscore_name>`.
- **Pure helpers called as `Cls._method(None, ...)`**: keep the orchestrator delegator as a regular method (not `@staticmethod`) that ignores `self`, so the existing 3-arg unbound call pattern keeps working. Mark the collaborator's version `@staticmethod`.
- **Patched imports**: when a collaborator imports a function the test patches at the orchestrator module path, either (a) import lazily via `from massgen import orchestrator as _orch_mod; _orch_mod.<symbol>()` so the patch is seen, or (b) update the test patch target to the new module path. PlanningToolInjector uses option (a); FinalResultReporter required option (b).
- **Suite-not-just-net**: characterization tests miss `__new__`-bypass, `MagicMock(spec=)`, and monkeypatch-bypass patterns. After each batch, run the broader tracked unit suite, not just the characterization file.
