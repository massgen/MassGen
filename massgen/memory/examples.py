# -*- coding: utf-8 -*-
"""
Usage examples for MassGen memory system.

These examples demonstrate how to use conversation and persistent memory
in your MassGen agents.
"""

import asyncio


async def example_conversation_memory():
    """Example: Using ConversationMemory for short-term dialogue."""
    from massgen.memory import ConversationMemory

    print("=" * 60)
    print("Example 1: Conversation Memory (Short-term)")
    print("=" * 60)

    memory = ConversationMemory()

    # Simulate a conversation
    conversation = [
        {"role": "user", "content": "Hello! My name is Alice."},
        {"role": "assistant", "content": "Hi Alice! How can I help you today?"},
        {"role": "user", "content": "I'm interested in learning about Python."},
        {
            "role": "assistant",
            "content": "Great! Python is a versatile programming language...",
        },
    ]

    # Add messages one by one
    for msg in conversation:
        await memory.add(msg)
        print(f"Added: {msg['role']} - {msg['content'][:50]}...")

    # Get all messages
    await memory.get_messages()
    print(f"\nTotal messages: {await memory.size()}")

    # Get last message
    last = await memory.get_last_message()
    print(f"Last message role: {last['role']}")

    # Filter by role
    user_messages = await memory.get_messages_by_role("user")
    print(f"User messages: {len(user_messages)}")

    # Truncate to keep only recent messages
    await memory.truncate_to_size(2)
    print(f"After truncation: {await memory.size()} messages")

    # Save and restore state
    state = memory.state_dict()
    print(f"\nState saved: {len(state['messages'])} messages")

    # Create new memory from state
    restored_memory = ConversationMemory()
    restored_memory.load_state_dict(state)
    print(f"State restored: {await restored_memory.size()} messages")

    print("\n✅ Conversation memory example completed!\n")


async def example_persistent_memory():
    """
    Example: Using PersistentMemory for long-term storage.

    Note: This requires mem0 to be installed and proper backends configured.
    This is a conceptual example - adjust backends as needed.
    """
    print("=" * 60)
    print("Example 2: Persistent Memory (Long-term)")
    print("=" * 60)

    # NOTE: This is a conceptual example
    # In practice, you need to provide actual MassGen backends
    print("\n⚠️  This example requires actual LLM and embedding backends.")
    print("     Uncomment and configure backends to run this example.\n")

    # Conceptual usage:
    """
    from massgen.memory import PersistentMemory
    from massgen.backend import OpenAIBackend  # Or your backend

    # Initialize backends
    llm_backend = OpenAIBackend(model="gpt-4")
    embedding_backend = OpenAIBackend(model="text-embedding-3-small")

    # Create persistent memory
    memory = PersistentMemory(
        agent_name="learning_assistant",
        user_name="alice",
        llm_backend=llm_backend,
        embedding_backend=embedding_backend,
        on_disk=True
    )

    # Record a conversation
    await memory.record([
        {"role": "user", "content": "I love Python programming"},
        {"role": "assistant", "content": "That's great! Python is very versatile."}
    ])
    print("✓ Recorded conversation to long-term memory")

    # Retrieve relevant memories
    query = "What programming languages does the user like?"
    relevant = await memory.retrieve(query)
    print(f"Retrieved: {relevant}")

    # Agent-controlled memory saving
    result = await memory.save_to_memory(
        thinking="User expressed interest in a topic",
        content=["User likes Python", "User is a beginner"]
    )
    print(f"Save result: {result}")

    # Agent-controlled memory recall
    result = await memory.recall_from_memory(
        keywords=["programming", "Python"],
        limit=3
    )
    print(f"Recalled {result['count']} memories")
    for mem in result['memories']:
        print(f"  - {mem}")
    """

    print("✅ Persistent memory example completed!\n")


async def example_combined_usage():
    """Example: Using both memory types together."""
    print("=" * 60)
    print("Example 3: Combined Memory Usage")
    print("=" * 60)

    from massgen.memory import ConversationMemory

    # Short-term memory for active conversation
    short_term = ConversationMemory()

    # Simulate ongoing conversation
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What's the weather like?"},
        {"role": "assistant", "content": "I can help you check the weather!"},
    ]

    for msg in messages:
        await short_term.add(msg)

    print(f"Short-term memory: {await short_term.size()} messages")

    # In a real agent, you would:
    # 1. Retrieve relevant long-term memories based on current message
    # 2. Inject them into the conversation context
    # 3. Generate response
    # 4. Add response to short-term memory
    # 5. Optionally save important parts to long-term memory

    print("\n💡 In production, this would be integrated with:")
    print("   - LLM backend for generating responses")
    print("   - Persistent memory for cross-session knowledge")
    print("   - Tool system for agent-controlled memory")

    print("\n✅ Combined usage example completed!\n")


async def example_memory_management():
    """Example: Memory management best practices."""
    print("=" * 60)
    print("Example 4: Memory Management")
    print("=" * 60)

    from massgen.memory import ConversationMemory

    memory = ConversationMemory()

    # Add many messages to simulate long conversation
    for i in range(100):
        await memory.add(
            {
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"Message {i}",
            },
        )

    print(f"Added {await memory.size()} messages")

    # Best practice 1: Regular truncation
    await memory.truncate_to_size(50)
    print(f"After truncation: {await memory.size()} messages")

    # Best practice 2: Get only recent messages
    recent = await memory.get_messages(limit=10)
    print(f"Retrieved last {len(recent)} messages")

    # Best practice 3: Periodic cleanup
    user_msgs = await memory.get_messages_by_role("user")
    print(f"User sent {len(user_msgs)} messages")

    # Best practice 4: Clear when starting new topic
    await memory.clear()
    print(f"After clearing: {await memory.size()} messages")

    # Best practice 5: State persistence for crash recovery
    await memory.add({"role": "user", "content": "Important message"})
    state = memory.state_dict()
    print(f"State saved with {len(state['messages'])} messages")

    print("\n💾 Save this state to disk for persistence across restarts!")
    print("\n✅ Memory management example completed!\n")


async def main():
    """Run all examples."""
    print("\n🚀 MassGen Memory System Examples\n")

    await example_conversation_memory()
    await example_persistent_memory()
    await example_combined_usage()
    await example_memory_management()

    print("=" * 60)
    print("All examples completed! 🎉")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Install mem0: pip install mem0ai")
    print("2. Configure your LLM and embedding backends")
    print("3. Try persistent memory with real backends")
    print("4. Integrate into your MassGen agents")
    print("\n")


if __name__ == "__main__":
    asyncio.run(main())
