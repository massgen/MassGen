# Orchestrator Shared Memory Integration

## Overview

This document describes how the MassGen `Orchestrator` uses shared memory to enable collaboration between multiple agents. Unlike individual agents that maintain their own private memory, the Orchestrator provides shared memory that all coordinated agents can access and contribute to.

## Motivation

In multi-agent coordination scenarios, agents need to:
- Share findings and discoveries with each other
- Build on each other's work
- Avoid duplicating efforts
- Maintain a unified knowledge base

The shared memory system enables these capabilities by providing a common memory space that all agents can read from and write to.

## Architecture

The Orchestrator supports two types of shared memory:

1. **Shared ConversationMemory**: All agents see the same conversation history
2. **Shared PersistentMemory**: All agents contribute to and retrieve from shared long-term knowledge

```
┌─────────────────────────────────────────────────────────────────┐
│                       Orchestrator                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────────────┐    ┌─────────────────────────────┐ │
│  │ Shared Conversation    │    │ Shared Persistent           │ │
│  │ Memory (Optional)      │    │ Memory (Optional)           │ │
│  ├────────────────────────┤    ├─────────────────────────────┤ │
│  │ • Agent contributions  │    │ • Cross-session knowledge   │ │
│  │ • Shared insights      │    │ • Semantic search           │ │
│  │ • Agent attribution    │    │ • Long-term collaboration   │ │
│  └────────────────────────┘    └─────────────────────────────┘ │
│           ▲                              ▲                       │
│           │                              │                       │
│           │      Inject & Record         │                       │
│           │                              │                       │
│  ┌────────┴──────┐  ┌──────────┐  ┌────┴──────┐               │
│  │   Agent 1     │  │ Agent 2  │  │  Agent 3  │               │
│  │               │  │          │  │           │               │
│  │ Reads shared  │  │ Reads    │  │ Reads     │               │
│  │ memory before │  │ shared   │  │ shared    │               │
│  │ responding    │  │ memory   │  │ memory    │               │
│  │               │  │          │  │           │               │
│  │ Writes to     │  │ Writes   │  │ Writes    │               │
│  │ shared memory │  │ to shared│  │ to shared │               │
│  └───────────────┘  └──────────┘  └───────────┘               │
└─────────────────────────────────────────────────────────────────┘
```

## Implementation Details

### Initialization

The Orchestrator accepts shared memory instances during initialization:

```python
from massgen.orchestrator import Orchestrator
from massgen.memory import ConversationMemory, PersistentMemory

# Create shared memories
shared_conv_memory = ConversationMemory()
shared_persist_memory = PersistentMemory(
    user_id="team_workspace",
    agent_id="orchestrator"
)

# Create orchestrator with shared memories
orchestrator = Orchestrator(
    agents=agents_dict,
    shared_conversation_memory=shared_conv_memory,  # Optional
    shared_persistent_memory=shared_persist_memory   # Optional
)
```

Both parameters are optional - orchestrators can use:
- Only shared conversation memory
- Only shared persistent memory
- Both shared memories
- No shared memory (agents work independently)

### Memory Injection Workflow

When an agent is about to process a task, the Orchestrator injects shared memory context into the agent's messages through the `_inject_shared_memory_context()` method.

#### Method Signature

```python
async def _inject_shared_memory_context(
    self,
    messages: List[Dict[str, Any]],
    agent_id: str
) -> List[Dict[str, Any]]:
```

**Code location**: `massgen/orchestrator.py:330-399`

#### Injection Process

1. **Check if shared memory exists**
   - If no shared memory is configured, return original messages unchanged
   - This ensures orchestrators work fine without shared memory

2. **Retrieve Shared ConversationMemory** (if configured)
   - Fetches recent messages from shared conversation memory (last 10 messages)
   - Formats each message with agent attribution: `[agent_id]: content`
   - Creates a "SHARED CONVERSATION MEMORY" section

3. **Retrieve Shared PersistentMemory** (if configured)
   - Calls `retrieve()` to get semantically relevant long-term knowledge
   - Creates a "SHARED PERSISTENT MEMORY" section

4. **Inject into messages**
   - Adds a system message with the memory context
   - Inserts after the first system message (if exists) or at the beginning
   - Memory context is clearly labeled for the agent

#### Example Memory Injection

