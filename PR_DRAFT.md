# PR Draft: v0.1.92 God-Class Refactor — Collaborator Extraction

## Summary

Refactor MassGen's two largest files into modular collaborators with **zero breaking changes**, gated by characterization tests written first. Establishes a repeatable extract-collaborators pattern for the remaining cleanup work.

- **`orchestrator.py`: 21,599 → 8,574 lines (−13,025, 60% reduction)** — 49 collaborator classes extracted into a new `massgen/orchestrator_collaborators/` package. The Orchestrator class keeps thin delegator methods so every existing call site (internal and external) works unchanged.
- **`textual_terminal_display.py`: 14,580 → 14,287** — 3 sibling display modules extracted (`_textual_terminal_capabilities.py`, `_textual_provider_model.py`, `_textual_widget_debug.py`).
- **Two characterization test files** (77 tests) pin the public contract + extraction seams so the refactor is provably safe.
- **Six tracked test files** updated to repoint monkeypatch / mock-stub seams to the new collaborator locations (no test deletions or assertion weakenings).
- **`orchestrator.py` stays a single `.py` module** (not a package) — preserves `Path(__file__).parent / 'skills'` resolution.

### Collaborators extracted (49, alphabetical)

`ActiveCoordinationCleanup`, `AgentOrchestrationSetup`, `AnswerLimitGate`, `AnswerTextNormalizer`, `BootstrapCriteriaEngine`, `BroadcastToolInitializer`, `ChangedocCoordinator`, `ChatFollowupHandler`, `ChecklistGateManager`, `CheckpointCoordinator`, `ContextPathWriteTracker`, `CriteriaEvolutionRunner`, `DockerDiagnostics`, `DspyParaphraseCoordinator`, `EnforcementBufferHelper`, `EssentialFilesHelper`, `EvaluationCriteriaGeneratorCollaborator`, `EvaluatorResultExtractor`, `FairnessGate`, `FinalPresentationRunner`, `FinalResultReporter`, `IsolatedChangeReviewer`, `MetricsReporter`, `MidStreamInjectionHookInstaller` (partial — 6 of 18 pure helpers), `NlipRoutingInitializer`, `OrchestratorTimeoutCalculator`, `PeerAnswerVisibilityTracker`, `PersonaInjector`, `PlanningToolInjector`, `PostEvaluationRunner`, `PreCollabHelpers`, `PreviousLogRestorer`, `PromptImproverCollaborator`, `QuestionIrreversibilityAnalyzer`, `RateLimitController`, `RoundEvaluatorGateConfig`, `RoundEvaluatorRunner`, `RoundStartContextQueue`, `RunModeStrategyResolver`, `RuntimeInputDelivery`, `SkillsConfigValidator`, `SnapshotManager`, `StepModeHandler`, `SubagentLifecycleCoordinator`, `SubagentToolInjector`, `ToolMessageHelpers`, `TraceAnalyzerRunner`, `WorkspaceLifecycleManager`, `WorkspaceModalPresenter`.

### Public contracts preserved

- `massgen.orchestrator`: `Orchestrator`, `AgentState`, `WORKFLOW_TOOL_NAMES`, `create_orchestrator` (`MassOrchestrator` intentionally absent — lives in `massgen/v1/orchestrator.py`).
- `massgen.frontend.displays.textual_terminal_display`: `TextualApp`, `AgentPanel`, `TextualTerminalDisplay`, `ProgressIndicator`, `tui_log`, `EMOJI_FALLBACKS`, `TerminalCapabilityProbe`, `_PrecollabSubagentState`.

### Implementation patterns established

- Collaborators exposed via `functools.cached_property` (not eager `__init__` attrs) so tests using `Orchestrator.__new__(Orchestrator)` still resolve them lazily.
- Collaborators hold an orchestrator back-reference for shared mutable state; pure helpers are `@staticmethod`.
- All shared state (`_pre_populated_workspaces`, `workflow_tools`, `_bootstrap_criteria_accumulator`, `_subagent_launch_watcher`, `_planning_injection_dirs`, etc.) is mutated via the orchestrator back-ref to preserve single ownership.
- Cross-collaborator method calls route through the orchestrator delegator (e.g. `self._orchestrator._check_fairness_answer_lead_cap(...)`) so monkeypatches at the orchestrator level keep working.

### Dev-note

Full roadmap, lessons-learned, and the 6 remaining (high-risk, paused) steps are documented in `docs/dev_notes/orchestrator_refactor_roadmap.md`.

