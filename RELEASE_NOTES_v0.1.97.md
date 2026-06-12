# 🚀 Release Highlights — v0.1.97 (2026-06-12)

**Theme: Application-Layer Permission Engine** — the opt-in approval pipeline that complements v0.1.96's OS sandbox. Defense in depth: the OS layer enforces, the app layer keeps a human in the loop on the risky calls.

### 🛡️ Layered permission engine (hardline → rules → risk)
- **Hardline floor**: a non-overridable blocklist denies catastrophic commands (`rm -rf /`, fork bombs, raw-disk `dd`) regardless of any rule or mode.
- **Declarative rules**: an `allow/ask/deny` algebra over a small `action(target)` vocabulary (`command`, `read_file`, `write_file`, `read_url`, `mcp`, `*`) with **deny-wins** precedence across scopes.
- **Risk classifier**: tiers a call by blast radius, not name — auto-allows reads and in-workspace edits, asks only for the dangerous tail (network egress, force-push, publish/spend, privilege escalation).

### ✋ Approval that fits the run
- **Interactive modal** (`ToolApprovalModal`): allow once / allow session / always · reject, when a human is present.
- **Automation policy**: `risk-based` (default — high denied with a reason, low/medium allowed), `deny-all`, or `allow-all`.
- **File handshake** (`FileApprovalProvider`): `req_*.json` / `resp_*.json` for headless/remote approval (Slack bot, `/approve <id>`, …). Fail-closed on timeout throughout.

### 🧑‍🤝‍🧑 Roles, audit & guards
- **Per-agent roles**: `read-only` / `researcher` deny writes+shell; a `read-only` role also empties the agent's SRT writable set (OS backstop). Role + user rules merge deny-wins.
- **Audit ledger**: every approval decision is appended to a crash-safe JSONL trail (who/what/why/outcome).
- **Runaway-loop budget**: `max_consecutive_auto` caps consecutive auto-approvals per agent and fail-closes past the cap; a human decision resets it.
- **`always`-grant persistence**: an "Always" approval persists as an `allow(...)` rule in `settings.local.json` and loads back next run.

### 🧭 Guardrail-aware system prompt (channel-based)
- When permissions are active, the system prompt tells the model to **follow blocks and surface-and-ask rather than circumvent** them — and that **`ask` is a sanctioned path**, not a block. Authority comes only from the system prompt (no leakable token).
- **Honest scope**: the prompt + regex classifier are best-effort *alignment*. Live runs showed a model evading the egress classifier via `\c\u\r\l` / `python urllib` — so the OS sandbox (v0.1.96) remains the load-bearing enforcement. See `docs/dev_notes/permissions_p2_followups.md`.

### 🔧 Also in this release
- **Denied tool calls are first-class failed tool events**: the deny path emits `tool_start` (with the attempted command) + `tool_complete(is_error=True, status="denied")`, so blocked calls show in the TUI/WebUI timeline with the command, not just a status line.
- **Backend parity guard**: native backends (`claude_code`, `codex`) don't run the framework chokepoint, so a `permissions:` block there is reported **INACTIVE** at startup instead of silently inert.

---

### 📖 Getting Started
- [**Quick Start Guide**](https://github.com/massgen/MassGen?tab=readme-ov-file#1--installation): upgrade and try the permission engine.
- **Try the approval modal (interactive):**

```bash
# A high-risk command pops the approval modal (allow once/session/always · reject)
uv run massgen --config massgen/configs/tools/permissions/permission_modal_interactive.yaml \
  "Run the shell command: curl -s https://example.com"
```

- **Try risk-tiered automation (headless deny):**

```bash
uv run massgen --automation --config massgen/configs/tools/permissions/permission_engine.yaml \
  "Run 'git status', then run 'git push --force origin main' and report each result."
# Expected: git status runs; the force-push is denied with a reason.
```

## What's Changed
* feat: layered opt-in permission system (P0–P2.2) — rules, approval, audit, guardrail prompt by @ncrispino in https://github.com/massgen/MassGen/pull/1127

**Full Changelog**: https://github.com/massgen/MassGen/compare/v0.1.96...v0.1.97