```python
# Original messages
messages = [
    {"role": "system", "content": "You are a helpful agent"},
    {"role": "user", "content": "Solve the problem"}
]

# After injection (example)
injected_messages = [
    {"role": "system", "content": "You are a helpful agent"},
    {
        "role": "system",
        "content": """
=== SHARED CONVERSATION MEMORY ===
[agent1]: I found that the issue is in module X
[agent2]: I've verified agent1's finding and tested a fix

=== SHARED PERSISTENT MEMORY ===
Historical context: Previous sessions show this is a recurring issue
"""
    },
    {"role": "user", "content": "Solve the problem"}
]
```

### Memory Recording Workflow

When an agent produces output, the Orchestrator records it to shared memory through the `_record_to_shared_memory()` method.

#### Method Signature

```python
async def _record_to_shared_memory(
    self,
    agent_id: str,
    content: str,
    role: str = "assistant"
) -> None:
```

**Code location**: `massgen/orchestrator.py:400-433`

#### Recording Process

1. **Create message with metadata**
   ```python
   message = {
       "role": role,
       "content": content,
       "agent_id": agent_id,
       "timestamp": time.time()
   }
   ```

2. **Add to Shared ConversationMemory** (if configured)
   - Stores the message in chronological order
   - Includes agent attribution
   - Errors are logged but don't interrupt workflow

3. **Record to Shared PersistentMemory** (if configured)
   - Records the message for long-term storage
   - Handles `NotImplementedError` gracefully
   - Errors are logged but don't interrupt workflow

### Integration with Agent Workflow

The Orchestrator integrates shared memory at key points in the agent coordination workflow:

#### 1. Before Agent Processes Task

**Code location**: `massgen/orchestrator.py:1474-1476`

```python
# Inject shared memory context before agent responds
conversation_messages = await self._inject_shared_memory_context(
    conversation_messages, agent_id
)
```

This happens right before the agent starts working on its task, ensuring it sees all shared knowledge.

#### 2. After Agent Votes

**Code location**: `massgen/orchestrator.py:1771-1775`

```python
# Record vote to shared memory
await self._record_to_shared_memory(
    agent_id=agent_id,
    content=vote_message,
    role="assistant"
)
```

When an agent votes for another agent's answer, the vote is recorded to shared memory so all agents can see voting activity.

#### 3. After Agent Provides New Answer

**Code location**: `massgen/orchestrator.py:1823-1827`

```python
# Record new answer to shared memory
await self._record_to_shared_memory(
    agent_id=agent_id,
    content=content,
    role="assistant"
)
```

When an agent produces a new answer, it's immediately shared with all other agents.

## Memory Visibility and Attribution

### Agent Attribution

Every message recorded to shared memory includes the `agent_id` field, which allows:
- Tracking which agent contributed what
- Proper attribution in memory injection
- Understanding collaboration patterns

### Cross-Agent Visibility

Key principle: **All agents see all shared memory**

- Agent A can see Agent B's contributions
- Agent B can see Agent C's findings
- Agent C can see both A and B's work

This creates a collaborative environment where agents build on each other's work.

### Example Collaboration Flow

```
Step 1: Agent1 analyzes the problem
  → Records to shared memory: "The issue is in the database connection"

Step 2: Agent2 receives task
  → Sees Agent1's finding in shared memory
  → Builds on it: "Confirmed. The connection pool is exhausted"
  → Records to shared memory

Step 3: Agent3 receives task
  → Sees both Agent1 and Agent2's findings
  → Provides solution: "Increased pool size to 50. Issue resolved"
  → Records to shared memory

Result: Efficient collaboration with no duplicate work
```

## Error Handling

The Orchestrator implements robust error handling for shared memory operations:

### Memory Retrieval Errors

```python
# Code location: massgen/orchestrator.py:353-356
try:
    conv_messages = await self.shared_conversation_memory.get_messages()
except Exception as e:
    logger.warning(f"Failed to retrieve shared conversation memory: {e}")
    conv_messages = []
```

- Errors during retrieval are logged
- Orchestrator continues with empty memory context
- Agents still receive their tasks

### Memory Recording Errors

```python
# Code location: massgen/orchestrator.py:420-423
try:
    await self.shared_conversation_memory.add(message)
except Exception as e:
    logger.warning(f"Failed to add to shared conversation memory: {e}")
```

