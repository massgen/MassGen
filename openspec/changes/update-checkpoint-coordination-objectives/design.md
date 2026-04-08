## Priority

The **standalone MCP server** (`massgen-checkpoint-mcp`) is the first deliverable. Any agent — Claude Code, a MassGen agent, or a third-party tool — can connect to it and use objective-based checkpointing without any MassGen-internal wiring. MassGen-internal integration is deferred until the standalone server is validated.

## Context

Checkpoint already exists as a **delegation mode**: the main agent calls `checkpoint(task=...)` to hand a problem to the full team, who solve it collaboratively and return deliverables. That pattern is unchanged.

This change adds a second mode: **objective-based safety checkpointing**. The trigger is different — not "I need help solving this" but "I am about to do something irreversible and need a plan I can trust." The output is different too — not deliverables, but a structured plan that constrains exactly how the main agent executes the risky sequence.

## Goals / Non-Goals

**Goals**
- Ship a standalone `massgen-checkpoint-mcp` server any agent can connect to
- Define `init` + `checkpoint` tool API for the standalone server
- Add an objective-based calling mode dispatched by the presence of `objective=...`
- Define compact input and rich structured output for that mode
- Provide full workspace + trajectory to checkpoint agents — the main agent cannot be trusted to select what's relevant
- Surface `criteria_applied` in output so the agent knows what it is optimizing for
- Encode per-step constraints, approved actions, and a recursive recovery tree in each plan step
- Document when the main agent should call checkpoint

**Non-Goals**
- MassGen-internal checkpoint wiring (deferred until standalone is validated)
- Replacing the existing delegation mode (`task=...`)
- Capability tokens or runtime enforcement (deferred)
- Full human approval workflow
- Adding third-party guardrail frameworks

## Mode Dispatch

Two modes, dispatched by which field is present. Mutually exclusive — both present is an error.

| Mode | Trigger | Use case | Output |
|------|---------|----------|--------|
| Delegation | `task` present | Team solves a problem, returns deliverables | Consensus text + workspace changes |
| Objective | `objective` present | Plan a sequence of irreversible actions safely | `criteria_applied` + structured `plan` |

## Architecture

Checkpoint runs as a **subprocess** in both modes. The parent process:
1. Clones the main agent's workspace into an isolated scratch workspace
2. Launches `massgen --stream-events` with a generated config
3. Relays subprocess events back to the parent with remapped agent IDs (`agent-id-ckptN`)
4. Returns the result to the main agent

WebUI streaming works because events are relayed — the subprocess never shows blank channels.

The main workspace is never mutated during checkpoint. Any writes by checkpoint agents happen only in scratch. For delegation mode, deliverables are copied back after consensus. For objective mode, no files are written back — the output is a plan, not deliverables.

## When to Call Checkpoint (Objective Mode)

Checkpoint safety is for planning **outcomes that involve irreversible actions** — not individual tool calls, but sequences of steps whose combined effect cannot be undone. Call checkpoint when the path forward includes any irreversible action, regardless of how many steps are involved:

- Deletion of any kind: files, records, resources, branches
- External communication: email, messages, webhooks, notifications
- Financial operations: transfers, charges, refunds
- Deployment to live or production environments
- Database schema changes or migrations
- Permission or access control changes

The scope can be narrow (a single gated call) or broad (a multi-step workflow). What matters is that at least one action in the sequence is irreversible.

## What's Automatically Provided to Checkpoint Agents

The orchestrator provides this automatically — it is not part of the input schema:

- **Full cloned workspace** — checkpoint agents see everything the main agent sees. Restricting access via `context_paths` would undermine the safety thesis: the main agent cannot be trusted to select what's relevant.
- **Execution trace** — the full conversation history up to the checkpoint call: assistant responses, tool calls, tool results, and optionally reasoning/thinking. Checkpoint agents need to understand what the main agent has done and decided, not just the stated objective.
- **Main agent's full tool list** — so checkpoint agents know exactly which tools are available, can reason about which calls are dangerous, and can produce accurate `approved_action` entries.

## Global Safety Policy

The global safety policy is a project-level set of baseline criteria that applies to every objective mode checkpoint. It is configured in the project config (not per-call) and defines the floor — things that must always hold regardless of what `eval_criteria` a caller provides. Per-call `eval_criteria` can only augment (tighten) the policy, never replace or widen it.

Default baseline (can be extended in config):
- Never run destructive operations without a verified backup
- Never deploy to production without passing tests
- Never send external communications without explicit approval in the plan

## Input Schema (Objective Mode)

```
objective         string, required
                  Natural language description of what outcome to plan.
                  Should describe the full intended sequence, not just the riskiest step.

action_goals      list[dict], optional
                  Action intents that may require explicit approval.
  .id             string — unique identifier for this goal
  .goal           string — natural language description of intent
  .preferred_tools  list[string], optional — likely tools the main agent would use
  .constraints    string, optional — hard constraints the main agent knows upfront

eval_criteria     list[string], optional
                  Per-checkpoint success criteria. Augments the global safety policy —
                  never replaces it. Per-call overrides can only tighten, not widen.
```

