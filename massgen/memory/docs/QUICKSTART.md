# MassGen Memory - Quick Start Guide

Get up and running with MassGen memory in 5 minutes!

## Installation

```bash
# Install mem0 for persistent memory support
pip install mem0ai
```

## Basic Usage

### 1. Short-term Conversation Memory

Perfect for maintaining context during active chats:

```python
import asyncio
from massgen.memory import ConversationMemory

async def chat_example():
    # Create memory
    memory = ConversationMemory()

    # Add messages
    await memory.add({"role": "user", "content": "What's 2+2?"})
    await memory.add({"role": "assistant", "content": "2+2 equals 4."})

    # Get all messages
    messages = await memory.get_messages()
    print(f"Stored {len(messages)} messages")

    # Get only recent messages
    recent = await memory.get_messages(limit=10)

asyncio.run(chat_example())
```

**When to use**: Current conversation, temporary storage, quick message access

### 2. Long-term Persistent Memory

For cross-session knowledge retention:

```python
import asyncio
from massgen.memory import PersistentMemory

async def persistent_example():
    # NOTE: Replace with your actual backends
    from massgen.backend import YourLLMBackend, YourEmbeddingBackend

    llm = YourLLMBackend(model="gpt-4")
    embedding = YourEmbeddingBackend(model="text-embedding-3-small")

    # Create persistent memory
    memory = PersistentMemory(
        agent_name="my_assistant",
        llm_backend=llm,
        embedding_backend=embedding,
        on_disk=True  # Persist across restarts
    )

    # Record conversation
    await memory.record([
        {"role": "user", "content": "I love hiking in mountains"},
        {"role": "assistant", "content": "That sounds wonderful!"}
    ])

    # Later, retrieve relevant info
    context = await memory.retrieve("user's hobbies")
    print(f"Retrieved: {context}")  # "user loves hiking"

asyncio.run(persistent_example())
```

**When to use**: Long-term facts, cross-session knowledge, semantic search

## Common Patterns

### Pattern 1: Simple Chat Agent

```python
class SimpleChatAgent:
    def __init__(self, backend):
        self.backend = backend
        self.memory = ConversationMemory()

    async def chat(self, user_message):
        # Add user message
        await self.memory.add({"role": "user", "content": user_message})

        # Get context
        context = await self.memory.get_messages()

        # Generate response
        response = await self.backend.chat(context)

        # Save response
        await self.memory.add({"role": "assistant", "content": response})

        return response
```

### Pattern 2: Agent with Memory

```python
class SmartAgent:
    def __init__(self, llm_backend, embedding_backend):
        self.backend = llm_backend
        self.short_term = ConversationMemory()
        self.long_term = PersistentMemory(
            agent_name="smart_agent",
            llm_backend=llm_backend,
            embedding_backend=embedding_backend
        )

    async def chat(self, user_message):
        # 1. Add to short-term
        await self.short_term.add({"role": "user", "content": user_message})

        # 2. Get relevant long-term memories
        context = await self.long_term.retrieve(user_message)

        # 3. Build full context
        messages = await self.short_term.get_messages()
        if context:
            messages.insert(0, {
                "role": "system",
                "content": f"Relevant background: {context}"
            })

        # 4. Generate response
        response = await self.backend.chat(messages)

        # 5. Save to short-term
        await self.short_term.add({"role": "assistant", "content": response})

        # 6. Optionally save to long-term
        # (only if important)
        if self._is_important(response):
            await self.long_term.record(messages[-2:])

        return response

    def _is_important(self, message):
        # Implement your logic
        keywords = ["remember", "important", "fact", "name", "birthday"]
        return any(kw in message.lower() for kw in keywords)
```

### Pattern 3: Agent-Controlled Memory (Tools)

```python
class AutonomousAgent:
    def __init__(self, backend, embedding_backend):
        self.backend = backend
        self.memory = PersistentMemory(
            agent_name="autonomous",
            llm_backend=backend,
            embedding_backend=embedding_backend
        )

        # Register memory as tools
        self.tools = [
            {
                "name": "save_to_memory",
                "description": "Save important facts for later",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "thinking": {"type": "string"},
                        "content": {"type": "array", "items": {"type": "string"}}
                    }
                },
                "function": self.memory.save_to_memory
            },
            {
                "name": "recall_from_memory",
                "description": "Search your memory for information",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keywords": {"type": "array", "items": {"type": "string"}}
                    }
                },
                "function": self.memory.recall_from_memory
            }
        ]

    async def chat(self, user_message):
        # Agent can now decide when to save/recall memories
        response = await self.backend.chat(
            messages=[{"role": "user", "content": user_message}],
            tools=self.tools
        )

        # If agent called save_to_memory or recall_from_memory,
        # those functions will be executed automatically

        return response
```

