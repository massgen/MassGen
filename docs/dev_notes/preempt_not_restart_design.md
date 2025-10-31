# Preempt with Injection (Not Restart) - Design Doc

**Status**: Design Phase
**Issue**: #376 - Preserve agent work-in-progress during coordination
**Branch**: `preempt_not_restart`
**Date**: 2025-10-26

## Executive Summary

Replace the current "kill and restart" behavior with **"inject update and continue"**. When an agent provides a new answer, inject that information into other agents' ongoing work instead of restarting them.

## Current Behavior (Restart-Based) ❌

```
Agent A: Working on solution...
Agent B: ✅ Provides new answer
         ↓
Agent A: restart_pending = True
         ↓ (at next safe point)
         Kill stream
         Clear workspace
         Start fresh with Agent B's answer in context
         ❌ Lost all thinking and partial work
```

## Proposed Behavior (Injection-Based) ✅

```
Agent A: Working on solution...
Agent B: ✅ Provides new answer
         ↓
Agent A: restart_pending = True
         ↓ (at next safe point)
         📨 Inject: "UPDATE: Agent B answered: [answer]"
         📨 Inject: "Workspaces updated with new files"
         ✅ Continue working with new context
         Agent A: "I see Agent B's approach, I'll build on that..."
```

## Technical Design

### 1. Detection (Unchanged)

**Location**: `orchestrator.py:1073-1107` (`_coordinate_agents_in_parallel`)

When any agent provides `new_answer`:
```python
if result_type == "answer":
    reset_signal = True
    # This triggers restart_pending for all other agents
```

### 2. Injection Point (CHANGED)

**Location**: `orchestrator.py:1991-2000` and 8 other locations

**Current code:**
```python
if self._check_restart_pending(agent_id):
    await self._handle_agent_restart(agent_id, answers)
    yield ("content", f"🔁 [{agent_id}] gracefully restarting\n")
    yield ("done", None)
    return  # ← Stream ends here ❌
```

**New code (using helper function):**
```python
if self._check_restart_pending(agent_id):
    # Inject update and continue (helper handles all logic)
    should_continue = await self._inject_update_and_continue(
        agent_id,
        answers,
        conversation_messages
    )

    if should_continue:
        yield ("content", f"📨 [{agent_id}] receiving update with new answers\n")
        continue  # ← Agent continues working ✅
    else:
        # Fallback to restart if injection not possible
        yield ("content", f"🔁 [{agent_id}] gracefully restarting\n")
        yield ("done", None)
        return
```

**Helper function consolidates logic** - prevents repetition across 9 locations.

### 3. Helper Functions

**New method 1**: `_inject_update_and_continue(agent_id, answers, conversation_messages) -> bool`

```python
async def _inject_update_and_continue(
    self,
    agent_id: str,
    answers: Dict[str, str],
    conversation_messages: List[Dict]
) -> bool:
    """
    Inject update message and prepare agent to continue.

    Returns:
        bool: True if injection succeeded and agent can continue, False if should restart
    """
    logger.info(f"[Orchestrator] Injecting update for {agent_id}")

    # Build and inject update message
    update_message = self._build_update_message(agent_id, answers)
    conversation_messages.append(update_message)

    # Sync temp workspace if applicable
    await self._sync_temp_workspace_for_agent(agent_id)

    # Clear restart_pending so we don't re-inject
    self.agent_states[agent_id].restart_pending = False

    return True  # Injection successful, continue
```

**New method 2**: `_build_update_message(agent_id, answers) -> Dict`

```python
async def _build_update_message(self, agent_id: str, answers: Dict[str, str]) -> Dict[str, str]:
    """Build update message to inject when new answers arrive."""

    # Get normalized answers for this agent
    normalized_answers = self._normalize_workspace_paths_in_answers(
        answers,
        viewing_agent_id=agent_id
    )

    # Create anonymous mapping (same logic as CURRENT ANSWERS)
    agent_mapping = {}
    for i, real_id in enumerate(sorted(answers.keys()), 1):
        agent_mapping[real_id] = f"agent{i}"

    # Format answers
    answers_section = []
    for real_id, answer in normalized_answers.items():
        anon_id = agent_mapping[real_id]
        answers_section.append(f"<{anon_id}> {answer} </{anon_id}>")

    answers_text = "\n".join(answers_section)

    # Check if this agent has workspace/filesystem enabled
    agent = self.agents.get(agent_id)
    has_workspace = agent and agent.backend.filesystem_manager is not None

    # Build update content (conditionally include workspace info)
    update_parts = [
        "UPDATE: While you were working, new answers were provided.",
        "",
        "<NEW ANSWERS>",
        answers_text,
        "</NEW ANSWERS>",
        "",
    ]

    # Only mention workspace if agent has filesystem access
    if has_workspace:
        update_parts.extend([
            "WORKSPACE UPDATE:",
            "- Your workspace files are preserved",
            "- Temp workspace may contain new files from other agents",
            "- Check temp workspace for latest agent work",  # replace with real paths?
            "",
        ])

    update_parts.extend([
        "You can now:",
        "1. Continue your current approach if you think it's better or different",
        "2. Build upon or refine the new answers",
        "3. Vote for an existing answer if you agree with it",
        "",
        "Proceed with your decision (continue working, vote, or provide new_answer)."
    ])

    return {"role": "user", "content": "\n".join(update_parts)}
```