## Issues

- Linear: TBD
- GitHub: TBD

## Tests

- New characterization tests (must pass before any extraction can ship):
  - `uv run pytest massgen/tests/test_orchestrator_characterization.py -q` (37 tests)
  - `uv run pytest massgen/tests/frontend/test_textual_terminal_display_characterization.py -q` (40 cases)
- Suites that exercise extracted collaborators (regression coverage):
  - `uv run pytest massgen/tests/test_vote_only_mode.py massgen/tests/test_decomposition_mode.py -q` (load-bearing `_is_vote_only_mode` side effect)
  - `uv run pytest massgen/tests/test_orchestrator_skills_injection.py massgen/tests/test_essential_files_manifest.py massgen/tests/test_evaluator_personas.py -q` (MagicMock-stub fixtures rewired to real collaborators)
  - `uv run pytest massgen/tests/integration/test_orchestrator_hooks_broadcast_subagents.py massgen/tests/integration/test_orchestrator_restart_and_external_tools.py massgen/tests/test_auto_trace_analysis.py massgen/tests/unit/test_orchestrator_unit.py -q` (monkeypatch seams repointed to collaborator)
- Full fast non-API lane:
  - `uv run pytest massgen/tests/ -q --tb=no -ra -p no:cacheprovider -m "not live_api and not docker and not expensive and not integration" --ignore=massgen/tests/frontend/test_launch_run_card.py --ignore=massgen/tests/test_interactive_system_prompt.py`
- Lint: `uv run ruff check massgen/orchestrator.py massgen/orchestrator_collaborators/ massgen/frontend/displays/textual_terminal_display.py massgen/frontend/displays/_textual_*.py` — all checks passed.

## Verification

- Public-method set of `Orchestrator` is byte-identical to HEAD (no methods silently dropped or renamed).
- `MassOrchestrator` correctly absent from `massgen.orchestrator` (asserted in characterization tests).
- Built-in skills directory still resolves to `<repo>/massgen/skills` (`SkillsConfigValidator` anchors via `massgen.orchestrator.__file__`, NOT the collaborator's `__file__`).
- Working tree is the only artifact — no commits.

## Known Test Lane Note

- Independent review (senior-code-reviewer) ran the fast non-API lane against HEAD vs this branch:
  - **HEAD baseline: 60 failures** (all unrelated to this PR — pre-existing on `dev/v0.1.92` from in-flight WIP)
  - **This branch: 59 failures**
  - Net impact: **0 regressions introduced, +1 test newly passing** (`test_lazy_collaborator_accessors_do_not_require_init` — fails on HEAD because the cached-property pattern doesn't exist there; passes here)
- The 60 baseline failures are largely from untracked WIP test files that this PR does not touch (e.g. `test_subagent_round_timeouts.py`, `test_interactive_thread_style.py`, `test_subagent_continuation.py`, `test_broadcast_integration.py`, `test_interactive_mode.py`, plus the long-standing `test_timeline_snapshot_scaffold.py` snapshot mismatch).
- The same untracked WIP test-file collection errors as v0.1.91 still apply (`test_launch_run_card.py` missing `launch_run_card` module; `test_interactive_system_prompt.py` missing `InteractiveOrchestratorSection`).

## Out of scope (paused for follow-up release)

One remaining concern needs behavior-changing work before extraction:

- **`MidStreamInjectionHookInstaller` (remaining 12 of 18 methods)** — `_setup_hook_manager_for_agent`, `_setup_codex_mcp_hooks`, `_setup_codex_hybrid_hooks`, `_setup_native_hooks_for_agent`, `_register_round_timeout_hooks`, etc. These contain duplicated `get_injection_content` closures across 3 backend paths. Need a callback-unification pass first (behavior-changing, separate validation surface), THEN extract. The 6 pure helpers (`_close_agent_stream`, `_check_restart_pending`, `_should_defer_restart_for_first_answer`, `_clear_framework_mcp_state`, `_compute_plan_progress_stats`, `_build_tool_result_injection`) ARE extracted in this PR.

Also out of scope: the streaming/coordination cores (`_stream_agent_execution` 2,239 lines, `_stream_coordination_with_agents` 911, `_coordinate_agents` 541, `__init__` ~557, `chat` 180) — these need structural restructuring rather than pure extraction, deferred to a separate PR.

The full plan, ordered steps, and applied-during-this-PR lessons learned are in `docs/dev_notes/orchestrator_refactor_roadmap.md` to make the follow-up straightforward.
