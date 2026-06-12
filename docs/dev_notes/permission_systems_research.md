# Designing MassGen's Permission System: Synthesis of 11 Coding-Agent CLIs + HITL Research

## 1. Executive Summary — Thesis

**MassGen should not build a new permission engine. It already has the three load-bearing primitives that every mature CLI converged on — a deny/ask/allow hook chokepoint (`GeneralHookManager`), an app-layer path/permission validator (`PathPermissionManager`), and an OS sandbox (`SRT`). What it is missing is the *connective tissue*: a declarative rule layer, a working `ask` → human-approval path, risk-tiering, and an audit ledger.**

The strongest finding across all 11 CLIs and the HITL literature is a **three-layer separation that must never be collapsed**:

1. **Authorization** (deterministic): a policy/hook that hard-allows or hard-denies *regardless of what the model says*. Source of truth at the tool-calling boundary, never the prompt. This is MassGen's `PathPermissionManager` + `GeneralHookManager` + `SRT`.
2. **Approval** (human checkpoint): a confirmation for *ambiguous or high-stakes* actions. **"Approvals are not authorization"** — a click is not a security control; it is a UX signal. MassGen has the *plumbing* (interactive `approval_request.json`/`approval_response.json` handshake) but the per-tool-call `ask` decision is **currently a no-op at the chokepoint** (verified: `base_with_custom_tool_and_mcp.py` handles `deny` but falls through on `ask`).
3. **Guardrails** (probabilistic triage): an LLM-judge / classifier that decides *what reaches the human queue* — never the final gate for irreversible actions.

The single biggest lever MassGen is leaving on the table is **risk-tiering the `ask` decision** (gate on *blast radius*, not tool name) plus a **multi-scope declarative rule layer** (managed > project > user > agent) that compiles down to the hooks it already runs. MassGen's unique twist — it is **multi-agent** — means it also needs **per-agent / per-subagent permission scoping** (Amp's `context: thread|subagent`, Roo's per-mode tool groups) and a **per-agent SRT profile**, both of which map cleanly onto existing primitives.

Opinionated bottom line: steal **Claude Code's fixed evaluation order + multi-scope deny-wins**, **Codex's two-orthogonal-axes (approval policy ⟂ sandbox mode) + Starlark execpolicy**, **OpenHands' inline self-scored risk + analyzer/policy decoupling**, **Amp's `delegate`-to-external-policy + `context` per-agent scoping**, and **OpenClaw/Hermes' shell-hook policy callback + resolved-binary-path allowlist**. Wire `ask` into the existing approval handshake, harden the handshake with timeout/decline-vs-cancel/idempotent-resume, and add an append-only approval ledger.

---

## 2. Comparison Matrix