- Recording failures are logged
- Workflow continues normally
- Other agents may miss this contribution but system remains stable

### NotImplementedError Handling

```python
# Code location: massgen/orchestrator.py:427-430
try:
    await self.shared_persistent_memory.record([message])
except NotImplementedError:
    pass  # Memory backend doesn't support record
```

- Gracefully handles unimplemented memory operations
- Allows using memory backends with partial functionality

## Usage Examples

### Example 1: Orchestrator with Shared ConversationMemory

```python
from massgen.orchestrator import Orchestrator
from massgen.memory import ConversationMemory
from massgen.chat_agent import SingleAgent

# Create agents
agents = {
    "analyzer": SingleAgent(backend=backend1, agent_id="analyzer"),
    "implementer": SingleAgent(backend=backend2, agent_id="implementer"),
    "reviewer": SingleAgent(backend=backend3, agent_id="reviewer")
}

# Create shared conversation memory
shared_memory = ConversationMemory()

# Create orchestrator
orchestrator = Orchestrator(
    agents=agents,
    shared_conversation_memory=shared_memory
)

# Use orchestrator - agents automatically share findings
async for chunk in orchestrator.chat(messages):
    print(chunk)

# Check what was shared
shared_messages = await shared_memory.get_messages()
for msg in shared_messages:
    print(f"[{msg['agent_id']}]: {msg['content']}")
```

### Example 2: Orchestrator with Shared PersistentMemory

```python
from massgen.orchestrator import Orchestrator
from massgen.memory import PersistentMemory
from massgen.chat_agent import SingleAgent

# Create agents
agents = {
    "agent1": SingleAgent(backend=backend, agent_id="agent1"),
    "agent2": SingleAgent(backend=backend, agent_id="agent2")
}

# Create shared persistent memory
shared_persist_memory = PersistentMemory(
    user_id="team_project_alpha",
    agent_id="orchestrator"
)

# Create orchestrator
orchestrator = Orchestrator(
    agents=agents,
    shared_persistent_memory=shared_persist_memory
)

# Session 1
messages1 = [{"role": "user", "content": "Design the API"}]
async for chunk in orchestrator.chat(messages1):
    print(chunk)

# Session 2 - agents remember previous session
messages2 = [{"role": "user", "content": "Implement the API we designed"}]
async for chunk in orchestrator.chat(messages2):
    print(chunk)
```

### Example 3: Orchestrator with Both Shared Memories

```python
from massgen.orchestrator import Orchestrator
from massgen.memory import ConversationMemory, PersistentMemory
from massgen.chat_agent import SingleAgent

# Create agents
agents = {
    "researcher": SingleAgent(backend=backend, agent_id="researcher"),
    "developer": SingleAgent(backend=backend, agent_id="developer"),
    "tester": SingleAgent(backend=backend, agent_id="tester")
}

# Create both shared memories
shared_conv_memory = ConversationMemory()
shared_persist_memory = PersistentMemory(
    user_id="project_gamma",
    agent_id="orchestrator"
)

# Create orchestrator with both
orchestrator = Orchestrator(
    agents=agents,
    shared_conversation_memory=shared_conv_memory,
    shared_persistent_memory=shared_persist_memory
)

# Benefits:
# - Current session: All agents see each other's work
# - Cross-session: Knowledge persists and accumulates over time
messages = [{"role": "user", "content": "Build a new feature"}]
async for chunk in orchestrator.chat(messages):
    print(chunk)
```

### Example 4: Orchestrator without Shared Memory

```python
from massgen.orchestrator import Orchestrator
from massgen.chat_agent import SingleAgent

# Create agents
agents = {
    "agent1": SingleAgent(backend=backend, agent_id="agent1"),
    "agent2": SingleAgent(backend=backend, agent_id="agent2")
}

# Create orchestrator without shared memory
orchestrator = Orchestrator(agents=agents)

# Agents work independently, no shared context
# Useful for independent parallel tasks
messages = [{"role": "user", "content": "Analyze this problem"}]
async for chunk in orchestrator.chat(messages):
    print(chunk)
```

## Memory Flow Diagram

