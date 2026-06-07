# Worktrees Module

## Overview

When `write_mode` is enabled, agents work under git isolation — each coordination round gets its own branch, branches are preserved across rounds for cross-agent visibility, and scratch files are archived for continuity.

There are **two isolation modes**, chosen by whether the agent has writable `context_paths`:

| Mode | When | Where the agent works | Code path |
|------|------|-----------------------|-----------|
| **Worktree mode** | Writable `context_paths` exist | A separate git *worktree* checkout per context path (`{workspace}/.worktree/`) | `initialize_context()` |
| **Workspace mode** | No `context_paths` (the workspace *is* the project) | **In place**, in the agent's own workspace dir, on a per-round branch | `setup_workspace_scratch()` |

Both live in `IsolationContextManager` (`massgen/filesystem_manager/_isolation_context_manager.py`). The single-agent/native-CLI configs (antigravity, codex, claude_code) typically run in **workspace mode** — see [Workspace Mode](#workspace-mode-in-place) and [Per-Round Workspace Reset](#per-round-workspace-reset) below, which document the in-place lifecycle that the worktree-mode diagram does not show.

## Lifecycle

```
Round 1                          Round 2                         Final Presentation
─────────────────────────────    ──────────────────────────────  ─────────────────────────
agent1: massgen/a1b2c3d4         agent1: massgen/e5f6g7h8        presenter: presenter
agent2: massgen/i9j0k1l2         agent2: massgen/m3n4o5p6          (based on winner's branch)
     │                                │
     ▼                                ▼
cleanup_round()                  cleanup_round()
  ├─ auto-commit changes           ├─ auto-commit changes
  ├─ archive scratch → agent1/     ├─ archive scratch → agent1/
  ├─ remove worktree               ├─ remove worktree
  └─ keep branch                   └─ keep branch
                                                                cleanup_session()
                                                                  └─ delete all branches
```

## Workspace Mode (in-place)

When an agent has **no writable `context_paths`**, the workspace itself is the agent's project. Instead of a separate worktree checkout, the agent works **in place** in its own workspace directory, and isolation is done with per-round branches on a repo that lives *inside* the workspace.

`setup_workspace_scratch()` (`_isolation_context_manager.py`), called at the **start** of each round:

1. **Git-inits the workspace as its own standalone repo** if it isn't already one — `[INIT] MassGen workspace` commit. (It deliberately uses `_is_own_git_root`, not `is_git_repo`, so it never creates branches on the parent project repo even though the workspace lives under `.massgen/workspaces/`.)
2. **Creates and checks out a fresh branch** for the round: `git checkout -b massgen/{hex}`.
3. Creates the git-excluded `.massgen_scratch/`.

```
Round 1 (in-place)              Round 2 (in-place)
──────────────────────────      ──────────────────────────
checkout -b massgen/a1b2c3d4    checkout -b massgen/e5f6g7h8
agent writes files in place     (workspace was wiped clean first — see below)
     │                                │
     ▼                                ▼
cleanup_round() [workspace mode]:
  ├─ auto-commit work → branch  ([ROUND] Auto-commit)
  ├─ git checkout main          (switch off the round branch, keep it)
  └─ _clear_workspace_between_rounds()   ← wipes everything except .git
```

## Per-Round Workspace Reset

**The workspace is wiped to a clean state between every round.** This is the single most surprising part of the lifecycle, so it is called out explicitly:

- **It is NOT done by `Orchestrator.clear_workspace()`.** That call site (`orchestrator.py`, in the per-round setup) has been **commented out since commit `f90f83b4` / v0.0.22** (disabled for performance). Do not reason about per-round clearing from that method — it never runs.
- **It IS done by `_clear_workspace_between_rounds()`** (`_isolation_context_manager.py`), invoked from `cleanup_round()` in workspace mode. It `rmtree`s **everything except `.git/`**:

  > *"Remove all non-.git files from workspace ... so the next round starts with a clean workspace."*

  This runs **after** the round's work is auto-committed to that round's branch, so nothing is lost — it just clears the *working tree*.

### What this means

- **Round independence holds.** Each round starts from a clean working tree on the base branch. An agent does **not** see its own prior round's leftover files sitting in the workspace; it sees prior answers only through the normal `<CURRENT ANSWERS>` injection + `temp_workspaces/` snapshots, the same as every other backend. Native-CLI metadata (e.g. agy's `.antigravity/`, codex's `.codex/`) is wiped too, so those backends get **no carried-over hidden session memory** across rounds.
- **The live workspace symlink only shows the *current* round.** `…/agent_b/workspace` is a symlink to the live workspace dir. Mid-run (or on an interrupted run) it reflects only the in-progress round — often just `AGENTS.md` written at round start. It is **not** where finished deliverables accumulate. Don't judge a run's output by the live symlink.
- **Where a round's work actually lives** (three durable copies):
  1. **Per-round git branch** (`massgen/{hex}`) inside the workspace `.git` — auto-committed `[ROUND]`, kept (`delete_branch=False`) for cross-agent `git diff` visibility.
  2. **Per-round log snapshot** — `…/agent_b/{timestamp}/workspace/…` (and the final run's `turn_*/final/agent_b/workspace/`).
  3. **`temp_workspaces/…/agentN/`** copies, for peer visibility.
- **Native-CLI deliverable promotion.** Because the working tree is wiped each round and metadata dirs like `.antigravity/` are excluded from snapshots, any deliverable a native CLI writes into its *own* hidden dir must be promoted into the visible workspace to survive in the snapshot. The Antigravity backend does this via its scratch-promotion step (`antigravity_cli.py` → `_promote_scratch_deliverables`); see that backend for the pattern.

> **Applies to every backend** in workspace mode — the reset lives in the isolation/write-mode path, keyed on `context_paths`/`write_mode`, not on backend type.

## Branch Naming

| Context | Branch Name | Example |
|---------|------------|---------|
| Regular rounds | `massgen/{8-char hex}` | `massgen/f028d1c7` |
| Final presentation | `branch_label` param (explicit) | `presenter` |
| No `branch_label` | Random hex suffix | `massgen/a1b2c3d4` |

Branch names are intentionally short and anonymous. They do NOT contain agent IDs, round numbers, or session IDs.

### Why not `agent1`, `agent2` as branch names?

An agent's branch gets deleted when it starts a new round (`previous_branch` mechanism). If agent1's branch were named `agent1` in round 1, then in round 2 that branch gets deleted and recreated — meaning other agents lose the reference mid-session. Short random names avoid this collision.

Instead, the **system prompt** maps other agents' branches to readable labels:

```
Other agents' branches:
- agent1: `massgen/f028d1c7`
- agent2: `massgen/a1b2c3d4`
```

## Scratch Directory

Each worktree gets a `.massgen_scratch/` directory:

- Git-excluded (via `info/exclude` in the **common** git dir)
- For experiments, eval scripts, notes
- Invisible to `git status`, `git diff`, and reviewers

### Scratch Archive

On `cleanup_round()`, scratch files are moved to the workspace:

```
{workspace}/.scratch_archive/
├── agent1/          # From round N (named by archive_label)
│   └── notes.md
└── agent2/
    └── eval.py
```

The `archive_label` parameter on `move_scratch_to_workspace()` controls the directory name. The orchestrator passes the anonymous agent ID (e.g. `agent1`), making archives human-readable.

Without `archive_label`, falls back to the hex suffix from the branch name.

## Key Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `IsolationContextManager` | `massgen/filesystem_manager/_isolation_context_manager.py` | Creates/manages worktrees, scratch dirs, branch lifecycle |
| `WorktreeManager` | `massgen/infrastructure/` | Low-level GitPython wrapper for worktree operations |
| `WorkspaceStructureSection` | `massgen/system_prompt_sections.py` | System prompt section showing branches and workspace info |

## IsolationContextManager Parameters

| Parameter | Type | Used For |
|-----------|------|----------|
| `session_id` | `str` | Not used in branch names (only for logging) |
| `write_mode` | `str` | `"auto"`, `"worktree"`, `"isolated"`, `"legacy"` |
| `workspace_path` | `str` | Where worktrees are created (`{workspace}/.worktree/`) |
| `previous_branch` | `str` | Branch to delete on init (one-branch-per-agent invariant) |
| `base_commit` | `str` | Starting point for worktree (e.g. winner's branch for final pres) |
| `branch_label` | `str` | Explicit branch name override (e.g. `"presenter"`) |

## System Prompt

The `WorkspaceStructureSection` shows agents:

1. **Their branch**: "Your work is on branch `massgen/f028d1c7`. All changes are auto-committed when your turn ends."
2. **Other agents' branches** (with anonymous labels): `agent1: massgen/abc123`
3. **Scratch archive reminder**: "Check `.scratch_archive/` for experiments from prior rounds."

The prompt does NOT reveal which anonymous ID the agent is — maintaining anonymity. The agent sees its branch name (which is random) but doesn't know it corresponds to any particular agent label.

## Auto-Commit

`cleanup_round()` auto-commits all uncommitted changes before removing the worktree:

```python
# In _auto_commit_worktree():
repo.git.add("-A")
repo.index.commit("[ROUND] Auto-commit")
```

This ensures the branch contains the agent's actual work even after the worktree is gone. Without this, the branch would point at HEAD (empty) and cross-agent visibility would find nothing.

## Orchestrator Integration

### Regular Rounds (`_stream_agent_execution`)

```python
round_isolation_mgr = IsolationContextManager(
    session_id=f"{self.session_id}-{round_suffix}",
    write_mode=write_mode,
    workspace_path=workspace_path,
    previous_branch=previous_branch,
    # No branch_label — uses short random name
)
```

Other branches passed to system prompt as `Dict[str, str]`:
```python
other_agent_branches = {
    agent_mapping.get(aid, aid): branch  # {"agent1": "massgen/abc123"}
    for aid, branch in self._agent_current_branches.items()
    if aid != agent_id and branch
}
```

### Final Presentation

```python
self._isolation_manager = IsolationContextManager(
    session_id=self.session_id,
    write_mode=write_mode,
    workspace_path=workspace_path,
    base_commit=winner_branch,       # Start from winner's work
    branch_label="presenter",        # Explicit readable name
)
```

## Testing

Tests live in `massgen/tests/test_write_mode_scratch.py`. Key test classes:

| Class | Covers |
|-------|--------|
| `TestScratchDirectory` | `.massgen_scratch/` creation, git exclusion, diff filtering |
| `TestScratchArchiveLabel` | `archive_label` naming, fallback to hex suffix |
| `TestBranchLifecycle` | `cleanup_round` keeps branch, `cleanup_session` deletes, `previous_branch` deletion |
| `TestWorkspaceScratchNoContextPaths` | Workspace mode (no context_paths) branch + scratch lifecycle |
| `TestAutoCommitBeforeCleanup` | Auto-commit on cleanup, no-op when clean |
| `TestWorkspaceStructureBranchInfo` | System prompt shows branch name, other branches with labels, scratch archive mention |
| `TestRestartContextBranchInfo` | Branch info in restart context (dict format) |

```bash
uv run pytest massgen/tests/test_write_mode_scratch.py -v
```
