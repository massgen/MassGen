# MassGen v0.1.92 Roadmap

**Target Release:** May 29, 2026

## Overview

Version 0.1.92 picks up the image/video edit work deferred from v0.1.86-v0.1.91 and continues multimodal provider-parity work.

---

## Feature: Image/Video Edit Capabilities (Deferred from v0.1.86-v0.1.91)

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

- **v0.1.91**: Config reliability and hook safety — centralized config parsing, strict unknown-key validation, checklist runtime control wiring, and nested native-hook permission precedence
- **v0.1.90**: Discriminative criteria refinements and checklist calibration — score-spread pruning, per-criterion feedback, position-bias counterbalancing, unified checklist gate, and shared score utilities
- **v0.1.89**: Antigravity CLI full integration and hardening — workflow-mode parity, auth checks, workspace project anchoring, standalone hooks.json, and prompt affordance gating
- **v0.1.88**: Antigravity CLI backend wrapping Google's `agy` binary, with workspace-local `.antigravity/` config isolation and runnable Antigravity examples
- **v0.1.87**: Documentation — framework comparison pages (CrewAI, LangGraph, AutoGen) and `llms.txt` index ([#1094](https://github.com/massgen/MassGen/pull/1094)); plus a one-line `refine=False` fix for the `bootstrap_subagent` discriminator
- **v0.1.86**: Functional `bootstrap_subagent` discriminator and Codex MCP approval fix
- **v0.1.85**: Discriminative Criteria Emergence (`criteria_mode`) — `bootstrap_inline` and accumulator infrastructure

## What's Next

- Continued multimodal expansion and provider parity
- Further quality-loop ergonomics for long-running multi-agent refinement
