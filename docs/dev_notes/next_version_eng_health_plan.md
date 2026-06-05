# Next Version — Engineering Health Plan

**Theme: Parallelism Hardening** — strengthen the orchestrator's parallel execution: move blocking work off the event loop so agents keep streaming concurrently, close the latent concurrency races that the currently-serialized copy keeps hidden, and finish the one remaining refactor blocker. No per-backend functionality changes (parity principle).

**Date:** 2026-06-04

## Implementation status (2026-06-04)

Implemented under TDD (tests written first, confirmed red, then green) with cost-free
simulation (mock backends / real collaborator code, no LLM calls). Zero regressions —
the 37-test orchestrator characterization safety net plus the injection/decomposition/
novelty suites stay green; all pre-existing failures verified identical with changes
stashed.

| Item | Status | Tests |
|---|---|---|
| R1 lost peer-answer revision | ✅ done | `test_concurrency_race_fixes.py` (R1 ×4) |
| R2/R3 lost subagent result (blind pop) | ✅ done | same (R2 ×5) |
| R4 leaked trace tasks on cleanup | ✅ done | same (R4 ×2) |
| R5 cancel-without-await teardown | ✅ done | same (R5 ×1) |
| D2 surface worktree-isolation degradation | ✅ done + **emit bug fixed** | same (D2 ×3) + `test_d2_emits_status_with_valid_signature` |
| D3 changedoc enrichment non-fatal | ✅ done (scoped to changedoc) | same (D3 ×2) |
| B1 snapshot copy off the event loop | ✅ done + **race hardened** | `test_snapshot_copy_offload.py` (×5) |
| **B1-race shared-source fix** | ✅ **done** — a post-merge review caught that B1's `to_thread` offload removed the implicit event-loop serialization between the peer-context `copytree` (now on a worker thread) and `save_snapshot`'s in-place `rmtree`+rebuild of the **same** `<base>/<agent_id>` dir (the offload's "disjoint paths" safety claim only covered copy *destinations*, not the shared *source*). Fix: snapshots are now **immutable, versioned** — `save_snapshot` publishes `<base>/.versions/<agent_id>/v<N>` and atomically repoints the `<base>/<agent_id>` symlink; the peer-context reader `acquire`s (refcounts) the current version so a concurrent republish can't delete/mutate it mid-copy. See `SnapshotVersionStore`. | `test_snapshot_version_store.py` (×9, incl. concurrent-republish-during-read), `test_snapshot_versioned_save.py` (×3) |
| C2 eager debug f-strings | ✅ done (loguru brace-style; NOT `isEnabledFor` — logger is loguru) | `test_answer_normalizer_debug_guard.py` (×3) |
| E1 assertion-free context test | ✅ done (assertions verified vs real output) | `test_message_context_building.py` (×4) |
| E2 assertion-free grok test | ✅ done (offline unit + live_api skips) | `test_grok_backend.py` |
| A3 stale roadmap | ✅ done | `orchestrator_refactor_roadmap.md` |
| **A1 unify injection closures** | ✅ **done** — the two ~150-line `get_injection_content` closures collapsed to `MidStreamInjectionHookInstaller.build_midstream_injection(..., native=)`; both setup methods now delegate. orchestrator.py 8,561 → 8,422. Canonical side-effect order preserves the `update_context → refresh_checklist` invariant for both paths. | `test_midstream_injection_unified.py` (×9, incl. cross-path effect-order equality) + 201-test injection/restart/hooks regression sweep |
| **B2 incremental snapshot copy** | ⏳ **deferred** by design — large + real correctness risk (per-viewing anonymization + dest rewriting); only justify after B1's stall-vs-volume split is measured in a real run. |
| **C3 save_agent_snapshot offload** | ⛔ **assessed, not done (intentional)** — unlike B1 (disjoint temp dirs), this method mutates shared `AgentState` counters (answer_count / checklist_calls / pending_checklist_recheck_labels — load-bearing per its docstring). Offloading to a worker thread would risk a NEW race on that shared state — the opposite of the goal. Audit rated it Low (discrete events, not hot path). Leave on the loop. |
| **B5 per-round subagent rewrite guard** | ◐ **partial** — corrected the stale "workspace clears remove .massgen/" comment (false: clear_workspace is disabled + preserves .massgen). Did NOT add the skip-guard: `rewrite_subagent_mcp_config_files(agent_id)` may legitimately change per round; guarding without verifying idempotency could silently break subagent MCP wiring for a few-ms win. |
| **D3 (emitter/status/web-display guards)** | ⏳ remaining — deliberately scoped small; the changedoc path (the only unguarded throw-prone bookkeeping op) is done. Broaden only if a real failure is seen. |
| **B4 path-rewrite skip** | ⏳ fold into B2 when that lands. |

**Critical sequencing honored:** R1 + R2/R3 (the yield-exposed races) landed BEFORE B1,
so making the copy truly async did not expose a latent race. A B1 test asserts peer/
subagent delivery survives a genuinely-yielding copy window.

**New helpers added:** `PeerAnswerVisibilityTracker.mark_seen_answer_revisions(..., seen_counts=)`
+ `register_injected_answer_updates(..., seen_counts=)`; `Orchestrator._capture_answer_revision_counts`,
`_consume_pending_subagent_results`, `_record_round_isolation_degraded`,
`_attach_changedoc_to_latest_answer`; `SubagentLifecycleCoordinator.consume_pending_subagent_results`;
`FilesystemManager._copy_snapshots_to_temp_workspace_sync` (offloaded via `asyncio.to_thread`).
`AgentState.round_isolation_degraded` / `round_isolation_error` fields.

---

**Source:** two adversarially-verified audit workflows (`massgen-eng-health-audit`, `massgen-parallelism-correctness-sweep`). Every finding below was checked through ≥2 independent verifier lenses; impact ratings are the verifier-revised values, not the original finder claims.

> **Verify before acting.** These are point-in-time observations with file:line anchors that may drift. Re-read the cited code before implementing — the audits already caught several stale-roadmap and overstated-impact claims, so treat magnitudes skeptically and trust the *mechanism* over the prose.

---

## 0. Where the refactor actually stands (correcting the old roadmap)

The collaborator-extraction refactor is **substantially done and healthy** — more refactoring is **not** the right theme for the next version.

- `orchestrator.py`: **21,599 → 8,561 lines**, 50 collaborator modules in `massgen/orchestrator_collaborators/`.
- `AgentOrchestrationSetup` is **already fully extracted** (`agent_orchestration_setup.py:20-141`); only a thin delegator loop remains in `__init__` (`orchestrator.py:884-908`). The roadmap *table* (`orchestrator_refactor_roadmap.md:45,47`) is stale; the prose (`:56-90`) is correct.
- **Only one genuine refactor blocker remains** (A1 below): the duplicated mid-stream injection closures across 3 backend paths, which block completing `MidStreamInjectionHookInstaller`.
- **De-scoped as LOC-only (no correctness/hot-path payoff):**
  - `textual_terminal_display.py` (14k) — `TextualApp` already uses constructor injection, not closure-over-self; a split is pure LOC redistribution with real UI-regression risk. Defer.
  - `config_builder.py` (5.5k) — interactive wizard, near-zero mutable state, already tested + faceted via `run()`. Defer.
  - `system_prompt_sections.py` / `base_with_custom_tool_and_mcp.py` — cohesive, never on the roadmap. Only `ChecklistGate` (1,558 LOC inside `system_prompt_sections.py:237-1794`) is a real extraction candidate, and only if that file is touched anyway.

---

## 1. The critical interaction (read this first)

**Several concurrency races are currently masked because `copy_snapshots_to_temp_workspace` (`_filesystem_manager.py:2339`) is an `async def` doing purely blocking sync I/O — it never yields.** That accidental non-yielding critical section serializes work that would otherwise race.

The headline latency fix (B1) is to wrap that copy in `asyncio.to_thread` so it stops stalling every other agent's streaming. **But doing B1 introduces a real yield point**, which can expose the latent races that the blocking copy currently hides.

**Therefore: the race fixes (R1, R2/R3) are PREREQUISITES for B1, not independent of it.** Shipping B1 alone would trade a latency win for a correctness regression. Sequencing below respects this.

---

## 2. Correctness — concurrency races (Tranche 1, do first, all lock-free)

MassGen's concurrency is **mostly safe-by-construction**: the FIRST_COMPLETED consumer loop (`orchestrator.py:2511`) processes agent results one-at-a-time. Real races only intrude where (a) per-agent injection hooks hit genuinely-yielding awaits, or (b) detached background tasks append concurrently. **None crash or corrupt state — they silently drop peer/subagent feedback, degrading refinement quality.**

### R1 — Lost peer-answer revision (seen-count re-read live after await) — **Medium / Medium**
- **Where:** `orchestrator.py:3589` (select content) → `:3618` (await snapshot copy = real yield) → `:3662` (mark seen); live re-read at `orchestrator_collaborators/peer_answer_visibility_tracker.py:93`.
- **Shared state:** `agent_states[A].seen_answer_counts[B]` vs `coordination_tracker.answers_by_agent[B]` length.
- **Interleaving:** A's injection hook captures B's rev-2 content at 3589, suspends at the 3618 await; the consumer loop appends B's rev-3 (`:2646`); A resumes and sets `seen_answer_counts[B] = len(...) = 3` though it was only shown rev-2.
- **Consequence:** `_has_unseen_answer_updates(A)` returns False for B → rev-3 never injected, never triggers restart → A refines against stale peer work.
- **Fix:** Capture the source revision counts in the *same* read as content selection (before the 3618 await); thread the captured count through `register_injected_answer_updates` / `mark_seen_answer_revisions`, or set `seen_answer_counts[src] = min(captured, current)`. **Same pattern recurs at `orchestrator.py:4057/4078`, `4354/4392/4410`, `4776/4802/4821` — fix all sites.** Pure data-flow, no lock.

### R2 — Lost background result, blind whole-key pop (hook path) — **Medium / Small**
- **Where:** `orchestrator.py:4019` (read-snapshot) → `:4064` (await copy) → `:4116` (`pop(agent_id, None)`); writer `subagent_lifecycle_coordinator.py:54-56`, fired from detached task `trace_analyzer_runner.py:623`.
- **Shared state:** `orchestrator._pending_subagent_results[agent_id]`.
- **Interleaving:** Consumer snapshots the list, awaits; the detached trace-analyzer task appends during the window; consumer resumes and `pop()`s the *whole* key, deleting the fresh append.
- **Consequence:** Result silently dropped. **Trace-analyzer guidance is permanently lost** (only flows through this in-process queue; no MCP-poll fallback). Real MCP subagents self-heal on next poll.
- **Fix:** Remove only the consumed snapshot's ids, not the whole key:
  `self._pending_subagent_results[agent_id] = [e for e in ...get(agent_id, []) if e[0] not in consumed_ids]` (drop key if empty). **Do NOT add an asyncio.Lock in this hot path.**
- **Correction from audit:** the real production writer is `trace_analyzer_runner.py`; `register_completion_callback` is test-only wiring.

### R3 — Same blind-pop, hookless path — **Low / Small**
- **Where:** `orchestrator.py:4216` → `:4222` (await `subagent_hook.execute`) → `:4229` (`pop`). Same shape as R2 on the Codex/hookless fallback. Self-heals via MCP re-poll → delayed delivery, not silent loss.
- **Fix:** Same consumed-id filtering; apply at `:4116` and `:4229` together.

### R4 — Detached trace tasks not cancelled by timeout cleanup — **Low / Small**
- **Where:** `active_coordination_cleanup.py:39` (flush) + `:41-62` (cancels only `_active_tasks`, never `_background_trace_tasks`).
- **Consequence:** On orchestrator timeout, a trace task survives past the hard timeout (wastes compute), then appends post-flush into a dict no one reads. No corruption; violates the cleanup docstring contract.
- **Fix:** In `ActiveCoordinationCleanup.cleanup()`, cancel-and-await `_background_trace_tasks` (mirror the `_active_tasks` loop at `:49-62`), then clear. The task's `CancelledError` path (`trace_analyzer_runner.py:476-489`) returns without writing, so awaiting fully closes the window.

### R5 — `cancel_all_subagents` cancels without awaiting before clearing registry — **Low / Small (teardown hygiene)**
- **Where:** `subagent/manager.py:4190-4232`. Shutdown-only. Both damaging outcomes already guarded (cancelled-status preservation `:2887-2902`; idempotent late pop). Only residual: a late completion callback post-shutdown.
- **Fix:** `await asyncio.gather(*cancelled_tasks, return_exceptions=True)` before `clear()`/marking. Hygiene, not a user-facing bug.

### R6 — Background status-file writer torn read — **Low (benign) / Optional (WONTFIX)**
- **Where:** writer `coordination_tracker.py:660/752`; reader `save_status_file` offloaded via `run_in_executor` (`step_mode_handler.py:187`). Genuine cross-thread read, but **no exception possible** (keys fixed at init `:232`; CPython append-during-iteration doesn't raise). `status.json` is observational only.
- **Fix (optional):** build an immutable copy of needed fields on the event-loop thread before handing to the executor. Do **not** lock the hot append path.

### Safe-by-construction — do NOT "fix" these
- **`pending_checklist_recheck_labels` "dual-writer"** (`peer_answer_visibility_tracker.py:251` vs `checklist_gate_manager.py:872`): both writers run inside the *same single agent's* task → cannot interleave. The roadmap's dual-writer flag is a **false alarm**; keep only as a tripwire if injection ever moves to a task distinct from the agent's tool-execution task.
- **`restart_pending` overwrite:** currently safe *only because* the snapshot copy doesn't yield. **Re-evaluate after B1.** (R1 is independent of this — R1 is the live count re-read, not the bool.)
- **Midstream injection fairness cap:** one task per agent (`orchestrator.py:2503`, `:6817`); hooks run sequentially (`hooks.py:584`).
- **`rate_limiter.py`:** check-then-act with no await between check and assignment; real sections under `async with self._lock`. Correct.
- **`BroadcastChannel`:** all mutations + compound ops under one `async with self._lock` (`:321`); shadow path is sequential (`:233-250`). Correct.

---

## 3. Latency — event-loop offloading (Tranche 2, after race fixes)

### B1 — `to_thread`-wrap the snapshot copy — **Medium impact / Small effort** (the single best ROI)
- **Where:** `_filesystem_manager.py:2339-2397` (`copy_snapshots_to_temp_workspace`: `_safe_rmtree:2360`, `copytree:2379`, `scrub:2395`; TODO at `:2353`); wrapper `snapshot_manager.py:144-195`; call sites `orchestrator.py:3618,4064,4392,4802,6069`; parallel loop `:2511`.
- **Problem:** `async def` doing synchronous `rmtree`/`copytree`/scrub/path-walk with no `to_thread`. While one agent copies peers' snapshots, the single event-loop thread is blocked → no other agent's chunk is consumed → the intended FIRST_COMPLETED parallelism is serialized.
- **Fix:** Wrap the blocking body in `await asyncio.to_thread(...)`. Each agent owns a distinct temp workspace → concurrent offloaded copies write disjoint dirs, no race.
- **Gate:** Only after R1/R2/R3 land (this introduces the real yield that exposes them). Add a test asserting peer-revision delivery survives a yielding copy.

### Opportunistic offloads (fold in when adjacent code is touched)
- **C3** `save_agent_snapshot` sync writes + copytree (`snapshot_manager.py:222-279`) — Low; offload to `to_thread`, preserve byte-for-byte side-effect ordering (`:22-26`).
- **C2 (debug-guard half)** eager `logger.debug` f-strings interpolating full answer bodies even with DEBUG off (`answer_text_normalizer.py:108-110,115-117`) — guard with `if logger.isEnabledFor(logging.DEBUG):`. Skip the micro-optimization of the replace loop (N,M ~2-5).
- **B5/C4** per-round subagent dir + MCP-config rewrite (`orchestrator.py:6084-6087`) — Low; the "defensive against workspace clears" rationale is **dead** (`.massgen/` is now preserved, `_filesystem_manager.py:2059-2063`; in-loop `clear_workspace()` at `:6078` is commented out). Guard on a cheap existence check.

---

## 4. Refactor blocker + reliability (Tranche 3)

### A1 — Unify duplicated mid-stream injection closures — **Medium / Medium**
- **Where:** `orchestrator.py:3553-3700` (GeneralHookManager closure) vs `:4745-4858` (native closure); duplicated tails `:3705-3806` vs `:4863-4929`; remaining install methods `:3491,3808,3863,4712`. Target: `orchestrator_collaborators/midstream_injection_hook_installer.py` (already owns 6 pure helpers).
- **Problem:** Two near-identical `async def get_injection_content()` closures; a debug workspace-listing block exists in only one path (proof of drift). A fix to one backend path silently skips the other (CLAUDE.md backend-parity hazard).
- **Note:** the scary "ordering divergence" claim was **verified inert** — `restart_pending` recompute reads only `seen_answer_counts`, mutated at the same relative position in both paths. This is near-mechanical de-dup.
- **Fix:** Extract a single `async build_midstream_injection(agent_id, answers, *, native=False)` onto the installer; both setup methods call it via the hook callback. Move the ~95%-duplicated tails into a shared `_register_common_post_tool_hooks(...)`. Add a regression test asserting `available_agent_labels` reflect injected labels across both paths. Completes the `MidStreamInjectionHookInstaller` extraction.

### D3 — Make post-record bookkeeping non-fatal — **Small (targeted)**
- **Where:** `orchestrator.py:2544` (one try spanning the whole per-chunk handler) → `:3110-3136` (except, `is_killed=True` at `:3123`). `add_agent_answer` at `:2646` runs *before* the fallible enrichment.
- **Problem:** A bug in non-essential bookkeeping (changedoc `:2662-2681`, emitter `:2698-2705`, status writes) kills the whole agent identically to a real stream error.
- **Note:** "answer may be lost" is mostly refuted — `add_agent_answer` runs first and `is_killed` doesn't purge `answers_by_agent`. Genuine loss only in the narrow pre-record window (`_coerce` `:2627`, `_save_agent_snapshot` `:2633`).
- **Fix:** Wrap **only** the post-record enrichment in a local `try/except-log-continue`; leave stream consumption (`:2546`) and pre-record snapshot (`:2633`) under the fatal except. **Do NOT split the whole 570-line try** (high risk in a hot loop). Tests: inject changedoc/emitter failures, assert answer survives and `is_killed` stays False.

### D2 — Surface worktree-isolation degradation — **Low–Medium / Medium**
- **Where:** `orchestrator.py:6216-6218` (broad `except Exception` → `logger.warning` → `round_worktree_paths=None`).
- **Note:** "cross-agent clobbering" is **substantially refuted** — each agent already owns a separate `cwd`; the per-round feature only layers git branches on top, and shared dicts are written only after success (`:6211-6212`). Real kernel: weak observability from a bare except. Strongest residual risk is the writable shared-context-path case.
- **Fix:** Narrow the except to git/worktree errors; emit a user-visible `StreamChunk` warning (not just `logger.warning`) and record degraded state on `AgentState`. Don't abort the round on transient git errors (would regress graceful degradation). Test: inject isolation-setup failure, assert visible signal + recorded state.

---

## 5. Hygiene quick wins (any time, all Small)

- **A3** — fix the stale roadmap table (`orchestrator_refactor_roadmap.md:45,47`): mark AgentOrchestrationSetup done, re-scope the installer cluster to (1) closure unification, (2) hook-method relocation.
- **E1** — `test_message_context_building.py:52,82,125,172`: 4 collected tests with **zero assertions** (only `print()`s, return None → pass unconditionally). Convert booleans to `assert`s, strip the `sys.path`/`main()` scaffolding (`:11-13,243-274`), verify red-green, or delete. Narrow real gap: history-section rendering / turn-progression (core path otherwise covered in `test_position_bias_calibration.py`).
- **E2** — `test_grok_backend.py:20,54,92`: print-driven, `return True/False`, no asserts. **Correction:** these do NOT error in CI (return-not-None only fires for *sync* tests; under `asyncio_mode=auto` they pass silently). Grok coverage already exists elsewhere → **rewrite as real pytest or just delete**.
- **Sweep:** `rg -L "def test_" massgen/tests | xargs rg -L "assert"` to find other assertion-free collected test files.

---

## 6. Recommended sequencing

1. **Tranche 1 — Correctness (lock-free):** R1, R2/R3. Prerequisites for B1. Directly improves convergence quality.
2. **Tranche 2 — Latency:** B1 `to_thread` offload (now safe). Test peer-revision delivery survives a yielding copy. Fold in C2 debug-guard.
3. **Tranche 3 — Refactor + reliability:** A1 (finish installer extraction), R4, D3 (targeted), D2. Plus A3/E1/E2 hygiene.
4. **Tranche 4 — Bigger latency (only after B1 measured):** B2 incremental snapshot copy (hash/mtime-skip unchanged peers; copy only just-answered agents on injection), folding in B4 path-rewrite skip and C1 single-walk. Large effort + real correctness risk (per-viewing anonymization + dest rewriting), bounded by the 2-injection/round cap — justify only after B1 reveals stall-vs-volume split.

**Ordering rationale:** correctness before the latency change that exposes it; B1 establishes the measurement baseline before the expensive B2; the one refactor blocker (A1) is mechanical and de-risked; hygiene is free.

---

## What's Next

- Implement Tranche 1 (R1 + R2/R3) under TDD — write the race-exposing tests first (force a yield between content-select and seen-mark; force a background append during the pop window).
- Then B1 with its delivery-survival test, confirming the race fixes hold under a genuinely-yielding copy.
- Defer Linear issues / branch / push until explicitly approved (per current instruction).
- Re-run the parallelism sweep's failed `check-then-act` verifier leg if deeper assurance on that angle is wanted before implementation.

**Raw audit outputs (this session, ephemeral):**
- Eng-health: `/private/tmp/.../tasks/w60ugzohg.output`
- Concurrency: `/private/tmp/.../tasks/wuisd41xj.output`
- Workflow scripts saved under `.../workflows/scripts/` (re-runnable via `Workflow({scriptPath, resumeFromRunId})`).
