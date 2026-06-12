# MassGen v0.1.97 Release Announcement (Application-Layer Permission Engine)

<!--
This is the current release announcement. Copy this + feature-highlights.md to LinkedIn/X.
After posting, update the social links below.
-->

## Release Summary

MassGen v0.1.97 — an **application-layer permission engine** for agent tool calls! 🛡️ The companion to v0.1.96's OS sandbox: a fully opt-in pipeline of a hardline catastrophic-command floor, declarative `allow/ask/deny` rules, and a blast-radius risk classifier — resolving to allow / **ask** / deny. An `ask` is resolved by an automation policy (`risk-based`/`deny-all`/`allow-all`) or a file request/response handshake for headless/remote approval. Every decision is audited; per-agent roles scope each agent; a guardrail system prompt nudges the model to surface blocks rather than circumvent them. Presence-gated — no `permissions:` block means nothing changes.

## Install

```bash
pip install massgen==0.1.97
```

## Links

- **Release notes:** https://github.com/massgen/MassGen/releases/tag/v0.1.97
- **X post:** [TO BE ADDED AFTER POSTING]
- **LinkedIn post:** [TO BE ADDED AFTER POSTING]

## Posting Notes

- **Suggested image:** A terminal capture of an automation run where a denied call renders as a first-class failed tool row (`🔧 Calling execute_command(curl …) → ❌ Denied by automation policy: high-risk`), alongside an allowed low-risk call. Pairs well with the v0.1.96 sandbox image to tell the defense-in-depth story.

---

## Full Announcement (for LinkedIn)

Copy everything below this line, then append content from `feature-highlights.md`:

---

MassGen v0.1.97 — an application-layer permission engine for agent tool calls! 🛡️ Building on v0.1.96's OS sandbox, agents' tool calls now flow through a layered, opt-in approval pipeline — and you stay in the loop on the risky ones.

**Key Improvements:**

🧱 **Hardline + rules + risk** — a non-overridable catastrophic-command floor (`rm -rf /`, fork bombs), declarative `allow/ask/deny` rules over a small `action(target)` algebra (deny-wins), and a blast-radius classifier that auto-allows reads/in-workspace edits and asks only for the dangerous tail (egress, force-push, publish, privilege).

✋ **Approval that fits the run** — an `ask` resolves via an automation policy (`risk-based` / `deny-all` / `allow-all`) or a file request/response handshake for headless/remote approval (Slack bot, `/approve <id>`, …). Fail-closed by design.

🧑‍🤝‍🧑 **Per-agent roles + audit** — scope each agent with a `role` (e.g. `read-only`), which also empties its OS-sandbox writable set; every approval decision lands in an append-only JSONL audit ledger; a runaway-loop budget caps consecutive auto-approvals.

🧭 **Guardrail-aware prompt** — when permissions are on, the system prompt tells the model to follow blocks and surface-and-ask rather than circumvent them — while keeping `ask` a sanctioned path. (Honest scope: the prompt is best-effort alignment; the OS sandbox is the enforcement.)

**Install:**

```bash
pip install massgen==0.1.97
```

Feature highlights:

<!-- Paste feature-highlights.md content here -->
