#!/usr/bin/env python3
"""
Test script for Grok backend integration with v3 architecture.
Tests basic functionality, tool integration, and streaming.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from massgen.v3.backend.grok_backend import GrokBackend
from massgen.v3.chat_agent import SingleAgent


async def test_grok_basic():
    """Test basic Grok backend functionality."""
    print("🧪 Testing Grok Backend - Basic Functionality")
    
    # Check if API key is available
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        print("❌ XAI_API_KEY not found in environment variables")
        print("⚠️  Set XAI_API_KEY to test Grok backend")
        return False
    
    try:
        backend = GrokBackend(api_key=api_key)
        
        # Test basic info
        print(f"✅ Provider: {backend.get_provider_name()}")
        print(f"✅ Supported tools: {backend.get_supported_builtin_tools()}")
        
        # Test token estimation
        test_text = "Hello world, this is a test message"
        tokens = backend.estimate_tokens(test_text)
        print(f"✅ Token estimation: {tokens} tokens for '{test_text}'")
        
        # Test cost calculation
        cost = backend.calculate_cost(100, 50, "grok-3-mini")
        print(f"✅ Cost calculation: ${cost:.6f} for 100 input + 50 output tokens")
        
        return True
        
    except Exception as e:
        print(f"❌ Basic test failed: {e}")
        return False


async def test_grok_streaming():
    """Test Grok streaming without tools."""
    print("\n🧪 Testing Grok Backend - Streaming")
    
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        print("❌ XAI_API_KEY not found - skipping streaming test")
        return False
    
    try:
        backend = GrokBackend(api_key=api_key)
        
        messages = [
            {"role": "user", "content": "Say hello and explain what you are in one sentence."}
        ]
        
        print("📤 Sending request to Grok...")
        response_content = ""
        
        async for chunk in backend.stream_with_tools(messages, tools=[], model="grok-3-mini"):
            if chunk.type == "content" and chunk.content:
                response_content += chunk.content
                print(chunk.content, end="", flush=True)
            elif chunk.type == "error":
                print(f"\n❌ Error: {chunk.error}")
                return False
        
        print(f"\n✅ Streaming test completed. Response length: {len(response_content)} chars")
        return True
        
    except Exception as e:
        print(f"❌ Streaming test failed: {e}")
        return False


async def test_grok_with_agent():
    """Test Grok backend through SingleAgent integration."""
    print("\n🧪 Testing Grok Backend - SingleAgent Integration")
    
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        print("❌ XAI_API_KEY not found - skipping agent test")
        return False
    
    try:
        # Create Grok backend and agent
        backend = GrokBackend(api_key=api_key)
        agent = SingleAgent(
            backend=backend,
            system_message="You are a helpful AI assistant.",
            agent_id="test_grok_agent"
        )
        
        print("📤 Testing agent response...")
        response_content = ""
        
        # Test agent with a simple message
        messages = [{"role": "user", "content": "What is 2+2? Answer briefly."}]
        async for chunk in agent.chat(messages):
            if chunk.type == "content" and chunk.content:
                response_content += chunk.content
                print(chunk.content, end="", flush=True)
            elif chunk.type == "error":
                print(f"\n❌ Agent error: {chunk.error}")
                return False
        
        print(f"\n✅ Agent test completed. Response: '{response_content.strip()}'")
        return True
        
    except Exception as e:
        print(f"❌ Agent test failed: {e}")
        return False


async def main():
    """Run all Grok backend tests."""
    print("🚀 MassGen v3 - Grok Backend Testing")
    print("=" * 50)
    
    results = []
    
    # Run tests
    results.append(await test_grok_basic())
    results.append(await test_grok_streaming())
    results.append(await test_grok_with_agent())
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Results:")
    print(f"✅ Passed: {sum(results)}")
    print(f"❌ Failed: {len(results) - sum(results)}")
    
    if all(results):
        print("🎉 All Grok backend tests passed!")
    else:
        print("⚠️  Some tests failed - check XAI_API_KEY and network connection")


if __name__ == "__main__":
    asyncio.run(main())