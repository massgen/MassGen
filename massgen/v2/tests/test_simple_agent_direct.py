#!/usr/bin/env python3
"""
Simple direct test of agent with tools - bypassing orchestrator complexity.
"""

import asyncio
import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, project_root)

from massgen.v2 import create_simple_agent


async def test_simple_agent_direct():
    """Test agent directly with a simple math question."""
    print("🧪 Simple Agent Direct Test")
    print("=" * 40)
    
    # Create agent
    agent = create_simple_agent(
        agent_id="math_tutor",
        model="gpt-4o-mini",
        system_message="You are a helpful math tutor. Answer questions clearly and concisely."
    )
    
    # Simple conversation without orchestrator tools
    messages = [
        {"role": "user", "content": "What is 2 + 2?"}
    ]
    
    print("📝 Question: What is 2 + 2?")
    print("📥 Agent response:")
    
    full_response = ""
    async for chunk in agent.chat(messages):
        if chunk.type == "content":
            print(chunk.content, end="", flush=True)
            full_response += chunk.content
        elif chunk.type == "done":
            print("\n✅ Complete!")
            break
        elif chunk.type == "error":
            print(f"\n❌ Error: {chunk.error}")
            break
    
    print(f"\n📊 Full response: {full_response}")
    print("🎉 Direct agent test completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_simple_agent_direct())