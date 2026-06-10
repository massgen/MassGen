# MassGen v0.1.97 Roadmap

**Target Release:** TBD

## Overview

Version 0.1.97 picks up the image/video edit work deferred from v0.1.86-v0.1.96 and continues multimodal provider-parity work.

---

## Feature: Image/Video Edit Capabilities (Deferred from v0.1.86-v0.1.96)

**Issue:** [#959](https://github.com/massgen/MassGen/issues/959)
**Owner:** @ncrispino

### Goals

- **Edit Capability Coverage**: Investigate and support image and video editing capabilities across providers
- **Multi-Turn Editing**: Multi-turn editing workflows with continuation IDs
- **Provider Parity**: Document which providers support generation, editing, continuation, and media input/output combinations

### Success Criteria

- [ ] Image editing capabilities documented and tested
- [ ] Video editing capabilities documented and tested
- [ ] Multi-turn editing flow works end-to-end
- [ ] Provider capability notes are updated where users discover multimodal examples

---

## Related Tracks

- **v0.1.96**: OS-Level Agent Sandboxing — `command_line_execution_mode: srt` wraps agent command/code execution in Anthropic's sandbox-runtime (bubblewrap/Seatbelt) with OS-enforced filesystem + network isolation derived from the same `PathPermissionManager` policy as the app layer (defense in depth), configurable read confinement (default `confined`), and a hardened key-agnostic permission-hook escape scan
- **v0.1.95**: Steering Improvements — programmatic steering inbox (`--inbox-dir`) routed to the shared `set_pending_input` chokepoint, mid-round interrupt-and-resume for Codex and Antigravity (`codex exec resume` / `agy --continue`), MCP-server-hook payload IPC for Antigravity (codex parity), and the Antigravity `--model` flag wired through
- **v0.1.94**: Parallelism Hardening (engineering health) — snapshot copy moved off the event loop with immutable versioned snapshots, lock-free concurrency-race fixes, unified mid-stream injection, and worktree-isolation degradation surfaced
- **v0.1.93**: CLI package decomposition and pydantic config migration — focused `massgen/cli/` package, construction-time config validation with `Literal`-typed modes, single-source exclusion lists, dead-code removal, and test-signal/type-checking hardening
- **v0.1.92**: Orchestrator collaborator refactor and Parallel Search MCP — 49 collaborator extractions, Textual display helper split, characterization coverage, and a Parallel hosted search example
- **v0.1.91**: Config reliability and hook safety — centralized config parsing, strict unknown-key validation, checklist runtime control wiring, and nested native-hook permission precedence
- **v0.1.90**: Discriminative criteria refinements and checklist calibration — score-spread pruning, per-criterion feedback, position-bias counterbalancing, unified checklist gate, and shared score utilities
- **v0.1.89**: Antigravity CLI full integration and hardening — workflow-mode parity, auth checks, workspace project anchoring, standalone hooks.json, and prompt affordance gating
- **v0.1.88**: Antigravity CLI backend wrapping Google's `agy` binary, with workspace-local `.antigravity/` config isolation and runnable Antigravity examples

## What's Next

- Continued multimodal expansion and provider parity
- Further quality-loop ergonomics for long-running multi-agent refinement
