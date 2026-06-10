# PR Draft: OS-Level Agent Sandboxing (SRT) + Permission-Hook Hardening

**Branch:** `feat/better-sandboxing`

## Summary

Adds **OS-level execution sandboxing** for agents via Anthropic's [sandbox-runtime](https://github.com/anthropic-experimental/sandbox-runtime) (`srt`: bubblewrap/Linux, Seatbelt/macOS), and **hardens the existing application-layer permission hook** against file-tool sandbox escapes. Default-off, one-knob opt-in; current behavior is unchanged unless a config sets `command_line_execution_mode: srt`.

Defense in depth, by design: the OS layer (SRT) and the app layer (`PathPermissionManager`) are derived from the **same** path policy and both stay active. SRT closes the shell escape hatch (e.g. `echo x > /etc/passwd`); the hardened hook closes file-tool escapes (`write_file`/`move`/`copy` to/from outside the workspace).

## What's included

### 1. SRT sandbox mode (`command_line_execution_mode: srt`)
- **`SrtManager`** (`massgen/filesystem_manager/_srt_manager.py`) — derives per-agent SRT settings from `PathPermissionManager.managed_paths`: `allowWrite` = writable paths, `denyWrite`/`denyRead` for read-only/protected paths, **network deny-all by default** (allowlist is opt-in, documented as a capability grant), and a **built-in read-deny baseline for secret stores** (`~/.ssh`, `~/.aws`, `~/.gnupg`, cloud creds, `/etc/shadow`, …) since SRT reads are otherwise allow-all.
- **Command-line MCP** wraps each executed command: `srt --settings cfg sh -c '<cmd>'`.
- **Filesystem-tools MCP servers** are OS-wrapped too (defense in depth), via the **`sh -c` form** — required because `srt` otherwise consumes the server's `--` separator. **npx/npm launchers (and the no-roots wrapper that spawns npx) auto-skip** wrapping (they need the registry + `~/.npm` writes the sandbox blocks) and keep their app-layer protection.
- **Native-sandbox backends degrade `srt`→`local`**: `has_native_execution_sandbox()` (True for `codex` `--full-auto` and `claude_code`) prevents nested Seatbelt/Landlock hangs; the stored config is normalized so downstream raw reads see `local`.
- **Subagents inherit** the parent's `command_line_srt_*` settings (parity with Docker).
- New backend params `command_line_srt_network_allowed_domains` / `_deny_read` / `_allow_unix_sockets` added to the single-source exclusion list; `srt` added to the MCP executable allowlist.
- Config example: `massgen/configs/tools/filesystem/sandbox/srt_sandbox.yaml`.

### 2. Permission-hook hardening (`PathPermissionManager`)
- New `_validate_no_path_arg_escapes`: a **key-agnostic scan** that walks the full tool-args tree (nested dicts + lists) and denies any value resolving outside all managed areas. Closes the prior **fail-open** behavior (path under an unrecognized key, list-valued path, or move/copy `source` pointing outside) without false positives (non-path strings resolve harmlessly inside the workspace; content keys are skipped). Symlinks/`..` were already handled by `.resolve()`.

## Tests

| File | Covers |
|------|--------|
| `test_srt_manager.py` | settings derivation, profiles, secret read-deny baseline, protected-path read+write deny, wrapping, availability guards |
| `test_srt_filesystem_integration.py` | command-line + fs-tools config wiring, `sh -c` wrap, npx / no-roots auto-skip, MCP-security validation |
| `test_srt_backend_degrade.py` | `srt`→`local` degrade for native-sandbox backends; API backends keep `srt` |
| `test_path_permission_hook_adversarial.py` | 15 escape vectors (absolute/`..`/symlink/unrecognized-key/list/nested-dict/move-source/copy-source/read-exfil) + false-positive guards |
| `test_subagent_manager.py::TestSrtSettingsInheritance` | subagent inherits parent srt settings |

## Live verification (macOS 15.7, srt 1.0.0)
- Standalone srt: allowed-write ✓, out-of-scope write blocked ✓, deny-all network blocked ✓, **secret read blocked** ✓.
- **3 API backends** (openrouter/`chatcompletion`, OpenAI Responses/`openai`, Gemini/`gemini`): workspace write OK; out-of-workspace write → `Operation not permitted`; file-tool escape blocked.
- **codex + srt** and **claude_code + srt**: degrade to local, run via native sandbox, complete.

## Pre-merge quality gate
A multi-agent code review (correctness/security/parity/tests, adversarially verified) was run on the diff; **all 15 confirmed findings fixed** — most notably a HIGH read-confinement hole (SRT reads were default-allow) and a subagent settings-inheritance parity gap.

## Known follow-ups (not in this PR)
- `write_file`/`edit_file` (npx filesystem server) is app-layer-only; full OS coverage needs a globally-installed (non-npx) filesystem server.
- Network-egress MITM / per-agent credential scoping (allowlist-only egress can leak via embedded API keys).
- claude_code native-sandbox lever via `ClaudeAgentOptions`.

## Configs used to test
- `massgen/configs/tools/filesystem/sandbox/srt_sandbox.yaml` (committed)
- Throwaway smoke configs (openrouter/openai/gemini/codex/claude_code + srt) under `/tmp/srt_smoke/` (not committed).