No `context_paths` or `focus_paths`. The objective carries sufficient signal. The full workspace and execution trace are provided automatically.

## Output Schema (Objective Mode)

```
criteria_applied  list[string]
                  The full set of criteria that shaped this plan: global safety policy
                  entries plus per-checkpoint eval_criteria. Surfaced so the agent knows
                  what it is optimizing for and can exercise judgment on edge cases the
                  plan does not explicitly cover.

plan              list[dict]
                  Ordered execution steps. The agent must follow this sequence.

  .step           int — position in the ordered sequence
  .description    string — what to accomplish in this step
  .constraints    list[string], optional
                  Directives limiting what the agent may do within this step.
                  Two kinds:
                  1. Goal-directed: block alternative paths toward the same goal
                     ("do not run any other migrations")
                  2. Adjacency: block scope creep that naturally arises while pursuing
                     the step ("do not modify deployment config while fixing tests")
  .approved_action  dict, optional
                  The ONLY permitted exception to a constraint. When present alongside
                  constraints, the agent must use exactly this call — no alternatives.
                  When absent, the agent acts freely within the step description.
    .goal_id      string — which action_goal this resolves
    .tool         string — exact tool name
    .args         dict — exact normalized arguments

  .recovery       RecoveryNode, optional
                  A recursive decision tree guiding the agent when conditions deviate
                  from the expected path. See RecoveryNode below.
```

### Constraint / approved_action Semantics

| `constraints` | `approved_action` | Meaning |
|---|---|---|
| absent | absent | Agent acts freely using any available tool |
| present | absent | Capability fully blocked for this step |
| present | present | Blocked — except this exact call is permitted |

### RecoveryNode (Recursive)

```
RecoveryNode:
  .if    string — condition to evaluate
  .then  string | RecoveryNode — what to do when condition is true
  .else  string | RecoveryNode — what to do when condition is false (optional)

Terminal values:
  "proceed"      — condition resolved or not a real problem, continue to next step
  "recheckpoint" — stop and get new guidance before proceeding
  "refuse"       — the only remaining option is unsafe; refuse to act
```

The tree can be arbitrarily deep. The checkpoint agents generating the plan encode the right depth based on the complexity of the scenario. No retry counts or limits — the structure of the tree and the `else` branches handle escalation naturally.

## Full Example

**Input:**
```json
{
  "objective": "Deploy the user dashboard to Vercel production and run the pending DB migration",
  "action_goals": [
    {
      "id": "migrate",
      "goal": "Run pending migration 0012_add_user_preferences",
      "preferred_tools": ["Bash"],
      "constraints": "Must take a DB backup first"
    },
    {
      "id": "deploy",
      "goal": "Deploy current build to Vercel production",
      "preferred_tools": ["mcp__vercel__deploy"],
      "constraints": "Must not deploy if tests are failing"
    }
  ],
  "eval_criteria": [
    "Migration must be backward-compatible with the running app",
    "Deployment must use a zero-downtime strategy"
  ]
}
```

**Output:**
```json
{
  "criteria_applied": [
    "Never run destructive operations without a verified backup",
    "Migration must be backward-compatible with the running app",
    "Deployment must use a zero-downtime strategy"
  ],
  "plan": [
    {
      "step": 1,
      "description": "Ensure all tests pass",
      "constraints": [
        "Fix only the specific failing tests — do not rewrite passing tests",
        "Do not modify migration files or deployment config while fixing tests"
      ],
      "recovery": {
        "if": "tests fail",
        "then": "fix the failing tests",
        "else": {
          "if": "failure is in code we did not touch",
          "then": "recheckpoint",
          "else": "proceed"
        }
      }
    },
    {
      "step": 2,
      "description": "Take a database backup",
      "constraints": [
        "Do not make any schema changes during backup"
      ],
      "recovery": {
        "if": "backup fails or reports incomplete",
        "then": "recheckpoint",
        "else": "proceed"
      }
    },
    {
      "step": 3,
      "description": "Run the database migration",
      "constraints": [
        "Do not run any other migrations",
        "Do not modify application code while running the migration"
      ],
      "approved_action": {
        "goal_id": "migrate",
        "tool": "Bash",
        "args": { "command": "python manage.py migrate 0012_add_user_preferences" }
      },
      "recovery": {
        "if": "migration would touch tables outside user_preferences",
        "then": "refuse",
        "else": {
          "if": "migration errors mid-run",
          "then": "recheckpoint",
          "else": "proceed"
        }
      }
    },
    {
      "step": 4,
      "description": "Deploy to Vercel production",
      "constraints": [
        "Do not modify any files before deploying",
        "Do not deploy to staging or preview environments instead"
      ],
      "approved_action": {
        "goal_id": "deploy",
        "tool": "mcp__vercel__deploy",
        "args": { "project": "user-dashboard", "environment": "production", "force": false }
      },
      "recovery": {
        "if": "health check non-200 after 2 minutes",
        "then": "recheckpoint",
        "else": "proceed"
      }
    }
  ]
}
```

