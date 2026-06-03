# Changelog

All notable changes to MassGen will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## Recent Releases

**v0.1.93 (June 3, 2026)** - CLI Package Decomposition & Pydantic Config Migration
Splits the monolithic `cli.py` into a focused `massgen/cli/` package, migrates the configuration classes to pydantic dataclasses with `Literal`-typed modes validated at construction, removes ~8.7k lines of dead legacy code, and hardens the test-signal and type-checking tooling (coverage gate, no-assert guard, `uv.lock` enforcement, and an incremental mypy ratchet). Internal-quality release with no runtime behavior changes.

**v0.1.92 (June 1, 2026)** - Orchestrator Collaborator Refactor & Parallel Search MCP
Refactors the monolithic orchestrator into 49 lazy collaborators with stable delegator call sites, splits focused TUI display helpers into sibling modules, adds characterization coverage for the extraction seams, and introduces a Parallel Web Search MCP registry entry plus runnable example config.

**v0.1.91 (May 27, 2026)** - Config Reliability & Hook Safety
Hardens release-critical configuration paths with centralized coordination, timeout, and orchestrator runtime parsing; strict unknown-key validation for typo detection; checklist runtime control wiring; and safer Gemini/Codex native hook path permission precedence.

**v0.1.90 (May 25, 2026)** - Discriminative Criteria Refinements & Checklist Calibration
Improves checklist-gated refinement quality with discriminative-power pruning, per-criterion feedback carried into the next round, position-bias counterbalancing, deterministic tie-breaking, a unified checklist gate on a single 0-10 scale, shared score parsing utilities, and fast-iteration config updates.

**v0.1.89 (May 22, 2026)** - Antigravity CLI Full Integration & Hardening
Completes the follow-up Antigravity integration pass with workflow-mode parity, early auth and binary health checks, workspace-root file writes via `--add-dir`, `.antigravitycli/` project-root anchoring, standalone `hooks.json` wiring with `enableJsonHooks`, prompt affordance gating for disabled subagents, and expanded regression coverage.

**v0.1.88 (May 20, 2026)** - Antigravity CLI Backend
Adds a new `antigravity_cli` backend wrapping Google's `agy` binary, with workspace-local `.antigravity/` isolation, MCP config emission using Antigravity's `serverUrl` schema, native-hook adapter support, OAuth/API-key auth handling, and new runnable configs for both single-agent and mixed Gemini + Antigravity runs.

**v0.1.87 (May 15, 2026)** - Documentation: Framework Comparisons & `llms.txt`
Documentation release adding three "MassGen vs ..." comparison pages (CrewAI, LangGraph, AutoGen/AG2), a curated `llms.txt` index plus full-corpus `llms-full.txt` dump (per [llmstxt.org](https://llmstxt.org) spec), and small README/landing-page pointers so AI agents and crawlers can discover the docs. Also ships a one-line `refine=False` fix for the `bootstrap_subagent` discriminator that was being shadowed by the orchestrator's default `max_new_answers_per_agent`.

**v0.1.86 (May 13, 2026)** - `bootstrap_subagent` Discriminator + Codex MCP Approval Fix
Variant B (`criteria_mode: bootstrap_subagent`) is now functional: the orchestrator runs an in-process critic between rounds, merges critic-proposed criteria into the accumulator, and augments the next round's checklist. This release also fixes Codex MCP tool calls under `codex exec` by writing the approval bypasses needed for non-interactive runs.

**v0.1.85 (May 11, 2026)** - Discriminative Criteria Emergence (`criteria_mode`)
New `orchestrator.coordination.criteria_mode` option lets evaluation criteria emerge from observed gaps across rounds instead of being pre-authored. `bootstrap_inline` variant is fully functional on all backends with checklist tool support — agents emit `proposed_criteria` alongside `submit_checklist`, the accumulator dedupes/caps, and the next round's checklist is augmented automatically.

---

## [0.1.93] - 2026-06-03

### Changed
- **CLI Package Decomposition**: The monolithic `massgen/cli.py` (12,206 lines) was split into an 18-module `massgen/cli/` package with a facade `__init__` that preserves the public surface — `from massgen.cli import X` and `massgen.cli.X` continue to work unchanged. The ~886-line per-turn handler inside the Textual interactive loop was extracted into a module-level, dependency-injected function, dropping that loop from ~1,200 to ~284 lines.
- **Pydantic Config Migration**: The configuration classes (`AgentConfig`, `CoordinationConfig`, `TimeoutConfig`, `StepModeConfig`, `PromptImproverConfig`, and the persona/criteria/decomposer/subagent-orchestrator sub-configs) were migrated from plain dataclasses to `pydantic.dataclasses`, validating field types on construction while preserving `from_dict`/`to_dict`/`__post_init__` semantics. `pydantic>=2.0` is now a declared dependency.
- **Typed Mode Fields (Single Source of Truth)**: Mode fields (`write_mode`, `coordination_mode`, `novelty_injection`, `drift_conflict_policy`, `final_answer_strategy`, etc.) are now `Literal` types in `massgen/config_modes.py`, and `config_validator` derives its `VALID_*` sets from them via `get_args` so the validator can no longer drift from the config models.
- **Single-Source Exclusion Lists**: The two hand-duplicated 104/105 "params never forwarded to provider APIs" lists in `backend/base.py` and the API params handler now derive from one `frozenset` (`backend/_excluded_params.py`), with a regression test locking them in sync.

### Fixed
- **Concurrent-Run Log Isolation (MAS-274)**: The Textual interactive orchestration thread now inherits the per-run logging session via `contextvars.copy_context()`, so concurrent in-process runs no longer cross-contaminate logs and snapshot paths by falling back to the process-global session.
- **Stale Validator Set**: The validator's subagent runtime-mode set omitted `delegated` and would have rejected valid configs; deriving it from the `Literal` source of truth fixes this.
- **Config Default Regression**: `CoordinationConfig.from_dict` now drops `None` values so absent YAML keys fall back to field defaults (previously `write_mode` could become `None` instead of `"auto"`).
- **Backend Tool-Arg Logging**: The Response backend routes tool-call argument parsing through the shared normalizer, logging malformed payloads instead of silently dropping them to `{}`.

### Removed
- **Dead Legacy Packages**: Deleted ~8,700 lines of unreferenced legacy code (`massgen/v1`, `massgen/prototype`) that were being shipped in the wheel.

### Tests
- **Test-Signal Hardening**: Fixed the broken coverage configuration (`source` matched no real package), enabled `error::pytest.PytestReturnNotNoneWarning` so no-assert tests fail, and switched CI to enforce `uv.lock` (`uv sync --frozen`) with actionable `--tb=short`.
- **Incremental mypy Ratchet**: Re-enabled mypy (previously fully disabled) on a curated island of clean modules via `scripts/mypy_island.sh`, wired as a blocking pre-commit hook and CI gate, plus a non-blocking full-repo mypy job for visibility.
- Added `test_config_pydantic_validation.py`, `test_excluded_params_single_source.py`, and CLI helper/run-loop characterization suites; verified all 282 bundled configs still validate.

### Notes
- Image/Video Edit Capabilities ([#959](https://github.com/massgen/MassGen/issues/959)) remain deferred to a future release.
- This is an internal-quality release: behavior is preserved, with the focus on decomposing the CLI, giving configuration real type validation, and re-enabling type checking.

### Technical Details
- **Major Focus**: Shrink and harden MassGen's CLI and configuration layers without changing runtime behavior, making future changes easier to isolate, type-check, and review.
- **Key Commits**: `68fcd74b`, `51483e17`, `74f9b21a`, `1dcd01b9`, `701b11e5`
- **Contributors**: @ncrispino and the MassGen team

---

## [0.1.92] - 2026-06-01

### Added
- **Parallel Web Search MCP**: Added a `parallel_search` MCP server registry entry and `massgen/configs/tools/web-search/parallel_search_example.yaml` for Parallel's hosted Search MCP server, supporting anonymous exploratory use and optional `PARALLEL_API_KEY` headers for higher rate limits.
- **Orchestrator Refactor Roadmap**: Added `docs/dev_notes/orchestrator_refactor_roadmap.md` to document the extraction sequence, lessons learned, and high-risk follow-up work left intentionally out of scope.
- **Characterization Coverage**: Added orchestrator and Textual terminal display characterization suites to pin public contracts and extraction seams before continuing deeper refactors.

### Changed
- **Orchestrator Collaborator Extraction**: `massgen/orchestrator.py` was reduced from 21,599 to 8,574 lines by extracting 49 lazy collaborators into `massgen/orchestrator_collaborators/`. Existing methods remain available through thin delegators so current internal and external call sites keep working.
- **Textual Terminal Display Cleanup**: Provider/model display helpers, terminal capability probing, and widget-debug helpers moved out of `textual_terminal_display.py` into focused sibling modules while preserving public imports.
- **Refactor Test Seams**: Existing monkeypatch and mock-stub tests were repointed to the collaborator locations without deleting tests or weakening assertions.

### Tests
- Added `massgen/tests/test_orchestrator_characterization.py` covering the orchestrator public contract and lazy collaborator access pattern.
- Added `massgen/tests/frontend/test_textual_terminal_display_characterization.py` covering Textual display public exports and helper extraction seams.
- Updated integration/unit coverage around broadcast hooks, restart/external tools, auto trace analysis, essential files, evaluator personas, and orchestrator units for the new collaborator seams.
- Verified targeted characterization and collaborator suites; ruff checks pass for the refactored orchestrator, collaborator package, and Textual display modules.

### Notes
- Image/Video Edit Capabilities ([#959](https://github.com/massgen/MassGen/issues/959)) remain deferred to v0.1.94.
- Remaining high-risk extraction work for MidStreamInjectionHookInstaller and streaming/coordination cores is documented for follow-up.

### Technical Details
- **Major Focus**: Shrink MassGen's orchestration core without changing behavior, making future coordination changes easier to isolate and review.
- **Key Commits**: `f9227eaf`, `a80281cb`, `efa4dd4c`, `b155a346`
- **PRs Merged**: [#1108](https://github.com/massgen/MassGen/pull/1108)
- **Contributors**: @NormallyGaussian, @ncrispino, @HenryQi and the MassGen team

---

## [0.1.91] - 2026-05-27

### Added
- **Config Drift Detection**: Config validation now warns on unknown `orchestrator.coordination.*`, top-level `orchestrator.*`, and `timeout_settings.*` keys so YAML typos are visible, and strict config validation treats those warnings as release-blocking.
- **Native Hook Permission Specificity**: Gemini CLI and Codex standalone hook scripts now enforce more-specific managed paths and protected paths before broader writable parents, preventing nested read-only paths from being masked by workspace-level write access.

### Changed
- **Centralized Config Wiring**: `CoordinationConfig.from_dict()` and `TimeoutConfig.from_dict()` now own YAML parsing for their surfaces, while `AgentConfig.apply_orchestrator_config()` owns top-level orchestrator runtime field application. CLI helpers remain as compatibility wrappers.
- **Checklist Runtime Controls**: `max_checklist_calls_per_round` and `checklist_first_answer` now flow through the centralized top-level orchestrator runtime helper instead of being validation-only settings.
- **Claude Native Hook Injection Contract**: Claude Code native hook tests and docs now match the adapter's SDK-native `additionalContext` injection format.

### Tests
- Added parser/validator parity coverage for coordination config fields, timeout settings, top-level orchestrator runtime fields, nested `standalone_checkpoint` aliases, documented YAML field coverage, and strict `scripts/validate_all_configs.py` behavior.
- Added native hook regression coverage for nested read-only path precedence, protected-path enforcement, and Claude Code `additionalContext` injection conversion.

### Notes
- Image/Video Edit Capabilities ([#959](https://github.com/massgen/MassGen/issues/959)) remain deferred to v0.1.94.

### Technical Details
- **Major Focus**: Make release-critical YAML configuration surfaces typo-resistant and parser-complete while hardening native hook path authorization.
- **Commits**: `3d25441e`, `47449c69`
- **Contributors**: @ncrispino, @HenryQi and the MassGen team

---

## [0.1.90] - 2026-05-25

### Added
- **Discriminative-Power Criteria Pruning**: Bootstrap criteria now compute per-criterion score spread across agents and demote low-spread, non-discriminative criteria to `stretch` while preserving a protected floor so the gate is not hollowed out.
- **Per-Criterion Feedback Loop**: Checklist score reasoning is extracted into a `<CRITERION FEEDBACK ...>` memo and queued into the next round, preserving the diagnostic gradient instead of reducing failures to numeric scores only.
- **Position-Bias Calibration**: Candidate answer presentation is deterministically rotated per scoring agent, distributing the primacy slot and placing the scorer's own answer last in its view.
- **Canonical Score Utilities**: New `massgen/score_utils.py` centralizes score extraction and per-agent score-shape detection across checklist, quality, and bootstrap-criteria paths.

### Changed
- **Checklist Gate Unification**: `ChecklistGate.from_budget(...)` derives effective threshold, required-true count, and confidence cutoff from one 0-10 scale, replacing drift-prone duplicate calculations.
- **Tie-Break Determinism**: Equal aggregate checklist scores now resolve independently of dictionary insertion order.
- **Backend Circuit-Breaker Config**: Shared `llm_circuit_breaker_*` kwarg parsing moved into `CustomToolAndMCPBackend`, removing duplicate backend implementations.
- **Fast-Iteration Configs**: Fast-iteration examples are updated for local command execution by default and current Gemini/Codex/Antigravity pairings.
- **Criteria Generation Fallback Signaling**: Generic fallback criteria now log and display as a warning so users can see when domain-specific generation failed.

### Tests
- `massgen/tests/test_discriminative_pruning.py` covers score-spread calculation, non-discriminative criterion demotion, protected floors, and orchestrator wiring.
- `massgen/tests/test_criterion_feedback.py` covers reasoning extraction from flat/per-agent score shapes and next-round feedback memo delivery.
- `massgen/tests/test_position_bias_calibration.py` covers deterministic tie-breaking and answer-order counterbalancing.
- `massgen/tests/test_score_utils.py` covers canonical score parsing behavior and per-agent score-shape detection.
- `massgen/tests/test_checklist_tools_server.py` updated for shared score parsing, feedback extraction, and checklist gate behavior.

### Notes
- Discriminative Criteria Refinements from the v0.1.90 roadmap landed in this release.
- Image/Video Edit Capabilities ([#959](https://github.com/massgen/MassGen/issues/959)) remain deferred to v0.1.94.

### Technical Details
- **Major Focus**: Make checklist-gated refinement a stronger optimization loop by improving the loss signal, reducing scoring bias, and preventing low-signal criteria from dominating later rounds.
- **Commits**: `96e9aff7`, `62cf4bf0`
- **Contributors**: @ncrispino, @HenryQi and the MassGen team

---

## [0.1.89] - 2026-05-22

### Added
- **Antigravity Workflow-Mode Parity** ([#1099](https://github.com/massgen/MassGen/pull/1099)): Ported Gemini CLI workflow-mode inference into `antigravity_cli`, including `new_answer_only` rounds when no candidate answers exist, post-evaluation phase guards, duplicate workflow-call suppression, and text-fallback parsing for `new_answer` / `vote`.
- **Auth and Binary Health Checks** ([#1099](https://github.com/massgen/MassGen/pull/1099)): The backend now verifies `agy --version` at construction time and fails fast when neither API-key auth nor cached Google OAuth credentials are available.
- **Workspace Project Anchoring** ([#1099](https://github.com/massgen/MassGen/pull/1099)): Antigravity runs now pre-create a workspace-root `.antigravitycli/` marker and pass `--add-dir <cwd>` so agy's project discovery and file writes stay inside the MassGen workspace.
- **Standalone Antigravity Hooks Wiring** ([#1099](https://github.com/massgen/MassGen/pull/1099)): Native hooks now emit Antigravity's standalone `hooks.json` format and enable it through `settings.json` with `enableJsonHooks`.

### Changed
- **System Prompt Affordance Gating**: `TaskContextSection` now advertises subagent affordances only when subagents are actually enabled, preventing phantom subagent MCP calls in multimodal-only runs.
- **Antigravity Settings and Cleanup**: System-prompt `AGENTS.md` writes are atomic, transient hook files are restored, and `.antigravity/` / `.antigravitycli/` are ignored as runtime artifacts.
- **Antigravity Native Hook Adapter Docs**: Adapter comments now describe agy's `hooks.json` storage model instead of Gemini CLI's embedded `settings.json["hooks"]` model.

### Tests
- `massgen/tests/test_antigravity_cli_backend.py` expanded from initial backend coverage to 1,100+ lines covering health checks, authentication, workspace anchoring, `--add-dir`, hooks.json, workflow-mode filtering, duplicate tool-call suppression, multimodal prompt flattening, cancellation cleanup, and agent-id propagation.
- `massgen/tests/test_system_prompt_sections.py` adds regression coverage that `TaskContextSection` hides `spawn_subagents` when subagents are disabled and shows it only when enabled.

### Notes
- This release completes the follow-up Antigravity integration pass that v0.1.88 introduced as a first version.
- Discriminative Criteria Refinements landed in v0.1.90; Image/Video Edit Capabilities ([#959](https://github.com/massgen/MassGen/issues/959)) remain deferred to v0.1.94.

### Technical Details
- **Major Focus**: Make Antigravity CLI reliable in real MassGen coordination runs by hardening auth, workspace isolation, workflow-tool semantics, hook integration, and prompt affordance boundaries.
- **PRs Merged**: [#1099](https://github.com/massgen/MassGen/pull/1099)
- **Contributors**: @ncrispino, @HenryQi and the MassGen team

---

## [0.1.88] - 2026-05-20

### Added
- **Antigravity CLI Backend** ([#1097](https://github.com/massgen/MassGen/pull/1097)): New `massgen/backend/antigravity_cli.py` wraps Google's `agy` binary as a MassGen backend. It accepts the `antigravity_cli` backend type, streams content from the subprocess, tails Antigravity session logs for tool/thinking events, and exposes provider metadata through the backend capabilities registry.
- **Workspace-Local Antigravity Isolation** ([#1097](https://github.com/massgen/MassGen/pull/1097)): The backend passes Antigravity's hidden `--gemini_dir <workspace>/.antigravity` flag so MCP config and settings stay inside the run workspace instead of mutating the user's global `~/.gemini/` config.
- **Antigravity MCP Config Translation** ([#1097](https://github.com/massgen/MassGen/pull/1097)): MassGen MCP server entries are translated to Antigravity's `mcp_config.json` schema, including `serverUrl` for HTTP servers and `command`/`args`/`env` for stdio servers.
- **Native Hook Adapter** ([#1097](https://github.com/massgen/MassGen/pull/1097)): Added `massgen/mcp_tools/native_hook_adapters/antigravity_cli_adapter.py`, reusing Gemini CLI hook behavior for Antigravity's compatible hook protocol.
- **Example Configs** ([#1097](https://github.com/massgen/MassGen/pull/1097)):
  - `massgen/configs/providers/antigravity/antigravity_cli_local.yaml` — single Antigravity CLI agent
  - `massgen/configs/features/fast_iteration_gemini_antigravity.yaml` — mixed Gemini API + Antigravity CLI fast-iteration run

### Changed
- **Backend Registry and CLI Wiring**: `antigravity_cli` is exported from `massgen/backend/__init__.py`, registered in `massgen/backend/capabilities.py`, and instantiated in `massgen/cli.py`.
- **Workspace Snapshot Hygiene**: `.antigravity` / `.antigravitycli` metadata directories are excluded from meaningful-content and snapshot-copy heuristics.
- **Feature Highlights**: Announcement feature highlights now list Antigravity CLI alongside Claude Code, Codex, Gemini CLI, and GitHub Copilot.

### Tests
- `massgen/tests/test_antigravity_cli_backend.py` — 490 lines covering binary discovery, command construction, workspace-local config, MCP config schema, provider metadata, stdout/error streaming, workflow JSON envelopes, Docker/API-key constraints, native hook adapter wiring, and environment passthrough.

### Notes
- Antigravity CLI (`agy`) must be installed separately with `curl -fsSL https://antigravity.google/cli/install.sh | bash`.
- Local mode can use existing Google OAuth state at `~/.gemini/google_accounts.json`; Docker mode requires `GEMINI_API_KEY` or `GOOGLE_API_KEY` because OAuth state does not cross container boundaries.
- Follow-up Antigravity hardening landed in v0.1.89; Discriminative Criteria Refinements landed in v0.1.90; Image/Video Edit Capabilities ([#959](https://github.com/massgen/MassGen/issues/959)) remain deferred to v0.1.94.

### Technical Details
- **Major Focus**: Add Google Antigravity CLI as a first-class MassGen backend while keeping project-local isolation and MassGen workflow/tool semantics intact.
- **PRs Merged**: [#1097](https://github.com/massgen/MassGen/pull/1097)
- **Contributors**: @ncrispino, @HenryQi and the MassGen team

---

## [0.1.87] - 2026-05-15

### Added
- **Framework Comparison Pages** ([#1094](https://github.com/massgen/MassGen/pull/1094)): Three new "MassGen vs ..." pages under `docs/source/reference/comparisons/` — `crewai.rst`, `langgraph.rst`, `autogen.rst`. Each page positions MassGen's parallel-refinement-with-voting model against the target framework's coordination shape and lists when to reach for one versus the other
- **`llms.txt` Index** ([#1094](https://github.com/massgen/MassGen/pull/1094)): Curated [llmstxt.org](https://llmstxt.org)-spec index published at the docs site root via Sphinx `html_extra_path` (`docs/source/_extra/llms.txt`) — gives AI agents a small, hand-picked map of the docs
- **`llms-full.txt` Corpus** ([#1094](https://github.com/massgen/MassGen/pull/1094)): Concatenated full-docs dump (~1 MB across 59 files), generated by a Sphinx `build-finished` hook in `docs/source/conf.py` and shipped alongside `llms.txt` for crawlers that want the complete corpus
- **Docs Landing Page Update** ([#1094](https://github.com/massgen/MassGen/pull/1094)): "How Does MassGen Compare?" section on `docs/source/index.rst` now lists all four comparisons (LLM Council + the three new ones), with the parent `docs/source/reference/comparisons.rst` losing its "coming soon" note and gaining a toctree
- **README Pointers** ([#1094](https://github.com/massgen/MassGen/pull/1094)): One-line pointers in `README.md` (and synced `README_PYPI.md`) directing AI agents to `llms.txt` / `llms-full.txt`

### Fixed
- **`bootstrap_subagent` Discriminator Single-Shot** ([#1094](https://github.com/massgen/MassGen/pull/1094)): `Orchestrator._run_bootstrap_discriminator_step` now passes `refine=False` to `SubagentManager.spawn_subagent`. This is the canonical single-shot knob that `SubagentManager` actually respects at the orchestrator level — without it, the orchestrator's `max_new_answers_per_agent: 3` default shadowed the coordination-dict overrides, letting the discriminator refine instead of single-shot. Found via live log inspection (`log_20260513_095921_816676`)
  - `massgen/orchestrator.py:1298` — `refine=False` added to `spawn_subagent` call
  - `massgen/tests/test_bootstrap_criteria.py` — new assertion that `discriminator must pass refine=False to spawn_subagent for single-shot`

### Documentations, Configurations and Resources
- **Comparison pages**: `docs/source/reference/comparisons/{crewai,langgraph,autogen}.rst`
- **Sphinx `build-finished` hook**: `docs/source/conf.py` — generates `llms-full.txt` from the source tree at build time
- **README pointers**: `README.md`, `README_PYPI.md` — AI agents are directed to `llms.txt` / `llms-full.txt`

### Notes
- Originally-planned Image/Video Edit Capabilities ([#959](https://github.com/massgen/MassGen/issues/959)) and Discriminative Criteria Refinements deferred to v0.1.88.
- Closes [#1082](https://github.com/massgen/MassGen/issues/1082) (publish `llms.txt` + `llms-full.txt`) and [#1083](https://github.com/massgen/MassGen/issues/1083) (CrewAI / LangGraph / AutoGen comparison pages).

### Technical Details
- **Major Focus**: Make MassGen discoverable to AI agents and crawlers, and give human readers structured "MassGen vs ..." comparisons against the three frameworks most often asked about
- **PRs Merged**: [#1094](https://github.com/massgen/MassGen/pull/1094)
- **Issues Closed**: [#1082](https://github.com/massgen/MassGen/issues/1082), [#1083](https://github.com/massgen/MassGen/issues/1083)
- **Contributors**: @ncrispino, @HenryQi and the MassGen team

---

## [0.1.86] - 2026-05-13

### Added
- **Functional `bootstrap_subagent` Variant**: `orchestrator.coordination.criteria_mode: bootstrap_subagent` now runs a between-rounds LLM critic via `Orchestrator._run_bootstrap_discriminator_step()`. The critic reads the task and each agent's latest answer, emits `proposed_criteria` as JSON, and the orchestrator merges them into the accumulator for the next round's checklist.
- **Discriminator De-Duping Gate**: `_maybe_run_bootstrap_discriminator` runs the critic once per unique answer snapshot, avoiding repeated critiques when the visible answer set has not changed.
- **Session-End Criteria Drain**: `Orchestrator._drain_at_session_end` forces a final drain before final presentation so late stdio JSONL emissions are not stranded after the last checklist resolution pass.

### Fixed
- **Codex MCP Approval Bypass**: `CodexBackend._write_workspace_config` now writes both top-level `approval_policy = "never"` and per-MCP-server `default_tools_approval_mode = "approve"` for non-interactive approval modes. This prevents external MCP tools such as `submit_checklist`, `create_task_plan`, `new_answer`, and `read_media` from failing immediately with "user cancelled MCP tool call" under `codex exec`.

### Documentations, Configurations and Resources
- **Updated Config**: `massgen/configs/coordination/bootstrap_subagent_criteria.yaml` now documents the v0.1.86+ active critic-driven flow.

### Tests
- `massgen/tests/test_bootstrap_criteria.py` — expanded to 35 tests covering session-end drain, mocked discriminator spawning and merge behavior, static/inline no-op paths, and empty-answer no-op behavior.
- `massgen/tests/test_codex_native_hook_adapter.py::TestCodexWorkspaceApprovalPolicy` — covers Codex workspace approval policy output across approval modes.

### Notes
- Image/Video Edit Capabilities ([#959](https://github.com/massgen/MassGen/issues/959)) remain deferred to v0.1.87.

### Technical Details
- **Major Focus**: Complete the discriminative criteria emergence story by making the dedicated critic-driven path functional, and restore Codex MCP tool-call reliability for non-interactive automation.
- **PRs Merged**: [#1090](https://github.com/massgen/MassGen/pull/1090)
- **Contributors**: @ncrispino, @HenryQi and the MassGen team

---

## [0.1.85] - 2026-05-11

### Added
- **Discriminative Criteria Emergence**: New `orchestrator.coordination.criteria_mode` option lets evaluation criteria emerge from observed gaps across rounds, instead of requiring them to be authored upfront via `--eval-criteria` or `--checklist-criteria-preset`. Two variants:
  - **`bootstrap_inline`** (fully functional on **all backends with checklist tool support** — SDK *and* stdio): each agent emits a short `proposed_criteria` list alongside its `submit_checklist` call — criteria a stronger answer would satisfy that the current answers do *not*. Proposals are deduped by exact text, FIFO-capped (`bootstrap_max_total`, default 30), persisted to `bootstrap_criteria_accumulator.json` in the session log dir, and merged into the next round's effective checklist via the existing `EvaluationSection` machinery. SDK path (Claude Code) gets the field directly in the in-process tool schema; stdio backends (gemini, codex, response, chat_completions, claude, grok) get a JSONL emission channel — `proposed_criteria.jsonl` next to the checklist specs, drained by the orchestrator on each criteria resolution.
  - **`bootstrap_subagent`** (wired, LLM step deferred): same accumulator pipeline but criteria are intended to come from a between-rounds critic rather than the agents. The accumulator still propagates seeded entries; the in-process LLM discriminator pass is queued for v0.1.86.
- **`massgen/bootstrap_criteria.py`** (new module): houses `merge_proposals`, `augment_with_accumulator`, `is_bootstrap_mode`, and `validate_criteria_mode` — pure helpers shared between orchestrator and tests.
- **Coordination Config Fields**: `CoordinationConfig.{criteria_mode, bootstrap_max_per_agent_per_round, bootstrap_max_total}` — parsed in `cli.py:_parse_coordination_config`, validated in `CoordinationConfig._validate_criteria_mode`, excluded from API params in `backend/base.py:get_base_excluded_config_params`.
- **SDK Path Wiring** (`Orchestrator._init_checklist_tool_sdk`): the `submit_checklist` schema gains an optional `proposed_criteria` array in `bootstrap_inline` mode only; static-mode agents see the historical schema unchanged. Parsed proposals land on `AgentState.criteria_proposals` and are drained into the orchestrator's accumulator on each criteria resolution.
- **Stdio Path Wiring** (`massgen/mcp_tools/checklist_tools_server.py`): the FastMCP `submit_checklist` tool conditionally adds `proposed_criteria` to its `inspect.Signature` when `state["criteria_mode"] == "bootstrap_inline"`. Emissions are appended to `proposed_criteria.jsonl` in the specs directory; `Orchestrator._drain_pending_criteria_proposals` reads and truncates the file each pass.

### Why This Matters
- Removes a cold-start friction: users no longer need to pre-author criteria for a new task. The first round produces both answers *and* the criteria the second round must rise to.
- **Anti-Goodhart by construction** — criteria come from observed gaps, not priors that may not match the task.
- Uses MassGen's multi-round/multi-agent shape directly; the cross-agent channel (workspace sharing) already existed, so no new transport was needed.

### Documentations, Configurations and Resources
- **New Configs**: `massgen/configs/coordination/bootstrap_inline_criteria.yaml` and `bootstrap_subagent_criteria.yaml` (forked from `features/fast_iteration.yaml`) — runnable examples for both variants
- **Updated `docs/modules/coordination_workflow.md`**: new section documenting `criteria_mode`, accumulator semantics, and the two variants

### Tests
- `massgen/tests/test_bootstrap_criteria.py` — 30 new tests (476 lines) covering merge/dedup/cap, config validation, `AgentState.criteria_proposals` field, `_resolve_effective_checklist_criteria` augmentation across criteria sources, `EvaluationSection` rendering gating, `_drain_pending_criteria_proposals` behavior, and round-N → round-N+1 propagation end-to-end

### Notes
- Originally-planned Image/Video Edit Capabilities ([#959](https://github.com/massgen/MassGen/issues/959)) deferred to v0.1.86.
- `bootstrap_subagent` LLM discriminator pass queued for v0.1.86.

### Technical Details
- **Major Focus**: Let evaluation criteria emerge from the run rather than be pre-authored — anti-Goodhart, anti-cold-start, and natively shaped by MassGen's multi-round refinement loop
- **Contributors**: @ncrispino, @HenryQi and the MassGen team

---

## [0.1.84] - 2026-05-08

### Added
- **TUI Consensus Map** ([#1085](https://github.com/massgen/MassGen/pull/1085)): Compact visual map mounted below the agent status ribbon during multi-agent runs that summarizes coordination state without replacing the timeline. Shows one node per agent with latest answer labels, vote direction arrows, current vote leader, winner state, and waiting/working indicators. Hidden on welcome screen and single-agent runs
  - `massgen/frontend/displays/textual_widgets/consensus_map.py` — new `ConsensusMapState`, `ConsensusAgentState`, `ConsensusMapSnapshot`, and `ConsensusMap` widget
  - `massgen/frontend/displays/textual_widgets/__init__.py` — widget export
  - `massgen/frontend/displays/textual_terminal_display.py` — mounting below status ribbon, event/status wiring, visibility logic
  - `massgen/frontend/displays/tui_event_pipeline.py` — event routing for the map
  - `massgen/frontend/displays/textual_themes/base.tcss` — consensus map theme styling
- **Event-Driven State Updates** ([#1085](https://github.com/massgen/MassGen/pull/1085)): The Consensus Map subscribes to existing structured coordination events (`answer_submitted`, `vote`, `agent_stopped`, `winner_selected`, `final_presentation_start`, `agent_restart`, `phase_change`, `context_received`) — no backend schema changes required
- **Direct-Callback Fallback** ([#1085](https://github.com/massgen/MassGen/pull/1085)): When direct TUI callbacks update agent status or votes (without the unified event pipeline), the map remains accurate for the same visible state

### Documentations, Configurations and Resources
- **OpenSpec Change Proposal**: `openspec/changes/add-tui-consensus-map/{proposal,tasks}.md` and `specs/textual-tui/spec.md` — full design proposal, scenario coverage, and validation tasks

### Tests
- `massgen/tests/frontend/test_consensus_map.py` — unit tests for state transitions and Textual widget compact rendering / visibility (244 lines)
- `massgen/tests/frontend/test_timeline_snapshot_scaffold.py` — runtime TUI snapshot coverage for answer/vote/winner state (+68 lines)
- `massgen/tests/frontend/__snapshots__/test_timeline_snapshot_scaffold/test_timeline_snapshot_real_tui_consensus_map.svg` — golden TUI snapshot

### Notes
- Originally-planned Image/Video Edit Capabilities ([#959](https://github.com/massgen/MassGen/issues/959)) deferred to v0.1.85.

### Technical Details
- **Major Focus**: Make the physical shape of multi-agent collaboration visible at a glance — convergence, votes, and leader without scanning timelines and toasts
- **PRs Merged**: [#1085](https://github.com/massgen/MassGen/pull/1085)
- **Contributors**: @ncrispino, @HenryQi and the MassGen team

---

## [0.1.83] - 2026-05-01

### Added
- **In-Session Standalone Checkpoint MCP** ([#1079](https://github.com/massgen/MassGen/pull/1079)): The standalone checkpoint MCP server (originally for external hosts like Claude Code) can now be exposed *inside* a normal MassGen run, so a single-agent session can call its richer `init` + `checkpoint` tools and have its own reviewer team evaluate plans
  - `massgen/mcp_tools/standalone/checkpoint_mcp_server.py` — wired into in-session orchestration
  - `massgen/orchestrator.py` — orchestrator integration with affordance gating
  - `massgen/system_message_builder.py`, `massgen/system_prompt_sections.py` — standalone checkpoint prompt section
- **`coordination.standalone_checkpoint` Config Block** ([#1079](https://github.com/massgen/MassGen/pull/1079)): New YAML block under `orchestrator.coordination` with fields:
  - `enabled` (bool, default `false`) — opt-in gate
  - `team_config` (path) — team YAML the standalone server runs
  - `mode` (`generate` | `verify`, default `generate`) — invalid values fall back to `generate` with a warning
  - `single_checkpoint` (bool, default `false`) — one-shot checkpoint per session
  - `include_workspace_context` (bool, default `false`) — mount parent workspace read-only for reviewers
  - `massgen/agent_config.py` — `CoordinationConfig` fields and `to_dict` serialization
  - `massgen/cli.py` — `_parse_standalone_checkpoint` parser with mode validation
- **Enhanced Checkpoint Tool Card** ([#1079](https://github.com/massgen/MassGen/pull/1079)): Tool card visualization distinguishes primary operations from system tasks with improved context and result display
  - `massgen/frontend/displays/textual_widgets/tool_card.py`
- **Example Configs** ([#1079](https://github.com/massgen/MassGen/pull/1079)):
  - `massgen/configs/checkpoint/standalone_mcp/fast_iteration.yaml` — fast-iteration single-agent run with in-session standalone checkpoint
  - `massgen/configs/checkpoint/standalone_mcp/reviewers.yaml` — reviewer team config for the standalone server

### Changed
- **Single-Agent-Only Affordance Gating** ([#1079](https://github.com/massgen/MassGen/pull/1079)): When `standalone_checkpoint.enabled: true` is set on a multi-agent parent, the system skips the standalone server with a warning (the standalone server runs its own reviewer panel)
- **Workspace Metadata Exclusions** ([#1079](https://github.com/massgen/MassGen/pull/1079)): Updated `_metadata_dirs` in filesystem manager constants to keep standalone-checkpoint metadata out of final snapshots
  - `massgen/filesystem_manager/_constants.py`
- **Backend & API Param Exclusion Lists** ([#1079](https://github.com/massgen/MassGen/pull/1079)): New coordination keys excluded from forwarded backend/API params
  - `massgen/backend/base.py`, `massgen/api_params_handler/_api_params_handler_base.py`

### Documentations, Configurations and Resources
- **New Checkpoint Module Section**: `docs/modules/checkpoint.md` — added "Standalone Checkpoint MCP (in-session)" subsection with config schema, behavior table, and sample config reference
- **Configuration Examples**: `massgen/configs/checkpoint/standalone_mcp/{fast_iteration,reviewers}.yaml` — runnable examples for in-session standalone checkpoint

### Tests
- `massgen/tests/test_standalone_checkpoint_config.py` — config parsing & defaults
- `massgen/tests/test_standalone_checkpoint_mcp_config.py` — MCP server config wiring
- `massgen/tests/test_standalone_checkpoint_injection.py` — orchestrator-level injection
- `massgen/tests/test_standalone_checkpoint_prompt.py` — prompt section rendering across modes
- `massgen/tests/test_standalone_checkpoint_backend_parity.py` — backend parity coverage
- `massgen/tests/frontend/test_standalone_checkpoint_tool_card.py` — TUI tool card visualization

### Notes
- **Originally-planned features deferred**: Checkpoint Safety Mode for Irreversible Actions ([#1026](https://github.com/massgen/MassGen/issues/1026)) and Round Evaluator over-indexing fix ([#994](https://github.com/massgen/MassGen/issues/994)) deferred to a future release.

### Technical Details
- **Major Focus**: Bringing the standalone checkpoint MCP's richer planning affordance into single-agent in-session use, with explicit single-agent-only gating
- **PRs Merged**: [#1079](https://github.com/massgen/MassGen/pull/1079)
- **Contributors**: @ncrispino, @HenryQi and the MassGen team

---

## [0.1.82] - 2026-04-29

### Added
- **TUI Copy Mode** ([#1076](https://github.com/massgen/MassGen/pull/1076)): New `Ctrl+Shift+S` toggle that releases terminal mouse tracking so users can drag-select text natively and copy with the terminal's built-in shortcut; press again to restore Textual's normal mouse behavior. Auto-restores mouse capture on exit if copy mode is active
  - `massgen/frontend/displays/textual_widgets/copy_mode_banner.py` — banner widget and `set_terminal_mouse_capture` helper
  - `massgen/frontend/displays/textual_terminal_display.py` — `action_toggle_copy_mode` and `CopyModeBanner` integration
- **Checkpoint Workspace Context Option** ([#1076](https://github.com/massgen/MassGen/pull/1076)): New `include_workspace_context` config field for the standalone checkpoint MCP server — optionally mounts the executor's workspace directory as read-only context for reviewer agents (default `false`)
  - `massgen/mcp_tools/standalone/checkpoint_mcp_server.py`
- **Checkpoint Plan Quality Criteria** ([#1076](https://github.com/massgen/MassGen/pull/1076)): New `_build_checkpoint_plan_quality_criteria` produces mode-aware quality criteria (single vs. multi-checkpoint) that score selective branch depth and fallback handling in generated plans
- **Checkpoint Agent Recovery Guidance** ([#1076](https://github.com/massgen/MassGen/pull/1076)): Single-checkpoint mode continuation workflow added to `checkpoint_instructions.md` — detailed recovery steps for agents when a plan branch resolves to `terminate` without requiring a re-checkpoint

### Changed
- **TUI Ribbon Dividers** ([#1076](https://github.com/massgen/MassGen/pull/1076)): Visual separators in the agent status ribbon changed from `│` (pipe) to `·` (dot) for a cleaner look
  - `massgen/frontend/displays/textual_widgets/agent_status_ribbon.py`
- **Checkpoint "Better Means" Safety Guidance** ([#1076](https://github.com/massgen/MassGen/pull/1076)): Extended checkpoint planning prompt with four axes for recognizing when a cheaper path becomes unsafe: scarcity/contention, external visibility, authority substitution, and scope expansion
  - `massgen/mcp_tools/standalone/checkpoint_mcp_server.py`
- **Checkpoint Workspace Section Templated** ([#1076](https://github.com/massgen/MassGen/pull/1076)): Workspace section in checkpoint planning prompt now uses a `{workspace_section}` template variable, with content injected based on `include_workspace_context` setting

### Fixed
- **TUI Copy Mode Exit Cleanup** ([#1076](https://github.com/massgen/MassGen/pull/1076)): Mouse tracking is correctly restored before the driver tears down when the user exits while copy mode is active

### Documentations, Configurations and Resources
- **Updated Checkpoint Instructions**: `massgen/mcp_tools/standalone/checkpoint_instructions.md` — single-checkpoint continuation workflow with agent recovery steps for `terminate` branches

### Technical Details
- **Major Focus**: TUI copy mode for easier text selection and checkpoint quality/safety improvements
- **PRs Merged**: [#1076](https://github.com/massgen/MassGen/pull/1076)
- **Contributors**: @ncrispino, @HenryQi and the MassGen team

---

## [0.1.81] - 2026-04-27

### Added
- **Multi-Region Circuit Breaker Failover (Phase 6)** ([#1072](https://github.com/massgen/MassGen/pull/1072)): LLM circuit breaker fails over to backup regions when the primary trips OPEN, with automatic recovery when the primary returns to healthy

### Technical Details
- **Major Focus**: Multi-region failover for production-grade circuit breaker resilience — completes the circuit breaker series (Phase 1-6)
- **PRs Merged**: [#1072](https://github.com/massgen/MassGen/pull/1072)
- **Contributors**: @amabito, @HenryQi and the MassGen team

---

## [0.1.80] - 2026-04-22

### Added
- **Circuit Breaker Adaptive Thresholds (Phase 5)** ([#1065](https://github.com/massgen/MassGen/pull/1065)): Self-tuning thresholds that respond to each backend's actual failure patterns
- **Single Checkpoint Mode** ([#1070](https://github.com/massgen/MassGen/pull/1070)): New standalone checkpoint mode — no recheckpointing within a single operation
- **Draft Plan Verify Mode** ([#1070](https://github.com/massgen/MassGen/pull/1070)): New standalone checkpoint mode — verify a draft plan before executing

### Changed
- **Effective Threshold Helpers**: Extracted helper functions for cleaner threshold computation
- **Benign Case Clarity** ([#1070](https://github.com/massgen/MassGen/pull/1070)): Clearer benign-case handling in checkpoint flow

### Fixed
- **Force-Open Metrics** ([#1065](https://github.com/massgen/MassGen/pull/1065)): Gated `force_open` metrics and log on actual state transition
- **Preserve `_open_until`** ([#1065](https://github.com/massgen/MassGen/pull/1065)): Preserved `_open_until` on `force_open` with intent comments for clearer semantics

### Documentation, Configurations and Resources
- **Updated Standalone MCP README**: Updated `massgen/mcp_tools/standalone/README.md` with new checkpoint modes
- **Updated Checkpoint Instructions**: Updated `massgen/mcp_tools/standalone/checkpoint_instructions.md`

### Technical Details
- **Major Focus**: Adaptive circuit breaker thresholds and new standalone checkpoint modes
- **PRs Merged**: [#1065](https://github.com/massgen/MassGen/pull/1065), [#1070](https://github.com/massgen/MassGen/pull/1070)
- **Contributors**: @amabito, @ncrispino, @HenryQi and the MassGen team

---

## [0.1.79] - 2026-04-20

### Added
- **Better Fast Mode Options**: New options to control coordination speed — fine-grained speed vs. quality tradeoff

### Changed
- **Broader Checkpoint Framing**: Checkpoint mode framing broadened from safety-only to high-stakes and coordinated phases — use for deploys, deletions, financial ops, AND coordinated planning steps
- **Checkpoint Instructions Clarity**: More clarity in trust settings for checkpoint agents

### Documentation, Configurations and Resources
- **Updated Checkpoint Module**: Updated `docs/modules/checkpoint.md` with broadened framing
- **Updated Fast Iteration Config**: Updated `massgen/configs/features/fast_iteration.yaml` with new speed options
- **Updated Standalone MCP README**: Updated `massgen/mcp_tools/standalone/README.md`
- **Updated Checkpoint Instructions**: Updated `massgen/mcp_tools/standalone/checkpoint_instructions.md` with trust setting clarity

### Technical Details
- **Major Focus**: Fast mode speed control and broader checkpoint framing
- **Contributors**: @ncrispino, @HenryQi and the MassGen team

---

## [0.1.78] - 2026-04-17

### Added
- **Circuit Breaker Distributed Store (Phase 4)** ([#1061](https://github.com/massgen/MassGen/pull/1061)): Pluggable *state store* for the LLM circuit breaker. Previously each process kept its own CB state, so one worker tripping OPEN did not stop siblings from hammering a rate-limited upstream. CB state (failure counts, open/half-open/closed, cooldown timers) can now be shared across workers and processes. Default (`store=None`) keeps the existing single-process path unchanged.
  - `CircuitBreakerStore` Protocol: the interface the CB uses to persist state
  - `InMemoryStore` (CB state store): thread-safe, zero-deps — useful for single-process and tests
  - `RedisStore` (distributed CB state store): shares CB state across processes via Redis (`redis>=4.0`, lazy-imported); available through the optional `redis-store` extra
  - Atomic `atomic_record_failure` / `atomic_record_success` so CB state transitions are linearizable when workers race on the same backend
- **Optional Redis Dependency Group**: New `redis-store` extra for the Redis-backed CB store — install with `pip install massgen[redis-store]`

### Tests
- **CB Store Unit Tests** ([#1061](https://github.com/massgen/MassGen/pull/1061)): New `massgen/tests/test_cb_store.py` covering `InMemoryStore` and `RedisStore` behavior, Protocol contract, and metrics integration
- **CB Store Adversarial Tests** ([#1061](https://github.com/massgen/MassGen/pull/1061)): New `massgen/tests/test_cb_store_adversarial.py` covering TOCTOU races, Redis eviction, corrupted state handling, CAS semantics, probe-claiming, and TTL edge cases

### Documentation, Configurations and Resources
- **New Roadmap**: New `ROADMAP_v0.1.79.md` for the next release
- **Updated `pyproject.toml`**: Added `redis-store` optional dependency group

### Technical Details
- **Major Focus**: Distributed circuit breaker state — completes the CB observability stack started in v0.1.72 / v0.1.76
- **PRs Merged**: [#1061](https://github.com/massgen/MassGen/pull/1061)
- **Contributors**: @amabito, @ncrispino, @HenryQi and the MassGen team

---

## [0.1.77] - 2026-04-15

### Added
- **Answer Now Button** ([#1062](https://github.com/massgen/MassGen/pull/1062)): New "Answer Now" button lets agents submit answers more quickly, both within a round, and bypassing additional refinement rounds when quality is already sufficient

### Changed
- **Updated Checkpoint Instructions**: Refined agent memory instructions for checkpoint MCP
- **Updated Coordination Workflow Docs**: Clarified coordination workflow documentation

### Technical Details
- **Major Focus**: Answer Now Button — faster answers when quality is sufficient
- **PRs Merged**: [#1062](https://github.com/massgen/MassGen/pull/1062)
- **Contributors**: @ncrispino, @HenryQi and the MassGen team

---

## [0.1.76] - 2026-04-13

### Added
- **Exa AI Search Tool** ([#1057](https://github.com/massgen/MassGen/pull/1057)): New Exa AI-powered search tool added to MCP server registry with example config
- **Circuit Breaker Observability (Phase 3)** ([#1056](https://github.com/massgen/MassGen/pull/1056)): Observability module with probe ownership, lock release mechanisms, and per-attempt latency regression tracking
- **Checkpoint Agent Instructions** ([#1058](https://github.com/massgen/MassGen/pull/1058)): Copyable custom instructions for agent memory files with checkpoint MCP information

### Fixed
- **Docker Dependencies** ([#1058](https://github.com/massgen/MassGen/pull/1058)): Fixed Dockerfile installs for reliable container builds
- **Circuit Breaker Strengthening** ([#1056](https://github.com/massgen/MassGen/pull/1056)): Strengthened observability across all backends

### Documentation, Configurations and Resources
- **Updated MCP Server Registry**: Updated `docs/source/reference/mcp_server_registry.rst` with Exa search tool
- **Updated MCP Integration Guide**: Updated `docs/source/user_guide/tools/mcp_integration.rst`
- **Updated Standalone MCP README**: Updated `massgen/mcp_tools/standalone/README.md` with checkpoint instructions
- **New Checkpoint Instructions**: New `massgen/mcp_tools/standalone/checkpoint_instructions.md`
- **New Config**: New `massgen/configs/tools/web-search/exa_search_example.yaml`

### Technical Details
- **Major Focus**: Exa AI Search & Circuit Breaker Observability (Phase 3)
- **PRs Merged**: [#1056](https://github.com/massgen/MassGen/pull/1056), [#1057](https://github.com/massgen/MassGen/pull/1057), [#1058](https://github.com/massgen/MassGen/pull/1058)
- **Contributors**: @amabito, @HenryQi, @ncrispino, @teocollazo and the MassGen team

---

## [0.1.75] - 2026-04-10

### Added
- **Codex Native Hooks** ([#1053](https://github.com/massgen/MassGen/pull/1053)): Hybrid hook system for Codex backend combining native hooks and MCP capabilities
- **Checkpoint WebUI Auto-Launch** ([#1053](https://github.com/massgen/MassGen/pull/1053)): Checkpoint workflows now auto-launch the WebUI with configurable host/port for visual monitoring
- **Standalone MCP Server Documentation**: Guide for `massgen-checkpoint-mcp` with setup, examples, troubleshooting, and safety policy integration

### Changed
- **Checkpoint Planning Improvements** ([#1053](https://github.com/massgen/MassGen/pull/1053)): Precondition validation and recovery tree support; user/system prompt and eval criteria pass-through to checkpoint agents
- **Safety Policy Update**: Updated safety policy for checkpoint based on Claude Code safe mode

### Fixed
- **WebUI Automation Redirect** ([#1053](https://github.com/massgen/MassGen/pull/1053)): Fixed erroneous setup redirect during automation mode

### Documentation, Configurations and Resources
- **Updated Coordination Workflow**: Updated `docs/modules/coordination_workflow.md` with hook architecture and delivery rules
- **Updated Injection Guide**: Updated `docs/modules/injection.md`
- **Standalone MCP README**: New comprehensive `massgen/mcp_tools/standalone/README.md`

### Technical Details
- **Major Focus**: Codex Hooks & Checkpoint WebUI — deeper Codex integration and visual checkpoint monitoring
- **PRs Merged**: [#1053](https://github.com/massgen/MassGen/pull/1053)
- **Contributors**: @ncrispino, @HenryQi and the MassGen team

---

## [0.1.74] - 2026-04-08

### Changed
- **Checkpoint MCP Improvements** ([#1050](https://github.com/massgen/MassGen/pull/1050)): Major enhancements to standalone checkpoint MCP server (`massgen/mcp_tools/standalone/checkpoint_mcp_server.py`) — refinements to subprocess execution, isolation, workspace handling, and event relay
- **Pre-collab Criteria Refinements** ([#1050](https://github.com/massgen/MassGen/pull/1050)): Improvements to evaluation criteria generation in `precollab_utils.py`

### Fixed
- **Duplicate Tool Calls** ([#1050](https://github.com/massgen/MassGen/pull/1050)): Resolved duplicate tool call issues in `base_with_custom_tool_and_mcp.py`, `chat_completions.py` (including for MiniMax on OpenRouter), and `response.py` backends

### Documentation, Configurations and Resources
- **Updated Checkpoint Module**: Updated `docs/modules/checkpoint.md` with checkpoint MCP improvements
- **OpenSpec Updates**: Updated `openspec/changes/update-checkpoint-coordination-objectives/` design, spec, and tasks

### Technical Details
- **Major Focus**: Checkpoint MCP improvements and stability fixes
- **PRs Merged**: [#1050](https://github.com/massgen/MassGen/pull/1050)
- **Contributors**: @ncrispino, @HenryQi and the MassGen team

---

## [0.1.73] - 2026-04-06

### Added
- **Eval Criteria Evolver Subagent** ([#1047](https://github.com/massgen/MassGen/pull/1047)): New subagent type that evolves evaluation criteria across rounds — sharper, more opinionated criteria as the run progresses
- **Checkpoint Objective Mode (Initial Draft)** ([#1047](https://github.com/massgen/MassGen/pull/1047)): Initial draft of checkpoint MCP with `objective` mode for safety planning of irreversible actions (deletions, deployments, financial operations); returns ordered plan with per-step constraints and recursive recovery trees

### Changed
- **Improved Eval Criteria Visibility**: See what criteria agents are working against, more clearly
- **Trace Analyzer Improvements**: Refinements to trace analyzer subagent behavior

### Fixed
- **Evolver Fixes**: Stability fixes for the criteria evolver subagent

### Documentation, Configurations and Resources
- **Updated Checkpoint Module**: Updated `docs/modules/checkpoint.md` with objective mode documentation
- **OpenSpec Change**: New `openspec/changes/update-checkpoint-coordination-objectives/` proposal and spec for objective mode

### Technical Details
- **Major Focus**: Eval Criteria Evolver & Checkpoint Objectives — self-improving criteria and safety planning
- **PRs Merged**: [#1047](https://github.com/massgen/MassGen/pull/1047)
- **Contributors**: @ncrispino, @HenryQi and the MassGen team

---

## [0.1.72] - 2026-04-03

### Changed
- **Grok Backend Update** ([#1044](https://github.com/massgen/MassGen/pull/1044)): Updated Grok backend with latest improvements

### Added
- **Circuit Breaker Phase 2** ([#1038](https://github.com/massgen/MassGen/pull/1038)): LLM API circuit breaker extended to ChatCompletions, Response API, and Gemini backends (was Claude-only in v0.1.68); Gemini also handles 503 errors
- **Config Plumbing Smoke Tests** ([#1038](https://github.com/massgen/MassGen/pull/1038)): Smoke tests verify circuit breaker wiring and API call timing for all backends

### Fixed
- **Response API Timing** ([#1038](https://github.com/massgen/MassGen/pull/1038)): Added start/end API call timing to ResponseBackend non-MCP path

### Technical Details
- **Major Focus**: Circuit Breaker Phase 2 — rate limit protection across all major backends
- **PRs Merged**: [#1038](https://github.com/massgen/MassGen/pull/1038), [#1044](https://github.com/massgen/MassGen/pull/1044)
- **Contributors**: @amabito, @HenryQi, @ncrispino and the MassGen team

---

## [0.1.71] - 2026-04-01

### Changed
- **Better Evaluation Criteria**: Improved criteria generation for higher-quality, more opinionated output
- **System Prompt Tuning**: Adjusted system prompts for better agent performance across coordination rounds

### Fixed
- **Final Injection Fix**: Corrected injection behavior at the final stage
- **Eval Criteria GPT Pre-Collab Fix**: Resolved evaluation criteria issues with GPT models during pre-collaboration phase
- **Execution Trace Analyzer Launch Fix**: Trace analyzer now starts correctly
- **Trace Memory Fix**: Corrected memory handling in execution traces
- **Auto Round Memory Fix**: Fixed automatic round handling for memory

### Documentation, Configurations and Resources
- **Updated Log Analyzer Skill**: Updated `massgen/skills/massgen-log-analyzer/SKILL.md`
- **Updated Execution Trace Analyzer**: Updated `massgen/subagent_types/execution_trace_analyzer/SUBAGENT.md`

### Technical Details
- **Major Focus**: Stability and polish for v0.1.70's evaluation criteria system
- **Contributors**: @ncrispino, @HenryQi and the MassGen team

---

## [0.1.70] - 2026-03-30

### Added
- **Evaluation Criteria Redesign** ([#1035](https://github.com/massgen/MassGen/pull/1035)): Three-tier categorization (`primary`, `standard`, `stretch`) with anti-pattern definitions per criterion and aspiration statements
- **Improved Checklist-Gated Evaluation** ([#1035](https://github.com/massgen/MassGen/pull/1035)): Tighter iterative submission cycles — improved scoring, gap analysis, and improvement proposals drive more meaningful iteration before final voting
- **Fast Iteration Mode** ([#1035](https://github.com/massgen/MassGen/pull/1035)): Streamlined multi-round submission phases via `fast_iteration.yaml` config
- **WebUI Review Modal** ([#1035](https://github.com/massgen/MassGen/pull/1035)): Approve and comment on outputs directly in the browser when working in git
- **Background Trace Analysis** ([#1035](https://github.com/massgen/MassGen/pull/1035)): Execution trace analyzer starts automatically from round 2

### Changed
- **Improved Evaluation Criteria Generation** ([#1035](https://github.com/massgen/MassGen/pull/1035)): Criteria generation now produces opinionated, task-specific criteria with aspiration statements
- **Enhanced Workspace Cleanup** ([#1035](https://github.com/massgen/MassGen/pull/1035)): Improved isolation between rounds
- **Refined Per-Round Token Tracking** ([#1035](https://github.com/massgen/MassGen/pull/1035)): More accurate per-round token usage tracking

### Fixed
- **Subagent Fixes** ([#1035](https://github.com/massgen/MassGen/pull/1035)): General fixes for subagent behavior and path issues

### Documentation, Configurations and Resources
- **Updated Coordination Workflow**: Updated `docs/modules/coordination_workflow.md` with checklist-gated workflow documentation
- **Updated Subagents Guide**: Updated `docs/modules/subagents.md` with background trace analysis
- **New Injection Guide**: New `docs/modules/injection.md` for injection documentation
- **Updated Concepts Guide**: Updated `docs/source/user_guide/concepts.rst` with evaluation criteria redesign
- **Updated YAML Schema**: Updated `docs/source/reference/yaml_schema.rst` with new configuration options
- **Updated MassGen Skill**: Updated `massgen/skills/massgen/SKILL.md` with opinionated criteria format
- **Updated Criteria Guide**: Updated `massgen/skills/massgen/references/criteria_guide.md` with three-tier system
- **New Config**: New `massgen/configs/features/fast_iteration.yaml` for fast iteration mode

### Technical Details
- **Major Focus**: Evaluation Criteria Redesign — three-tier categorization with anti-patterns and checklist-gated workflow
- **PRs Merged**: [#1035](https://github.com/massgen/MassGen/pull/1035)
- **Contributors**: @ncrispino, @HenryQi and the MassGen team

## [0.1.69] - 2026-03-27

### Added
- **WebUI Automation Auto-Start** ([#1032](https://github.com/massgen/MassGen/pull/1032)): Automation mode now auto-starts coordination runs without browser interaction — open the URL at any point to monitor progress, even mid-run
- **MassGen Skill Redesign** ([#1032](https://github.com/massgen/MassGen/pull/1032)): Increased usability and integration with the WebUI; skill now launches the WebUI for live session tracking
- **Quickstart Wizard Rework** ([#1032](https://github.com/massgen/MassGen/pull/1032)): New WelcomeStep, SkillsStep, ApiKeyStep redesign, DockerStep expansion, and SetupModeStep restructure for smoother onboarding
- **Workspace Browser Expansion** ([#1032](https://github.com/massgen/MassGen/pull/1032)): WorkspaceModal and improved workspace connection

### Changed
- **Flexible Evaluation Criteria Fields** ([#1032](https://github.com/massgen/MassGen/pull/1032)): Criteria JSON now accepts `description` or `name` as alternatives to `text` field for more flexible criterion authoring
- **Automatic Config Resolution** ([#1032](https://github.com/massgen/MassGen/pull/1032)): Automation mode auto-resolves config when none is specified (same as CLI without `--web`)

### Fixed
- **Web Automation Skill Lifecycle** ([#1032](https://github.com/massgen/MassGen/pull/1032)): Web automation now correctly auto-ends when a skill completes
- **WebUI Version Default** ([#1032](https://github.com/massgen/MassGen/pull/1032)): Fixed WebUI defaulting to v2

### Documentation, Configurations and Resources
- **Updated WebUI Guide**: Updated `docs/source/user_guide/webui.rst` with automation mode flags, auto-start behavior, and interactive examples
- **MassGen Skill**: Updated `massgen/skills/massgen/SKILL.md` with WebUI wrapper and monitoring instructions
- **Advanced Workflows**: Updated `massgen/skills/massgen/references/advanced_workflows.md` with skill WebUI integration patterns
- **Config Setup**: Updated `massgen/skills/massgen/references/config_setup.md` with updated quickstart guidance

### Technical Details
- **Major Focus**: WebUI Automation & Improved Skill — seamless integration between the skill workflow and WebUI monitoring
- **PRs Merged**: [#1032](https://github.com/massgen/MassGen/pull/1032)
- **Contributors**: @ncrispino, @HenryQi and the MassGen team

## [0.1.68] - 2026-03-25

### Added
- **Checkpoint Coordination Mode** ([#1028](https://github.com/massgen/MassGen/pull/1028)): New delegator pattern — main agent plans solo then calls `checkpoint()` to delegate execution to fresh agent instances with clean backends and cloned workspaces
- **WebUI Checkpoint Support** ([#1028](https://github.com/massgen/MassGen/pull/1028)): Checkpoint mode display integrated into the modernized WebUI
- **LLM API Circuit Breaker** ([#1024](https://github.com/massgen/MassGen/pull/1024)): Automatic 429 rate limit handling with circuit breaker pattern for Claude backend

### Fixed
- **LiteLLM Supply Chain Fix** ([#1025](https://github.com/massgen/MassGen/pull/1025)): Pinned litellm<=1.82.6 and committed uv.lock to prevent dependency attacks

### Technical Details
- **Major Focus**: Checkpoint Mode — delegator pattern for multi-agent coordination
- **PRs Merged**: [#1028](https://github.com/massgen/MassGen/pull/1028), [#1025](https://github.com/massgen/MassGen/pull/1025), [#1024](https://github.com/massgen/MassGen/pull/1024)
- **Contributors**: @ncrispino, @amabito, @HenryQi and the MassGen team

## [0.1.67] - 2026-03-23

### Added
- **Modernized WebUI** ([#1016](https://github.com/massgen/MassGen/pull/1016)): Complete UI redesign with inline final answers, keyboard shortcuts, and Zustand state management (message, mode, tile, agent, theme stores)
- **RoundBudgetGuardHook** ([#1013](https://github.com/massgen/MassGen/pull/1013)): Per-round cost enforcement with configurable warning thresholds (50%, 75%, 90%) and graceful termination on budget overrun
- **Unified Pre-Collab Phases** ([#1016](https://github.com/massgen/MassGen/pull/1016)): Persona generation, evaluation criteria, and prompt improvement now run in parallel with unified TUI batch display
- **Regression Guard** ([#1016](https://github.com/massgen/MassGen/pull/1016)): Blind A/B verification subagent before submitting revisions to catch silent regressions

### Technical Details
- **Major Focus**: Modernized WebUI and quality improvements
- **PRs Merged**: [#1016](https://github.com/massgen/MassGen/pull/1016), [#1013](https://github.com/massgen/MassGen/pull/1013)
- **Contributors**: @ncrispino, @amabito, @HenryQi and the MassGen team

## [0.1.66] - 2026-03-20

### Added
- **Step Mode** ([#1011](https://github.com/massgen/MassGen/pull/1011)): New `--step` CLI flag runs a single agent for one iteration then exits, loading/writing state from a session directory — building block for external orchestrators like massgen-refinery
- **Console Text Sanitization** ([#1010](https://github.com/massgen/MassGen/pull/1010)): Reusable `sanitize_console_text` utility for safe TUI and logger rendering

### Fixed
- **Codex Windows UTF-8** ([#1010](https://github.com/massgen/MassGen/pull/1010)): Ensure UTF-8 encoding when writing files in Codex backend
- **TUI Event Pipeline** ([#1010](https://github.com/massgen/MassGen/pull/1010)): Console safety features for logger and text sanitization in event pipeline

### Technical Details
- **Major Focus**: Step Mode — building block for external orchestrators
- **PRs Merged**: [#1011](https://github.com/massgen/MassGen/pull/1011), [#1010](https://github.com/massgen/MassGen/pull/1010)
- **Contributors**: @ncrispino, @praneeth999, @HenryQi and the MassGen team

## [0.1.65] - 2026-03-18

### Added
- **Quality Server** ([#1007](https://github.com/massgen/MassGen/pull/1007)): Standalone `massgen_quality_tools` MCP server with session-based checklist evaluation, configurable scoring thresholds, improvement proposals, and coverage validation
- **Workflow Server** ([#1007](https://github.com/massgen/MassGen/pull/1007)): Standalone `massgen_workflow_tools` MCP server with multi-round answer submission, automatic deliverable snapshots, and vote support
- **Media Server** ([#1007](https://github.com/massgen/MassGen/pull/1007)): Standalone `massgen_media_tools` MCP server with image/video/audio generation and critical-first media analysis

### Technical Details
- **Major Focus**: MassGen Refinery Plugin — standalone MCP servers for Claude Code
- **PRs Merged**: [#1007](https://github.com/massgen/MassGen/pull/1007)
- **Contributors**: @ncrispino, @HenryQi and the MassGen team

## [0.1.64] - 2026-03-16

### Added
- **Gemini CLI Backend** ([#999](https://github.com/massgen/MassGen/pull/999), [#952](https://github.com/massgen/MassGen/issues/952)): New subprocess-based backend for Google's Gemini CLI with session persistence, MCP tools via `.gemini/settings.json`, and Docker support
- **WebSocket Mode** ([#990](https://github.com/massgen/MassGen/pull/990)): Persistent WebSocket transport for OpenAI Response API with auto-reconnection and real-time event streaming
- **Execution Trace Analyzer** ([#1002](https://github.com/massgen/MassGen/pull/1002)): New subagent type for mechanistic analysis of agent execution traces with 7-dimension evaluation framework
- **Copilot Docker Mode** ([#999](https://github.com/massgen/MassGen/pull/999)): Containerized tool execution for Copilot backend with sudo and network configuration

### Fixed
- **Response API Duplicates** ([#1000](https://github.com/massgen/MassGen/pull/1000)): Prevent duplicate item errors in recursive tool loops

### Technical Details
- **Major Focus**: Gemini CLI Backend
- **PRs Merged**: [#999](https://github.com/massgen/MassGen/pull/999), [#990](https://github.com/massgen/MassGen/pull/990), [#1002](https://github.com/massgen/MassGen/pull/1002), [#1000](https://github.com/massgen/MassGen/pull/1000)
- **Contributors**: @praneeth999, @ncrispino, @HenryQi, @db-ol and the MassGen team

## [0.1.63] - 2026-03-13

### Added
- **Ensemble Pattern Defaults** ([#996](https://github.com/massgen/MassGen/pull/996)): `disable_injection` and `defer_voting_until_all_answered` now default to true for ensemble-style subagent orchestration
- **Transformation Pressure** ([#996](https://github.com/massgen/MassGen/pull/996)): Round evaluator applies transformation pressure to push agents toward meaningful structural changes
- **Success Contracts** ([#996](https://github.com/massgen/MassGen/pull/996)): Explicit quality gates that agents must satisfy before the round evaluator allows convergence

### Changed
- **Lighter Refinement** ([#996](https://github.com/massgen/MassGen/pull/996)): Subagents use lighter refinement prompts to reduce token overhead and latency
- **Killed Agent Handling** ([#996](https://github.com/massgen/MassGen/pull/996)): Graceful management of agents that time out or fail mid-round
- **Verification Replay** ([#996](https://github.com/massgen/MassGen/pull/996)): Evaluation consistency across rounds via replayed verification context

### Fixed
- **Timeout Fallback** ([#996](https://github.com/massgen/MassGen/pull/996)): More robust coordination when agents hit timeout boundaries

### Technical Details
- **Major Focus**: Ensemble & Contracts — ensemble pattern defaults, transformation pressure, success contracts, lighter refinement
- **PRs Merged**: [#996](https://github.com/massgen/MassGen/pull/996) (dev/v0.1.62-p1)
- **Contributors**: @ncrispino, @HenryQi and the MassGen team

## [0.1.62] - 2026-03-11

### Added
- **MassGen Skill** ([#992](https://github.com/massgen/MassGen/pull/992)): New general-purpose multi-agent skill with 4 modes (general, evaluate, plan, spec) for Claude Code and other AI agents
- **Session Viewer** ([#992](https://github.com/massgen/MassGen/pull/992)): New `massgen viewer` command for real-time observation of automation sessions with interactive session picker and web mode
- **Headless Quickstart** ([#992](https://github.com/massgen/MassGen/pull/992)): Non-interactive setup via `--quickstart --headless` for CI/CD integration
- **Web Quickstart** ([#992](https://github.com/massgen/MassGen/pull/992)): Browser-based setup flow via `--web-quickstart`
- **Skill Auto-Sync** ([#992](https://github.com/massgen/MassGen/pull/992)): GitHub Actions workflow to auto-sync MassGen Skill to separate repository for easy installation

### Changed
- **Claude Code Backend** ([#992](https://github.com/massgen/MassGen/pull/992)): Background task execution support and SDK MCP integration
- **Codex Backend** ([#992](https://github.com/massgen/MassGen/pull/992)): Native filesystem access, JSONL event streaming, and MCP tool support
- **Copilot Model Discovery** ([#992](https://github.com/massgen/MassGen/pull/992)): Runtime model fetching with metadata caching
- **Planning & Evaluation** ([#992](https://github.com/massgen/MassGen/pull/992)): Better planning prompts with thoroughness support, removed should/could criteria to reduce output similarity
- **CLI Enhancements** ([#992](https://github.com/massgen/MassGen/pull/992)): `--print-backends` table, viewer subcommand, multi-agent quickstart via `--quickstart-agent`

### Fixed
- **Skill Viewer** ([#992](https://github.com/massgen/MassGen/pull/992)): Fixed skill viewer display and added convenience shell script
- **Correctness Prompts** ([#992](https://github.com/massgen/MassGen/pull/992)): Updated correctness prompts for improved accuracy

### Technical Details
- **Major Focus**: MassGen Skill & Viewer — general-purpose skill, session observation, backend improvements
- **PRs Merged**: [#992](https://github.com/massgen/MassGen/pull/992) (evaluator-skill)
- **Contributors**: @ncrispino (6 commits), @HenryQi (2 commits) and the MassGen team

## [0.1.61] - 2026-03-09

### Added
- **Round Evaluator Subagent Type** ([#986](https://github.com/massgen/MassGen/pull/986)): New `round_evaluator` subagent type that delegates evaluation to specialized evaluator subagents for deeper quality assessment
- **`round_evaluator_example.yaml` Config** ([#986](https://github.com/massgen/MassGen/pull/986)): New example config for the round evaluator paradigm

### Changed
- **Orchestrator Refactoring** ([#986](https://github.com/massgen/MassGen/pull/986)): Major orchestrator refactoring (+1,189 lines) to support the round evaluation workflow
- **Evaluation Prompts** ([#986](https://github.com/massgen/MassGen/pull/986)): Improved evaluation prompts for clearer, more actionable feedback with task plan injection
- **Simplified Config** ([#986](https://github.com/massgen/MassGen/pull/986)): Simplified config handling for evaluation parameters
- **SUBAGENT.md Generality** ([#986](https://github.com/massgen/MassGen/pull/986)): Improved SUBAGENT.md for broader subagent compatibility

### Fixed
- **Session Resumption** ([#986](https://github.com/massgen/MassGen/pull/986)): Fixed resumption from already-resumed logs
- **Round Evaluation Prompts** ([#986](https://github.com/massgen/MassGen/pull/986)): Improved round evaluation prompt clarity

### Technical Details
- **Major Focus**: Round evaluator paradigm — delegated evaluation to specialized subagents
- **PRs Merged**: [#986](https://github.com/massgen/MassGen/pull/986) (improve_verification_time)
- **Contributors**: @ncrispino (8 commits), @HenryQi (1 commit)

## [0.1.60] - 2026-03-06

### Added
- **read_media Rewrite** ([#978](https://github.com/massgen/MassGen/pull/978)): Rewritten with clearer schema, better error handling, and improved naming
- **MediaCallLedgerHook** ([#978](https://github.com/massgen/MassGen/pull/978)): New `MediaCallLedgerHook` for tracking read/generate media tool calls via the hook framework
- **GPT-5.4 Support** ([#978](https://github.com/massgen/MassGen/pull/978)): New default OpenAI flagship model added to the model registry
- **Subagent Backend Inheritance** ([#978](https://github.com/massgen/MassGen/pull/978)): New `inherit_spawning_agent_backend` option — subagents automatically inherit the spawning agent's backend
- **Subagent Final Answer Strategy** ([#978](https://github.com/massgen/MassGen/pull/978)): New `final_answer_strategy` option for child orchestrator final-answer policy (winner_reuse, winner_present, synthesize)
- **Per-Agent Subagent Agents** ([#978](https://github.com/massgen/MassGen/pull/978)): Per-agent `subagent_agents` override and orchestrator config file support with robust JSON parsing

### Changed
- **Decomp Mode Cooperates with Checklist** ([#978](https://github.com/massgen/MassGen/pull/978)): Decomposition mode now cooperates with the checklist workflow for unified quality-gated subtask iteration
- **System Prompt Focus** ([#978](https://github.com/massgen/MassGen/pull/978)): Refocused system prompt on evaluating entire output quality
- **Verification Prompts** ([#978](https://github.com/massgen/MassGen/pull/978)): Improved verification_latest prompts for faster verification rounds

### Fixed
- **Checklist & Proposal Injections** ([#978](https://github.com/massgen/MassGen/pull/978)): Fixed proposal injection improvements for more reliable checklist behavior
- **Task Plan Refresh** ([#978](https://github.com/massgen/MassGen/pull/978)): Fixed task plan refresh during quality rounds
- **Codex Prompt Caching** ([#978](https://github.com/massgen/MassGen/pull/978)): Fixed prompt caching calculation for pricing accuracy
- **Skill Prefix Handling** ([#978](https://github.com/massgen/MassGen/pull/978)): Fixed skill prefix handling edge cases

### Technical Details
- **Major Focus**: Multimodal tools, subagent enhancements, GPT-5.4, decomp+checklist cooperation
- **PRs Merged**: [#978](https://github.com/massgen/MassGen/pull/978) (improve_verification_time)
- **Contributors**: @ncrispino (6 commits), @HenryQi (1 commit)

## [0.1.59] - 2026-03-04

### Added
- **Planning Improvements** ([#969](https://github.com/massgen/MassGen/pull/969)): Smarter quality rounds with improved planning
  - Auto-add improvements to task plan for better iteration tracking
  - Plan review enhancements for more thorough quality evaluation

- **Checklist & Evaluation Enhancements** ([#969](https://github.com/massgen/MassGen/pull/969)): More reliable evaluation pipeline
  - Better eval gen config for more accurate quality assessments
  - Checklist fixes for consistent behavior across rounds
  - Gemini tool name normalization for MCP compatibility (ease for MCP)

### Changed
- **Subagent Behavior** ([#969](https://github.com/massgen/MassGen/pull/969)): Adjusted subagent behavior and manager enhancements
  - Improved subagent coordination and task delegation
  - Docker skill write access fixes for containerized execution
- **Video Generation Skills** ([#969](https://github.com/massgen/MassGen/pull/969)): Adjusted video gen skill behavior
  - No fallback to animated on errors — fail cleanly instead
  - Video understanding criticality improvements
  - Impact metric restoration for quality assessment

### Fixed
- **Answer Anonymization** ([#969](https://github.com/massgen/MassGen/pull/969)): Fixed answer anonymization during evaluation
- **Quickstart & Tests** ([#969](https://github.com/massgen/MassGen/pull/969)): Updated quickstart flow and test suite
- **Plan & Docker Fixes** ([#969](https://github.com/massgen/MassGen/pull/969)): Small fixes for plan mode and Docker execution

### Technical Details
- **Major Focus**: Quality round improvements — planning, evaluation, subagents, media fixes
- **PRs Merged**: [#969](https://github.com/massgen/MassGen/pull/969) (improve_quality_rounds)
- **Contributors**: @ncrispino (7 commits), @HenryQi (1 commit)

## [0.1.58] - 2026-03-02

### Added
- **Comprehensive Multimodal Revamp**: Major expansion of multimodal generation and understanding capabilities
  - ElevenLabs TTS & STT ([#942](https://github.com/massgen/MassGen/issues/942)): High-quality voice synthesis and transcription via `generate_media` and `read_media` tools
  - Nano Banana 2 Image Generation ([#951](https://github.com/massgen/MassGen/issues/951)): New default image generation model with higher quality output
  - Grok Image/Video Generation: Grok multimedia generation support via xAI API
  - Media Generation Skills: New reusable skills for image, video, and audio generation workflows
  - Multi-Turn Image Editing: Continuation IDs for iterative image editing sessions

- **Nvidia NIM Backend** ([#962](https://github.com/massgen/MassGen/pull/962)): First-class provider integration for NVIDIA Inference Microservices
  - Support for NVIDIA-hosted models via NIM API
  - Full integration with MassGen's multi-agent coordination

- **Quality Rethinking Subagent** ([#964](https://github.com/massgen/MassGen/pull/964)): New `quality_rethinking` subagent type for targeted per-element craft improvements
  - Explicit improve/preserve listings in checklists
  - Better label refresh ordering for more coherent checklist updates

- **CLI Mode Flags**: New command-line flags mirroring TUI toggles
  - `--quick`, `--single-agent`, `--coordination-mode`, `--personas` flags
  - Plan mode accessible from command line

### Changed
- **Logging Architecture Refactor**: Fixed concurrent logging for parallel multi-agent execution with `LoggingSession` isolation
  - Each agent gets isolated logging context preventing log interleaving
- **Evaluation Criteria Defaults**: Sensible defaults for evaluation criteria when not explicitly specified
- **Checklist Label Refresh Ordering**: Improved ordering of checklist label refreshes for better coherence

### Fixed
- **Subagent Hardening** ([#964](https://github.com/massgen/MassGen/pull/964)): Better '@' parsing and error handling for multiple `submit_checklist` calls
  - Clearer subagent context and improved error messages
- **Pre-Collaboration Checklist**: Fixed checklist behavior before collaboration phase
- **Evaluation Criteria Defaults**: Fixed default handling for evaluation criteria

### Technical Details
- **Major Focus**: Multimodal revamp, Nvidia NIM backend, quality rethinking subagent, checklist improvements
- **PRs Merged**: [#962](https://github.com/massgen/MassGen/pull/962) (Nvidia NIM), [#964](https://github.com/massgen/MassGen/pull/964) (Subagent hardening)
- **Contributors**: @ncrispino (11 commits), @AbhimanyuAryan (1 commit)

## [0.1.57] - 2026-02-27

### Added
- **Subagent Delegation Protocol** ([#955](https://github.com/massgen/MassGen/pull/955), MAS-325): File-based delegation for container-to-host subagent spawning
  - `SubagentLaunchWatcher` polls shared delegation directory for request files
  - Atomic JSON-based `DelegationRequest`/`DelegationResponse` exchange protocol
  - Workspace path validation against allowlist for security
  - Cancel sentinel support for graceful subagent termination

- **Builder Subagent Type** ([#955](https://github.com/massgen/MassGen/pull/955)): New subagent for executing substantial pre-specified work with fresh context
  - Transformative redesigns, large artifact generation, complex multi-file rewrites
  - Prescriptive spec input with positive goals AND forbidden patterns (negative constraints)
  - Auto-triggered by checklist when transformative changes identified

- **Claude Code Reasoning Parameters** ([#955](https://github.com/massgen/MassGen/pull/955)): Updated SDK integration with new unified reasoning config
  - Migrated from deprecated `max_thinking_tokens` to `reasoning` config dict
  - Supports `type` (adaptive/enabled/disabled), `effort` (low/medium/high/max), `budget_tokens`
  - Backward compatible with legacy configurations

- **Substantiveness Tracking** ([#955](https://github.com/massgen/MassGen/pull/955)): Checklist captures specific planned changes to prevent satisficing
  - List format: `transformative`, `structural`, `incremental` items with descriptions
  - `decision_space_exhausted` flag for convergence signaling
  - Builder subagent suggestion when transformative changes identified
  - Novelty subagent injection when transformation count = 0 (plateau detection)

- **Diagnostic Report Gating** ([#955](https://github.com/massgen/MassGen/pull/955)): Optional quality gate requiring structured diagnostic reports
  - Validates report file existence, minimum length, and markdown format
  - Required sections: Failure Patterns, Root Causes, Goal Alignment

- **Verification Subdirectory for Scratch** ([#955](https://github.com/massgen/MassGen/pull/955)): Organized scratch work with verification subdirectory support

### Changed
- **Subagent Workspace Management** ([#955](https://github.com/massgen/MassGen/pull/955)): Auto-mounted parent workspace (read-only) by default via `include_parent_workspace`
  - Eliminates need for `context_paths: ["./"]` — subagents get parent workspace automatically
  - `context_paths` now for additional paths only (peer workspaces, external resources)
- **Evaluation Criteria** ([#955](https://github.com/massgen/MassGen/pull/955)): Cleaned up subagent paths and eval criteria organization
- **Memory Config Simplified** ([#955](https://github.com/massgen/MassGen/pull/955)): Simplified memory config option to only final presentation
- **Per-Agent Checklist Scoring** ([#955](https://github.com/massgen/MassGen/pull/955)): Support for evaluating multiple agents separately with format detection

### Fixed
- **Subagent Launch for Codex** ([#955](https://github.com/massgen/MassGen/pull/955)): Fixed codex backend subagent spawning
- **Subagent Timing** ([#955](https://github.com/massgen/MassGen/pull/955)): Improved synchronization and timeout handling
- **Subagent Temp Dir** ([#955](https://github.com/massgen/MassGen/pull/955)): Fixed temporary workspace directory support
- **Subagent Type Initialization** ([#955](https://github.com/massgen/MassGen/pull/955)): Fixed type definitions and initialization
- **Test Fixes** ([#955](https://github.com/massgen/MassGen/pull/955)): Various test updates for new features

### Documentation, Configurations and Resources
- New `massgen/subagent_types/builder/SUBAGENT.md` - Builder subagent type definition
- Updated `massgen/subagent_types/evaluator/SUBAGENT.md` - Enhanced evaluator guidance
- New `docs/modules/coordination_workflow.md` - End-to-end coordination lifecycle documentation
- Updated `docs/modules/subagents.md` - Delegation protocol and workspace management
- Updated `massgen/configs/BACKEND_CONFIGURATION.md` - Reasoning parameter documentation
- New `ROADMAP_v0.1.58.md` - Next release roadmap

### Technical Details
- **Major Focus**: Subagent delegation protocol, builder subagent, convergence improvements
- **PRs Merged**: [#955](https://github.com/massgen/MassGen/pull/955) (Delegation protocol, builder subagent, reasoning params, eval improvements)
- **Files Changed**: 68 files, +7348/-503 lines
- **New Tests**: `test_launch_watcher.py`, `test_launch_watcher_e2e.py`, `test_subagent_delegated_mode.py`, `test_round_resume.py`, `test_checklist_tools_server.py` (substantiveness), `test_write_mode_scratch.py`, `test_claude_code_skills_config.py`, `test_gepa_evaluation_flow.py`, `test_novelty_injection.py`
- **Contributors**: @ncrispino (8 commits), @HenryQi (2 commits)

## [0.1.56] - 2026-02-25

### Added
- **Critic Subagent** ([#945](https://github.com/massgen/MassGen/pull/945)): New subagent type for honest, unbiased quality assessment
  - Detects genuine vs incremental improvement across refinement rounds
  - First impression, quality ceiling assessment, incrementalism verdict, independent E-criterion scoring
  - Describes the 10/10 vision and distance to excellence
  - Complements existing subagent types (evaluator, explorer, researcher, novelty)

- **Spec Plan Mode** ([#945](https://github.com/massgen/MassGen/pull/945)): Formal requirements specification before execution
  - `plan_mode="spec"` for structured requirements gathering
  - Spec creation, approval modal, and execution pipeline
  - TUI spec mode state with dedicated mode bar support
  - Spec storage and changedoc integration

- **read_media Conversation Continuity** ([#945](https://github.com/massgen/MassGen/pull/945)): Follow-up conversations on supported media (image) via `continue_from` conversation_id
  - Multi-turn image analysis with severity parsing

- **ask_others Targeted Messaging** ([#937](https://github.com/massgen/MassGen/pull/937)): `target_agents` parameter for focused agent-to-agent communication
  - Validation and per-target response counting
  - Shadow-agent prompt improvements for prior work separation

- **Codex OAuth Login Fix** ([#937](https://github.com/massgen/MassGen/pull/937), MAS-322): Codex backend always available in WebUI regardless of OPENAI_API_KEY
  - OAuth authentication fix via `codex login`

- **Background Subagent Continuation** ([#945](https://github.com/massgen/MassGen/pull/945)): Non-blocking subagent task execution
  - Enhanced subagent state tracking and graceful cancellation

- **Docker Configuration Mounting** ([#945](https://github.com/massgen/MassGen/pull/945)): Claude and Codex configuration mounting options for Docker containers

### Changed
- **Evaluation Criteria Taxonomy** ([#945](https://github.com/massgen/MassGen/pull/945)): Updated from core/stretch to must/should/could tiers
- **Novelty Subagent Enhancement** ([#945](https://github.com/massgen/MassGen/pull/945)): Updated guidance for growth-oriented refinement
- **Multimodal Tool Configs** ([#945](https://github.com/massgen/MassGen/pull/945)): Updated text-to-image, text-to-speech, and text-to-video generation configs

### Fixed
- Test and spec reading fixes ([#945](https://github.com/massgen/MassGen/pull/945))
- Audio cleanup for future release stability ([#945](https://github.com/massgen/MassGen/pull/945))

### Documentation, Configurations and Resources
- New `massgen/subagent_types/critic/SUBAGENT.md` - Critic subagent type definition
- Updated `massgen/subagent_types/novelty/SUBAGENT.md` - Enhanced novelty guidance
- Updated `massgen/tool/_multimodal_tools/TOOL.md` - Audio multimodal documentation
- Updated `massgen/configs/features/background_subagent_example.yaml`
- Updated multimodal tool configs (text-to-image, text-to-speech, text-to-video)
- New `ROADMAP_v0.1.57.md` - Next release roadmap

### Technical Details
- **Major Focus**: Spec plan mode, targeted messaging, critic subagent
- **PRs Merged**: [#945](https://github.com/massgen/MassGen/pull/945) (Spec mode, critic subagent, audio multimodal), [#937](https://github.com/massgen/MassGen/pull/937) (Codex OAuth, ask_others targeting)
- **Files Changed**: 89 files, +8684/-1089 lines
- **New Tests**: 16 new test files covering spec execution, spec storage, spec approval modal, audio multimodal, read_media analysis/followup, refinement quality, and more
- **Contributors**: @HenryQi (3 commits), @MuL1ian (3 commits), and the MassGen team (4 commits)

## [0.1.55] - 2026-02-23

### Added
- **Specialized Subagent Types** ([#938](https://github.com/massgen/MassGen/pull/938)): Discovery-based system for specialized subagent roles via `SUBAGENT.md` frontmatter
  - Built-in types: evaluator (programmatic verification), explorer (investigation), researcher (deep analysis), novelty (breaks refinement plateaus)
  - TUI visualization for subagent roles

- **Dynamic Evaluation Criteria** ([#938](https://github.com/massgen/MassGen/pull/938)): GEPA-inspired task-specific evaluation criteria generation replacing static E1-E4 items
  - Domain-specific presets (persona, decomposition, evaluation, prompt, analysis)
  - Core/stretch categorization for smarter convergence off-ramps
  - Score scale 0-10
  - Config: `evaluation_criteria_generator`

- **Native Backend Image Routing** ([#938](https://github.com/massgen/MassGen/pull/938), MAS-300): `understand_image` routes to agent's own backend (Claude, Gemini, Grok, Claude Code, Codex) instead of always using OpenAI
  - Fallback to OpenAI for backends without `image_understanding` capability

- **Configurable Video Frame Extraction** ([#938](https://github.com/massgen/MassGen/pull/938)): Scene-based (PySceneDetect) or uniform extraction modes
  - `max_frames` cost guardrail (default 30, max 60)
  - Config: `multimodal_config.video`

- **Remotion Skill in Quickstart** ([#938](https://github.com/massgen/MassGen/pull/938)): Video generation/editing skill installed when selected during quickstart

### Changed
- **Checklist System Update** ([#938](https://github.com/massgen/MassGen/pull/938)): T-prefix to E-prefix naming, 0-100 to 0-10 score scale, `item_categories` for core/stretch, convergence off-ramp when all core items pass
- **Unified Pre-Collaboration** ([#938](https://github.com/massgen/MassGen/pull/938)): Persona generation, decomposition, and eval criteria generation unified as composable primitives

### Fixed
- Background subagent cancel name fix ([#938](https://github.com/massgen/MassGen/pull/938))
- Initial TUI sizing fix ([#938](https://github.com/massgen/MassGen/pull/938))

### Documentation
- New `docs/modules/composition.md` - Composable primitives, phase architecture, domain-specific checklist gates

### Technical Details
- **Major Focus**: Specialized subagent types, dynamic evaluation criteria, native image routing, video frame extraction
- **PRs Merged**: [#938](https://github.com/massgen/MassGen/pull/938) (Subagent roles / specialized types)
- **Contributors**: @ncrispino and the MassGen team

## [0.1.54] - 2026-02-20

### Added
- **Copilot SDK Backend** ([#862](https://github.com/massgen/MassGen/pull/862)): New `copilot` backend using `github-copilot-sdk`
  - Native MCP server integration and custom tool handling
  - Session management with cache invalidation
  - Auth via GitHub subscription

- **Subagent Runtime Messaging** ([#926](https://github.com/massgen/MassGen/pull/926)): New `send_message_to_subagent` tool to steer running background subagents mid-execution
  - Supports per-agent targeting within subagent orchestrators

- **Gemini 3.1 Pro Support** ([#926](https://github.com/massgen/MassGen/pull/926), MAS-312): `gemini-3.1-pro-preview` model added to capabilities registry

- **Per-Agent Injection Targeting** ([#926](https://github.com/massgen/MassGen/pull/926)): Injections can target specific agents or broadcast to all

### Changed
- **MCP Hooks Improvements** ([#926](https://github.com/massgen/MassGen/pull/926)): Hook middleware for subagent MCP servers, `InjectionDeliveryStatus` enum, hook-dir argument for PostToolUse injection
- **Type Annotation Modernization** ([#926](https://github.com/massgen/MassGen/pull/926)): Codebase-wide migration from `typing.Dict/List/Optional/Union` to modern `dict/list/X | None` syntax

### Fixed
- MCP hooks issue fix ([#926](https://github.com/massgen/MassGen/pull/926))
- Subagent message sending fix ([#926](https://github.com/massgen/MassGen/pull/926))
- fstmcp version fix ([#920](https://github.com/massgen/MassGen/pull/920))

### Technical Details
- **Major Focus**: Subagent runtime messaging, Copilot SDK backend, Gemini 3.1 Pro support
- **PRs Merged**: [#862](https://github.com/massgen/MassGen/pull/862) (Copilot SDK backend), [#926](https://github.com/massgen/MassGen/pull/926) (Subagent messaging), [#921](https://github.com/massgen/MassGen/pull/921) (Cloud infra research), [#920](https://github.com/massgen/MassGen/pull/920) (Minor fixes)
- **Contributors**: @ncrispino and the MassGen team

## [0.1.53] - 2026-02-18

### Added
- **Background Tool Execution** ([#917](https://github.com/massgen/MassGen/pull/917)): Non-blocking lifecycle tools for long-running work
  - `start_background_tool`, `get_background_tool_status`, `get_background_tool_result`, `wait_for_background_tool`, `cancel_background_tool`, `list_background_tools`
  - Compatible with custom tools and MCP server tools

- **Planning Task Verification** ([#917](https://github.com/massgen/MassGen/pull/917)): Tasks now require `verification` and `verification_method` fields by default
  - `--no-require-verification` flag to opt out
  - Framework-injected tasks exempt from verification requirements

- **TUI Background Job Indicators** ([#917](https://github.com/massgen/MassGen/pull/917)): Agent status ribbon with background job indicators
  - Background tasks modal with lifecycle controls

- **Subagent Infrastructure** ([#917](https://github.com/massgen/MassGen/pull/917)): Groundwork for specialized subagent types
  - Evaluator and Explorer type definitions via `SUBAGENT.md` frontmatter

### Changed
- **Tool Argument Normalization** ([#917](https://github.com/massgen/MassGen/pull/917)): Consistent argument handling across backends

### Fixed
- Task plan verification improvements
- Codex reasoning config alignment

### Technical Details
- **Major Focus**: Background tool execution, planning verification, TUI background indicators
- **PRs Merged**: [#917](https://github.com/massgen/MassGen/pull/917) (Background tools & subagent infrastructure)
- **Contributors**: @ncrispino and the MassGen team

## [0.1.52] - 2026-02-16

### Added
- **Dedicated Final Answer Modal** ([#901](https://github.com/massgen/MassGen/pull/901)): Tabbed modal with Answer tab (markdown content, post-evaluation, and file list) and Workspace/Review Changes tab (diff review)
  - Trophy header with agent identity and model name
  - Approve/Reject/Cancel action bar with rework controls for iteration

- **Substantive Gate** ([#901](https://github.com/massgen/MassGen/pull/901)): Quality gate preventing coordination from continuing with only incremental changes
  - Tracks `transformative`/`structural`/`incremental` classification
  - Detects `decision_space_exhausted` for convergence
  - Config: `require_substantiveness: true` (mandatory in checklist)

- **Novelty Injection** ([#901](https://github.com/massgen/MassGen/pull/901)): Creative pressure injection when agents converge or stall
  - Levels: `none` (default), `gentle`, `moderate`, `aggressive`
  - Intensifies after restarts
  - Config: `novelty_injection` in coordination section

- **Agent Identity & Versioning** ([#901](https://github.com/massgen/MassGen/pull/901)): Unique agent identity with versioned answer labels (e.g., `agent1.2`)
  - `answer_label_mapping` for provenance tracking

- **Subagent Evaluation Infrastructure** ([#901](https://github.com/massgen/MassGen/pull/901)): Foundation for delegating evaluation to spawned subagent instances

### Changed
- **First Answer Non-Restart** ([#901](https://github.com/massgen/MassGen/pull/901)): First answer from each agent no longer triggers automatic restarts even if quality checks fail, enabling more natural coordination flow

### Fixed
- Approved/rejected state display in final answer card
- Auto-open workspace behavior
- Final answer view in main timeline
- Tool spacing in final card

### Documentation, Configurations and Resources
- **Substantive Gate Config**: New `require_substantiveness` YAML parameter (mandatory in checklist)
- **Novelty Injection Config**: New `novelty_injection` parameter in coordination section (`none`/`gentle`/`moderate`/`aggressive`)

### Technical Details
- **Major Focus**: Final answer modal redesign, substantive gate, novelty injection, agent identity versioning
- **PRs Merged**: [#901](https://github.com/massgen/MassGen/pull/901) (Final answer improvements)
- **Contributors**: @ncrispino and the MassGen team

## [0.1.51] - 2026-02-13

### Added
- **Change Documents (Changedoc)** ([#896](https://github.com/massgen/MassGen/pull/896)): Decision journals agents write in `tasks/changedoc.md` during coordination, capturing decision provenance, rationale, and code traceability
  - Observation context: changedocs passed to other agents in `<changedoc>` tags for shared decision awareness
  - Config: `enable_changedoc: true` (default on)

- **Changedoc-Anchored Evaluation Checklist** ([#896](https://github.com/massgen/MassGen/pull/896)): 5 changedoc-specific checklist items for structured quality evaluation
  - Decision Completeness, Rationale Quality, Traceability, Output Quality, Novel Elements

- **Checklist Gap Report** ([#896](https://github.com/massgen/MassGen/pull/896)): Mandatory structured gap analysis before verdict
  - Config: `checklist_require_gap_report: true` (default on)

- **Drift Conflict Policy**: Configurable handling of target-file drift when applying isolated changes
  - `drift_conflict_policy: skip|prefer_presenter|fail`

- **Scratch Directory in Worktrees**: `.massgen_scratch/` for agent temporary files, git-excluded

- **CLI `--cwd-context` Flag**: Inject CWD into context paths — `ro`/`read` for read-only, `rw`/`write` for write access
  - Equivalent to `Ctrl+P` in TUI

- **Final Presentation Matrix**: Deterministic decision matrix for final presentation path selection

### Changed
- **Review Modal Improvements**: Multi-context, multi-file diff visualization with critique capabilities

- **Mode Bar Responsive Labels**: Compact labels adapting to terminal width

### Fixed
- Final presentation fallback for empty presentations
- Task execution timing fixes

### Documentation, Configurations and Resources
- **Changedoc System Prompt Sections**: New `<changedoc>` observation context blocks in agent system prompts
- **Checklist Gap Report Config**: New `checklist_require_gap_report` YAML parameter (default: `true`)
- **Drift Conflict Policy Config**: New `drift_conflict_policy` YAML parameter (`skip`/`prefer_presenter`/`fail`)
- **Scratch Directory Convention**: `.massgen_scratch/` added to `.gitignore` in worktrees

### Technical Details
- **Major Focus**: Change documents for multi-agent coordination traceability, changedoc-anchored evaluation checklists
- **PRs Merged**: [#896](https://github.com/massgen/MassGen/pull/896) (Changedoc system), even_execute_time branch
- **Contributors**: @ncrispino and the MassGen team

## [0.1.50] - 2026-02-11

### Added
- **Chunked Plan Execution** ([#877](https://github.com/massgen/MassGen/pull/877)): Plans now divided into chunks (e.g., `C01_foundation`) and executed one chunk at a time with progress checkpoints
  - Chunk browsing in TUI with chunk-level progress tracking
  - Frozen plan snapshots preserve original plan state during execution
  - `target_steps` and `target_chunks` parameters for plan sizing
  - Dynamic mode for adaptive plan depth controls

- **Iterative Planning Review Modal** ([#877](https://github.com/massgen/MassGen/pull/877)): New modal with Continue Planning / Quick Edit / Finalize Plan options
  - Allows plan iteration before execution begins
  - Quick edit for inline plan adjustments

- **Skill Lifecycle Management** ([#878](https://github.com/massgen/MassGen/pull/878)): New lifecycle modes (`create_or_update`, `create_new`, `consolidate`) for evolving skills
  - Skill organizer for merging overlapping skills into consolidated workflows
  - `SKILL_REGISTRY.md` routing guide for skill discovery and selection
  - Lifecycle mode selection during skill creation

- **Previous-Session Skills** ([#878](https://github.com/massgen/MassGen/pull/878)): Load evolving skills from past run logs with `load_previous_session_skills` config
  - Automatic skill discovery from previous session log directories

- **Local Skills MCP** ([#878](https://github.com/massgen/MassGen/pull/878)): New MCP tool for skill list/read access in Docker/local execution contexts
  - Enables skill access without filesystem tools

### Changed
- **Worktree Improvements** ([#877](https://github.com/massgen/MassGen/pull/877)): Branch accumulation across rounds, cross-agent diff visibility via `generate_branch_summaries()`, orphan cleanup
  - Branches accumulate across coordination rounds instead of being recreated
  - Other agents can see diffs from worktree branches via branch summaries

- **Responsive TUI Mode Bar** ([#877](https://github.com/massgen/MassGen/pull/877)): Vertical/horizontal adaptive layout with compact labels on narrow terminals

- **TUI Homescreen & Theming** ([#877](https://github.com/massgen/MassGen/pull/877)): Improved welcome screen layout, CSS refinements, palette updates for light/dark themes

- **Skills Modal** ([#878](https://github.com/massgen/MassGen/pull/878)): Source grouping (builtin/project/user/previous_session), quick actions (Enable All/Disable All)

- **Plan Depth Controls** ([#877](https://github.com/massgen/MassGen/pull/877)): Dynamic mode, `target_steps`/`target_chunks` parameters for plan sizing

### Fixed
- **Test Fixes** ([#877](https://github.com/massgen/MassGen/pull/877)): Fixed hooks, Docker mounts, and snapshot tests across the test suite

### Technical Details
- **Major Focus**: Chunked plan execution for safer long-form task completion, skill lifecycle management with consolidation
- **PRs Merged**: [#877](https://github.com/massgen/MassGen/pull/877) (Chunk planning mode), [#878](https://github.com/massgen/MassGen/pull/878) (Improve skill handling)
- **Contributors**: @ncrispino and the MassGen team

## [0.1.49] - 2026-02-09

### Added
- **Log Analysis Mode in TUI** ([#869](https://github.com/massgen/MassGen/pull/869)): New "Analyzing" state in the TUI mode bar for in-app run analysis
  - Mode bar cycle: Normal → Planning → Executing → Analyzing
  - Browse and select log directories and turns directly in the TUI
  - Configurable analysis profiles for different analysis depths
  - Empty submit in analysis mode runs default analysis on selected target

- **Fairness Gate for Coordination** ([#869](https://github.com/massgen/MassGen/pull/869)): Prevents fast agents from dominating coordination rounds
  - Configurable `fairness_lead_cap_answers` to limit how far ahead one agent can get
  - `max_midstream_injections_per_round` to control injection frequency
  - Ensures balanced participation across agents of different speeds

- **Checklist Voting Tool** ([#869](https://github.com/massgen/MassGen/pull/869)): New `checklist_tools_server.py` MCP server for structured quality evaluation
  - Binary pass/fail scoring for objective quality assessment
  - Structured checklist-based evaluation replacing subjective voting

- **Automated Testing Infrastructure** ([#869](https://github.com/massgen/MassGen/pull/869)): CI/CD workflow (`tests.yml`), SVG snapshot baselines, testing strategy spec, 16+ new test files
  - GitHub Actions CI pipeline for automated test execution
  - SVG snapshot baseline testing for TUI visual regression
  - Comprehensive testing strategy specification

- **Skills Modal in TUI** ([#869](https://github.com/massgen/MassGen/pull/869)): New modal for discovering and toggling skills in interactive mode
  - `skills_modals.py` for skill discovery and management in TUI

- **Docker Overlay Images** ([#869](https://github.com/massgen/MassGen/pull/869)): `Dockerfile.overlay` and build script for Agent Browser and OpenSkills integration

### Changed
- **Persona Easing in TUI Mode Bar** ([#869](https://github.com/massgen/MassGen/pull/869)): Persona easing toggle now accessible from the TUI mode bar
- **Improved Decomposition Prompts** ([#869](https://github.com/massgen/MassGen/pull/869)): Better hook injection for non-hook backends
- **Enhanced System Prompt Sections** ([#869](https://github.com/massgen/MassGen/pull/869)): Project instructions discovery and checklist evaluation blocks
- **Expanded Skills Installer** ([#869](https://github.com/massgen/MassGen/pull/869)): Playwright, Agent Browser, and OpenSkills support
- **Native Codex & Claude Code Skills** ([#869](https://github.com/massgen/MassGen/pull/869)): Direct skill integration for both backends

### Fixed
- **Shadow Agent Chunk Type Comparison** ([#861](https://github.com/massgen/MassGen/pull/861)): Fixed "[No response generated]" errors caused by incorrect chunk type comparison
- **Round Banner Timing** ([#869](https://github.com/massgen/MassGen/pull/869)): Round banner no longer appears before final answer is locked
- **Hook Injection for Non-Hook Backends** ([#869](https://github.com/massgen/MassGen/pull/869)): Corrected decomposition prompt injection for backends without native hook support
- **Final Answer Lock Responsiveness** ([#869](https://github.com/massgen/MassGen/pull/869)): Improved lock timing and reduced hover lag
- **Multiple Test Failures** ([#869](https://github.com/massgen/MassGen/pull/869)): Fixed hooks, persona easing, Docker mounts, and snapshot tests

### Documentation, Configurations and Resources
- **Testing Strategy**: New `docs/modules/testing.md` with testing architecture and CI gates
- **SVG Snapshots**: Baseline snapshots in `massgen/tests/snapshot_tests/`
- **CI/CD Pipeline**: `.github/workflows/tests.yml` for automated testing

### Technical Details
- **Major Focus**: Coordination quality improvements (log analysis TUI, fairness gate, checklist voting), automated testing infrastructure
- **PRs Merged**: [#869](https://github.com/massgen/MassGen/pull/869) (Automate testing), [#861](https://github.com/massgen/MassGen/pull/861) (Shadow agent fix)
- **Files Modified**:
  - New: `massgen/mcp_tools/servers/checklist_tools_server.py`, `massgen/frontend/displays/textual/widgets/modals/skills_modals.py`
  - Modified: `massgen/orchestrator.py` (fairness gate), `massgen/persona_generator.py` (easing), `massgen/frontend/displays/textual_widgets/mode_bar.py` (analysis mode)
  - Infrastructure: `.github/workflows/tests.yml`, `Dockerfile.overlay`, `massgen/tests/` (16+ new test files)
- **Contributors**: @ncrispino, @MuL1ian, and the MassGen team

## [0.1.48] - 2026-02-06

### Added
- **Decomposition Coordination Mode** ([#858](https://github.com/massgen/MassGen/pull/858)): New coordination mode that decomposes tasks into subtasks assigned to individual agents
  - Task decomposer with presenter agent role for final synthesis
  - TUI mode bar toggle, subtask assignment display, and generation modals
  - Quickstart wizard integration for decomposition mode selection

- **Worktree Isolation** ([#857](https://github.com/massgen/MassGen/pull/857)): Git worktree-based isolation for agent file writes with review workflow
  - New `write_mode` config parameter (`auto`/`worktree`/`isolated`/`legacy`)
  - `IsolationContextManager` for per-round worktree creation with `.massgen_scratch/` directories
  - `ChangeApplier` and review modal for approving/rejecting changes before applying to original paths
  - `WorktreeManager` and `ShadowRepo` infrastructure for git and non-git directories
  - Deprecation of `use_two_tier_workspace` in favor of `write_mode`

- **Stop Tool** ([#858](https://github.com/massgen/MassGen/pull/858)): New tool enabling agents to signal completion and exit workflows

- **Global Answer Limits** ([#858](https://github.com/massgen/MassGen/pull/858)): Orchestrator-level `max_answers` config alongside existing per-agent controls

### Changed
- **Quickstart Wizard Docker Setup** ([#857](https://github.com/massgen/MassGen/pull/857)): Docker setup step integrated into quickstart wizard when Docker mode is selected, with animated pull progress and real-time stdout streaming

- **Codex Backend** ([#858](https://github.com/massgen/MassGen/pull/858)): Default model updated from `gpt-5.2-codex` to `gpt-5.3-codex`

### Fixed
- **Light Theme Visibility** ([#857](https://github.com/massgen/MassGen/pull/857)): Fixed invisible mode bar underlines, separator lines, and toast notifications in light theme with new semantic CSS variables
- **Subagent Timeout** ([#857](https://github.com/massgen/MassGen/pull/857)): Added timeout exemption for subagent-related MCP tools (`spawn_subagents`, `get_subagent_status`, `cancel_subagents`) that manage their own timeouts
- **Post-evaluation Restarts** ([#857](https://github.com/massgen/MassGen/pull/857)): Disabled `max_orchestration_restarts` in quickstart defaults to prevent TUI crash on restart

### Documentation, Configurations and Resources
- **Agent Workspaces Guide**: New `docs/source/user_guide/agent_workspaces.rst` for worktree isolation workflow
- **Worktrees Module**: New `docs/modules/worktrees.md` with integration examples
- **Decomposition Configuration**: Updated `docs/source/reference/yaml_schema.rst`, `configuration.rst`, and `running-massgen.rst` with decomposition mode examples
- **Backends Guide**: Updated `docs/source/user_guide/backends.rst` with Codex model update
- **Capabilities Registry**: Updated `massgen/backend/capabilities.py` with `gpt-5.3-codex`

### Technical Details
- **Major Focus**: Decomposition coordination mode, worktree isolation for file writes, quickstart improvements
- **Files Modified**:
  - Orchestrator: `massgen/orchestrator.py` (decomposition + worktree isolation logic)
  - New: `massgen/task_decomposer.py`, `massgen/infrastructure/worktree_manager.py`, `massgen/infrastructure/shadow_repo.py`
  - New: `massgen/filesystem_manager/_isolation_context_manager.py`, `massgen/filesystem_manager/_change_applier.py`
  - New: `massgen/frontend/displays/textual/widgets/modals/review_modal.py`, `massgen/frontend/displays/textual/widgets/modals/input_modals.py`
  - TUI: Mode bar decomposition toggle, subagent decomposition display, quickstart wizard Docker step
  - Docs: `docs/source/user_guide/agent_workspaces.rst`, `docs/modules/worktrees.md`
- **Dependencies**: Added `gitpython`
- **Contributors**: @ncrispino and the MassGen team

## [0.1.47] - 2026-02-04

### Added
- **Codex Backend** ([#843](https://github.com/massgen/MassGen/pull/843)): New `codex` backend type for OpenAI Codex CLI
  - Local and Docker execution modes with workspace mounting
  - OAuth and API key authentication
  - `NativeToolMixin` abstract mixin for shared native tool handling between Codex and Claude Code
  - Custom and workflow MCP servers (`custom_tools_server.py`, `workflow_tools_server.py`) for exposing MassGen tools to CLI-based backends

### Changed
- **TUI Theme System** ([#842](https://github.com/massgen/MassGen/pull/842)): Refactored to palette-based architecture with unified `base.tcss` replacing per-widget inline CSS
  - Semantic CSS variables for consistent cross-component theming
  - Theme palette files for dark and light variants
  - Removed legacy `transparent.tcss`

- **Per-agent Voting Sensitivity** ([#842](https://github.com/massgen/MassGen/pull/842)): Voting sensitivity (`strict`/`balanced`/`lenient`) now configurable per-agent, overriding orchestrator-level defaults with rewritten evaluation criteria

- **Claude Code Backend** ([#843](https://github.com/massgen/MassGen/pull/843)): Refactored to use `NativeToolMixin` with native filesystem support and OS-level sandbox, extracting shared tool handling logic

- **Round Display Tracking** ([#842](https://github.com/massgen/MassGen/pull/842)): Vote and answer submissions now track and display submission round numbers in TUI timeline and coordination UI

- **Gemini Backend** ([#842](https://github.com/massgen/MassGen/pull/842)): Globally unique tool call ID generation and configuration improvements

### Fixed
- **Final Presentation Display** ([#842](https://github.com/massgen/MassGen/pull/842)): Fixed rendering issues with final presentation box
- **MCP Tool Call Error Handling** ([#842](https://github.com/massgen/MassGen/pull/842)): Enhanced error handling for invalid MCP tool calls with clearer user guidance

### Documentation, Configurations and Resources
- **Backends User Guide**: Updated `docs/source/user_guide/backends.rst` with Codex backend documentation
- **Interactive Mode Design**: New `docs/modules/interactive_mode.md` architecture document
- **Capabilities Registry**: Updated `massgen/backend/capabilities.py` with Codex models (`gpt-5.2-codex`, `gpt-5.1-codex`, `gpt-5-codex`, `gpt-4.1`)
- **Backend Integrator Skill**: New `massgen/skills/backend-integrator/SKILL.md` for guided backend integration workflows
- **OpenSpec Documents**: Interactive mode proposal, design, vision, and spec documents

### Technical Details
- **Major Focus**: Codex backend integration, TUI theme refactoring, per-agent voting sensitivity
- **Files Modified**:
  - Backend: `massgen/backend/codex.py` (new), `massgen/backend/native_tool_mixin.py` (new), `massgen/backend/claude_code.py` (refactored)
  - TUI: `massgen/frontend/displays/textual_themes/base.tcss` (new), palette files (new/moved), widget CSS extraction
  - MCP: `massgen/mcp_tools/custom_tools_server.py` (new), `massgen/mcp_tools/workflow_tools_server.py` (new)
  - Docs: `docs/source/user_guide/backends.rst`, `docs/modules/interactive_mode.md`
- **Contributors**: @ncrispino and the MassGen team

## [0.1.46] - 2026-02-02

### Added
- **Subagent TUI Streaming** ([#821](https://github.com/Leezekun/MassGen/issues/821)): Stream and display subagents almost identically to main process in TUI
  - Clickable subagent preview cards that expand to full timeline views
  - Real-time event streaming from subprocess logs via symlinks
  - Unified display components reused for both main agents and subagents
  - Subagent rounds tracking and status visualization

- **Enhanced Final Presentation Display**:
  - Final presentation now includes workspace visualization
  - Winning agent highlighted with clear visual indicator
  - Workspace symlinks (`curr_workspace`) for easy access to final agent's workspace
  - Improved final answer formatting with better separation from reasoning

### Changed
- **TUI Event Architecture Refactor**: Major refactor to structured event emission pipeline
  - Single source of truth for TUI display creation shared between main and subagent views
  - Unified event parsing for consistent tool displays across agent types
  - Stream chunk handling removed in favor of direct event emission (phase 4 refactor)
  - Improved event streaming architecture for better maintainability

- **Subagent Display Improvements**:
  - Refactored subagent rendering to remove older streams and prevent clutter
  - Better debugging support with enhanced logging
  - Tool numbering fixes for consistent display

### Fixed
- **Banner Display Issues**: Fixed banners not showing up for first coordination round
- **Tool Call ID Handling**: Fixed issue when tool call IDs are not alphanumeric (e.g., kimi2.5 models)
- **Round Tracking**: Improved round tracking logic for more accurate status display

### Documentation, Configurations and Resources
- **Tutorial Video GIFs**: New `docs/source/_static/images/tutorial-*.gif` files for visual documentation
- **Module Documentation**: New `docs/modules/subagents.md` comprehensive guide for subagent architecture
- **Updated Documentation**: `docs/source/index.rst` with tutorial GIF previews and updated video links
- **OpenSpec Design Docs**: Multiple design documents for TUI refactoring and event pipeline architecture

### Technical Details
- **Major Focus**: Subagent TUI streaming, event architecture refactor, final presentation improvements
- **Files Modified**:
  - TUI: `massgen/frontend/displays/textual_widgets/subagent_screen.py`, `subagent_card.py`, event handling modules
  - Subagent: `massgen/subagent/manager.py` with improved logging directory structure
  - Final presentation: Enhanced workspace handling and visual indicators
  - Docs: `docs/modules/subagents.md`, `docs/source/index.rst`
- **Contributors**: @ncrispino (23 commits), @HenryQi, @franklinnwren, and the MassGen team

## [0.1.45] - 2026-01-31

### Changed
- **BREAKING (Soft):** Default display changed from `rich_terminal` to `textual_terminal`
  - All users now get the superior TUI experience by default
  - Existing configs with `display_type: "rich_terminal"` will show deprecation warning and use TUI
  - Use `--display rich` flag to force legacy Rich display
  - Updated ALL 160+ example configs to use `textual_terminal`

### Improved
- **Setup Wizard**: `--setup` and `--quickstart` now generate configs with TUI display by default
- **Documentation**: Enhanced with prominent TUI feature descriptions and benefits
- **First-Run Experience**: Clear explanation of TUI benefits for new users

### Deprecated
- **Rich Terminal Display**: `rich_terminal` display type is now deprecated in favor of `textual_terminal`
  - Configs using `rich_terminal` will show warning and auto-convert to TUI
  - Use `--display rich` to explicitly request legacy Rich display

### Fixed
- **Documentation Paths**: Fixed case study page paths for proper rendering
- **PyPI Packaging**: Added missing files to MANIFEST.in for complete package distribution
- **ReadTheDocs Config**: Updated Python version to 3.12 for documentation builds

### Documentation, Configurations and Resources
- **Updated Documentation**: `docs/quickstart/installation.rst` and `docs/quickstart/running-massgen.rst` with TUI as default
- **Config Migration**: Example configs in `massgen/configs/` updated to use `textual_terminal`
- **ReadTheDocs**: Updated `.readthedocs.yaml` with Python 3.12

### Technical Details
- **Major Focus**: TUI default transition, config migration, documentation improvements
- **Files Modified**:
  - Configs: All YAML files in `massgen/configs/`
  - Docs: `docs/source/quickstart/*.rst`, `.readthedocs.yaml`
  - Packaging: `MANIFEST.in`, `pyproject.toml`
- **Contributors**: @ncrispino, @HenryQi, and the MassGen team

## [0.1.44] - 2026-01-28

### Added
- **Execute Mode**: Independent mode for browsing and executing existing plans ([#819](https://github.com/massgen/MassGen/pull/819))
  - Cycle through modes: Normal → Planning → Execute via `Shift+Tab` or mode bar click
  - Plan selector popover shows up to 10 recent plans with timestamps and prompts
  - "View Full Plan" button opens modal with all plan tasks
  - Empty submission (just pressing Enter) executes selected plan
  - Context paths preserved from planning phase to execution phase
  - Warning shown if no plans exist when trying to enter Execute mode

- **Case Studies Setup Guide**: Interactive setup instructions on case studies page ([#818](https://github.com/massgen/MassGen/pull/818))
  - "Try it yourself" collapsible sections with setup guide
  - Quick start command: `uv run massgen --web`
  - Model selection guidance (Claude 4.5 Opus, Gemini 3 Pro, GPT 5.2)
  - Terminal config file example for CLI users
  - Helper text prompting users to compare MassGen with single-agent baselines

### Fixed
- **Plan Mode Separation**: Fixed bug where planning instructions were injected during execute mode
  - Planning prompt prepending now only occurs for `plan_mode == "plan"`
  - Execute mode uses `build_execution_prompt()` without planning overhead

- **Tool Call Spacing**: Fixed spacing issues in tool card display
- **Timeline Performance**: Improved scrolling performance with viewport optimization and reduced timeline size limits

### Changed
- **Context Paths Storage**: `PlanMetadata` now includes `context_paths` field in `massgen/plan_storage.py`
  - Context paths stored during `finalize_planning_phase`
  - Restored automatically in `prepare_plan_execution_config` during execution
  - Enables consistent file/directory access between planning and execution

- **Empty Submission Support**: Input widget now allows empty submission in execute mode
  - Placeholder text: "Press Enter to execute selected plan - or type instructions"
  - Removed input text guard to enable plan execution without additional input

- **Plan Options Widget**: Enhanced `PlanOptionsPopover` with "View Full Plan" functionality
  - New `ViewPlanRequested` message for modal communication
  - Better plan browsing experience

### Documentation, Configurations and Resources
- **Case Studies Enhancement**: `docs/source/case_studies/index.html` with setup guide
  - New `docs/source/case_studies/terminal_config.txt` with example YAML configuration
  - Video tutorial links moved higher for better discoverability
  - Added contextual notes for baseline comparisons

- **Shortcuts Documentation**: Updated `shortcuts_modal.py` with Shift+Tab mode cycling description

### Technical Details
- **Major Focus**: Execute mode for independent plan selection, TUI performance improvements, case studies UX
- **Files Modified**:
  - TUI: `textual_terminal_display.py`, `mode_bar.py`, `plan_options.py`, `multi_line_input.py`, `content_sections.py`
  - Plan system: `plan_storage.py`, `plan_execution.py`, `tui_modes.py`
  - Backend: `claude_code.py` (tool tracking improvements)
  - Docs: `index.rst`, `case_studies/index.html`
- **Contributors**: @ncrispino and the MassGen team

## [0.1.43] - 2026-01-26

### Added
- **Tool Call Batching**: Consecutive MCP tool calls are now grouped into collapsible tree views ([#815](https://github.com/massgen/MassGen/pull/815))
  - Shows 3 items by default, collapses rest with "+N more" indicator
  - Click to expand full list
  - Respects Timeline Chronology Rule: tools only batch when consecutive (no intervening content)
  - New `ToolBatchCard` widget and `ToolBatchTracker` state machine

- **Interactive Case Studies**: New documentation page with visual comparisons ([#812](https://github.com/massgen/MassGen/pull/812))
  - Side-by-side SVG comparisons between MassGen and single-agent solutions
  - Iterative refinement examples showing multi-round improvements
  - Collapsible sections with baseline visualizations

- **Video Tutorials Section**: New documentation with Getting Started and Development videos
  - Prominent CTAs linking to YouTube tutorials
  - Descriptive text for each video category

- **Plan Mode Enhancements**: New `PlanOptionsPopover` widget for plan management
  - Browse recent plans with quick access
  - Plan depth selector (thorough/balanced/quick)
  - Broadcast mode toggle (human/agents/none)
  - Plan validation before execution

- **Quoted Path Support**: Paths with spaces now work correctly using quotes
  - `@"/path/with spaces/file.txt"` syntax for context injection
  - Tab completion support for quoted paths
  - Write permission suffix works with quotes: `@"/path/file.txt":w`

### Fixed
- **Final Presentation Display**: Fixed critical bug where final answers weren't displayed properly
  - Reasoning text now separated from actual answer content
  - Visual distinction: reasoning collapsed/smaller, answer prominent
  - Fixed content filtering in `ContentNormalizer.should_display` logic

- **Bottom Status Bar**: Fixed status bar not showing in certain scenarios
- **Scrolling Bar**: Fixed scrolling bar on right side display issues
- **Mode Buttons**: Fixed mode button interaction and alignment
- **Task Highlighting**: Fixed task highlighting in task plan cards
- **Toast Location**: Fixed toast notification positioning

### Changed
- **Reasoning/Content Display**: Enhanced formatting with vertical line indicators for thinking blocks
- **Tool Presentation**: Improved tool card visual presentation
- **Demo GIF**: Updated `docs/source/_static/images/readme.gif` with higher resolution

### Documentation, Configurations and Resources
- **Interactive Case Studies**: New `docs/source/case_studies/index.html` with SVG comparisons
  - Example SVGs for Claude, GPT, Gemini, and MassGen outputs
  - `docs/source/case_studies/example_svgs/` directory with visualization assets
- **Homepage Updates**: Updated `docs/source/index.rst` with case studies CTA and video tutorials section
- **OpenSpec Proposals**: Multiple TUI improvement specifications in `openspec/changes/`:
  - `add-tui-tool-call-batching/` - Tool batching design and implementation
  - `improve-tui-final-presentation-display/` - Final presentation fix specs
  - `fix-tui-mode-bar-alignment/` - Mode bar alignment fix
  - `fix-tui-tool-card-spacing/` - Tool card spacing improvements
  - `add-tui-workflow-comprehension/` - Workflow comprehension enhancements

### Technical Details
- **Major Focus**: TUI UX polish, tool call batching, documentation enhancements
- **Contributors**: @ncrispino (22 commits), @franklinnwren (8 commits), @HenryQi (3 commits) and the MassGen team

## [0.1.42] - 2026-01-23

### Added
- **TUI Visual Redesign**: Comprehensive visual overhaul with modern "Conversational AI" aesthetic ([#806](https://github.com/massgen/MassGen/pull/806))
  - **Phase 1**: Unified input card with integrated mode toggles, rounded corners (╭╮╰╯), simplified radio-style indicators
  - **Phase 2**: Agent tabs redesign with dot indicators (◉ active, ○ waiting, ✓ done), two-line display (name + model)
  - **Phase 3**: Tool cards with adaptive density - collapsed by default, click to expand parameters/results
  - **Phase 4**: Welcome screen improvements with centered input and muted help hints
  - **Phase 5**: Task lists with visual progress bars, "X of Y" counts, and "← current" markers
  - **Phase 6**: Modal polish with rounded containers, consistent headers, softer borders, unified button styling
  - **Phase 7**: Header polish with bullet separators, desaturated color palette, warmer tones
  - **Phase 8**: Professional visual polish throughout
  - **Phase 9**: Edge-to-edge borderless container layout
  - **Phase 11**: UX polish with collapsible reasoning blocks, scroll indicators
  - **Phase 12**: CSS-based round navigation (partial)
  - **Phase 13**: Backend integration with token usage updates for TUI status ribbon

- **Human Input Queue**: Inject messages to agents mid-stream during execution
  - `HumanInputHook` for queuing and injecting human input during agent execution
  - Thread-safe queue with per-agent tracking (each message delivered once per agent)
  - Callback support for TUI visual indicator updates
  - Messages persist until turn ends, allowing injection to multiple agents

### Fixed
- **AG2 Single-Agent Coordination**: Fixed coordination issues for single-agent AG2 setups ([#804](https://github.com/massgen/MassGen/pull/804))
  - Single agent can now vote for itself after producing its first answer
  - Properly clears `restart_pending` flag for single-agent scenarios
  - Fixes stuck coordination when using AG2 adapter with single agent

- **Plan Execution in TUI**: Fixed plan-then-execute workflow in Textual TUI
- **Planning Prompt Improvements**: Better subagent clarity and planning guidance

### Changed
- **Token Usage Updates**: Orchestrator now emits `token_usage_update` stream chunks for real-time TUI status updates
- **Plan Session ID**: Orchestrator accepts optional `plan_session_id` to prevent workspace contamination during plan execution

### Documentation, Configurations and Resources
- **TUI Redesign Handoffs**: Design handoff documents for implementation phases
  - New `docs/dev_notes/tui_redesign_phase6_handoff.md` for modal improvements
  - New `docs/dev_notes/tui_redesign_phase9_11_13_handoff.md` for layout and UX polish
- **OpenSpec Proposals**: Complete TUI redesign specification in `openspec/changes/update-tui-conversational-design/`
  - `proposal.md` - Full 13-phase redesign proposal
  - `design.md` - Visual design decisions and rationale
  - `specs/tui/spec.md` - Detailed component specifications
  - `tasks.md` - Implementation task breakdown
  - `HANDOFF_PHASE12.md` - Phase 12 handoff for CSS round navigation

### Technical Details
- **Major Focus**: TUI visual redesign, human input injection, AG2 single-agent fixes
- **Contributors**: @ncrispino, @HenryQi, @db-ol and the MassGen team
## [0.1.41] - 2026-01-21

### Added
- **Async Subagent Execution**: Background subagent execution with `async_=True` parameter (MAS-214)
  - Parent agents continue working while subagents run in background
  - Non-blocking `spawn_subagents` returns immediately with running status
  - Parent can poll for subagent completion and retrieve results
  - Configurable injection strategies: `tool_result` (default) or `user_message`
  - Batch injection when multiple subagents complete simultaneously

- **Result Polling**: Check subagent completion status and retrieve results
  - Poll for completed background subagents when ready
  - Results returned in structured XML format with metadata
  - Includes execution time, token usage, and workspace paths

- **Subagent Round Timeouts**: Per-round timeout control for subagents
  - New `subagent_round_timeouts` configuration section
  - Supports `initial_round_timeout_seconds`, `subsequent_round_timeout_seconds`, `round_timeout_grace_seconds`
  - Inherits from parent `timeout_settings` if omitted

### Configuration
- **New Subagent Parameters**: Extended YAML configuration options
  - `enable_subagents`: Enable subagent tools for parallel task execution
  - `subagent_default_timeout`: Default timeout in seconds (default: 300)
  - `subagent_min_timeout`: Minimum allowed timeout (default: 60)
  - `subagent_max_timeout`: Maximum allowed timeout (default: 600)
  - `subagent_max_concurrent`: Maximum concurrent subagents (default: 3)
  - `subagent_round_timeouts`: Per-round timeout settings for subagents
  - `async_subagents`: Async execution settings (`enabled`, `injection_strategy`)

### Documentation, Configurations and Resources
- **Subagents Guide**: Updated `docs/source/user_guide/advanced/subagents.rst` with async execution section
- **Async Example Config**: New `massgen/configs/features/async_subagent_example.yaml`
- **OpenSpec Proposals**: Design documents in `openspec/changes/add-async-subagent-execution/`
  - `proposal.md` - Feature proposal and impact analysis
  - `design.md` - Architecture decisions and implementation details
  - `specs/subagent/spec.md` - Detailed specification

### Technical Details
- **Major Focus**: Async subagent execution, subagent round timeouts, subagent configuration parameters
- **Contributors**: @ncrispino, @HenryQi and the MassGen team

## [0.1.40] - 2026-01-19

### Added
- **Textual TUI Interactive Mode**: Interactive terminal UI with `--display textual` for interactive MassGen sessions
  - Real-time agent output streaming with syntax highlighting
  - Agent tab bar for switching between agents and post-evaluation views
  - Keyboard-driven navigation with extensive keyboard shortcuts
  - Keyboard navigation with `j/k` scrolling and `:q` to quit
  - Comprehensive modals:
    - `?` or `h`: Keyboard shortcuts help
    - `f`: Full agent output
    - `c`: Cost breakdown (token usage and costs)
    - `m`: Tool metrics
    - `v`: Vote results
    - `o`: Orchestrator events
    - `s`: System status
    - `p`: MCP server status
    - `b`: Answer browser with side-by-side comparisons
    - `t`: Coordination timeline
    - `w`: Workspace file browser with tree navigation and file preview
  - Context path injection UI with `@` syntax support
  - Human feedback integration with prompt modal
  - Enhanced final answer presentation with formatting
  - Plan execution mode selection UI
  - Scrolling improvements with visual indicators
  - Tool input/output display with color-coded formatting

### Changed
- **Final Answer View**: Improved presentation and formatting in Textual TUI
- **Subagent Display**: Fixed subagent rendering and progress bar updates
- **Context Path Handling**: Enhanced context path validation and display
- **Broadcasting**: Improved broadcasting behavior for questions similar to context injection

### Fixed
- **Tool Inputs Not Showing**: Fixed issue where tool inputs were not displayed in later answers
- **Empty Space Issue**: Resolved empty space rendering problem in agent answers
- **Scrolling**: Fixed scrolling behavior and visual indicators
- **Cancellation**: Improved Ctrl+C handling and graceful shutdown
- **Menu Display**: Fixed issue with too many items being displayed in menus
- **Click Handling**: Resolved click event issues in TUI
- **Path Permissions**: Fixed workspace path permission handling
- **Task Plan Display**: Fixed task plan rendering in TUI

### Documentation, Configurations and Resources
- **Textual TUI Architecture**: New `docs/dev_notes/textual_tui_architecture.md` for TUI implementation details
- **Textual UI Developer Skill**: New `massgen/skills/textual-ui-developer/SKILL.md` for TUI development workflows
- **OpenSpec Proposals**: Multiple design documents in `openspec/changes/`:
  - `add-tui-modes/` - TUI modes design and specs
  - `tui-production-upgrade/` - Enhanced TUI widgets
  - `update-textual-tui-polish/` - TUI polish and refinements
- **Updated CLAUDE.md**: Enhanced project instructions with TUI development guidance
- **Updated Config**: Modified `massgen/configs/basic/multi/three_agents_default.yaml` for TUI testing

### Technical Details
- **Major Focus**: Textual TUI interactive mode, keyboard navigation, workspace browser, performance optimization
- **Contributors**: @ncrispino, @praneeth999, @HenryQi and the MassGen team

## [0.1.39] - 2026-01-16

### Added
- **Plan and Execute Workflow**: Complete plan-then-execute workflow separating "what to build" from "how to build it"
  - `--plan-and-execute`: Create plan then immediately execute it
  - `--execute-plan <id|path|latest>`: Execute an existing plan without re-planning
  - `--broadcast <human|agents|false>`: Control planning collaboration (auto-switches to `false` in automation mode)

- **Task Verification Workflow**: New `verified` status for distinguishing implementation from validation
  - Status flow: `pending` → `in_progress` → `completed` → `verified`
  - `verification_group` labels for batch verification (e.g., "foundation", "frontend_ui")
  - `get_tasks_awaiting_verification()` and `get_verification_group_status()` helpers
  - Agents verify entire groups at logical checkpoints

- **Plan Storage System**: Persistent plan management in `.massgen/plans/`
  - Plan structure: `plan_metadata.json`, `execution_log.jsonl`, `plan_diff.json`
  - `frozen/` directory for immutable planning-phase snapshots
  - `workspace/` directory for modified plan after execution
  - Plan IDs use timestamp format: `YYYYMMDD_HHMMSS_microseconds`

### Changed
- **Planning Prompt Improvements**: Updated guidance to focus on outcomes over implementation
  - "Describe WHAT the final product needs, not HOW to build it"
  - Verification methods must be automated (not manual inspection)
  - Quality focus: "If it's visual, it should LOOK good"

### Fixed
- **Response API Function Call Messages**: Sanitized function_call messages for OpenAI Response API compatibility ([#792](https://github.com/massgen/MassGen/pull/792))
  - Filter function_call messages to only include valid fields (type, name, arguments, call_id, id)
  - Remove invalid fields like 'content' that cause `Unknown parameter` errors
  - Ensure 'arguments' field is JSON-serialized string, not an object
  - Fixes: `Unknown parameter: 'input[N].content'` and `Invalid type for 'input[N].arguments'`

- **Plan Execution Edge Cases**: Various fixes for plan execution workflow
  - Single-agent config handling for both `agent:` and `agents:` shapes
  - Plan collection path fixed to look for `tasks/plan.json` (file) not `plan/` (directory)
  - Subprocess deadlock prevention by merging stderr into stdout
  - Argparse handling for questions starting with `-` via `--` end-of-options marker
  - Progress calculation now counts `verified` tasks as completed

### Documentations, Configurations and Resources
- **Planning Mode Guide**: Updated `docs/source/user_guide/advanced/planning_mode.rst` with plan-and-execute workflow
- **Roadmap**: New `ROADMAP_v0.1.40.md` for next release planning

### Technical Details
- **Major Focus**: Plan-and-execute workflow, task verification, plan storage system
- **Contributors**: @ncrispino, @HenryQi, @db-ol and the MassGen team

## [0.1.38] - 2026-01-15

### Added
- **Task Planning Mode**: Create structured plans for future workflows with `--plan` flag (plan-only, no auto-execution)
  - `--plan`: Enable task planning mode for structured work breakdown
  - `--plan-depth`: Control planning granularity (shallow/medium/deep)
  - Planning prompt prefix for configurable depth
  - Outputs `feature_list.json` with task dependencies and priorities

- **Two-Tier Workspace**: Git-backed scratch/deliverable separation
  - `use_two_tier_workspace: true` config option
  - `scratch/` directory for work-in-progress
  - `deliverable/` directory for complete, self-contained outputs
  - Automatic `[INIT]`, `[SNAPSHOT]`, `[TASK]` git commits
  - Task completion triggers git commit with completion notes
  - Agents can use `git log` to review work history

- **Project Instructions Auto-Discovery**: CLAUDE.md/AGENTS.md support following [agents.md](https://agents.md/) standard
  - Automatic discovery from context paths (via `@path` syntax)
  - Hierarchical "closest wins" algorithm for monorepo support
  - CLAUDE.md takes precedence over AGENTS.md at same level
  - Contents injected into system prompts with softer framing

- **Batch Image Analysis**: Multi-image support in media tools
  - `understand_image` accepts `images` dict for named multi-image comparison
  - `read_media` accepts `inputs` list for batch image processing
  - Dict keys become reference names in prompts for image identification
  - `max_concurrent` parameter for concurrency control

- **Docker Health Monitoring**: Container diagnostics on MCP failures
  - `get_container_health()` for health status checking
  - `get_container_logs()` and `save_container_logs()` for log retrieval
  - Automatic log capture when MCP disconnections occur
  - Health info tracked in enforcement events

- **Enhanced Enforcement Tracking**: Improved status.json visibility
  - `finish_reason`: `"timeout"`, `"completed"`, `"error"`, or `"in_progress"`
  - `finish_reason_details`: Human-readable explanation
  - `is_complete`: Boolean completion status
  - Fields appear at top of status.json for immediate visibility

### Changed
- **Improved Deliverable Guidance**: System prompts emphasize self-contained packages
  - Checklist: all required files, dependencies, assets, README
  - Explicit examples for different artifact types
  - Soft timeout message reinforces complete deliverables

- **Git History in System Prompt**: Agents aware of version control
  - Commit prefix documentation: `[INIT]`, `[SNAPSHOT]`, `[TASK]`
  - Guidance to use `git log` for reviewing work history

### Fixed
- **Vote Tracking Bug**: Ignored votes no longer leak into final results
  - Clear `agent_states[agent_id].votes` when vote ignored due to restart
  - Sync between `agent_states` and `coordination_tracker.votes`

- **Soft→Hard Timeout Race Condition**: Guaranteed progression
  - Hard timeout now calculated from soft timeout injection time
  - Soft timeout must fire before hard timeout can trigger
  - `RoundTimeoutState` class for shared state between hooks

- **MCP Reset on Restart**: Full tools restored after hard timeout restart
  - Reset `_mcp_initialized = False` in `handle_restart()`
  - Forces MCP re-initialization (17 tools vs 2)

- **Circuit Breaker for Hard Timeout**: Prevents infinite denial loops
  - Tracks consecutive denied tool calls
  - Warning after 3+ consecutive denials
  - Force terminate after 10 blocked tool calls

- **`use_two_tier_workspace` Config Pass-Through**: Flag now reaches orchestrator
  - Added to `CoordinationConfig` creation in cli.py
  - Planning MCP server receives `--use-two-tier-workspace` flag

### Documentations, Configurations and Resources
- **Project Integration Guide**: New `docs/source/user_guide/files/project_integration.rst`
- **Debugging Assumptions**: Added guidance to `CLAUDE.md` for log analysis
- **OpenSpec Proposals**: New `openspec/changes/add-enforcement-observability/` and `openspec/changes/add-task-planning-mode/`
- **Skills**: New `massgen/skills/massgen-log-analyzer/SKILL.md`
- **Roadmap**: Renamed `ROADMAP_v0.1.38.md` to `ROADMAP_v0.1.39.md`

### Technical Details
- **Major Focus**: Task planning, two-tier workspaces, project instructions, timeout reliability
- **Contributors**: @ncrispino, @chiwang, @HenryQi and the MassGen team

## [0.1.37] - 2026-01-12

### Added
- **Execution Traces**: Full execution history preserved as searchable markdown files ([MAS-226](https://linear.app/massgen-ai/issue/MAS-226))
  - **Trace file format**: Human-readable `execution_trace.md` saved alongside snapshots
  - **Compression recovery**: Agents can read trace files to recover detailed history after context compression
  - **Cross-agent access**: Other agents can access execution traces in temp workspaces to understand approaches
  - **Full content preservation**: Tool calls, results, and reasoning blocks saved without truncation
  - **Grep-friendly**: Searchable format for debugging and analysis

- **Claude Code Thinking Mode**: Streaming buffer support for Claude Code reasoning
  - Thinking content captured in streaming buffer for trace files
  - Integration with execution trace system

- **Voting Execution Traces**: Vote reasoning captured in execution trace files
  - Full vote context preserved for analysis

### Changed
- **Standardized Agent Labeling**: Consistent agent identification across backends
  - Unified labeling format for multi-agent coordination
  - Improved workspace anonymization for cross-agent sharing

- **Gemini Thinking Mode**: Fixed thinking/reasoning content handling
  - Proper streaming buffer integration for Gemini reasoning blocks

- **Streaming Buffer Improvements**: Enhanced reasoning content capture
  - Better handling of thinking blocks across providers
  - Improved trace file generation

### Fixed
- **Claude Code Backend**: Fixed skills and tool handling issues
- **Config Builder**: Fixed configuration generation edge cases
- **Round Timeout Handling**: Improved timeout behavior during coordination

### Documentations, Configurations and Resources
- **Timeouts Guide**: Updated `docs/source/reference/timeouts.rst` with comprehensive timeout documentation
- **Backends Guide**: Updated `docs/source/user_guide/backends.rst` with OpenRouter support
- **Logging Guide**: Updated `docs/source/user_guide/logging.rst` with execution trace information
- **Debug Config**: New `massgen/configs/debug/round_timeout_test.yaml` for timeout testing
- **OpenSpec**: New `openspec/changes/add-execution-traces/` with proposal and specs

### Technical Details
- **Major Focus**: Execution traces for context recovery, thinking mode improvements, standardized agent labeling
- **Contributors**: @ncrispino, @chiwang, @HenryQi and the MassGen team

## [0.1.36] - 2026-01-09

### Added
- **Hook Framework**: General hook framework for extending agent behavior at key execution points ([MAS-215](https://linear.app/massgen-ai/issue/MAS-215))
  - **PreToolUse hooks**: Execute before tool invocation for permission validation and argument modification
  - **PostToolUse hooks**: Execute after tool results for content injection and processing
  - **Injection strategies**: `tool_result` (append to output) and `user_message` (separate message)
  - **Built-in hooks**: MidStreamInjectionHook for cross-agent updates, HighPriorityTaskReminderHook for task completion
  - **Custom hooks**: Python callable hooks with glob-style pattern matching (`*`, `Write|Edit`, `mcp__*`)
  - **Error handling**: Configurable fail-open (default) or fail-closed behavior for security-critical hooks
  - **Debug support**: `debug_delay_seconds` and `debug_delay_after_n_tools` for testing mid-stream injection

- **Unified `@path` Context Handling**: Inline context path references in prompts
  - **Inline file picker**: Type `@` in CLI to trigger autocomplete popup (like Claude Code)
  - **Syntax support**: `@path` (read), `@path:w` (write), `@dir/` (directory)
  - **Context accumulation**: Paths from earlier turns remain accessible in later turns
  - **Permission upgrade**: `@file` in turn 1, `@file:w` in turn 2 grants write permission
  - **Deferred agent creation**: Docker containers launch once with all paths from first prompt

- **Claude Code Native Hooks**: Integration with Claude Code's hook system
  - Support for Claude Code temp filesystem tools permission handling

### Changed
- **Docker Resource Management**: Clean up Docker resources when recreating agents for new `@path` references
  - Prevents resource leaks during interactive sessions with path changes

- **Installation Instructions**: Revised README with clearer `uv` installation steps
  - Streamlined quickstart guide for faster onboarding

### Fixed
- **Path Handling**: Fixed path reference handling for Web UI and Rich CLI
  - Consistent behavior across CLI interactive mode, automation mode, and Web UI

### Documentations, Configurations and Resources
- **Hook Framework Guide**: New `docs/source/user_guide/advanced/hooks.rst` with comprehensive hook documentation
- **File Operations Guide**: Updated `docs/source/user_guide/files/file_operations.rst` with `@path` syntax
- **Installation Guide**: Updated `docs/source/quickstart/installation.rst` with `uv` instructions
- **Hook Config Example**: New `massgen/configs/hooks/example_hooks.yaml` for hook configuration
- **Debug Config**: New `massgen/configs/debug/injection_delay_test.yaml` for testing mid-stream injection
- **OpenSpec**: New `openspec/changes/add-hook-framework/` and `openspec/changes/unify-context-path-handling/` proposals

### Technical Details
- **Major Focus**: Hook framework for agent lifecycle events, unified `@path` syntax, Claude Code integration
- **Contributors**: @ncrispino, @franklinnwren, @HenryQi and the MassGen team

## [0.1.35] - 2026-01-07

### Added
- **Log Analysis CLI Command**: New `massgen logs analyze` for AI-assisted log analysis ([MAS-227](https://linear.app/massgen-ai/issue/MAS-227))
  - **Prompt mode** (default): Generates analysis prompt referencing `massgen-log-analyzer` skill for coding CLIs
  - **Self-analysis mode** (`--mode self`): Runs 3-agent MassGen team for multi-perspective analysis
  - **Per-turn analysis reports**: Reports placed at `turn_N/ANALYSIS_REPORT.md` instead of per-attempt
  - Supports `--turn/-t` for specific turn, `--force/-f` for overwrite, `--ui` for UI mode selection
  - Enhanced `massgen logs list` with "Analyzed" column and `--analyzed`/`--unanalyzed` filters

- **Logfire Workflow Analysis Attributes**: Comprehensive observability for understanding agent behavior ([MAS-199](https://linear.app/massgen-ai/issue/MAS-199))
  - **Round context**: `massgen.round.intent`, `available_answers`, `answer_previews` for workflow explanation
  - **Vote context**: Extended `massgen.vote.reason` (500 chars), `answer_label_mapping` for vote analysis
  - **Agent work products**: `massgen.agent.files_created`, `file_count` for detecting repeated work
  - **Restart context**: `massgen.restart.reason`, `trigger`, `triggered_by_agent`
  - **Local file references**: `massgen.log_path`, `agent.log_path`, `answer_path` for hybrid access

- **`direct_mcp_servers` Config Option**: Keep specific MCP servers as direct protocol tools
  - When `enable_code_based_tools: true`, exempts specified servers from code-only filtering
  - Useful for debugging/monitoring tools (e.g., Logfire) that need immediate access
  - Subagents automatically inherit `direct_mcp_servers` from parent
  - Logs warning if server not found in `mcp_servers`

- **Task Context Module**: New `massgen/context/` package for unified context management
  - `TaskContext` class for managing agent task state and context

### Changed
- **Skill & Voting Improvements**: Enhanced skill execution and voting coordination
  - MCPs can now run directly in certain scenarios
  - Improved skill parameter handling

- **Analysis Per-Turn**: Log analysis now operates at turn level rather than attempt level
  - More intuitive organization of analysis reports

### Fixed
- **Unknown Tool Handling**: Unknown/malformed tool names (e.g., Gemini's `default_api:` prefix) no longer cause agent termination ([MAS-225](https://linear.app/massgen-ai/issue/MAS-225))
  - Only client-provided external tools trigger external tool call path
  - Unknown tools logged and skipped gracefully

- **Vote-Only Mode**: Fixed agents wasting rounds when reaching `max_new_answers_per_agent`
  - System message now correctly omits `new_answer` tool
  - Internal tool filtering uses agent-specific tools
  - Prevents hallucinated `new_answer` calls from passing validation

- **Grok Backend**: Fixed tool handling issues

- **Gemini Backend**: Fixed tool-related problems and parameter handling

- **Metadata Saving**: Config loader now returns raw/unexpanded config to avoid logging secrets

### Documentations, Configurations and Resources
- **Logging Guide**: Updated `docs/source/user_guide/logging.rst` with CLI quick reference and analysis workflow
- **Code-Based Tools Guide**: New "Direct MCP Servers" section in `docs/source/user_guide/tools/code_based_tools.rst`
- **CLI Reference**: Updated `docs/source/reference/cli.rst` with `logs analyze` command documentation
- **YAML Schema**: Added `direct_mcp_servers` parameter in `docs/source/reference/yaml_schema.rst`
- **Analysis Configs**: New `massgen/configs/analysis/log_analysis.yaml` and `log_analysis_cli.yaml`
- **Skill Update**: Comprehensive update to `massgen/skills/massgen-log-analyzer/SKILL.md`
- **OpenSpec**: New `openspec/changes/add-logfire-workflow-analysis/` with proposal and specs

### Technical Details
- **Major Focus**: Log analysis CLI, Logfire workflow attributes, direct MCP servers, tool handling fixes
- **Contributors**: @ncrispino, @chiwang, @HenryQi and the MassGen team

## [0.1.34] - 2026-01-05

### Added
- **OpenAI-Compatible Server**: Local HTTP server exposing MassGen as an OpenAI-compatible API
  - Run with `massgen server` or `python -m massgen.openai_server`
  - Compatible with any OpenAI SDK client for easy integration
  - Aggregates usage statistics in server responses
  - Uses `massgen run` backend for feature parity with CLI

- **Dynamic Model Discovery**: Authenticated model listing for Groq and Together backends
  - Fetches available models via API instead of hardcoded lists
  - Supports OpenAI-compatible model discovery endpoints
  - Design documentation in `docs/dev_notes/discovery/`

- **Review Skill**: New skill for code review workflows

### Changed
- **WebUI Improvements**: Enhanced frontend experience
  - File diff display for workspace changes
  - Answer refresh polling for real-time updates
  - Optimized workspace browser timing and performance
  - Better caching for office documents and scanning
  - Removed unnecessary workspace browser elements

- **Subagent System Reliability**: Improved multi-agent coordination
  - Better status tracking and error handling
  - Cancellation recovery improvements
  - Context and media handling fixes
  - Warning improvements for subagent operations

- **Pre-commit Workflow**: Added convenience scripts for pre-commit hooks

### Fixed
- **OpenAI Server**: Fixed null args handling in server responses

- **WebUI Status Tracking**: Fixed "Done" status tracking error

- **Responses Compression**: Fixed compression input issue

- **Superseded Vote Tracking**: Fixed vote tracking for superseded responses

- **Historical Workspace**: Fixed workspace history retrieval problems

- **Logfire Optional**: Made Logfire truly optional in base_with_custom_tool_and_mcp.py

- **Persona Handling**: Use persona JSONs even if generation not finished

### Documentations, Configurations and Resources
- **HTTP Server Integration Guide**: New `docs/source/user_guide/integration/http_server.rst` for OpenAI-compatible server usage
- **Model Discovery Design**: New `docs/dev_notes/backend_model_listing.md` design document for backend model listing (MAS-163)
- **Subagent Documentation**: Updated `docs/source/user_guide/advanced/subagents.rst` with status tracking and recovery details
- **CLI Reference**: Updated `docs/source/reference/cli.rst` with server command documentation
- **Skills**: New `massgen/skills/release-prep/SKILL.md` for release automation, new `massgen/skills/pr-checks/SKILL.md` for code review

### Technical Details
- **Major Focus**: OpenAI-compatible server, dynamic model discovery, WebUI improvements, subagent reliability
- **Contributors**: @ncrispino, @Angela, @maxim-saplin, @chiwang, @randombet, @HenryQi and the MassGen team

## [0.1.33] - 2026-01-02

### Added
- **Reactive Context Compression**: Automatic conversation compression when context length errors are detected
  - Summarizes older messages while preserving recent context
  - Supports all major backends: OpenAI, Claude, Gemini, OpenRouter, Grok
  - Includes message truncation fallback when compression alone is insufficient

- **Streaming Buffer System**: Tracks accumulated streaming content for compression recovery
  - Captures text deltas, tool calls, tool results, and reasoning/thinking content
  - New `--save-streaming-buffers` CLI flag to save buffers for debugging
  - New `persist_conversation_buffers` config option for cross-agent buffer inspection

### Changed
- **File Overwrite Protection**: `write_file` tool now refuses to overwrite existing files (use `edit_file` instead)

- **Task Plan Duplicate Protection**: `create_task_plan` MCP tool prevents re-creating plans after recovery, avoiding duplicate work

- **Grok Backend MCP Tools**: Fixed MCP tools visibility by removing incorrect stream method override

- **Circuit Breaker Debugging**: Added `agent_id`, `error_type`, and `error_message` parameters for better failure diagnostics

- **Voting Prompts**: Improved agent coordination prompts to encourage answer synthesis before voting

- **Subagent Failure Handling**: Results now include both `workspace` and `log_path` for debugging failed/timed-out subagents

### Fixed
- **GPT-5 Model Behavior**: System prompt adjustments ensure MassGen task planning is used over native model planning

- **Gemini Vote-Only Mode**: Fixed `vote_only` parameter handling in Gemini backend streaming

- **Subagent Failed Paths**: Fixed subagent MCP server handling of failed subagent results

- **Incomplete Response Recovery**: Added recovery mechanism when API streams end early, preserving partial content

### Documentations, Configurations and Resources
- **Context Compression Design Doc**: New `docs/dev_notes/context_compression_design.md` with architecture, testing, and backend-specific notes
- **Test Configurations**: New `test_reactive_compression.yaml` for compression testing

### Technical Details
- **Major Focus**: Reactive context compression, streaming buffer system, MCP tool protections
- **Contributors**: @ncrispino and the MassGen team

## [0.1.32] - 2025-12-31

### Changed
- **Session Export Multi-Turn Support**: Enhanced `massgen export` command with multi-turn session handling
  - New `--turns` flag for turn range selection (`all`, `N`, `N-M`, `latest`)
  - Workspace options: `--no-workspace`, `--workspace-limit` (default 500KB per agent)
  - Export controls: `--yes` (skip prompts), `--dry-run`, `--verbose`, `--json`
  - Multi-turn file collection preserves turn/attempt structure in exported gists

- **Logfire Optional Dependency**: Moved Logfire from required to optional `[observability]` dependency
  - Install with `pip install massgen[observability]` to enable Logfire tracing
  - Helpful error message when `--logfire` flag used without Logfire installed
  - Reduces default installation size for users who don't need observability

- **Per-Attempt Logging**: Each orchestration restart attempt now has isolated log files
  - Separate `massgen.log` and `execution_metadata.yaml` per attempt directory
  - Log handlers reconfigured on restart via `set_log_attempt()` function
  - Viewer adjusted to handle multiple attempt directories

- **Office Document PDF Conversion**: Automatic PDF conversion for DOCX/PPTX/XLSX when sharing sessions
  - Uses Docker + LibreOffice for headless conversion
  - Includes both original file (for download) and PDF (for preview) in gists
  - Tries sudo image first (`mcp-runtime-sudo`), falls back to standard image

### Documentations, Configurations and Resources
- **Installation Documentation**: Clarified `uv run` commands for tests and examples in README and quickstart docs
- **Logfire Documentation**: Updated installation instructions for observability optional extra

### Technical Details
- **Major Focus**: Multi-turn session export, Logfire optional dependency, per-attempt logging
- **Contributors**: @ncrispino @AbhimanyuAryan and the MassGen team

## [0.1.31] - 2025-12-29

### Added
- **Logfire Observability Integration**: Comprehensive structured logging and tracing via [Logfire](https://logfire.pydantic.dev/)
  - Automatic LLM instrumentation for OpenAI, Anthropic Claude, and Google Gemini backends
  - Tool execution tracing for MCP and custom tools with timing metrics
  - Agent coordination observability with per-round spans and token usage logging
  - Enable via `--logfire` CLI flag or `MASSGEN_LOGFIRE_ENABLED=true` environment variable
  - Graceful degradation to loguru when Logfire is disabled
  - New `massgen-log-analyzer` skill for AI-assisted log analysis

### Fixed
- **Azure OpenAI Native Tool Call Streaming**: Tool calls now accumulated and yielded as structured `tool_calls` chunks instead of plain content

- **OpenRouter Web Search Logging**: Fixed logging output for web search operations

### Documentations, Configurations and Resources
- **Logfire Documentation**: New `docs/source/user_guide/logging.rst` with usage guide and SQL query examples
- **Python Installation Guide**: Added link to Python installation guide in quickstart docs

### Technical Details
- **Major Focus**: Logfire observability integration, Azure OpenAI tool call streaming
- **Contributors**: @ncrispino @AbhimanyuAryan @shubham2345 @franklinnwren and the MassGen team

## [0.1.30] - 2025-12-26

### Added
- **OpenRouter Web Search Plugin**: Native web search integration via OpenRouter's plugins array
  - Maps `enable_web_search` to `{"id": "web"}` plugin format
  - Configurable search engine (`exa`/`native`) and `max_results` parameters
  - Added to research preset's auto-enabled web search backends

### Changed
- **Persona Generator Diversity Modes**: Enhanced persona generation with two diversity modes and phase-based adaptation
  - New `diversity_mode`: `perspective` (different values/priorities) or `implementation` (different solution types)
  - Phase-based adaptation: strong personas for exploration, softened for convergence
  - Multi-turn persistence via `persist_across_turns` option
  - Web UI integration with toggle in coordination settings

- **Azure OpenAI Multi-Endpoint Support**: Support both Azure-specific and OpenAI-compatible endpoints
  - Auto-detect endpoint format and use appropriate client (`AsyncAzureOpenAI` vs `AsyncOpenAI`)
  - Conditionally disable `stream_options` for Ministral/Mistral models

- **Environment Variable Expansion in Configs**: Use `${VAR}` syntax in YAML/JSON config files for flexible configuration

### Fixed
- **Azure OpenAI Workflow Tool Extraction**: Improved JSON parsing with fallback patterns for models outputting tool arguments without `tool_name` wrapper

- **Persistent Memory Retrieval**: Fixed regression by enabling retrieval on first turn

- **Backend Tool Registration**: Fixed tool registration and updated binary file extensions list

### Documentations, Configurations and Resources
- **OpenRouter Web Search Configs**: New `single_openrouter_web_search.yaml` and `openrouter_web_search.yaml`
- **Azure Multi-Endpoint Config**: Updated `azure_openai_multi.yaml` with env var examples
- **Diversity Documentation**: Updated `docs/source/user_guide/advanced/diversity.rst` with new diversity modes

### Technical Details
- **Major Focus**: OpenRouter web search, persona diversity modes, Azure OpenAI compatibility
- **Contributors**: @ncrispino @shubham2345 @AbhimanyuAryan @maxim-saplin and the MassGen team

## [0.1.29] - 2025-12-24

### Added
- **Subagent System**: Spawn parallel child MassGen processes for independent task execution
  - New `spawn_subagents` tool for agents to delegate parallelizable work
  - Process isolation with independent workspaces per subagent
  - Automatic inheritance of parent agent's backend configuration
  - Result aggregation with workspace paths and token usage tracking
  - Configurable via `enable_subagents`, `subagent_default_timeout`, and `subagent_max_concurrent`

### Changed
- **Tool Metrics with Distribution Statistics**: Enhanced `get_tool_metrics_summary()` with per-call averages and output distribution stats (min/max/median)

- **CLI Config Builder Per-Agent System Messages**: New mode in `massgen --quickstart` for assigning different system messages per agent ("Skip", "Same for all", "Different per agent")

### Fixed
- **OpenAI Responses API Duplicate Items**: Fixed duplicate item errors when using `previous_response_id` by skipping manual item addition when response ID is passed

- **Response Formatter Function Call ID Preservation**: Preserved 'id' field in function_call messages for proper pairing with reasoning items (required by OpenAI Responses API)

### Documentations, Configurations and Resources

- **Subagent Documentation**: New `docs/source/user_guide/advanced/subagents.rst` with usage guide, configuration examples, and best practices
- **Subagent Example Configs**: New `massgen/configs/features/test_subagent_orchestrator.yaml` and `test_subagent_orchestrator_code_mode.yaml`

### Technical Details
- **Major Focus**: Subagent parallel execution system, OpenAI Responses API compatibility
- **Contributors**: @ncrispino and the MassGen team

## [0.1.28] - 2025-12-22

### Added
- **Web UI Artifact Previewer**: Preview workspace artifacts directly in the web interface
  - Support for multiple formats: PDF, DOCX, PPTX, XLSX, images, HTML, SVG, Markdown, Mermaid diagrams
  - New `ArtifactPreviewModal` and `InlineArtifactPreview` components with Sandpack code preview

### Changed
- **Unified Multimodal Tools**: Consolidated `read_media` for understanding and `generate_media` for generation
  - Understanding: Image, audio, and video analysis with backend selector routing to Gemini, OpenAI, or OpenRouter
  - Generation: Create images (gpt-image-1, Imagen), videos (Sora, Veo), and audio (TTS) with provider selection
  - New `generation/` module with modular `_image.py`, `_video.py`, `_audio.py` implementations

- **OpenRouter Tool-Capable Model Filtering**: Model list now filters to only show models supporting tool calling
  - Checks `supported_parameters` for "tools" capability before including models

### Fixed
- **Azure OpenAI Tool Calls and Workflow Integration**: Comprehensive fixes for Azure OpenAI backend
  - Parameter filtering to exclude unsupported Azure parameters (`api_version`, `azure_endpoint`, `enable_rate_limit`)
  - Fixed `tool_choice` parameter handling (only set when tools are provided)
  - Message filtering for Azure's tool message validation requirements
  - Fallback extraction for Azure's `{"content":"..."}` response format

- **Web UI Display and Cancellation**: Fixed display issues and proper cancellation handling
  - Coordination tracker display fixes
  - Proper cancellation propagation in web server

- **Docker Background Shell**: Fixed background shell execution in Docker environments

- **Docker Sudo Configuration**: Fixed `Dockerfile.sudo` configuration

### Documentations, Configurations and Resources

- **Multimodal Tools Documentation**: Updated `massgen/tool/_multimodal_tools/TOOL.md` with generation capabilities
- **Web UI Components**: New artifact renderer components in `webui/src/components/artifactRenderers/`

### Technical Details
- **Major Focus**: Multimodal backend integration, artifact preview system, Azure OpenAI compatibility
- **Contributors**: @ncrispino @shubham2345 @AbhimanyuAryan and the MassGen team

## [0.1.27] - 2025-12-19

### Added
- **Session Sharing via GitHub Gist**: Share MassGen sessions with collaborators using `massgen export` (MAS-16)
  - Uploads session logs to GitHub Gist (requires `gh` CLI authenticated)
  - Returns shareable URL to MassGen Viewer (`https://massgen.github.io/MassGen-Viewer/?gist=...`)
  - Manage shares with `massgen shares list` and `massgen shares delete <gist_id>`
  - Auto-excludes large files, debug logs, and redacts API keys
  - New `massgen/share.py` module (373 lines)
  - New `massgen/session_exporter.py` for session export logic

- **Log Analysis CLI Command**: New `massgen logs` command for analyzing run logs with metrics visualization, tool breakdown, and export to JSON/CSV formats
  - New `massgen/logs_analyzer.py` with `LogAnalyzer` class (433 lines)
  - Enhanced `massgen/cli.py` with logs subcommand integration

- **Per-LLM Call Time Tracking**: Detailed timing metrics for individual LLM API calls
  - Track time spent on each API call across all backends (Claude, Gemini, OpenAI, Grok)
  - Aggregate timing statistics in metrics summary
  - Enhanced `massgen/backend/base.py` with timing instrumentation
  - New timing fields in `massgen/backend/response.py`

- **Gemini 3 Flash Model Support**: Added `gemini-3-flash-preview` model
  - Enhanced `massgen/backend/capabilities.py` with new models and release dates
  - New config: `massgen/configs/providers/gemini/gemini_3_flash.yaml`

- **Web UI Context Paths Wizard**: New `ContextPathsStep` component in quickstart wizard for configuring file context paths

- **Web UI "Open in Browser" Button**: Added button to open workspaces directly in browser from answer views
  - Enhanced `massgen/frontend/web/server.py` with browser open endpoint

### Changed
- **CLI Config Builder Enhancements**: Per-agent web search toggles, system message configuration, and improved default model selection
  - Enhanced `massgen/config_builder.py` with `_get_provider_capabilities()` helper (+234 lines)
  - Added per-agent `enable_web_search` toggle and system message prompts during quickstart

- **Logging System Improvements**: Enhanced logger configuration with better formatting and file output (`logger_config.py`)

### Fixed
- **Web Search Call Message Preservation**: Fixed response formatter to preserve `web_search_call` messages like reasoning messages (`_response_formatter.py`)

- **Claude Code Tool Permissions**: Fixed tool allow issue for Claude Code backend
  - Fixed `massgen/backend/claude_code.py`
  - Fixed `massgen/filesystem_manager/_filesystem_manager.py`

- **Orchestrator Workflow Timeout**: Fixed timeout handling in orchestrator error respawn logic (`massgen/orchestrator.py`)

- **Workflow Restart Loop**: Fixed issue where workflow would search first then keep running into workflow restarted errors (`massgen/backend/response.py`)

### Documentations, Configurations and Resources

- **Session Sharing Documentation**:
  - Updated `docs/source/user_guide/logging.rst`: Sharing sessions guide
  - Updated `docs/source/reference/cli.rst`: Export and shares CLI reference
  - Updated `docs/source/quickstart/running-massgen.rst`: Quickstart sharing guide

- **Log Analysis Documentation**:
  - Updated `docs/source/user_guide/logging.rst`: `massgen logs` command guide

- **Configuration Examples**:
  - `massgen/configs/providers/gemini/gemini_3_flash.yaml`: Gemini 3 Flash configuration
  - `massgen/configs/debug/error_respawn_test.yaml`: Orchestrator error respawn testing

- **Web UI Components**:
  - New `webui/src/components/wizard/ContextPathsStep.tsx` (234 lines): Context paths wizard step
  - Enhanced `webui/src/stores/wizardStore.ts`: Context path state management
  - Enhanced `webui/src/components/FinalAnswerView.tsx`: Share and open in browser buttons

### Technical Details
- **Major Focus**: Session sharing, log analysis tooling, per-LLM timing, CLI config builder UX, Web UI enhancements
- **Contributors**: @ncrispino @praneeth999 and the MassGen team

## [0.1.26] - 2025-12-17

### Added
- **Docker Diagnostics Module**: Comprehensive error detection with platform-specific resolution steps for Docker issues (binary not installed, daemon not running, permission denied, images missing)

- **Web UI Setup & Configuration System**: Guided first-run experience with new `SetupPage`, `ConfigEditorModal`, `CoordinationStep` components, enhanced wizard flow, and backend API endpoints for API key management and environment checks

- **Shadow Agent Response Depth**: Test-time compute scaling via `response_depth` parameter (`low`/`medium`/`high`) controlling solution complexity in broadcast responses

### Changed
- **Model Registry Updates**: Added GPT-5.1-Codex family (`gpt-5.1-codex-max`, `gpt-5.1-codex`, `gpt-5.1-codex-mini`), updated Claude model naming to alias notation (`claude-sonnet-4-5`), changed defaults to `gpt-5.1-codex` and `claude-opus-4-5`

- **Shadow Agent Claude Code Compatibility**: Special handling for Claude Code backend conversation history in shadow agent spawning

### Fixed
- **Claude Code API Key Handling**: Fixed API key configuration and environment variable handling

- **Web UI Asset Loading**: Fixed configuration and static asset paths (MAS-160)

- **Package Dependencies**: Fixed pyproject.toml dependency specification (MAS-161)

### Documentations, Configurations and Resources

- Updated agent communication docs with response depth and Claude Code limitation notice; added Claude Code API key examples to backend docs; updated broadcast config examples with `response_depth`

### Technical Details
- **Major Focus**: Web UI setup experience, Docker diagnostics, shadow agent test-time compute scaling
- **Contributors**: @ncrispino and the MassGen team

## [0.1.25] - 2025-12-15

### Added
- **UI-TARS Custom Tool**: New custom tool for ByteDance's UI-TARS-1.5-7B model for GUI automation with vision and reasoning
  - Connects to UI-TARS via HuggingFace Inference Endpoints
  - Image understanding capabilities for browser and desktop automation workflows

- **GPT-5.2 Model Support**: Added OpenAI's latest GPT-5.2 model as new default (replacing gpt-5.1)

- **Evolving Skill Creator System**: Framework for creating and iterating on reusable workflow plans
  - Skills capture steps, Python scripts, and learnings that improve through iteration
  - Support for loading skills from previous sessions
  - Enhanced system message builder (+67 lines) and system prompt sections (+130 lines)

### Changed
- **Textual Terminal Display Enhancement**: Improved terminal UI with adaptive layouts and dark/light theming
  - Adaptive layout management for different terminal sizes and agent states
  - Enhanced modal and panel components for better agent coordination visualization

### Fixed
- **OpenRouter Gemini Reasoning Details**: Preserved reasoning_details in streaming responses for complete reasoning chain

- **LiteLLM Provider Context Paths**: Fixed file path handling for configuration and documentation references

### Documentations, Configurations and Resources

- **UI-TARS Configuration Examples**:
  - `massgen/configs/tools/custom_tools/ui_tars_browser_example.yaml`: Browser automation example
  - `massgen/configs/tools/custom_tools/ui_tars_docker_example.yaml`: Docker automation example

- **Evolving Skills Documentation**:
  - `massgen/configs/skills/skills_with_previous_sessions.yaml`: Previous session skills configuration
  - `massgen/skills/evolving-skill-creator/SKILL.md` (209 lines): Skill creator guide
  - Updated `docs/source/user_guide/tools/skills.rst` (+112 lines): Code mode guide

- **Textual Terminal Themes**:
  - `massgen/frontend/displays/textual_terminal/dark.tcss` (+164 lines)
  - `massgen/frontend/displays/textual_terminal/light.tcss` (+180 lines)

- **Documentation Updates**:
  - Updated `docs/source/reference/python_api.rst` (+158 lines): LiteLLM provider guide
  - Updated `docs/source/reference/supported_models.rst`: GPT-5.2 model entry
  - Updated `docs/source/user_guide/backends.rst` (+11 lines): Backend updates

### Technical Details
- **Major Focus**: UI-TARS computer use backend, evolving skills framework, Textual terminal UI improvements
- **Contributors**: @ncrispino @praneeth999 @franklinnwren and the MassGen team

## [0.1.24] - 2025-12-12

### Changed
- **Enhanced Cost Tracking Across Multiple Backends**: Expanded token counting and cost calculation to support additional providers
  - Added real-time token usage tracking for OpenRouter, xAI/Grok, Gemini, and Claude Code backends
  - New `/inspect` option `c` displays detailed cost breakdown with per-agent token usage (input, output, reasoning, cached)
  - Per-round token history tracking via `get_round_token_history()` method
  - Aggregated cost totals and tool metrics across all agents in coordination status
  - Improved cost ordering and formatting in display tables

### Technical Details
- **Major Focus**: Multi-backend cost tracking with real-time visibility
- **Contributors**: @ncrispino and the MassGen team

## [0.1.23] - 2025-12-10

### Added
- **Turn History Inspection System**: New `/inspect` command for reviewing agent outputs and coordination data from any turn
  - `/inspect` or `/inspect <N>` to view specific turn details with interactive menu
  - `/inspect all` to list all turns in the session with task summaries and winning agents
  - Menu options for viewing individual agent outputs, final answers, system logs, and coordination tables

- **Web UI Automation Mode**: Streamlined interface for programmatic and monitoring workflows
  - New `AutomationView` component with phase/elapsed time status header and session polling
  - `--automation` flag enables timeline-focused view with `LOG_DIR` and `STATUS` path output
  - Session persistence API (`mark_session_completed`) preserves completed sessions in session list

### Changed
- **Docker Container Persistence for Multi-Turn**: Containers now persist across turns for faster transitions
  - New `SessionMountManager` class pre-mounts session directory to Docker containers
  - Eliminates container recreation between turns (sub-second vs 2-5 second transitions)
  - Automatic visibility of new turn workspace directories without remounting

- **Multi-Turn Cancellation Handling**: Improved Ctrl+C behavior in multi-turn mode
  - Flag-based cancellation instead of raising exceptions from signal handlers
  - Coordination loop detects cancellation flag and stops Rich display before printing messages
  - Terminal state restoration via `_restore_terminal_for_input()` after display cancellation
  - Cancelled turns now build proper history entries with partial results

- **Async Execution Consistency**: New utilities for safe async-from-sync execution
  - New `run_async_safely()` helper for nested event loop handling
  - ThreadPoolExecutor pattern prevents `async generator ignored GeneratorExit` errors
  - Fixed mem0 adapter async lifecycle issues

### Documentations, Configurations and Resources

- **Multi-Turn Mode Documentation**: Updated `docs/source/user_guide/sessions/multi_turn_mode.rst` with `/inspect` command documentation, turn history inspection examples, and updated slash command reference

### Technical Details
- **Major Focus**: Async consistency, Web UI automation mode, Docker persistence for multi-turn, turn history inspection
- **Contributors**: @ncrispino and the MassGen team

## [0.1.22] - 2025-12-08

### Added
- **Shadow Agent System**: Lightweight agent clones that respond to broadcast questions without interrupting parent agents
  - New `massgen/shadow_agent.py` with `ShadowAgentSpawner` class (482 lines)
  - Shadow agents share parent's backend (stateless) and copy full conversation history
  - Includes parent's current turn context: text content, tool calls, MCP calls, and reasoning
  - Uses simplified system prompt (preserves identity, removes workflow tools)
  - Generates tool-free text responses with debug file saving support (`--debug` flag)

### Changed
- **Broadcast Channel Architecture**: Replaced inject-then-continue pattern with parallel shadow agent spawning
  - New `_spawn_shadow_agents()` method using `asyncio.gather()` for true parallelization
  - Parent agents continue working uninterrupted while shadows respond
  - Informational messages injected to parent agents after shadow responds ("FYI, you were asked X...")
  - Deprecated `respond_to_broadcast` tool (responses now automatic)

- **Agent Context Tracking**: Enhanced `SingleAgent` to track current turn state for shadow agent access
  - New attributes: `_current_turn_content`, `_current_turn_tool_calls`, `_current_turn_reasoning`, `_current_turn_mcp_calls`
  - Context cleared at start of each turn and populated during stream processing
  - Enables shadow agents to see parent's work-in-progress

### Documentations, Configurations and Resources

- **Agent Communication Documentation**: Updated `docs/source/user_guide/advanced/agent_communication.rst` with shadow agent architecture details, full context responses explanation, and deprecated `respond_to_broadcast` notice

### Technical Details
- **Major Focus**: Shadow agent architecture for non-blocking, context-aware broadcast responses
- **Contributors**: @ncrispino and the MassGen team

## [0.1.21] - 2025-12-05

### Added
- **Graceful Cancellation System**: Ctrl+C during coordination saves partial progress instead of losing work
  - New `massgen/cancellation.py` with `CancellationManager` class (177 lines)
  - First Ctrl+C saves and exits gracefully; second Ctrl+C forces immediate exit
  - In multi-turn mode, first Ctrl+C returns to prompt instead of exiting

### Changed
- **Session Restoration for Incomplete Turns**: Cancelled sessions can be resumed with `--continue`
  - Partial answers combined into conversation history with agent attribution
  - All agent workspaces preserved and provided as read-only context on resume
  - New `get_partial_result()` method in Orchestrator for mid-coordination state capture

### Documentations, Configurations and Resources

- **Graceful Cancellation Guide**: New `docs/source/user_guide/sessions/graceful_cancellation.rst` (196 lines)

### Technical Details
- **Major Focus**: Graceful cancellation with partial progress preservation for multi-turn sessions
- **Contributors**: @ncrispino and the MassGen team

## [0.1.20] - 2025-12-03

### Added
- **Web UI System**: Browser-based real-time visualization for multi-agent coordination
  - New `massgen/frontend/web/server.py` FastAPI server with WebSocket endpoints (1808 lines)
  - New `massgen/frontend/displays/web_display.py` display adapter for web streaming (730 lines)
  - React frontend with 18+ components: AgentCarousel, AnswerBrowser, Timeline, VoteVisualization
  - CLI flags: `--web`, `--web-port`, `--web-host` for launching web server
  - Quickstart wizard, real-time streaming with syntax highlighting, and multi-turn session support

### Changed
- **Automatic Computer Use Docker Setup**: Auto-creates Ubuntu 22.04 container with Xfce desktop for GUI automation
  - New `setup_computer_use_docker()` function with auto-detection of `computer_use_docker_example` configs
  - Container includes X11 virtual display (:99), xdotool, Firefox, Chromium, and scrot

- **Response API Formatter Enhancement**: Improved function call handling for multi-turn contexts
  - Preserves `function_call` entries and generates stub outputs for calls without recorded responses

### Fixed
- **Web UI Multi-turn Support**: Fixed frontend session continuation and follow-up question handling
- **Timeline Tracking**: Fixed timeline arrows and backend event sequencing

### Documentations, Configurations and Resources

- **Web UI Guide**: New `docs/source/user_guide/webui.rst` (250 lines) covering display modes, timeline visualization, and workspace browsing

- **Computer Use Documentation**: Enhanced `docs/source/user_guide/advanced/computer_use.rst` (+66 lines) with environment naming conventions and automatic setup instructions

- **Filesystem-First Mode Documentation**: New `docs/source/user_guide/filesystem_first.rst` (872 lines, experimental v0.2.0+) documenting 98% context reduction via on-demand tool discovery

- **LLM Council Comparison**: New `docs/source/reference/comparisons.rst` (155 lines) comparing MassGen vs LLM Council with feature tables, UI differences, and architectural comparisons

### Technical Details
- **Major Focus**: Web UI for real-time coordination visualization, automatic Docker setup for computer use agents
- **Contributors**: @voidcenter @ncrispino @praneeth999 and the MassGen team

## [0.1.19] - 2025-12-01

### Added
- **LiteLLM Integration & Programmatic API**: MassGen as a LiteLLM custom provider with direct Python interface
  - New `massgen/litellm_provider.py` with `MassGenLLM` class and `register_with_litellm()` (452 lines)
  - New `run()` and `build_config()` functions for programmatic execution without CLI
  - Model string formats: `massgen/<example>`, `massgen/model:<model>`, `massgen/path:<config>`, `massgen/build`
  - New `NoneDisplay` silent display class for suppressing output in programmatic/LiteLLM use
  - Auto-detection of backends from model names (e.g., `gpt-5` → openai, `claude-sonnet-4-5` → claude)

### Changed
- **Claude Strict Tool Use & Structured Outputs**: Enhanced Claude backend with schema validation and improved defaults
  - New `enable_strict_tool_use` config flag with recursive `additionalProperties: false` patching
  - New `output_schema` parameter for structured JSON outputs (requires Sonnet 4.5 or Opus 4.1)
  - Per-tool opt-out via `strict: false` on individual tools
  - Increased default max_tokens and improved tool_result handling
  - ConfigValidator validation for `enable_strict_tool_use` and `output_schema` fields

- **Gemini Exponential Backoff**: Automatic retry mechanism for rate limit errors
  - New `BackoffConfig` dataclass with configurable retry parameters
  - Handles HTTP 429 (rate limit) and 503 (service unavailable) with jittered backoff
  - `Retry-After` header support and Gemini-specific error pattern matching

### Documentations, Configurations and Resources

- **Documentation Reorganization**: Major restructure into `files/`, `tools/`, `integration/`, `sessions/`, and `advanced/` sections with streamlined quickstart guides

- **Configuration Examples**: `massgen/configs/providers/claude/strict_tool_use_example.yaml` for strict tool use with custom and MCP tools

### Technical Details
- **Major Focus**: LiteLLM provider integration, Claude strict tool use with structured outputs, Gemini rate limit resilience
- **Contributors**: @ncrispino @praneeth999 and the MassGen team

## [0.1.18] - 2025-11-28

### Added
- **Agent Communication System**: Agents can now ask questions to other agents and optionally humans via the `ask_others()` tool
  - Three modes: disabled (default), agent-to-agent only (`broadcast: "agents"`), or human-only (`broadcast: "human"`)
  - Blocking execution with inline response delivery into agent context
  - Human interaction UI with timeout, skip options, and session-persistent Q&A history
  - Rate limiting and serialized calls to prevent spam and duplicate prompts
  - Comprehensive event tracking in coordination logs

- **Claude Programmatic Tool Calling**: Code execution can now invoke custom and MCP tools programmatically
  - New `enable_programmatic_flow` backend flag that automatically enables code execution sandbox
  - Custom and MCP tools callable from Claude's code sandbox via `allowed_callers` marking
  - Requires claude-opus-4-5 or claude-sonnet-4-5 models with streaming indicators for invocations

- **Claude Tool Search (Deferred Loading)**: Server-side tool discovery for large tool sets
  - New `enable_tool_search` flag with `tool_search_variant` option (`"regex"` or `"bm25"`)
  - Tools with `defer_loading: true` discovered on-demand, reducing initial context size
  - Per-tool and per-MCP-server override support with streaming indicators

### Changed
- **Backend Capabilities Enhancement**: Added tool search and programmatic flow capability flags to `massgen/backend/capabilities.py` (+17 lines)
- **ConfigValidator Enhancement**: Added `enable_programmatic_flow` and `enable_tool_search` boolean field validation (+2 lines)

### Documentations, Configurations and Resources

- **Claude Advanced Tooling Guide**: New `docs/claude-advanced-tooling.md` covering model requirements, API betas, configuration examples, and streaming cues
- **Agent Communication Documentation**: New `docs/source/user_guide/agent_communication.rst` with broadcast modes, serialization, Q&A history, and examples
- **Configuration Examples**:
  - `massgen/configs/providers/claude/programmatic_with_two_tools.yaml` - Programmatic tool calling with custom and MCP tools
  - `massgen/configs/providers/claude/tool_search_example.yaml` - Tool search with visible and deferred tools
  - `massgen/configs/broadcast/test_broadcast_agents.yaml` - Agent-to-agent broadcast communication
  - `massgen/configs/broadcast/test_broadcast_human.yaml` - Human broadcast communication with Q&A prompts

### Technical Details
- **Major Focus**: Agent communication system with human broadcast support, Claude programmatic tool calling from code execution, Claude tool search for deferred tool discovery
- **Contributors**: @ncrispino @praneeth999 and the MassGen team

## [0.1.17] - 2025-11-26

### Added
- **Textual Terminal Display System**: Interactive terminal UI using the Textual library for enhanced agent coordination visualization
  - New `massgen/frontend/displays/textual_terminal_display.py` (1673 lines)
  - Multi-panel layout with dedicated views for each agent and orchestrator status
  - Real-time streaming content display with syntax highlighting support
  - Emoji fallback mapping for terminals without Unicode support
  - Content filtering for critical patterns (votes, status changes, tools, presentations)
  - Keyboard shortcuts for display interaction and safe keyboard mode
  - Automatic file output with session logging to agent-specific files
  - Thread-safe display updates with buffered content batching

- **Dark and Light Themes**: TCSS stylesheets for customizable terminal appearance
  - New `massgen/frontend/displays/textual_themes/dark.tcss` (322 lines)
  - New `massgen/frontend/displays/textual_themes/light.tcss` (322 lines)
  - VS Code-inspired color schemes with styled containers for post-evaluation and final stream panels

### Changed
- **CoordinationUI Enhancement**: Extended display coordination with Textual Terminal support
  - Enhanced `massgen/frontend/coordination_ui.py` with Textual display integration (+348 lines)
  - New `textual_terminal` display type option alongside existing rich_terminal and simple displays
  - Automatic fallback when Textual library is not available
  - Unified reasoning content processing across all display types

- **Display Module Restructuring**: Improved display initialization and base class architecture
  - Enhanced `massgen/frontend/displays/__init__.py` with Textual display exports (+30 lines)
  - Enhanced `massgen/frontend/displays/terminal_display.py` with shared base functionality (+45 lines)
  - Better separation of concerns between display implementations

### Documentations, Configurations and Resources

- **Textual Configuration Example**: Reference configuration for Textual terminal display
  - New `massgen/configs/basic/single_agent_textual.yaml` (17 lines)

- **Dependencies**: Added Textual library for modern terminal UI
  - Updated `pyproject.toml` and `requirements.txt` with `textual>=0.47.0`

### Technical Details
- **Major Focus**: Textual Terminal Display for enhanced agent coordination visualization with theme support
- **Contributors**: @praneeth999 and the MassGen team

## [0.1.16] - 2025-11-24

### Added
- **Terminal Evaluation System**: Automated terminal session recording and AI-powered evaluation using VHS
  - New `docs/source/user_guide/terminal_evaluation.rst` comprehensive evaluation guide (450 lines)
  - New `massgen/tests/test_terminal_evaluation.py` with test suite (336 lines)
  - New `massgen/tests/demo_terminal_evaluation.py` demonstration script (210 lines)
  - Records terminal sessions as GIFs using VHS (Video Home System)
  - Analyzes session recordings with multimodal models (GPT-4.1, Claude)
  - Evaluates agent performance, UI quality, and interaction patterns
  - Automated testing workflows for continuous quality monitoring

- **LiteLLM Cost Tracking Integration**: Accurate cost calculation using LiteLLM's pricing database
  - New `calculate_cost_with_usage_object()` in `massgen/token_manager/token_manager.py` (+178 lines)
  - New `docs/dev_notes/litellm_cost_tracking_integration.md` design documentation (581 lines)
  - New `massgen/tests/test_litellm_integration.py` comprehensive test suite (331 lines)
  - New `massgen/tests/test_backend_cost_tracking.py` integration tests (183 lines)
  - Integrates LiteLLM pricing database covering 500+ models with auto-updates
  - Handles reasoning tokens for o1/o3 models with separate pricing
  - Handles cached tokens for Claude and OpenAI prompt caching
  - Fallback to legacy calculation when LiteLLM unavailable
  - More accurate cost estimates than manual price tables

- **Memory Archiving System**: Persistent memory with multi-turn session support
  - Enhanced `massgen/orchestrator.py` with memory archiving capabilities (+51 lines)
  - Enhanced `massgen/system_message_builder.py` with archive management (+170 lines)
  - Enhanced `massgen/system_prompt_sections.py` with archiving instructions (+201 lines)
  - Enhanced `massgen/cli.py` with session continuation support (+15 lines)
  - Enables archiving long-term memory for session persistence
  - Supports multi-turn conversations with memory continuity
  - Improved memory retrieval and context management

- **MassGen Self-Evolution Skills**: Skills for MassGen to develop and maintain itself
  - New `massgen/skills/massgen-config-creator/SKILL.md` for creating valid YAML configurations (183 lines)
  - New `massgen/skills/massgen-develops-massgen/SKILL.md` for self-improvement and feature development (490 lines)
  - New `massgen/skills/massgen-release-documenter/SKILL.md` for changelog and documentation updates (252 lines)
  - New `massgen/skills/model-registry-maintainer/SKILL.md` for maintaining model registry (483 lines)
  - Enables MassGen to maintain its own codebase and documentation
  - Self-documenting release workflows
  - Automated configuration validation and generation
  - Model registry updates with pricing and capability tracking

### Changed
- **Docker Infrastructure Enhancement**: Parallel image pulling, VHS recording support, and improved container management
  - Enhanced `massgen/cli.py` with parallel Docker image pulling (+242 lines)
  - Enhanced `massgen/docker/Dockerfile` with VHS installation and improved build process (+44 lines total)
  - Enhanced `massgen/docker/Dockerfile.sudo` with VHS support and enhanced permissions (+47 lines total)
  - Enhanced `massgen/filesystem_manager/_filesystem_manager.py` with VHS utilities and better Docker integration (+50 lines)
  - Parallel pulling of multiple Docker images for faster setup
  - VHS (Video Home System) integration for terminal session recording in Docker containers
  - Better error handling and progress reporting
  - Improved Docker container lifecycle management

- **Model Registry Updates**: Expanded model support with accurate pricing and metadata
  - Enhanced `massgen/backend/capabilities.py` with new models and release dates (+45 lines)
  - Added Grok 4.1 family models (grok-4.1, grok-4.1-mini) with pricing
  - Added GPT-4.1 family models for terminal evaluation
  - Added release dates to all models in BACKEND_CAPABILITIES
  - Removed o4 models (don't exist in production)
  - Removed unsupported Gemini experimental models
  - Improved model metadata for better cost tracking

- **Configuration Builder Enhancement**: Improved model selection and configuration workflow
  - Enhanced `massgen/config_builder.py` with better model defaults (+73 lines)
  - Enhanced `massgen/cli.py` with improved config selection interface (+65 lines)
  - Better model recommendations based on use case
  - Improved validation and error messages

### Fixed
- **Status Mode Log Directory**: Fixed missing log directory creation in status mode
  - Fixed `massgen/cli.py` to create log directories before writing
  - Prevents errors when running in status/automation mode

- **Filesystem Docker Zod Schema**: Resolved MCP tool argument parsing in Docker
  - Enhanced `massgen/backend/chat_completions.py` with schema validation (+16 lines)
  - Enhanced `massgen/backend/claude_code.py` with improved MCP handling (+13 lines)
  - Enhanced `massgen/mcp_tools/security.py` with schema fixes (+2 lines)
  - Fixed Zod schema errors preventing proper tool call execution
  - MCP tools now correctly parse arguments in Docker filesystem mode

### Documentations, Configurations and Resources

- **Terminal Evaluation Documentation**: Complete guide for automated terminal testing
  - New `docs/source/user_guide/terminal_evaluation.rst` with setup and usage (450 lines)
  - Covers VHS configuration, recording workflows, evaluation strategies
  - Best practices for multimodal session analysis

- **Memory Filesystem Mode Enhancement**: Expanded documentation for memory integration
  - Updated `docs/source/user_guide/memory_filesystem_mode.rst` with archiving workflows (+172 lines)
  - Documents memory persistence across sessions
  - Multi-turn conversation patterns with memory continuity
  - Best practices for long-running agent interactions

- **Skills Documentation Updates**: Enhanced skills guide with self-evolution examples
  - Updated `docs/source/user_guide/skills.rst` with MassGen self-evolution skills (+178 lines)
  - Documents the four new MassGen-specific skills
  - Examples of self-maintaining systems
  - Guidelines for creating meta-skills

- **Custom Tools Documentation**: Improved custom tools integration guide
  - Updated `docs/source/user_guide/custom_tools.rst` with terminal evaluation examples (+103 lines)
  - Documents VHS integration patterns
  - Best practices for recording and evaluation tools

- **Configuration Examples**: New YAML configurations for v0.1.16 features
  - New `massgen/configs/meta/massgen_evaluates_terminal.yaml` for terminal evaluation (72 lines)
  - New `massgen/configs/tools/custom_tools/terminal_evaluation.yaml` example config (88 lines)
  - Updated `massgen/configs/skills/test_memory.yaml` with memory archiving examples
  - Updated `massgen/configs/tools/filesystem/code_based/example_code_based_tools.yaml` with Docker improvements

### Technical Details
- **Major Focus**: Terminal evaluation infrastructure, LiteLLM cost tracking integration, memory archiving system, MassGen self-evolution capabilities
- **Contributors**: @ncrispino and the MassGen team

## [0.1.15] - 2025-11-21

### Added
- **Persona Generation System**: Automatic generation of diverse system messages for multi-agent configurations
  - New `massgen/persona_generator.py` for LLM-powered persona creation (365 lines)
  - Enhanced `massgen/orchestrator.py` with persona generation orchestration (+122 lines)
  - Enhanced `massgen/agent_config.py` with persona configuration support (+5 lines)
  - Enhanced `massgen/cli.py` with `--generate-personas` flag (+54 lines)
  - Multiple generation strategies: complementary, diverse, specialized, adversarial
  - Configurable backend for persona generation (defaults to gpt-4o-mini)
  - Custom persona guidelines support for domain-specific generation
  - Increases response diversity without manual system message crafting

### Changed
- **Docker Distribution & Custom Tools Enhancement**: GitHub Container Registry integration with custom tools support
  - Enhanced `.github/workflows/docker-publish.yml` with comprehensive CI/CD pipeline (+96 lines)
  - Enhanced `massgen/docker/Dockerfile` and `Dockerfile.sudo` with MassGen pre-installation (+13 lines each)
  - Enhanced `massgen/filesystem_manager/_docker_manager.py` with improved container management (+37 lines)
  - Enhanced `massgen/cli.py` with Docker-related commands and improvements (+104 lines)
  - Custom tools can now run in isolated Docker containers for security and portability (Issue #510)
  - ARM architecture support for Apple Silicon and ARM-based cloud instances
  - Automated Docker image pruning during CI builds

- **Config Builder Enhancement**: Improved interactive configuration experience
  - Enhanced `massgen/config_builder.py` with better model selection and defaults (+17 lines)

### Documentations, Configurations and Resources

- **Installation Documentation Overhaul**: Comprehensive Docker and setup guides
  - Updated `docs/source/quickstart/installation.rst` with Docker installation instructions (+150 lines)
  - Updated `docs/source/index.rst` with improved getting started guide (+66 lines)
  - Detailed GitHub Container Registry pull instructions
  - Platform-specific Docker setup guidance

- **Persona Generation Configuration Example**: Reference configuration for persona diversity
  - New `massgen/configs/basic/multi/persona_diversity_example.yaml` with strategy and backend configuration (123 lines)

- **Pre-commit Hooks Enhancement**: Additional code quality checks
  - New `scripts/precommit_check_package_name.py` for package name validation (39 lines)
  - Updated `.pre-commit-config.yaml` with package name check (+6 lines)

### Technical Details
- **Major Focus**: Persona generation for agent diversity, Docker distribution improvements, GitHub Container Registry integration
- **Contributors**: @ncrispino and the MassGen team


## [0.1.14] - 2025-11-19

### Added
- **Parallel Tool Execution System**: Configurable concurrent tool execution across all backends with asyncio-based scheduling
  - New `concurrent_tool_execution` configuration parameter for local parallel execution control
  - New `parallel_tool_calls` parameter support for OpenAI Response API (controls model behavior)
  - New `disable_parallel_tool_use` parameter for Claude backend (inverse toggle for tool parallelism)
  - New `max_concurrent_tools` semaphore limit for execution speed control (default: 10)
  - Enhanced `massgen/backend/response.py` with parallel execution infrastructure (+239 lines)
  - Enhanced `massgen/backend/base_with_custom_tool_and_mcp.py` with `_execute_tool_calls` method (+186 lines)
  - Enhanced `massgen/api_params_handler/_response_api_params_handler.py` with parameter handling (+20 lines)
  - Unified handling of custom and MCP tool calls with optional concurrent execution
  - Works with Response, ChatCompletions, Gemini, and Claude backends
  - Model-level controls (parallel_tool_calls) separate from local execution controls (concurrent_tool_execution)

- **Gemini 3 Pro Model Support**: Full integration for Google's Gemini 3 Pro model with function calling
  - Enhanced `massgen/backend/gemini.py` with Gemini 3 Pro compatibility (60 lines modified)
  - Fixed function calling behavior specific to Gemini 3 Pro model
  - Native support for Gemini's parallel function calling capabilities

### Changed
- **Config Builder Enhancement**: Interactive quickstart workflow with guided configuration creation
  - Enhanced `massgen/config_builder.py` with interactive prompts and improved UX (+394 lines)
  - Enhanced `massgen/cli.py` with quickstart command integration and improved interface (+214 lines)
  - Enhanced `massgen/backend/capabilities.py` with model metadata (+3 lines)
  - Streamlined onboarding experience from setup to first run
  - Improved provider selection and configuration validation
  - Better integration with config selection workflow
  - Better error messages and user guidance
  - Previously introduced in v0.1.9, now significantly enhanced for user experience

- **MCP Registry Client**: Enhanced MCP server metadata fetching with official registry integration
  - New `massgen/mcp_tools/registry_client.py` for fetching server descriptions from official MCP registry (358 lines)
  - New `massgen/tests/test_mcp_registry_client.py` comprehensive test suite (184 lines)
  - Enhanced `massgen/mcp_tools/security.py` with registry integration (+49 lines)
  - Fetches metadata from https://registry.modelcontextprotocol.io/v0/servers
  - Enhances system prompts with server descriptions for better agent understanding
  - Builds upon v0.1.13's MCP server registry (server_registry.py) with external registry support

- **Planning System Enhancements**: Improved skill and tool search capabilities in planning mode
  - Enhanced `massgen/mcp_tools/planning/_planning_mcp_server.py` with better search logic (+44 lines)
  - Enhanced `massgen/system_prompt_sections.py` with refined planning prompts (+34 lines)
  - Enhanced `massgen/orchestrator.py` with planning coordination (+21 lines)
  - Enhanced `massgen/system_message_builder.py` with planning context (+12 lines)
  - PR #534: Commit 98b1ec6f
  - Better discovery of available skills and tools during planning phase
  - Improved agent decision-making for tool selection
  - More accurate task decomposition with tool awareness

- **NLIP Routing Streamlining**: Simplified and unified NLIP execution flow across backends
  - Refactored `massgen/backend/response.py` with streamlined routing (net -209 lines)
  - Refactored `massgen/backend/claude.py` with unified handling (+98 lines modified)
  - Refactored `massgen/backend/gemini.py` with consistent patterns (+178 lines modified)
  - Unified custom and MCP tool call handling with improved NLIP routing
  - Reduced code complexity while maintaining full NLIP functionality
  - Better error handling and async management in NLIP message routing
  - Builds upon v0.1.13's NLIP integration with cleaner implementation

- **Coordination Tracking Enhancement**: Improved status monitoring for automation workflows
  - Enhanced `massgen/coordination_tracker.py` with parallel tool execution tracking (+23 lines)
  - Better visibility into concurrent tool execution status for automation mode

### Documentations, Configurations and Resources

- **Parallel Tool Execution Configuration Guide**: Comprehensive documentation for tool execution parallelism
  - New `docs/parallel-tool-execution.md` complete configuration reference (179 lines)
  - Explains model-level vs. local execution controls
  - Backend-specific configuration examples for OpenAI, Claude, Gemini
  - Quick reference for all parallelism-related parameters
  - Execution flow diagrams and best practices

- **Configuration Examples**: New YAML configurations demonstrating v0.1.14 features
  - `massgen/configs/tools/custom_tools/gpt5_nano_custom_tool_with_mcp_parallel.yaml`: Parallel tool execution example with configurable concurrency
  - `massgen/configs/tools/filesystem/code_based/example_code_based_tools.yaml`: Updated with enhanced instructions for code-based tools (+52 lines)
  - `massgen/configs/providers/gemini/gemini_3_pro.yaml`: Configuration template for Gemini 3 Pro model (30 lines)

- **CI/CD Workflow Configuration**: Docker image publishing automation
  - `.github/workflows/docker-publish.yml`: Automated Docker build and publish workflow for releases (60 lines)
  - Integration with GitHub Container Registry for automated container deployment

- **Docker Configuration Updates**: Enhanced Docker setup for development and deployment
  - `massgen/docker/Dockerfile`: Improvements for standard Docker builds (+7 lines)
  - `massgen/docker/Dockerfile.sudo`: Enhanced sudo mode support (+7 lines)

### Technical Details
- **Major Focus**: Parallel tool execution infrastructure, interactive quickstart experience, MCP registry client integration, Gemini 3 Pro support, NLIP routing optimization
- **Contributors**: @praneeth999 @ncrispino and the MassGen team

## [0.1.13] - 2025-11-17

### Added
- **Code-Based Tools System (CodeAct Paradigm)**: Tool integration via importable Python code instead of schema-based tools
  - New `massgen/filesystem_manager/_tool_code_writer.py` for writing MCP tool wrappers to workspace (450 lines)
  - New `massgen/mcp_tools/code_generator.py` for generating Python wrapper code from MCP schemas (507 lines)
  - New `massgen/mcp_tools/server_registry.py` for MCP server catalog with auto-discovery (205 lines)
  - Enhanced `massgen/filesystem_manager/_filesystem_manager.py` with code-based tools setup (+562 lines)
  - Agents import and use tools as native Python functions with type hints and docstrings
  - Reduces token usage by 98% through on-demand tool loading (Anthropic research)
  - Pre-configured registry with popular MCP servers (Playwright, GitHub, Context7, Memory)
  - Auto-discovery eliminates manual MCP server configuration

- **NLIP (Natural Language Interface Protocol) Integration**: Advanced tool routing with natural language interface
  - Enhanced `massgen/backend/response.py` with NLIP routing infrastructure (+134 lines)
  - Enhanced `massgen/backend/claude.py`, `gemini.py`, `chat_completions.py` with NLIP support (+255 lines total)
  - Enhanced `massgen/orchestrator.py` with orchestrator-level NLIP configuration (+48 lines)
  - Routes tool execution requests through natural language interface
  - Multi-backend support across Claude, Gemini, and OpenAI
  - Per-agent or orchestrator-level configuration with fallback to direct execution
  - Enables natural language task decomposition and intelligent tool selection

- **Skills Installation System**: Cross-platform automated skills installer
  - New `massgen/utils/skills_installer.py` for automated skills installation (350 lines)
  - New `scripts/init_skills.sh` and `scripts/init.sh` for shell-based setup (650 lines total)
  - **`massgen --setup-skills` command** for one-command installation
  - Installs openskills CLI, Anthropic skills collection, and Crawl4AI skill
  - Cross-platform support: Windows, macOS, Linux with idempotent installation
  - Comprehensive progress indicators and error handling

### Changed
- **Tool Size & Command-Line Enhancements**: Increased tool capacity and improved CLI execution
  - Updated `massgen/backend/utils.py` tool truncation threshold from 10,000 to 15,000 characters
  - Enhanced `massgen/backend/bash_cli.py` with command-line-only mode improvements
  - Commit: b51067b8 "Command line only mode; increase tool size from 10k to 15k"
  - Allows more comprehensive tool documentation and examples
  - Improved command parsing and error handling
  - Better integration with code-based tools workflow

- **Exclude File Operation MCPs**: Removed filesystem MCP tools in favor of native file operations
  - Updated `massgen/mcp_tools/mcp_manager.py` to exclude `@modelcontextprotocol/server-filesystem` (+204 lines)
  - Commit: 5bdf46bf "Adjusted prompts and added TOOL.md for custom tools"
  - Prevents redundancy with MassGen's built-in filesystem operations
  - Reduces token usage from duplicate tool definitions
  - Clearer tool usage patterns for agents

### Documentations, Configurations and Resources

- **TOOL.md Documentation System**: Standardized documentation format for custom tools
  - New `massgen/tool/_video_tools/TOOL.md` for video tools documentation (161 lines)
  - New `massgen/tool/_web_tools/TOOL.md` for web scraping tools documentation (161 lines)
  - New `massgen/tool/_playwright_mcp/TOOL.md` for Playwright MCP documentation (201 lines)
  - **Standardized structure**: name, description, category, tasks, keywords, usage examples
  - Frontmatter metadata in YAML format for tool discovery
  - Clear "When to Use This Tool" and "When NOT to Use" sections
  - Function signatures with parameter descriptions and return types
  - Configuration prerequisites and setup instructions
  - Common use cases and limitations documentation
  - Enables agents to understand tool capabilities and make informed decisions
  - Total: 12 new TOOL.md files across custom tools directory (~3,800 lines)

- **Configuration Examples**: New YAML configurations for v0.1.13 features
  - `massgen/configs/tools/filesystem/code_based/example_code_based_tools.yaml`: Code-based tools with auto-discovery and shared tools directory (153 lines)
  - `massgen/configs/tools/filesystem/exclude_mcps/test_minimal_mcps.yaml`: Minimal MCPs with command-line file operations and memory filesystem mode (37 lines)
  - `massgen/configs/examples/nlip_basic.yaml`: Basic NLIP protocol support with router and translation settings (54 lines)
  - `massgen/configs/examples/nlip_openai_weather_test.yaml`: OpenAI with NLIP integration for custom tools and MCP servers (36 lines)
  - `massgen/configs/examples/nlip_orchestrator_test.yaml`: Orchestrator-level NLIP configuration for multi-agent coordination (47 lines)

- **Skills Installation Documentation**: Comprehensive guides for skills setup
  - Updated `scripts/init.sh` with detailed help text and options (438 lines)
  - Updated `scripts/init_skills.sh` with skip flags for selective installation (212 lines)
  - Examples: `./init.sh --skip-docker`, `./init_skills.sh --skip-anthropic`

- **Code-Based Tools User Guide**: Complete documentation for CodeAct paradigm implementation
  - New `docs/source/user_guide/code_based_tools.rst` (726 lines)
  - Quick start examples and configuration
  - Explains 98% context reduction benefit (Anthropic research)
  - Covers workspace structure, Python wrapper generation, async workflows
  - Real-world examples: weather forecasting, GitHub integration, multi-tool composition

- **MCP Server Registry Reference**: Documentation for built-in MCP server catalog
  - New `docs/source/reference/mcp_server_registry.rst` (219 lines)
  - Documents all pre-configured MCP servers (Context7, GitHub, Filesystem, Memory, etc.)
  - Connection examples and tool listings
  - API key requirements and configuration
  - Auto-discovery setup instructions

- **Installation Guide Updates**: Enhanced setup documentation with automation scripts
  - Updated `docs/source/quickstart/installation.rst` (+115 lines)
  - Automated development setup using `scripts/init.sh`
  - Script options and flags documentation
  - System requirements and verification steps
  - Windows support roadmap notes

- **Documentation Updates**: Enhanced existing guides with v0.1.13 features
  - Updated `docs/source/user_guide/file_operations.rst` (+44 lines) - Code-based tools integration
  - Updated `docs/source/user_guide/mcp_integration.rst` (+71 lines) - Registry and auto-discovery
  - Updated `docs/source/reference/yaml_schema.rst` (+5 lines) - Code-based tools configuration options

### Technical Details
- **Major Focus**: CodeAct paradigm implementation, MCP registry infrastructure, skills installation automation, TOOL.md documentation standard, self-evolution capabilities, NLIP integration
- **Contributors**: @qidanrui @ncrispino @franklinnwren @praneeth999 and the MassGen team

## [0.1.12] - 2025-11-14

### Added
- **Semtools Skill**: Semantic search capabilities using embedding-based similarity matching
  - New `massgen/skills/semtools/SKILL.md` for meaning-based code and document search (606 lines)
  - Rust-based CLI for high-performance semantic search beyond keyword matching
  - Workspace management for indexing large codebases with fast repeated searches
  - Document parsing support for PDFs, DOCX, PPTX with optional API integration
  - Discovery-focused search finding relevant code without knowing exact keywords
  - Complements traditional ripgrep (keyword) and ast-grep (syntax) search tools

- **Serena Skill**: Symbol-level code understanding via Language Server Protocol (LSP)
  - New `massgen/skills/serena/SKILL.md` for IDE-like semantic code analysis (499 lines)
  - Symbol discovery across 30+ programming languages (classes, functions, variables, types)
  - Reference tracking to find all usage locations of symbols
  - Precise code editing with surgical symbol-level insertions
  - LSP-powered understanding of code structure, scope, and relationships
  - Enables symbol-aware refactoring and navigation capabilities

- **System Message Builder**: New modular system for constructing agent prompts
  - New `massgen/system_message_builder.py` for flexible prompt composition (488 lines)
  - Separates prompt construction logic from orchestrator
  - Enables better organization and reusability of system prompt components
  - Foundation for improved prompt engineering and customization

### Changed
- **System Prompt Architecture**: Complete refactoring for improved LLM attention and effectiveness
  - Enhanced `massgen/system_prompt_sections.py` with hierarchical prompt structure (1286 lines)
  - Reorganized prompt ordering to place critical instructions (skills, memory) at optimal positions
  - Reduced message template redundancy in `message_templates.py` (-682 lines)
  - Simplified orchestrator prompt assembly in `orchestrator.py` (-428 lines)
  - Applied 2025 prompt engineering best practices: XML structure, attention management, priority signaling
  - Improved skills and memory system visibility to agents through better positioning

- **Skills System Refactoring**: Enhanced architecture with local execution support
  - **Local Mode**: Skills can now execute directly without Docker containers
  - **Directory Reorganization**: Moved file-search from `skills/always/file_search/` to `skills/file-search/`
  - **Semantic Search Skills**: Promoted semtools and serena from optional to core skills directory
  - Enhanced `massgen/filesystem_manager/skills_manager.py` for local execution support
  - Enhanced `massgen/filesystem_manager/_code_execution_server.py` for local skill commands (+71 lines)
  - Enhanced `massgen/filesystem_manager/_filesystem_manager.py` with local mode capabilities (+173 lines)
  - Enhanced `massgen/filesystem_manager/_docker_manager.py` for skills integration (+59 lines)
  - Updated `massgen/backend/claude_code.py` for local skill execution (+26 lines)

- **Gemini Computer Use Tool**: Multi-agent support with Docker integration
  - Enhanced `massgen/tool/_gemini_computer_use/gemini_computer_use_tool.py` (949 lines total, +446 lines)
  - Added Docker container support for browser and desktop automation
  - New screenshot capture functions for Docker environments (`take_screenshot_docker`)
  - New action execution system for Docker (`execute_docker_action`)
  - X11 display integration with xdotool for precise control
  - VNC compatibility for remote visualization and debugging
  - Multi-agent coordination capabilities for collaborative computer use

- **Browser Automation Tool**: Enhanced screenshot management
  - Updated `massgen/tool/_browser_automation/browser_automation_tool.py` to save screenshots as files (+39 lines)
  - New `output_filename` parameter to save screenshots directly to agent workspace
  - Automatic workspace path resolution with `agent_cwd` parameter
  - Reduces token usage by avoiding base64-encoded screenshot returns
  - Better integration with file-based workflows and serena skill

### Documentations, Configurations and Resources

- **System Prompt Architecture Documentation**: Comprehensive design document for prompt refactoring
  - New `docs/dev_notes/system_prompt_architecture_redesign.md` (593 lines)
  - Documents LLM attention management and hierarchical structure principles
  - Explains XML-based prompt engineering for Claude models
  - Covers priority signaling and position-based emphasis strategies
  - Implementation roadmap for future prompt improvements

- **Computer Use Visualization Guide**: Multi-agent computer use documentation
  - New `docs/backend/docs/COMPUTER_USE_VISUALIZATION.md` (455 lines)
  - Covers VNC setup and remote visualization workflows
  - Documents multi-agent coordination patterns for computer use
  - Troubleshooting guide for Docker-based automation
  - Architecture diagrams for computer use tool integration

- **Skills Documentation Update**: Enhanced skills system guide
  - Updated `docs/source/user_guide/skills.rst` with local mode documentation (+222 lines)
  - Covers new semantic search skills (semtools/serena)
  - Documents skill directory reorganization
  - Local vs Docker execution trade-offs and best practices

- **YAML Schema Documentation**: Configuration reference updates
  - Updated `docs/source/reference/yaml_schema.rst` with skills configuration options (+36 lines)
  - Documents local mode parameters and skill settings

- **Computer Use Tools Guide**: Enhanced documentation
  - Updated `docs/backend/docs/COMPUTER_USE_TOOLS_GUIDE.md` with Gemini Docker support (+94 lines)
  - Multi-agent computer use configuration examples
  - VNC viewer setup instructions

- **Configuration Examples**: New YAML configurations for v0.1.12 features
  - `massgen/configs/tools/custom_tools/multi_agent_computer_use_example.yaml`: Multi-agent coordination for computer use (194 lines)
  - `massgen/configs/tools/custom_tools/gemini_computer_use_docker_example.yaml`: Gemini with Docker automation (84 lines)
  - Updated `massgen/configs/tools/custom_tools/simple_browser_automation_example.yaml`: File-based screenshot workflow

- **VNC Viewer Script**: Automated VNC setup for computer use visualization
  - New `scripts/enable_vnc_viewer.sh` for quick VNC configuration (40 lines)
  - Streamlines Docker-based computer use debugging and monitoring

### Technical Details
- **Major Focus**: System prompt architecture refactoring, semantic search skills (semtools/serena), local skill execution, multi-agent computer use with Docker
- **Contributors**: @ncrispino @franklinnwren @Henry-811 and the MassGen team

## [0.1.11] - 2025-11-12

### Added
- **Skills System**: Modular prompting framework for enhancing agent capabilities
  - New `SkillsManager` class in `massgen/filesystem_manager/skills_manager.py` for dynamic skill loading and injection (158 lines)
  - **File Search Skill**: Always-available skill for searching files and code across workspace (`massgen/skills/always/file_search/SKILL.md`, 280 lines)
  - Automatic skill discovery and loading from `massgen/skills/` directory structure
  - Docker-compatible skill mounting and environment setup
  - Skills organized into `always/` (auto-included) and `optional/` categories
  - Flexible skill injection into agent system prompts via orchestrator
  - Configuration examples in `massgen/configs/skills/` (skills_basic.yaml, skills_existing_filesystem.yaml, skills_with_memory.yaml)

- **Memory MCP Tool & Filesystem Integration**: MCP server for agent memory management with filesystem persistence and combined workflows
  - New `massgen/mcp_tools/memory/` module with memory MCP server implementation (513 lines total)
  - **MemoryMCPServer** in `_memory_mcp_server.py` (352 lines) for memory CRUD operations with automatic filesystem sync
  - **Memory data models** in `_memory_models.py` (161 lines) with short-term and long-term memory tiers
  - Memory persistence to workspace under `memory/short_term/` and `memory/long_term/` directories
  - Markdown-based memory storage format for human readability
  - Integration with orchestrator for cross-agent memory sharing (+218 lines in orchestrator.py)
  - Memory-specific message templates for memory operations (+95 lines in message_templates.py)
  - **Combined workflows**: Simultaneous use of memory MCP tools and filesystem operations for advanced workflows
  - Enables agents to maintain persistent memory while manipulating files
  - Configuration examples demonstrating integrated workflows for long-running projects requiring both code changes and learned context
  - Inspired by Letta's context hierarchy design pattern

- **Rate Limiting System (Gemini)**: Multi-dimensional rate limiting for Gemini API calls and agent startup
  - New `massgen/backend/rate_limiter.py` (321 lines) with comprehensive rate limiting infrastructure
  - Support for multiple limit types: requests per minute (RPM), tokens per minute (TPM), requests per day (RPD)
  - Model-specific rate limits with configurable thresholds for Gemini models
  - Graceful cooldown periods with exponential backoff
  - Agent startup rate limiting to prevent API quota exhaustion
  - Test suite in `massgen/tests/test_rate_limiter.py` (122 lines)
  - Configuration system in `massgen/configs/rate_limits/` with rate_limits.yaml and rate_limit_config.py (180 lines)
  - CLI flag `--enable-rate-limiting` for opt-in rate limiting

### Changed
- **Claude Code Backend**: Improved Windows support for long system prompts
  - Enhanced handling of long system prompts on Windows platforms
  - Resolved command-line length limitations and encoding issues
  - Updated `massgen/backend/claude_code.py` with more robust Windows compatibility (27 lines changed)

- **Planning MCP Server**: Added filesystem task persistence within workspace
  - Tasks now saved to agent workspace instead of separate tasks/ directory
  - Improved task organization and workspace management
  - Enhanced `massgen/mcp_tools/planning/_planning_mcp_server.py` (+84 lines)
  - Removed standalone tasks/ skill in favor of integrated planning

### Fixed
- **Rate Limiter Asyncio Lock**: Resolved asyncio lock event loop error
  - Fixed asyncio lock reuse across different event loops causing errors
  - Improved rate limiter thread safety and event loop handling
  - Updated `massgen/backend/rate_limiter.py` and added comprehensive tests

### Documentations, Configurations and Resources

- **Skills System Documentation**: Comprehensive guide for using and creating skills
  - New `docs/source/user_guide/skills.rst` (473 lines)
  - Covers skill structure, loading mechanisms, and best practices
  - Examples of creating custom skills for specific agent capabilities

- **Memory-Filesystem Mode Documentation**: Guide for integrated memory and filesystem workflows
  - New `docs/source/user_guide/memory_filesystem_mode.rst` (883 lines)
  - Demonstrates combining memory MCP tools with filesystem operations
  - Configuration examples and use case scenarios

- **Rate Limiting Documentation**: Complete rate limiting configuration guide
  - New `docs/rate_limiting.md` (254 lines)
  - Model-specific rate limits and configuration examples
  - Best practices for managing API quotas
  - New `massgen/configs/rate_limits/README.md` (108 lines)

- **Skills Configuration Examples**: Three YAML configurations for skills usage
  - `massgen/configs/skills/skills_basic.yaml`: Basic skills setup
  - `massgen/configs/skills/skills_existing_filesystem.yaml`: Skills with filesystem integration
  - `massgen/configs/skills/skills_with_memory.yaml`: Skills with memory MCP integration

- **Filesystem Tool Discovery Design**: Comprehensive design document for new tool paradigm
  - New `docs/dev_notes/filesystem_tool_discovery_design.md` (1,582 lines)
  - Proposes shift from context-based to filesystem-based tool discovery
  - Enables attaching 100+ MCP servers without context pollution
  - Details progressive disclosure and code-based tool composition
  - Includes implementation proposals and technical architecture

### Technical Details
- **Major Focus**: Skills system for modular agent prompting, memory MCP tool with filesystem persistence, multi-dimensional rate limiting, memory-filesystem integration mode
- **Contributors**: @ncrispino @abhimanyuaryan @qidanrui @sonichi @Henry-811 and the MassGen team

## [0.1.10] - 2025-11-10

### Added
- **Docker Custom Image Support**: Example Dockerfile for extending MassGen base image with custom packages
  - New `massgen/docker/Dockerfile.custom-example` demonstrating how to add ML/data science packages, development tools, and system utilities
  - Template for creating specialized Docker images for specific project needs

### Changed
- **Docker Authentication Configuration**: Restructured to nested dictionary format for better organization
  - New `command_line_docker_credentials` structure consolidating all credential-related settings
  - Nested `mount` array for credential file mounting (`ssh_keys`, `git_config`, `gh_config`, `npm_config`, `pypi_config`)
  - Nested `env_file`, `env_vars`, and `pass_all_env` for environment variable management
  - Nested `additional_mounts` for custom volume mounting
  - Migration from flat parameters (`command_line_docker_mount_ssh_keys`, `command_line_docker_pass_env_vars`, etc.) to organized nested structure
  - Enhanced `massgen/filesystem_manager/_docker_manager.py` and `_filesystem_manager.py` with new configuration parsing

- **Docker Package Management**: New nested configuration structure for dependency installation
  - New `command_line_docker_packages` structure with `auto_install_deps`, `auto_install_on_clone`, and `preinstall` settings
  - Support for pre-installing Python, npm, and system packages before agent execution
  - Improved dependency detection and installation workflow

- **Framework Interoperability Streaming**: Real-time intermediate step streaming for external framework agents
  - **LangGraph Streaming**: Updated `massgen/tool/_extraframework_agents/langgraph_lesson_planner_tool.py` (78 lines changed)
    - Now yields intermediate updates from each workflow node (standards, lesson_plan, reviewed_plan)
    - Distinguishes between logs (`is_log=True`) and final output using result type
    - Enables real-time progress tracking during LangGraph workflow execution
  - **SmoLAgent Streaming**: Updated `massgen/tool/_extraframework_agents/smolagent_lesson_planner_tool.py` (60 lines changed)
    - Streams ActionStep and PlanningStep outputs as logs during agent execution
    - FinalAnswerStep yielded as final output
    - Set verbosity_level=0 to prevent duplicate console output
  - Both frameworks now provide visibility into multi-step reasoning processes

- **Parallel Execution Safety**: Extended automatic workspace isolation to all execution modes
  - Parallel execution safety now works in both `--automation` and normal modes (previously automation-only)
  - Automatic Docker container naming with unique instance ID suffixes (e.g., `massgen-agent_a-a1b2c3d4`)
  - Enhanced `massgen/filesystem_manager/_filesystem_manager.py` with instance ID generation for all modes

### Fixed
- **Session Management**: Resolved CLI session handling issues
  - Fixed session restoration edge cases in `massgen/cli.py`
  - Improved error handling for session state loading

### Documentations, Configurations and Resources

- **MassGen Contributor Handbook**: Comprehensive contributor guide addressing issue #387
  - New handbook website at https://massgen.github.io/Handbook/
  - Eight major sections: Case Studies, Issues, Development, Documentation, Release, Announcements, Marketing, and Resources
  - Workflow diagrams illustrating contribution pipeline from research to release
  - Seven contribution tracks with assigned track owners
  - Communication channels and meeting schedules (daily sync 5:30pm PST, research 6:00pm PST)
  - Getting started guide for new contributors

- **Docker Configuration Examples**: Three new YAML configurations for advanced Docker workflows
  - `massgen/configs/tools/code-execution/docker_custom_image.yaml`: Using custom Docker images
  - `massgen/configs/tools/code-execution/docker_full_dev_setup.yaml`: Complete development environment setup
  - `massgen/configs/tools/code-execution/docker_github_readonly.yaml`: Read-only GitHub access configuration

- **Automation Documentation**: Enhanced parallel execution section
  - Updated `docs/source/user_guide/automation.rst` clarifying automatic isolation works in all modes
  - Added Docker container isolation examples with unique container naming
  - Clarified that `--automation` flag is for output control, not parallel safety

- **Code Execution Design Documentation**: Updated Docker configuration architecture
  - Enhanced `docs/dev_notes/CODE_EXECUTION_DESIGN.md` (90 lines revised)
  - New credential and package management configuration examples
  - Architecture diagrams for nested configuration structures

- **Computer Use Tools Documentation**: Clarified Docker usage requirements
  - Updated `massgen/tool/_computer_use/README.md` and `QUICKSTART.md`
  - Specified Docker requirements for Claude computer use
  - Added troubleshooting guide for computer use setup

### Technical Details
- **Major Focus**: Docker configuration improvements with nested structures for credentials and packages, framework interoperability streaming enhancements, parallel execution safety across all modes, contributor handbook
- **Contributors**: @ncrispino @Eric-Shang @franklinnwren and the MassGen team

## [0.1.9] - 2025-11-07

### Added
- **Session Management System**: Comprehensive session state tracking and restoration for multi-turn conversations
  - New `massgen/session/` module with session state and registry management (530 lines total)
  - **SessionState** dataclass for complete session state including conversation history, workspace paths, and turn metadata (`_state.py`, 219 lines)
  - **SessionRegistry** for listing, managing, and restoring previous sessions (`_registry.py`, 311 lines)
  - **restore_session()** function for seamless session continuation across CLI invocations
  - Session metadata tracking including winning agents history and orchestrator turn data
  - Automatic session storage with unique identifiers and timestamps
  - Test suite in `test_session_registry.py` (201 lines)

- **Computer Use Tools**: Browser and desktop automation capabilities for multi-agent workflows
  - **General Computer Use Tool**: OpenAI computer-use-preview integration for automated browser/computer control (`massgen/tool/_computer_use/computer_use_tool.py`, 741 lines)
    - Support for browser environment (Playwright) and Docker container execution
    - Action execution: click, type, scroll, navigate, screenshot analysis
    - Configurable max iterations and safety controls
  - **Claude Computer Use Tool**: Anthropic Claude Computer Use API integration (`massgen/tool/_claude_computer_use/claude_computer_use_tool.py`, 473 lines)
    - Native Claude Computer Use beta API support
    - Browser and desktop control with safety confirmations
    - Async execution with Playwright integration
  - **Gemini Computer Use Tool**: Google Gemini-based computer control (`massgen/tool/_gemini_computer_use/gemini_computer_use_tool.py`, 503 lines)
    - Gemini model integration for computer use workflows
    - Screenshot analysis and action generation
  - **Browser Automation Tool**: Lightweight browser automation for specific tasks (`massgen/tool/_browser_automation/browser_automation_tool.py`, 176 lines)
    - Focused browser automation without full computer use overhead
  - Comprehensive test suite in `test_computer_use.py` (629 lines)

- **OpenAI Operator API Handler**: Support for OpenAI's computer-use-preview model
  - New `massgen/api_params_handler/_openai_operator_api_params_handler.py` (72 lines)
  - Specialized parameter handling for computer use actions
  - Integration with computer use tool execution flow

### Changed
- **Config Builder Enhancement**: Intelligent model matching and discovery
  - **Fuzzy Model Name Matching**: New `massgen/utils/model_matcher.py` (214 lines) allowing approximate model name input
  - **Model Catalog System**: New `massgen/utils/model_catalog.py` (218 lines) with curated lists of common models across providers
  - Enhanced `massgen/config_builder.py` with automatic model search and suggestions
  - Support for partial model names with intelligent completion (e.g., "sonnet" → "claude-sonnet-4-5-20250929")
  - Contribution from acrobat3 (K. from JP)

- **Backend Capabilities Enhancement**: Expanded provider support with six new backend registrations
  - Added **Cerebras AI** backend capabilities (llama models with WSE hardware acceleration)
  - Added **Together AI** backend capabilities (Meta-Llama, Mixtral models)
  - Added **Fireworks AI** backend capabilities (Llama, Qwen models with fast inference)
  - Added **Groq** backend capabilities (Llama, Mixtral with LPU hardware)
  - Added **OpenRouter** backend capabilities (unified access to 200+ models with audio/video support)
  - Added **Moonshot (Kimi)** backend capabilities (Chinese-optimized models with long context)
  - Updated `massgen/backend/capabilities.py` with comprehensive backend specifications

- **Memory System Improvement**: Enhanced memory update logic for multi-agent coordination
  - New `massgen/memory/_update_prompts.py` (276 lines) with specialized update prompts for mem0
  - **MASSGEN_UNIVERSAL_UPDATE_MEMORY_PROMPT**: Philosophy for accumulating qualitative patterns vs statistics
  - Improved fact merging logic focusing on actionable tool usage patterns and technical insights

- **Chat Agent Enhancement**: Session restoration and improved orchestrator restart handling
  - Session state restoration in `massgen/chat_agent.py`
  - Enhanced turn tracking and workspace persistence
  - Improved logging and coordination with orchestrator restarts

- **CLI Enhancement**: Extended command-line interface for session management
  - Session listing and restoration commands in `massgen/cli.py`
  - Enhanced display selection and output formatting
  - Support for continuing previous sessions with automatic state restoration

### Documentations, Configurations and Resources

- **Diversity System Documentation**: Comprehensive guide for increasing agent diversity
  - New `docs/source/user_guide/diversity.rst` (388 lines)
  - Covers answer novelty requirements (lenient/balanced/strict)
  - Documents DSPy question paraphrasing integration (from v0.1.8)
  - Best practices for multi-agent diversity strategies
  - Configuration examples and recommendations

- **Memory System Documentation**: Updated memory user guide
  - Updated `docs/source/user_guide/memory.rst` with enhanced memory update logic and configuration

- **Computer Use Configuration Examples**: Five YAML configurations demonstrating computer use capabilities
  - `massgen/configs/tools/custom_tools/claude_computer_use_example.yaml`: Claude-specific computer use
  - `massgen/configs/tools/custom_tools/gemini_computer_use_example.yaml`: Gemini-specific computer use
  - `massgen/configs/tools/custom_tools/computer_use_example.yaml`: General computer use with OpenAI
  - `massgen/configs/tools/custom_tools/computer_use_docker_example.yaml`: Docker-based computer use
  - `massgen/configs/tools/custom_tools/computer_use_browser_example.yaml`: Browser automation focus

- **Session Management Configuration**: Example demonstrating session continuation
  - `massgen/configs/memory/grok4_gpt5_gemini_mcp_filesystem_test_with_claude_code.yaml`: Multi-turn session with MCP filesystem

- **Computer Use Documentation**:
  - New `massgen/backend/docs/COMPUTER_USE_TOOLS_GUIDE.md`: Comprehensive guide for computer use tools (494 lines)
  - New `scripts/computer_use_setup.md`: Setup instructions for computer use tools
  - New `scripts/setup_docker_cua.sh`: Automated Docker setup script for computer use

### Technical Details
- **Major Focus**: Session management with conversation restoration, computer use automation tools, intelligent config builder with fuzzy matching, expanded backend support, memory system enhancements
- **Contributors**: @franklinnwren @ncrispino @Henry-811 and the MassGen team

## [0.1.8] - 2025-11-05

### Added
- **Automation Mode for LLM Agents**: Complete infrastructure for running MassGen via LLM agents and programmatic workflows
  - New `--automation` CLI flag for silent execution with minimal output (~10 lines vs 250-3,000+)
  - New `SilentDisplay` class in `massgen/frontend/displays/silent_display.py` for automation-friendly output
  - Real-time `status.json` monitoring file updated every 2 seconds via enhanced `CoordinationTracker`
  - Meaningful exit codes: 0 (success), 1 (config error), 2 (execution error), 3 (timeout), 4 (interrupted)
  - Automatic workspace isolation for parallel execution with unique suffixes
  - Meta-coordination capabilities: MassGen running MassGen configurations
  - Automatic log directory creation and management for automation sessions

- **DSPy Question Paraphrasing Integration**: Intelligent question diversity for multi-agent coordination
  - New `massgen/dspy_paraphraser.py` module with semantic-preserving paraphrasing (557 lines)
  - Three paraphrasing strategies: "diverse", "balanced" (default), "conservative"
  - Configurable number of variants per orchestrator session
  - Automatic semantic validation using `SemanticValidationSignature` to ensure meaning preservation
  - Thread-safe caching system with SHA-256 hashing for performance
  - Support for all backends (Gemini, OpenAI, Claude, etc.) as paraphrasing engines

- **Case Study Summary**: Comprehensive documentation of MassGen capabilities
  - New `docs/CASE_STUDIES_SUMMARY.md` providing centralized overview of 33 case studies (368 lines)
  - Organized by category: Release Features, Research, Travel, Creative, In Development, Planned
  - Covers versions v0.0.3 to v0.1.5 with status tracking and links to videos
  - Statistics: 19 completed, 8 with video demonstrations, 6 categories

### Changed
- **Orchestrator Enhancement**: Integration of DSPy paraphrasing and automation tracking
  - Question variant distribution to different agents based on configured strategy
  - Improved coordination event logging with structured status exports

- **CLI Enhancement**: Extended command-line interface for automation workflows
  - Enhanced display selection logic automatically choosing SilentDisplay in automation mode
  - Improved output formatting optimized for LLM agent parsing and monitoring

### Documentations, Configurations and Resources

- **Case Study**: Meta-level self-analysis demonstrating automation mode
  - New `docs/source/examples/case_studies/meta-self-analysis-automation-mode.md`: Comprehensive case study showing MassGen analyzing its own v0.1.8 codebase using automation mode

- **Automation Documentation**: Comprehensive guides for LLM agent integration
  - New `AI_USAGE.md`: Complete guide for LLM agents running MassGen (319 lines)
  - New `docs/source/user_guide/automation.rst`: Full automation guide with BackgroundShellManager patterns (890 lines)
  - New `docs/source/reference/status_file.rst`: Complete `status.json` schema reference with field-by-field documentation (565 lines)
  - Updated `README.md` and `README_PYPI.md` with automation mode sections (135 lines each)

- **DSPy Documentation**: Complete implementation and usage guide
  - New `massgen/backend/docs/DSPY_IMPLEMENTATION_GUIDE.md`: Comprehensive DSPy integration guide (653 lines)
  - Covers quick start, configuration, strategies, troubleshooting, and semantic validation
  - Includes paraphrasing examples and best practices

- **Meta-Coordination Configurations**: MassGen running MassGen examples
  - `massgen/configs/meta/massgen_runs_massgen.yaml`: Single agent autonomously running MassGen experiments
  - `massgen/configs/meta/massgen_suggests_to_improve_massgen.yaml`: Self-improvement configuration
  - Demonstrates automation mode usage for meta-coordination workflows

- **DSPy Configuration Example**: New YAML configuration for DSPy-enabled coordination
  - `massgen/configs/basic/multi/three_agents_dspy_enabled.yaml`: Three-agent setup with DSPy paraphrasing

- **Case Study Summary Documentation**: Centralized case study reference
  - New `docs/CASE_STUDIES_SUMMARY.md`: Comprehensive overview of all MassGen case studies with categorization and status tracking

### Technical Details
- **Major Focus**: Automation infrastructure for LLM agents, DSPy-powered question paraphrasing, meta-coordination capabilities, comprehensive case study documentation
- **Contributors**: @ncrispino @praneeth999 @franklinnwren @qidanrui @sonichi @Henry-811 and the MassGen team

## [0.1.7] - 2025-11-03

### Added
- **Agent Task Planning System**: MCP-based task management with dependency tracking
  - New `massgen/mcp_tools/planning/` module with dedicated planning server (`_planning_mcp_server.py`)
  - Task dataclasses with dependency validation and status management (`planning_dataclasses.py`)
  - Support for task states (pending/in_progress/completed/blocked) with automatic transitions based on dependencies
  - Orchestrator integration for plan-aware coordination
  - Test suite in `test_planning_integration.py` and `test_planning_tools.py`

- **Background Shell Execution**: Long-running command support with persistent sessions
  - New `BackgroundShell` class in `massgen/filesystem_manager/background_shell.py`
  - Shell lifecycle management with output streaming and real-time monitoring
  - Automatic timeout handling for long-running processes
  - Enhanced code execution server with background execution capabilities
  - Test coverage in `test_background_shell.py`

- **Preemption Coordination**: Multi-agent coordination with interruption support
  - Agents can preempt ongoing coordination to submit better answers without full restart
  - Enhanced coordination tracker with preemption event logging
  - Improved orchestrator logic to preserve partial progress during preemption

### Fixed
- **System Message Handling**: Resolved system message extraction in Claude Code backend for background shell execution
- **Case Study Documentation**: Fixed broken links and outdated examples in older case studies

### Documentations, Configurations and Resources

- **Documentation Updates**: New user guides and design documentation
  - New `docs/source/user_guide/agent_task_planning.rst`: Task planning guide with usage patterns and API reference
  - Updated `docs/source/user_guide/code_execution.rst`: Added 122 lines for background shell usage
  - New `docs/dev_notes/agent_planning_coordination_design.md`: Comprehensive design document for agent planning and coordination system
  - New `docs/dev_notes/preempt_not_restart_design.md`: 456-line design document with preemption algorithms
  - Updated `docs/source/development/architecture.rst`: Added 61 lines for preemption coordination architecture

- **Configuration Examples**: New YAML configurations demonstrating v0.1.7 features
  - `example_task_todo.yaml`: Task planning configuration
  - `background_shell_demo.yaml`: Background shell execution demonstration

### Technical Details
- **Major Focus**: Agent task planning with dependencies, background command execution, preemption-based coordination
- **Contributors**: @ncrispino @Henry-811 and the MassGen team

## [0.1.6] - 2025-10-31

### Added
- **Framework Interoperability**: External agent framework integration as MassGen custom tools
  - New `massgen/tool/_extraframework_agents/` module with 5 framework integrations
  - **AG2 Lesson Planner Tool**: Nested chat functionality wrapped as custom tool for multi-agent lesson planning (supports streaming)
  - **LangGraph Lesson Planner Tool**: LangGraph graph-based workflows integrated as tool
  - **AgentScope Lesson Planner Tool**: AgentScope agent system wrapped for lesson creation
  - **OpenAI Assistants Lesson Planner Tool**: OpenAI Assistants API integrated as tool
  - **SmoLAgent Lesson Planner Tool**: HuggingFace SmoLAgent integration for lesson planning
  - Enables MassGen agents to delegate tasks to specialized external frameworks
  - Each framework runs autonomously and returns results to MassGen orchestrator
  - Note: Only AG2 currently supports streaming; other frameworks return complete results

- **Configuration Validator**: Comprehensive YAML configuration validation system
  - New `ConfigValidator` class in `massgen/config_validator.py` for pre-flight validation
  - Memory configuration validation with detailed error messages
  - Pre-commit hook integration for automatic config validation
  - Comprehensive test suite in `massgen/tests/test_config_validator.py`
  - Validates agent configurations, backend parameters, tool settings, and memory options
  - Provides actionable error messages with suggestions for common mistakes

### Changed
- **Backend Architecture Refactoring**: Unified tool execution with ToolExecutionConfig
  - New `ToolExecutionConfig` dataclass in `base_with_custom_tool_and_mcp.py` for standardized tool handling
  - Refactored `ResponseBackend` with unified tool execution flow
  - Refactored `ChatCompletionsBackend` with unified tool execution flow
  - Refactored `ClaudeBackend` with unified tool execution methods
  - Eliminates duplicate code paths between custom tools and MCP tools
  - Consistent error handling and status reporting across all tool types
  - Improved maintainability and extensibility for future tool systems

- **Gemini Backend Simplification**: Major architectural cleanup and consolidation
  - Removed `gemini_mcp_manager.py` module
  - Removed `gemini_trackers.py` module
  - Refactored `gemini.py` to use manual tool execution via base class
  - Streamlined tool handling and cleanup logic
  - Removed continuation logic and duplicate code
  - Updated `_gemini_formatter.py` for simplified tool conversion
  - Net reduction of 1,598 lines through consolidation
  - Improved maintainability and performance

- **Custom Tool System Enhancement**: Improved tool management and execution
  - Enhanced `ToolManager` with category management capabilities
  - Improved tool registration and validation system
  - Enhanced tool result handling and error reporting
  - Better support for async tool execution
  - Improved tool schema generation for LLM consumption

### Documentations, Configurations and Resources

- **Framework Interoperability Examples**: 8 new configuration files demonstrating external framework integration
  - **AG2 Examples**: `ag2_lesson_planner_example.yaml`, `ag2_and_langgraph_lesson_planner.yaml`, `ag2_and_openai_assistant_lesson_planner.yaml`
  - **LangGraph Examples**: `langgraph_lesson_planner_example.yaml`
  - **AgentScope Examples**: `agentscope_lesson_planner_example.yaml`
  - **OpenAI Assistants Examples**: `openai_assistant_lesson_planner_example.yaml`
  - **SmoLAgent Examples**: `smolagent_lesson_planner_example.yaml`
  - **Multi-Framework Examples**: `two_models_with_tools_example.yaml`

### Technical Details
- **Major Focus**: Framework interoperability for external agent integration, unified tool execution architecture, Gemini backend simplification, and configuration validation system
- **Contributors**: @Eric-Shang @praneeth999 @ncrispino @qidanrui @sonichi @Henry-811 and the MassGen team

## [0.1.5] - 2025-10-29

### Added
- **Memory System**: Complete long-term memory implementation with semantic retrieval
  - New `massgen/memory/` module with comprehensive memory management
  - **PersistentMemory** via mem0 integration for semantic fact storage and retrieval
  - **ConversationMemory** for short-term verbatim message tracking
  - **Automatic Context Compression** when approaching token limits
  - **Memory Sharing for Multi-Turn Conversations** with turn-aware filtering to prevent temporal leakage
  - **Session Management** for memory isolation and continuation across runs
  - **Qdrant Vector Database Integration** for efficient semantic search (server and local modes)
  - **Context Monitoring** with real-time token usage tracking
  - Fact extraction prompts with customizable LLM and embedding providers
  - Supports OpenAI, Anthropic, Groq, and other mem0-compatible providers

- **Memory Configuration Support**: New YAML configuration options
  - Memory enable/disable toggle at global and per-agent levels
  - Configurable compression thresholds (trigger_threshold, target_ratio)
  - Retrieval settings (limit, exclude_recent for smart retrieval)
  - Session naming for continuation and cross-session memory
  - LLM and embedding provider configuration for mem0
  - Qdrant connection settings (server/local mode, host, port, path)

### Changed
- **Chat Agent Enhancement**: Memory integration for agent workflows
  - Memory recording after agent responses (conversation and persistent)
  - Memory retrieval on restart/reset for context restoration
  - Integration with compression and context monitoring modules

- **Orchestrator Enhancement**: Memory coordination for multi-agent workflows
  - Memory initialization and management across agent lifecycles
  - Memory cleanup on orchestrator shutdown

### Documentations, Configurations and Resources

- **Memory Documentation**: Comprehensive memory system user guide
  - New `docs/source/user_guide/memory.rst`
  - Complete usage guide with quick start, configuration reference, and examples
  - Design decisions documentation explaining architecture choices
  - Troubleshooting guide for common memory issues
  - Monitoring and debugging instructions with log examples
  - API reference for PersistentMemory, ConversationMemory, and ContextMonitor

- **Configuration Examples**: 5 new memory-focused YAML configurations
  - `gpt5mini_gemini_context_window_management.yaml`: Multi-agent with context compression
  - `gpt5mini_gemini_research_to_implementation.yaml`: Research to implementation workflow
  - `gpt5mini_high_reasoning_gemini.yaml`: High reasoning agents with memory
  - `gpt5mini_gemini_baseline_research_to_implementation.yaml`: Baseline research workflow
  - `single_agent_compression_test.yaml`: Testing compression behavior

- **Infrastructure and Testing**:
  - Memory test suite with 4 test files in `massgen/tests/memory/`
  - Additional memory tests: `test_agent_memory.py`, `test_conversation_memory.py`, `test_orchestrator_memory.py`, `test_persistent_memory.py`

### Technical Details
- **Major Focus**: Long-term memory system with semantic retrieval and memory sharing for multi-turn conversations
- **Contributors**: @ncrispino @qidanrui @kitrakrev @sonichi @Henry-811 and the MassGen team

## [0.1.4] - 2025-10-27

### Added
- **Multimodal Generation Tools**: Comprehensive generation capabilities via OpenAI APIs
  - New `text_to_image_generation` tool for generating images from text prompts using DALL-E models
  - New `text_to_video_generation` tool for generating videos from text prompts
  - New `text_to_speech_continue_generation` tool for text-to-speech with continuation support
  - New `text_to_speech_transcription_generation` tool for audio transcription and generation
  - New `text_to_file_generation` tool for generating documents (PDF, DOCX, XLSX, PPTX)
  - New `image_to_image_generation` tool for image-to-image transformations
  - Implemented in `massgen/tool/_multimodal_tools/` with 6 new modules

- **Binary File Protection System**: Enhanced security for file operations
  - New binary file blocking in `PathPermissionManager` preventing text tools from reading binary files
  - Added `BINARY_FILE_EXTENSIONS` set covering images, videos, audio, archives, executables, and Office documents
  - New `_validate_binary_file_access()` method with intelligent tool suggestions
  - Prevents context pollution by blocking Read, read_text_file, and read_file tools from binary files
  - Comprehensive test suite in `test_binary_file_blocking.py`

- **Crawl4AI Web Scraping Integration**: Advanced web content extraction tool
  - New `crawl4ai_tool` for intelligent web scraping with LLM-powered extraction
  - Implemented in `massgen/tool/_web_tools/crawl4ai_tool.py`

### Changed
- **Multimodal File Size Limits**: Enhanced validation and automatic handling
  - Automatic image resizing for files exceeding size limits
  - Comprehensive size limit test suite in `test_multimodal_size_limits.py`
  - Enhanced validation in understand_audio and understand_video tools

### Documentations, Configurations and Resources

- **PyPI Package Documentation**: Standalone README for PyPI distribution
  - New `README_PYPI.md` with comprehensive package documentation
  - Improved package metadata and installation instructions

- **Release Management Documentation**: Comprehensive release workflow guide
  - New `docs/dev_notes/release_checklist.md` with step-by-step release procedures
  - Detailed checklist for testing, documentation, and deployment

- **Binary File Protection Documentation**: Enhanced protected paths user guide
  - Updated `docs/source/user_guide/protected_paths.rst` with binary file protection section
  - Documents 40+ protected binary file types and specialized tool suggestions

- **Configuration Examples**: 9 new YAML configuration files
  - **Generation Tools**: 8 multimodal generation configurations
    - `text_to_image_generation_single.yaml` and `text_to_image_generation_multi.yaml`
    - `text_to_video_generation_single.yaml` and `text_to_video_generation_multi.yaml`
    - `text_to_speech_generation_single.yaml` and `text_to_speech_generation_multi.yaml`
    - `text_to_file_generation_single.yaml` and `text_to_file_generation_multi.yaml`
  - **Web Scraping**: `crawl4ai_example.yaml` for Crawl4AI integration

### Technical Details
- **Major Focus**: Multimodal generation tools, binary file protection system, web scraping integration
- **Contributors**: @qidanrui @ncrispino @sonichi @Henry-811 and the MassGen team

## [0.1.3] - 2025-10-24

### Added
- **Post-Evaluation Workflow Tools**: Submit and restart capabilities for winning agents
  - New `PostEvaluationToolkit` class in `massgen/tool/workflow_toolkits/post_evaluation.py`
  - `submit` tool for confirming final answers
  - `restart_orchestration` tool for restarting with improvements and feedback
  - Post-evaluation phase where winning agent evaluates its own answer
  - Support for all API formats (Claude, Response API, Chat Completions)
  - Configuration parameter `enable_post_evaluation_tools` for opt-in/out

- **Custom Multimodal Understanding Tools**: Active tools for analyzing workspace files using OpenAI's GPT-4.1 API
  - New `understand_image` tool for analyzing images (PNG, JPEG, JPG) with detailed metadata extraction
  - New `understand_audio` tool for transcribing and analyzing audio files (WAV, MP3, FLAC, OGG)
  - New `understand_video` tool for extracting frames and analyzing video content (MP4, AVI, MOV, WEBM)
  - New `understand_file` tool for processing documents (PDF, DOCX, XLSX, PPTX) with text and metadata extraction
  - Works with any backend (uses OpenAI for analysis)
  - Returns structured JSON with comprehensive metadata

- **Docker Sudo Mode**: Enhanced Docker execution with privileged command support
  - New `use_sudo` parameter for Docker execution
  - Sudo mode for commands requiring elevated privileges
  - Enhanced security instructions and documentation
  - Test coverage in `test_code_execution.py`

### Changed
- **Interactive Config Builder Enhancement**: Improved workflow and provider handling
  - Better flow from automatic setup to config builder
  - Auto-detection of environment variables
  - Improved provider-specific configuration handling
  - Integrated multimodal tools selection in config wizard

### Fixed
- **System Message Warning**: Resolved deprecated system message configuration warning
  - Fixed system message handling in `agent_config.py`
  - Updated chat agent to properly handle system messages
  - Removed deprecated warning messages

- **Config Builder Issues**: Multiple configuration builder improvements
  - Fixed config display errors
  - Improved config saving across different provider types
  - Better error handling for missing configurations

### Documentations, Configurations and Resources

- **Multimodal Tools Documentation**: Comprehensive documentation for new multimodal tools
  - `docs/source/user_guide/multimodal.rst`: Updated with custom tools section
  - `massgen/tool/docs/multimodal_tools.md`: Complete 779-line technical documentation

- **Docker Sudo Mode Documentation**: Enhanced Docker execution documentation
  - `docs/source/user_guide/code_execution.rst`: Added 98 lines documenting sudo mode
  - `massgen/docker/README.md`: Updated with sudo mode instructions

- **Configuration Examples**: New example configurations
  - `configs/tools/multimodal_tools/understand_image.yaml`: Image analysis configuration
  - `configs/tools/multimodal_tools/understand_audio.yaml`: Audio transcription configuration
  - `configs/tools/multimodal_tools/understand_video.yaml`: Video analysis configuration
  - `configs/tools/multimodal_tools/understand_file.yaml`: Document processing configuration

- **Example Resources**: New test resources for v0.1.3 features
  - `massgen/configs/resources/v0.1.3-example/multimodality.jpg`: Image example
  - `massgen/configs/resources/v0.1.3-example/Sherlock_Holmes.mp3`: Audio example
  - `massgen/configs/resources/v0.1.3-example/oppenheimer_trailer_1920.mp4`: Video example
  - `massgen/configs/resources/v0.1.3-example/TUMIX.pdf`: PDF document example

- **Case Studies**: New case study demonstrating v0.1.3 features
  - `docs/source/examples/case_studies/multimodal-case-study-video-analysis.md`: Meta-level demonstration of multimodal video understanding with agents analyzing their own case study videos

### Technical Details
- **Major Focus**: Post-evaluation workflow tools, custom multimodal understanding tools, Docker sudo mode
- **Contributors**: @ncrispino @qidanrui @sonichi @Henry-811 and the MassGen team

## [0.1.2] - 2025-10-22

### Added
- **Claude 4.5 Haiku Support**: Added latest Claude Haiku model
  - New model: `claude-haiku-4-5-20251001`
  - Updated model registry in `backend/capabilities.py`

### Changed
- **Planning Mode Enhancement**: Intelligent automatic MCP tool blocking based on operation safety
  - New `_analyze_question_irreversibility()` method in orchestrator analyzes questions to determine if MCP operations are reversible
  - New `set_planning_mode_blocked_tools()`, `get_planning_mode_blocked_tools()`, and `is_mcp_tool_blocked()` methods in backend for selective tool control
  - Dynamically enables/disables planning mode - read-only operations allowed during coordination, write operations blocked
  - Planning mode supports different workspaces without conflicts
  - Zero configuration required - works transparently


- **Claude Model Priority**: Reorganized model list in capabilities registry
  - Changed default model from `claude-sonnet-4-20250514` to `claude-sonnet-4-5-20250929`
  - Moved `claude-opus-4-1-20250805` higher in priority order
  - Updated in both Claude and Claude Code backends

### Fixed
- **Grok Web Search**: Resolved web search functionality in Grok backend
  - Fixed `extra_body` parameter handling for Grok's Live Search API
  - New `_add_grok_search_params()` method for proper search parameter injection
  - Enhanced `_stream_with_custom_and_mcp_tools()` to support Grok-specific parameters
  - Improved error handling for conflicting search configurations
  - Better integration with Chat Completions API params handler

### Documentations, Configurations and Resources

- **Intelligent Planning Mode Case Study**: Complete feature documentation
  - `docs/source/examples/case_studies/INTELLIGENT_PLANNING_MODE.md`: Comprehensive guide for automatic planning mode
  - Demonstrates automatic irreversibility detection
  - Shows read/write operation classification
  - Includes examples for Discord, filesystem, and Twitter operations

- **Configuration Updates**: Enhanced YAML examples
  - Updated 5 planning mode configurations in `configs/tools/planning/` with selective blocking examples
  - Updated `three_agents_default.yaml` with Grok-4-fast model
  - Test coverage in `test_intelligent_planning_mode.py`

### Technical Details
- **Major Focus**: Intelligent planning mode with selective tool blocking, model support enhancements
- **Contributors**: @franklinnwren @ncrispino @qidanrui @sonichi @Henry-811 and the MassGen team

## [0.1.1] - 2025-10-20

### Added
- **Custom Tools System**: Complete framework for registering and executing user-defined Python functions as tools
  - New `ToolManager` class in `massgen/tool/_manager.py` for centralized tool registration and lifecycle management
  - Support for custom tools alongside MCP servers across all backends (Claude, Gemini, OpenAI Response API, Chat Completions, Claude Code)
  - Three tool categories: builtin, mcp, and custom tools
  - Automatic tool discovery with name prefixing and conflict resolution
  - Tool validation with parameter schema enforcement
  - Comprehensive test coverage in `test_custom_tools.py`

- **Voting Sensitivity & Answer Novelty Controls**: Three-tier system for multi-agent coordination
  - New `voting_sensitivity` parameter with three levels: "lenient", "balanced", "strict"
  - "Lenient": Accepts any reasonable answer
  - "Balanced": Default middle ground
  - "Strict": High-quality requirement
  - Answer novelty detection with `_check_answer_novelty()` method in `orchestrator.py` preventing duplicate answers
  - Configurable `max_new_answers_per_agent` limiting submissions per agent
  - Token-based similarity thresholds (50-70% overlap) for duplicate detection

- **Interactive Configuration Builder**: Wizard for creating YAML configurations
  - New `config_builder.py` module with step-by-step prompts
  - Guided workflow for backend selection, model configuration, and API key setup
  - Model-specific parameter handling (temperature, reasoning, verbosity)
  - Tool enablement options (MCP servers, custom tools, builtin tools)
  - Configuration validation and preview before saving
  - Integration with `massgen --config-builder` command

- **Backend Capabilities Registry**: Centralized feature support tracking
  - New `capabilities.py` module in `massgen/backend/` documenting backend capabilities
  - Feature matrix showing MCP, custom tools, multimodal, and code execution support
  - Runtime capability queries for backend selection

### Changed
- **Gemini Backend Architecture**: Major refactoring for improved maintainability
  - Extracted MCP management into `gemini_mcp_manager.py`
  - Extracted tracking logic into `gemini_trackers.py`
  - Extracted utilities into `gemini_utils.py`
  - New API params handler `_gemini_api_params_handler.py`
  - Improved session management and tool execution flow

- **Python Version Requirements**: Updated minimum supported version
  - Changed from Python 3.10+ to Python 3.11+ in `pyproject.toml`
  - Ensures compatibility with modern type hints and async features

- **API Key Setup Command**: Simplified command name
  - Renamed `massgen --setup-keys` to `massgen --setup` for brevity
  - Maintained all functionality for interactive API key configuration

- **Configuration Examples**: Updated example commands
  - Changed from `python -m massgen.cli` to simplified `massgen` command
  - Updated 40+ configuration files for consistency

### Fixed
- **CLI Configuration Selection**: Resolved error with large config lists
  - Fixed crash when using `massgen --select` with many available configurations
  - Improved pagination and display of configuration options
  - Enhanced error handling for configuration discovery

- **CLI Help System**: Improved documentation display
  - Fixed help text formatting in `massgen --help`
  - Better organization of command options and examples

### Documentations, Configurations and Resources

- **Case Study: Universal Code Execution via MCP**: Comprehensive v0.0.31 feature documentation
  - `docs/source/examples/case_studies/universal-code-execution-mcp.md`
  - Demonstrates pytest test creation and execution across backends
  - Shows command validation, security layers, and result interpretation

- **Documentation Updates**: Enhanced existing documentation
  - Added custom tools user guide and integration examples
  - Reorganized case studies for improved navigation
  - Updated configuration schema with new voting and tools parameters

- **Custom Tools Examples**: 40+ example configurations
  - Basic single-tool setups for each backend
  - Multi-agent configurations with custom tools
  - Integration examples combining MCP and custom tools
  - Located in `configs/tools/custom_tools/`

- **Voting Sensitivity Examples**: Configuration examples for voting controls
  - `configs/voting/gemini_gpt_voting_sensitivity.yaml`
  - Demonstrates lenient, balanced, and strict voting modes
  - Shows answer novelty threshold configuration

### Technical Details
- **Major Focus**: Custom tools system, voting sensitivity controls, interactive config builder, and comprehensive documentation
- **Contributors**: @qidanrui @ncrispino @praneeth999 @sonichi @Eric-Shang @Henry-811 and the MassGen team

## [0.1.0] - 2025-10-17 (PyPI Release)

### Added
- **PyPI Package Release**: Official MassGen package available on PyPI for easy installation via pip
- **Enhanced Documentation**: Comprehensive Sphinx documentation with improved structure and clarity
  - Rebuilt documentation with v0.1.0 version numbers
  - Improved backend capabilities table with split multimodal columns
  - Enhanced explanations for multimodal capabilities (Both, Understanding, Generation)
  - Updated homepage with v0.1.0 features

### Changed
- **Documentation Updates**: Major documentation improvements for PyPI release
  - Updated version numbers across all documentation files
  - Clarified multimodal capability terminology
  - Enhanced backend configuration guides

### Technical Details
- **Major Focus**: PyPI distribution and documentation improvements
- **Contributors**: @ncrispino @qidanrui @sonichi @Henry-811 and the MassGen team

## [0.0.32] - 2025-10-15

### Added
- **Docker Execution Mode**: Isolated command execution via Docker containers
  - New `DockerManager` class for persistent container lifecycle management
  - Container-based isolation with volume mounts for workspace and context paths
  - Configurable resource limits (CPU, memory) and network isolation modes (none/bridge/host)
  - Multi-agent support with dedicated containers per agent
  - Build script and comprehensive Dockerfile for massgen/mcp-runtime image
  - Enable via `command_line_execution_mode: "docker"` in agent configuration
  - Test suite in `test_code_execution.py` covering Docker and local execution modes

### Changed
- **Code Execution via MCP**: Extended v0.0.31's execute_command tool with Docker execution mode
  - Docker environment detection for automatic image verification
  - Local command execution remains available via `command_line_execution_mode: "local"`
  - Enhanced security layers for both local and Docker modes

- **Claude Code Backend**: Docker mode integration and MCP tool handling improvements
  - Automatic Bash tool disablement when Docker mode is enabled
  - MCP tool auto-permission support via `can_use_tool` hook
  - MCP server configuration format conversion (list to dict format)
  - System message enhancements to prevent git repository confusion in Docker

- **MCP Tools Architecture**: Major refactoring for simplicity and maintainability
  - Renamed `MultiMCPClient` to `MCPClient` reflecting simplified architecture
  - Removed deprecated `converters.py` module (275 lines removed)
  - Streamlined `client.py` with 1,029 lines removed through consolidation
  - Standardized type hints and module-level constants in `backend_utils.py`
  - Simplified exception handling in `exceptions.py` and security validation in `security.py`

### Fixed
- **Configuration Examples**: Improved configuration organization and usability
  - Renamed configuration files for better discoverability
  - Fixed CPU limits in example configurations to be runnable
  - Reverted gemini_mcp_test.yaml for consistency

- **Orchestrator Timeout and Cleanup**: Enhanced timeout handling and resource management
  - Improved timeout mechanisms for better reliability
  - Better cleanup of resources after orchestration sessions

### Documentations, Configurations and Resources

- **Docker Documentation**: New comprehensive Docker mode guide in `massgen/docker/README.md`
  - Complete Docker setup and usage documentation
  - Build scripts and Dockerfile with detailed comments
  - Security considerations for container-based execution
  - Resource management and isolation strategies

- **Code Execution Design**: Updated `CODE_EXECUTION_DESIGN.md` with Docker architecture details

- **New Configuration Files**: Added 5 Docker-specific example configurations
  - `docker_simple.yaml`: Basic single-agent Docker execution
  - `docker_multi_agent.yaml`: Multi-agent Docker deployment
  - `docker_with_resource_limits.yaml`: Resource-constrained Docker setup
  - `docker_claude_code.yaml`: Claude Code with Docker execution
  - `docker_verification.yaml`: Docker setup verification configuration

### Technical Details
- **Commits**: 17 commits including Docker execution, MCP refactoring, and Claude Code enhancements
- **Files Modified**: 32 files across backend, filesystem manager, MCP tools, and configurations
- **Major Features**: Docker execution mode, MCP architecture simplification, Claude Code Docker integration
- **New Module**: `_docker_manager.py` with DockerManager class (438 lines)
- **Dependencies Updated**: `docker>=7.0.0` added as optional dependency
- **Contributors**: @ncrispino @praneeth999 @qidanrui @sonichi @Henry-811 and the MassGen team

## [0.0.31] - 2025-10-14

### Added
- **Code Execution via MCP**: Universal command execution through MCP
  - New `execute_command` MCP tool enabling bash/shell execution across Claude, Gemini, OpenAI (Response API), and Chat Completions providers (Grok, ZAI, etc.)
  - AG2-inspired security with multi-layer protection: dangerous command sanitization, command filtering (whitelist/blacklist), PathPermissionManager hooks, path validation, timeout enforcement
  - Command filtering with regex patterns for whitelist/blacklist control
  - New MCP server `_code_execution_server.py` with subprocess-based local execution
  - Test coverage in `test_code_execution.py` covering basics, path validation, command sanitization, output handling, and virtual environment detection

- **Audio Generation Tools**: Text-to-speech and audio transcription capabilities via OpenAI APIs
  - New `generate_and_store_audio_no_input_audios` tool for generating audio from text using gpt-4o-audio-preview model
  - New `generate_text_with_input_audio` tool for transcribing audio files using OpenAI's Transcription API
  - New `convert_text_to_speech` tool for converting text to speech with gpt-4o-mini-tts model
  - Support for multiple voices (alloy, echo, fable, onyx, nova, shimmer, coral, sage) and audio formats (wav, mp3, opus, aac, flac)
  - Optional speaking instructions for tone and style control in TTS
  - Automatic workspace organization with timestamp-based filenames

- **Video Generation Tools**: Text-to-video generation via OpenAI's Sora-2 API
  - New `generate_and_store_video_no_input_images` tool for generating videos from text prompts
  - Support for Sora-2 model with configurable video duration
  - Asynchronous video generation with progress monitoring
  - Automatic MP4 format with workspace storage and organization

### Changed
- **AG2 Group Chat Support**: Enhanced AG2 adapter with native multi-agent group chat coordination
  - New group chat manager integration with AG2's `GroupChat` and `GroupChatManager`
  - Configurable speaker selection modes: auto (LLM-based), round_robin, manual
  - Support for nested conversations and workflow tools within group chat sessions
  - Automatic tool registration/unregistration for clean group chat lifecycle
  - Enhanced adapter architecture with group chat state management
  - Better agent reinitialization and termination logic for multi-turn group conversations
  - Test coverage in `test_ag2_adapter.py` and `test_ag2_utils.py`

- **File Operation Tracker**: Enhanced with auto-generated file exemptions
  - New `_is_auto_generated()` method to identify build artifacts and cache files
  - Prevents permission errors when agents clean up after running tests or builds

- **Path Permission Manager**: Added execute_command tool validation
  - Added `execute_command` to command_tools set for bash-like security validation
  - PreToolUse hooks now validate execute_command calls for dangerous patterns and path restrictions
  - Enhanced test coverage with 93 new test lines for command tool validation

- **Message Templates**: Added code execution result guidance
  - New system message guidance when `enable_command_execution=True` instructing agents to explain test results and command outputs in their answers
  - Better agent behavior for explaining what was tested and what results mean

### Documentations, Configurations and Resources

- **Code Execution Design Documentation**: Comprehensive technical design document
  - `CODE_EXECUTION_DESIGN.md`: Design doc covering architecture, security layers, implementation plan, virtual environment support, and future Docker enhancements

- **New Configuration Files**: Added 8 new example configurations
  - **AG2 Group Chat**: `ag2_groupchat.yaml`, `ag2_groupchat_gpt.yaml`
  - **Code Execution**: `basic_command_execution.yaml`, `code_execution_use_case_simple.yaml`, `command_filtering_whitelist.yaml`, `command_filtering_blacklist.yaml`,
  - **Audio Generation**: `single_gpt4o_audio_generation.yaml`, `gpt4o_audio_generation.yaml`
  - **Video Generation**: `single_gpt4o_video_generation.yaml`

### Technical Details
- **Commits**: 29 commits including AG2 group chat, code execution, audio/video generation, and enhancements
- **Files Modified**: 39 files with 3,649 insertions and 154 deletions
- **Major Features**: AG2 group chat, universal code execution via MCP, audio/video generation tools
- **New Tests**: `test_ag2_adapter.py`, `test_ag2_utils.py`, `test_code_execution.py`
- **Contributors**: @Eric-Shang @ncrispino @qidanrui @sonichi @Henry-811 and the MassGen team

## [0.0.30] - 2025-10-10

### Changed
- **Multimodal Support - Audio and Video Processing**: Extended v0.0.27's image-only multimodal foundation
  - Audio file support with WAV and MP3 formats for Chat Completions and Claude backends
  - Video file support with MP4, AVI, MOV, WEBM formats for Chat Completions and Claude backends
  - Audio/video path parameters (`audio_path`, `video_path`) for local files and HTTP/HTTPS URLs
  - Base64 encoding for local audio/video files with automatic MIME type detection
  - Configurable media file size limits (default 64MB, configurable via `media_max_file_size_mb`)
  - New audio/video content formatters in `_chat_completions_formatter.py` and `_claude_formatter.py`
  - Enhanced `base_with_mcp.py` with 340+ lines of multimodal content processing

- **Claude Code Backend SDK Update**: Updated to newer Agent SDK package
  - Migrated from `claude-code-sdk>=0.0.19` to `claude-agent-sdk>=0.0.22`
  - Updated internal SDK classes: `ClaudeCodeOptions` → `ClaudeAgentOptions`
  - Enhanced bash tool permission validation in `PathPermissionManager`
  - Improved system message handling with SDK preset support
  - New bash/shell/exec tool detection for dangerous operation prevention

- **Chat Completions Backend Enhancement**: Qwen API provider integration
  - Added Qwen API support to existing Chat Completions provider ecosystem
  - New `QWEN_API_KEY` environment variable support
  - Qwen-specific configuration examples for video understanding

### Fixed
- **Planning Mode Configuration**: Fixed crash when configuration lacks `coordination_config`
  - Added null check in `orchestrator.py` to prevent AttributeError
  - Improved graceful handling of missing planning mode configuration

- **Claude Code System Message Handling**: Resolved system message processing issues
  - Fixed system message extraction and formatting in `claude_code.py`
  - Better integration with Agent SDK for message handling

- **AG2 Adapter Import Ordering**: Resolved import sequence issues
  - Fixed import statements in `adapters/utils/ag2_utils.py`
  - Pre-commit isort formatting corrections

### Documentations, Configurations and Resources

- **Case Studies**: Comprehensive documentation for v0.0.28 and v0.0.29 features
  - `ag2-framework-integration.md`: AG2 adapter system and external framework integration
  - `mcp-planning-mode.md`: MCP Planning Mode design and implementation guide

- **New Configuration Files**: Added 7 new example configurations
  - `ag2/ag2_case_study.yaml`: AG2 framework integration case study configuration
  - `filesystem/cc_gpt5_gemini_filesystem.yaml`: Claude Code, GPT-5, and Gemini filesystem collaboration
  - `basic/single/single_gemini2.5pro.yaml`: Gemini 2.5 Pro single agent setup
  - `basic/single/single_openrouter_audio_understanding.yaml`: Audio understanding with OpenRouter
  - `basic/single/single_qwen_video_understanding.yaml`: Video understanding with Qwen API
  - `debug/test_sdk_migration.yaml`: Claude Code SDK migration testing

### Technical Details
- **Commits**: 20 commits including multimodal enhancements, Claude Code SDK migration, and documentation
- **Files Modified**: 25 files with 2,501 insertions and 84 deletions
- **Major Features**: Audio/video multimodal support, Claude Code Agent SDK migration, Qwen API integration
- **Dependencies Updated**: `anthropic>=0.61.0`, `claudecode>=0.0.12`
- **Contributors**: @ncrispino @praneeth999 @qidanrui @sonichi @Henry-811 and the MassGen team

## [0.0.29] - 2025-10-08

### Added
- **MCP Planning Mode**: New coordination strategy for irreversible MCP actions
  - New `CoordinationConfig` class with `enable_planning_mode` flag
  - Agents plan without executing during coordination, winning agent executes during final presentation
  - Orchestrator and frontend coordination UI support
  - Support for multiple backends: Response API, Chat Completions, and Gemini
  - Test suites in `test_mcp_blocking.py` and `test_gemini_planning_mode.py`

- **File Operation Tracker**: Read-before-delete enforcement for safer file operations
  - New `FileOperationTracker` class in `filesystem_manager/_file_operation_tracker.py`
  - Prevents agents from deleting files they haven't read first
  - Tracks read files and agent-created files (created files exempt from read requirement)
  - Directory deletion validation with comprehensive error messages

- **Path Permission Manager Enhancements**: Integration with FileOperationTracker
  - Added read/write/delete operation tracking methods to `PathPermissionManager`
  - Integration with `FileOperationTracker` for read-before-delete enforcement
  - Enhanced delete validation for files and batch operations
  - Extended test coverage in `test_path_permission_manager.py`

### Changed
- **Message Templates**: Improved multi-agent coordination guidance
  - Added `has_irreversible_actions` support for context path write access
  - Explicit temporary workspace path structure display for better agent understanding
  - Task handling priority hierarchy and simplified new_answer requirements
  - Unified evaluation guidance

- **MCP Tool Filtering**: Enhanced multi-level filtering capabilities
  - Combined backend-level and per-MCP-server tool filtering
  - MCP-server-specific `allowed_tools` can override backend-level settings
  - Merged `exclude_tools` from both backend and MCP server configurations

- **Backend Planning Mode Support**: Extended planning mode to multiple backends
  - Enhanced `base.py`, `response.py`, `chat_completions.py`, and `gemini.py`
  - Gemini backend now supports planning mode with session-based tool execution
  - Planning mode support across all major backend types


### Fixed
- **Circuit Breaker Logic**: Enhanced MCP server initialization in `base_with_mcp.py`
- **Final Answer Context**: Improved workspace copying when no new answer is provided
- **Multi-turn MCP Usage**: Addressed non-use of MCP in certain scenarios and improved final answer autonomy
- **Configuration Issues**: Updated Playwright automation configuration and fixed agent IDs

### Documentations, Configurations and Resources

- **MCP Planning Mode Examples**: 5 new planning mode configurations in `tools/planning/`
  - `five_agents_discord_mcp_planning_mode.yaml`: Discord MCP with planning mode (5 agents)
  - `five_agents_filesystem_mcp_planning_mode.yaml`: Filesystem MCP with planning mode
  - `five_agents_notion_mcp_planning_mode.yaml`: Notion MCP with planning mode (5 agents)
  - `five_agents_twitter_mcp_planning_mode.yaml`: Twitter MCP with planning mode (5 agents)
  - `gpt5_mini_case_study_mcp_planning_mode.yaml`: Case study configuration

- **MCP Example Configurations**: New example configurations for MCP integration in `tools/mcp/`
  - `five_agents_travel_mcp_test.yaml`: Travel planning MCP example (5 agents)
  - `five_agents_weather_mcp_test.yaml`: Weather service MCP example (5 agents)

- **Debug Configurations**: New debugging and testing utilities
  - `skip_coordination_test.yaml`: Test configuration for skipping coordination rounds

- **Documentation Updates**: Enhanced project documentation
  - Updated `permissions_and_context_files.md` in `backend/docs/` with file operation tracking details
  - Updated README with AG2 as optional installation and uv tool instructions

### Technical Details
- **Commits**: 23+ commits including planning mode, file operation tracking, and MCP enhancements
- **Files Modified**: 43 files across agent config, backend, filesystem manager, MCP tools, and configurations
- **Major Features**: MCP planning mode, FileOperationTracker, enhanced permissions, MCP tool filtering
- **New Tests**: `test_mcp_blocking.py`, `test_gemini_planning_mode.py` for planning mode validation
- **Contributors**: @ncrispino @franklinnwren @qidanrui @sonichi @praneeth999 and the MassGen team

## [0.0.28] - 2025-10-06

### Added
- **AG2 Framework Integration**: Complete adapter system for external agent frameworks
  - New `massgen/adapters/` module with base adapter architecture (`base.py`, `ag2_adapter.py`)
  - Support for AG2 ConversableAgent and AssistantAgent types
  - Code execution capabilities with multiple executor types: LocalCommandLineCodeExecutor, DockerCommandLineCodeExecutor, JupyterCodeExecutor, YepCodeCodeExecutor
  - Function/tool calling support for AG2 agents
  - Async execution with `a_generate_reply` for autonomous operation
  - AG2 utilities module for agent setup and API key management (`adapters/utils/ag2_utils.py`)

- **External Agent Backend**: New backend type for integrating external frameworks
  - New `ExternalAgentBackend` class supporting adapter registry pattern
  - Bridge between MassGen orchestration and external agent frameworks via adapters
  - Framework-specific configuration extraction and validation
  - Currently supports AG2 with extensible architecture for future frameworks

- **AG2 Test Suite**: Comprehensive test coverage for AG2 integration
  - `test_ag2_adapter.py`: AG2 adapter functionality tests
  - `test_agent_adapter.py`: Base adapter interface tests
  - `test_external_agent_backend.py`: External backend integration tests

### Fixed
- **MCP Circuit Breaker Logic**: Enhanced initialization for MCP servers
  - Improved circuit breaker state management in `base_with_mcp.py`
  - Better error handling during MCP server initialization

### Documentations, Configurations and Resources

- **AG2 Configuration Examples**: New YAML configurations demonstrating AG2 integration
  - `ag2/ag2_single_agent.yaml`: Basic single AG2 agent setup
  - `ag2/ag2_coder.yaml`: AG2 agent with code execution
  - `ag2/ag2_coder_case_study.yaml`: Multi-agent setup with AG2 and Gemini
  - `ag2/ag2_gemini.yaml`: AG2-Gemini hybrid configuration

- **Design Documentation**: Enhanced multi-source agent integration design
  - Updated `MULTI_SOURCE_AGENT_INTEGRATION_DESIGN.md` with AG2 adapter architecture

### Technical Details
- **Commits**: 12 commits including AG2 integration, testing, and configuration examples
- **Files Modified**: 18 files with 1,423 insertions and 71 deletions
- **Major Features**: AG2 framework integration, external agent backend, adapter architecture
- **New Module**: `massgen/adapters/` with AG2 support
- **Contributors**: @Eric-Shang @praneeth999 @qidanrui @sonichi @Henry-811 and the MassGen team

## [0.0.27] - 2025-10-03

### Added
- **Multimodal Support - Image Processing**: Foundation for multimodal content processing
  - New `stream_chunk` module with base classes for multimodal content (`base.py`, `text.py`, `multimodal.py`)
  - Support for image input and output in conversation messages
  - Image generation and understanding capabilities for multi-agent workflows
  - Multimodal content structure supporting images, audio, video, and documents (architecture ready)

- **File Upload and File Search**: Extended backend capabilities for document operations
  - File upload support integrated into Response backend via `_response_api_params_handler.py`
  - File search functionality for enhanced context retrieval and Q&A
  - Vector store management for file search operations
  - Cleanup utilities for uploaded files and vector stores

- **Workspace Tools Enhancements**: Extended MCP-based workspace management
  - Added `read_multimodal_files` tool for reading images as base64 data with MIME type

- **Claude Sonnet 4.5 Support**: Added latest Claude model to model mappings
  - Support for Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`)
  - Updated model registry in `utils.py`

### Changed
- **Message Architecture Refactoring**: Extracted and refactored messaging system for multimodal support
  - Extracted `StreamChunk` classes into dedicated module (`massgen/stream_chunk/`)
  - Enhanced message templates for image generation workflows
  - Improved orchestrator and chat agent for multimodal message handling

- **Backend Enhancements**: Extended backends for multimodal and file operations
  - Enhanced `response.py` with image generation, understanding, and saving capabilities
  - Improved `base_with_mcp.py` with image handling for MCP-based workflows
  - New `api_params_handler` module for centralized parameter management including file uploads
  - Better streaming and error handling for multimodal content

- **Frontend Display Improvements**: Enhanced terminal UI for multimodal content
  - Refactored `rich_terminal_display.py` for rendering images in terminal
  - Improved message formatting and visual presentation

### Documentations, Configurations and Resources

- **New Configuration Files**: Added multimodal and enhanced filesystem examples
  - `gpt4o_image_generation.yaml`: Multi-agent image generation setup
  - `gpt5nano_image_understanding.yaml`: Multi-agent image understanding configuration
  - `single_gpt4o_image_generation.yaml`: Single agent image generation
  - `single_gpt5nano_image_understanding.yaml`: Single agent image understanding
  - `single_gpt5nano_file_search.yaml`: Single agent file search example
  - `grok4_gpt5_gemini_filesystem.yaml`: Enhanced filesystem configuration
  - Updated `claude_code_gpt5nano.yaml` with improved filesystem settings

- **Case Study Documentation**: New `multi-turn-filesystem-support.md` demonstrating v0.0.25 multi-turn capabilities with Bob Dylan website example

- **Presentation Materials**: New `applied-ai-summit.html` presentation with updated build scripts and call-to-action slides

- **Example Resources**: New `multimodality.jpg` for testing multimodal capabilities under `massgen/configs/resources/v0.0.27-example/`


### Technical Details
- **Major Features**: Image processing foundation, StreamChunk architecture, file upload/search, workspace multimodal tools
- **New Module**: `massgen/stream_chunk/` with base, text, and multimodal classes
- **Contributors**: @qidanrui @sonichi @praneeth999 @ncrispino @Henry-811 and the MassGen team

## [0.0.26] - 2025-10-01

### Added
- **File Deletion and Workspace Management**: New MCP tools for workspace file operations
  - New workspace deletion tools: `delete_file`, `delete_files_batch` for managing workspace files
  - New comparison tools: `compare_directories`, `compare_files` for file diffing
  - Consolidated `_workspace_tools_server.py` replacing previous `_workspace_copy_server.py`
  - Improved workspace cleanup mechanisms for multi-turn sessions
  - Proper permission checks for all file operations

- **File-Based Context Paths**: Support for single file access without exposing entire directories
  - Context paths can now be individual files, not just directories
  - Better control over agent access to specific reference files
  - Enhanced path validation distinguishing between file and directory contexts

- **Protected Paths Feature**: Prevent agents from modifying specific reference files
  - Protected paths within write-permitted context paths
  - Agents can read but not modify protected files


### Changed
- **Code Refactoring**: Improved module structure and import paths
  - Moved utility modules from `backend/utils/` to top-level `massgen/` directory
  - Relocated `api_params_handler`, `formatter`, and `filesystem_manager` modules
  - Simplified import paths and improved code discoverability
  - Better separation of concerns between backend-specific and shared utilities

- **Path Permission Manager**: Major enhancements to permission system
  - Enhanced `will_be_writable` logic for better permission state tracking
  - Improved path validation distinguishing between context paths and workspace paths
  - Comprehensive test coverage in `test_path_permission_manager.py`
  - Better handling of edge cases and nested path scenarios

### Fixed
- **Path Permission Edge Cases**: Resolved various permission checking issues
  - Fixed file context path validation logic
  - Corrected protected path matching behavior
  - Improved handling of nested paths and symbolic links
  - Better error handling for non-existent paths

### Documentations, Configurations and Resources

- **Example Resources**: Added v0.0.26 example resources for testing new features
  - Bob Dylan themed website with multiple pages and styles
  - Additional HTML, CSS, and JavaScript examples
  - Resources organized under `massgen/configs/resources/v0.0.26-example/`

- **Design Documentation**: Added comprehensive design documentation
  - New `file_deletion_and_context_files.md` documenting file deletion and context file features
  - Updated `permissions_and_context_files.md` with v0.0.26 features
  - Added detailed examples for protected paths and file context paths

- **Release Workflow Documentation**: Added comprehensive release example checklist
  - Step-by-step guide for release preparation in `docs/workflows/release_example_checklist.md`
  - Best practices for testing new features

- **Configuration Examples**: New configuration examples for v0.0.26 features
  - `gemini_gpt5nano_protected_paths.yaml`: Protected paths example
  - `gemini_gpt5nano_file_context_path.yaml`: File-based context paths example
  - `gemini_gemini_workspace_cleanup.yaml`: Workspace cleanup example

### Technical Details
- **Commits**: 20+ commits including file deletion tools, protected paths, and refactoring
- **Files Modified**: 46 files with 4,343 insertions and 836 deletions
- **Major Features**: File deletion tools, protected paths, file-based context paths, enhanced CLI prompts
- **New Tools**: `delete_file`, `delete_files_batch`, `compare_directories`, `compare_files` MCP tools
- **Contributors**: @praneeth999 @ncrispino @qidanrui @sonichi @Henry-811 and the MassGen team

## [0.0.25] - 2025-09-29

### Added
- **Multi-Turn Filesystem Support**: Complete implementation for persistent filesystem context across conversation turns
  - Automatic session management (no flag needed)
  - Persistent workspace management across conversation turns with `.massgen` directory
  - Workspace snapshot preservation and restoration between turns
  - Support for maintaining file context and modifications throughout multi-turn sessions
  - New configuration examples: `two_gemini_flash_filesystem_multiturn.yaml`, `grok4_gpt5_gemini_filesystem_multiturn.yaml`, `grok4_gpt5_claude_code_filesystem_multiturn.yaml`
  - Design documentation in `multi_turn_filesystem_design.md`

- **SGLang Backend Integration**: Added SGLang support to inference backend alongside existing vLLM
  - New SGLang server support with default port 30000 and `SGLANG_API_KEY` environment variable
  - SGLang-specific parameters support (e.g., `separate_reasoning` for guided generation)
  - Auto-detection between vLLM and SGLang servers based on configuration
  - New configuration `two_qwen_vllm_sglang.yaml` for mixed server deployments
  - Unified `InferenceBackend` class replacing separate `vllm.py` implementation
  - Updated documentation renamed from `vllm_implementation.md` to `inference_backend.md`

- **Enhanced Path Permission System**: New exclusion patterns and validation improvements
  - Added `DEFAULT_EXCLUDED_PATTERNS` for common directories (.git, node_modules, .venv, etc.)
  - New `will_be_writable` flag for better permission state tracking
  - Improved path validation with different handling for context vs workspace paths
  - Enhanced test coverage in `test_path_permission_manager.py`

### Changed
- **CLI Enhancements**: Major improvements to command-line interface
  - Enhanced logging with configurable log levels and file output
  - Improved error handling and user feedback

- **System Prompt Improvements**: Refined agent system prompts for better performance
  - Clearer instructions for file context handling
  - Better guidance for multi-turn conversations
  - Improved prompt templates for filesystem operations

- **Documentation Updates**: Comprehensive documentation improvements
  - Updated README with clearer installation instructions

### Fixed
- **Filesystem Manager**: Resolved workspace and permission issues
  - Fixed warnings for non-existent temporary workspaces
  - Better cleanup of old workspaces
  - Fixed relative path issues in workspace copy operations

- **Configuration Issues**: Multiple configuration fixes
  - Fixed multi-agent configuration templates
  - Fixed code generation prompts for consistency

### Technical Details
- **Commits**: 30+ commits including multi-turn filesystem, SGLang integration, and bug fixes
- **Files Modified**: 33 files with 3,188 insertions and 642 deletions
- **Major Features**: Multi-turn filesystem support, unified vLLM/SGLang backend, enhanced permissions
- **New Backend**: SGLang integration alongside existing vLLM support
- **Contributors**: @praneeth999 @ncrispino @qidanrui @sonichi @Henry-811 and the MassGen team

## [0.0.24] - 2025-09-26

### Added
- **vLLM Backend Support**: Complete integration with vLLM for high-performance local model serving
  - New `vllm.py` backend supporting VLLM's OpenAI-compatible API
  - Configuration examples in `three_agents_vllm.yaml`
  - Comprehensive documentation in `vllm_implementation.md`
  - Support for large-scale model inference with optimized performance

- **POE Provider Support**: Extended ChatCompletions backend to support POE (Platform for Open Exploration)
  - Added POE provider integration for accessing multiple AI models through a single platform
  - Seamless integration with existing ChatCompletions infrastructure

- **GPT-5-Codex Model Recognition**: Added GPT-5-Codex to model registry
  - Extended model mappings in `utils.py` to recognize gpt-5-codex as a valid OpenAI model

- **Backend Utility Modules**: Major refactoring for improved modularity
  - New `api_params_handler` module for centralized API parameter management
  - New `formatter` module for standardized message formatting across backends
  - New `token_manager` module for unified token counting and management
  - Extracted filesystem utilities into dedicated `filesystem_manager` module

### Changed
- **Backend Consolidation**: Significant code refactoring and simplification
  - Refactored `chat_completions.py` and `response.py` with cleaner API handler patterns
  - Moved filesystem management from `mcp_tools` to `backend/utils/filesystem_manager`
  - Improved separation of concerns with specialized handler modules
  - Enhanced code reusability across different backend implementations

- **Documentation Updates**: Improved documentation structure
  - Moved `permissions_and_context_files.md` to backend docs
  - Added multi-source agent integration design documentation
  - Updated filesystem permissions case study for v0.0.21 and v0.0.22 features

- **CI/CD Pipeline**: Enhanced automated release process
  - Updated auto-release workflow for better reliability
  - Improved GitHub Actions configuration

- **Pre-commit Configuration**: Updated code quality tools
  - Enhanced pre-commit hooks for better code consistency
  - Updated linting rules for improved code standards

### Fixed
- **Streaming Chunk Processing**: Resolved critical bugs in chunk handling
  - Fixed chunk processing errors in response streaming
  - Improved error handling for malformed chunks
  - Better resilience in stream processing pipeline

- **Gemini Backend Session Management**: Improved cleanup
  - Implemented proper session closure for google-genai aiohttp client
  - Added explicit cleanup of aiohttp sessions to prevent potential resource leaks

### Technical Details
- **Commits**: 35 commits including backend refactoring, vLLM integration, and bug fixes
- **Files Modified**: 50+ files across backend, utilities, configurations, and documentation
- **Major Refactor**: Complete restructuring of backend utilities
- **New Backend**: vLLM integration for high-performance local inference
- **Contributors**: @qidanrui @sonichi @praneeth999 @ncrispino @Henry-811 and the MassGen team

## [0.0.23] - 2025-09-24

### Added
- **Backend Architecture Refactoring**: Major consolidation of MCP functionality
  - New `base_with_mcp.py` base class consolidating common MCP functionality (488 lines)
  - Extracted shared MCP logic from individual backends into unified base class
  - Standardized MCP client initialization and error handling across all backends

- **Formatter Module**: Extracted message and tool formatting logic into dedicated module
  - New `massgen/formatter/` module with specialized formatters
  - `message_formatter.py`: Handles message formatting across backends
  - `tool_formatter.py`: Manages tool call formatting
  - `mcp_tool_formatter.py`: Specialized MCP tool formatting

### Changed
- **Backend Consolidation**: Massive code deduplication across backends
  - Reduced `chat_completions.py` by 700+ lines
  - Reduced `claude.py` by 700+ lines
  - Simplified `response.py` by 468+ lines
  - Total reduction: ~1,932 lines removed across core backend files

### Fixed
- **Coordination Table Display**: Fixed escape key handling on macOS
  - Updated `create_coordination_table.py` and `rich_terminal_display.py`

### Technical Details
- **Commits**: 20+ commits focusing on backend refactoring and infrastructure improvements
- **Files Modified**: 100+ files across backend, documentation, CI/CD, and presentation components
- **Lines Changed**: Net reduction of ~1,932 lines through backend consolidation
- **Major Refactor**: MCP functionality extracted into shared `base_with_mcp.py` base class
- **Contributors**: @qidanrui @ncrispino @Henry-811 and the MassGen team

## [0.0.22] - 2025-09-22

### Added
- **Workspace Copy Tools via MCP**: New file copying capabilities for efficient workspace operations
  - Added `workspace_copy_server.py` with MCP-based file copying functionality (369 lines)
  - Support for copying files and directories between workspaces
  - Efficient handling of large files with streaming operations
  - Testing infrastructure for copy operations

- **Configuration Organization**: Major restructuring of configuration files for better usability
  - New hierarchical structure: `basic/`, `providers/`, `tools/`, `teams/` directories
  - Added comprehensive `README.md` for configuration guide
  - New `BACKEND_CONFIGURATION.md` with detailed backend setup
  - Organized configs by use case and provider for easier navigation
  - Added provider-specific examples (Claude, OpenAI, Gemini, Azure)

- **Enhanced File Operations**: Improved file handling for large-scale operations
  - Clear all temporary workspaces at startup for clean state
  - Enhanced security validation in MCP tools

### Changed

- **Workspace Management**: Optimized workspace operations and path handling
  - Enhanced `filesystem_manager.py` with 193 additional lines
  - Run MCP servers through FastMCP to avoid banner displays

- **Backend Enhancements**: Improved backend capabilities
  - Improved `response.py` with better error handling

### Fixed
- **Write Tool Call Issues**: Resolved large character count problems
  - Fixed write tool call issues when dealing with large character counts

- **Path Resolution Issues**: Resolved various path-related bugs
  - Fixed relative/absolute path workspace issues
  - Improved path validation and normalization

- **Documentation Fixes**: Corrected multiple documentation issues
  - Fixed broken links in case studies
  - Fixed config file paths in documentation and examples
  - Corrected example commands with proper paths

### Technical Details
- **Commits**: 50+ commits including workspace copy, configuration restructuring, and documentation improvements
- **Files Modified**: 90+ files across configs, backend, mcp_tools, and documentation
- **Major Refactoring**: Configuration file reorganization into logical categories
- **New Documentation**: Added 762+ lines of documentation for configs and backends
- **Contributors**: @ncrispino @qidanrui @Henry-811 and the MassGen team

## [0.0.21] - 2025-09-19

### Added
- **Advanced Filesystem Permissions System**: Comprehensive permission management for agent file access
  - New `PathPermissionManager` class for granular permission validation
  - User context paths with configurable READ/WRITE permissions for multi-agent file sharing
  - Test suite for permission validation in `test_path_permission_manager.py`
  - Documentation in `permissions_and_context_files.md` for implementation guide

- **Function Hook Manager**: Per-agent function call permission system
  - Refactored `FunctionHookManager` to be per-agent rather than global
  - Pre-tool-use hooks for validating file operations before execution
  - Support for write permission enforcement during context agent operations
  - Integration with all function-based backends (OpenAI, Claude, Chat Completions)

- **Grok MCP Integration**: Extended MCP support to Grok backend
  - Migrated Grok backend to inherit from Chat Completions backend
  - Full MCP server support for Grok including stdio and HTTP transports
  - Filesystem support through MCP servers

- **New Configuration Files**: Added test and example configurations
  - `grok3_mini_mcp_test.yaml`: Grok MCP testing configuration
  - `grok3_mini_mcp_example.yaml`: Grok MCP usage example
  - `grok3_mini_streamable_http_test.yaml`: Grok HTTP streaming test
  - `grok_single_agent.yaml`: Single Grok agent configuration
  - `fs_permissions_test.yaml`: Filesystem permissions testing configuration

### Changed
- **Backend Architecture**: Unified backend implementations and permission support
  - Grok backend refactored to use Chat Completions backend
  - All backends now support per-agent permission management
  - Enhanced context file support across Claude, Gemini, and OpenAI backends

### Technical Details
- **Commits**: 20+ commits including permission system, Grok MCP, and terminal improvements
- **Files Modified**: 40+ files across backends, MCP tools, permissions, and display modules
- **New Features**: Filesystem permissions, per-agent hooks, Grok MCP via Chat Completions
- **Contributors**: @Eric-Shang @ncrispino @qidanrui @Henry-811 and the MassGen team

## [0.0.20] - 2025-09-17

### Added
- **Claude Backend MCP Support**: Extended MCP (Model Context Protocol) integration to Claude backend
  - Filesystem support through MCP servers (`FilesystemSupport.MCP`) for Claude backend
  - Support for both stdio and HTTP-based MCP servers with Claude Messages API
  - Seamless integration with existing Claude function calling and tool use
  - Recursive execution model allowing Claude to autonomously chain multiple tool calls in sequence without user intervention
  - Enhanced error handling and retry mechanisms for Claude MCP operations

- **MCP Configuration Examples**: New YAML configurations for Claude MCP usage
  - `claude_mcp_test.yaml`: Basic Claude MCP testing with test server
  - `claude_mcp_example.yaml`: Claude MCP integration example
  - `claude_streamable_http_test.yaml`: HTTP transport testing for Claude MCP

- **Documentation**: Enhanced MCP technical documentation
  - `MCP_IMPLEMENTATION_CLAUDE_BACKEND.md`: Complete technical documentation for Claude MCP integration
  - Detailed architecture diagrams and implementation guides

### Changed
- **Backend Enhancements**: Improved MCP support across backends
  - Extended MCP integration from Gemini and Chat Completions to include Claude backend
  - Enhanced error reporting and debugging for MCP operations
  - Added Kimi/Moonshot API key support in Chat Completions backend

### Technical Details
- **New Features**: Claude backend MCP integration with recursive execution model
- **Files Modified**: Claude backend modules (`claude.py`), MCP tools, configuration examples
- **MCP Coverage**: Major backends now support MCP (Claude, Gemini, Chat Completions including OpenAI)
- **Contributors**: @praneeth999 @qidanrui @sonichi @ncrispino @Henry-811 MassGen development team

## [0.0.19] - 2025-09-15

### Added
- **Coordination Tracking System**: Comprehensive tracking of multi-agent coordination events
  - New `coordination_tracker.py` with `CoordinationTracker` class for capturing agent state transitions
  - Event-based tracking with timestamps and context preservation
  - Support for recording answers, votes, and coordination phases
  - New `create_coordination_table.py` utility in `massgen/frontend/displays/` for generating coordination reports

- **Enhanced Agent Status Management**: New enums for better state tracking
  - Added `ActionType` enum in `massgen/utils.py`: NEW_ANSWER, VOTE, VOTE_IGNORED, ERROR, TIMEOUT, CANCELLED
  - Added `AgentStatus` enum in `massgen/utils.py`: STREAMING, VOTED, ANSWERED, RESTARTING, ERROR, TIMEOUT, COMPLETED
  - Improved state machine for agent coordination lifecycle

### Changed
- **Frontend Display Enhancements**: Improved terminal interface with coordination visualization
  - Modified `massgen/frontend/displays/rich_terminal_display.py` to add coordination table display method
  - Added new terminal menu option 'r' to display coordination table
  - Enhanced menu system with better organization of debugging tools
  - Support for rich-formatted tables showing agent interactions across rounds

### Technical Details
- **Commits**: 20+ commits including coordination tracking system and frontend enhancements
- **Files Modified**: 5+ files across coordination tracking, frontend displays, and utilities
- **New Features**: Coordination event tracking with visualization capabilities
- **Contributors**: @ncrispino @qidanrui @sonichi @a5507203 @Henry-811 and the MassGen team

## [0.0.18] - 2025-09-12

### Added
- **Chat Completions MCP Support**: Extended MCP (Model Context Protocol) integration to ChatCompletions-based backends
  - Full MCP support for all Chat Completions providers (Cerebras AI, Together AI, Fireworks AI, Groq, Nebius AI Studio, OpenRouter)
  - Filesystem support through MCP servers (`FilesystemSupport.MCP`) for Chat Completions backend
  - Cross-provider function calling compatibility enabling seamless MCP tool execution across different providers
  - Universal MCP server compatibility with existing stdio and streamable-http transports

- **New MCP Configuration Examples**: Added 9 new Chat Completions MCP configurations
  - GPT-OSS configurations: `gpt_oss_mcp_example.yaml`, `gpt_oss_mcp_test.yaml`, `gpt_oss_streamable_http_test.yaml`
  - Qwen API configurations: `qwen_api_mcp_example.yaml`, `qwen_api_mcp_test.yaml`, `qwen_api_streamable_http_test.yaml`
  - Qwen Local configurations: `qwen_local_mcp_example.yaml`, `qwen_local_mcp_test.yaml`, `qwen_local_streamable_http_test.yaml`

- **Enhanced LMStudio Backend**: Improved local model support
  - Better tracking of attempted model loads
  - Improved server output handling and error reporting

### Changed
- **Backend Architecture**: Major MCP framework expansion
  - Extended existing v0.0.15 MCP infrastructure to support all ChatCompletions providers
  - Refactored `chat_completions.py` with 1200+ lines of MCP integration code
  - Enhanced error handling and retry mechanisms for provider-specific quirks

- **CLI Improvements**: Better backend creation and provider detection
  - Enhanced backend creation logic for improved provider handling
  - Better system message handling for different backend types

### Technical Details
- **Main Feature**: Chat Completions MCP integration enabling all providers to use MCP tools
- **Files Modified**: 20+ files across backend, mcp_tools, configurations, and CLI
- **Contributors**: @praneeth999 @qidanrui @sonichi @a5507203 @ncrispino @Henry-811 and the MassGen team

## [0.0.17] - 2025-09-10

### Added
- **OpenAI Backend MCP Support**: Extended MCP (Model Context Protocol) integration to OpenAI backend
  - Full MCP tool discovery and execution capabilities for OpenAI models
  - Support for both stdio and HTTP-based MCP servers with OpenAI
  - Seamless integration with existing OpenAI function calling
  - Robust error handling and retry mechanisms

- **MCP Configuration Examples**: New YAML configurations for OpenAI MCP usage
  - `gpt5_mini_mcp_test.yaml`: Basic OpenAI MCP testing with test server
  - `gpt5_mini_mcp_example.yaml`: Weather service integration example for OpenAI
  - `gpt5_mini_streamable_http_test.yaml`: HTTP transport testing for OpenAI MCP
  - Enhanced existing multi-agent configurations with OpenAI MCP support

- **Documentation**: Added case studies and technical documentation
  - `unified-filesystem-mcp-integration.md`: Case study demonstrating unified filesystem capabilities with MCP integration across multiple backends (from v0.0.16)
  - `MCP_INTEGRATION_RESPONSE_BACKEND.md`: Technical documentation for MCP integration with response backends

### Changed
- **Backend Enhancements**: Improved MCP support across backends
  - Extended MCP integration from Gemini and Claude Code to include OpenAI backend
  - Unified MCP tool handling across all supported backends
  - Enhanced error reporting and debugging for MCP operations

### Technical Details
- **New Features**: OpenAI backend MCP integration
- **Documentation**: Added case study for unified filesystem MCP integration
- **Contributors**: @praneeth999 @qidanrui @sonichi @ncrispino @a5507203 @Henry-811 and the MassGen team

## [0.0.16] - 2025-09-08

### Added
- **Unified Filesystem Support with MCP Integration**: Advanced filesystem capabilities designed for all backends
  - Complete `FilesystemManager` class providing unified filesystem access with extensible backend support
  - Currently supports Gemini and Claude Code backends, designed for seamless expansion to all backends
  - MCP-based filesystem operations enabling file manipulation, workspace management, and cross-agent collaboration

- **Expanded Configuration Library**: New YAML configurations for various use cases
  - **Gemini MCP Filesystem Testing**: `gemini_mcp_filesystem_test.yaml`, `gemini_mcp_filesystem_test_sharing.yaml`, `gemini_mcp_filesystem_test_single_agent.yaml`, `gemini_mcp_filesystem_test_with_claude_code.yaml`
  - **Hybrid Model Setups**: `geminicode_gpt5nano.yaml`

- **Case Studies**: Added comprehensive case studies from previous versions
  - `gemini-mcp-notion-integration.md`: Gemini MCP Notion server integration and productivity workflows
  - `claude-code-workspace-management.md`: Claude Code context sharing and workspace management demonstrations


### Technical Details
- **Commits**: 30+ commits including workspace redesign and orchestrator enhancements
- **Files Modified**: 40+ files across orchestrator, mcp_tools, configurations, and case studies
- **New Architecture**: Complete workspace management system with FilesystemManager
- **Contributors**: @ncrispino @a5507203 @sonichi @Henry-811 and the MassGen team

## [0.0.15] - 2025-09-05

### Added
- **MCP (Model Context Protocol) Integration Framework**: Complete implementation for external tool integration
  - New `massgen/mcp_tools/` package with 8 core modules for MCP support
  - Multi-server MCP client supporting simultaneous connections to multiple MCP servers
  - Two transport types: stdio (process-based) and streamable-http (web-based)
  - Circuit breaker patterns for fault tolerance and reliability
  - Comprehensive security framework with command sanitization and validation
  - Automatic tool discovery with name prefixing for multi-server setups

- **Gemini MCP Support**: Full MCP integration for Gemini backend
  - Session-based tool execution via Gemini SDK
  - Automatic tool discovery and calling capabilities
  - Robust error handling with exponential backoff
  - Support for both stdio and HTTP-based MCP servers
  - Integration with existing Gemini function calling

- **Test Infrastructure for MCP**: Development and testing utilities
  - Simple stdio-based MCP test server (`mcp_test_server.py`)
  - FastMCP streamable-http test server (`test_http_mcp_server.py`)
  - Comprehensive test suite for MCP integration

- **MCP Configuration Examples**: New YAML configurations for MCP usage
  - `gemini_mcp_test.yaml`: Basic Gemini MCP testing
  - `gemini_mcp_example.yaml`: Weather service integration example
  - `gemini_streamable_http_test.yaml`: HTTP transport testing
  - `multimcp_gemini.yaml`: Multi-server MCP configuration
  - Additional Claude Code MCP configurations

### Changed
- **Dependencies**: Updated package requirements
  - Added `mcp>=1.12.0` for official MCP protocol support
  - Added `aiohttp>=3.8.0` for HTTP-based MCP communication
  - Updated `pyproject.toml` and `requirements.txt`

- **Documentation**: Enhanced project documentation
  - Created technical analysis documents for Gemini MCP integration
  - Added comprehensive MCP tools README with architecture diagrams
  - Added security and troubleshooting guides for MCP

### Technical Details
- **Commits**: 40+ commits including MCP integration, documentation, and bug fixes
- **Files Modified**: 35+ files across MCP modules, backends, configurations, and tests
- **Security Features**: Configurable security levels (strict/moderate/permissive)
- **Contributors**: @praneeth999 @qidanrui @sonichi @a5507203 @ncrispino @Henry-811 and the MassGen team

## [0.0.14] - 2025-09-02

### Added
- **Enhanced Logging System**: Improved logging infrastructure with add_log feature
  - Better log organization and preservation for multi-agent workflows
  - Enhanced workspace management for Claude Code agents
  - New final answer directory structure in Claude Code and logs for storing final results

### Documentation
- **Release Documents**: Updated release documentation and materials
  - Updated CHANGELOG.md for better release tracking
  - Removed unnecessary use case documentation

### Technical Details
- **Commits**: 19 commits
- **Files Modified**: Logging system enhancements, documentation updates
- **New Features**: Enhanced logging, improved final presentation logging for Claude Code
- **Contributors**: @qidanrui @sonichi and the MassGen team

## [0.0.13] - 2025-08-28

### Added
- **Unified Logging System**: Better logging infrastructure for better debugging and monitoring
  - New centralized `logger_config.py` with colored console output and file logging
  - Debug mode support via `--debug` CLI flag for verbose logging
  - Consistent logging format across all backends, including Claude, Gemini, Grok, Azure OpenAI, and other providers
  - Color-coded log levels for better visibility (DEBUG: cyan, INFO: green)

- **Windows Platform Support**: Enhanced cross-platform compatibility
  - Windows-specific fixes for terminal display and color output
  - Improved path handling for Windows file systems
  - Better process management on Windows platform

### Changed
- **Frontend Improvements**: Refined display
  - Enhanced rich terminal display formatting to not show debug info in the final presentation

- **Documentation Updates**: Improved project documentation
  - Updated CONTRIBUTING.md with better guidelines
  - Enhanced README with logging configuration details
  - Renamed roadmap from v0.0.13 to v0.0.14 for future planning

### Technical Details
- **Commits**: 35+ commits including new logging system and Windows support
- **Files Modified**: 24+ files across backend, frontend, logging, and CLI modules
- **New Features**: Unified logging system with debug mode, Windows platform support
- **Contributors**: @qidanrui @sonichi @Henry-811 @JeffreyCh0 @voidcenter and the MassGen team

## [0.0.12] - 2025-08-27

### Added
- **Enhanced Claude Code Agent Context Sharing**: Improved multiple Claude Code agent coordination with workspace sharing
  - New workspace snapshot stored in orchestrator's space for better context management
  - New temporary working directory for each agent, stored in orchestrator's space
  - Claude Code agents can now share context by referencing their own temporary working directory in the orchestrator's workspace
  - Anonymous agent context mapping when referencing temporary directories
  - Improved context preservation across agent coordination cycles

- **Advanced Orchestrator Configurations**: Enhanced orchestrator configurations
  - Configurable system message support for orchestrator
  - New snapshot and temporary workspace settings for better context management

### Changed
- **Documentation Updates**: documentation improvements
  - Updated README with current features and usage examples
  - Improved configuration examples and setup instructions

### Technical Details
- **Commits**: 10+ commits including context sharing enhancements, workspace management, and configuration improvements
- **Files Modified**: 20+ files across orchestrator, backend, configuration, and documentation
- **New Features**: Enhanced Claude Code agent workspace sharing with temporary working directories and snapshot mechanisms
- **Contributors**: @qidanrui @sonichi @Henry-811 @JeffreyCh0 @voidcenter and the MassGen team

## [0.0.11] - 2025-08-25

### Known Issues
- **System Message Handling in Multi-Agent Coordination**: Critical issues affecting Claude Code agents
  - **Lost System Messages During Final Presentation** (`orchestrator.py:1183`)
    - Claude Code agents lose domain expertise during final presentation
    - ConfigurableAgent doesn't properly expose system messages via `agent.system_message`
  - **Backend Ignores System Messages** (`claude_code.py:754-762`)
    - Claude Code backend filters out system messages from presentation_messages
    - Only processes user messages, causing loss of agent expertise context
    - System message handling only works during initial client creation, not with `reset_chat=True`
  - **Ambiguous Configuration Sources**
    - Multiple conflicting system message sources: `custom_system_instruction`, `system_prompt`, `append_system_prompt`
    - Backend parameters silently override AgentConfig settings
    - Unclear precedence and behavior documentation
  - **Architecture Violations**
    - Orchestrator contains Claude Code-specific implementation details
    - Tight coupling prevents easy addition of new backends
    - Violates separation of concerns principle

### Fixed
- **Custom System Message Support**: Enhanced system message configuration and preservation
  - Added `base_system_message` parameter to conversation builders for agent's custom system message
  - Orchestrator now passes agent's `get_configurable_system_message()` to conversation builders
  - Custom system messages properly combined with MassGen coordination instructions instead of being overwritten
  - Backend-specific system prompt customization (system_prompt, append_system_prompt)
- **Claude Code Backend Enhancements**: Improved integration and configuration
  - Better system message handling and extraction
  - Enhanced JSON structured response parsing
  - Improved coordination action descriptions
- **Final Presentation & Agent Logic**: Enhanced multi-agent coordination (#135)
  - Improved final presentation handling for Claude Code agents
  - Better coordination between agents during final answer selection
  - Enhanced CLI presentation logic
  - Agent configuration improvements for workflow coordination
- **Evaluation Message Enhancement**: Improved synthesis instructions
  - Changed to "digest existing answers, combine their strengths, and do additional work to address their weaknesses"
  - Added "well" qualifier to evaluation questions
  - More explicit guidance for agents to synthesize and improve upon existing answers

### Changed
- **Documentation Updates**: Enhanced project documentation
  - Renamed roadmap from v0.0.11 to v0.0.12 for future planning
  - Updated README with latest features and improvements
  - Improved CONTRIBUTING guidelines
  - Enhanced configuration examples and best practices

### Added
- **New Configuration Files**: Introduced additional YAML configuration files
  - Added `multi_agent_playwright_automation.yaml` for browser automation workflows

### Removed
- **Deprecated Configurations**: Cleaned up configuration files
  - Removed `gemini_claude_code_paper_search_mcp.yaml`
  - Removed `gpt5_claude_code_paper_search_mcp.yaml`
- **Gemini CLI Tests**: Removed Gemini CLI related tests

### Technical Details
- **Commits**: 25+ commits including bug fixes, feature additions, and improvements
- **Files Modified**: 35+ files across backend, orchestrator, frontend, configuration, and documentation
- **New Configuration**: `multi_agent_playwright_automation.yaml` for browser automation workflows
- **Contributors**: @qidanrui @Leezekun @sonichi @voidcenter @Daucloud @Henry-811 and the MassGen team

## [0.0.10] - 2025-08-22

### Added
- **Azure OpenAI Support**: Integration with Azure OpenAI services
  - New `azure_openai.py` backend with async streaming capabilities
  - Support for Azure-hosted GPT-4.1 and GPT-5-chat models
  - Configuration examples for single and multi-agent Azure setups
  - Test suite for Azure OpenAI functionality
- **Enhanced Claude Code Backend**: Major refactoring and improvements
  - Simplified MCP (Model Context Protocol) integration
- **Final Presentation Support**: New orchestrator presentation capabilities
  - Support for final answer presentation in multi-agent scenarios
  - Fallback mechanisms for presentation generation
  - Test coverage for presentation functionality

### Fixed
- **Claude Code MCP**: Cleaned up and simplified MCP implementation
  - Removed redundant MCP server and transport modules
- **Configuration Management**: Improved YAML configuration handling
  - Fixed Azure OpenAI deployment configurations
  - Updated model mappings for Azure services

### Changed
- **Backend Architecture**: Significant refactoring of backend systems
  - Consolidated Azure OpenAI implementation using AsyncAzureOpenAI
  - Improved error handling and streaming capabilities
  - Enhanced async support across all backends
- **Documentation Updates**: Enhanced project documentation
  - Updated README with Azure OpenAI setup instructions
  - Renamed roadmap from v0.0.10 to v0.0.11
  - Improved presentation materials for DataHack Summit 2025
- **Test Infrastructure**: Expanded test coverage
  - Added comprehensive Azure OpenAI backend tests
  - Integration tests for final presentation functionality
  - Simplified test structure with better coverage

### Removed
- **Deprecated MCP Components**: Removed unused MCP modules
  - Removed standalone MCP client, transport, and server implementations
  - Cleaned up MCP test files and testing checklist
  - Simplified Claude Code backend by removing redundant MCP code

### Technical Details
- **Commits**: 35+ commits including Azure OpenAI integration and Claude Code improvements
- **Files Modified**: 30+ files across backend, configuration, tests, and documentation
- **New Backend**: Azure OpenAI backend with full async support
- **Contributors**: @qidanrui @Leezekun @sonichi and the MassGen team

## [0.0.9] - 2025-08-22

### Added
- **Quick Start Guide**: Comprehensive quickstart documentation in README
  - Streamlined setup instructions for new users
  - Example configurations for getting started quickly
  - Clear installation and usage steps
- **Multi-Agent Configuration Examples**: New configuration files for various setups
  - Paper search configuration with GPT-5 and Claude Code
  - Multi-agent setups with different model combinations
- **Roadmap Documentation**: Added comprehensive roadmap for version 0.0.10
  - Focused on Claude Code context sharing between agents
  - Multi-agent context synchronization planning
  - Enhanced backend features and CLI improvements roadmap

### Fixed
- **Web Search Processing**: Fixed bug in response handling for web search functionality
  - Improved error handling in web search responses
  - Better streaming of search results
- **Rich Terminal Display**: Fixed rendering issues in terminal UI
  - Resolved display formatting problems
  - Improved message rendering consistency

### Changed
- **Claude Code Integration**: Optimized Claude Code implementation
  - MCP (Model Context Protocol) integration
  - Streamlined Claude Code backend configuration
- **Documentation Updates**: Enhanced project documentation
  - Updated README with quickstart guide
  - Added CONTRIBUTING.md guidelines
  - Improved configuration examples

### Technical Details
- **Commits**: 10 commits including bug fixes, code cleanup, and documentation updates
- **Files Modified**: Multiple files across backend, configurations, and documentation
- **Contributors**: @qidanrui @sonichi @Leezekun @voidcenter @JeffreyCh0 @stellaxiang

## [0.0.8] - 2025-08-18

### Added
- **Timeout Management System**: Timeout capabilities for better control and time management
  - New `TimeoutConfig` class for configuring timeout settings at different levels
  - Orchestrator-level timeout with graceful fallback
  - Added `fast_timeout_example.yaml` configuration demonstrating conservative timeout settings
  - Test suite for timeout mechanisms in `test_timeout.py`
  - Timeout indicators in Rich Terminal Display showing remaining time
- **Enhanced Display Features**: Improved visual feedback and user experience
  - Optimized message display formatting for better readability
  - Enhanced status indicators for timeout warnings and fallback notifications
  - Improved coordination UI with better multi-agent status tracking

### Fixed
- **Display Optimization**: Multiple improvements to message rendering
  - Fixed message display synchronization issues
  - Optimized terminal display refresh rates
  - Improved handling of concurrent agent outputs
  - Better formatting for multi-line responses
- **Configuration Management**: Enhanced robustness of configuration loading
  - Fixed import ordering issues in CLI module
  - Improved error handling for missing configurations
  - Better validation of timeout settings

### Changed
- **Orchestrator Architecture**: Simplified and enhanced timeout implementation
  - Refactored timeout handling to be more efficient and maintainable
  - Improved graceful degradation when timeouts occur
  - Better integration with frontend displays for timeout notifications
  - Enhanced error messages for timeout scenarios
- **Code Cleanup**: Removed deprecated configurations and improved code organization
  - Removed obsolete `two_agents_claude_code` configuration
  - Cleaned up unused imports and redundant code
  - Reformatted files for better consistency
- **CLI Enhancements**: Improved command-line interface functionality
  - Better timeout configuration parsing
  - Enhanced error reporting for timeout scenarios
  - Improved help documentation for timeout settings

### Technical Details
- **Commits**: 18 commits including various optimizations and bug fixes
- **Files Modified**: 13+ files across orchestrator, frontend, configuration, and test modules
- **Key Features**: Timeout management system with graceful fallback, enhanced display optimizations
- **New Configuration**: `fast_timeout_example.yaml` for time-conscious usage
- **Contributors**: @qidanrui @Leezekun @sonichi @voidcenter

## [0.0.7] - 2025-08-15

### Added
- **Local Model Support**: Complete integration with LM Studio for running open-weight models locally
  - New `lmstudio.py` backend with automatic server management
  - Automatic model downloading and loading capabilities
  - Zero-cost reporting for local model usage
- **Extended Provider Support**: Enhanced ChatCompletionsBackend to support multiple providers
  - Cerebras AI, Together AI, Fireworks AI, Groq, Nebius AI Studio, OpenRouter
  - Provider-specific environment variable detection
  - Automatic provider name inference from base URLs
- **New Configuration Files**: Added configurations for local and hybrid model setups
  - `lmstudio.yaml`: Single agent configuration for LM Studio
  - `two_agents_opensource_lmstudio.yaml`: Hybrid setup with GPT-5 and local Qwen model
  - `gpt5nano_glm_qwen.yaml`: Three-agent setup combining Cerebras, ZAI GLM-4.5, and local Qwen
  - Updated `three_agents_opensource.yaml` for open-source model combinations

### Fixed
- **Backend Stability**: Improved error handling across all backend systems
  - Fixed API key resolution and client initialization
  - Enhanced provider name detection and configuration
  - Resolved streaming issues in ChatCompletionsBackend
- **Documentation**: Corrected references and updated model naming conventions
  - Fixed GPT model references in documentation diagrams
  - Updated case study file naming consistency

### Changed
- **Backend Architecture**: Refactored ChatCompletionsBackend for better extensibility
  - Improved provider registry and configuration management
  - Enhanced logging and debugging capabilities
  - Streamlined message processing and tool handling
- **Dependencies**: Added new requirements for local model support
  - Added `lmstudio==1.4.1` for LM Studio Python SDK integration
- **Documentation Updates**: Enhanced documentation for local model usage
  - Updated environment variables documentation
  - Added setup instructions for LM Studio integration
  - Improved backend configuration examples

### Technical Details
- **Commits**: 16 commits including merge pull requests #80 and #100
- **Files Modified**: 17+ files across backend, configuration, documentation, and CLI modules
- **New Dependencies**: LM Studio SDK (`lmstudio==1.4.1`)
- **Contributors**: @qidanrui @sonichi @Leezekun @praneeth999 @voidcenter

## [0.0.6] - 2025-08-13

### Added
- **GLM-4.5 Model Support**: Integration with ZhipuAI's GLM-4.5 model family
  - Added GLM-4.5 backend support in `chat_completions.py`
  - New configuration file `zai_glm45.yaml` for GLM-4.5 agent setup
  - Updated `zai_coding_team.yaml` with GLM-4.5 integration
  - Added GLM-4.5 model mappings and environment variable support
- **Enhanced Reasoning Display**: Improved reasoning presentation for GLM models
  - Added reasoning start and completion indicators in frontend displays
  - Enhanced coordination UI to show reasoning progress
  - Better visual formatting for reasoning states in terminal display

### Fixed
- **Claude Code Backend**: Updated default allowed tools configuration
  - Fixed default tools setup in `claude_code.py` backend

### Changed
- **Documentation Updates**: Updated README.md with GLM-4.5 support information
  - Added GLM-4.5 to supported models list
  - Updated environment variables documentation for ZhipuAI integration
  - Enhanced model comparison and configuration examples
- **Configuration Management**: Enhanced agent configuration system
  - Updated `agent_config.py` with GLM-4.5 support
  - Improved CLI integration for GLM models
  - Better model parameter handling in utils.py

### Technical Details
- **Commits**: 6 major commits including merge pull requests #90 and #94
- **Files Modified**: 12+ files across backend, frontend, configuration, and documentation
- **New Dependencies**: ZhipuAI GLM-4.5 model integration
- **Contributors**: @Stanislas0 @qidanrui @sonichi @Leezekun @voidcenter

## [0.0.5] - 2025-08-11

### Added
- **Claude Code Integration**: Complete integration with Claude Code CLI backend
  - New `claude_code.py` backend with streaming capabilities and tool support
  - Support for Claude Code SDK with stateful conversation management
  - JSON tool call functionality and proper tool result handling
  - Session management with append system prompt support
- **New Configuration Files**: Added Claude Code specific YAML configurations
  - `claude_code_single.yaml`: Single agent setup using Claude Code backend
  - `claude_code_flash2.5.yaml`: Multi-agent setup with Claude Code and Gemini Flash 2.5
  - `claude_code_flash2.5_gptoss.yaml`: Multi-agent setup with Claude Code, Gemini Flash 2.5, and GPT-OSS
- **Test Coverage**: Added test suite for Claude Code functionality
  - `test_claude_code_orchestrator.py`: orchestrator testing
  - Backend-specific test coverage for Claude Code integration

### Fixed
- **Backend Stability**: Multiple critical bug fixes across all backend systems
  - Fixed parameter handling in `chat_completions.py`, `claude.py`, `gemini.py`, `grok.py`
  - Resolved response processing issues in `response.py`
  - Improved error handling and client existence validation
- **Tool Call Processing**: Enhanced tool call parsing and execution
  - Deduplicated tool call parsing logic across backends
  - Fixed JSON tool call functionality and result formatting
  - Improved builtin tool result handling in streaming contexts
- **Message Handling**: Resolved system message processing issues
  - Fixed SystemMessage to StreamChunk conversion
  - Proper session info extraction from system messages
  - Cleaned up message formatting and display consistency
- **Frontend Display**: Fixed output formatting and presentation
  - Improved rich terminal display formatting
  - Better coordination UI integration and multi-turn conversation display
  - Enhanced status message display with proper newline handling

### Changed
- **Code Architecture**: Significant refactoring and cleanup across the codebase
  - Renamed and consolidated backend files for consistency
  - Simplified chat agent architecture and removed redundant code
  - Streamlined orchestrator logic with improved error handling
- **Configuration Management**: Updated and cleaned up configuration files
  - Updated agent configuration with Claude Code support
- **Backend Infrastructure**: Enhanced backend parameter handling
  - Improved stateful conversation management across all backends
  - Better integration with orchestrator for multi-agent coordination
  - Enhanced streaming capabilities with proper chunk processing
- **Documentation**: Updated project documentation
  - Added Claude Code setup instructions in README
  - Updated backend architecture documentation
  - Improved reasoning and streaming integration notes

### Technical Details
- **Commits**: 50+ commits since version 0.0.4
- **Files Modified**: 25+ files across backend, configuration, frontend, and test modules
- **Major Components Updated**: Backend systems, orchestrator, frontend display, configuration management
- **New Dependencies**: Added Claude Code SDK integration
- **Contributors**: @qidanrui @randombet @sonichi

## [0.0.4] - 2025-08-08

### Added
- **GPT-5 Series Support**: Full support for OpenAI's GPT-5 model family
  - GPT-5: Full-scale model with advanced capabilities
  - GPT-5-mini: Efficient variant for faster responses
  - GPT-5-nano: Lightweight model for resource-constrained deployments
- **New Model Parameters**: Introduced GPT-5 specific configuration options
  - `text.verbosity`: Control response detail level (low/medium/high)
  - `reasoning.effort`: Configure reasoning depth (minimal/medium/high)
  - Note: reasoning parameter is mutually exclusive with web search capability
- **Configuration Files**: Added dedicated YAML configurations
  - `gpt5.yaml`: Three-agent setup with GPT-5, GPT-5-mini, and GPT-5-nano
  - `gpt5_nano.yaml`: Three GPT-5-nano agents with different reasoning levels
- **Extended Model Support**: Added GPT-5 series to model mappings in utils.py
- **Reasoning for All Models**: Extended reasoning parameter support beyond GPT-5 models

### Fixed
- **Tool Output Formatting**: Added proper newline formatting for provider tool outputs
  - Web search status messages now display on new lines
  - Code interpreter status messages now display on new lines
  - Search query display formatting improved
- **YAML Configuration**: Fixed configuration syntax in GPT-5 related YAML files
- **Backend Response Handling**: Multiple bug fixes in response.py for proper parameter handling

### Changed
- **Documentation Updates**:
  - Updated README.md to highlight GPT-5 series support
  - Changed example commands to use GPT-5 models
  - Added new backend configuration examples with GPT-5 specific parameters
  - Updated models comparison table to show GPT-5 as latest OpenAI model
- **Parameter Handling**: Improved backend parameter validation
  - Temperature parameter now excluded for GPT-5 series models (like o-series)
  - Max tokens parameter now excluded for GPT-5 series models
  - Added conditional logic for GPT-5 specific parameters (text, reasoning)
- **Version Number**: Updated to 0.0.4 in massgen/__init__.py

### Technical Details
- **Commits**: 9 commits since version 0.0.3
- **Files Modified**: 6 files (response.py, utils.py, README.md, __init__.py, and 2 new config files)
- **Contributors**: @qidanrui @sonichi @voidcenter @JeffreyCh0 @praneeth999

## [0.0.3] - 2025-08-03

### Added
- Complete architecture with foundation release
- Multi-backend support: Claude (Messages API), Gemini (Chat API), Grok (Chat API), OpenAI (Responses API)
- Builtin tools: Code execution and web search with streaming results
- Async streaming with proper chat agent interfaces and tool result handling
- Multi-agent orchestration with voting and consensus mechanisms
- Real-time frontend displays with multi-region terminal UI
- CLI with file-based YAML configuration and interactive mode
- Proper StreamChunk architecture separating tool_calls from builtin_tool_results
- Multi-turn conversation support with dynamic context reconstruction
- Chat interface with orchestrator supporting async streaming
- Case study configurations and specialized YAML configs
- Claude backend support with production-ready multi-tool API and streaming
- OpenAI builtin tools support for code execution and web search streaming

### Fixed
- Grok backend testing and compatibility issues
- CLI multi-turn conversation display with coordination UI integration
- Claude streaming handler with proper tool argument capture
- CLI backend parameter passing with proper ConfigurableAgent integration

### Changed
- Restructured codebase with new architecture
- Improved message handling and streaming capabilities
- Enhanced frontend features and user experience

## [0.0.1] - Initial Release

### Added
- Basic multi-agent system framework
- Support for OpenAI, Gemini, and Grok backends
- Simple configuration system
- Basic streaming display
- Initial logging capabilities