### 4. Workspace Sync (Conditional)

**New method 3**: `_sync_temp_workspace_for_agent(agent_id)`

```python
async def _sync_temp_workspace_for_agent(self, agent_id: str) -> None:
    """Ensure agent's temp workspace has latest snapshots from all agents."""
    agent = self.agents.get(agent_id)

    # Only sync if agent has filesystem enabled
    if not agent or not agent.backend.filesystem_manager:
        logger.info(f"[Orchestrator] Agent {agent_id} has no filesystem - skipping workspace sync")
        return

    # Temp workspace is already synced via save_snapshot mechanism
    # When agents save answers, their workspace files are copied to temp_workspaces
    # This agent's filesystem_manager already has access to those files
    logger.info(f"[Orchestrator] Temp workspace ready for {agent_id}")
```

**Important**: Workspace updates are **conditional**:
- If `agent.backend.filesystem_manager is None` → No workspace features → Don't mention in prompt
- If filesystem enabled → Include workspace update info in prompt

### 5. Loop Control Changes

**Key change**: Use `continue` instead of `return`

The `for attempt in range(max_attempts)` loop continues:
- Iteration N: Agent starts work
- Iteration N+1: `restart_pending` → inject update → continue
- Iteration N+2: Agent continues with update in conversation

## Benefits

### 1. Full Context Preservation ✅
- Agent keeps all its thinking
- No need to regenerate ideas
- Builds on its own partial work

### 2. Natural Collaboration ✅
```
Agent A: "I was creating a multi-page site with..."
📨 UPDATE: Agent B provided: "I created index.html..."
Agent A: "I see Agent B's index.html. I'll add CSS animations to enhance it..."
```

### 3. Workspace Continuity ✅
- Agent's own files preserved
- Can access other agents' new files
- Natural file-based collaboration

### 4. Simpler Code ✅
- No summary generation
- No context reconstruction
- No special state handling
- Just message injection

## Implementation Plan

### Phase 1: Helper Functions

1. **Create `_build_update_message(agent_id, answers)` method**
   - Format new answers with anonymous IDs
   - **Conditionally** include workspace info (only if filesystem enabled)
   - Return user message dict

2. **Create `_sync_temp_workspace_for_agent(agent_id)` method**
   - Check if agent has filesystem
   - Log sync status (actual sync already handled by existing code)

3. **Create `_inject_update_and_continue(agent_id, answers, conversation_messages)` method**
   - Build update message
   - Append to conversation_messages
   - Sync workspace if needed
   - Clear restart_pending flag
   - Return True (continue) or False (restart fallback)

### Phase 2: Update Restart Checks (Use Helper)

**Replace restart logic at ALL 9 locations** with helper call:

```python
# Old (repeated 9 times):
if self._check_restart_pending(agent_id):
    await self._handle_agent_restart(agent_id, answers)
    yield ("content", f"🔁 restarting\n")
    yield ("done", None)
    return

# New (single helper call):
if self._check_restart_pending(agent_id):
    should_continue = await self._inject_update_and_continue(agent_id, answers, conversation_messages)
    if should_continue:
        yield ("content", f"📨 [{agent_id}] receiving update\n")
        continue
    else:
        yield ("content", f"🔁 [{agent_id}] restarting (fallback)\n")
        yield ("done", None)
        return
```

**Locations to update**:
- orchestrator.py:~1991 (main location in iteration loop)
- orchestrator.py:~2130, 2161, 2207, 2241, 2289, 2313, 2341, 2380 (error handling paths)

### Phase 3: Cleanup (Remove Summary Code)

Since injection eliminates the need for summaries:

1. **Remove from `agent_config.py`**:
   - `capture_restart_summaries` field from CoordinationConfig
   - Update serialization methods

2. **Remove from `orchestrator.py`**:
   - `in_progress_summaries: Dict[str, str]`
   - `current_response` field from AgentState
   - `_generate_restart_summary()` method
   - Summary generation in reset_signal block
   - `_handle_agent_restart()` method (replaced by injection)

3. **Remove from `cli.py`**:
   - All `capture_restart_summaries` parsing (4 locations)

4. **Remove from `config_builder.py`**:
   - Interactive prompt for capture_restart_summaries

5. **Remove from `message_templates.py`**:
   - `format_work_in_progress()` method
   - `in_progress_summaries` parameter from message builders

