# 🚀 Release Highlights — v0.1.95 (2026-06-08)

v0.1.95 — Mid-Stream Steering — extends mid-stream injection from a UI-only capability into a programmatic, headless one, and upgrades it from inject-at-next-boundary into true interrupt-and-resume for the CLI backends. A human (or any UI-less caller) can now drop guidance into an agent *while it is streaming* — over a file inbox in `--automation`, or through the MCP-middleware hook path — and Codex/Antigravity will interrupt the in-flight turn, fold the steering in, and resume rather than restart. The injection chokepoint stays shared across TUI, WebUI, and the new headless path.

### 📨 Programmatic Steering Inbox (`--inbox-dir`)
- `send_steering_message()` (`massgen/steering.py`) drops a `msg_*.json` into a caller-known inbox directory
- `RuntimeInboxPoller` routes it through `RuntimeInputDelivery.poll_runtime_inbox` to the same `set_pending_input` chokepoint the TUI (`_queue_human_input`) and WebUI (`broadcast_response`) already use
- Reachable from `--automation` and any UI-less caller, with per-message targeting (one agent / a subset / broadcast); the resolved inbox is announced as `RUNTIME_INBOX:` in automation output

### ⏯️ Interrupt-and-Resume Steering (Codex & Antigravity)
- When steering arrives mid-turn, the watcher kills the in-flight turn and resumes — `codex exec resume <session_id> <prompt>` for Codex, `agy --continue -p <prompt>` for Antigravity — folding the steering in without waiting for a round boundary
- Antigravity promotes pre-interrupt scratch deliverables to the workspace first, so work done before the interrupt isn't lost
- Gated by `supports_interrupt_resume()` with `interrupt_poll_seconds` / `max_interrupts_per_turn` knobs

### 🪝 MCP-Server-Hook Payload IPC (Antigravity, codex parity)
- `write_post_tool_use_hook()` / `read_unconsumed_hook_content()` with `expires_at`-guarded payloads consumed by the MCP middleware (`massgen/mcp_tools/hook_middleware.py`)
- The backend-agnostic per-chunk injection flush now works for `agy` the same way it does for codex
- The Antigravity `--model` flag is now actually passed to `agy` (was previously resolved but omitted)

### 🔧 Bug Fixes
- **`--inbox-dir` honored for all session modes**: the env-var export lived inside the new-session branch, so `--session-id` / config `session_id` / `--continue` runs silently dropped programmatic steering — now hoisted into `_resolve_runtime_inbox()` before the branch
- **Stale steering carryforward**: `read_unconsumed_hook_content()` now drops payloads past `expires_at` (fail-open on malformed values), so a stale hook can't trigger an unexpected interrupt/resume — both backends
- **Swallowed watcher failures**: interrupt/resume cleanup now logs non-cancellation failures at debug instead of passing — both backends
- **Round-1 native-hook gap (Antigravity)**: `hook_dir` is set at orchestrator fetch time so first-round hooks are wired before the initial stream; middleware `hook_dir` coerced to `Path`

### 🧪 Tests
- New deterministic suites: `test_steering_inbox.py`, `test_codex_interrupt_resume.py`, `test_mcp_hook_middleware.py`, `test_live_proc_io.py`; expanded `test_antigravity_cli_backend.py`
- New opt-in live-fire tests (`@pytest.mark.live_api`): `test_steering_live.py`, `test_codex_interrupt_resume_live.py`, `test_antigravity_interrupt_resume_live.py`, `test_codex_middleware_firing_live.py`, `test_codex_hook_firing_live.py` — with non-blocking stdout polling so a buffering child can't hang the test

---

### 📖 Install
```bash
pip install massgen==0.1.95
```

### 🧭 Try It — headless steering
```bash
# Start a run, exposing a file inbox for programmatic steering
uv run massgen --automation --inbox-dir /tmp/inbox \
  --config massgen/configs/debug/codex_mcp_middleware_test.yaml "Write and refine a short essay."

# In another shell, drop a steering message mid-stream:
python -c "from massgen.steering import send_steering_message; send_steering_message('/tmp/inbox', 'prioritize concision')"
```

## What's Changed
* feat: Programmatic mid-stream injection and switch to resume by @ncrispino in https://github.com/massgen/MassGen/pull/1114

**Full Changelog**: https://github.com/massgen/MassGen/compare/v0.1.94...v0.1.95
