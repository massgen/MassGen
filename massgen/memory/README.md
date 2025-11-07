# MassGen Memory System

The MassGen memory system provides agents with the ability to store and recall information across conversations, enabling more contextual and intelligent interactions.

## Architecture

The memory system consists of three main components:

### 1. **ConversationMemory** - Short-term Memory
Fast in-memory storage for active conversations.

```python
from massgen.memory import ConversationMemory

# Initialize
memory = ConversationMemory()

# Add messages
await memory.add({"role": "user", "content": "Hello!"})
await memory.add({"role": "assistant", "content": "Hi there!"})

# Retrieve messages
messages = await memory.get_messages()
print(f"Stored {len(messages)} messages")

# Get last 10 messages only
recent = await memory.get_messages(limit=10)

# Filter by role
user_messages = await memory.get_messages_by_role("user")

# Manage memory size
await memory.truncate_to_size(100)  # Keep last 100 messages

# Clear all
await memory.clear()

# Save/load state
state = memory.state_dict()
# ... later ...
new_memory = ConversationMemory()
new_memory.load_state_dict(state)
```

### 2. **PersistentMemory** - Long-term Memory
Semantic memory storage using mem0 with vector search capabilities.

```python
from massgen.memory import PersistentMemory
from massgen.backend import OpenAIBackend

# Initialize with backends
llm_backend = OpenAIBackend(model="gpt-4")
embedding_backend = OpenAIBackend(model="text-embedding-3-small")

memory = PersistentMemory(
    agent_name="my_agent",
    llm_backend=llm_backend,
    embedding_backend=embedding_backend,
    on_disk=True  # Persist to disk
)

# Developer Interface: Record conversation
await memory.record([
    {"role": "user", "content": "My name is Alice"},
    {"role": "assistant", "content": "Nice to meet you, Alice!"}
])

# Developer Interface: Retrieve relevant memories
relevant = await memory.retrieve("What's the user's name?")
print(relevant)  # "Alice"

# Agent Tool Interface: Agent saves important info
result = await memory.save_to_memory(
    thinking="User shared personal information",
    content=["User's favorite color is blue", "User works as a teacher"]
)

# Agent Tool Interface: Agent recalls from memory
result = await memory.recall_from_memory(
    keywords=["favorite color", "job"],
    limit=5
)
for mem in result['memories']:
    print(mem)
```

### 3. **Memory Integration Modes**

#### Mode 1: Developer-Controlled (Automatic)
```python
# Framework automatically manages memory

class MyAgent:
    def __init__(self):
        self.conversation_memory = ConversationMemory()
        self.persistent_memory = PersistentMemory(
            agent_name="agent_1",
            llm_backend=llm,
            embedding_backend=embedding
        )

    async def chat(self, user_message):
        # Auto-add to conversation memory
        await self.conversation_memory.add({
            "role": "user",
            "content": user_message
        })

        # Auto-retrieve relevant long-term memories
        context = await self.persistent_memory.retrieve(user_message)

        # Build full context
        messages = await self.conversation_memory.get_messages()
        if context:
            messages.insert(0, {
                "role": "system",
                "content": f"Relevant memories: {context}"
            })

        # Generate response...
        response = await self.backend.chat(messages)

        # Auto-record response
        await self.conversation_memory.add({
            "role": "assistant",
            "content": response
        })

        # Optionally save important conversations to long-term memory
        await self.persistent_memory.record(messages)

        return response
```

#### Mode 2: Agent-Controlled (Tools)
```python
# Agent actively manages its own memory

# Register memory tools
tools = [
    {
        "name": "save_to_memory",
        "description": "Save important information for future reference",
        "parameters": {
            "thinking": "Why this information is important",
            "content": ["List of things to remember"]
        },
        "function": memory.save_to_memory
    },
    {
        "name": "recall_from_memory",
        "description": "Search long-term memory for information",
        "parameters": {
            "keywords": ["Keywords to search for"]
        },
        "function": memory.recall_from_memory
    }
]

# Agent can now call these tools during conversation
# Example agent reasoning:
# "The user mentioned their birthday. I should save this."
# -> Calls save_to_memory(thinking="...", content=["Birthday: March 15"])
```

## Installation

The memory system requires the mem0 library for persistent memory:

```bash
pip install mem0ai
```

## Vector Store Options

By default, PersistentMemory uses Qdrant for vector storage. You can configure other backends:

```python
from mem0.vector_stores.configs import VectorStoreConfig

# Custom vector store
vector_config = VectorStoreConfig(
    provider="qdrant",  # or "chroma", "pinecone", etc.
    config={
        "on_disk": True,
        "path": "./my_memories"
    }
)

memory = PersistentMemory(
    agent_name="agent_1",
    llm_backend=llm,
    embedding_backend=embedding,
    vector_store_config=vector_config
)
```

## Memory Organization

Memories are organized by metadata:

- **agent_name**: Isolate memories per agent
- **user_name**: Track user-specific information
- **session_name**: Separate different conversation sessions

```python
# Agent-specific memory
agent_memory = PersistentMemory(agent_name="research_agent")

# User-specific memory
user_memory = PersistentMemory(user_name="alice")

# Session-specific memory
session_memory = PersistentMemory(
    agent_name="agent_1",
    session_name="session_123"
)

# Combined filtering
memory = PersistentMemory(
    agent_name="agent_1",
    user_name="alice",
    session_name="2024-01-15"
)
```

## Best Practices

1. **Short-term for speed**: Use ConversationMemory for current dialogue
2. **Long-term for knowledge**: Use PersistentMemory for cross-session information
3. **Truncate regularly**: Keep conversation memory manageable
4. **Meaningful metadata**: Use descriptive agent/user/session names
5. **Selective persistence**: Only save important information to long-term memory

## Advanced: Custom mem0 Configuration

For full control over mem0 behavior:

```python
from mem0.configs.base import MemoryConfig
from mem0.configs.llms.configs import LlmConfig
from mem0.configs.embeddings.configs import EmbedderConfig

custom_mem0_config = MemoryConfig(
    llm=LlmConfig(provider="openai", config={"model": "gpt-4"}),
    embedder=EmbedderConfig(provider="openai", config={"model": "text-embedding-3-large"}),
    # ... other mem0 settings
)

memory = PersistentMemory(
    agent_name="agent_1",
    mem0_config=custom_mem0_config
)
```

## Troubleshooting

**Issue**: `ImportError: mem0 library is required`
- **Solution**: `pip install mem0ai`

**Issue**: Memories not persisting across restarts
- **Solution**: Ensure `on_disk=True` in PersistentMemory initialization

**Issue**: Out of memory errors
- **Solution**: Use `truncate_to_size()` on ConversationMemory regularly

**Issue**: Slow retrieval
- **Solution**: Reduce `limit` parameter in retrieve calls, or upgrade vector store

## Contributing

The memory system is designed to be extensible. To add new memory types:

1. Inherit from `MemoryBase` or `PersistentMemoryBase`
2. Implement required abstract methods
3. Add to `__init__.py` exports
