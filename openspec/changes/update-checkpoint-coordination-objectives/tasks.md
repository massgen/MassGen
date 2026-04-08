## 1. OpenSpec
- [x] 1.1 Update proposal.md — extend, not replace; standalone-first; subprocess confirmed
- [x] 1.2 Rewrite design.md — mode dispatch, I/O schema, RecoveryNode, constraint semantics, standalone MCP API, global safety policy
- [x] 1.3 Rewrite spec.md — objective mode requirements, auto-provided context, subprocess model, no writeback
- [x] 1.4 Update docs/modules/checkpoint.md — both modes documented, lifecycle corrected, standalone MCP section added
- [ ] 1.5 Validate with `openspec validate update-checkpoint-coordination-objectives --strict`

## 2. Standalone MCP Server (First Priority)

### Tests First
- [ ] 2.1 Write failing test: `init` stores workspace_dir, trajectory_path, available_tools in server session state
- [ ] 2.2 Write failing test: `checkpoint` without prior `init` returns a clear error
- [ ] 2.3 Write failing test: `checkpoint(objective=...)` launches subprocess with correct config (workspace, trajectory, tools injected)
- [ ] 2.4 Write failing test: output matches `{criteria_applied, plan}` schema — each step has description, optional constraints, optional approved_action, optional recovery
- [ ] 2.5 Write failing test: `approved_action` present only on steps where a constraint would otherwise block the capability
- [ ] 2.6 Write failing test: RecoveryNode terminals are one of `proceed`, `recheckpoint`, `refuse`
- [ ] 2.7 Write failing test: installed console script `massgen-checkpoint-mcp` is present after `pip install`

### Implementation
- [ ] 2.8 Add `massgen/mcp_tools/standalone/checkpoint_mcp_server.py` — `init` + `checkpoint` tools
- [ ] 2.9 Wire `trajectory_path` read into subprocess config generation
- [ ] 2.10 Wire `available_tools` into subprocess config so checkpoint agents receive the tool list
- [ ] 2.11 Add `checkpoint` tool schema: `objective` (required), `action_goals`, `eval_criteria`
- [ ] 2.12 Add output normalization: validate and return `criteria_applied` + `plan` structure
- [ ] 2.13 Add `pyproject.toml` console script entry: `massgen-checkpoint-mcp`
- [ ] 2.14 Document Claude Code setup path: `claude mcp add ... -- massgen-checkpoint-mcp`

## 3. Global Safety Policy

### Tests First
- [ ] 3.1 Write failing test: `eval_criteria` in checkpoint call augments policy, does not replace it
- [ ] 3.2 Write failing test: `criteria_applied` in output contains both policy entries and per-call criteria

### Implementation
- [ ] 3.3 Define global safety policy YAML structure under `orchestrator.coordination.checkpoint.policy`
- [ ] 3.4 Add default baseline policy (no destructive ops without backup, no prod deploy without passing tests)
- [ ] 3.5 Update `CoordinationConfig` dataclass and `_parse_coordination_config()` for policy field
- [ ] 3.6 Inject policy into checkpoint subprocess config so agents receive it

## 4. Objective Mode Output Shape

### Tests First
- [ ] 4.1 Write failing test: plan step with constraints + approved_action — approved_action is the only permitted exception
- [ ] 4.2 Write failing test: plan step with constraints and no approved_action — capability is fully blocked
- [ ] 4.3 Write failing test: RecoveryNode is correctly recursive — `then`/`else` can be nodes or terminals
- [ ] 4.4 Write failing test: no top-level `approved_actions` list in output

### Implementation
- [ ] 4.5 Add output schema validation for `criteria_applied`, `plan`, RecoveryNode
- [ ] 4.6 Add system prompt section for checkpoint agents describing the expected output shape

## 5. MassGen-Internal Integration (Deferred)
- [ ] 5.1 Orchestrator: implicit `init` wiring (session_dir → workspace_dir + trajectory_path + tools)
- [ ] 5.2 Wire objective mode dispatch into `_activate_checkpoint()` / subprocess config generation
- [ ] 5.3 Skip workspace writeback when objective mode result is returned
- [ ] 5.4 Backend parity follow-ups: `claude_code` and `codex` paths

## 6. Verification
- [ ] 6.1 Run targeted standalone MCP tests
- [ ] 6.2 Manual smoke test: connect `massgen-checkpoint-mcp` to Claude Code, call `init` + `checkpoint`, verify plan output shape
- [ ] 6.3 Run full checkpoint test suite: `uv run pytest massgen/tests/test_checkpoint_coordination.py -v`
- [ ] 6.4 Run standalone MCP tests: `uv run pytest massgen/tests/test_standalone_mcp_servers.py -v`

## What's Next
- After standalone server is validated, proceed to section 5 (MassGen-internal integration)
- After internal integration, add backend parity enforcement for `claude_code` and `codex`
- Capability token generation + verification is a separate future change
