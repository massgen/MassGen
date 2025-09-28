# Multi-Turn Filesystem Support – Design Documentation

## Overview

This document describes the architecture and design decisions for MassGen's multi-turn conversation support with filesystem persistence. This feature enables agents to maintain state across multiple conversation turns, building upon previous work incrementally.

---

## Table of Contents
1. [Core Concepts](#core-concepts)
2. [Architecture](#architecture)
3. [Workspace Access Patterns](#workspace-access-patterns)
4. [Session Persistence](#session-persistence)
5. [Logging Design](#logging-design)
6. [Design Decisions](#design-decisions)
7. [Implementation Details](#implementation-details)
8. [Cleanup and Refactoring](#cleanup-and-refactoring)

---

## Core Concepts

### Turn-Based Workflow

Each user interaction in a multi-turn conversation represents one **turn**:
- **Turn 1**: Initial user request → agent processes → results saved to `sessions/session_X/turn_1/`
- **Turn 2**: Follow-up request → agent has access to turn 1 results → results saved to `turn_2/`
- **Turn N**: Agent can reference all previous turns while building new work

### Session Structure

```
sessions/
└── session_20250927_123456/
    ├── SESSION_SUMMARY.txt           # Human-readable summary
    ├── turn_1/
    │   ├── workspace/                # Final output from turn 1
    │   ├── answer.txt                # Normalized answer with corrected paths
    │   └── metadata.json             # Turn metadata (timestamp, winning agent, task)
    ├── turn_2/
    │   ├── workspace/                # Final output from turn 2 (built on turn 1)
    │   ├── answer.txt
    │   └── metadata.json
    └── turn_3/
        └── ...
```

### Logging Structure

Logs mirror the session structure for easy correlation:

```
massgen_logs/
└── log_20250927_123456/
    ├── turn_1/
    │   └── massgen_debug.log         # All logs for turn 1
    ├── turn_2/
    │   └── massgen_debug.log         # All logs for turn 2
    └── turn_3/
        └── massgen_debug.log
```

**Key Design Point:** Logs for turn N go into `turn_N/` directory (not `turn_N-1/` or base dir).

---

## Architecture

### Component Responsibilities

#### 1. CLI (`massgen/cli.py`)
**Responsibilities:**
- Session ID generation and management
- Turn counter management
- Agent recreation with previous turn context paths
- Logging reconfiguration for each turn
- Calling session persistence after orchestrator completes

**Key Functions:**
- `run_interactive_mode()` - Main loop managing turns
- `load_previous_turns()` - Loads turn metadata from session storage
- `handle_session_persistence()` - Persists orchestrator results after each turn

#### 2. Orchestrator (`massgen/orchestrator.py`)
**Responsibilities:**
- Receives `previous_turns` list from CLI
- Pre-populates agent workspaces with turn N-1 results (writable copy)
- Provides turn information to agents via system messages
- Exposes `get_final_result()` for CLI to persist

**Key Methods:**
- `_clear_agent_workspaces()` - Clears and pre-populates workspaces
- `_get_previous_turns_context_paths()` - Returns turn metadata for system message
- `get_final_result()` - Returns final answer, winning agent, and workspace path

#### 3. Logger (`massgen/logger_config.py`)
**Responsibilities:**
- Creates turn-specific log directories
- Routes logs to correct turn directory

**Key Functions:**
- `get_log_session_dir(turn)` - Returns log directory for given turn
- `setup_logging(debug, log_file, turn)` - Configures logging for specific turn

---

## Workspace Access Patterns

### Dual-Access Design

Agents in turn N have **TWO ways** to access turn N-1 results:

#### 1. Writable Workspace (Pre-populated Copy)
- **Location**: Agent's own workspace directory (e.g., `workspace1/`)
- **Permission**: Read + Write
- **Content**: Complete copy of turn N-1's final workspace
- **Purpose**: Agent can modify, extend, or build upon previous work
- **Mechanism**: Orchestrator copies `turn_N-1/workspace/` → agent's workspace before execution

#### 2. Read-Only Context Path (Original)
- **Location**: Session storage (e.g., `sessions/.../turn_1/workspace/`)
- **Permission**: Read-only
- **Content**: Original, unmodified turn N-1 results
- **Purpose**: Agent can reference original state for comparison ("what did I change?")
- **Mechanism**: CLI adds previous turn as context path when recreating agents

### Example: Turn 3 Access Pattern

**Agent perspective during turn 3:**
```
My Workspace (writable):
  /path/to/workspace1/
  ├── file1.txt         # Copy from turn 2, can modify
  └── file2.txt         # Copy from turn 2, can modify

Read-Only Context Paths:
  /sessions/session_X/turn_1/workspace/  # Original turn 1 results
  /sessions/session_X/turn_2/workspace/  # Original turn 2 results (same as workspace copy)
```

**System Message Excerpt:**
```
**Your Workspace**: `/path/to/workspace1/` - Write actual files here.
**Note**: Your workspace already contains a writable copy of the previous
turn's results - you can modify or build upon these files. The original
unmodified version is also available as a read-only context path if you
need to reference what was originally there.

**Context Path**: `/sessions/.../turn_2/workspace` (read-only)
**Context Path**: `/sessions/.../turn_1/workspace` (read-only)

**Note**: This is a multi-turn conversation. Each User/Assistant exchange
in the conversation history represents one turn. The workspace from each
turn is available as a read-only context path listed above.
```

### Why Dual Access?

This design allows agents to:
1. **Iterate freely** on previous work (via writable workspace)
2. **Compare changes** by checking original vs. modified (via context paths)
3. **Reference older turns** without cluttering current workspace
4. **Maintain audit trail** of what changed in each turn

---

## Session Persistence

### Flow

1. **Orchestrator completes** → `get_final_result()` returns:
   - `final_answer`: Agent's response text
   - `winning_agent_id`: Which agent won
   - `workspace_path`: Temporary workspace location

2. **CLI calls `handle_session_persistence()`**:
   - Increments turn counter
   - Creates `sessions/session_X/turn_N/` directory
   - Normalizes answer paths (replaces temp paths with persistent paths)
   - Copies workspace to `turn_N/workspace/`
   - Saves `answer.txt` and `metadata.json`
   - Updates `SESSION_SUMMARY.txt`

3. **Returns** `(session_id, turn_number, normalized_answer)`

### Path Normalization

Agents work in temporary directories like `/tmp/workspace1/`. Before persistence:
```python
# Agent's answer references temporary path
"I created files in /tmp/workspace1/file.txt"

# After normalization
"I created files in /sessions/session_X/turn_1/workspace/file.txt"
```

This ensures conversation history has correct, persistent paths.

---

## Logging Design

### Original Problem

**Initial design (incorrect):**
- Turn 1 starts: `current_turn = 0` → logs go to base directory
- Turn 1 completes: increment to `current_turn = 1`, reconfigure logging
- Turn 2 starts: `current_turn = 1` → logs go to `turn_1/` (should be `turn_2/`)

**Result:** Logs were always one turn behind session directories.

### Solution

**Corrected design:**
- Turn starts: increment BEFORE processing, reconfigure logging immediately
- Turn 1 starts: `next_turn = 1`, reconfigure → logs go to `turn_1/`
- Turn 1 completes: persist to `sessions/.../turn_1/`

**Key code change in `cli.py`:**
```python
# BEFORE processing (not after)
next_turn = current_turn + 1
setup_logging(debug=_DEBUG_MODE, turn=next_turn)
reconfig_logger.info(f"Starting turn {next_turn}")

# Process turn...
response = await run_question_with_history(...)

# AFTER processing
current_turn = updated_turn  # Update from persistence result
```

### Benefits

1. **Aligned numbering**: `turn_1` logs match `turn_1` session directory
2. **No pre-creation**: Directories only created when turn actually starts
3. **Clear audit trail**: All logs for turn N in one place

---

## Design Decisions

### 1. CLI vs. Orchestrator Responsibility Split

**Decision:** CLI handles all session persistence, Orchestrator only exposes data

**Rationale:**
- Orchestrator is a reusable component used in various contexts (single-turn, multi-agent, etc.)
- Session persistence is specific to CLI's interactive mode
- Keeps orchestrator stateless between turns
- Allows other interfaces (API, UI) to implement their own persistence

**Alternatives Considered:**
- ❌ Orchestrator handles persistence → Couples orchestrator to CLI's storage format
- ❌ Shared persistence service → Adds complexity without clear benefit

### 2. Agent Recreation vs. Workspace Update

**Decision:** Fully recreate agents with updated context paths before each turn

**Rationale:**
- MCP servers need to be initialized with correct context paths
- No clean way to "hotswap" MCP configuration without recreation
- Fresh agent state prevents cross-turn contamination

**Trade-offs:**
- ✅ Clean, predictable state
- ✅ MCPs properly configured
- ❌ Slower (requires backend cleanup and recreation)
- ❌ More complex code

**Future Improvement (TODO):**
```python
# Instead of recreation, if MCPs support dynamic reconfiguration:
if hasattr(agent.backend, 'update_context_paths'):
    agent.backend.update_context_paths(new_paths)
```

### 3. Workspace Pre-population

**Decision:** Orchestrator pre-populates agent workspaces with turn N-1

**Rationale:**
- Agents expect to "continue" work from previous turn
- Copying files is simpler than managing read-only mounts
- Allows agents to modify previous work directly

**Alternatives Considered:**
- ❌ Read-only mount → Agents can't modify files, need complex copy logic
- ❌ No pre-population → Agents must manually copy files they want to modify

### 4. Dual Workspace Access (Writable + Read-Only)

**Decision:** Provide BOTH writable copy AND read-only original

**Rationale:**
- Enables comparison workflows ("what changed since last turn?")
- Supports verification tasks
- Maintains audit trail

**Cost:** Additional storage (one copy per turn), but worth it for flexibility

### 5. Turn Numbering Starts at 1

**Decision:** First turn is `turn_1`, not `turn_0`

**Rationale:**
- More intuitive for users ("Turn 1" sounds like first turn)
- Avoids confusion with zero-based indexing
- Matches common language ("Turn 1, Turn 2, ...")

### 6. Session ID Format

**Decision:** `session_YYYYMMDD_HHMMSS` timestamp-based

**Rationale:**
- Human-readable
- Sortable chronologically
- Unique (within second resolution)

**Alternatives Considered:**
- ❌ UUID → Less readable
- ❌ Sequential numbers → Requires persistent counter

---

## Implementation Details

### Key Files Modified

1. **`massgen/cli.py`**
   - Added `load_previous_turns()` - Loads turn metadata
   - Added `handle_session_persistence()` - Persists results
   - Modified `run_interactive_mode()` - Manages turn lifecycle
   - Added `run_question_with_history()` - Passes session info to orchestrator

2. **`massgen/orchestrator.py`**
   - Added `previous_turns` parameter to `__init__()`
   - Added `_clear_agent_workspaces()` - Pre-populates with previous turn
   - Added `_get_previous_turns_context_paths()` - Provides turn metadata
   - Added `get_final_result()` - Exposes data for persistence

3. **`massgen/logger_config.py`**
   - Added `turn` parameter to `setup_logging()`
   - Added turn subdirectory logic to `get_log_session_dir()`
   - Tracks current turn with `_CURRENT_TURN` global

4. **`massgen/message_templates.py`**
   - Added `previous_turns` parameter to `filesystem_system_message()`
   - Added `workspace_prepopulated` parameter
   - Added note connecting conversation history to context paths

5. **`massgen/backend/utils/filesystem_manager/_path_permission_manager.py`**
   - Added `add_previous_turn_paths()` (unused in current implementation)

### Session Info Flow

```
CLI (run_interactive_mode)
  ↓
  session_info = {
      "session_id": "session_20250927_123456",
      "current_turn": 1,  # Previous turn number
      "session_storage": "sessions"
  }
  ↓
run_question_with_history()
  ↓
load_previous_turns(session_info)  # Loads turn_1, turn_2, etc.
  ↓
Orchestrator(__init__, previous_turns=[...])
  ↓
[Orchestrator executes]
  ↓
handle_session_persistence()
  ↓
Returns (session_id, turn_2, normalized_answer)  # Incremented turn
  ↓
CLI updates: current_turn = 2
```

---

## Final Architecture

**Clean separation of concerns:**
- **CLI:** Session management, persistence, agent lifecycle
- **Orchestrator:** Coordination logic, workspace pre-population, data exposure
- **Logger:** Turn-specific log routing
- **Message Templates:** System message generation with turn context

---

## Future Improvements

### 1. Optimized Agent Recreation
Instead of full recreation, support dynamic MCP reconfiguration:
```python
# Pseudocode
if agent.backend.supports_dynamic_context_paths():
    agent.backend.update_context_paths(new_turn_paths)
else:
    # Fall back to recreation
    agent = recreate_agent_with_paths(new_turn_paths)
```

### 2. Turn Branching
Support branching from previous turns:
```
turn_1 → turn_2 → turn_3a (try approach A)
              ↓
              → turn_3b (try approach B)
```

### 3. Turn Diff Visualization
Show what changed between turns:
```bash
massgen diff turn_1 turn_2
# Shows added/modified/deleted files
```

### 4. Turn Rollback
Ability to continue from an earlier turn:
```bash
massgen continue-from turn_2
# Discards turn_3, continues from turn_2
```

---

## Related Documentation

- **Filesystem MCP Design:** `docs/dev_notes/gemini_filesystem_mcp_design.md`
- **Context Sharing (v0.0.14):** `docs/dev_notes/v0.0.14-context.md`
- **User Context Path Support:** `docs/case_studies/user-context-path-support-with-copy-mcp.md`
- **Claude Code Workspace Management:** `docs/case_studies/claude-code-workspace-management.md`

---

## Summary

Multi-turn filesystem support enables agents to build upon previous work across conversation turns. The design emphasizes:

1. **Clear separation of concerns** - CLI manages persistence, Orchestrator manages coordination
2. **Dual workspace access** - Writable copy for iteration + read-only original for comparison
3. **Aligned logging** - Turn N logs match turn N session directories
4. **Audit trail** - Complete history of work, changes, and decisions
5. **Flexibility** - Agents can reference any previous turn via context paths

This architecture provides a foundation for complex multi-turn workflows while maintaining clean abstractions and avoiding tight coupling between components.