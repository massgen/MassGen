#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test Context Compression at Agent Level

This script tests compression with a SingleAgent directly (not through orchestrator).
It creates many messages to trigger compression and verifies it works.

Usage:
    uv run python massgen/configs/memory/test_agent_compression.py
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from dotenv import load_dotenv  # noqa: E402

from massgen.backend.chat_completions import ChatCompletionsBackend  # noqa: E402
from massgen.chat_agent import SingleAgent  # noqa: E402
from massgen.memory import ConversationMemory, PersistentMemory  # noqa: E402
from massgen.memory._context_monitor import ContextWindowMonitor  # noqa: E402

load_dotenv()


async def main():
    """Test compression with a single agent."""
    print("=" * 80)
    print("Testing Context Compression at Agent Level")
    print("=" * 80 + "\n")

    # Check API key
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY not set")
        return

    # Configuration
    model_name = "gpt-4o-mini"
    provider = "openai"
    trigger_threshold = 0.05  # Trigger at 5% for quick testing
    target_ratio = 0.02  # Keep only 2% after compression

    print("Configuration:")
    print(f"  Model: {model_name}")
    print(f"  Trigger: {trigger_threshold*100:.0f}%")
    print(f"  Target: {target_ratio*100:.0f}%\n")

    # 1. Create backend
    backend = ChatCompletionsBackend(
        type=provider,
        model=model_name,
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    # 2. Create memories
    conversation_memory = ConversationMemory()

    embedding_backend = ChatCompletionsBackend(
        type="openai",
        model="text-embedding-3-small",
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    persistent_memory = PersistentMemory(
        agent_name="test_compression_agent",
        session_name="test_session",
        llm_backend=backend,
        embedding_backend=embedding_backend,
        on_disk=False,  # In-memory for testing
    )

    print("✅ Memories created")

    # 3. Create context monitor
    monitor = ContextWindowMonitor(
        model_name=model_name,
        provider=provider,
        trigger_threshold=trigger_threshold,
        target_ratio=target_ratio,
        enabled=True,
    )

    print(f"✅ Monitor created (window: {monitor.context_window:,} tokens)")
    print(f"   Will warn at: {int(monitor.context_window * trigger_threshold):,} tokens\n")

    # 4. Create agent with monitor
    agent = SingleAgent(
        backend=backend,
        agent_id="test_agent",
        system_message="You are a helpful assistant. Provide detailed, thorough responses.",
        conversation_memory=conversation_memory,
        persistent_memory=persistent_memory,
        context_monitor=monitor,
    )

    # Verify compressor was created
    if agent.context_compressor:
        print("✅ Context compressor created!\n")
    else:
        print("❌ Context compressor NOT created!\n")
        return

    # 5. Simulate multiple turns to fill context
    print("=" * 80)
    print("Simulating conversation to trigger compression...")
    print("=" * 80 + "\n")

    # Create several turns with verbose responses
    prompts = [
        "Explain how Python's garbage collection works in detail.",
        "Now explain Python's Global Interpreter Lock (GIL) in detail.",
        "Explain Python's asyncio event loop architecture in detail.",
        "Explain Python's descriptor protocol in detail.",
        "Explain Python's metaclasses and how they work in detail.",
    ]

    for i, prompt in enumerate(prompts, 1):
        print(f"\n--- Turn {i} ---")
        print(f"User: {prompt[:60]}...")

        # Check context before turn
        current_messages = await conversation_memory.get_messages()
        print(f"Messages before turn: {len(current_messages)}")

        response_text = ""
        async for chunk in agent.chat([{"role": "user", "content": prompt}]):
            if chunk.type == "content" and chunk.content:
                response_text += chunk.content

        print(f"Response: {len(response_text)} chars")

        # Check context after turn
        current_messages = await conversation_memory.get_messages()
        print(f"Messages after turn: {len(current_messages)}")

        # Small delay between turns
        await asyncio.sleep(0.5)

    # 6. Show final statistics
    print("\n" + "=" * 80)
    print("Final Statistics")
    print("=" * 80)

    stats = monitor.get_stats()
    print("\n📊 Monitor Stats:")
    print(f"  Total turns: {stats['turn_count']}")
    print(f"  Total tokens: {stats['total_tokens']:,}")
    print(f"  Peak usage: {stats['peak_usage_percent']*100:.1f}%")

    if agent.context_compressor:
        comp_stats = agent.context_compressor.get_stats()
        print("\n📦 Compression Stats:")
        print(f"  Total compressions: {comp_stats['total_compressions']}")
        print(f"  Messages removed: {comp_stats['total_messages_removed']}")
        print(f"  Tokens removed: {comp_stats['total_tokens_removed']:,}")

    final_messages = await conversation_memory.get_messages()
    print("\n💾 Final Memory State:")
    print(f"  Messages in conversation_memory: {len(final_messages)}")

    print("\n" + "=" * 80)
    if agent.context_compressor and comp_stats["total_compressions"] > 0:
        print("✅ SUCCESS: Compression worked!")
    else:
        print("⚠️  No compression occurred (context may not have reached threshold)")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
