# 🚀 Release Highlights — v0.1.94 (2026-06-05)

v0.1.94 — Parallelism Hardening (Engineering Health) — strengthens the orchestrator's parallel execution. It moves the snapshot copy off the event loop so agents keep streaming concurrently, backs it with immutable versioned snapshots that keep the off-loop copy safe, and closes latent concurrency races. No per-backend functionality changes (parity principle).

### ⚡ Snapshot Copy Off the Event Loop
- `FilesystemManager.copy_snapshots_to_temp_workspace` now runs its blocking `rmtree`/`copytree`/scrub on a worker thread via `asyncio.to_thread`
- One agent's snapshot copy no longer stalls every other agent's streaming

### 🔒 Immutable, Versioned Snapshots
- Each agent's snapshot path `<base>/<agent_id>` is now a symlink to an immutable `<base>/.versions/<agent_id>/v<N>` directory
- `save_snapshot` (and the interrupted-turn partial save) publish a fresh version and atomically repoint the symlink instead of rewriting in place
- The peer-context copy `acquire`s (refcounts) the current version for the duration of its copy; GC never deletes a pinned or in-flight version
- Eliminates the read-during-write race the off-loop copy would otherwise expose — coordinated by the new `SnapshotVersionStore`

### 🧵 Concurrency Correctness Fixes
- **R1** — lost peer-answer revision across the injection `await` window (counts now captured at selection time)
- **R2/R3** — lost background-subagent result from a blind queue `pop` (consume only the consumed ids)
- **R4** — leaked background trace-analyzer tasks on cleanup (cancelled before the flush)
- **R5** — cancel-without-await teardown (`cancel_all_subagents` now awaits cancellations against the live registry)
- **D2** — worktree-isolation degradation never surfaced because `emit_status` was called with an invalid `status=` kwarg whose `TypeError` was swallowed
- **D3** — changedoc enrichment made non-fatal

### 🧩 Unified Mid-Stream Injection
- The two ~150-line per-backend `get_injection_content` closures collapsed into one `build_midstream_injection(..., native=)`, preserving the `update_context → refresh_checklist` side-effect order on both paths
- The triplicated background-wait interrupt provider consolidated into one helper

### 🧪 Tests
- New race/regression suites driven under TDD with cost-free simulation: `test_concurrency_race_fixes.py`, `test_snapshot_version_store.py`, `test_snapshot_versioned_save.py`, `test_snapshot_copy_offload.py`, `test_midstream_injection_unified.py`, `test_wait_interrupt_provider.py`

---

### 📖 Install
```bash
pip install massgen==0.1.94
```
