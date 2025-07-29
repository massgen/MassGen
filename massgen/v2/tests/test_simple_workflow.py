#!/usr/bin/env python3
"""
Simple test to verify agent system message + coordination workflow.
"""

import asyncio
import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
sys.path.insert(0, project_root)

from massgen.v2 import create_simple_agent
from massgen.v2.message_templates import MessageTemplates


async def test_simple_workflow():
    """Test simple agent with workflow tools."""
    print("🧪 Simple Workflow Test")
    print("=" * 40)
    
    # Create agent
    agent = create_simple_agent(
        agent_id="test_agent",
        model="gpt-4o-mini",
        system_message="You are a helpful math tutor."
    )
    
    # Create message templates and tools
    templates = MessageTemplates()
    tools = templates.get_standard_tools(["agent1"])
    
    # Build conversation with combined system message
    conversation = templates.build_initial_conversation(
        task="What is 2 + 2?",
        original_system_message=agent.system_message
    )
    
    messages = [
        {"role": "system", "content": conversation["system_message"]},
        {"role": "user", "content": conversation["user_message"]}
    ]
    
    print("📤 Sending to agent:")
    print(f"System: {conversation['system_message'][:100]}...")
    print(f"User: {conversation['user_message'][:100]}...")
    print(f"Tools: {len(tools)} tools")
    print()
    
    print("📥 Agent response:")
    async for chunk in agent.chat(messages, tools):
        if chunk.type == "content":
            print(chunk.content, end="", flush=True)
        elif chunk.type == "tool_calls":
            print(f"\n🔧 Tool calls: {chunk.content}")
        elif chunk.type == "done":
            print("\n✅ Complete!")
            break
        elif chunk.type == "error":
            print(f"\n❌ Error: {chunk.error}")
            break


if __name__ == "__main__":
    asyncio.run(test_simple_workflow())