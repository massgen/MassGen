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

## Usage

### Zero Configuration Required!

Just use MassGen normally in multi-turn mode:

```bash
# Single agent with MCP
massgen --config @examples/mcp/discord_single.yaml

# Multi-agent with MCP
massgen --config @examples/mcp/discord_multi.yaml
```

### In Your Configuration Files

No changes needed! Works automatically:

```yaml
agents:
  - id: "discord_agent"
    backend:
      type: "claude_code"
      # No planning_mode setting needed!
      mcp_servers:
        discord:
          type: "stdio"
          command: "npx"
          args: ["-y", "mcp-discord"]
```

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

### Run the Demo

```bash
uv run python examples/intelligent_planning_mode_demo.py
```

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

## Future Enhancements

### 1. Tool-Specific Analysis
Instead of blocking all MCP tools, analyze per-tool:

```python
# Future feature
tool_permissions = {
    "discord_read": False,   # No planning mode
    "discord_send": True,    # Planning mode enabled
    "discord_delete": True,  # Planning mode enabled
}
```

### 2. Confidence Scoring
Use multiple agents for consensus:

```python
# Future feature
agents_agree = sum(agent.analyze(question) for agent in agents)
enable_planning = agents_agree >= threshold
```

### 3. Learning from History
Track accuracy and improve:

```python
# Future feature
if outcome_was_safe and planning_was_enabled:
    improve_analysis_prompt()
```

### 4. User Preferences
Allow users to override:

```yaml
# Future feature
orchestrator:
  risk_tolerance: "high"  # More read operations allowed
  custom_irreversibility_rules:
    - "send*": true
    - "read*": false
```

## Troubleshooting

### Issue: Planning mode always enabled

**Possible causes:**
1. Analysis failing (check logs)
2. No agents available
3. All responses parsing as "YES"

**Solution:**
```bash
# Enable debug logging to see what's happening
massgen --debug --config your_config.yaml
```

### Issue: Planning mode never enabled

**Possible causes:**
1. Analysis always returning "NO"
2. Agents not recognizing irreversible operations

**Solution:**
Check analysis prompt effectiveness, may need tuning

### Issue: Inconsistent behavior

**Possible causes:**
Random agent selection means different agents may analyze differently

**Solution:**
This is expected behavior - different perspectives are valuable

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
