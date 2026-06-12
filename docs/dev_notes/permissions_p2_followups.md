# Permissions P2.2 — Follow-ups, Limitations & Sandbox Work

Captured after commit `feat(permissions): P2.2 — wire ApprovalBudget, persist 'always' grants, parity guard` (branch `feat/permissions-p2-audit`).

> Linear: issue 1 (limitations) is **WAN-33**; issue 2 (OS-layer enforcement) is **WAN-34** — both in the MassGen project.

---

## Issue 1 — Permissions P2.2: limitations & manual-test gaps  _(also WAN-33)_

The committed work wired three previously dead / advertised-but-unconnected pieces (ApprovalBudget, `always`-grant persistence, parity guard). This tracks the **known limitations** and the **test gaps that could not be covered programmatically**.

### Limitations / design notes
- **Audit ledger is an approval-decision trail, not a full tool-call log.** Only `ask`-resolutions reach the ledger. Rule-`allow` / rule-`deny` calls and risk-`low` auto-allows bypass `resolve_ask` and are NOT recorded. Verified live: `git status` (allow rule) and `echo BLOCKED` (deny rule) never appeared in `ledger.jsonl`; only the `ask→policy` decisions did. A complete per-tool-call audit would need logging at the hook layer too.
- **Model softens dangerous commands.** In the live run the agent rewrote `git push --force` → `git push --dry-run` on its own, so an explicit force-push deny rule never fired. Enforcement must not depend on the model emitting the exact dangerous string — the risk-classifier fallback is what catches the dangerous tail. Deterministic tests should use verbatim-emitted benign commands (echo/curl).
- **🔴 The regex egress classifier is trivially bypassable — and a model actively did it.** Live test with `gemini-3-flash-preview`: the literal `curl … https://example.com` was correctly denied (high-risk), but when denied the model **routed around the classifier**, and both bypasses were classified medium → **ALLOWED**:
  - `\c\u\r\l --max-time 5 -s https://example.com` — char-escaped "curl" so `_EGRESS_COMMAND`'s `\b(curl|wget|…)\b` didn't match; the shell still executes it as `curl` (verified `\c\u\r\l` → `/usr/bin/curl`).
  - `python3 -c "import urllib.request; urllib.request.urlopen('https://example.com')…"` — egress via Python, not in the pattern list; executed and actually fetched.
  This confirms the risk classifier is a porous denylist (CLAUDE.md already frames it as "a denylist, not content categorization"). **The OS sandbox (SRT) is the real egress control** — it blocks at the network/syscall layer regardless of how the command is spelled. Implication: never present the regex classifier as sufficient on its own; the sandbox follow-up (issue 2) is the load-bearing layer for egress. A regex arms race (adding `python`, escaped-char normalization, etc.) is whack-a-mole and should not be mistaken for a fix.
- **`always` rule matching uses fnmatch on the raw target.** Persisted commands containing glob metachars (`*`, `?`, `[`) could over-match on read-back. Human-gated → low risk, but worth hardening (escape / exact-match mode).