```
┌─────────────────────────────────────────────────────────┐
│            User sends task to Orchestrator              │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│         Orchestrator assigns task to Agent 1            │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│    _inject_shared_memory_context(messages, "agent1")   │
│                                                         │
│  1. Retrieve from Shared ConversationMemory            │
│     └─ Get recent agent contributions                  │
│                                                         │
│  2. Retrieve from Shared PersistentMemory              │
│     └─ Get relevant long-term knowledge                │
│                                                         │
│  3. Inject into messages as system message             │
│     └─ Agent sees what others have found               │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│              Agent 1 processes task                     │
│                                                         │
│  • Sees shared memory context                          │
│  • Understands what others have done                   │
│  • Builds on previous findings                         │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│        Agent 1 produces answer/vote                     │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│   _record_to_shared_memory("agent1", content)          │
│                                                         │
│  1. Record to Shared ConversationMemory                │
│     └─ Add with agent_id and timestamp                 │
│                                                         │
│  2. Record to Shared PersistentMemory                  │
│     └─ Store for future sessions                       │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│         Next agent sees Agent 1's contribution          │
└─────────────────────────────────────────────────────────┘
```

## Key Differences from Agent Memory

| Feature | Agent Memory | Orchestrator Shared Memory |
|---------|-------------|---------------------------|
| **Scope** | Private to one agent | Shared across all agents |
| **Purpose** | Track agent's own conversation | Enable agent collaboration |
| **Visibility** | Only the agent sees it | All agents see all contributions |
| **Attribution** | Not needed | Agent ID tracked for each message |
| **Use Case** | Single-agent conversations | Multi-agent coordination |
| **Injection** | Automatic per agent | Orchestrator injects before tasks |
| **Recording** | Agent records own messages | Orchestrator records all agent outputs |

## Key Files

Implementation files:
- `massgen/orchestrator.py:73-100` - Orchestrator class definition
- `massgen/orchestrator.py:330-399` - Memory injection implementation
- `massgen/orchestrator.py:400-433` - Memory recording implementation
- `massgen/orchestrator.py:1474-1476` - Injection before agent task
- `massgen/orchestrator.py:1771-1827` - Recording after agent output

Test files:
- `massgen/tests/test_orchestrator_memory.py` - Comprehensive orchestrator memory tests

## Best Practices

1. **Choose Shared Memory Based on Task**:
   - Use Shared ConversationMemory for short-term collaboration tasks
   - Use Shared PersistentMemory for long-running projects across sessions
   - Use both for comprehensive team collaboration

2. **Memory Size Management**:
   - Shared ConversationMemory shows last 10 messages by default
   - Prevents overwhelming agents with too much context
   - For very large teams, consider more aggressive filtering

3. **Agent Attribution**:
   - Always check which agent contributed what
   - Use agent_id to track collaboration patterns
   - Attribution helps debug coordination issues

4. **Error Resilience**:
   - Shared memory failures don't crash the orchestrator
   - Agents can still work if memory is unavailable
   - Monitor logs for memory errors in production

5. **Privacy and Isolation**:
   - If agents need private memory, give them individual memories (not shared)
   - Shared memory is truly shared - all agents see everything
   - Consider task requirements when deciding to use shared memory

## Limitations

1. **Shared ConversationMemory**:
   - Shows last 10 messages only (hardcoded limit)
   - May miss earlier contributions in very long collaborations
   - No filtering by relevance, only recency

2. **Shared PersistentMemory**:
   - Retrieval is semantic and may not be perfect
   - All agents use the same user_id/agent_id for shared memory
   - No per-agent persistent memory isolation when using shared mode

3. **Scalability**:
   - Memory injection happens for every agent task
   - May add latency with many agents or large memory
   - No caching of memory context between agent calls

4. **Attribution Overhead**:
   - Agent attribution increases message size
   - More context tokens consumed by LLM
   - Formatting overhead for memory display

## Future Enhancements

- [ ] Configurable memory window size (currently hardcoded to 10)
- [ ] Relevance-based filtering instead of only recency
- [ ] Memory context caching to reduce retrieval overhead
- [ ] Per-agent memory isolation within orchestrator
- [ ] Memory compression for large collaborations
- [ ] Analytics on agent collaboration patterns
- [ ] Selective memory sharing (agent groups/permissions)
- [ ] Memory summarization for very long collaborations
