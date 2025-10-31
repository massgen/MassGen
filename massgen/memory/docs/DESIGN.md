# MassGen Memory System Design

## Overview

The MassGen memory system provides agents with both short-term conversation memory and long-term persistent memory capabilities. The design is inspired by how humans maintain working memory for immediate tasks while building long-term knowledge over time.

## Design Philosophy

1. **Layered Architecture**: Separate short-term (fast, ephemeral) from long-term (semantic, persistent) memory
2. **Async-First**: All operations are asynchronous for high performance
3. **Backend Agnostic**: Works with any MassGen-compatible LLM/embedding backend
4. **Dual Control**: Support both developer-controlled and agent-controlled memory management
5. **Serializable**: Enable session persistence and state recovery

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    MassGen Agent                             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────────────┐    ┌─────────────────────────┐ │
│  │ ConversationMemory     │    │ PersistentMemory        │ │
│  │ (Short-term)           │    │ (Long-term)             │ │
│  ├────────────────────────┤    ├─────────────────────────┤ │
│  │ - Fast in-memory list  │    │ - mem0 integration      │ │
│  │ - Current conversation │    │ - Vector search         │ │
│  │ - Temporary storage    │    │ - Semantic retrieval    │ │
│  │ - Session-scoped       │    │ - Cross-session         │ │
│  └────────────────────────┘    └─────────────────────────┘ │
│           │                              │                  │
│           ├──────────────┬───────────────┤                  │
│           │              │               │                  │
│  ┌────────▼────────┐  ┌─▼───────────┐ ┌─▼───────────────┐ │
│  │ Add messages    │  │ Retrieve    │ │ State mgmt      │ │
│  │ Get messages    │  │ context     │ │ Save/Load       │ │
│  │ Filter by role  │  │ memories    │ │ Serialize       │ │
│  │ Truncate size   │  │ Search      │ │ Persist         │ │
│  └─────────────────┘  └─────────────┘ └─────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Module Structure

```
massgen/memory/
├── __init__.py              # Public exports
├── _base.py                 # Abstract base classes
├── _conversation.py         # Short-term memory implementation
├── _persistent.py           # Long-term memory (mem0-based)
├── _mem0_adapters.py        # Adapters for MassGen backends
├── README.md                # User documentation
├── DESIGN.md                # This file
└── examples.py              # Usage examples
```

## Component Details

### 1. Base Classes (`_base.py`)

#### MemoryBase
Abstract interface for all memory types:
- `add()`: Store new items
- `delete()`: Remove items
- `retrieve()`: Query items
- `size()`: Get item count
- `clear()`: Remove all items
- `get_messages()`: Get formatted messages
- `state_dict()`: Serialize state
- `load_state_dict()`: Restore state

#### PersistentMemoryBase
Abstract interface for long-term memory:
- **Developer Interface**:
  - `record()`: Automatically save conversations
  - `retrieve()`: Automatically inject relevant context
- **Agent Interface** (Tools):
  - `save_to_memory()`: Agent explicitly saves info
  - `recall_from_memory()`: Agent queries memory

### 2. Conversation Memory (`_conversation.py`)

**Purpose**: Fast, in-memory storage for active conversations

**Key Features**:
- List-based storage for O(1) append
- Message ID generation for duplicate detection
- Index-based deletion
- Role-based filtering
- Size truncation
- State serialization

**Use Cases**:
- Maintaining chat history during a session
- Providing context window for LLM
- Temporary storage before persistence
- Quick message retrieval

**Memory Management**:
```python
# Automatic ID assignment
msg = {"role": "user", "content": "Hello"}
await memory.add(msg)  # ID auto-generated

# Duplicate prevention
await memory.add(same_msg)  # Skipped if allow_duplicates=False

# Size management
await memory.truncate_to_size(100)  # Keep last 100 messages
```

### 3. Persistent Memory (`_persistent.py`)

**Purpose**: Long-term semantic storage using mem0

**Key Features**:
- Vector-based semantic search
- Persistent storage across sessions
- Metadata-based organization (agent/user/session)
- Automatic summarization via mem0
- Dual control modes (developer + agent)

**Architecture**:
```
PersistentMemory
     │
     ├── MassGen LLM Backend ──▶ Mem0 LLM (via adapter)
     ├── MassGen Embedding ──▶ Mem0 Embedder (via adapter)
     └── mem0.AsyncMemory
             │
             ├── Vector Store (Qdrant/Chroma/Pinecone)
             ├── Metadata Store
             └── Memory Index
```

**Memory Organization**:
- `agent_id`: Separate memories per agent
- `user_id`: Track user-specific information
- `session_id`: Organize by conversation session

### 4. Mem0 Adapters (`_mem0_adapters.py`)

**Purpose**: Bridge MassGen backends to mem0's interface

#### MassGenLLMAdapter
- Converts MassGen LLM backend to mem0's `LLMBase`
- Handles async→sync conversion (mem0 limitation)
- Streams response and aggregates to string

#### MassGenEmbeddingAdapter
- Converts MassGen embedding backend to mem0's `EmbeddingBase`
- Handles batch embedding requests
- Returns vector representations

**Why Adapters?**
- mem0 has its own provider system
- MassGen backends don't natively match mem0's interface
- Adapters provide seamless integration

## Control Modes

### Mode 1: Developer-Controlled (Static)

Framework automatically manages memory:

