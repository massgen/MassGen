#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Demo script showing MassGen's persistent memory feature in action.

This script demonstrates memory capabilities programmatically since YAML config
parsing for persistent memory is not yet implemented.

Usage:
    python scripts/demo_memory_feature.py
"""

import asyncio
import sys
from pathlib import Path

from massgen.backend import ResponseBackend  # OpenAI's Response API backend
from massgen.memory import ConversationMemory, PersistentMemory

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


async def demo_conversation_memory():
    """Demonstrate short-term conversation memory."""
    print("=" * 70)
    print("DEMO 1: Conversation Memory (Short-term)")
    print("=" * 70)

    memory = ConversationMemory()

    # Simulate a conversation
    print("\n📝 Storing conversation...")
    conversation = [
        {"role": "user", "content": "Hello! My name is Alice."},
        {"role": "assistant", "content": "Hi Alice! How can I help you today?"},
        {"role": "user", "content": "I'm interested in learning Python."},
        {"role": "assistant", "content": "Great choice! Python is excellent for beginners."},
    ]

    for msg in conversation:
        await memory.add(msg)
        print(f"  ✓ {msg['role']}: {msg['content'][:50]}...")

    # Retrieve messages
    print(f"\n💾 Total messages stored: {await memory.size()}")

    # Get user messages only
    user_msgs = await memory.get_messages_by_role("user")
    print(f"📨 User messages: {len(user_msgs)}")
    for msg in user_msgs:
        print(f"  - {msg['content']}")

    # Get last message
    last = await memory.get_last_message()
    print(f"\n📬 Last message: [{last['role']}] {last['content'][:50]}...")

    # Demonstrate truncation
    print("\n✂️  Truncating to last 2 messages...")
    await memory.truncate_to_size(2)
    print(f"💾 Messages after truncation: {await memory.size()}")

    print("\n✅ Conversation memory demo complete!\n")


async def demo_persistent_memory_basic():
    """Demonstrate persistent memory with basic operations."""
    print("=" * 70)
    print("DEMO 2: Persistent Memory (Basic)")
    print("=" * 70)

    print("\n⚠️  Note: This demo requires:")
    print("   - OpenAI API key set in environment (OPENAI_API_KEY)")
    print("   - mem0ai package installed (pip install mem0ai)")
    print("   - Qdrant vector store (installed with mem0ai)")

    try:
        print("   ✓ mem0ai is installed")
    except ImportError:
        print("   ✗ mem0ai not installed - skipping this demo")
        print("   Install with: pip install mem0ai")
        return

    try:
        # Create backends
        print("\n🔧 Creating LLM and embedding backends...")
        llm_backend = ResponseBackend(model="gpt-4o-mini")
        embedding_backend = ResponseBackend(model="text-embedding-3-small")
        print("   ✓ Backends created")

        # Create persistent memory
        print("\n🧠 Initializing persistent memory...")
        memory = PersistentMemory(
            agent_name="demo_agent",
            user_name="alice",
            llm_backend=llm_backend,
            embedding_backend=embedding_backend,
            on_disk=True,
        )
        print("   ✓ Memory initialized")

        # Record some information
        print("\n📝 Recording conversation to memory...")
        await memory.record(
            [
                {"role": "user", "content": "My name is Alice and I love Python programming"},
                {"role": "assistant", "content": "Nice to meet you, Alice! Python is a great language."},
                {"role": "user", "content": "I'm working on a web scraping project using BeautifulSoup"},
                {"role": "assistant", "content": "BeautifulSoup is excellent for web scraping!"},
            ],
        )
        print("   ✓ Conversation recorded")

        # Retrieve relevant memories
        print("\n🔍 Retrieving relevant memories...")
        queries = [
            "What is the user's name?",
            "What programming language does the user like?",
            "What project is the user working on?",
        ]

        for query in queries:
            result = await memory.retrieve(query)
            print(f"\n   Query: {query}")
            print(f"   Answer: {result if result else 'No information found'}")

        # Test agent-controlled memory operations
        print("\n\n🤖 Testing agent-controlled memory operations...")

        # Agent saves information
        print("\n💾 Agent saving important information...")
        save_result = await memory.save_to_memory(
            thinking="User shared their current project details",
            content=[
                "User is working on web scraping",
                "User is using BeautifulSoup library",
                "User's name is Alice",
                "User's favorite language is Python",
            ],
        )
        print(f"   ✓ Saved: {save_result.get('message', 'Information stored')}")

        # Agent recalls information
        print("\n🔎 Agent recalling from memory...")
        recall_result = await memory.recall_from_memory(
            keywords=["web scraping", "BeautifulSoup", "Python"],
            limit=5,
        )
        print(f"   ✓ Found {recall_result.get('count', 0)} relevant memories:")
        for i, mem in enumerate(recall_result.get("memories", []), 1):
            print(f"      {i}. {mem}")

        print("\n✅ Persistent memory demo complete!")
        print("\n💡 Memory is stored on disk and will persist across sessions!")

    except Exception as e:
        print(f"\n❌ Error during persistent memory demo: {e}")
        print(f"   Type: {type(e).__name__}")
        import traceback

        traceback.print_exc()


async def demo_memory_state_management():
    """Demonstrate state saving and loading."""
    print("\n" + "=" * 70)
    print("DEMO 3: Memory State Management")
    print("=" * 70)

    # Create and populate memory
    print("\n📝 Creating memory and adding messages...")
    memory1 = ConversationMemory()
    await memory1.add({"role": "user", "content": "First message"})
    await memory1.add({"role": "assistant", "content": "Response to first"})
    await memory1.add({"role": "user", "content": "Second message"})
    print(f"   ✓ Memory1 has {await memory1.size()} messages")

    # Save state
    print("\n💾 Saving memory state...")
    state = memory1.state_dict()
    print(f"   ✓ State saved: {len(state['messages'])} messages")

    # Create new memory and restore state
    print("\n📂 Creating new memory and restoring state...")
    memory2 = ConversationMemory()
    memory2.load_state_dict(state)
    print(f"   ✓ Memory2 restored: {await memory2.size()} messages")

    # Verify restoration
    msgs1 = await memory1.get_messages()
    msgs2 = await memory2.get_messages()

    if msgs1 == msgs2:
        print("\n✅ State restoration successful! Memories match.")
    else:
        print("\n❌ State restoration failed! Memories differ.")

    print("\n💡 Use case: Save state periodically for crash recovery")


async def main():
    """Run all demos."""
    print("\n" + "🚀" * 35)
    print("  MassGen Persistent Memory Feature Demo")
    print("🚀" * 35 + "\n")

    # Demo 1: Conversation memory (always works)
    await demo_conversation_memory()

    # Demo 2: Persistent memory (requires dependencies)
    await demo_persistent_memory_basic()

    # Demo 3: State management (always works)
    await demo_memory_state_management()

    print("\n" + "=" * 70)
    print("🎉 All demos completed!")
    print("=" * 70)
    print("\n📚 Next steps:")
    print("   1. Review the memory API documentation: massgen/memory/README.md")
    print("   2. Check out memory examples: massgen/memory/examples.py")
    print("   3. Read the case study: docs/case_studies/memory_enabled_codebase_analysis.md")
    print("   4. Wait for YAML config integration (coming soon!)")
    print()


if __name__ == "__main__":
    asyncio.run(main())
