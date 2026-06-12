# MassGen v0.1.96 Release Announcement (OS-Level Agent Sandboxing)

<!--
This is the current release announcement. Copy this + feature-highlights.md to LinkedIn/X.
After posting, update the social links below.
-->

## Release Summary

MassGen v0.1.96 — OS-Level Agent Sandboxing! 🚀 Agents that run commands can now be confined at the OS level via Anthropic's [sandbox-runtime](https://github.com/anthropic-experimental/sandbox-runtime) (`srt`), with a hardened permission hook on top. Defense in depth: OS and app layers from the same path policy, both active. Default-off, one knob (`command_line_execution_mode: srt`).

## Install

```bash
pip install massgen==0.1.96
```

## Links

- **Release notes:** https://github.com/massgen/MassGen/releases/tag/v0.1.96
- **X post:** [TO BE ADDED AFTER POSTING]
- **LinkedIn post:** [TO BE ADDED AFTER POSTING]

## Posting Notes

- **Suggested image:** A terminal screenshot of the `srt_sandbox.yaml` demo run — agent writes to its workspace successfully, then an out-of-workspace read (`~/.ssh/id_rsa`) and network egress are both denied with `Operation not permitted`. This is a headless/security feature, so a clean before/after terminal capture beats a TUI screenshot.

---

## Full Announcement (for LinkedIn)

Copy everything below this line, then append content from `feature-highlights.md`:

---

MassGen v0.1.96 — OS-Level Agent Sandboxing! 🚀 Agents that run commands can now be confined at the OS level, not just by MassGen's permission layer. Both layers derive from the same path policy and stay active together, closing the shell and file-tool escape hatches at once. Default-off, opt-in with a single knob.

**Key Improvements:**

🛡️ **OS-level execution sandbox** — `command_line_execution_mode: srt` wraps agent command/code execution in Anthropic's sandbox-runtime (bubblewrap on Linux, Seatbelt on macOS) for OS-enforced filesystem + network isolation, derived from the same permission policy as the app layer. Network is deny-all by default.

🔒 **Configurable read confinement** — by default (`confined`), sandboxed commands can't read your `$HOME` (secrets, other projects), only the workspace + context, while system paths stay readable so commands still run.

🧱 **Hardened permission hook** — a key-agnostic scan walks the full tool-args tree and denies any path resolving outside managed areas, closing prior fail-open gaps with no false positives.

**Install:**

```bash
pip install massgen==0.1.96
```

Feature highlights:

<!-- Paste feature-highlights.md content here -->
