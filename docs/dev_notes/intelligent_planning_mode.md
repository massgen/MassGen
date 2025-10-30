# Intelligent Planning Mode 🧠

> Automatically analyze questions to determine if MCP tools have irreversible outcomes, then dynamically enable/disable planning mode accordingly.

## Overview

Traditional planning mode blocks **all** MCP tool executions during the coordination phase. This is safe but overly restrictive - not all MCP tools have irreversible outcomes.

**Intelligent Planning Mode** solves this by:
1. 🔍 Analyzing each user question before coordination
2. 🤖 Using a randomly selected agent to determine if operations are irreversible
3. ⚡ Dynamically enabling/disabling planning mode for all agents
4. 👻 Operating completely transparently (users never see the analysis)

## The Problem

### Before: Static Planning Mode

```yaml
# Configuration file
agents:
  - id: "discord_agent"
    backend:
      type: "claude_code"
      planning_mode: true  # Blocks ALL MCP tools
```

**Issues:**
- ❌ Blocks read-only operations unnecessarily
- ❌ Agents can't access real data during coordination
- ❌ Less informed decision-making
- ❌ Manual configuration required

### After: Intelligent Planning Mode

```python
# No configuration needed - works automatically!
```

**Benefits:**
- ✅ Read operations allowed during coordination
- ✅ Write operations still blocked (safety maintained)
- ✅ Better informed agent decisions
- ✅ Fully automatic - zero configuration

## How It Works

### Reversible vs Irreversible Operations

#### Irreversible Operations (Planning Mode ENABLED)
- 📤 Sending messages (Discord, Slack, Twitter)
- 🗑️ Deleting files or data
- ✏️ Modifying external systems
- 📝 Creating permanent records
- ⚙️ Executing commands that change state

#### Reversible Operations (Planning Mode DISABLED)
- 📥 Reading messages or data
- 🔍 Searching or querying information
- 📋 Listing files or resources
- 🌐 Fetching data from APIs
- 👀 Viewing channel information
- 📖 Any read-only operation

### The Analysis Flow

```
┌─────────────────────────────────────────────────────────────┐
│ User asks: "Show me the last 10 Discord messages"          │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ Orchestrator: [Silently selects random agent for analysis] │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ Selected Agent: "NO - this is a read-only operation"       │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ Planning Mode: DISABLED for all agents                     │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ Coordination: Agents CAN read Discord messages             │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│ Result: Better informed decisions with real data           │
└─────────────────────────────────────────────────────────────┘
```

## Examples

### Example 1: Reading Discord Messages ✅

```bash
You: Show me the last 10 messages from #general
```

**What happens:**
1. Agent analyzes: "This is reading (reversible)" → **NO**
2. Planning mode: **DISABLED**
3. Agents can read messages during coordination
4. Result: Accurate responses based on actual data

**Log output:**
```
[ORCHESTRATOR] Analyzing question irreversibility
  analyzer_agent: agent2
  question_preview: Show me the last 10 messages...

[ORCHESTRATOR] Irreversibility analysis complete
  response: NO
  has_irreversible: False

[ORCHESTRATOR] Set planning mode for agent1
  planning_mode_enabled: False
```

### Example 2: Sending Discord Messages 🛡️

```bash
You: Send 'Hello everyone!' to #general
```

**What happens:**
1. Agent analyzes: "This sends a message (irreversible)" → **YES**
2. Planning mode: **ENABLED**
3. Agents cannot send during coordination
4. Result: Message sent only in final presentation (safe)

**Log output:**
```
[ORCHESTRATOR] Analyzing question irreversibility
  analyzer_agent: agent1
  question_preview: Send 'Hello everyone!' to...

[ORCHESTRATOR] Irreversibility analysis complete
  response: YES
  has_irreversible: True

[ORCHESTRATOR] Set planning mode for agent1
  planning_mode_enabled: True
```

### Example 3: Mixed Operations 🔒

```bash
You: Read the latest messages and send a summary to #general
```

**What happens:**
1. Agent analyzes: "Contains sending (irreversible)" → **YES**
2. Planning mode: **ENABLED** (safe default)
3. All operations blocked during coordination
4. Result: Everything happens in final presentation

### Multi-Turn Conversations

The analysis happens **every turn**:

```
Turn 1:
You: What channels are available?
→ Planning mode: DISABLED (read-only)

Turn 2:
You: Send a message to #general
→ Planning mode: ENABLED (irreversible)

Turn 3:
You: Show me the message history
→ Planning mode: DISABLED (read-only)
```

## Testing

### Run the Test Suite

```bash
uv run pytest massgen/tests/test_intelligent_planning_mode.py -v
```

**Test Coverage:**
- ✅ Irreversible operations enable planning mode
- ✅ Reversible operations disable planning mode
- ✅ Planning mode set on all agents
- ✅ Errors default to safe mode
- ✅ Random agent selection
- ✅ Response parsing handles mixed text

## Implementation Details

