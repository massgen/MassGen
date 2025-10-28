#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Force Compression Test

Directly tests compression by manually adding many messages to trigger it.
Bypasses LLM calls for faster testing.

Usage:
    uv run python massgen/configs/memory/test_force_compression.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from massgen.context_monitor import ContextWindowMonitor  # noqa: E402
from massgen.memory import ContextCompressor, ConversationMemory  # noqa: E402
from massgen.token_manager.token_manager import TokenCostCalculator  # noqa: E402


async def main():
    """Test compression by manually creating a large conversation."""
    print("=" * 80)
    print("Force Compression Test")
    print("=" * 80 + "\n")

    # Create components
    calculator = TokenCostCalculator()
    conversation_memory = ConversationMemory()

    # Create monitor with low threshold
    monitor = ContextWindowMonitor(
        model_name="gpt-4o-mini",
        provider="openai",
        trigger_threshold=0.10,  # 10% = 12,800 tokens
        target_ratio=0.05,  # 5% = 6,400 tokens
        enabled=True,
    )

    # Create compressor (no persistent memory for this test)
    compressor = ContextCompressor(
        token_calculator=calculator,
        conversation_memory=conversation_memory,
        persistent_memory=None,  # Test without it first
    )

    print("Configuration:")
    print(f"  Context window: {monitor.context_window:,} tokens")
    print(f"  Trigger at: {int(monitor.context_window * monitor.trigger_threshold):,} tokens ({monitor.trigger_threshold*100:.0f}%)")
    print(f"  Target after: {int(monitor.context_window * monitor.target_ratio):,} tokens ({monitor.target_ratio*100:.0f}%)\n")

    # Manually create a large conversation
    print("Creating large conversation...")

    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
    ]

    # Add many long messages to exceed threshold
    long_content = "This is a detailed explanation about Python programming. " * 200  # ~2000 tokens per message

    for i in range(10):
        messages.append({"role": "user", "content": f"Question {i}: {long_content}"})
        messages.append({"role": "assistant", "content": f"Answer {i}: {long_content}"})

    # Add to conversation memory
    await conversation_memory.add(messages)

    message_count = len(messages)
    total_tokens = calculator.estimate_tokens(messages)

    print("✅ Created conversation:")
    print(f"  Messages: {message_count}")
    print(f"  Estimated tokens: {total_tokens:,}\n")

    # Check if we should compress
    usage_info = monitor.log_context_usage(messages, turn_number=1)

    print("\n📊 Context Analysis:")
    print(f"  Current: {usage_info['current_tokens']:,} / {usage_info['max_tokens']:,} tokens")
    print(f"  Usage: {usage_info['usage_percent']*100:.1f}%")
    print(f"  Should compress: {usage_info['should_compress']}\n")

    if not usage_info["should_compress"]:
        print("⚠️  Not over threshold yet, adding more messages...\n")
        # Add more messages
        for i in range(10, 20):
            messages.append({"role": "user", "content": f"Question {i}: {long_content}"})
            messages.append({"role": "assistant", "content": f"Answer {i}: {long_content}"})

        await conversation_memory.add(messages[21:])  # Add new messages
        total_tokens = calculator.estimate_tokens(messages)
        usage_info = monitor.log_context_usage(messages, turn_number=2)

        print("\n📊 After adding more:")
        print(f"  Messages: {len(messages)}")
        print(f"  Current: {usage_info['current_tokens']:,} tokens")
        print(f"  Usage: {usage_info['usage_percent']*100:.1f}%")
        print(f"  Should compress: {usage_info['should_compress']}\n")

    # Trigger compression
    print("=" * 80)
    print("Triggering Compression...")
    print("=" * 80 + "\n")

    compression_stats = await compressor.compress_if_needed(
        messages=messages,
        current_tokens=usage_info["current_tokens"],
        target_tokens=usage_info["target_tokens"],
        should_compress=True,  # Force it
    )

    # Show results
    print("\n" + "=" * 80)
    print("Compression Results")
    print("=" * 80 + "\n")

    if compression_stats:
        print("✅ COMPRESSION OCCURRED!")
        print("\n📦 Stats:")
        print(f"  Messages removed: {compression_stats.messages_removed}")
        print(f"  Tokens removed: {compression_stats.tokens_removed:,}")
        print(f"  Messages kept: {compression_stats.messages_kept}")
        print(f"  Tokens kept: {compression_stats.tokens_kept:,}")

        # Verify conversation memory was updated
        final_messages = await conversation_memory.get_messages()
        print("\n💾 Conversation Memory After Compression:")
        print(f"  Messages remaining: {len(final_messages)}")
        print(f"  Expected: {compression_stats.messages_kept}")

        if len(final_messages) == compression_stats.messages_kept:
            print("\n✅ SUCCESS: Conversation memory correctly updated!")
        else:
            print("\n❌ ERROR: Message count mismatch!")

        # Show compressor overall stats
        comp_stats = compressor.get_stats()
        print("\n📊 Compressor Total Stats:")
        print(f"  Total compressions: {comp_stats['total_compressions']}")
        print(f"  Total messages removed: {comp_stats['total_messages_removed']}")
        print(f"  Total tokens removed: {comp_stats['total_tokens_removed']:,}")

    else:
        print("❌ No compression occurred")

    print("\n" + "=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
