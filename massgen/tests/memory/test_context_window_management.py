#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script for Context Window Management with Memory.

This script demonstrates how to configure and test the context window
management feature with persistent memory integration.

Usage:
    python massgen/configs/tools/memory/test_context_window_management.py

    # Or specify a custom config:
    python massgen/configs/tools/memory/test_context_window_management.py --config path/to/config.yaml
"""

import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import yaml  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from massgen.backend.chat_completions import ChatCompletionsBackend  # noqa: E402
from massgen.chat_agent import SingleAgent  # noqa: E402
from massgen.memory import ConversationMemory, PersistentMemory  # noqa: E402

# Load environment variables from .env file
load_dotenv()


def load_config(config_path: str = None) -> dict:
    """Load configuration from YAML file."""
    if config_path is None:
        # Default to the config in same directory
        config_path = Path(__file__).parent / "gpt5mini_gemini_context_window_management.yaml"

    with open(config_path, "r") as f:
        return yaml.safe_load(f)


async def test_with_persistent_memory(config: dict):
    """Test context compression with persistent memory enabled."""
    # Check if memory is enabled in config
    memory_config = config.get("memory", {})
    if not memory_config.get("enabled", True):
        print("\n⚠️  Skipping: memory.enabled is false in config")
        return

    persistent_enabled = memory_config.get("persistent_memory", {}).get("enabled", True)
    if not persistent_enabled:
        print("\n⚠️  Skipping: memory.persistent_memory.enabled is false in config")
        return

    print("\n" + "=" * 70)
    print("TEST 1: Context Window Management WITH Persistent Memory")
    print("=" * 70 + "\n")

    # Get memory settings from config
    persistent_config = memory_config.get("persistent_memory", {})
    agent_name = persistent_config.get("agent_name", "storyteller_agent")
    session_name = persistent_config.get("session_name", "test_session")
    on_disk = persistent_config.get("on_disk", True)

    # Create LLM backend for both agent and memory
    llm_backend = ChatCompletionsBackend(
        type="openai",
        model="gpt-4o-mini",  # Use smaller model for faster testing
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    # Create embedding backend for persistent memory
    embedding_backend = ChatCompletionsBackend(
        type="openai",
        model="text-embedding-3-small",
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    # Initialize memory systems
    conversation_memory = ConversationMemory()
    persistent_memory = PersistentMemory(
        agent_name=agent_name,
        session_name=session_name,
        llm_backend=llm_backend,
        embedding_backend=embedding_backend,
        on_disk=on_disk,
    )

    # Create agent with memory
    agent = SingleAgent(
        backend=llm_backend,
        agent_id="storyteller",
        system_message="You are a creative storyteller. Create detailed, " "immersive narratives with rich descriptions.",
        conversation_memory=conversation_memory,
        persistent_memory=persistent_memory,
    )

    print("✅ Agent initialized with memory")
    print("   - ConversationMemory: Active")
    print(f"   - PersistentMemory: Active (agent={agent_name}, session={session_name}, on_disk={on_disk})")
    print("   - Model context window: 128,000 tokens")
    print("   - Compression triggers at: 96,000 tokens (75%)")
    print("   - Target after compression: 51,200 tokens (40%)\n")

    # Simulate a conversation that will fill context
    # Each turn will add significant tokens
    story_prompts = [
        "Tell me the beginning of a space exploration story. Include details about the ship, crew, and their mission. (Make it 400+ words)",
        "What happens when they encounter their first alien planet? Describe it in vivid detail.",
        "Describe a tense first contact situation with aliens. What do they look like? How do they communicate?",
        "The mission takes an unexpected turn. What crisis occurs and how does the crew respond?",
        "Show me a dramatic action sequence involving the ship's technology and the alien environment.",
        "Reveal a plot twist about one of the crew members or the mission itself.",
        "Continue the story with escalating tension and more discoveries.",
        "How do cultural differences between humans and aliens create conflicts?",
        "Describe a major decision point for the crew captain. What are the stakes?",
        "Bring the story to a climactic moment with high drama.",
    ]

    turn = 0
    for prompt in story_prompts:
        turn += 1
        print(f"\n--- Turn {turn} ---")
        print(f"User: {prompt}\n")

        response_text = ""
        async for chunk in agent.chat([{"role": "user", "content": prompt}]):
            if chunk.type == "content" and chunk.content:
                response_text += chunk.content

        print(f"Agent: {response_text[:200]}...")
        print(f"       [{len(response_text)} chars in response]")

        # Check if compression occurred by examining conversation size
        if conversation_memory:
            size = await conversation_memory.size()
            print(f"       [Conversation memory: {size} messages]\n")

    print("\n✅ Test completed!")
    print("   Check the output above for compression logs:")
    print("   - Look for: '📊 Context usage: ...'")
    print("   - Look for: '📦 Compressed N messages into long-term memory'")


async def test_without_persistent_memory(config: dict):
    """Test context compression without persistent memory (warning case)."""
    # Check if we should run this test
    memory_config = config.get("memory", {})
    persistent_enabled = memory_config.get("persistent_memory", {}).get("enabled", True)

    if persistent_enabled:
        # Skip if persistent memory is enabled - we already tested that scenario
        print("\n⚠️  Skipping Test 2: persistent memory is enabled in config")
        print("   To test without persistent memory, set memory.persistent_memory.enabled: false")
        return

    print("\n" + "=" * 70)
    print("TEST 2: Context Window Management WITHOUT Persistent Memory")
    print("=" * 70 + "\n")

    # Create LLM backend
    llm_backend = ChatCompletionsBackend(
        type="openai",
        model="gpt-4o-mini",
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    # Only conversation memory, NO persistent memory
    conversation_memory = ConversationMemory()

    # Create agent without persistent memory
    agent = SingleAgent(
        backend=llm_backend,
        agent_id="storyteller_no_persist",
        system_message="You are a creative storyteller.",
        conversation_memory=conversation_memory,
        persistent_memory=None,  # No persistent memory!
    )

    print("⚠️  Agent initialized WITHOUT persistent memory")
    print("   - ConversationMemory: Active")
    print("   - PersistentMemory: NONE")
    print("   - This will trigger warning messages when context fills\n")

    # Shorter test - just trigger compression
    story_prompts = [
        "Tell me a 500-word science fiction story about time travel.",
        "Continue the story with 500 more words about paradoxes.",
        "Add another 500 words with a plot twist.",
        "Continue with 500 words about the resolution.",
        "Write a 500-word epilogue.",
    ]

    turn = 0
    for prompt in story_prompts:
        turn += 1
        print(f"\n--- Turn {turn} ---")
        print(f"User: {prompt}\n")

        response_text = ""
        async for chunk in agent.chat([{"role": "user", "content": prompt}]):
            if chunk.type == "content" and chunk.content:
                response_text += chunk.content

        print(f"Agent: {response_text[:150]}...")

    print("\n✅ Test completed!")
    print("   Check the output above for warning messages:")
    print("   - Look for: '⚠️  Warning: Dropping N messages'")
    print("   - Look for: 'No persistent memory configured'")


async def main(config_path: str = None):
    """Run all tests."""
    print("\n" + "=" * 70)
    print("Context Window Management Test Suite")
    print("=" * 70)

    # Load configuration
    config = load_config(config_path)

    # Show memory configuration
    memory_config = config.get("memory", {})
    print("\n📋 Memory Configuration (from YAML):")
    print(f"   - Enabled: {memory_config.get('enabled', True)}")
    print(f"   - Conversation Memory: {memory_config.get('conversation_memory', {}).get('enabled', True)}")
    print(f"   - Persistent Memory: {memory_config.get('persistent_memory', {}).get('enabled', True)}")

    if memory_config.get("persistent_memory", {}).get("enabled", True):
        pm_config = memory_config.get("persistent_memory", {})
        print(f"   - Agent Name: {pm_config.get('agent_name', 'N/A')}")
        print(f"   - Session Name: {pm_config.get('session_name', 'N/A')}")
        print(f"   - On Disk: {pm_config.get('on_disk', True)}")

    compression_config = memory_config.get("compression", {})
    print(f"   - Compression Trigger: {compression_config.get('trigger_threshold', 0.75)*100}%")
    print(f"   - Target After Compression: {compression_config.get('target_ratio', 0.40)*100}%\n")

    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        print("\n❌ Error: OPENAI_API_KEY environment variable not set")
        print("   Please set your OpenAI API key:")
        print("   export OPENAI_API_KEY='your-key-here'")
        return

    try:
        # Test 1: With persistent memory (if enabled)
        await test_with_persistent_memory(config)

        # Wait between tests
        print("\n" + "-" * 70)
        print("Waiting 5 seconds before next test...")
        print("-" * 70)
        await asyncio.sleep(5)

        # Test 2: Without persistent memory (if disabled in config)
        await test_without_persistent_memory(config)

    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Test failed with error: {e}")
        import traceback

        traceback.print_exc()

    print("\n" + "=" * 70)
    print("All tests completed!")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test context window management with memory")
    parser.add_argument(
        "--config",
        type=str,
        help="Path to YAML config file (default: gpt5mini_gemini_context_window_management.yaml)",
    )
    args = parser.parse_args()

    asyncio.run(main(args.config))