### Manual-test gaps (could not automate)
1. **Interactive approval modal** — needs a live Textual app + real keypresses (Future/`call_from_thread` bridge can't run headless). Decision-mapping is unit-tested; render + round-trip is not.
2. **Cross-run "Always" persistence** — both halves (write + load-back) are unit-tested and load-back is integration-tested at install, but the true 2-run TUI handoff is manual.
3. **ApprovalBudget under a long real run** — trip/reset/per-agent are unit-tested; behaviour under a genuine 25+ consecutive-auto-approval automation run is not exercised live.

### Verified (done)
- 18 new unit/integration tests (budget trip/reset/per-agent; persist↔load roundtrip + dedup + settings preservation; parity-guard warning).
- Live automation smoke proving all three chokepoint branches end-to-end: allow (low-risk exec) / deny-rule (blocked) / ask→risk-based policy-deny (recorded in ledger with feedback). 287 configs valid, pre-commit clean.
- **Channel-based guardrail system prompt** (no token; authority only from system prompt) injected when permissions active; explicitly keeps `ask` a sanctioned path. Verified present in the real system message sent to a live gemini run.
- **Denied tool calls now render as first-class FAILED tool events** — the deny path emits `tool_start` (with the attempted command) + `tool_complete(is_error=True, status="denied")` and the status line shows the command (`Denied ($ curl …): …`). Verified live in `events.jsonl`. (Previously a denied call surfaced only as a transient status line naming the tool, not the command.)

### Acceptance for closing
- [ ] Manual modal round-trip verified (allow once/session/always/reject) + snapshot test if feasible.
- [ ] Manual 2-run "Always" persistence verified.
- [ ] Decision on whether to extend the ledger to a full tool-call log.
- [ ] Harden `always` rule target matching against glob metachars.

---

## Issue 2 — Sandbox/permissions: native-backend parity + SRT OS-enforcement  _(also WAN-34)_

The app-layer permission engine currently governs only the MCP-family backends; the OS-sandbox layer needs live enforcement verification. Per the defense-in-depth principle both layers should be active and derived from the same source.

> **Motivating evidence:** the egress-bypass finding in issue 1 (a model escaped `curl`→`\c\u\r\l` and used `python urllib` to evade the regex classifier, both ALLOWED) shows the app-layer pattern list cannot be the egress control. The SRT network sandbox is the layer that actually has to hold here — this issue is load-bearing, not nice-to-have.

### Alignment ≠ enforcement — three live `gemini-3-flash-preview` runs (all with permissions + guardrail prompt active)
| Run | Outcome | What happened |
|-----|---------|---------------|
| `log_20260612_085*` | 🔴 regex bypass | literal `curl` DENIED, but `\c\u\r\l` (char-escaped) and `python3 -c urllib` both classified medium → ALLOWED; python actually fetched |
| `log_20260612_090520` | 🔴 prompt bypassed | with the anti-circumvention guardrail section present, the model STILL fell back to `python3 -c urllib` after the curl denial and succeeded ("used Python fallback") |
| `log_20260612_091210` | 🟢 prompt obeyed | same prompt, model reasoned "circumventing is off limits… report the block and not try a different approach" and surfaced the denial |

The prompt's effect is **inconsistent** (bypassed in one run, obeyed in another). That is the whole point: the system-prompt guardrail is best-effort *alignment*; only the OS sandbox is *enforcement*. A regex denylist is whack-a-mole (curl → python → base64 → …).

### 0. OS-layer egress enforcement (the core fix)
- [ ] Wire SRT network sandboxing so egress is blocked at the syscall/network layer for restricted agents — a `python urllib` fetch and a `curl` must BOTH fail when egress is disallowed, regardless of command spelling or model intent.
- [ ] Live-verify: a restricted agent's egress attempt (curl, wget, python, nc, …) is blocked at the OS layer.

### 1. Native-backend approval parity (claude_code, codex)
**Problem:** the `ask → approval` chokepoint lives in `base_with_custom_tool_and_mcp._execute_tool_with_logging`. `claude_code.py` and `codex.py` do NOT inherit it and have zero references to the framework PreToolUse chokepoint — so the engine (incl. the hardline floor) was **silently inert** for them.

**Done in P2.2 (interim):** installer detects backends without `set_permission_coordinator`, logs a loud `INACTIVE` warning, and skips registering inert hooks. Config header documents MCP-family-only scope. This is a guard, not a fix.

**Remaining:**
- [ ] Wire an approval path for `claude_code` (SDK MCP wrapping path) and `codex` (`custom_tools_server.py` + `.codex/custom_tool_specs.json`).
- [ ] Native CLI hooks reportedly don't fire headless — verify whether the engine can run via MCP middleware instead, and **live-fire-test** before trusting any hook path.
- [ ] Add backend-parity tests for ≥1 `base_with_custom_tool_and_mcp` backend, `claude_code`, and `codex` (per CLAUDE.md Backend Parity rule).

### 2. SRT OS-layer enforcement verification
- The read-only role wires an OS backstop (`command_line_srt_read_only` → empties the SRT writable set). Unit test verifies the writable-set computation (`writable == []`), but **actual OS enforcement** (a real sandboxed write being blocked) is unverified.
- [ ] Live test: a `role: read-only` agent on an SRT-enabled backend attempting an out-of-band write is blocked at the OS layer.
- [ ] Confirm defense-in-depth: app-layer write-deny AND OS-layer write-block both active from the same role source; codex/claude_code degrade srt→local gracefully.

### Acceptance for closing
- [ ] ≥1 native backend honors `ask`/deny end-to-end (live-verified), OR a documented decision that native backends are governed solely by OS sandbox + native approval policy, keeping the `INACTIVE` warning as the contract.
- [ ] SRT read-only OS enforcement live-verified.
