#!/usr/bin/env python3
"""
Test a single agent with gpt-4o-mini.
"""

import asyncio
import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, project_root)

from massgen.v2.simple_agent import create_simple_agent


async def test_single_agent():
    """Test single agent functionality with gpt-4o-mini."""
    print("🤖 Testing Single Agent with gpt-4o-mini")
    print("=" * 50)
    
    # Create agent directly
    agent = create_simple_agent(
        agent_id="test_agent",
        model="gpt-4o-mini",
        system_message="You are a helpful assistant that provides concise answers."
    )
    
    print(f"✅ Created agent: {agent.agent_id}")
    print(f"📊 Model: gpt-4o-mini")
    print(f"🔧 Status: {agent.get_status()['status']}")
    
    # Test simple chat
    messages = [{"role": "user", "content": "What is 2 + 2?"}]
    
    print(f"\n📝 Question: What is 2 + 2?")
    print("\n🤖 Agent response:")
    print("-" * 30)
    
    full_response = ""
    async for chunk in agent.chat(messages):
        if chunk.type == "content":
            print(chunk.content, end="")
            full_response += chunk.content
        elif chunk.type == "done":
            print(f"\n\n✅ Chat completed!")
            break
        elif chunk.type == "error":
            print(f"\n❌ Error: {chunk.error}")
            break
    
    # Show final status
    final_status = agent.get_status()
    print(f"\n📊 Final Status:")
    print(f"  - Agent ID: {final_status['agent_id']}")
    print(f"  - Status: {final_status['status']}")
    
    print(f"\n🎉 Single agent test completed successfully!")


if __name__ == "__main__":
    asyncio.run(test_single_agent())