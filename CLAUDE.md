# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

<!-- OPENSPEC:START -->
## OpenSpec Instructions

These instructions are for AI assistants working in this project.

Always open `@/openspec/AGENTS.md` when the request:
- Mentions planning or proposals (words like proposal, spec, change, plan)
- Introduces new capabilities, breaking changes, architecture shifts, or big performance/security work
- Sounds ambiguous and you need the authoritative spec before coding

Use `@/openspec/AGENTS.md` to learn:
- How to create and apply change proposals
- Spec format and conventions
- Project structure and guidelines

Keep this managed block so 'openspec update' can refresh the instructions.

<!-- OPENSPEC:END -->

## Planning
When planning or creating specs, use AskUserQuestions to ensure you align with the user before creating full planning files.

Also, please add a 'What's Next' section at the end of each plan. This will let us chain plans and clear context in a smart manner.

## Instruction File Parity

`CLAUDE.md` and `AGENTS.md` are required to stay identical in this repo.

- Pre-commit hook `sync-agent-instructions` auto-syncs them.
- If both files are edited differently in one change, resolve manually so they match exactly.

## Debugging Assumptions

**IMPORTANT**: When the user asks you to check logs from a MassGen run, assume they ran with the current uncommitted changes unless they explicitly say otherwise. Do NOT assume "the run used an older commit" just because the execution_metadata.yaml shows a different git commit - the user likely ran with local modifications after you suggested changes. Always debug the actual code behavior first.

## Implementation Guidelines

After implementing any feature that involves passing parameters through multiple layers (e.g., backend -> manager -> component), always verify the full wiring chain end-to-end by tracing the parameter from its origin to its final usage site. Do not rely solely on unit tests passing -- add an integration smoke test or assertion that the parameter actually arrives at its destination, not just that the downstream logic works when the parameter is provided.

For cross-backend tool-calling behavior (OpenAI-compatible, Claude, Gemini, Codex/Claude Code via MCP, etc.), treat backend-side argument normalization and schema validation as the source of truth. Prompt guidance can encourage correct argument shape, but correctness must not depend on prompt compliance alone (e.g., tolerate/detect accidentally stringified JSON argument payloads in adapters and tool gateways).

