# MassGen v0.1.91 Release Announcement

<!--
This is the current release announcement. Copy this + feature-highlights.md to LinkedIn/X.
After posting, update the social links below.
-->

## Release Summary

We're excited to release MassGen v0.1.91 — Config Reliability & Hook Safety! 🚀 This is a reliability pass for the config and hook paths that releases depend on. Coordination, timeout, and orchestrator runtime settings now go through centralized parsers; validation catches unknown YAML keys earlier; and strict mode turns those typos into release blockers. Checklist runtime controls use the same wiring, while Gemini/Codex standalone hooks respect nested protected paths before broader workspace write permissions.

## Install

```bash
pip install massgen==0.1.91
```

## Links

- **Release notes:** https://github.com/massgen/MassGen/releases/tag/v0.1.91
- **X post:** [TO BE ADDED AFTER POSTING]
- **LinkedIn post:** [TO BE ADDED AFTER POSTING]

## Posting Notes

- **Suggested image:** Use a screenshot of the v0.1.91 release notes.

---

## Full Announcement (for LinkedIn)

Copy everything below this line, then append content from `feature-highlights.md`:

---

We're excited to release MassGen v0.1.91 — Config Reliability & Hook Safety! 🚀 This is a reliability pass for the config and hook paths that releases depend on. Coordination, timeout, and orchestrator runtime settings now go through centralized parsers; validation catches unknown YAML keys earlier; and strict mode turns those typos into release blockers. Checklist runtime controls use the same wiring, while Gemini/Codex standalone hooks respect nested protected paths before broader workspace write permissions.

**Key Improvements:**

🧭 **Centralized Config Wiring**:
- `CoordinationConfig.from_dict()` now owns coordination YAML parsing
- `TimeoutConfig.from_dict()` now owns timeout setting parsing
- `AgentConfig.apply_orchestrator_config()` now owns top-level orchestrator runtime field application
- CLI helpers remain as compatibility wrappers around the centralized paths

🔎 **Config Drift Detection**:
- Unknown `orchestrator.coordination.*` keys now produce validation warnings
- Unknown top-level `orchestrator.*` and `timeout_settings.*` keys are also flagged
- `scripts/validate_all_configs.py --strict` treats those warnings as release-blocking

✅ **Checklist Runtime Controls**:
- `max_checklist_calls_per_round` now flows through the centralized orchestrator runtime helper
- `checklist_first_answer` is wired through the same path
- Documented planning and subagent timeout fields have parser coverage

🛡️ **Native Hook Permission Safety**:
- Gemini CLI and Codex standalone hook scripts now prefer more-specific managed paths
- Nested read-only and protected paths override broader writable parent directories
- Claude Code hook injection tests/docs now match the SDK-native `additionalContext` contract

🧪 **Tests**:
- New parser/validator parity coverage for coordination config, timeout settings, and top-level orchestrator runtime fields
- Strict config validation tests cover typo detection for release configs
- Native hook regression tests cover nested read-only precedence and protected-path enforcement

**Getting Started:**

```bash
pip install massgen==0.1.91
uv run massgen --config massgen/configs/features/fast_iteration.yaml "Create an svg of an AI agent coding."
```

Release notes: https://github.com/massgen/MassGen/releases/tag/v0.1.91

Feature highlights:

<!-- Paste feature-highlights.md content here -->