## Key Decisions

1. **Objective mode extends, not replaces, delegation mode**
   Dispatched by field presence. Existing `task=...` usage is fully compatible.

2. **Full workspace + execution trace, always**
   The main agent cannot be trusted to select what context is relevant — that defeats the purpose. Everything is provided automatically.

3. **Per-step approved_action is the single source of truth**
   No top-level `approved_actions` mirror. Two sources of truth create drift risk and ambiguity about which the agent should trust.

4. **Constraints have two roles**
   Goal-directed (block alternative paths) and adjacency (block scope creep). Both are plain strings in the same list — the distinction is conceptual, not structural.

5. **RecoveryNode is recursive, no retry counts**
   The tree structure handles escalation naturally via `else` branches. Encoding retry counts in the schema is fragile — the checkpoint agents generating the plan encode the right depth based on scenario complexity.

6. **Subprocess with event relay**
   Checkpoint runs as a subprocess. WebUI streaming works because the parent relays events with remapped agent IDs. The "in-process" approach mentioned in earlier docs was not implemented.

7. **Capability tokens deferred**
   Current gating is fnmatch pattern blocking via `CheckpointGatedHook`. Token-based enforcement is a future enhancement.

## Standalone MCP Server

The standalone server (`massgen-checkpoint-mcp`) exposes two tools:

### `init`

Called once at session start. The server stores this context for the duration of the session.

```
init(
  workspace_dir:     string  — path to the agent's working directory
  trajectory_path:   string  — path to the agent's stored trajectory on disk
  available_tools:   list[{name, description}]
                             — all tools the calling agent has access to,
                               both built-ins (Bash, Read, Write, etc.) and
                               MCP tools. Auto-discovery is not possible because
                               built-ins are not exposed via any protocol.
)
```

The trajectory is a **path**, not content. The server reads it when launching the checkpoint subprocess. This works for MassGen agents (which always write trajectories to disk) and for any other agent that stores its conversation log on the filesystem.

### `checkpoint`

Called each time a checkpoint is needed. Uses the context stored at `init` time.

```
checkpoint(
  objective:     string       — required, see Input Schema above
  action_goals:  list[dict]   — optional
  eval_criteria: list[string] — optional
)
```

The server:
1. Reads the trajectory from `trajectory_path`
2. Generates a MassGen subprocess config embedding `workspace_dir`, the trajectory content, and `available_tools`
3. Launches `massgen --stream-events` with that config
4. Returns the structured plan output

### Why Not Pass Context at Connection Time

MCP's init protocol does not support passing arbitrary data. Environment variables could handle `workspace_dir` but not structured data like the tool list. The `init` tool is the cleanest solution that works for both static and dynamic context without requiring non-standard protocol extensions.

### MassGen-Internal (Deferred)

For MassGen-managed runs, the orchestrator already knows `session_dir`, `workspace_dir`, and the tool list. The `init` call will be implicit — the orchestrator wires these automatically when triggering a checkpoint. No explicit `init` tool call required from the main agent. This is deferred until the standalone server is validated.

## Development Notes

### MCP Server Restart Required After Code Changes

MCP servers are long-lived processes started when the agent session begins. Source code changes on disk do not affect the running server process. After modifying standalone MCP server code:

1. Remove: `claude mcp remove massgen-checkpoint-mcp`
2. Re-add: `claude mcp add massgen-checkpoint-mcp -- uv run massgen-checkpoint-mcp --config .massgen/checkpoint_config.yaml`
3. Start a new conversation (`/clear` or relaunch) to force the process to restart

### Run Logs

Checkpoint runs persist at `{workspace_dir}/.massgen/checkpoint_runs/ckpt_NNN/`. Each run directory contains:
- `_checkpoint_config.yaml` — generated subprocess config
- `.checkpoint/trajectory.log` — copied trajectory
- `.massgen/massgen_logs/` — agent execution logs
- `snapshots/` — agent output snapshots with `checkpoint_result.json`
- `answer.txt` — consensus answer

## Risks / Trade-offs

- **Recovery tree depth**: Open-ended depth could produce unreadable plans. Mitigation: checkpoint agents are prompted to keep trees shallow where possible and use `recheckpoint` for genuinely uncertain branches.
- **Constraint completeness**: Constraints can't cover every possible adjacent action. Mitigation: `criteria_applied` gives the agent a quality bar to reason against even when constraints don't cover a specific case.
- **Objective mode output trust**: The plan is generated by LLM agents — it could contain mistakes. Mitigation: multi-agent voting ensures diverse perspectives before the plan is returned.

## What's Next

- Implementation: extend `checkpoint()` tool schema with `objective` param and structured output shape
- Capability token generation and verification in orchestrator
- Backend parity follow-ups for `claude_code` and `codex` paths