When fixing `E501` in prompt text (especially triple-quoted system prompts), preserve the rendered prompt exactly. Wrap long source lines using escaped line continuation (`\` at end-of-line) so lint passes without introducing extra newline characters or changing prompt behavior.

## Anti-Patterns

- **No keyword/heuristic matching for categorization or similarity.** Avoid writing code that infers categories, detects similarity, or organizes content using keyword lists, Jaccard similarity, Levenshtein distance, or similar heuristics. These approaches are brittle and produce low-quality results. Use LLM-based approaches instead -- that's the whole point of this project.
- **No explicit tool call syntax in prompts.** Do not hardcode specific tool/function call syntax (e.g., `tool_name(param="value")`) in system prompts, skill instructions, or user-facing text. Models determine the correct calling convention from tool schemas. Describe what the agent should do in natural language instead. Hardcoded syntax is fragile across providers and couples prompts to implementation details.

## Test-Driven Development (TDD)

**TDD is the default development methodology for this project.** With 121 test files and 1580+ tests across unit, integration, frontend, and snapshot layers, the test infrastructure is mature. All non-trivial work MUST follow the TDD cycle.

### The TDD Contract

For every non-trivial change (bug fix, new feature, refactor, backend change, TUI work, WebUI work), follow this sequence **in order**:

1. **Agree on acceptance tests first.** Before writing any production code, align with the user on what tests will prove the change works. Define pass/fail criteria explicitly.
2. **Write the tests.** Implement or update tests that express the desired behavior. These tests MUST fail initially -- if they pass before you write production code, either the tests are wrong or the feature already exists.
3. **Confirm tests fail for the right reason.** Run the tests and verify they fail because the feature/fix is missing, not because of a test bug.
4. **Implement the minimum code to pass.** Write production code until the test suite passes. Do not add untested behavior.
5. **Refactor under green.** Clean up only while all tests remain green.
6. **Commit tests alongside code.** Tests are not throwaway scaffolding -- they are permanent regression protection.

### When to Apply TDD

| Change Type | TDD Required? | Rationale |
|-------------|:---:|-----------|
| New feature / capability | **Yes** | Define behavior before implementing it |
| Bug fix | **Yes** | Write a test that reproduces the bug first |
| Backend changes | **Yes** | Test across affected backends |
| TUI behavior changes | **Yes** | Use snapshot, golden, or event pipeline tests |
| WebUI changes | **Yes** | Vitest unit + Playwright E2E as appropriate |
| Refactoring | **Yes** | Ensure existing tests pass before AND after |
| Config/YAML changes | **Yes** | Validate with config validation tests |
| Trivial one-liner fixes (typos, imports) | No | Use judgment -- but when in doubt, test |

### What "Non-Trivial" Means

If you're tempted to skip tests, ask: *"Could this break silently?"* If the answer is anything other than a confident "no," write a test. Specifically:
- Any change touching `orchestrator.py`, `chat_agent.py`, `backend/*.py`, `mcp_tools/`, or `coordination_tracker.py` is always non-trivial.
- Any change to TUI widgets, content handlers, or event processing is always non-trivial.
- Any change to system prompts, config validation, or YAML parsing is always non-trivial.

### Test Placement

| Test Type | Location | When to Use |
|-----------|----------|-------------|
| Unit tests | `massgen/tests/` or `massgen/tests/unit/` | Isolated logic, single-component |
| Integration tests | `massgen/tests/integration/` | Multi-component orchestration flows |
| Frontend/TUI tests | `massgen/tests/frontend/` | Widget, snapshot, golden transcript |
| WebUI tests | `webui/src/**/*.test.ts` | Store, component, E2E |

### Anti-Patterns (Do NOT Do These)

- **Implement first, test later.** This inverts the TDD cycle and leads to tests that confirm what was written rather than what was intended.
- **Skip tests "because it's small."** Small changes cause big regressions. The test suite exists to catch exactly these.
- **Write tests that always pass.** A test that can't fail is not a test. Always verify the red-green cycle.
- **Test only the happy path.** Cover edge cases, error conditions, and boundary values.
- **Rely on manual testing.** If you tested it by running `massgen --automation`, also encode that expectation as an automated test.

### Reference

Full testing strategy, marker model, CI gates, and layer definitions: `docs/modules/testing.md`

## Project Overview

MassGen is a multi-agent system that coordinates multiple AI agents to solve complex tasks through parallel processing, intelligence sharing, and consensus building. Agents work simultaneously, observe each other's progress, and vote to converge on the best solution.

### Design Principles: The Quality Matrix

MassGen's strength comes from two orthogonal dimensions working together:

|                        | **Parallel** (same task, N agents) | **Decomposition** (subtasks, owned) |
|------------------------|------------------------------------|-------------------------------------|
| **Enforcing Refinement** | Agents iterate until quality is genuinely achieved, not just adequate | Each subtask owner refines until their piece meets quality gates |
| **Ensuring Depth in Roles** | Strong personas give agents distinct creative visions, producing diverse high-quality attempts | Persona specialization ensures deep domain fit per subtask |

- **Enforcing refinement** (currently: checklist-gated voting, gap analysis, improvements echo) = controls *how much* agents iterate and ensures each iteration is *worth it*. Multiple agents are key here: each round's evaluator sees all agents' prior answers, can identify unique strengths across them, and synthesizes the best elements into the next attempt. Without refinement, agents settle for "good enough."
- **Ensuring depth in roles** = persona/role generation that gives agents strong opinionated visions. A bare user prompt is rarely enough for quality output -- the persona fills in the creative direction. Consider using a preliminary MassGen call to generate rich personas/briefs before the main execution run.

Neither dimension alone is sufficient. Refinement without strong roles produces polished mediocrity. Strong roles without refinement produces ambitious first drafts that never mature.

## Essential Commands

All commands use `uv run` prefix:

```bash
# Run tests
uv run pytest massgen/tests/                           # All tests
uv run pytest massgen/tests/test_specific.py -v        # Single test file
uv run pytest massgen/tests/test_file.py::test_name -v # Single test

# Run MassGen (ALWAYS use --automation for programmatic execution)
uv run massgen --automation --config [config.yaml] "question"

# Build documentation
cd docs && make html                    # Build docs
cd docs && make livehtml                # Auto-reload dev server at localhost:8000

# Pre-commit checks
uv run pre-commit run --all-files

# Validate all configs
uv run python scripts/validate_all_configs.py

# Build Web UI (required after modifying webui/src/*)
cd webui && npm run build
```

## Architecture Overview

Core flow, key components, backend hierarchy, agent statelessness, and TUI design principles. Full guide: `docs/modules/architecture.md`.

```text
cli.py -> orchestrator.py -> chat_agent.py -> backend/*.py
                |
        coordination_tracker.py (voting, consensus)
                |
        mcp_tools/ (tool execution)
```

```text
base.py (abstract interface)
    +-- base_with_custom_tool_and_mcp.py (tool + MCP support)
            |-- response.py (OpenAI Response API)
            |-- chat_completions.py (generic OpenAI-compatible)
            |-- claude.py (Anthropic)
            |-- claude_code.py (Claude Code SDK)
            |-- gemini.py (Google)
            +-- grok.py (xAI)
```

## Backend Parity (Critical)

When adding framework tooling capabilities (for example custom-tool lifecycle, background execution, or MCP behavior), do not assume one backend implementation covers all backends.

- `base_with_custom_tool_and_mcp.py` changes cover its inheritors (`response`, `chat_completions`, `claude`, `gemini`, `grok`), but **not** native backends like `claude_code.py` and `codex.py`.
- `claude_code.py` has its own SDK MCP wrapping path and requires explicit wiring for new framework custom tools.
- `codex.py` relies on `massgen/mcp_tools/custom_tools_server.py` + `.codex/custom_tool_specs.json`; new custom/background capabilities must be wired through that path explicitly.
- Any non-trivial tooling feature should add backend parity tests for at least: one `base_with_custom_tool_and_mcp` backend, `claude_code`, and `codex`.
- **Workspace metadata directories**: Backends that create config directories in the workspace (e.g., `.codex/` for Codex) must add those directory names to the `_metadata_dirs` set in `FilesystemManager.save_snapshot()`'s `has_meaningful_content()` helper (`massgen/filesystem_manager/_filesystem_manager.py`). Otherwise, these metadata-only directories cause the final snapshot to copy a near-empty workspace instead of falling back to `snapshot_storage` with the real deliverables. Current exclusions: `.git`, `.codex`, `.massgen`, `memory`.

## Configuration

YAML configs in `massgen/configs/` define agent setups. Structure:
- `basic/` - Simple single/multi-agent configs
- `tools/` - MCP, filesystem, code execution configs
- `providers/` - Provider-specific examples
- `teams/` - Pre-configured specialized teams

When adding new YAML parameters, update **both**:
- `massgen/backend/base.py` -> `get_base_excluded_config_params()`
- `massgen/api_params_handler/_api_params_handler_base.py` -> `get_base_excluded_config_params()`

When adding new **coordination** YAML parameters (under `orchestrator.coordination`), update **all three**:
- `massgen/agent_config.py` -> `CoordinationConfig` dataclass field
- `massgen/cli/config_parsing.py` -> `_parse_coordination_config()` (must explicitly map the key or it silently defaults to `False`)
- `massgen/agent_config.py` -> `to_dict()` if the field needs to serialize back

## Workflow Guidelines

1. **TDD is the default.** Every non-trivial task starts with tests. See the [TDD section above](#test-driven-development-tdd) for the full contract. Do not skip this -- if you find yourself writing production code before tests, stop and reverse course.
2. **Run tests early and often.** After each meaningful code change, run the relevant test subset. Do not batch up changes and test at the end.
3. **Keep PR_DRAFT.md updated** - Create a PR_DRAFT.md that references each new feature with corresponding Linear (e.g., `Closes MAS-XXX`) and GitHub issue numbers. Keep this updated as new features are added. You may need to ask the user whether to overwrite or append to this file. Ensure you include test cases here as well as configs used to test them.
4. **Review PRs** with `pr-checks` skill.
5. **Git staging**: Use `git add -u .` for modified tracked files

## Documentation Requirements

Documentation must be consistent with implementation, concise, and usable. Full guide with per-PR tables, quality standards, and file locations: `docs/modules/documentation.md`.

## Registry Updates

Checklists for adding new models and new YAML parameters. Full guide: `docs/modules/registry.md`. Key rule: when adding YAML params, update both `base.py` and `_api_params_handler_base.py` exclusion lists.

## Code-Based Tools and FRAMEWORK_MCPS

When `enable_code_based_tools` is on (CodeAct paradigm), MCP tools are converted to Python wrapper scripts that agents call via filesystem execution — **unless** the MCP server name is in `FRAMEWORK_MCPS` (`massgen/filesystem_manager/_constants.py`). Framework MCPs stay as direct protocol tools sent to the model.

**When adding a new MCP server that must be called directly by the model** (not via code execution), add its server name to `FRAMEWORK_MCPS`. If you forget, the tool will silently work but only through the code-based path — the model won't see it as a native tool call. This is critical for tools like `massgen_checklist` where the orchestrator depends on the tool result to control agent flow.

## CodeRabbit Integration

Automated PR reviews via CodeRabbit. Full guide: `docs/modules/code_review.md`. Quick command: `coderabbit --prompt-only`.

## Custom Tools

Tools in `massgen/tool/` require `TOOL.md` with YAML frontmatter:
```yaml
---
name: tool-name
description: One-line description
category: primary-category
requires_api_keys: [OPENAI_API_KEY]  # or []
tasks:
  - "Task this tool can perform"
keywords: [keyword1, keyword2]
---
```

Docker execution mode auto-excludes tools missing required API keys.

## Testing Notes

Full testing strategy, markers, commands, snapshot workflow, and backend testing patterns: `docs/modules/testing.md`.

```bash
# Fast local suite (PR gate)
uv run pytest massgen/tests --run-integration -m "not live_api and not docker and not expensive" -q --tb=short

# Just unit tests
uv run pytest massgen/tests/ -q --tb=short

# Integration tests (deterministic, non-costly)
uv run pytest massgen/tests/integration -q
```

Markers: `@pytest.mark.integration` (opt-in: `--run-integration`), `@pytest.mark.live_api` (opt-in: `--run-live-api`), `@pytest.mark.expensive`, `@pytest.mark.docker`, `@pytest.mark.asyncio`.

### AI Test Run Protocol (Required)

When running pytest as an AI agent, always capture full output to a log and print explicit completion markers. This prevents accidental duplicate reruns caused by partial/streamed output.

```bash
# Run once and emit explicit completion markers
uv run pytest massgen/tests/ -q --tb=short -ra --color=no > /tmp/pytest_ai.log 2>&1
rc=$?
echo "__PYTEST_EXIT_CODE:$rc"
echo "__PYTEST_LOG:/tmp/pytest_ai.log"

# Return concise but fully explainable output
tail -n 80 /tmp/pytest_ai.log
rg -n "^(FAILED|ERROR) " /tmp/pytest_ai.log | tail -n 20
```

Interpretation rules:
- `__PYTEST_EXIT_CODE:0` means pytest completed successfully.
- Any non-zero exit code means pytest completed with failures/errors (not "still running").
- Never use `pytest ... | grep ...` as the primary execution command, since it can hide context and make completion detection unreliable.

## Key Files for New Contributors

- Entry point: `massgen/cli/` package (console script `massgen.cli:cli_main`; argparse in `massgen/cli/entrypoint.py`)
- Coordination logic: `massgen/orchestrator.py`
- Agent implementation: `massgen/chat_agent.py`
- Backend interface: `massgen/backend/base.py`
- Config validation: `massgen/config_validator.py`
- Model registry: `massgen/utils.py`

## Module Documentation

Detailed documentation for specific modules lives in `docs/modules/`. **Always check these before working on a module, and update them when making changes.**

- `docs/modules/architecture.md` - Core flow, key components, backend hierarchy, agent statelessness, TUI design principles
- `docs/modules/testing.md` - Testing strategy, TDD contract, CI gates, markers, backend testing, TUI/WebUI test architecture
- `docs/modules/documentation.md` - Per-PR documentation requirements, quality standards, file locations
- `docs/modules/registry.md` - Adding new models, adding new YAML parameters
- `docs/modules/code_review.md` - CodeRabbit integration, CLI options, PR commands
- `docs/modules/skills.md` - Skill discovery, creation, improvement
- `docs/modules/release.md` - GitHub Actions automation, release-prep, announcements, full release process
- `docs/modules/subagents.md` - Subagent spawning, logging architecture, TUI integration
- `docs/modules/interactive_mode.md` - Interactive mode architecture, launch_run MCP, system prompts, project workspace
- `docs/modules/worktrees.md` - Worktree lifecycle, branch naming, scratch archives, system prompt integration
- `docs/modules/composition.md` - **Composable primitives, phase architecture, domain-specific checklist gates** — how personas, eval criteria, decomposition, and planning compose for maximum quality
- `docs/modules/checkpoint.md` - **Checkpoint coordination mode** — tool schema, fresh agent instantiation, state save/restore, workspace propagation, WebUI behavior
- `docs/modules/coordination_workflow.md` - **Round lifecycle and checklist workflow** — the implement → evaluate → submit cycle, when to call `submit_checklist` vs `new_answer`, and why agents must not re-evaluate within a round

## MassGen Skills

Specialized skills in `massgen/skills/` for common workflows. Full guide: `docs/modules/skills.md`. Symlink to `.claude/skills/` for discovery.

## Linear Integration

This project uses Linear for issue tracking.

### Setup (if Linear tools unavailable)

If `mcp__linear-server__*` tools aren't available:

```bash
claude mcp add --transport http linear-server https://mcp.linear.app/mcp
```

### Feature Workflow

1. **Create Linear issue first** -> `mcp__linear-server__create_issue`
2. **For significant changes** -> Create OpenSpec proposal referencing the issue
3. **Implement** -> Reference issue ID in commits
4. **Update status** -> `mcp__linear-server__update_issue`

This ensures features are tracked in Linear and spec'd via OpenSpec before implementation.

*Note*: When using Linear, ensure you use the MassGen project and prepend '[FEATURE]', '[DOCS]', '[BUG]', or '[ROADMAP]' to the issue name. By default, set issues as 'Todo'.

## Release Workflow

Automated GitHub Actions, release-prep skill, announcement files, and full release process. Full guide: `docs/modules/release.md`. Quick command: `release-prep v0.1.XX`.