| CLI | Modes / Autonomy axes | Rule syntax | Granularity | HITL flow | OS Sandbox | Extensibility / policy callback |
|---|---|---|---|---|---|---|
| [**Claude Code**](https://code.claude.com/docs/en/permissions) | 6 modes: default, acceptEdits, plan, auto (server classifier), dontAsk, bypassPermissions | `Tool`/`Tool(specifier)` allow/ask/deny in settings.json; gitignore-anchored paths (`//abs`,`~/`,`/`,`./`); shell-operator-aware Bash globs | per-tool, per-command-pattern, per-path, per-domain, per-MCP-server/tool, per-subagent, per-scope | Interactive prompt: allow-once / "don't ask again" (persists rule); per-subcommand rule save | Seatbelt (mac) / bubblewrap+proxy (Linux), Bash-only, network proxy | PreToolUse hooks (allow/deny/ask/defer, updatedInput); SDK `canUseTool`; managed-settings lock |
| [**Codex CLI**](https://developers.openai.com/codex/config-reference) | **2 orthogonal axes**: approval_policy (untrusted/on-request/never/granular) ⟂ sandbox_mode (read-only/workspace-write/danger) + `approvals_reviewer=auto_review` | TOML config + **Starlark `.rules` execpolicy** (`prefix_rule(pattern, decision)`, forbidden>prompt>allow, self-testing) | per-mode, per-command-prefix, per-path, per-domain, per-tool, per-approval-category, per-project-trust, per-MCP-server | TUI prompt; session-level via `/permissions`; granular categories pre-authorize; `auto_review` subagent | Seatbelt / bubblewrap+seccomp; default-deny net + domain proxy | Lifecycle hooks (PreToolUse/PermissionRequest allow/deny/ask); `requirements.toml` enterprise hard-lock |
| [**Antigravity (agy)**](https://antigravity.google/docs/cli-permissions) | request-review, proceed-in-sandbox, always-proceed, strict, `--dangerously-skip-permissions` | **`action(target)` algebra** (read_file/write_file/read_url/execute_url/command/unsandboxed/mcp/`*`) in deny/ask/allow; Deny>Ask>Allow | per-tool, per-command-pattern (exact/glob/regex), per-path, per-domain, per-MCP, per-workspace, per-session | Editable prompt cards (widen/narrow scope inline); persistence gated by workspace trust | Seatbelt / nsjail; **read_url domains compiled into sandbox net allowlist** | Plugins bundle skills/agents/rules/MCP/hooks; no public policy-callback API (closed source) |
| [**opencode**](https://opencode.ai/docs/permissions/) | allow / ask / deny (uniform string, per-tool map, or per-tool pattern object) | Per-tool object, **last-match-wins** glob patterns (`"git *":allow`, `"rm *":deny`) | per-tool, per-command-pattern, per-path, per-URL/query, per-agent, per-project; `doom_loop`, `external_directory` | TUI: once / always (tool-suggested safe pattern) / reject (with feedback) | **None native** | Plugin `tool.execute.before/after` (throw-to-deny, mutate args); `permission.ask` hook partially wired |
| [**OpenClaw**](https://docs.openclaw.ai/) | exec.security (deny/allowlist/full) × ask (off/on-miss/always); sandbox.mode (off/non-main/all) | JSON exec-approvals; **glob on RESOLVED BINARY PATH** (defeats PATH-shadowing); safe-bin argv profiles | per-agent, per-command-pattern, per-binary-argv, per-tool, per-path, per-session, per-network, per-channel | allow-once / always-allow / deny; **channel-portable** (`/approve <id>` from Slack/Discord) | Docker/SSH/OpenShell backends; net default `none`; 3 sequential gates (deny is final) | ~30 typed plugin hooks; `before_tool_call` returns block/params/**requireApproval** (severity, timeout, onResolution) |
| [**Hermes**](https://hermes-agent.nousresearch.com/docs/) | manual / smart (LLM triage) / off; YOLO; **non-overridable hardline blocklist** | ~30 built-in regex danger patterns + coarse `command_allowlist` by name; **shell hooks return `{decision:block}`** | per-command-pattern, per-command-name, per-tool, per-path/cwd (via hooks), per-user/platform; no per-project | once/session/always/deny; fail-closed (timeout=deny); channel reply yes/no | Backend-selectable (local/ssh/docker/modal/daytona); container = boundary (skips checks) | **Shell-hook policy callbacks** (`pre_tool_call` JSON stdin→block stdout); consent-gated hooks |
| [**Gemini CLI**](https://github.com/google-gemini/gemini-cli) | default, auto_edit, plan, yolo (session-only) | **5-tier TOML Policy Engine** `[[rule]]` (toolName/argsPattern-regex/commandPrefix/mcpName → allow/deny/ask_user, decimal priority) + legacy settings.json | per-tool, per-command-pattern, **per-arg-content (argsPattern regex)**, per-MCP, per-subagent, per-mode, per-project/user/admin | Proceed-once / always-allow tool / always-allow server; `ask_user`→deny in headless | Seatbelt profiles / Docker / gVisor / Win Low-Integrity; **proxied profiles restrict egress** | Policy Engine (admin root-owned dirs, SHA-256 integrity); Trusted Folders safe-mode; MCP trust |
| [**aider**](https://aider.chat) | Interactive confirm (default), `--yes-always`, deny, dry-run, no-auto-commits | **No rule DSL** — boolean flags + `.aider.conf.yml` + env vars | per-action-category, per-item-at-prompt; no per-tool ACL / glob / domain | Single `confirm_ask` primitive: Yes/No/All/Skip-all/Don't-ask-again; explicit_yes_required blocks "All" for shell | **None** | No policy-callback API; custom `InputOutput` subclass (unofficial) |
| [**Sourcegraph Amp**](https://ampcode.com) | **Default = no prompts** (philosophy); rule engine when configured: allow/ask/reject/**delegate** | JSON `amp.permissions` (tool glob + `matches:{cmd,path,url}`) AND terse text shorthand; first-match-wins, default-allow | per-tool, per-command-pattern, per-path, per-domain, per-MCP, **per-agent (`context: thread\|subagent`)**, per-arg-value | `[y/n/!]` (allow-once / reject / allowlist-permanently) | **None** (Git-as-undo philosophy) | **Plugin `tool.call`: allow/reject/modify/synthesize**; **`delegate`→external program (OPA) via stdin JSON + exit codes**; managed-settings tier |
| [**Goose**](https://goose-docs.ai/) | GooseMode: auto, approve, **smart_approve (LLM PermissionJudge)**, chat | Mode string + per-tool `permission.yaml` (AlwaysAllow/AskBefore/NeverAllow); Extension Allowlist (exact MCP launch cmd) | per-mode, per-tool, **per-operation-risk (LLM judge + MCP read_only/destructive annotations)**, per-MCP-server | Allow/Deny; promote to AlwaysAllow/NeverAllow (persists); smart_approve caches verdicts | macOS-Desktop-only Seatbelt + filtering egress proxy; CLI **not** sandboxed | **`ToolInspector` trait pipeline** (approve/deny/escalate); MCP annotations; Allowlist URL |
| [**Cline / Roo Code**](https://docs.cline.bot) | Plan/Act; Manual; per-category Auto-Approve; YOLO; **Roo per-mode tool-groups** | Markdown rules + path-glob frontmatter; **Roo `fileRegex`-restricted edit scope**; Roo allowed/denied command **prefix** lists (longest-prefix-wins) | per-action-category, per-path-scope, per-command-prefix, per-MCP-tool, **per-mode (Roo)**, per-rule-path | Approve/Reject card; persistence via Auto-Approve panel; **Max Requests** budget caps runaway loops | **None native** (approval = boundary) | **Cline Hooks PreToolUse** (`{cancel:true}` blocks any tool); SDK plugin system |
| [**OpenHands**](https://docs.openhands.dev/) | AlwaysConfirm, NeverConfirm, **ConfirmRisky(threshold)**; analyzers: LLM/Invariant/Pattern/PolicyRail/Ensemble | **No allow/deny DSL by default** — risk enum (LOW/MED/HIGH/UNKNOWN); Python `SecurityAnalyzerBase` subclass; Jinja2 policy; Invariant rule lang | per-action, per-command-pattern, **per-risk-threshold**, per-agent, **per-environment (conditional policy)** | `WAITING_FOR_CONFIRMATION` state; proceed/reject(+feedback)/always-proceed; **reject feedback → safer retry** | **Docker runtime** (fs isolation, net policy, CPU/mem/disk limits); analyzer ≠ sandbox | **2-axis decouple: SecurityAnalyzer ⟂ ConfirmationPolicy**; **inline `security_risk` JSON-schema self-score**; EnsembleAnalyzer (max-severity); runtime swap |

---

## 3. The Most Powerful Features Worth Stealing (ranked)

1. **Two orthogonal axes: approval policy ⟂ sandbox mode** — *Codex, OpenHands.* Decouple "WHEN to ask a human" from "WHAT the OS permits." MassGen already has the two enforcement layers (app `ask`/`deny` + SRT); it should expose them as **independent knobs** so `read-only + never-ask` (safe automation) and `risk-gated + sandboxed` (interactive) are first-class.
2. **Risk-tiered approval gated on blast radius, not tool name** — *OpenHands (inline `security_risk` self-score), OpenAI Agents SDK (`needs_approval` as callable), Goose (LLM PermissionJudge).* The single biggest anti-fatigue lever: auto-allow reads/edits inside the worktree; require approval only for force-push, out-of-workspace delete, net egress, secrets, publish, spend.
3. **Declarative multi-scope rule layer with fixed deny-wins evaluation order** — *Claude Code, Gemini CLI (5-tier), Codex (`requirements.toml`).* A YAML/TOML rule set (`managed > project > user > agent`) that *compiles down* to MassGen's hooks, where **deny at any scope beats allow at any scope** and managed-deny can't be loosened by CLI flags.
4. **`delegate` to an external policy program** — *Amp (`delegate to: OPA` via stdin JSON + exit codes), Hermes/OpenClaw (shell-hook `{decision:block}`).* Lets orgs plug OPA/Cedar without touching MassGen. A near-zero-cost extension of `PythonCallableHook` → a `SubprocessPolicyHook`.
5. **Per-agent / per-subagent permission scoping** — *Amp (`context: thread|subagent`), Roo Code (per-mode tool groups + `fileRegex`), opencode (per-agent overrides).* MassGen is multi-agent; a "researcher" agent should be read-only while an "implementer" writes. Maps onto `GeneralHookManager`'s existing per-agent hook registration.
6. **`updatedInput` / modify / sanitize-before-run** — *Claude Code (`updatedInput`), Amp (`modify`/`synthesize`), opencode/OpenClaw (mutate args).* MassGen's `HookResult` already carries `updated_input`/`modified_args` and chains them — extend usage to *scope-narrow* a command (e.g., inject `--dry-run`) rather than binary allow/deny.
7. **Allowlist on the resolved binary path + argv profiles** — *OpenClaw.* Globbing the *resolved* binary defeats PATH-shadowing/lookalike-binary attacks; safe-bin argv profiles (`maxPositional`, `deniedFlags`) let stdin-only filters run unprompted without becoming exfil vectors. Directly hardens MassGen's `_validate_command_tool`.
8. **Trusted Folders / project-trust gating** — *Gemini CLI (safe-mode), Codex (untrusted projects skip `.codex`), Antigravity (trust-state persistence).* An untrusted repo's `.massgen/` config, hooks, and rules must NOT auto-load — neutralizes config-injection from cloned repos.
9. **Sandbox network allowlist compiled from declared URL permissions** — *Antigravity.* Unify "what the agent may browse" with "what the sandbox may reach": a `read_url(domain)` grant injects that domain into SRT's `allowedDomains`. Closes the gap where app-layer and OS-layer net policy drift.
10. **Append-only approval ledger + reject-with-feedback** — *HITL research (OWASP ASI09), OpenHands (`reject_pending_actions(reason)` → safer retry), Cline `Max Requests`.* Turn ephemeral clicks into queryable accountability; feed denial reasons back so the agent self-corrects; cap runaway loops.
11. **Hardline blocklist immune to YOLO/bypass** — *Hermes, Claude Code (`rm -rf /` circuit breaker), OpenClaw (host-policy-wins-when-stricter).* A fixed catastrophic-pattern floor (`rm -rf /`, fork bombs, `dd` to disk) that survives even `--dangerously-skip-permissions`.
12. **Auto-review reviewer subagent** — *Codex (`auto_review`), Goose (PermissionJudge).* An LLM approver as a *triage* layer that auto-allows clearly-safe and auto-denies clearly-dangerous, escalating only ambiguous cases — **never** the final gate for irreversible actions.

---

## 4. Human-in-the-Loop Design

### 4.1 The core gap to fix first
The chokepoint (`base_with_custom_tool_and_mcp.py::_execute_tool_with_logging`) **handles `deny` but silently falls through on `decision == "ask"`** (verified — there is no `ask` branch; it executes the tool). Step one is wiring `ask` → the existing interactive approval handshake (`approval_request.json` / `approval_response.json`, surfaced as the TUI card). This is the highest-leverage change because every other HITL feature hangs off it.

### 4.2 Approval-grant model (allow-once / session / always)
Adopt the **four-scope grant** that nearly every CLI converged on, mapped to MassGen's scopes:
- **once** — single execution (in-memory, no persistence).
- **session** — sticky for this run (OpenAI SDK `alwaysApprove`, Claude `acceptEdits`). Store in an in-memory `SessionApprovalCache` keyed by `(agent_id, tool, normalized-pattern)`.
- **always** — persist a generated rule to `.massgen/settings.local.json` (Claude's `updatedPermissions`/`localSettings` model). **Gate persistence on project trust** (Antigravity's lesson: untrusted workspace → session-only).
- **deny / reject-with-feedback** — distinct from passive timeout. Reject feeds the reason back to the agent (OpenHands), so the agent retries a safer path instead of hard-failing.

Crucially, follow aider's **`explicit_yes_required`** guardrail: a batch "approve all" must **never** blanket-authorize arbitrary command execution or out-of-workspace writes.

### 4.3 Risk-based escalation (the anti-fatigue engine)
Replace tool-name gating with a **`RiskClassifier`** that scores each call into `{low, medium, high}` from *arguments + blast radius*, not identity. Concrete tiers:
- **low** (auto-allow): reads/edits/Bash inside the agent worktree, idempotent ops.
- **medium** (batch into a single digest, not N modals): writes to context paths, new MCP servers, network reads to allowlisted domains.
- **high** (always interrupt): force-push, delete outside workspace, secrets access, net egress to new domains, package publish, any spend, anything matching the hardline blocklist (which *cannot* be downgraded).

This is implementable two ways, composably (OpenHands' Ensemble, max-severity): (a) deterministic — `PathPermissionManager` already knows blast radius (out-of-boundary, protected-path, read-before-delete); promote its `(False, reason)` results that are *recoverable* to `ask` instead of `deny`; (b) probabilistic — an optional LLM-judge triage hook (Goose/Codex) that only routes ambiguous cases to the human.

### 4.4 Batching / queueing
For multi-agent runs, N agents × M tool calls = approval storm. Batch **medium-risk** approvals into one reviewable digest per agent turn (SOC alert-fatigue research: undifferentiated prompts cause batch rubber-stamping). Surface the **authorization object** — actor (which agent/subagent), concrete action, exact resource/scope, the diff/command, risk class, default timeout — not a bare tool name (counters scope-loss, evidence-loss, persuasion risk).

### 4.5 Async / remote approval (harden the existing handshake)
MassGen's `approval_request.json`→poll→`approval_response.json` is **functionally an awakeable** (Restate) / durable interrupt (LangGraph `interrupt()` + checkpointer). Harden it:
- **Durable timeout + default** (n8n Wait-node lesson): every `ask` carries a deadline; on expiry apply a configured default (**deny = fail-closed** for high-risk, per Hermes; configurable per-risk-tier).
- **Idempotent resume**: the chokepoint re-checks the approval cache before re-prompting (avoid double-asks if the run restarts mid-poll).
- **Three-action model** (MCP Elicitation): distinguish **accept / decline (explicit no → route alternative) / cancel (dismissed → re-prompt or fail-safe)** — don't collapse to a boolean.
- **Channel-portable** (OpenClaw): the JSON handshake already decouples request from responder; add an optional notifier (Slack/Discord `/approve <id>`) and out-of-band URL mode for any credential/OAuth flow (MCP URL-mode rule: secrets must never enter the LLM context).

### 4.6 Rule-learning
When a user picks "always," persist the *tool-suggested safe pattern* (opencode), not a blanket tool grant — and record it in the ledger so you can later *auto-propose* promotions ("you've approved `git status*` 20×; promote to allow?").

### 4.7 LLM-judge-as-approver
Use it strictly as **triage into the human queue** (Goose PermissionJudge / Codex auto_review / NeMo/Llama-Guard). Adversarial-guardrail evals show these are bypassable under prompt injection, so for delete/deploy/spend the **deterministic** `PathPermissionManager` + hardline blocklist + human approval still apply. The judge buys low fatigue; the policy layer buys safety.

---

## 5. Recommended MassGen Permission Architecture

A four-layer stack, each mapping onto an existing primitive, with the **fixed evaluation order** (Claude Code / Gemini model):

```
PreToolUse hooks (subprocess/python/policy)   →   ALREADY: GeneralHookManager
  → deny rules (any scope wins)               →   NEW: declarative rule layer over PatternHook
  → hardline blocklist (immune to bypass)     →   NEW (partial: dangerous-pattern list exists in PPM._validate_command_tool)
  → PathPermissionManager (boundary/perm)     →   ALREADY (promote recoverable denies → ask)
  → ask rules → RiskClassifier → approval     →   NEW classifier; PARTIAL approval (handshake exists, ask unwired)
  → permission mode (plan/normal/auto)        →   NEW: named modes
  → allow rules → SessionApprovalCache        →   NEW
  → SRT OS sandbox (per-agent profile)        →   ALREADY (add per-agent profiles + URL→net-allowlist unification)
  → [every decision] → ApprovalLedger         →   NEW
```

**Layer A — Declarative rule layer (NEW).** A YAML rule block (`permissions.allow/ask/deny`, Antigravity's `action(target)` algebra is the cleanest model: `command(...)`, `read_file(...)`, `write_file(...)`, `read_url(...)`, `mcp(server/tool)`, `*`) that the existing `GeneralHookManager.register_hooks_from_config` compiles into `PatternHook`s. Multi-scope precedence `managed > project > user > agent`, **deny-wins across scopes**. Gate project-scope loading on **trust** (Gemini/Codex). This is the biggest genuinely-missing piece: today rules are *imperative* Python hooks; users need *declarative* allow/ask/deny.

**Layer B — Wire `ask` to the approval handshake (PARTIAL → fix).** Add the missing `ask` branch at the chokepoint: pause, write the **authorization object** to `approval_request.json`, poll `approval_response.json` with a **durable timeout + per-risk default**, cache the grant (`once`/`session`/`always`). `HookResult.ask()` already exists and `GeneralHookManager.execute_hooks` already propagates `decision="ask"` — only the consumer is missing.

**Layer C — RiskClassifier + per-agent scoping (NEW).** A composable classifier (deterministic PPM signals + optional LLM-judge, max-severity à la OpenHands Ensemble) that maps each call to a risk tier and routes low→allow / medium→batch / high→interrupt. Reuse `GeneralHookManager`'s per-agent hook registration for **per-agent / per-subagent** rule sets (Amp `context`, Roo modes).

**Layer D — SRT per-agent + unified net allowlist (extend ALREADY-present).** Today SRT derives one filesystem policy from `PathPermissionManager`. Extend to **per-agent SRT profiles** (researcher = read-only + no net; implementer = workspace-write) and **compile declared `read_url(domain)` grants into SRT `allowedDomains`** (Antigravity) so app-layer and OS-layer net policy can't drift.

**Cross-cutting — ApprovalLedger + hardline floor (NEW).** Append-only JSONL (`run_id, agent_id, operator, authorization_object, decision, evidence_ptr, outcome`) for audit + rule-learning. Promote the existing `_validate_command_tool` dangerous-pattern list into a formal **hardline blocklist immune to any bypass mode** (Hermes/Claude).

### What's genuinely NEW vs already-present

| Capability | Status | Where it lands |
|---|---|---|
| deny/ask/allow chokepoint, glob PatternHook, YAML hooks, fail-open/closed | **ALREADY** | `GeneralHookManager` / `HookResult` |
| Per-path boundary, read-before-delete, protected paths, escape scan | **ALREADY** | `PathPermissionManager` |
| OS sandbox: fs allow/deny, net deny-all + allowlist, read modes | **ALREADY** | `SRT` manager |
| Interactive approval handshake (request/response JSON + TUI card) | **ALREADY (plumbing)** | interactive controller / MCP server |
| Per-agent hook registration | **ALREADY** | `GeneralHookManager.register_agent_hook` |
| `ask` decision actually pausing for human at the chokepoint | **NEW (gap — `ask` is a no-op today)** | chokepoint + handshake |
| Declarative allow/ask/deny rule layer + multi-scope deny-wins | **NEW** | config layer over `PatternHook` |
| RiskClassifier (gate on blast radius, not tool name) | **NEW** | composable PreToolUse hook |
| Risk-tiered escalation + batching of medium-risk | **NEW** | classifier + approval UX |
| Durable timeout + decline-vs-cancel + idempotent resume | **NEW (harden handshake)** | handshake |
| Append-only approval ledger + rule-learning | **NEW** | new artifact |
| `delegate`→external policy program (OPA/Cedar) | **NEW** | `SubprocessPolicyHook` subclass |
| Per-agent SRT profiles + URL→net-allowlist unification | **NEW (extend SRT)** | SRT manager |
| Named operating modes (plan / normal / auto) | **NEW** | session-level setting |
| Hardline blocklist immune to bypass | **NEW (partial)** | promote PPM dangerous-pattern list |
| Project-trust gating of repo-local config/hooks/rules | **NEW** | config loader |
| Resolved-binary-path allowlist + argv profiles | **NEW (hardens `_validate_command_tool`)** | PPM command validation |

**Low-confidence / flagged items:** opencode's `always`-persistence scope is *ambiguous* across sources (session vs SQLite). Antigravity CLI is *closed-source* — its hook internals are unverified beyond docs. Codex Linux sandbox is bwrap+seccomp per official docs (third-party "Landlock" claims are unverified/older). OpenHands' exact Invariant rule DSL could not be fetched authoritatively. Treat these as design *inspiration*, not implementation specs.

---

## 6. Sources (deduped, verified)

**Per-CLI permission docs**
- Claude Code: https://code.claude.com/docs/en/permissions · https://code.claude.com/docs/en/permission-modes · https://code.claude.com/docs/en/sandboxing · https://code.claude.com/docs/en/agent-sdk/permissions · https://code.claude.com/docs/en/agent-sdk/user-input · https://code.claude.com/docs/en/hooks
- Codex CLI: https://developers.openai.com/codex/config-reference · https://developers.openai.com/codex/agent-approvals-security · https://developers.openai.com/codex/concepts/sandboxing · https://developers.openai.com/codex/cli/reference · https://developers.openai.com/codex/rules · https://developers.openai.com/codex/hooks · https://developers.openai.com/codex/enterprise/managed-configuration · https://github.com/openai/codex/blob/main/docs/config.md
- Antigravity (agy): https://antigravity.google/docs/cli-permissions · https://antigravity.google/docs/ide-settings · https://antigravity.google/docs/cli-features · https://readysetcompute.com/antigravsec/ · https://antigravitylab.net/en/articles/antigravity/antigravity-command-approval-dialog-repeating-fix · https://github.com/google-antigravity/antigravity-cli
- opencode: https://opencode.ai/docs/permissions/ · https://opencode.ai/docs/plugins/ · https://opencode.ai/docs/tools/ · https://deepwiki.com/sst/opencode/5.2-permission-system · https://github.com/sst/opencode/pull/2148 · https://github.com/anomalyco/opencode/issues/7006 · https://github.com/sst/opencode/issues/5529
- OpenClaw: https://docs.openclaw.ai/ · https://open-claw.bot/docs/tools/exec-approvals/ · https://open-claw.bot/docs/gateway/sandboxing/ · https://deepwiki.com/openclaw/docs/2.3-security-and-sandboxing · https://raw.githubusercontent.com/openclaw/openclaw/main/docs/plugins/hooks.md · https://github.com/openclaw/openclaw
- Hermes Agent: https://hermes-agent.nousresearch.com/docs/user-guide/security/ · https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/security.md · https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/hooks.md · https://github.com/nousresearch/hermes-agent/blob/main/website/docs/reference/cli-commands.md · https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/configuration.md
- Gemini CLI: https://github.com/google-gemini/gemini-cli · https://geminicli.com/docs/reference/configuration/ · https://geminicli.com/docs/cli/trusted-folders/ · https://geminicli.com/docs/cli/sandbox/ · https://geminicli.com/docs/reference/policy-engine/ · https://github.com/google-gemini/gemini-cli/blob/main/docs/reference/policy-engine.md
- aider: https://aider.chat/docs/config/options.html · https://aider.chat/docs/config/aider_conf.html · https://aider.chat/docs/scripting.html · https://raw.githubusercontent.com/Aider-AI/aider/main/aider/io.py · https://github.com/Aider-AI/aider/issues/3903
- Sourcegraph Amp: https://ampcode.com/news/tool-level-permissions · https://ampcode.com/permissions · https://ampcode.com/manual · https://ampcode.com/manual/appendix/legacy-permissions-rules.txt · https://ampcode.com/news/mcp-permissions · https://embracethered.com/blog/posts/2025/amp-agents-that-modify-system-configuration-and-escape/
- Goose: https://goose-docs.ai/docs/guides/goose-permissions/ · https://deepwiki.com/block/goose/6.2-permission-modes-and-tool-approval · https://deepwiki.com/block/goose/6.1-permission-system-architecture · https://github.com/block/goose/blob/main/crates/goose-server/ALLOWLIST.md · https://goose-docs.ai/docs/guides/sandbox/
- Cline / Roo Code: https://docs.cline.bot/features/auto-approve · https://docs.cline.bot/features/cline-rules · https://cline.bot/blog/cline-v3-36-hooks · https://roocodeinc.github.io/Roo-Code/features/auto-approving-actions · https://roocodeinc.github.io/Roo-Code/features/custom-modes
- OpenHands: https://docs.openhands.dev/sdk/guides/security · https://docs.openhands.dev/openhands/usage/architecture/runtime · https://docs.openhands.dev/openhands/usage/run-openhands/cli-mode · https://github.com/OpenHands/OpenHands/blob/main/config.template.toml · https://arxiv.org/html/2511.03690v1

**HITL patterns & policy**
- LangGraph interrupts: https://docs.langchain.com/oss/python/langgraph/interrupts · https://www.langchain.com/blog/making-it-easier-to-build-human-in-the-loop-agents-with-interrupt
- OpenAI Agents SDK: https://openai.github.io/openai-agents-python/tools/ · https://openai.github.io/openai-agents-js/guides/human-in-the-loop/ · https://developers.openai.com/api/docs/guides/agents/guardrails-approvals · https://developers.openai.com/api/docs/guides/tools-connectors-mcp
- AutoGen: https://microsoft.github.io/autogen/0.2/docs/reference/agentchat/conversable_agent/
- Durable execution: https://docs.temporal.io/ai-cookbook/human-in-the-loop-python · https://temporal.io/blog/human-in-the-loop-approvals · https://docs.restate.dev/ai/patterns/human-in-the-loop · https://docs.n8n.io/integrations/builtin/app-nodes/n8n-nodes-base.slack/
- MCP Elicitation: https://modelcontextprotocol.io/specification/draft/client/elicitation
- Policy engines: https://natoma.ai/blog/mcp-access-control-opa-vs-cedar-the-definitive-guide · https://www.osohq.com/learn/opa-vs-cedar-vs-zanzibar · https://codilime.com/blog/why-use-open-policy-agent-for-your-ai-agents/
- Approvals-are-not-authorization & guardrails: https://blakecrosley.com/blog/ai-agent-approval-prompts-not-authorization · https://dl.acm.org/doi/10.1145/3723158 · https://arxiv.org/pdf/2402.01822 · https://arxiv.org/pdf/2406.02622 · https://arxiv.org/pdf/2502.15427

**MassGen primitives (verified in-repo)**
- `massgen/mcp_tools/hooks.py` (`GeneralHookManager`, `HookResult.ask/deny/allow`, `PatternHook`, `register_hooks_from_config`)
- `massgen/filesystem_manager/_path_permission_manager.py` (`pre_tool_use_hook`, boundary/permission checks, `_validate_command_tool` dangerous-pattern list, escape scan)
- `massgen/filesystem_manager/_srt_manager.py` (allowWrite/denyWrite/denyRead, read modes confined/strict/open, network deny-all + allowedDomains)
- `massgen/backend/base_with_custom_tool_and_mcp.py::_execute_tool_with_logging` (chokepoint — **`deny` handled, `ask` is a no-op**)
- `massgen/mcp_tools/hook_middleware.py` (PostToolUse file-IPC injection)
- `massgen/frontend/interactive_controller.py`, `massgen/cli/run.py` (interactive/approval flow)