### Phase 4: Testing

1. Test scenarios:
   - Fast agent provides answer → slow agent receives update mid-work
   - Multiple updates in sequence
   - Agent votes after seeing update
   - Agent improves answer after seeing update

2. Verify:
   - ✅ No context loss
   - ✅ Agents reference new answers
   - ✅ Workspace files accessible
   - ✅ Natural collaboration

## Edge Cases

### Case 1: Agent mid-tool-call
**Current behavior**: `restart_pending` check happens between iterations, not mid-tool
**Solution**: Same - wait for safe point (after tool response)

### Case 2: Multiple rapid updates
**Scenario**: Agent B answers → Agent C answers → Agent A still working
**Solution**:
- First update injected at safe point
- `restart_pending` stays True for second update
- Next iteration injects second update
- OR: Batch multiple updates into one message

### Case 3: Agent already decided to answer
**Scenario**: Agent A composed answer, about to call `new_answer`, update comes in
**Solution**:
- Injection happens
- Agent sees update before submitting
- Can revise decision

## Configuration

### Option 1: Always Use Injection (Recommended)
No config needed - just change behavior globally. Simpler and better.

### Option 2: Config Flag (If needed for migration)
```yaml
orchestrator:
  coordination:
    update_mode: "inject"  # or "restart" for legacy
```

**Recommendation**: Skip config, just use injection. It's strictly better.

## Comparison: Restart vs Injection

| Aspect | Restart (Old) | Injection (New) |
|--------|--------------|-----------------|
| Context preservation | ❌ Lost | ✅ Kept |
| Code complexity | High | Low |
| Agent experience | Jarring | Natural |
| Workspace files | Cleared | Preserved |
| Collaboration quality | Limited | Enhanced |
| Performance | Slower (overhead) | Faster |

## Success Criteria

1. ✅ Agent receives new answers while working
2. ✅ Agent continues with full context preserved
3. ✅ Agent can reference new answers in its work
4. ✅ Agent can access new workspace files
5. ✅ No infinite loops (existing limits apply)
6. ✅ Clear console feedback (📨 messages)

## Implementation Status

**STATUS: ✅ IMPLEMENTED** (2025-10-30)

The inject feature has been successfully implemented with the following behavior:

### What Works
- Agents receive updates via injection when `new_answer` is provided by other agents
- Agents continue their work with full context preserved (no restart from scratch)
- Only the triggering agent (who provided new_answer) and agents currently streaming receive injections
- Coordination tracker properly logs UPDATE_INJECTED events

### Race Condition Limitation
There is an intentional design limitation due to safe-point injection:

**Scenario**: Agent is deep in first response when new answer arrives
- The agent won't see the injection until it completes current response
- By the time it loops back, it may already have full context from orchestrator
- Result: Agent gets full context but via normal flow, not injection

**Why this is acceptable**:
- We can't interrupt agents mid-stream (would break their reasoning)
- Injections only happen at "safe points" (between iterations in the loop)
- Agent still gets the new context, just via different mechanism
- Final outcome is the same: agent has all answers

**Example from logs** (2025-10-30):
- gemini_agent provides answer at 17:03:20
- grok_agent gets injection at 17:03:23 ✅ (was streaming, hit safe point)
- openai_agent doesn't appear until 17:04:22 (started with 3 answers already)

This is working as designed - fast agents get injections, slow agents get full context on restart.

## Key Implementation Details

### Helper Functions (DRY Principle)

All 9 restart_pending locations will call the same helper function to avoid code duplication:

1. `_inject_update_and_continue()` - Main orchestrator
2. `_build_update_message()` - Message formatter (workspace-aware)
3. `_sync_temp_workspace_for_agent()` - Workspace sync (conditional)

### Workspace Conditional Logic

```python
# In _build_update_message:
agent = self.agents.get(agent_id)
has_workspace = agent and agent.backend.filesystem_manager is not None

if has_workspace:
    # Include workspace update instructions
else:
    # Skip workspace mentions - agent has no filesystem
```

This ensures:
- ✅ Agents with filesystem get workspace update info
- ✅ Agents without filesystem (text-only) don't see confusing workspace messages
- ✅ Works with all backend types (OpenAI, Claude, Gemini, etc.)

## Next Steps

1. Write design doc ✅ (this document)
2. Implement 3 helper functions in orchestrator.py
3. Update first restart_pending check (line ~1991) to use helper
4. Test with 2-agent scenario (1 with filesystem, 1 without)
5. Roll out helper to remaining 8 locations
6. Clean up summary code (agent_config, cli, config_builder, message_templates)
7. Test thoroughly with various scenarios
8. Update tests in `massgen/tests/`
9. Commit and create PR

---

**Decision**: Proceed with injection approach. Eliminates need for summaries entirely while providing superior agent collaboration.
