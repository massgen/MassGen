# 🚀 Release Highlights — v0.1.96 (2026-06-10)

v0.1.96 — OS-Level Agent Sandboxing — adds an opt-in OS sandbox for agent command execution via Anthropic's [sandbox-runtime](https://github.com/anthropic-experimental/sandbox-runtime) (`srt`: bubblewrap on Linux, Seatbelt on macOS), and hardens MassGen's application-layer permission hook against file-tool escapes. Defense in depth by design: both layers derive from the same path policy and stay active together. Default-off, one knob: `command_line_execution_mode: srt`.

### 🛡️ OS-Level Execution Sandbox
- New `command_line_execution_mode: srt` wraps agent command/code execution in `srt`
- `SrtManager` derives per-agent settings from `PathPermissionManager.managed_paths`: writable paths become `allowWrite`, read-only/protected paths become `denyWrite`
- Command-line MCP execution and filesystem-tools MCP servers are both OS-wrapped where the launcher supports it

### 🔒 Read & Network Confinement
- `command_line_srt_read_mode` defaults to `confined`: deny `$HOME`, then re-allow only workspace + context paths while keeping system runtime paths readable
- `strict` and `open` read modes are available for tighter or broader policies
- Network is deny-all by default; `command_line_srt_network_allowed_domains` is an explicit capability grant
- Built-in secret-store read denies are active, with `command_line_srt_deny_read` and `command_line_srt_allow_read` for config-specific adjustments

### 🧱 Permission-Hook Hardening
- `PathPermissionManager` now scans the full tool-argument tree, not just known path keys
- Blocks escapes through unrecognized keys, nested dicts/lists, `move`/`copy` sources, absolute paths, `..`, and symlinks resolving outside managed areas
- Keeps false positives low by skipping content-like fields and resolving non-path strings inside the workspace

### ⚙️ Backend Parity & Degrade Behavior
- Native-sandbox backends (Codex `--full-auto`, Claude Code) degrade `srt` to `local` to avoid nested sandbox hangs
- Subagents inherit parent `command_line_srt_*` settings, matching Docker inheritance behavior
- Framework MCP read roots are re-allowed under confined/strict profiles so wrapped filesystem-tool servers can read their own runtime while user secrets remain denied

### 🧪 Tests
- New deterministic suites: `test_srt_manager.py`, `test_srt_filesystem_integration.py`, `test_srt_backend_degrade.py`, `test_path_permission_hook_adversarial.py`
- Expanded `test_subagent_manager.py` with SRT settings inheritance coverage
- Live-verified on macOS 15.7 with `srt` 1.0.0 across standalone SRT, OpenRouter/chatcompletion, OpenAI Responses, Gemini, Codex, and Claude Code paths

---

### 📦 Install
```bash
pip install massgen==0.1.96
```

### ▶️ Try It — SRT sandboxing
```bash
# Prerequisite:
npm install -g @anthropic-ai/sandbox-runtime

uv run massgen --automation \
  --config massgen/configs/tools/filesystem/sandbox/srt_sandbox.yaml \
  "Create out.txt in the workspace, then try to read ~/.ssh/id_rsa"
```

Expected: the workspace write succeeds; out-of-scope reads and network egress are denied by the OS sandbox.

## What's Changed
* feat: OS-level SRT agent sandboxing + permission-hook hardening by @ncrispino in https://github.com/massgen/MassGen/pull/1125

**Full Changelog**: https://github.com/massgen/MassGen/compare/v0.1.95...v0.1.96
