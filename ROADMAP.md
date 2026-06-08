# MassGen Roadmap

**Current Version:** v0.1.95

**Release Schedule:** Mondays, Wednesdays, Fridays @ 9am PT

**Last Updated:** June 8, 2026

This roadmap outlines MassGen's development priorities for upcoming releases. Each release focuses on specific capabilities with real-world use cases.

---

## 👥 Contributors & Contact

Want to contribute or collaborate on a specific track? Reach out to the track owners below:

| Track | GitHub | Discord |
|-------|--------|---------|
| Tool System Refactoring | [@qidanrui](https://github.com/qidanrui) | danrui2020 |
| Multimodal Support | [@qidanrui](https://github.com/qidanrui) | danrui2020 |
| General Interoperability | [@qidanrui](https://github.com/qidanrui) | danrui2020 |
| RL Integration | [@qidanrui](https://github.com/qidanrui) [@praneeth999](https://github.com/praneeth999) | danrui2020, ram2561 |
| Agent Adapter System | [@Eric-Shang](https://github.com/Eric-Shang) | ericshang. |
| Framework Streaming | [@Eric-Shang](https://github.com/Eric-Shang) | ericshang. |
| Irreversible Actions Safety | [@franklinnwren](https://github.com/franklinnwren) | zhichengren |
| Computer Use | [@franklinnwren](https://github.com/franklinnwren) | zhichengren |
| Memory Module | [@qidanrui](https://github.com/qidanrui) [@ncrispino](https://github.com/ncrispino) | danrui2020, nickcrispino |
| Rate Limiting System | [@AbhimanyuAryan](https://github.com/AbhimanyuAryan) | abhimanyuaryan |
| DSPy Integration | [@praneeth999](https://github.com/praneeth999) | ram2561 |
| MassGen Handbook | [@a5507203](https://github.com/a5507203) [@Henry-811](https://github.com/Henry-811) | crinvo, henry_weiqi |
| Session Management | [@ncrispino](https://github.com/ncrispino) | nickcrispino |
| Automatic MCP Tool Selection | [@ncrispino](https://github.com/ncrispino) | nickcrispino |
| Parallel File Operations | [@ncrispino](https://github.com/ncrispino) | nickcrispino |
| MassGen Terminal Evaluation | [@ncrispino](https://github.com/ncrispino) | nickcrispino |
| Textual Terminal Display | [@praneeth999](https://github.com/praneeth999) | ram2561 |
| Web UI | [@voidcenter](https://github.com/voidcenter) | justin_zhang |

*For general questions, join the #massgen channel on [Discord](https://discord.gg/VVrT2rQaz5)*

---


| Release | Target | Feature | Owner | Use Case |
|---------|--------|---------|-------|----------|
| **v0.1.96** | TBD | Image/Video Edit Capabilities | @ncrispino | Check and support img/video editing capabilities — deferred from v0.1.86-v0.1.95 ([#959](https://github.com/massgen/MassGen/issues/959)) |

*All releases ship on MWF @ 9am PT when ready*

---

## ✅ v0.1.95 - Mid-Stream Steering (Completed)

**Released:** June 8, 2026

### Features
- **Programmatic Steering Inbox (`--inbox-dir`)**: `send_steering_message()` (`massgen/steering.py`) writes a `msg_*.json` to a caller-known inbox; `RuntimeInboxPoller` routes it through `RuntimeInputDelivery` to the same `set_pending_input` chokepoint the TUI/WebUI use, so `--automation` and any UI-less caller can inject mid-stream human input (with one/subset/broadcast targeting)
- **Interrupt-and-Resume Steering (Codex & Antigravity)**: steering mid-turn kills the in-flight turn and resumes (`codex exec resume <session> <prompt>` / `agy --continue -p <prompt>`) instead of waiting for a round boundary; Antigravity promotes pre-interrupt scratch deliverables first
- **MCP-Server-Hook Payload IPC (Antigravity, codex parity)**: `write_post_tool_use_hook()` / `read_unconsumed_hook_content()` with `expires_at`-guarded payloads consumed by the MCP middleware, enabling the backend-agnostic per-chunk injection flush for `agy`
- **Antigravity `--model` wired through**: the resolved model label is now actually passed to `agy`

### Bug Fixes
- `--inbox-dir` honored for resumed sessions (`--session-id` / config `session_id` / `--continue`), not just new sessions
- `read_unconsumed_hook_content()` honors `expires_at` so stale steering can't trigger an unexpected interrupt/resume (both backends)
- Watcher-cleanup failures logged at debug instead of swallowed (both backends)
- Round-1 native-hook gap closed (Antigravity `hook_dir` set at orchestrator fetch time); middleware `hook_dir` coerced to `Path`

### Notes
- All items landed under TDD, with deterministic coverage plus opt-in live-fire tests.
- Image/Video Edit Capabilities ([#959](https://github.com/massgen/MassGen/issues/959)) remain deferred to v0.1.96.

---

## ✅ v0.1.94 - Parallelism Hardening (Engineering Health) (Completed)

**Released:** June 5, 2026

### Features
- **Snapshot Copy Off the Event Loop**: `FilesystemManager.copy_snapshots_to_temp_workspace` offloads its blocking `rmtree`/`copytree`/scrub to a worker thread via `asyncio.to_thread`, so one agent's snapshot copy no longer serializes every other agent's streaming
- **Immutable, Versioned Snapshots**: snapshots publish to `<base>/.versions/<id>/v<N>` with an atomically-repointed symlink; readers `acquire`/refcount the current version for the duration of their copy (new `SnapshotVersionStore`), eliminating the read-during-write race the off-loop copy would otherwise expose
- **Concurrency Correctness**: fixed lost peer-answer revisions (R1), lost background-subagent results (R2/R3), leaked background trace tasks on cleanup (R4), and a cancel-without-await teardown (R5)
- **Worktree-Isolation Degradation Surfaced (D2)**: an invalid `emit_status(status=…)` kwarg had its `TypeError` swallowed, silencing the signal entirely
- **Unified Mid-Stream Injection (A1)**: the two ~150-line per-backend `get_injection_content` closures collapsed into one `build_midstream_injection(..., native=)`; the background-wait interrupt provider was deduplicated, removing backend-parity drift

### Notes
- Engineering-health release: no per-backend functionality changes (parity principle); all items landed under TDD with cost-free simulation.
- Image/Video Edit Capabilities ([#959](https://github.com/massgen/MassGen/issues/959)) remain deferred to v0.1.95.

---

## ✅ v0.1.93 - CLI Package Decomposition & Pydantic Config Migration (Completed)

**Released:** June 3, 2026

### Features
- **CLI Package Decomposition**: The monolithic `massgen/cli.py` (12,206 lines) was split into an 18-module `massgen/cli/` package with a facade that preserves the public import surface; the ~886-line Textual per-turn handler was extracted into a dependency-injected function
- **Pydantic Config Migration**: Config classes migrated to `pydantic.dataclasses` (type validation on construction) with `Literal`-typed modes in `massgen/config_modes.py` that `config_validator` derives from — closing a real validator-drift bug
- **Single-Source Exclusion Lists**: The two hand-duplicated "params never forwarded to provider APIs" lists now derive from one frozenset, locked by a regression test
- **Dead Code Removal**: Deleted ~8,700 lines of unreferenced legacy `v1`/`prototype` code that was shipping in the wheel
- **Tooling**: Fixed the broken coverage gate, enabled a no-assert test guard, enforced `uv.lock` in CI, and re-enabled type checking via an incremental mypy ratchet
- **Fixes**: Concurrent-run log isolation (MAS-274), a config default regression, and logged (not silent) backend tool-arg parsing

### Notes
- Internal-quality release: runtime behavior is preserved.
- Image/Video Edit Capabilities ([#959](https://github.com/massgen/MassGen/issues/959)) remain deferred to v0.1.94.

---

## ✅ v0.1.92 - Orchestrator Collaborator Refactor & Parallel Search MCP (Completed)

**Released:** June 1, 2026

### Features
- **Orchestrator Collaborator Extraction**: `orchestrator.py` dropped from 21,599 to 8,574 lines by extracting 49 lazy collaborators into `massgen/orchestrator_collaborators/`
- **Stable Delegator Surface**: Public methods remain available through thin delegators, preserving existing internal and external call sites
- **Textual Display Cleanup**: Provider/model helpers, terminal capability probing, and widget-debug helpers moved out of `textual_terminal_display.py` into focused sibling modules
- **Parallel Web Search MCP**: New `parallel_search` MCP registry entry and `massgen/configs/tools/web-search/parallel_search_example.yaml` for Parallel's hosted Search MCP server
- **Refactor Roadmap**: `docs/dev_notes/orchestrator_refactor_roadmap.md` documents remaining high-risk follow-up extraction work
- **Tests**: 77 new characterization cases cover orchestrator and Textual display contracts, with existing integration/unit seams repointed to the collaborators

### Notes
- Image/Video Edit Capabilities ([#959](https://github.com/massgen/MassGen/issues/959)) remain deferred to v0.1.94.

---

## ✅ v0.1.91 - Config Reliability & Hook Safety (Completed)

**Released:** May 27, 2026

### Features
- **Centralized Config Wiring**: `CoordinationConfig.from_dict()` and `TimeoutConfig.from_dict()` now own YAML parsing for coordination and timeout settings, while `AgentConfig.apply_orchestrator_config()` owns top-level orchestrator runtime field application
- **Config Drift Detection**: Unknown `orchestrator.coordination.*`, top-level `orchestrator.*`, and `timeout_settings.*` keys now produce validation warnings, and strict config validation treats those warnings as release-blocking
- **Checklist Runtime Controls**: `max_checklist_calls_per_round` and `checklist_first_answer` now flow through the centralized top-level orchestrator runtime helper instead of being validation-only settings
- **Native Hook Permission Safety**: Gemini CLI and Codex standalone hook scripts now enforce more-specific managed paths and protected paths before broader writable parents
- **Claude Hook Contract Alignment**: Claude Code native hook tests and docs now match the SDK-native `additionalContext` injection format
- **Tests**: New parser/validator parity coverage and native hook regression tests protect these release-critical paths

### Notes
- Image/Video Edit Capabilities ([#959](https://github.com/massgen/MassGen/issues/959)) remain deferred to v0.1.94.

---

## ✅ v0.1.90 - Discriminative Criteria Refinements & Checklist Calibration (Completed)

**Released:** May 25, 2026

### Features
- **Discriminative-Power Pruning**: Bootstrap criteria now compute per-criterion score spread across agents and demote low-spread criteria to `stretch`, keeping low-signal checks visible without letting them act as hard gates
- **Criterion Feedback Loop**: Checklist reasoning is extracted into a next-round feedback memo so agents see exactly which criterion gaps to address
- **Position-Bias Calibration**: Candidate answer ordering is rotated per scoring agent, distributing the primacy slot and reducing self-preference
- **Checklist Gate Unification**: `ChecklistGate.from_budget(...)` derives effective threshold, required-true count, and confidence cutoff from one 0-10 scale
- **Shared Score Utilities**: `massgen/score_utils.py` centralizes score extraction and per-agent score-shape detection across checklist, quality, and bootstrap paths
- **Fast-Iteration Config Updates**: Fast-iteration examples now default to local command execution and current Gemini/Codex/Antigravity pairings
- **Tests**: New coverage for discriminative pruning, criterion feedback, position-bias calibration, score parsing, and checklist server behavior

### Notes
- Discriminative Criteria Refinements from the roadmap landed in this release.
- Image/Video Edit Capabilities ([#959](https://github.com/massgen/MassGen/issues/959)) remain deferred to v0.1.94.

---

## ✅ v0.1.89 - Antigravity CLI Full Integration & Hardening (Completed)

**Released:** May 22, 2026 | PRs: [#1099](https://github.com/massgen/MassGen/pull/1099)

### Features
- **Workflow-Mode Parity**: Antigravity now mirrors Gemini CLI's workflow handling for `new_answer` / `vote`, including `new_answer_only` rounds, post-evaluation guards, and duplicate workflow-call suppression
- **Auth and Binary Health Checks**: The backend verifies `agy --version` and fails fast when neither API-key auth nor cached Google OAuth credentials are available
- **Workspace Write Reliability**: MassGen passes `--add-dir <cwd>` and creates a workspace-root `.antigravitycli/` marker so agy writes files into the shared workspace instead of hidden scratch directories
- **Native Hooks**: Antigravity native hooks now use standalone `hooks.json` plus `enableJsonHooks`
- **Prompt Guardrails**: `TaskContextSection` hides `spawn_subagents` when subagents are disabled, preventing phantom subagent MCP calls in multimodal-only runs
- **Tests**: `massgen/tests/test_antigravity_cli_backend.py` and `massgen/tests/test_system_prompt_sections.py` cover health checks, auth, workspace anchoring, hooks, workflow filtering, and prompt affordance gating

### Notes
- This completes the follow-up Antigravity integration pass introduced in v0.1.88.
- Discriminative Criteria Refinements landed in v0.1.90; Image/Video Edit Capabilities ([#959](https://github.com/massgen/MassGen/issues/959)) remain deferred to v0.1.94.

---

## ✅ v0.1.88 - Antigravity CLI Backend (Completed)

**Released:** May 20, 2026 | PRs: [#1097](https://github.com/massgen/MassGen/pull/1097)

### Features
- **Antigravity CLI Backend**: New `antigravity_cli` backend wraps Google's `agy` binary as a MassGen backend
- **Workspace-Local Isolation**: Antigravity config and MCP settings are written under `.antigravity/` in the run workspace via `--gemini_dir`, avoiding global `~/.gemini/` mutation
- **MCP Config Translation**: MassGen MCP server entries are translated to Antigravity's schema, including `serverUrl` for HTTP servers
- **Native Hook Adapter**: `AntigravityCLINativeHookAdapter` reuses Gemini CLI hook behavior for Antigravity's compatible hook protocol
- **Example Configs**: `massgen/configs/providers/antigravity/antigravity_cli_local.yaml` and `massgen/configs/features/fast_iteration_gemini_antigravity.yaml`
- **Tests**: `massgen/tests/test_antigravity_cli_backend.py` covers command construction, config isolation, MCP schema, workflow JSON envelopes, Docker/API-key constraints, hook wiring, and env passthrough

### Notes
- Follow-up Antigravity hardening landed in v0.1.89; Discriminative Criteria Refinements landed in v0.1.90; Image/Video Edit Capabilities ([#959](https://github.com/massgen/MassGen/issues/959)) remain deferred to v0.1.94.

---

## ✅ v0.1.87 - Documentation: Framework Comparisons & `llms.txt` (Completed)

**Released:** May 15, 2026 | PRs: [#1094](https://github.com/massgen/MassGen/pull/1094)

### Features
- **Framework Comparison Pages**: Three new "MassGen vs ..." pages — `crewai.rst`, `langgraph.rst`, `autogen.rst` — under `docs/source/reference/comparisons/`, positioning MassGen against each framework's coordination shape
- **`llms.txt` Index**: Curated [llmstxt.org](https://llmstxt.org)-spec index published at the docs site root via Sphinx `html_extra_path`
- **`llms-full.txt` Corpus**: Concatenated full-docs dump (~1 MB, 59 files), generated by a Sphinx `build-finished` hook in `conf.py`
- **Docs Landing Page Update**: "How Does MassGen Compare?" now lists all four comparisons (LLM Council + the three new ones); parent `comparisons.rst` drops "coming soon" and gains a toctree
- **README Pointers**: One-line pointer in `README.md` / `README_PYPI.md` directing AI agents to `llms.txt` / `llms-full.txt`
- **`bootstrap_subagent` Single-Shot Fix**: `Orchestrator._run_bootstrap_discriminator_step` passes `refine=False` to `spawn_subagent` — the canonical knob `SubagentManager` respects at the orchestrator level (the orchestrator's `max_new_answers_per_agent: 3` default was shadowing coordination-dict overrides)

### Notes
- Image/Video Edit Capabilities ([#959](https://github.com/massgen/MassGen/issues/959)) ultimately carried forward to v0.1.94.
- Closes [#1082](https://github.com/massgen/MassGen/issues/1082) (`llms.txt` + `llms-full.txt`) and [#1083](https://github.com/massgen/MassGen/issues/1083) (CrewAI / LangGraph / AutoGen comparison pages).

---

## ✅ v0.1.86 - `bootstrap_subagent` Discriminator + Codex MCP Approval Fix (Completed)

**Released:** May 13, 2026 | PRs: [#1090](https://github.com/massgen/MassGen/pull/1090)

### Features
- **`bootstrap_subagent` Variant (fully functional)**: The dedicated critic-driven criteria path now runs an in-process LLM discriminator between rounds. The critic reads the task and each agent's latest answer, emits `proposed_criteria` as JSON, and merges them into the accumulator for the next round's checklist
- **Answer-Snapshot Gate**: The discriminator runs once per unique answer snapshot, avoiding repeated critiques when the answer set has not changed
- **Session-End Drain**: Late stdio JSONL criteria emissions are drained before final presentation so they are not stranded after the final checklist resolution pass
- **Codex MCP Approval Fix**: Codex workspaces now write both non-interactive approval bypasses needed for external MCP tool calls under `codex exec`
- **Tests**: Bootstrap criteria coverage expanded to 35 tests; Codex workspace approval policy coverage added across approval modes

### Notes
- Image/Video Edit Capabilities ([#959](https://github.com/massgen/MassGen/issues/959)) remain deferred to v0.1.87.

---

## ✅ v0.1.85 - Discriminative Criteria Emergence (`criteria_mode`) (Completed)

**Released:** May 11, 2026

### Features
- **`bootstrap_inline` Variant (fully functional)**: Agents emit `proposed_criteria` alongside `submit_checklist`; proposals are deduped, FIFO-capped, persisted to `bootstrap_criteria_accumulator.json`, and merged into the next round's checklist via `EvaluationSection`. Works on all backends with checklist tool support — SDK (Claude Code) via in-process schema, stdio backends via a JSONL emission channel
- **`bootstrap_subagent` Variant (wired, LLM step deferred)**: Same accumulator pipeline; in-process LLM discriminator pass queued for v0.1.86
- **New Module**: `massgen/bootstrap_criteria.py` with `merge_proposals`, `augment_with_accumulator`, `is_bootstrap_mode`, `validate_criteria_mode`
- **Config Fields**: `CoordinationConfig.{criteria_mode, bootstrap_max_per_agent_per_round, bootstrap_max_total}`
- **Anti-Goodhart by construction**: Criteria come from observed gaps, not priors
- **Example Configs**: `massgen/configs/coordination/{bootstrap_inline_criteria,bootstrap_subagent_criteria}.yaml`
- **Tests**: 30 new tests in `massgen/tests/test_bootstrap_criteria.py` (476 lines) covering merge/dedup/cap, config validation, augmentation, rendering gating, and round-N → round-N+1 propagation

### Notes
- Originally-planned Image/Video Edit Capabilities ([#959](https://github.com/massgen/MassGen/issues/959)) deferred to v0.1.86.

---

## ✅ v0.1.84 - TUI Consensus Map (Completed)

**Released:** May 8, 2026 | PRs: [#1085](https://github.com/massgen/MassGen/pull/1085)

### Features
- **TUI Consensus Map**: Compact visual map below the agent status ribbon during multi-agent runs that summarizes coordination state without replacing the timeline
- **Visibility Logic**: Hidden on welcome screen and single-agent runs; only shown when more than one active agent is coordinating
- **Event-Driven State**: Map state updates from existing coordination events (`answer_submitted`, `vote`, `agent_stopped`, `winner_selected`, `final_presentation_start`, `agent_restart`, `phase_change`, `context_received`) without backend schema changes
- **Direct-Callback Fallback**: Map remains accurate even when direct TUI callbacks update agent status or votes outside the unified event pipeline
- **OpenSpec Coverage**: Full change proposal, scenarios, and tasks under `openspec/changes/add-tui-consensus-map/`

### Notes
- Originally-planned Image/Video Edit Capabilities ([#959](https://github.com/massgen/MassGen/issues/959)) deferred to v0.1.85.

---

## ✅ v0.1.83 - In-Session Standalone Checkpoint MCP Integration (Completed)

**Released:** May 1, 2026 | PRs: [#1079](https://github.com/massgen/MassGen/pull/1079)

### Features
- **In-Session Standalone Checkpoint**: Standalone checkpoint MCP server (originally for external hosts like Claude Code) can now run *inside* a normal MassGen single-agent session, exposing the richer `init` + `checkpoint` tools backed by its own reviewer team
- **`coordination.standalone_checkpoint` Config Block**: New YAML block with `enabled`, `team_config`, `mode` (`generate` | `verify`), `single_checkpoint`, `include_workspace_context`; invalid `mode` falls back to `generate` with a warning
- **Single-Agent-Only Affordance Gating**: Multi-agent parents skip the standalone server with a warning — the standalone server runs its own reviewer panel
- **Enhanced Checkpoint Tool Card**: TUI tool card visualization distinguishes primary checkpoint operations from system tasks
- **Example Configs**: `massgen/configs/checkpoint/standalone_mcp/{fast_iteration,reviewers}.yaml`

### Notes
- Originally-planned Checkpoint Safety Mode ([#1026](https://github.com/massgen/MassGen/issues/1026)) and Round Evaluator over-indexing fix ([#994](https://github.com/massgen/MassGen/issues/994)) deferred to a future release.

---

## ✅ v0.1.82 - TUI Copy Mode & Checkpoint Quality Improvements (Completed)

**Released:** April 29, 2026 | PRs: [#1076](https://github.com/massgen/MassGen/pull/1076)

### Features
- **TUI Copy Mode**: New `Ctrl+Shift+S` toggle releases terminal mouse tracking so users can drag-select text natively; auto-restores on exit
- **Checkpoint Workspace Context**: New `include_workspace_context` config option for standalone checkpoint MCP server (default off)
- **Checkpoint Plan Quality Criteria**: Mode-aware quality criteria with selective branch depth scoring for single vs. multi-checkpoint modes
- **Single-Checkpoint Agent Recovery**: Detailed recovery workflow for agents when a plan branch resolves to `terminate`
- **TUI Visual Polish**: Ribbon dividers changed from `│` to `·`

### Notes
- Cloud Modal MVP deferred from v0.1.82 to v0.1.83.

---

## ✅ v0.1.81 - Multi-Region Circuit Breaker Failover (Phase 6) (Completed)

**Released:** April 27, 2026 | PRs: [#1072](https://github.com/massgen/MassGen/pull/1072)

### Features
- **Multi-Region Failover**: LLM circuit breaker fails over to backup regions when the primary trips OPEN, with automatic recovery when the primary returns to healthy
- **Production-Grade Resilience**: Builds on Phase 4 (distributed store) and Phase 5 (adaptive thresholds) for full multi-region resilience

### Notes
- Cloud Modal MVP originally planned for v0.1.81 — deferred again to v0.1.82.

---

## ✅ v0.1.80 - Adaptive Circuit Breaker & Checkpoint Modes (Completed)

**Released:** April 22, 2026 | PRs: [#1065](https://github.com/massgen/MassGen/pull/1065), [#1070](https://github.com/massgen/MassGen/pull/1070)

### Features
- **Circuit Breaker Adaptive Thresholds (Phase 5)**: Self-tuning thresholds that respond to each backend's actual failure patterns
- **Single Checkpoint Mode**: New standalone checkpoint mode — no recheckpointing within a single operation
- **Draft Plan Verify Mode**: New standalone checkpoint mode — verify a draft plan before executing

### Notes
- Cloud Modal MVP originally planned for v0.1.80 — deferred again to v0.1.81.

---

## ✅ v0.1.79 - Fast Mode Speed Control & Broader Checkpoint Framing (Completed)

**Released:** April 20, 2026

### Features
- **Better Fast Mode Options**: New options to control coordination speed — fine-grained speed vs. quality tradeoff
- **Broader Checkpoint Framing**: Checkpoint mode framing broadened from safety-only to high-stakes and coordinated phases
- **Checkpoint Instructions Clarity**: More clarity in trust settings for checkpoint agents

### Notes
- Cloud Modal MVP originally planned for v0.1.79 — deferred again to v0.1.80.

---

## ✅ v0.1.78 - Circuit Breaker Distributed Store (Phase 4) (Completed)

**Released:** April 17, 2026 | PRs: [#1061](https://github.com/massgen/MassGen/pull/1061)

### Features
- **Pluggable CB state store**: The LLM circuit breaker's state is now held behind a `CircuitBreakerStore` Protocol and can be shared across workers and processes. Default (`store=None`) preserves single-process behavior.
- **In-memory CB state store**: Thread-safe, zero-dependency implementation for single-process deployments and tests.
- **Redis-backed CB state store**: Distributed implementation via optional `redis>=4.0`; install with `pip install massgen[redis-store]`.
- **Atomic CB transitions**: `atomic_record_failure` / `atomic_record_success` make CB state transitions linearizable when workers race on the same upstream backend.

### Notes
- Cloud Modal MVP originally planned for v0.1.78 — deferred to v0.1.79.

---

## ✅ v0.1.77 - Answer Now Button (Completed)

**Released:** April 15, 2026 | PRs: [#1062](https://github.com/massgen/MassGen/pull/1062)

### Features
- **Answer Now Button**: Agents can submit answers more quickly, both within a round, and bypassing additional refinement rounds when quality is already sufficient

---

## ✅ v0.1.76 - Exa Search & Circuit Breaker Observability (Completed)

**Released:** April 13, 2026 | PRs: [#1056](https://github.com/massgen/MassGen/pull/1056), [#1057](https://github.com/massgen/MassGen/pull/1057), [#1058](https://github.com/massgen/MassGen/pull/1058)

### Features
- **Exa AI Search Tool**: New Exa AI-powered search tool for MCP with example config
- **Circuit Breaker Observability (Phase 3)**: Probe ownership, lock release, per-attempt latency tracking across all backends
- **Checkpoint Agent Instructions**: Copyable custom instructions for agent memory files with checkpoint MCP information
- **Docker Dependency Fixes**: Fixed Dockerfile installs for reliable container builds

---

## ✅ v0.1.75 - Codex Hooks & Checkpoint WebUI (Completed)

**Released:** April 10, 2026 | PRs: [#1053](https://github.com/massgen/MassGen/pull/1053)

### Features
- **Codex Native Hooks**: Hybrid hook system for Codex backend combining native hooks and MCP capabilities
- **Checkpoint WebUI Auto-Launch**: Checkpoint workflows auto-launch WebUI with configurable host/port for visual monitoring
- **Standalone MCP Server Docs**: Guide for `massgen-checkpoint-mcp` with safety policy integration
- **Safety Policy Update**: Updated safety policy for checkpoint based on Claude Code safe mode

---

## 📋 v0.1.96 - Image/Video Edit Capabilities (Deferred from v0.1.86-v0.1.95)

### Features

**Image/Video Edit Capabilities** (@ncrispino)
- Issue: [#959](https://github.com/massgen/MassGen/issues/959)
- Investigate and support image and video editing capabilities across providers
- Multi-turn editing workflows with continuation IDs
- **Use Case**: Enable iterative media editing within multi-agent workflows

### Success Criteria
- [ ] Image editing capabilities documented and tested
- [ ] Video editing capabilities documented and tested
- [ ] Multi-turn editing flow works end-to-end
- [ ] Provider capability notes are updated where users discover multimodal examples

---

## 🔨 Ongoing Work & Continuous Releases

These features are being actively developed on **separate parallel tracks** and will ship incrementally on the MWF release schedule:

### Track: Agent Adapter System (@Eric-Shang, ericshang.)
- PR: [#283](https://github.com/massgen/MassGen/pull/283)
- Unified agent interface for easier backend integration
- **Shipping:** Continuous improvements

### Track: Irreversible Actions Safety (@franklinnwren, zhichengren)
- Human-in-the-loop approval system for dangerous operations
- LLM-based tool risk detection
- **Target:** v0.1.3 and beyond

### Track: Multimodal Support (@qidanrui, danrui2020)
- PR: [#252](https://github.com/massgen/MassGen/pull/252)
- Image, audio, video processing across backends
- **Shipping:** Incremental improvements each release

### Track: Memory Module (@qidanrui, @ncrispino, danrui2020, nickcrispino)
- Issues: [#347](https://github.com/massgen/MassGen/issues/347), [#348](https://github.com/massgen/MassGen/issues/348)
- Short and long-term memory implementation with persistence
- **Status:** ✅ Completed in v0.1.5

### Track: Agent Task Planning (@ncrispino, nickcrispino)
- Agent task planning with dependency tracking
- **Status:** ✅ Completed in v0.1.7

### Track: Automation & Meta-Coordination (@ncrispino, nickcrispino)
- LLM agent automation with status tracking and silent execution
- MassGen running MassGen for self-improvement workflows
- **Status:** ✅ Completed in v0.1.8
- **Case Study:** Meta-level self-analysis demonstrating automation mode (`meta-self-analysis-automation-mode.md`)

### Track: DSPy Integration (@praneeth999, ram2561)
- Question paraphrasing for multi-agent diversity
- Semantic validation and caching system
- **Status:** ✅ Completed in v0.1.8

### Track: Framework Streaming (@Eric-Shang, ericshang.)
- PR: [#462](https://github.com/massgen/MassGen/pull/462)
- Real-time streaming for LangGraph and SmoLAgent intermediate steps
- Enhanced debugging and monitoring for external framework tools
- **Status:** ✅ Completed in v0.1.10

### Track: Rate Limiting System (@AbhimanyuAryan, abhimanyuaryan)
- PR: [#383](https://github.com/massgen/MassGen/pull/383)
- Multi-dimensional rate limiting for Gemini models
- Model-specific limits with sliding window tracking
- **Status:** ✅ Completed in v0.1.11

### Track: MassGen Handbook (@a5507203, @Henry-811, crinvo, henry_weiqi)
- Issue: [#387](https://github.com/massgen/MassGen/issues/387)
- Comprehensive user documentation and handbook at https://massgen.github.io/Handbook/
- Centralized policies and resources for development and research teams
- **Status:** ✅ Completed in v0.1.10

### Track: Computer Use (@franklinnwren, zhichengren)
- PR: [#402](https://github.com/massgen/MassGen/pull/402)
- Browser and desktop automation with OpenAI, Claude, and Gemini integration
- Visual perception through screenshot processing and action execution
- **Status:** ✅ Completed in v0.1.9

### Track: Session Management (@ncrispino, nickcrispino)
- PR: [#466](https://github.com/massgen/MassGen/pull/466)
- Complete session state tracking and restoration
- Resume previous MassGen conversations with full context
- **Status:** ✅ Completed in v0.1.9

### Track: Semtools & Serena Skills (@ncrispino, nickcrispino)
- PR: [#515](https://github.com/massgen/MassGen/pull/515)
- Semantic search capabilities via semtools (embedding-based similarity)
- Symbol-level code understanding via serena (LSP integration)
- Package as reusable skills within MassGen framework
- **Status:** ✅ Completed in v0.1.12

### Track: System Prompt Architecture (@ncrispino, nickcrispino)
- PR: [#515](https://github.com/massgen/MassGen/pull/515)
- Complete refactoring of system prompt assembly
- Hierarchical structure with improved LLM attention management
- Skills system local execution support
- **Status:** ✅ Completed in v0.1.12

### Track: Multi-Agent Computer Use (@franklinnwren, zhichengren)
- PR: [#513](https://github.com/massgen/MassGen/pull/513)
- Enhanced Gemini computer use with Docker integration
- Multi-agent coordination for computer automation
- VNC visualization and debugging support
- **Status:** ✅ Completed in v0.1.12

### Track: Code-Based Tools System / Automatic MCP Tool Selection (@ncrispino, nickcrispino)
- Issue: [#414](https://github.com/massgen/MassGen/issues/414)
- Tool integration via importable Python code instead of schema-based tools
- MCP server registry with auto-discovery
- Reduces token usage through on-demand tool loading
- **Status:** ✅ Completed in v0.1.13

### Track: NLIP Integration (@praneeth999, @qidanrui, ram2561, danrui2020)
- PR: [#475](https://github.com/massgen/MassGen/pull/475)
- Natural Language Integration Platform for advanced tool routing
- Multi-backend support across Claude, Gemini, and OpenAI
- Per-agent and orchestrator-level configuration
- **Status:** ✅ Completed in v0.1.13

### Track: Parallel Tool Execution (@praneeth999, ram2561)
- PR: [#520](https://github.com/massgen/MassGen/pull/520)
- Configurable concurrent tool execution across all backends
- Model-level and local execution controls
- Asyncio-based scheduling with semaphore limits
- **Status:** ✅ Completed in v0.1.14

### Track: Gemini 3 Pro Support (@ncrispino, nickcrispino)
- PR: [#530](https://github.com/massgen/MassGen/pull/530)
- Full integration for Google's Gemini 3 Pro model
- Function calling support with parallel tool capabilities
- **Status:** ✅ Completed in v0.1.14

### Track: Parallel File Operations (@ncrispino, nickcrispino)
- Issue: [#441](https://github.com/massgen/MassGen/issues/441)
- Increase parallelism of file read operations
- Standard efficiency evaluation and benchmarking methodology
- **Status:** ✅ Completed in v0.1.14

### Track: Persona Generation System (@ncrispino, nickcrispino)
- PR: [#547](https://github.com/massgen/MassGen/pull/547)
- Automatic generation of diverse system messages for multi-agent configurations
- Multiple generation strategies: complementary, diverse, specialized, adversarial
- **Status:** ✅ Completed in v0.1.15

### Track: Docker Distribution Enhancement (@ncrispino, nickcrispino)
- PR: [#545](https://github.com/massgen/MassGen/pull/545), [#538](https://github.com/massgen/MassGen/pull/538)
- GitHub Container Registry integration with ARM support
- MassGen pre-installed in Docker images for immediate use
- **Status:** ✅ Completed in v0.1.15

### Track: Launch Custom Tools in Docker (@ncrispino, nickcrispino)
- Issue: [#510](https://github.com/massgen/MassGen/issues/510)
- Enable custom tools to run in isolated Docker containers
- Security isolation and portability for custom tool execution
- **Status:** ✅ Completed in v0.1.15

### Track: MassGen Terminal Evaluation (@ncrispino, nickcrispino)
- Issue: [#476](https://github.com/massgen/MassGen/issues/476)
- PR: [#553](https://github.com/massgen/MassGen/pull/553)
- Self-evaluation and improvement of frontend/UI through terminal recording
- Automated video generation and case study creation using VHS
- **Status:** ✅ Completed in v0.1.16

### Track: LiteLLM Cost Tracking Integration (@ncrispino, nickcrispino)
- Issue: [#543](https://github.com/massgen/MassGen/issues/543)
- PR: [#553](https://github.com/massgen/MassGen/pull/553)
- Accurate cost calculation using LiteLLM's pricing database
- Integration with LiteLLM pricing for 500+ models with auto-updates
- **Status:** ✅ Completed in v0.1.16

### Track: Memory Archiving System (@ncrispino, nickcrispino)
- PR: [#555](https://github.com/massgen/MassGen/pull/555)
- Persistent memory with multi-turn session support
- Memory archiving for session persistence and continuity
- **Status:** ✅ Completed in v0.1.16

### Track: MassGen Self-Evolution Skills (@ncrispino, nickcrispino)
- Issue: [#476](https://github.com/massgen/MassGen/issues/476)
- Four new skills for MassGen to develop and maintain itself
- Self-documenting release workflows and configuration generation
- **Status:** ✅ Completed in v0.1.16

### Track: Improve Consistency of Memory & Tool Reminders (@ncrispino, nickcrispino)
- Issue: [#537](https://github.com/massgen/MassGen/issues/537)
- Enhance consistency of memory retrieval across agents
- Improve tool reminder system for better agent awareness
- Standardize memory access patterns
- **Status:** ✅ Completed in v0.1.16

### Track: Textual Terminal Display (@praneeth999, ram2561)
- Issue: [#539](https://github.com/massgen/MassGen/issues/539)
- PR: [#482](https://github.com/massgen/MassGen/pull/482)
- Rich terminal UI using Textual framework with dark/light themes
- Enhanced visualization for multi-agent coordination
- **Status:** ✅ Completed in v0.1.17

### Track: Broadcasting to Humans/Agents (@ncrispino, nickcrispino)
- Issue: [#437](https://github.com/massgen/MassGen/issues/437)
- PR: [#569](https://github.com/massgen/MassGen/pull/569)
- Enable agents to broadcast questions when facing implementation uncertainties
- Human-in-the-loop and agent-to-agent communication for clarification
- **Status:** ✅ Completed in v0.1.18

### Track: Claude Advanced Tooling (@praneeth999, ram2561)
- PR: [#568](https://github.com/massgen/MassGen/pull/568)
- Programmatic tool calling from code execution sandbox
- Server-side tool search with deferred loading
- **Status:** ✅ Completed in v0.1.18

### Track: LiteLLM Integration & Programmatic API (@ncrispino, nickcrispino)
- PR: [#580](https://github.com/massgen/MassGen/pull/580)
- MassGen as a LiteLLM custom provider with `MassGenLLM` class
- New `run()` and `build_config()` functions for programmatic execution
- `NoneDisplay` for silent output in programmatic/LiteLLM use
- **Status:** ✅ Completed in v0.1.19

### Track: Claude Strict Tool Use & Structured Outputs (@praneeth999, ram2561)
- PR: [#572](https://github.com/massgen/MassGen/pull/572)
- `enable_strict_tool_use` config flag with recursive schema patching
- `output_schema` parameter for structured JSON outputs
- **Status:** ✅ Completed in v0.1.19

### Track: Gemini Exponential Backoff (@praneeth999, ram2561)
- PR: [#576](https://github.com/massgen/MassGen/pull/576)
- Automatic retry mechanism for rate limit errors (429, 503)
- Jittered exponential backoff with `Retry-After` header support
- **Status:** ✅ Completed in v0.1.19

### Track: CUA Dockerfile / Auto Docker Setup (@franklinnwren, zhichengren)
- Issue: [#552](https://github.com/massgen/MassGen/issues/552)
- Automatic Docker container setup for Computer Use Agent
- Auto-detection of CUA configs with automatic container creation
- **Status:** ✅ Completed in v0.1.20

### Track: Web UI (@voidcenter, justin_zhang)
- PR: [#588](https://github.com/massgen/MassGen/pull/588)
- Browser-based real-time visualization for multi-agent coordination
- FastAPI server with WebSocket streaming and React frontend
- **Status:** ✅ Completed in v0.1.20

### Track: Response API Formatter Enhancement (@praneeth999, ram2561)
- Improved function call handling for multi-turn contexts
- Preserves function_call entries and generates stub outputs
- **Status:** ✅ Completed in v0.1.20

### Track: Computer Use Documentation (@franklinnwren, zhichengren)
- Issue: [#562](https://github.com/massgen/MassGen/issues/562)
- Comprehensive documentation for computer use workflows
- Environment naming conventions and automatic setup instructions
- **Status:** ✅ Completed in v0.1.20

### Track: Graceful Cancellation (@ncrispino, nickcrispino)
- PR: [#596](https://github.com/massgen/MassGen/pull/596)
- Ctrl+C saves partial progress during multi-agent coordination
- Session restoration for incomplete turns with `--continue`
- Multi-turn mode returns to prompt instead of exiting
- **Status:** ✅ Completed in v0.1.21

### Track: Shadow Agent Architecture (@ncrispino, nickcrispino)
- PR: [#600](https://github.com/massgen/MassGen/pull/600)
- Shadow agents for non-blocking broadcast responses
- Full context inheritance (conversation history + current turn)
- Parallel spawning with asyncio.gather()
- **Status:** ✅ Completed in v0.1.22

### Track: Web UI Automation Mode (@voidcenter, @ncrispino, justin_zhang, nickcrispino)
- PR: [#607](https://github.com/massgen/MassGen/pull/607)
- Automation-friendly Web UI view with status header and session polling
- LOG_DIR and STATUS path output for programmatic monitoring
- Session persistence API for completed sessions
- **Status:** ✅ Completed in v0.1.23

### Track: Multi-Turn Cancellation Improvements (@ncrispino, nickcrispino)
- PR: [#608](https://github.com/massgen/MassGen/pull/608)
- Flag-based cancellation handling in multi-turn mode
- Terminal state restoration after Rich display cancellation
- Cancelled turns build proper history entries with partial results
- **Status:** ✅ Completed in v0.1.23

### Track: Docker Container Persistence (@ncrispino, nickcrispino)
- Commit: 34279c88
- SessionMountManager for pre-mounting session directories to Docker containers
- Eliminates container recreation between turns (sub-second vs 2-5 second transitions)
- **Status:** ✅ Completed in v0.1.23

### Track: Turn History Inspection (@ncrispino, nickcrispino)
- Commits: 028f591d, 477423a6
- New `/inspect` command for reviewing agent outputs from any turn
- `/inspect all` to list all turns with summaries
- Interactive menu for viewing agent outputs, final answers, and coordination logs
- **Status:** ✅ Completed in v0.1.23

### Track: Async Execution Consistency (@ncrispino, nickcrispino)
- PR: [#608](https://github.com/massgen/MassGen/pull/608)
- New `run_async_safely()` helper for nested event loop handling
- Fixed mem0 adapter async lifecycle issues
- **Status:** ✅ Completed in v0.1.23

### Track: Enhanced Cost Tracking (@ncrispino, nickcrispino)
- Expanded token counting and cost calculation across multiple providers
- Real-time token usage for OpenRouter, xAI/Grok, Gemini, Claude Code backends
- Per-agent token breakdown with cost inspection command
- **Status:** ✅ Completed in v0.1.24

### Track: UI-TARS Backend Support (@franklinnwren, zhichengren)
- PR: [#584](https://github.com/massgen/MassGen/pull/584)
- New backend for ByteDance's UI-TARS-1.5-7B model for GUI automation
- OpenAI-compatible API via HuggingFace Inference Endpoints
- Tool implementation with Docker and browser automation examples
- **Status:** ✅ Completed in v0.1.25

### Track: Evolving Skill Creator System (@ncrispino, nickcrispino)
- PR: [#629](https://github.com/massgen/MassGen/pull/629)
- Framework for creating and iterating on reusable workflow plans
- Skills capture steps, Python scripts, and learnings through iteration
- Support for loading skills from previous sessions
- **Status:** ✅ Completed in v0.1.25

### Track: Textual Terminal Display Enhancement (@praneeth999, ram2561)
- PR: [#589](https://github.com/massgen/MassGen/pull/589)
- Adaptive layout management for different terminal sizes
- Enhanced dark/light themes with modals and panels
- Improved agent coordination visualization
- **Status:** ✅ Completed in v0.1.25

### Track: Shadow Agent Response Depth (@ncrispino, nickcrispino)
- PR: [#634](https://github.com/massgen/MassGen/pull/634)
- Test-time compute scaling via `response_depth` parameter (low/medium/high)
- Controls solution complexity in shadow agent broadcast responses
- **Status:** ✅ Completed in v0.1.26

### Track: Docker Diagnostics Module (@ncrispino, nickcrispino)
- PR: [#634](https://github.com/massgen/MassGen/pull/634)
- Comprehensive Docker error detection with platform-specific resolution
- Distinguishes binary not installed, daemon not running, permission denied, images missing
- **Status:** ✅ Completed in v0.1.26

### Track: Web UI Setup System (@ncrispino, nickcrispino)
- PR: [#634](https://github.com/massgen/MassGen/pull/634)
- Guided first-run setup with SetupPage, ConfigEditorModal, CoordinationStep
- API key management endpoints and environment checks
- **Status:** ✅ Completed in v0.1.26

### Track: Multimodal Backend Integration (@ncrispino, @qidanrui, nickcrispino, danrui2020)
- Commits: 598a32f8, dc920078
- Native multimodal understanding for Gemini and OpenAI backends
- Image, audio, video understanding via `read_media` with backend-native APIs
- **Status:** ✅ Completed in v0.1.28

### Track: Multimodal Generation Consolidation (@ncrispino, nickcrispino)
- Commit: dc920078
- Unified `generate_media` tool with provider selection
- New `generation/` module for OpenAI (DALL-E, Sora, TTS), Google (Imagen, Veo), OpenRouter
- **Status:** ✅ Completed in v0.1.28

### Track: Web UI Artifact Previewer (@ncrispino, @voidcenter, nickcrispino, justin_zhang)
- Commit: 598a32f8
- Preview workspace artifacts directly in web interface
- Support for PDF, DOCX, PPTX, XLSX, images, HTML, SVG, Markdown, Mermaid
- **Status:** ✅ Completed in v0.1.28

### Track: Minimum Answers Before Voting (@ncrispino, nickcrispino)
- Commit: bc7881d2
- New `min_answers_before_voting` orchestrator configuration option
- Integrated into CLI quickstart wizard and Web UI CoordinationStep
- **Status:** ✅ Completed in v0.1.28

### Track: Azure OpenAI Workflow Fixes (@AbhimanyuAryan, abhimanyuaryan)
- Commit: c71094ac
- Parameter filtering for unsupported Azure parameters
- Fixed tool_choice handling, message validation, and response format extraction
- **Status:** ✅ Completed in v0.1.28

### Track: OpenRouter Tool-Capable Model Filtering (@shubham2345)
- Commit: 40acf82c
- Model list filters to only show models supporting tool calling
- Checks `supported_parameters` for "tools" capability
- **Status:** ✅ Completed in v0.1.28

### Track: Subagent System (@ncrispino, nickcrispino)
- PR: [#690](https://github.com/massgen/MassGen/pull/690)
- Spawn parallel child MassGen processes for independent task execution
- Process isolation with independent workspaces per subagent
- New `spawn_subagents` tool with result aggregation and token tracking
- **Status:** ✅ Completed in v0.1.29

### Track: Async Subagent Execution (@ncrispino, @HenryQi, nickcrispino, henry_weiqi)
- PR: [#801](https://github.com/massgen/MassGen/pull/801)
- Linear: MAS-214
- Background subagent execution with `async_=True` parameter
- Poll for subagent completion and retrieve results
- **Status:** ✅ Completed in v0.1.41

### Track: TUI Visual Redesign (@ncrispino, @praneeth999, nickcrispino, ram2561)
- PR: [#806](https://github.com/massgen/MassGen/pull/806)
- Comprehensive visual overhaul with modern "Conversational AI" aesthetic
- Rounded corners, desaturated colors, edge-to-edge layouts, polished modals
- Human Input Queue for injecting messages to agents mid-stream
- **Status:** ✅ Completed in v0.1.42

### Track: AG2 Single-Agent Coordination Fix (@db-ol)
- PR: [#804](https://github.com/massgen/MassGen/pull/804)
- Fixed coordination issues for single-agent AG2 setups
- Single agent can now vote for itself after producing its first answer
- **Status:** ✅ Completed in v0.1.42

### Track: Tool Call Batching (@ncrispino, nickcrispino)
- PR: [#815](https://github.com/massgen/MassGen/pull/815)
- Consecutive MCP tool calls grouped into collapsible tree views
- Shows 3 items by default with "+N more" indicator, click to expand
- Respects Timeline Chronology Rule: tools only batch when consecutive
- New `ToolBatchCard` widget and `ToolBatchTracker` state machine
- **Status:** ✅ Completed in v0.1.43

### Track: Interactive Case Studies & Documentation (@franklinnwren, zhichengren)
- PR: [#812](https://github.com/massgen/MassGen/pull/812)
- New documentation page with visual SVG comparisons (MassGen vs single-agent)
- Video tutorials section with Getting Started and Development videos
- Iterative refinement examples showing multi-round improvements
- **Status:** ✅ Completed in v0.1.43

### Track: TUI UX Polish (@ncrispino, nickcrispino)
- PR: [#815](https://github.com/massgen/MassGen/pull/815)
- Final presentation display fix (reasoning vs answer separation)
- Plan mode enhancements with PlanOptionsPopover
- Quoted path support for paths with spaces
- Various bug fixes (status bar, scrolling, mode buttons)
- **Status:** ✅ Completed in v0.1.43

### Track: Tool Metrics Distribution Statistics (@ncrispino, nickcrispino)
- Commit: 30aca047
- Enhanced `get_tool_metrics_summary()` with per-call averages
- Output distribution stats (min/max/median) for bottleneck analysis
- **Status:** ✅ Completed in v0.1.29

### Track: CLI Per-Agent System Messages (@ncrispino, nickcrispino)
- Commit: 78177372
- New mode for assigning different system messages per agent in quickstart
- Options: "Skip", "Same for all", "Different per agent"
- **Status:** ✅ Completed in v0.1.29

### Track: OpenAI Responses API Fixes (@ncrispino, nickcrispino)
- PR: [#685](https://github.com/massgen/MassGen/pull/685)
- Fixed duplicate item errors when using `previous_response_id`
- Preserved function call ID for proper reasoning item pairing
- **Status:** ✅ Completed in v0.1.29

### Track: OpenRouter Web Search Plugin (@shubham2345)
- PR: [#693](https://github.com/massgen/MassGen/pull/693)
- Native web search integration via OpenRouter's plugins array
- Maps `enable_web_search` to `{"id": "web"}` plugin format
- **Status:** ✅ Completed in v0.1.30

### Track: Persona Generator Diversity Modes (@ncrispino, nickcrispino)
- PR: [#699](https://github.com/massgen/MassGen/pull/699)
- Two diversity modes: `perspective` (values/priorities) and `implementation` (solution types)
- Phase-based adaptation with softened personas for convergence
- **Status:** ✅ Completed in v0.1.30

### Track: Azure OpenAI Multi-Endpoint Support (@AbhimanyuAryan, abhimanyuaryan)
- PR: [#698](https://github.com/massgen/MassGen/pull/698)
- Support both Azure-specific and OpenAI-compatible endpoints
- Environment variable expansion (`${VAR}`) in config files
- **Status:** ✅ Completed in v0.1.30

### Track: Test Suite Fixes (@maxim-saplin)
- PR: [#688](https://github.com/massgen/MassGen/pull/688)
- Comprehensive test fixes with xfail registry
- Fixed persistent memory retrieval and backend tool registration
- **Status:** ✅ Completed in v0.1.30

### Track: Logfire Observability Integration (@ncrispino, nickcrispino)
- PR: [#708](https://github.com/massgen/MassGen/pull/708)
- Comprehensive structured logging and tracing via Logfire (Pydantic team)
- Automatic LLM instrumentation for OpenAI, Anthropic Claude, and Google Gemini backends
- Tool execution tracing with timing metrics and agent coordination observability
- Enable via `--logfire` CLI flag or `MASSGEN_LOGFIRE_ENABLED=true` environment variable
- **Status:** ✅ Completed in v0.1.31

### Track: Azure OpenAI Native Tool Call Streaming (@AbhimanyuAryan, abhimanyuaryan)
- PR: [#705](https://github.com/massgen/MassGen/pull/705)
- Tool calls accumulated and yielded as structured `tool_calls` chunks
- Fixed streaming behavior for Azure OpenAI tool calling
- **Status:** ✅ Completed in v0.1.31

### Track: OpenRouter Web Search Logging (@shubham2345)
- PR: [#704](https://github.com/massgen/MassGen/pull/704)
- Fixed logging output for web search operations
- **Status:** ✅ Completed in v0.1.31

### Track: Session Export Multi-Turn Support (@ncrispino, nickcrispino)
- PR: [#715](https://github.com/massgen/MassGen/pull/715)
- Enhanced `massgen export` with turn range selection and workspace options
- Multi-turn file collection preserving turn/attempt structure
- **Status:** ✅ Completed in v0.1.32

### Track: Logfire Optional Dependency (@AbhimanyuAryan, abhimanyuaryan)
- PR: [#711](https://github.com/massgen/MassGen/pull/711)
- Moved Logfire from required to optional `[observability]` extra
- Helpful error message when `--logfire` used without Logfire installed
- **Status:** ✅ Completed in v0.1.32

### Track: Per-Attempt Logging (@ncrispino, nickcrispino)
- Commit: a808d730
- Separate log files per orchestration restart attempt
- Handler reconfiguration via `set_log_attempt()` function
- **Status:** ✅ Completed in v0.1.32

### Track: Office Document PDF Conversion (@ncrispino, nickcrispino)
- Commit: 7c7a32e3
- Automatic DOCX/PPTX/XLSX to PDF conversion for session sharing
- Docker + LibreOffice headless conversion with image fallback
- **Status:** ✅ Completed in v0.1.32

### Track: Reactive Context Compression (@ncrispino, nickcrispino)
- Issue: [#617](https://github.com/massgen/MassGen/issues/617)
- PR: [#697](https://github.com/massgen/MassGen/pull/697)
- Automatic context compression when context length errors are detected
- Streaming buffer system for compression recovery
- **Status:** ✅ Completed in v0.1.33

### Track: Backend Model List Auto-Update (@ncrispino, nickcrispino)
- Issue: [#645](https://github.com/massgen/MassGen/issues/645)
- PR: [#669](https://github.com/massgen/MassGen/pull/669)
- Native model listing APIs for providers (Groq, Together, and others)
- Research third-party wrappers; document manual update processes
- **Status:** ✅ Completed in v0.1.34

### Track: OpenAI-Compatible Chat Server (@maxim-saplin)
- Issue: [#628](https://github.com/massgen/MassGen/issues/628)
- PR: [#689](https://github.com/massgen/MassGen/pull/689)
- Run MassGen as an OpenAI-compatible API server
- **Status:** ✅ Completed in v0.1.34

### Track: Code-Based Tools in Web UI (@ncrispino, nickcrispino)
- Issue: [#612](https://github.com/massgen/MassGen/issues/612)
- Ensure code-based tools work properly in Web UI
- Integration with new Web UI features
- **Status:** ✅ Completed in v0.1.34

### Track: Test MassGen for PPTX Slides (@ncrispino, nickcrispino)
- Issue: [#686](https://github.com/massgen/MassGen/issues/686)
- Verify and improve PPTX generation capabilities
- Test slide generation workflows and output quality
- **Status:** ✅ Completed in v0.1.34

### Track: OpenRouter Tool-Use Model Filtering (@shubham2345)
- Issue: [#647](https://github.com/massgen/MassGen/issues/647)
- Restrict OpenRouter model list to only show models that support tool use
- Filter based on `supported_parameters` capability checks
- **Status:** ✅ Completed in v0.1.34

### Track: OpenAI Responses /compact Endpoint (@ncrispino, nickcrispino)
- Issue: [#739](https://github.com/massgen/MassGen/issues/739)
- Use OpenAI's native `/compact` endpoint instead of custom summarization
- Leverage API-level context compression for better efficiency
- **Status:** ✅ Completed in v0.1.48

### Track: Improve Logging (@ncrispino, nickcrispino)
- Issue: [#683](https://github.com/massgen/MassGen/issues/683)
- PR: [#761](https://github.com/massgen/MassGen/pull/761)
- Enhanced logging for better debugging and observability via Logfire workflow attributes
- New `massgen logs analyze` CLI command with self-analysis mode
- **Status:** ✅ Completed in v0.1.35

### Track: Add Model Selector for Log Analysis (@ncrispino, nickcrispino)
- Issue: [#766](https://github.com/massgen/MassGen/issues/766)
- Allow users to choose which model to use for `massgen logs analyze` self-analysis mode
- Configurable model selection for different analysis requirements
- **Status:** ✅ Completed in v0.1.50

### Track: General Hook Framework (@ncrispino, nickcrispino)
- Issue: [#745](https://github.com/massgen/MassGen/issues/745)
- PR: [#769](https://github.com/massgen/MassGen/pull/769)
- Extensible hook system for agent lifecycle events
- Enable custom actions at key orchestration points
- **Status:** ✅ Completed in v0.1.36

### Track: Plan and Execute Workflow (@ncrispino, nickcrispino)
- PR: [#794](https://github.com/massgen/MassGen/pull/794)
- Complete plan-then-execute workflow separating "what to build" from "how to build it"
- `--plan-and-execute` and `--execute-plan` CLI options
- Task verification workflow with `verified` status and verification groups
- Plan storage system in `.massgen/plans/` with frozen snapshots
- **Status:** ✅ Completed in v0.1.39

### Track: Improve Log Sharing and Analysis (@ncrispino, nickcrispino)
- Issue: [#722](https://github.com/massgen/MassGen/issues/722)
- Enhanced log sharing workflows
- Improved analysis tools and visualizations
- **Target:** v0.1.50+

### Track: Claude Code Plugin for MassGen Agents (@ncrispino, nickcrispino)
- Issue: [#773](https://github.com/massgen/MassGen/issues/773)
- Plugin/extension for spawning MassGen agents directly from Claude Code interface
- Seamless integration with Claude Code workflows
- **Target:** v0.1.50+

### Track: Refactor ask_others for Targeted Agent Queries (@ncrispino, nickcrispino)
- Issue: [#809](https://github.com/massgen/MassGen/issues/809)
- Support targeted queries to specific agents via subagent spawning
- Three modes: broadcast to all, selective broadcast, targeted ask
- Pass full `_streaming_buffer` to shadow agents for improved context
- **Target:** v0.1.52

### Track: Decomposition Coordination Mode (@ncrispino, nickcrispino)
- PR: [#858](https://github.com/massgen/MassGen/pull/858)
- New coordination mode that decomposes tasks into subtasks assigned to individual agents
- Task decomposer with presenter agent role for final synthesis
- TUI mode bar toggle, subtask assignment display, and generation modals
- **Status:** ✅ Completed in v0.1.48

### Track: Worktree Isolation (@ncrispino, nickcrispino)
- PR: [#857](https://github.com/massgen/MassGen/pull/857)
- Linear: MAS-272
- Git worktree-based isolation for agent file writes with review workflow
- Review modal for approving/rejecting changes before applying to original paths
- Shadow repo support for non-git directories
- **Status:** ✅ Completed in v0.1.48

### Track: Quickstart Wizard Docker Setup (@ncrispino, nickcrispino)
- PR: [#857](https://github.com/massgen/MassGen/pull/857)
- Linear: MAS-267
- Docker setup step in quickstart wizard with animated pull progress
- Real-time stdout streaming for image downloads
- **Status:** ✅ Completed in v0.1.48

### Track: Fairness Gate for Coordination (@ncrispino, nickcrispino)
- PR: [#869](https://github.com/massgen/MassGen/pull/869)
- Prevents fast agents from dominating coordination rounds
- Configurable `fairness_lead_cap_answers` and `max_midstream_injections_per_round`
- **Status:** ✅ Completed in v0.1.49

### Track: Persona Easing TUI Integration (@ncrispino, nickcrispino)
- PR: [#869](https://github.com/massgen/MassGen/pull/869)
- Persona easing toggle now accessible from TUI mode bar
- **Status:** ✅ Completed in v0.1.49

### Track: Checklist Voting Tool (@ncrispino, nickcrispino)
- PR: [#869](https://github.com/massgen/MassGen/pull/869)
- New `checklist_tools_server.py` MCP server for structured quality evaluation
- Binary pass/fail scoring for objective quality assessment
- **Status:** ✅ Completed in v0.1.49

### Track: Log Analysis Mode in TUI (@ncrispino, nickcrispino)
- PR: [#869](https://github.com/massgen/MassGen/pull/869)
- New "Analyzing" state in TUI mode bar for in-app run analysis
- Configurable analysis profiles with log directory and turn selection
- **Status:** ✅ Completed in v0.1.49

### Track: Automated Testing Infrastructure (@ncrispino, nickcrispino)
- PR: [#869](https://github.com/massgen/MassGen/pull/869)
- CI/CD workflow (`tests.yml`), SVG snapshot baselines, 16+ new test files
- Testing strategy specification and visual regression testing
- **Status:** ✅ Completed in v0.1.49

### Track: Shadow Agent Chunk Type Fix (@MuL1ian)
- PR: [#861](https://github.com/massgen/MassGen/pull/861)
- Fixed "[No response generated]" errors from incorrect chunk type comparison
- **Status:** ✅ Completed in v0.1.49

### Track: Chunked Plan Execution (@ncrispino, nickcrispino)
- PR: [#877](https://github.com/massgen/MassGen/pull/877)
- Plans divided into chunks executed one at a time with progress checkpoints
- Chunk browsing in TUI, frozen plan snapshots, `target_steps`/`target_chunks` parameters
- Iterative planning review modal with Continue/Edit/Finalize options
- **Status:** ✅ Completed in v0.1.50

### Track: Skill Lifecycle Management (@ncrispino, nickcrispino)
- PR: [#878](https://github.com/massgen/MassGen/pull/878)
- New lifecycle modes (`create_or_update`, `create_new`, `consolidate`)
- Skill organizer for merging overlapping skills, `SKILL_REGISTRY.md` routing guide
- Previous-session skill loading with `load_previous_session_skills` config
- Local Skills MCP for Docker/local execution contexts
- **Status:** ✅ Completed in v0.1.50

### Track: Worktree Improvements (@ncrispino, nickcrispino)
- PR: [#877](https://github.com/massgen/MassGen/pull/877)
- Branch accumulation across rounds, cross-agent diff visibility via `generate_branch_summaries()`
- Orphan worktree cleanup
- **Status:** ✅ Completed in v0.1.50

### Track: Responsive TUI Mode Bar (@ncrispino, nickcrispino)
- PR: [#877](https://github.com/massgen/MassGen/pull/877)
- Vertical/horizontal adaptive layout with compact labels on narrow terminals
- TUI homescreen and theming improvements
- **Status:** ✅ Completed in v0.1.50

### Track: Subagent Delegation Protocol (@ncrispino, nickcrispino)
- PR: [#955](https://github.com/massgen/MassGen/pull/955)
- File-based delegation protocol for container-to-host subagent spawning
- SubagentLaunchWatcher with atomic JSON request/response exchange
- Workspace path validation against allowlist for security
- **Status:** ✅ Completed in v0.1.57

### Track: Iterative Refinement Improvements (@ncrispino, nickcrispino)
- PR: [#955](https://github.com/massgen/MassGen/pull/955)
- Issue: [#874](https://github.com/massgen/MassGen/issues/874)
- Substantiveness tracking (transformative/structural/incremental) for convergence decisions
- Builder subagent type for large artifact generation with fresh context
- Diagnostic report gating and per-agent checklist scoring
- Claude Code reasoning parameters for updated SDK
- **Status:** ✅ Completed in v0.1.57

### Track: Multimodal Revamp (@ncrispino, nickcrispino)
- Issues: [#942](https://github.com/massgen/MassGen/issues/942), [#951](https://github.com/massgen/MassGen/issues/951)
- ElevenLabs TTS & STT integration for high-quality voice synthesis and transcription
- Nano Banana 2 as default image generation model
- Grok Imagine image/video generation ([#958](https://github.com/massgen/MassGen/issues/958)) via xAI API
- Media generation skills (image, video, audio) and multi-turn image editing with continuation IDs
- **Status:** ✅ Completed in v0.1.58

### Track: Nvidia NIM Backend (@ncrispino, nickcrispino)
- PR: [#962](https://github.com/massgen/MassGen/pull/962)
- First-class provider integration for NVIDIA Inference Microservices
- Support for NVIDIA-hosted models via NIM API
- **Status:** ✅ Completed in v0.1.58

### Track: Quality Rethinking Subagent (@ncrispino, nickcrispino)
- PR: [#964](https://github.com/massgen/MassGen/pull/964)
- New `quality_rethinking` subagent type for targeted per-element craft improvements
- Explicit improve/preserve listings in checklists with better label refresh ordering
- Subagent hardening: better '@' parsing, error handling for multiple submit_checklist calls
- **Status:** ✅ Completed in v0.1.58

### Track: Coding Agent Enhancements (@ncrispino, nickcrispino)
- PR: [#251](https://github.com/massgen/MassGen/pull/251)
- Enhanced file operations and workspace management
- **Shipping:** Continuous improvement

---

## 🎯 Long-Term Vision (v0.2.0+)

**Advanced Orchestration Patterns**
- Advanced task decomposition strategies and parallel coordination
- Assignment of agents to specific tasks and increasing of diversity
- Improvement in voting as tasks continue

**Self-Learning & Adaptation**
- Agents learn from past executions to improve future performance
- Automatic skill acquisition from successful task completions
- Feedback loops for continuous improvement
- Memory systems for retaining learned patterns across sessions

**Visual Workflow Designer**
- No-code multi-agent workflow creation
- Drag-and-drop agent configuration
- Real-time testing and debugging

**Enterprise Features**
- Role-based access control (RBAC)
- Audit logs and compliance reporting
- Multi-user collaboration
- Advanced analytics and cost tracking

**Additional Framework Integrations**
- LangChain agent support
- CrewAI compatibility
- Custom framework adapters

**Complete Multimodal Pipeline**
- End-to-end audio processing (speech-to-text, text-to-speech)
- Video understanding and generation
- Advanced document processing (PDF, Word, Excel)

---

## 🔗 GitHub Integration

Track development progress:
- [Active Issues](https://github.com/massgen/MassGen/issues)
- [Pull Requests](https://github.com/massgen/MassGen/pulls)
- [Project Boards](https://github.com/massgen/MassGen/projects) (TODO)

---

## 🤝 Contributing

Interested in contributing? You have two options:

**Option 1: Join an Existing Track**
1. See [Contributors & Contact](#-contributors--contact) table above for active tracks
2. Contact the track owner via Discord to discuss your ideas
3. Follow [CONTRIBUTING.md](CONTRIBUTING.md) for development process

**Option 2: Create Your Own Track**
1. Have a significant feature idea? Propose a new track!
2. Reach out via the #massgen channel on [Discord](https://discord.gg/VVrT2rQaz5)
3. Work with the MassGen dev team to integrate your track into the roadmap
4. Become a track owner and guide other contributors

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code standards, testing, and documentation requirements.

---

## 📚 Related Documentation

- [CHANGELOG.md](CHANGELOG.md) - Complete release history
- [CONTRIBUTING.md](CONTRIBUTING.md) - Contribution guidelines
- [Documentation](https://docs.massgen.ai/en/latest/) - Full user guide

---

*This roadmap is community-driven. Releases ship on **Mondays, Wednesdays, Fridays @ 9am PT**. Timelines may shift based on priorities and feedback. Open an issue to suggest changes!*

**Last Updated:** April 17, 2026
**Maintained By:** MassGen Team
