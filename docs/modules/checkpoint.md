# Checkpoint Coordination Mode

Checkpoint has two modes dispatched by which field is present in the tool call:

| Mode | Trigger | Use case | Output |
|------|---------|----------|--------|
| **Delegation** | `task` present | Team solves a problem, returns deliverables | Consensus text + workspace changes |
| **Objective** | `objective` present | Plan a sequence of irreversible actions safely | `criteria_applied` + structured `plan` |

Both present → error. Neither present → error.

## Architecture

Checkpoint runs as a **subprocess** in both modes. The orchestrator:
1. Clones the main agent's workspace into an isolated scratch workspace
2. Launches `massgen --stream-events` with a generated config
3. Relays subprocess events back to the parent with remapped agent IDs (`agent-id-ckptN`)
4. Returns the result to the main agent

WebUI streaming works because events are relayed — the subprocess never shows blank channels. The main workspace is never mutated during checkpoint execution.

```
Main Agent        Orchestrator          Checkpoint Subprocess
    │                  │                        │
    │  checkpoint()    │                        │
    │─────────────────>│                        │
    │                  │  clone workspace       │
    │                  │  generate config       │
    │                  │  launch subprocess ───>│
    │                  │                        │ agents iterate/vote
    │                  │<── relay events ───────│
    │                  │<── result ─────────────│
    │<── plan/result ──│                        │
```

### Delegation Mode: Workspace Writeback

After consensus, deliverable files are copied from the winning participant's scratch workspace back to the main agent's workspace.

### Objective Mode: No Writeback

The output is a structured plan only — no files are written back. The main agent executes the plan using its own tools, guided by per-step constraints and recovery trees.

### Why Fresh Instances

Participants are created as brand-new agent objects — new backends, empty conversation history, cloned workspaces. Context isolation prevents pre-checkpoint reasoning from biasing participant work.

### Why Clone Workspace (Not Empty)

Participants inherit the main agent's workspace files because the main agent may have set up context files, configs, or scaffolding that participants need.

## Checkpoint Tool Schema

### Delegation Mode

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `task` | Yes | `string` | What agents should accomplish |
| `eval_criteria` | Yes | `list[string]` | Evaluation criteria for the checkpoint round |
| `context` | No | `string` | Background info, prior work |
| `personas` | No | `dict[string, string]` | Agent role assignments |
| `gated_actions` | No | `list[dict]` | Tools agents should propose rather than execute |

### Objective Mode

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `objective` | Yes | `string` | What outcome to plan |
| `action_goals` | No | `list[dict]` | Action intents needing approval (`id`, `goal`, `preferred_tools`, `constraints`) |
| `eval_criteria` | No | `list[string]` | Per-checkpoint criteria — augments global safety policy |

**Automatically provided by the server (not caller params):**
- Full cloned workspace
- Agent trajectory (read from `trajectory_path` set at `init`)
- Main agent's full tool list (from `available_tools` set at `init`)

### Objective Mode Output

```
criteria_applied  list[string] — global safety policy + per-checkpoint criteria

plan  list[dict]
  .step             int
  .description      string
  .constraints      list[string], optional
  .approved_action  dict, optional — {goal_id, tool, args}
                    The ONLY permitted exception to constraints.
                    Per-step only — no top-level mirror.
  .recovery         RecoveryNode, optional

RecoveryNode (recursive):
  .if    string
  .then  string | RecoveryNode
  .else  string | RecoveryNode
  Terminals: "proceed", "recheckpoint", "refuse"
```

**Constraint semantics:**

| `constraints` | `approved_action` | Meaning |
|---|---|---|
| absent | absent | Agent acts freely |
| present | absent | Capability fully blocked |
| present | present | Blocked — except this exact call |

## When to Call Objective Mode

Checkpoint objective mode is for planning **outcomes that involve irreversible actions** — sequences of steps whose combined effect cannot be undone:

- Deletion of any kind: files, records, resources, branches
- External communication: email, messages, webhooks, notifications
- Financial operations: transfers, charges, refunds
- Deployment to live or production environments
- Database schema changes or migrations
- Permission or access control changes

## Global Safety Policy

The global safety policy is a set of baseline criteria applied to every objective mode checkpoint. It is configured at the project level and cannot be narrowed by per-call `eval_criteria`. Per-call criteria can only add stricter requirements. The policy defines the floor — things like "never run destructive operations without a verified backup."

## Standalone MCP Server

`massgen-checkpoint-mcp` is a standalone server any agent can connect to. It exposes two tools:

### `init`
Called once at session start:
```
init(workspace_dir, trajectory_path, available_tools)
  workspace_dir:    string — path to agent's working directory
  trajectory_path:  string — path to agent's stored trajectory on disk
  available_tools:  list[{name, description}] — all tools (built-ins + MCP)
```

### `checkpoint`
Called each time a checkpoint is needed:
```
checkpoint(objective, action_goals, eval_criteria)
```

The server reads the trajectory from `trajectory_path`, generates a MassGen subprocess config, and returns the structured plan.

## Configuration (MassGen-Internal)

```yaml
agents:
  - id: architect
    main_agent: true
    backend:
      type: claude
      model: claude-sonnet-4-20250514
  - id: builder_a
    backend:
      type: claude
      model: claude-sonnet-4-20250514

orchestrator:
  coordination:
    checkpoint_enabled: true
    checkpoint_mode: conversation  # or "task"
    checkpoint_gated_patterns:
      - "mcp__vercel__deploy*"
```

## WebUI Behavior

- Initially shows only the main agent channel
- On checkpoint: new channels appear for each participant (`agent_a-ckpt1`, `agent_b-ckpt1`)
- Main agent channel shows delegation notice
- Checkpoint tool call renders as a styled delegation card
- After checkpoint: completion notice added to main agent channel

## Log Structure

```
log_session_dir/
  agent_a/                    # Main agent's pre-checkpoint work
    20260323_130655/
    workspace -> /workspace_abc123
  agent_a-ckpt1/             # Checkpoint participant
    20260323_130720/
    workspace -> /workspace_abc123_ckpt_1_a1b2
  agent_b-ckpt1/
    20260323_130720/
    workspace -> /workspace_abc123_ckpt_1_c3d4
  agent_outputs/
    main.txt
    agent_a-ckpt1.txt
    agent_b-ckpt1.txt
```

## Key Files

| File | Role |
|------|------|
| `massgen/orchestrator.py` | `_activate_checkpoint()`, subprocess launch, event relay |
| `massgen/mcp_tools/checkpoint/` | Checkpoint MCP server, signal file I/O |
| `massgen/mcp_tools/checkpoint/_subprocess_manager.py` | Subprocess launch, workspace clone, event relay |
| `massgen/tool/workflow_toolkits/checkpoint.py` | Checkpoint tool schema definition |
| `massgen/events.py` | `checkpoint_activated` / `checkpoint_completed` event types |

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| Subprocess with event relay | Stronger state isolation; WebUI streaming preserved via parent relaying subprocess events with remapped agent IDs (`-ckptN` suffix) |
| Fresh instances (not session reuse) | Context isolation prevents pre-checkpoint reasoning from biasing participant work |
| Clone workspace (not empty) | Participants need files the main agent set up |
| Resume original session (not fresh) | Main agent needs its planning context to continue |
| Full workspace to checkpoint agents | Main agent cannot be trusted to select what context is relevant — restricting access undermines the safety thesis |
| Per-step approved_action only | Single source of truth; a top-level mirror creates drift risk |
| Capability tokens deferred | Current gating via fnmatch pattern blocking (`CheckpointGatedHook`) is sufficient for v1 |