```python
class Agent:
    async def chat(self, user_msg):
        # 1. Add to short-term
        await self.conv_memory.add({"role": "user", "content": user_msg})

        # 2. Retrieve from long-term
        context = await self.persist_memory.retrieve(user_msg)

        # 3. Build full context
        messages = await self.conv_memory.get_messages()
        if context:
            messages.insert(0, {"role": "system", "content": context})

        # 4. Generate response
        response = await self.backend.chat(messages)

        # 5. Save response to short-term
        await self.conv_memory.add({"role": "assistant", "content": response})

        # 6. Save important info to long-term
        await self.persist_memory.record(messages)

        return response
```

### Mode 2: Agent-Controlled (Dynamic)

Agent actively manages its memory via tools:

```python
# Register memory tools
tools = [
    {
        "name": "save_to_memory",
        "description": "Save important information",
        "function": memory.save_to_memory
    },
    {
        "name": "recall_from_memory",
        "description": "Search your memory",
        "function": memory.recall_from_memory
    }
]

# Agent decides when to use memory
# Example: Agent thinks "User mentioned birthday, should save this"
# -> Calls save_to_memory(thinking="...", content=["Birthday: March 15"])
```

### Mode 3: Hybrid

Combine both approaches:
- Framework handles routine memory operations
- Agent has tools for explicit memory management
- Best of both worlds

## Integration with mem0

### Why mem0?

1. **Mature vector search**: Proven semantic retrieval
2. **Multiple backends**: Support for Qdrant, Chroma, Pinecone
3. **Auto summarization**: Intelligent memory compression
4. **Metadata filtering**: Organize by agent/user/session
5. **Active community**: Regular updates and improvements

### Mem0 Configuration

```python
# Simple config (mem0 handles defaults)
memory = PersistentMemory(
    agent_name="my_agent",
    llm_backend=llm,
    embedding_backend=embedding
)

# Advanced config (full control)
from mem0.configs.base import MemoryConfig

custom_config = MemoryConfig(
    llm=...,
    embedder=...,
    vector_store=...,
    # ... other mem0 settings
)

memory = PersistentMemory(
    agent_name="my_agent",
    mem0_config=custom_config
)
```

### Mem0 Metadata Usage

```python
# Record with metadata
await memory._mem0_add(
    messages=[{"role": "user", "content": "..."}],
    # These become searchable metadata:
    agent_id="researcher",
    user_id="alice",
    run_id="session_123"
)

# Retrieve filters by metadata automatically
results = await memory.retrieve(query="...")
# Only returns memories matching agent_id/user_id/run_id
```

## State Management

### Conversation Memory State

```python
state = {
    "messages": [
        {"role": "user", "content": "...", "id": "msg_abc123"},
        {"role": "assistant", "content": "...", "id": "msg_def456"}
    ]
}
```

### Persistent Memory State

State is managed by mem0's vector store (Qdrant/etc):
- Vectors stored in vector DB
- Metadata in associated store
- No explicit state_dict() needed (handled by mem0)

## Performance Considerations

### Conversation Memory
- **Add**: O(1) - append to list
- **Get**: O(n) - iterate list
- **Delete**: O(n) - rebuild list
- **Search by role**: O(n) - linear scan

### Persistent Memory
- **Add**: O(1) amortized - vector indexing
- **Retrieve**: O(log n) - vector similarity search
- **Memory**: Scales with vector DB backend

### Optimization Tips
1. Truncate conversation memory regularly
2. Use metadata filters to narrow long-term search
3. Batch record operations when possible
4. Consider semantic vs procedural memory types

## Error Handling

```python
try:
    await memory.add(messages)
except TypeError as e:
    # Invalid message format
    logger.error(f"Message format error: {e}")

try:
    await persist_memory.retrieve(query)
except ImportError:
    # mem0 not installed
    logger.error("mem0 required: pip install mem0ai")

try:
    await persist_memory.record(messages)
except RuntimeError as e:
    # Backend error
    logger.error(f"Memory recording failed: {e}")
```

## Testing Strategy

1. **Unit Tests**:
   - Test each method in isolation
   - Mock backends for persistent memory
   - Verify state serialization

2. **Integration Tests**:
   - Test with real backends
   - Verify mem0 integration
   - Test cross-component workflows

3. **Performance Tests**:
   - Benchmark large conversations
   - Test vector search speed
   - Memory usage profiling

## Future Enhancements

### Planned Features
- [ ] Collaboration memory (agent-to-agent shared memory)
- [ ] Memory compression strategies
- [ ] Automatic important message detection
- [ ] Memory analytics and insights
- [ ] Memory export/import utilities
- [ ] Multi-modal memory (images, audio)

### Potential Improvements
- [ ] LRU cache for frequent retrievals
- [ ] Async batch operations
- [ ] Memory pruning strategies
- [ ] Cross-agent memory sharing protocols
- [ ] Privacy-preserving memory

## Migration from agentscope

Key differences from agentscope's memory:

| Aspect | agentscope | MassGen |
|--------|-----------|---------|
| Message format | `Msg` objects | `Dict[str, Any]` |
| Base class | `StateModule` | No dependency |
| Naming | `InMemoryMemory` | `ConversationMemory` |
| Naming | `Mem0LongTermMemory` | `PersistentMemory` |
| Adapters | `AgentScope*` | `MassGen*` |
| Tool names | `record_to_memory` | `save_to_memory` |
| Tool names | `retrieve_from_memory` | `recall_from_memory` |
| Documentation | Academic style | Practical examples |

## Conclusion

The MassGen memory system provides a robust foundation for building agents with both short-term and long-term memory capabilities. By leveraging mem0 for persistent storage and providing clean abstractions, it enables developers to create more contextual and intelligent agent systems.
