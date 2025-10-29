# Agent Memory Integration

## Overview

This document describes how MassGen agents (`SingleAgent` and `ConfigurableAgent`) integrate with the memory system to maintain conversation history and long-term knowledge.

## Architecture

Agents can use two types of memory:

1. **ConversationMemory**: Stores short-term conversation history for the current session
2. **PersistentMemory**: Stores long-term knowledge that persists across sessions

```
┌─────────────────────────────────────────────────────────────┐
│                     MassGen Agent                            │
│                 (SingleAgent/ConfigurableAgent)              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────────────┐    ┌─────────────────────────┐ │
│  │ ConversationMemory     │    │ PersistentMemory        │ │
│  │ (Optional)             │    │ (Optional)              │ │
│  ├────────────────────────┤    ├─────────────────────────┤ │
│  │ • Message history      │    │ • Retrieve context      │ │
│  │ • Add new messages     │    │ • Record interactions   │ │
│  │ • Clear history        │    │ • Cross-session memory  │ │
│  └────────────────────────┘    └─────────────────────────┘ │
│           ▲                              ▲                  │
│           │                              │                  │
│           └──────────┬───────────────────┘                  │
│                      │                                      │
│              ┌───────▼────────┐                             │
│              │  Agent.chat()  │                             │
│              │                │                             │
│              │ 1. Retrieve    │                             │
│              │ 2. Process     │                             │
│              │ 3. Record      │                             │
│              └────────────────┘                             │
└─────────────────────────────────────────────────────────────┘
```

## Implementation Details

### Initialization

Agents accept memory instances during initialization:

```python
from massgen.chat_agent import SingleAgent
from massgen.memory import ConversationMemory, PersistentMemory

# Create memory instances
conv_memory = ConversationMemory()
persist_memory = PersistentMemory(
    user_id="user_123",
    agent_id="agent_1"
)

# Initialize agent with memories
agent = SingleAgent(
    backend=backend,
    agent_id="my_agent",
    conversation_memory=conv_memory,      # Optional
    persistent_memory=persist_memory       # Optional
)
```

Both memory parameters are optional - agents can use:
- Only conversation memory
- Only persistent memory
- Both memories
- No memory (stateless operation)

### Memory Lifecycle During Chat

When the agent's `chat()` method is called, the following memory operations occur:

#### 1. Pre-Processing: Memory Retrieval

**ConversationMemory** (if configured):
- Handles conversation history automatically based on `clear_history` and `reset_chat` flags
- If `clear_history=True`: Clears conversation memory before processing
- If `reset_chat=True`: Resets conversation memory before processing

**PersistentMemory** (if configured):
- Retrieves relevant context from long-term memory
- Context is based on the current messages being processed
- Retrieved context is injected into the message flow

```python
# Code location: massgen/chat_agent.py:325-327
if self.persistent_memory:
    try:
        memory_context = await self.persistent_memory.retrieve(messages)
```

#### 2. Processing: Message Handling

During chat:
- Agent processes messages with injected memory context
- ConversationMemory tracks the conversation flow
- PersistentMemory context helps inform agent responses

#### 3. Post-Processing: Memory Recording

**ConversationMemory** (if configured):
- Records all user and assistant messages
- Maintains chronological conversation history
- Messages are stored with role and content

```python
# Code location: massgen/chat_agent.py:250-253
if self.conversation_memory:
    try:
        await self.conversation_memory.add(messages_to_record)
```

**PersistentMemory** (if configured):
- Records the interaction for long-term storage
- Messages are semantically indexed for future retrieval
- Supports cross-session knowledge building

```python
# Code location: massgen/chat_agent.py:257-259
if self.persistent_memory:
    try:
        await self.persistent_memory.record(messages_to_record)
```

### Memory State Management

#### Clearing Memory

Agents provide a `reset()` method to clear conversation memory:

```python
# Clear conversation memory
await agent.reset()
```

This only affects ConversationMemory - PersistentMemory is preserved across resets.

#### Chat Flags

The `chat()` method supports flags for memory control:

- **`clear_history=True`**: Clears conversation memory before processing new messages
- **`reset_chat=True`**: Resets the conversation memory state

```python
# Start a new conversation, clearing previous history
async for chunk in agent.chat(messages, clear_history=True):
    # Process chunks
    pass

# Reset chat state
async for chunk in agent.chat(messages, reset_chat=True):
    # Process chunks
    pass
```

## Error Handling

The agent implementation includes robust error handling for memory operations:

### ConversationMemory Errors

If ConversationMemory operations fail:
- The error is caught silently
- Agent continues operation without conversation memory
- User interaction is not interrupted

```python
# Code location: massgen/chat_agent.py:252-254
try:
    await self.conversation_memory.add(messages_to_record)
except Exception:
    pass  # Fail silently to not interrupt chat
```

### PersistentMemory Errors

If PersistentMemory operations fail or raise `NotImplementedError`:
- The error is caught
- Agent continues without persistent memory features
- User interaction proceeds normally

```python
# Code location: massgen/chat_agent.py:259-261
try:
    await self.persistent_memory.record(messages_to_record)
except (Exception, NotImplementedError):
    pass  # Fail silently
```

## Usage Examples

### Example 1: Agent with ConversationMemory Only

