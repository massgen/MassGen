# MassGen v0.1.95 Release Announcement (Mid-Stream Steering)

<!--
This is the current release announcement. Copy this + feature-highlights.md to LinkedIn/X.
After posting, update the social links below.
-->

## Release Summary

We're excited to release MassGen v0.1.95 — Mid-Stream Steering! 🚀 This release lets a human (or any UI-less caller) drop guidance into an agent *while it is streaming*: over a file inbox in `--automation`, or through the MCP-middleware hook path. Codex and Antigravity now interrupt the in-flight turn, fold the steering in, and resume — instead of waiting for a round boundary. The injection chokepoint stays shared across the TUI, WebUI, and the new headless path.

## Install

```bash
pip install massgen==0.1.95
```

## Links

- **Release notes:** https://github.com/massgen/MassGen/releases/tag/v0.1.95
- **X post:** [TO BE ADDED AFTER POSTING]
- **LinkedIn post:** [TO BE ADDED AFTER POSTING]

## Posting Notes

- **Suggested image:** A TUI screenshot of a mid-stream steering moment — agent streaming, a steering message landing, the agent visibly changing course. (Headless file-inbox half isn't TUI-visible; cover it in text.)

---

## Full Announcement (for LinkedIn)

Copy everything below this line, then append content from `feature-highlights.md`:

---

We're excited to release MassGen v0.1.95 — Mid-Stream Steering! 🚀 You can now steer agents *mid-thought*: drop a message into a running agent and have it fold the guidance in and keep going — no restart, no waiting for a round boundary, and no UI required.

**Key Improvements:**

📨 **Programmatic steering inbox (`--inbox-dir`)**:
- `send_steering_message()` drops a message into a caller-known inbox; the orchestrator routes it to the same `set_pending_input` chokepoint the TUI and WebUI use
- Reachable from `--automation` and any UI-less caller, with per-message targeting (one agent / a subset / broadcast)

⏯️ **Interrupt-and-resume steering (Codex & Antigravity)**:
- Steering mid-turn kills the in-flight turn and resumes (`codex exec resume` / `agy --continue`) instead of waiting for a round boundary
- Antigravity promotes pre-interrupt deliverables first, so work isn't lost

🪝 **MCP-hook injection parity**:
- Antigravity gains codex-parity mid-stream injection through the MCP middleware, with `expires_at`-guarded payloads
- The Antigravity `--model` flag is now actually wired through

🔧 **Reliability fixes**:
- `--inbox-dir` now honored for resumed sessions (`--session-id` / `--continue`), stale steering can't carry forward past `expires_at`, and watcher failures are logged instead of swallowed

**Install:**

```bash
pip install massgen==0.1.95
```

Release notes: https://github.com/massgen/MassGen/releases/tag/v0.1.95

Feature highlights:

<!-- Paste feature-highlights.md content here -->
