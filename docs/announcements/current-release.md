# MassGen v0.1.94 Release Announcement (Parallelism Hardening)

<!--
This is the current release announcement. Copy this + feature-highlights.md to LinkedIn/X.
After posting, update the social links below.
-->

## Release Summary

We're excited to release MassGen v0.1.94 — Parallelism Hardening (Engineering Health)! 🚀 This release strengthens the orchestrator's parallel execution: we moved the per-round snapshot copy off the event loop so agents keep streaming concurrently, backed it with an immutable, versioned snapshot store that keeps the off-loop copy safe, and closed several latent concurrency races. No per-backend functionality changes — pure parallelism correctness and reliability.

## Install

```bash
pip install massgen==0.1.94
```

## Links

- **Release notes:** https://github.com/massgen/MassGen/releases/tag/v0.1.94
- **X post:** [TO BE ADDED AFTER POSTING]
- **LinkedIn post:** [TO BE ADDED AFTER POSTING]

## Posting Notes

- **Suggested image:** Use a screenshot of the v0.1.94 release notes.

---

## Full Announcement (for LinkedIn)

Copy everything below this line, then append content from `feature-highlights.md`:

---

We're excited to release MassGen v0.1.94 — Parallelism Hardening (Engineering Health)! 🚀 This release strengthens the orchestrator's parallel execution: it moves blocking snapshot work off the event loop so agents keep streaming concurrently, backs it with immutable versioned snapshots that keep the off-loop copy safe, and closes latent concurrency races. No per-backend functionality changes.

**Key Improvements:**

⚡ **Snapshot copy off the event loop**:
- The peer-context snapshot copy now runs its blocking `rmtree`/`copytree`/scrub on a worker thread via `asyncio.to_thread`
- One agent's snapshot copy no longer stalls every other agent's streaming

🔒 **Immutable, versioned snapshots**:
- Each agent's snapshot path is now a symlink to an immutable `.versions/<id>/v<N>` directory
- Writers publish a new version and atomically repoint the symlink; readers pin (refcount) the current version for the duration of their copy
- Eliminates the read-during-write race the off-loop copy would otherwise expose — no `FileNotFoundError`, no torn snapshots

🧵 **Concurrency correctness fixes**:
- Lost peer-answer revisions across the injection `await` window — fixed (revision counts captured at selection time)
- Lost background-subagent results from a blind queue `pop` — fixed (consume only the consumed ids)
- Leaked background trace tasks on cleanup, and a cancel-without-await teardown — fixed
- Worktree-isolation degradation is now surfaced (a swallowed `TypeError` previously hid it)

🧩 **Unified mid-stream injection**:
- The two large per-backend injection closures collapsed into one shared implementation; the background-wait interrupt provider was likewise deduplicated, removing backend-parity drift

**Install:**

```bash
pip install massgen==0.1.94
```

Release notes: https://github.com/massgen/MassGen/releases/tag/v0.1.94

Feature highlights:

<!-- Paste feature-highlights.md content here -->