```python
from massgen.chat_agent import SingleAgent
from massgen.memory import ConversationMemory

# Create conversation memory
conv_memory = ConversationMemory()

# Create agent
agent = SingleAgent(
    backend=backend,
    conversation_memory=conv_memory
)

# First conversation
messages1 = [{"role": "user", "content": "Hello!"}]
async for chunk in agent.chat(messages1):
    print(chunk)

# Second conversation - remembers first conversation
messages2 = [{"role": "user", "content": "What did I say earlier?"}]
async for chunk in agent.chat(messages2):
    print(chunk)

# Check conversation history
history = await conv_memory.get_messages()
print(f"Conversation has {len(history)} messages")
```

### Example 2: Agent with PersistentMemory Only

```python
from massgen.chat_agent import SingleAgent
from massgen.memory import PersistentMemory

# Create persistent memory
persist_memory = PersistentMemory(
    user_id="user_123",
    agent_id="assistant"
)

# Create agent
agent = SingleAgent(
    backend=backend,
    persistent_memory=persist_memory
)

# Chat with long-term memory
messages = [{"role": "user", "content": "Remember that I like Python"}]
async for chunk in agent.chat(messages):
    print(chunk)

# Later session - memory persists
messages2 = [{"role": "user", "content": "What programming language do I like?"}]
async for chunk in agent.chat(messages2):
    print(chunk)
```

### Example 3: Agent with Both Memories

```python
from massgen.chat_agent import SingleAgent
from massgen.memory import ConversationMemory, PersistentMemory

# Create both memory types
conv_memory = ConversationMemory()
persist_memory = PersistentMemory(
    user_id="user_123",
    agent_id="assistant"
)

# Create agent with both memories
agent = SingleAgent(
    backend=backend,
    conversation_memory=conv_memory,
    persistent_memory=persist_memory
)

# Benefits:
# - Short-term: Full conversation context in current session
# - Long-term: Knowledge persists across sessions
messages = [{"role": "user", "content": "My name is Alice"}]
async for chunk in agent.chat(messages):
    print(chunk)
```

### Example 4: ConfigurableAgent with Memory

```python
from massgen.chat_agent import ConfigurableAgent
from massgen.agent_config import AgentConfig
from massgen.memory import ConversationMemory, PersistentMemory

# Create agent configuration
config = AgentConfig(
    agent_id="my_configurable_agent",
    backend_params={"model": "gpt-4o-mini"}
)

# Create memories
conv_memory = ConversationMemory()
persist_memory = PersistentMemory(
    user_id="user_123",
    agent_id="my_configurable_agent"
)

# Create configurable agent with memory
agent = ConfigurableAgent(
    config=config,
    backend=backend,
    conversation_memory=conv_memory,
    persistent_memory=persist_memory
)

# Use exactly like SingleAgent
messages = [{"role": "user", "content": "Hello!"}]
async for chunk in agent.chat(messages):
    print(chunk)
```

## Memory Flow Diagram

```
User Message
    │
    ▼
┌───────────────────────────────────────────┐
│         Agent.chat() Called                │
└───────────────────────────────────────────┘
    │
    ├─── Check clear_history/reset_chat flags
    │         │
    │         ├─── If clear_history: Clear ConversationMemory
    │         └─── If reset_chat: Reset ConversationMemory
    │
    ├─── Retrieve from PersistentMemory
    │         │
    │         └─── Inject context into messages
    │
    ├─── Process messages with LLM backend
    │         │
    │         └─── Generate response
    │
    └─── Record to Memories
              │
              ├─── Add to ConversationMemory
              │         └─── Store user + assistant messages
              │
              └─── Record to PersistentMemory
                        └─── Store for long-term retrieval
```

## Key Files

Implementation files:
- `massgen/chat_agent.py:33-41` - Memory initialization in ChatAgent base class
- `massgen/chat_agent.py:250-261` - Memory recording logic
- `massgen/chat_agent.py:298-310` - Clear history and reset chat logic
- `massgen/chat_agent.py:325-327` - Persistent memory retrieval
- `massgen/chat_agent.py:397-398` - Reset method

Test files:
- `massgen/tests/test_agent_memory.py` - Comprehensive agent memory tests

## Best Practices

1. **Choose the Right Memory Type**:
   - Use ConversationMemory for multi-turn conversations within a session
   - Use PersistentMemory for knowledge that should persist across sessions
   - Use both for comprehensive memory management

2. **Handle Memory Gracefully**:
   - Both memory types are optional
   - Agents work fine without memory (stateless mode)
   - Memory failures don't crash the agent

3. **Clear Memory When Needed**:
   - Use `clear_history=True` to start fresh conversations
   - Use `reset_chat=True` to reset conversation state
   - Call `agent.reset()` to explicitly clear conversation memory

4. **Memory Scope**:
   - ConversationMemory is session-scoped (cleared on reset)
   - PersistentMemory is user/agent-scoped (persists across sessions)

## Limitations

1. **ConversationMemory**:
   - Not persistent across agent restarts
   - Memory grows indefinitely unless cleared
   - Stored in-memory (not suitable for very long conversations)

2. **PersistentMemory**:
   - Requires additional setup (mem0, embedding model)
   - Retrieval is semantic, not exact
   - May not retrieve all relevant context

3. **Error Handling**:
   - Memory errors are silently caught
   - No explicit feedback to user when memory operations fail
   - Debugging memory issues requires logging inspection

## Future Enhancements

- [ ] Memory size limits and automatic truncation for ConversationMemory
- [ ] Explicit error handling modes (silent vs. explicit)
- [ ] Memory statistics and monitoring
- [ ] Selective memory clearing (by role, time range, etc.)
- [ ] Memory compression for long conversations
- [ ] Agent-controlled memory management (tools to add/remove/search memory)