### Core Method: `_analyze_question_irreversibility()`

**Location:** `massgen/orchestrator.py`

**Process:**
1. Randomly select an available agent
2. Send specialized analysis prompt
3. Parse YES/NO response
4. Return boolean result
5. Default to True (safe mode) on errors

### Integration Points

**In `chat()` method:**
- Before initial coordination (new task)
- Before follow-up handling (multi-turn)

**Planning mode setting:**
```python
for agent_id, agent in self.agents.items():
    if hasattr(agent.backend, 'set_planning_mode'):
        agent.backend.set_planning_mode(has_irreversible)
```

### Error Handling

**Safe defaults:**
- Analysis failure → Planning mode **ENABLED**
- No agents available → Planning mode **ENABLED**
- Parse error → Planning mode **ENABLED**

**Rationale:** Better to be overly cautious than risk irreversible actions.

## Logging & Debugging

### Enable Debug Logging

```bash
massgen --debug --config your_config.yaml
```

### What Gets Logged

1. **Analysis initiation:**
   - Which agent was selected
   - Question preview

2. **Analysis result:**
   - Agent's response
   - Irreversibility determination

3. **Planning mode changes:**
   - Which agents affected
   - New planning mode state
   - Reason for change

### Example Log Output

```
[2025-10-20 14:30:45] [ORCHESTRATOR] Analyzing question irreversibility
  analyzer_agent: discord_agent_2
  question_preview: Show me the last 10 messages from #general

[2025-10-20 14:30:46] [ORCHESTRATOR] Irreversibility analysis complete
  analyzer_agent: discord_agent_2
  response: NO
  has_irreversible: False

[2025-10-20 14:30:46] [ORCHESTRATOR] Set planning mode for discord_agent_1
  planning_mode_enabled: False
  reason: irreversibility analysis

[2025-10-20 14:30:46] [ORCHESTRATOR] Set planning mode for discord_agent_2
  planning_mode_enabled: False
  reason: irreversibility analysis
```

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    Orchestrator                         │
│                                                         │
│  ┌───────────────────────────────────────────────┐    │
│  │ _analyze_question_irreversibility()           │    │
│  │  - Randomly selects agent                     │    │
│  │  - Sends analysis prompt                      │    │
│  │  - Parses YES/NO response                     │    │
│  │  - Returns boolean result                     │    │
│  └───────────────────────────────────────────────┘    │
│                        ↓                               │
│  ┌───────────────────────────────────────────────┐    │
│  │ chat() / _handle_followup()                   │    │
│  │  - Calls analysis before coordination         │    │
│  │  - Sets planning mode for all agents          │    │
│  │  - Continues with coordination                │    │
│  └───────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│                   All Agent Backends                    │
│  ┌───────────────┐  ┌───────────────┐  ┌────────────┐ │
│  │ set_planning_ │  │ is_planning_  │  │ _execute_  │ │
│  │ mode()        │  │ mode_enabled()│  │ mcp_func() │ │
│  └───────────────┘  └───────────────┘  └────────────┘ │
└─────────────────────────────────────────────────────────┘
```

## Selective Tool Blocking Implementation

### Overview
This following section describes the implementation of selective MCP tool blocking during planning mode. Instead of blocking ALL MCP tools when irreversible operations are detected, the system can now selectively block only specific tools while allowing read-only operations to proceed.

### Architecture

#### 1. Core Backend Support (`massgen/backend/base.py`)

Added to `LLMBackend` class:
- `_planning_mode_blocked_tools: set` - Stores specific tool names to block
- `set_planning_mode_blocked_tools(tool_names: set)` - Set tools to block
- `get_planning_mode_blocked_tools() -> set` - Get currently blocked tools
- `is_mcp_tool_blocked(tool_name: str) -> bool` - Check if specific tool is blocked

**Blocking Logic:**
- Planning mode disabled → All tools allowed
- Planning mode enabled + empty blocked_tools → Block ALL tools (backward compatible)
- Planning mode enabled + specific blocked_tools → Block only listed tools

#### 2. Question Analysis (`massgen/orchestrator.py`)

Modified `_analyze_question_irreversibility()`:
- **Return type changed:** `bool` → `Dict[str, Any]`
- **Returns:** `{"has_irreversible": bool, "blocked_tools": set}`
- **Enhanced prompt:** Asks LLM to identify specific MCP tools to block
- **Isolated Workspace Detection:** Automatically detects if agents have isolated workspaces (directories with "workspace" in name)
- **Filesystem Exception:** When isolated workspaces are detected, filesystem operations are NOT blocked as they're contained within temporary sandboxes
- **Response format:**
  ```
  IRREVERSIBLE: YES/NO
  BLOCKED_TOOLS: mcp__discord__discord_send, mcp__twitter__post_tweet
  ```

Modified `chat()` method:
- Unpacks analysis result to get both flag and tool list
- Sets both planning mode and blocked tools on all agents

#### 3. MCP Execution Layer (`massgen/backend/base_with_mcp.py`)

Modified `_execute_mcp_function_with_retry()`:
- Changed from `if self.is_planning_mode_enabled()` to `if self.is_mcp_tool_blocked(function_name)`
- Now checks specific tool blocking instead of blanket blocking
- Provides specific error message naming the blocked tool

### Example Usage

#### Scenario 1: Block ALL MCP tools (Backward Compatible)
```python
backend.set_planning_mode(True)
backend.set_planning_mode_blocked_tools(set())  # Empty set

