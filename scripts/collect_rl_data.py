#!/usr/bin/env python3
"""
RL Data Collection Script

This script demonstrates how to collect RL training data using
MassGen agents with RL integration enabled.

Usage:
    python scripts/collect_rl_data.py

The script will:
1. Create RL-enabled agents
2. Execute a set of tasks
3. Collect execution traces
4. Save traces to local storage

The collected data can later be used for training RL models.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from massgen import AgentConfig
from massgen.chat_agent import SingleAgent
from massgen.rl import RLAgentMixin, RLConfig, StoreConfig


# Create RL-enabled agent class
class RLSingleAgent(RLAgentMixin, SingleAgent):
    """Single agent with RL trace collection"""
    pass


async def collect_data_single_agent():
    """
    Collect RL data from a single agent.

    This demonstrates basic RL data collection from an individual agent.
    """
    print("=" * 60)
    print("RL Data Collection - Single Agent Demo")
    print("=" * 60)

    # Configure RL
    rl_config = RLConfig(
        enable_rl=True,
        store_config=StoreConfig(
            type="local",
            path="./rl_data"
        ),
        enable_tool_rewards=True,
        enable_answer_quality_rewards=True,
        collect_only=True  # Only collect, don't train
    )

    # Create agent config
    agent_config = AgentConfig.create_openai_config(
        model="gpt-4o-mini",
        system_message="You are a helpful AI assistant."
    )

    # Create RL-enabled agent
    print("\n1. Creating RL-enabled agent...")
    agent = RLSingleAgent(
        backend=agent_config.create_backend(),
        agent_id="demo_agent",
        system_message=agent_config.system_message,
        enable_rl=True,
        rl_config=rl_config
    )
    print("   ✓ Agent created with RL enabled")

    # Sample tasks
    tasks = [
        "What is the capital of France?",
        "Explain quantum computing in simple terms",
        "Write a Python function to calculate factorial",
    ]

    # Execute tasks and collect traces
    print("\n2. Executing tasks and collecting traces...")
    for i, task in enumerate(tasks, 1):
        print(f"\n   Task {i}/{len(tasks)}: {task}")

        messages = [{"role": "user", "content": task}]

        # Collect response
        full_response = ""
        async for chunk in agent.chat(messages):
            if hasattr(chunk, 'content') and chunk.content:
                full_response += chunk.content

        print(f"   ✓ Response: {full_response[:100]}...")

        # Get RL statistics
        stats = agent.get_rl_statistics()
        print(f"   ✓ RL stats: {stats}")

    print("\n3. Data collection complete!")
    print(f"   Traces saved to: {rl_config.store_config.path}")

    # Check stored data
    from massgen.rl import LightningStore
    store = LightningStore(rl_config.store_config)
    stats = await store.get_statistics()
    print(f"\n4. Storage statistics:")
    print(f"   Total traces: {stats.get('total_traces', 0)}")
    print(f"   Total agents: {stats.get('total_agents', 0)}")
    print(f"   Total reward: {stats.get('total_reward', 0.0):.2f}")

    return stats


async def main():
    """Main entry point"""
    try:
        # Check if OpenAI API key is set
        if not os.getenv('OPENAI_API_KEY'):
            print("\n⚠️  Warning: OPENAI_API_KEY not set")
            print("   Please set your OpenAI API key:")
            print("   export OPENAI_API_KEY='your-key-here'\n")
            return

        # Run data collection
        await collect_data_single_agent()

        print("\n" + "=" * 60)
        print("✓ RL Data Collection Demo Complete!")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Inspect traces in ./rl_data/traces/")
        print("2. Use traces for training RL models (future feature)")
        print("3. Deploy trained models to improve agent performance")

    except Exception as e:
        print(f"\n❌ Error during data collection: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
