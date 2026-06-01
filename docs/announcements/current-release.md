# MassGen v0.1.92 Release Announcement

<!--
This is the current release announcement. Copy this + feature-highlights.md to LinkedIn/X.
After posting, update the social links below.
-->

## Release Summary

We're excited to release MassGen v0.1.92 — Orchestrator Collaborator Refactor & Parallel Search MCP! 🚀 This release takes a cleanup-heavy step toward a smaller, easier-to-test orchestration core. The monolithic orchestrator has been split into 49 lazy collaborators while preserving existing public call sites, TUI display helpers moved into focused sibling modules, and characterization tests now pin the extraction seams. It also adds a Parallel Web Search MCP example for LLM-optimized research workflows.

## Install

```bash
pip install massgen==0.1.92
```

## Links

- **Release notes:** https://github.com/massgen/MassGen/releases/tag/v0.1.92
- **X post:** [TO BE ADDED AFTER POSTING]
- **LinkedIn post:** [TO BE ADDED AFTER POSTING]

## Posting Notes

- **Suggested image:** Use a screenshot of the v0.1.92 release notes.

---

## Full Announcement (for LinkedIn)

Copy everything below this line, then append content from `feature-highlights.md`:

---

We're excited to release MassGen v0.1.92 — Orchestrator Collaborator Refactor & Parallel Search MCP! 🚀 This release takes a cleanup-heavy step toward a smaller, easier-to-test orchestration core. The monolithic orchestrator has been split into 49 lazy collaborators while preserving existing public call sites, TUI display helpers moved into focused sibling modules, and characterization tests now pin the extraction seams. It also adds a Parallel Web Search MCP example for LLM-optimized research workflows.

**Key Improvements:**

🧩 **Orchestrator Collaborator Extraction**:
- `orchestrator.py` dropped from 21,599 to 8,574 lines
- 49 collaborators now live under `massgen/orchestrator_collaborators/`
- Thin delegator methods keep existing internal and external call sites working
- Collaborators use lazy cached properties so `Orchestrator.__new__` test fixtures still work

🖥️ **TUI Display Module Cleanup**:
- `textual_terminal_display.py` now delegates provider/model helpers, terminal capability probing, and widget-debug helpers to focused sibling modules
- Public TUI exports remain stable for existing imports

🔎 **Parallel Web Search MCP**:
- New `parallel_search` server registry entry
- New runnable example at `massgen/configs/tools/web-search/parallel_search_example.yaml`
- Supports anonymous exploratory use, with optional `PARALLEL_API_KEY` for higher rate limits

🧪 **Characterization Safety Net**:
- 77 new characterization cases pin public contracts and extraction seams
- Existing monkeypatch/mock seams were repointed to collaborator locations without deleting tests or weakening assertions
- The refactor roadmap and remaining high-risk follow-up work are documented in `docs/dev_notes/orchestrator_refactor_roadmap.md`

**Getting Started:**

```bash
pip install massgen==0.1.92
uv run massgen --config massgen/configs/tools/web-search/parallel_search_example.yaml "Research the latest advances in multi-agent AI systems"
```

Release notes: https://github.com/massgen/MassGen/releases/tag/v0.1.92

Feature highlights:

<!-- Paste feature-highlights.md content here -->