# Result: ALL MCP tools blocked
backend.is_mcp_tool_blocked("mcp__discord__discord_send")  # True
backend.is_mcp_tool_blocked("mcp__discord__discord_read_channel")  # True
```

#### Scenario 2: Selective Blocking
```python
backend.set_planning_mode(True)
backend.set_planning_mode_blocked_tools({
    "mcp__discord__discord_send",
    "mcp__twitter__post_tweet"
})

# Result: Only specified tools blocked
backend.is_mcp_tool_blocked("mcp__discord__discord_send")  # True (blocked)
backend.is_mcp_tool_blocked("mcp__discord__discord_read_channel")  # False (allowed)
backend.is_mcp_tool_blocked("mcp__twitter__search_tweets")  # False (allowed)
```

#### Scenario 3: Planning Mode Disabled
```python
backend.set_planning_mode(False)

# Result: ALL tools allowed regardless of blocked_tools set
backend.is_mcp_tool_blocked("mcp__discord__discord_send")  # False
backend.is_mcp_tool_blocked("any_tool")  # False
```

## Real-World Example

### Example 1: User Question with Isolated Workspace

**User Question:** "Create a Python script that reads data.json and generates a report"

**System Detects:**
- Agents have isolated workspaces (e.g., `/tmp/massgen_workspace_agent1/`)
- Filesystem operations are within isolated sandboxes

**Analysis Result:**
```python
{
    "has_irreversible": False,  # No irreversible operations
    "blocked_tools": set()      # No tools blocked
}
```

**Behavior:**
1. Planning mode DISABLED (no irreversible operations)
2. Agents can freely use all filesystem tools ✅
3. Files created in isolated workspace are temporary and safe
4. No coordination restrictions needed

### Example 2: Discord Message with Isolated Workspace

**User Question:** "Send a message to #general saying 'Hello' and create a log file"

**System Detects:**
- Agents have isolated workspaces
- Request involves Discord message (external system) + file creation (isolated workspace)

**Analysis Result:**
```python
{
    "has_irreversible": True,
    "blocked_tools": {"mcp__discord__discord_send"}  # Only block Discord send
}
```

**Behavior:**
1. Planning mode ENABLED for coordination
2. Agent can create log file in workspace ✅ (isolated, safe)
3. Agent can read Discord channels ✅ (read-only)
4. Agent cannot send Discord message 🚫 (blocked - external system)
5. After coordination, planning mode disabled
6. Agent executes plan including sending message ✅

### Example 3: No Isolated Workspace (Traditional Behavior)

**User Question:** "Write a configuration file to /etc/myapp/config.yaml"

**System Detects:**
- No isolated workspaces detected
- Filesystem operation targets external system path

**Analysis Result:**
```python
{
    "has_irreversible": True,
    "blocked_tools": {"mcp__filesystem__write_file"}
}
```

**Behavior:**
1. Planning mode enabled for coordination
2. Agent cannot write to /etc/myapp ✅ (blocked during planning)
3. Agent plans the configuration structure
4. After coordination, planning mode disabled
5. Agent writes the actual file ✅

## Benefits

1. **Better Coordination:** Agents can gather information during planning phase
2. **Safer Execution:** Still prevents irreversible actions during coordination
3. **Workspace-Aware:** Automatically detects isolated workspaces and allows safe operations
4. **Flexible Sandbox:** Agents can use temporary workspaces freely without restrictions
5. **Backward Compatible:** Empty blocked set behaves like before (block all)
6. **Smart Analysis:** LLM determines which tools are irreversible based on context
7. **Transparent:** Clear logging shows which tools are blocked and why


## Related Documentation

- 📖 [Multi-Turn Mode](../docs/source/user_guide/multi_turn_mode.rst)
- 📖 [MCP Integration](../docs/source/user_guide/mcp_integration.rst)
- 📖 [Implementation Details](../docs/dev_notes/intelligent_planning_mode.md)
- 🧪 [Test Suite](../massgen/tests/test_intelligent_planning_mode.py)
- 🎬 [Demo Script](../examples/intelligent_planning_mode_demo.py)

## Contributing

Want to improve the analysis logic? Here's how:

1. **Customize the prompt:** Edit `_analyze_question_irreversibility()` in `orchestrator.py`
2. **Add new test cases:** Add to `test_intelligent_planning_mode.py`
3. **Improve parsing:** Enhance YES/NO detection logic
4. **Add confidence scoring:** Implement multi-agent consensus

## License

Same as MassGen project license.