## Configuration Options

### Conversation Memory

```python
memory = ConversationMemory()

# Truncate to last N messages
await memory.truncate_to_size(100)

# Get messages by role
user_msgs = await memory.get_messages_by_role("user")

# Save/restore state
state = memory.state_dict()
new_memory = ConversationMemory()
new_memory.load_state_dict(state)
```

### Persistent Memory

```python
# Basic configuration
memory = PersistentMemory(
    agent_name="agent_1",
    llm_backend=llm,
    embedding_backend=embedding
)

# With user tracking
memory = PersistentMemory(
    agent_name="agent_1",
    user_name="alice",
    llm_backend=llm,
    embedding_backend=embedding
)

# With session tracking
memory = PersistentMemory(
    agent_name="agent_1",
    session_name="2024-01-15",
    llm_backend=llm,
    embedding_backend=embedding
)

# Custom vector store
from mem0.vector_stores.configs import VectorStoreConfig

vector_config = VectorStoreConfig(
    provider="qdrant",
    config={
        "on_disk": True,
        "path": "./my_memory_db"
    }
)

memory = PersistentMemory(
    agent_name="agent_1",
    llm_backend=llm,
    embedding_backend=embedding,
    vector_store_config=vector_config
)
```

## Tips & Best Practices

### 1. Memory Management
```python
# Keep conversation memory manageable
if await memory.size() > 100:
    await memory.truncate_to_size(50)  # Keep last 50

# Or clear when starting new topic
await memory.clear()
```

### 2. Selective Persistence
```python
# Don't save everything to long-term memory
# Only save important information

if contains_important_info(message):
    await long_term.record([message])
```

### 3. Efficient Retrieval
```python
# Use specific queries for better results
context = await memory.retrieve("user's name and preferences")

# Instead of vague queries
# context = await memory.retrieve("information")  # Too broad
```

### 4. State Persistence
```python
import json

# Save state to file
state = memory.state_dict()
with open("memory_state.json", "w") as f:
    json.dump(state, f)

# Restore state from file
with open("memory_state.json", "r") as f:
    state = json.load(f)
new_memory = ConversationMemory()
new_memory.load_state_dict(state)
```

## Troubleshooting

### Problem: ImportError for mem0
```bash
# Solution: Install mem0
pip install mem0ai
```

### Problem: Memory not persisting
```python
# Make sure on_disk=True
memory = PersistentMemory(
    agent_name="agent_1",
    llm_backend=llm,
    embedding_backend=embedding,
    on_disk=True  # ← Important!
)
```

### Problem: Out of memory
```python
# Regularly truncate conversation memory
await conv_memory.truncate_to_size(100)

# Or clear when no longer needed
await conv_memory.clear()
```

### Problem: Slow retrieval
```python
# Reduce limit in retrieve calls
context = await memory.retrieve(query, limit=3)  # Instead of default 5

# Use more specific queries
# Good: "user's favorite color"
# Bad: "information about user"
```

## Next Steps

1. **Read the full documentation**: Check `README.md` for detailed API reference
2. **Explore examples**: Run `examples.py` to see more usage patterns
3. **Understand design**: Read `DESIGN.md` for architecture details
4. **Try it out**: Integrate memory into your agents!

## Complete Example

Here's a fully working example you can copy and run:

```python
import asyncio
from massgen.memory import ConversationMemory

async def complete_example():
    # Create memory
    memory = ConversationMemory()

    # Simulate a conversation
    print("Starting conversation...")

    await memory.add({"role": "user", "content": "Hi, I'm Alice"})
    await memory.add({"role": "assistant", "content": "Nice to meet you, Alice!"})
    await memory.add({"role": "user", "content": "What's my name?"})
    await memory.add({"role": "assistant", "content": "Your name is Alice."})

    # Show stored messages
    messages = await memory.get_messages()
    print(f"\n📚 Stored {len(messages)} messages:")
    for msg in messages:
        print(f"  {msg['role']}: {msg['content']}")

    # Show memory size
    size = await memory.size()
    print(f"\n📊 Memory size: {size} messages")

    # Get last message
    last = await memory.get_last_message()
    print(f"\n💬 Last message: {last['role']}: {last['content']}")

    # Save state
    state = memory.state_dict()
    print(f"\n💾 State saved: {len(state['messages'])} messages")

    print("\n✅ Example completed!")

if __name__ == "__main__":
    asyncio.run(complete_example())
```

Run this with:
```bash
python -m massgen.memory.examples  # Or save the code above
```

Happy coding! 🚀
