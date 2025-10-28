#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple Compression Test (No Persistent Memory)

Tests core compression logic by:
1. Creating an agent with only conversation_memory (no persistent_memory)
2. Adding many long messages to trigger compression
3. Verifying old messages are removed

Usage:
    uv run python massgen/configs/memory/test_simple_compression.py
"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from dotenv import load_dotenv  # noqa: E402

from massgen.backend.chat_completions import ChatCompletionsBackend  # noqa: E402
from massgen.chat_agent import SingleAgent  # noqa: E402
from massgen.context_monitor import ContextWindowMonitor  # noqa: E402
from massgen.memory import ConversationMemory  # noqa: E402

load_dotenv()


async def main():
    """Test compression without persistent memory."""
    print("=" * 80)
    print("Simple Compression Test (Conversation Memory Only)")
    print("=" * 80 + "\n")

    # Check API key
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY not set")
        return

    # Configuration - set very low thresholds to trigger quickly
    model_name = "gpt-4o-mini"
    provider = "openai"
    trigger_threshold = 0.03  # Trigger at 3% (very low for testing)
    target_ratio = 0.01  # Keep only 1% after compression

    print("Configuration:")
    print(f"  Model: {model_name}")
    print("  Context window: 128,000 tokens")
    print(f"  Trigger at: {int(128000 * trigger_threshold):,} tokens (3%)")
    print(f"  Target after: {int(128000 * target_ratio):,} tokens (1%)\n")

    # 1. Create backend
    backend = ChatCompletionsBackend(
        type=provider,
        model=model_name,
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    # 2. Create conversation memory ONLY (no persistent memory)
    conversation_memory = ConversationMemory()
    print("✅ Conversation memory created (NO persistent memory)")

    # 3. Create context monitor
    monitor = ContextWindowMonitor(
        model_name=model_name,
        provider=provider,
        trigger_threshold=trigger_threshold,
        target_ratio=target_ratio,
        enabled=True,
    )
    print("✅ Monitor created\n")

    # 4. Create agent (no persistent_memory!)
    agent = SingleAgent(
        backend=backend,
        agent_id="test_agent",
        system_message="You are a helpful assistant.",
        conversation_memory=conversation_memory,
        persistent_memory=None,  # Explicitly None
        context_monitor=monitor,
    )

    # Verify compressor was created
    if agent.context_compressor:
        print("✅ Context compressor created!")
        print(f"   Persistent memory: {agent.context_compressor.persistent_memory is not None}\n")
    else:
        print("❌ Context compressor NOT created (need both monitor + conversation_memory)\n")
        return

    # 5. Run one turn with a complex question
    print("=" * 80)
    print("Running conversation to trigger compression...")
    print("=" * 80 + "\n")

    prompt = """Explain in extreme detail:
    1. How Python's garbage collection works
    2. The Global Interpreter Lock (GIL)
    3. Python's asyncio event loop
    4. The descriptor protocol
    5. Metaclasses and the type system

    Provide comprehensive explanations with code examples for each topic."""

    print("Sending complex prompt to generate long response...\n")

    response_text = ""
    async for chunk in agent.chat([{"role": "user", "content": prompt}]):
        if chunk.type == "content" and chunk.content:
            response_text += chunk.content
            print(".", end="", flush=True)

    print(f"\n\nResponse generated: {len(response_text):,} characters\n")

    # 6. Check results
    print("=" * 80)
    print("Results")
    print("=" * 80 + "\n")

    final_messages = await conversation_memory.get_messages()
    print(f"Messages in conversation_memory: {len(final_messages)}")

    stats = monitor.get_stats()
    print("\n📊 Monitor Stats:")
    print(f"  Turns: {stats['turn_count']}")
    print(f"  Total tokens: {stats['total_tokens']:,}")

    comp_stats = agent.context_compressor.get_stats()
    print("\n📦 Compression Stats:")
    print(f"  Compressions: {comp_stats['total_compressions']}")
    print(f"  Messages removed: {comp_stats['total_messages_removed']}")
    print(f"  Tokens removed: {comp_stats['total_tokens_removed']:,}")

    print("\n" + "=" * 80)
    if comp_stats["total_compressions"] > 0:
        print("✅ SUCCESS: Compression triggered and removed messages!")
    else:
        print("⚠️  No compression - response may not have been long enough")
        print(f"   (Needed {int(128000 * trigger_threshold):,} tokens to trigger)")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
