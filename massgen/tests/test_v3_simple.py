#!/usr/bin/env python3
"""
Simple test script for MassGen v3 basic functionality.
Tests single agent and basic orchestrator functionality.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from massgen.backend.response import ResponseBackend
from massgen.chat_agent import SingleAgent
from massgen.orchestrator import Orchestrator


async def test_single_agent():
    """Test basic SingleAgent functionality."""
    print("🧪 Testing SingleAgent Basic Functionality")
    print("-" * 50)
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not found - skipping single agent test")
        return False
    
    try:
        backend = ResponseBackend(api_key=api_key)
        agent = SingleAgent(
            backend=backend,
            agent_id="test_agent",
            system_message="You are a helpful assistant. Provide brief, accurate answers."
        )
        
        print("📤 Testing single agent response...")
        
        messages = [{"role": "user", "content": "What is 2+2?"}]
        response_content = ""
        
        async for chunk in agent.chat(messages):
            if chunk.type == "content" and chunk.content:
                response_content += chunk.content
                print(chunk.content, end="", flush=True)
            elif chunk.type == "error":
                print(f"\n❌ Error: {chunk.error}")
                return False
            elif chunk.type == "done":
                break
        
        print(f"\n✅ Single agent test completed. Response: '{response_content.strip()}'")
        return True
        
    except Exception as e:
        print(f"❌ Single agent test failed: {e}")
        return False


async def test_orchestrator_single():
    """Test orchestrator with single agent."""
    print("\n🧪 Testing Orchestrator with Single Agent")
    print("-" * 50)
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not found - skipping orchestrator test")
        return False
    
    try:
        backend = ResponseBackend(api_key=api_key)
        agent = SingleAgent(
            backend=backend,
            agent_id="solo_agent",
            system_message="You are a knowledgeable assistant."
        )
        
        orchestrator = Orchestrator(agents={"solo": agent})
        
        print("📤 Testing orchestrator with single agent...")
        
        messages = [{"role": "user", "content": "Explain photosynthesis in one sentence."}]
        response_content = ""
        
        async for chunk in orchestrator.chat(messages):
            if chunk.type == "content" and chunk.content:
                response_content += chunk.content
                print(chunk.content, end="", flush=True)
            elif chunk.type == "error":
                print(f"\n❌ Error: {chunk.error}")
                return False
            elif chunk.type == "done":
                break
        
        print(f"\n✅ Orchestrator single agent test completed. Response length: {len(response_content)} chars")
        return True
        
    except Exception as e:
        print(f"❌ Orchestrator single agent test failed: {e}")
        return False


async def test_agent_status():
    """Test agent status functionality."""
    print("\n🧪 Testing Agent Status")
    print("-" * 50)
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not found - skipping status test")
        return False
    
    try:
        backend = ResponseBackend(api_key=api_key)
        agent = SingleAgent(
            backend=backend,
            agent_id="status_test_agent",
            system_message="Test agent for status checking."
        )
        
        # Test initial status
        status = agent.get_status()
        print(f"📊 Agent Status: {status}")
        
        if status.get("agent_id") == "status_test_agent":
            print("✅ Agent status test passed")
            return True
        else:
            print("❌ Agent status test failed - incorrect ID")
            return False
        
    except Exception as e:
        print(f"❌ Agent status test failed: {e}")
        return False


async def test_conversation_history():
    """Test conversation history management."""
    print("\n🧪 Testing Conversation History")
    print("-" * 50)
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ OPENAI_API_KEY not found - skipping history test")
        return False
    
    try:
        backend = ResponseBackend(api_key=api_key)
        agent = SingleAgent(
            backend=backend,
            agent_id="history_agent",
            system_message="You are a test agent."
        )
        
        # Initial history should contain system message
        initial_history = agent.get_conversation_history()
        print(f"📝 Initial history length: {len(initial_history)}")
        
        # Add a message
        messages = [{"role": "user", "content": "Hello"}]
        async for chunk in agent.chat(messages):
            if chunk.type == "done":
                break
        
        # Check updated history
        updated_history = agent.get_conversation_history()
        print(f"📝 Updated history length: {len(updated_history)}")
        
        if len(updated_history) > len(initial_history):
            print("✅ Conversation history test passed")
            return True
        else:
            print("❌ Conversation history test failed - no history update")
            return False
        
    except Exception as e:
        print(f"❌ Conversation history test failed: {e}")
        return False


async def main():
    """Run all simple functionality tests."""
    print("🚀 MassGen - Simple Functionality Test Suite")
    print("=" * 60)
    
    results = []
    
    # Run all tests
    results.append(await test_single_agent())
    results.append(await test_orchestrator_single()) 
    results.append(await test_agent_status())
    results.append(await test_conversation_history())
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Results:")
    print(f"✅ Passed: {sum(results)}")
    print(f"❌ Failed: {len(results) - sum(results)}")
    
    if all(results):
        print("🎉 All simple functionality tests passed!")
        print("✅ MassGen basic functionality is working correctly")
    else:
        print("⚠️  Some tests failed - check API key and configuration")


if __name__ == "__main__":
    asyncio.run(main())