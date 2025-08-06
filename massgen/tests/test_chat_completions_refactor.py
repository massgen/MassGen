#!/usr/bin/env python3
"""
Test script to verify ChatCompletionsBackend refactoring.
Tests integration with different OpenAI-compatible providers.
"""

import asyncio
import os
from typing import Dict, Any
from massgen.backend import ChatCompletionsBackend


async def test_openai_backend():
    """Test ChatCompletionsBackend with OpenAI."""
    print("🔧 Testing ChatCompletionsBackend with OpenAI...")
    
    # Create backend with OpenAI defaults
    backend = ChatCompletionsBackend()
    print(f"Provider: {backend.get_provider_name()}")
    print(f"Base URL: {backend.base_url}")
    print(f"API Key configured: {'Yes' if backend.api_key else 'No'}")
    
    # Test token estimation
    test_text = "Hello world, how are you doing today?"
    tokens = backend.estimate_tokens(test_text)
    print(f"Estimated tokens for '{test_text}': {tokens}")
    
    # Test cost calculation
    cost = backend.calculate_cost(1000, 500, "gpt-4o-mini")
    print(f"Cost for 1000 input + 500 output tokens (gpt-4o-mini): ${cost:.4f}")


async def test_together_ai_backend():
    """Test ChatCompletionsBackend configured for Together AI."""
    print("\n🔧 Testing ChatCompletionsBackend with Together AI...")
    
    # Create backend configured for Together AI
    backend = ChatCompletionsBackend(
        base_url="https://api.together.xyz/v1",
        provider_name="Together AI",
        api_key=os.getenv("TOGETHER_API_KEY")
    )
    print(f"Provider: {backend.get_provider_name()}")
    print(f"Base URL: {backend.base_url}")
    print(f"API Key configured: {'Yes' if backend.api_key else 'No'}")
    
    # Test cost calculation with Together AI model
    cost = backend.calculate_cost(1000, 500, "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo")
    print(f"Cost for 1000 input + 500 output tokens (fallback pricing): ${cost:.4f}")


async def test_cerebras_backend():
    """Test ChatCompletionsBackend configured for Cerebras AI."""
    print("\n🔧 Testing ChatCompletionsBackend with Cerebras AI...")
    
    # Create backend configured for Cerebras AI
    backend = ChatCompletionsBackend(
        base_url="https://api.cerebras.ai/v1",
        provider_name="Cerebras AI",
        api_key=os.getenv("CEREBRAS_API_KEY")
    )
    print(f"Provider: {backend.get_provider_name()}")
    print(f"Base URL: {backend.base_url}")
    print(f"API Key configured: {'Yes' if backend.api_key else 'No'}")


async def test_tool_conversion():
    """Test tool format conversion."""
    print("\n🔧 Testing tool format conversion...")
    
    backend = ChatCompletionsBackend()
    
    # Test Response API format conversion
    response_tools = [
        {
            "type": "function",
            "name": "get_weather",
            "description": "Get weather information",
            "parameters": {
                "type": "object",
                "properties": {"location": {"type": "string"}},
                "required": ["location"]
            }
        }
    ]
    
    converted = backend.convert_tools_to_chat_completions_format(response_tools)
    print("Response API tools converted to Chat Completions format:")
    print(f"  Original: {response_tools[0]}")
    print(f"  Converted: {converted[0]}")
    
    # Test Chat Completions format (should remain unchanged)
    chat_tools = [
        {
            "type": "function",
            "function": {
                "name": "search_web",
                "description": "Search the web",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"]
                }
            }
        }
    ]
    
    converted_chat = backend.convert_tools_to_chat_completions_format(chat_tools)
    print("\nChat Completions tools (should remain unchanged):")
    print(f"  Original: {chat_tools[0]}")
    print(f"  After conversion: {converted_chat[0]}")


async def main():
    """Run all tests."""
    print("🚀 Testing ChatCompletionsBackend refactoring...")
    print("="*60)
    
    try:
        await test_openai_backend()
        await test_together_ai_backend()
        await test_cerebras_backend()
        await test_tool_conversion()
        
        print("\n" + "="*60)
        print("✅ All tests completed successfully!")
        print("\n📋 ChatCompletionsBackend is now ready for use with:")
        print("   • OpenAI (default)")
        print("   • Together AI")  
        print("   • Cerebras AI")
        print("   • Any OpenAI-compatible provider")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(asyncio.run(main()))