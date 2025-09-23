#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude Backend Integration Tests for MassGen

Tests the Claude backend implementation with real API calls:
- Basic text streaming
- Tool calling functionality
- Multi-tool support (web search + code execution + user functions)
- Message format conversion
- Error handling and token tracking

Requires ANTHROPIC_API_KEY environment variable.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from massgen.backend.claude import ClaudeBackend  # noqa: E402


async def test_claude_basic_streaming():
    """Test basic Claude streaming functionality."""
    print("🧪 Testing Claude Basic Streaming...")

    backend = ClaudeBackend()

    messages = [{"role": "user", "content": "Explain quantum computing in 2-3 sentences."}]

    content = ""
    async for chunk in backend.stream_with_tools(messages, [], model="claude-3-5-haiku-20241022"):
        if chunk.type == "content":
            content += chunk.content
            print(chunk.content, end="", flush=True)
        elif chunk.type == "complete_message":
            print(f"\n✅ Complete message received: {len(chunk.complete_message.get('content', ''))} chars")
        elif chunk.type == "done":
            print("\n✅ Basic streaming test completed")
            break
        elif chunk.type == "error":
            print(f"\n❌ Error: {chunk.error}")
            return False

    return len(content) > 50


async def test_claude_tool_calling():
    """Test Claude with user-defined tool calling."""
    print("\n🧪 Testing Claude Tool Calling...")

    backend = ClaudeBackend()

    # Define a simple tool
    tools = [
        {
            "type": "function",
            "name": "calculate_area",
            "description": "Calculate the area of a rectangle",
            "parameters": {
                "type": "object",
                "properties": {
                    "width": {"type": "number", "description": "Width of rectangle"},
                    "height": {"type": "number", "description": "Height of rectangle"},
                },
                "required": ["width", "height"],
            },
        },
    ]

    messages = [
        {
            "role": "user",
            "content": "Calculate the area of a rectangle with width 5 and height 3.",
        },
    ]

    tool_calls_received = []
    async for chunk in backend.stream_with_tools(messages, tools, model="claude-3-5-haiku-20241022"):
        if chunk.type == "content":
            print(chunk.content, end="", flush=True)
        elif chunk.type == "tool_calls":
            tool_calls_received = chunk.tool_calls
            print(f"\n🔧 Tool calls received: {len(tool_calls_received)}")
            for tool_call in tool_calls_received:
                tool_name = backend.extract_tool_name(tool_call)
                tool_args = backend.extract_tool_arguments(tool_call)
                print(f"   - {tool_name}: {tool_args}")
        elif chunk.type == "complete_message":
            print("\n✅ Complete message with tool calls received")
        elif chunk.type == "done":
            print("✅ Tool calling test completed")
            break
        elif chunk.type == "error":
            print(f"\n❌ Error: {chunk.error}")
            return False

    return len(tool_calls_received) > 0


async def test_claude_multi_tool_support():
    """Test Claude's multi-tool capabilities (server-side + user-defined)."""
    print("\n🧪 Testing Claude Multi-Tool Support...")

    backend = ClaudeBackend()

    # Define user tool
    user_tools = [
        {
            "type": "function",
            "name": "format_result",
            "description": "Format a result nicely",
            "parameters": {
                "type": "object",
                "properties": {"title": {"type": "string"}, "data": {"type": "string"}},
                "required": ["title", "data"],
            },
        },
    ]

    messages = [
        {
            "role": "user",
            "content": "Search for recent news about AI and format the result with a nice title.",
        },
    ]

    # Enable both server-side tools and user tools
    tool_calls_received = []
    search_used = False

    async for chunk in backend.stream_with_tools(
        messages,
        user_tools,
        model="claude-3-5-haiku-20241022",
        enable_web_search=True,  # Server-side tool
        enable_code_execution=False,
    ):
        if chunk.type == "content":
            print(chunk.content, end="", flush=True)
            if "search" in chunk.content.lower():
                search_used = True
        elif chunk.type == "tool_calls":
            tool_calls_received.extend(chunk.tool_calls)
            print(f"\n🔧 Tool calls: {len(chunk.tool_calls)}")
        elif chunk.type == "done":
            print("\n✅ Multi-tool test completed")
            break
        elif chunk.type == "error":
            print(f"\n❌ Error: {chunk.error}")
            return False

    print(f"   Search used: {search_used}")
    print(f"   Tool calls: {len(tool_calls_received)}")

    return search_used or len(tool_calls_received) > 0


async def test_claude_message_conversion():
    """Test Claude's message format conversion capabilities."""
    print("\n🧪 Testing Claude Message Conversion...")

    backend = ClaudeBackend()

    # Test with tool result message (Chat Completions format)
    messages = [
        {"role": "user", "content": "What's 5 + 3?"},
        {
            "role": "assistant",
            "content": "Let me calculate that.",
            "tool_calls": [
                {
                    "id": "call_123",
                    "type": "function",
                    "function": {"name": "add", "arguments": {"a": 5, "b": 3}},
                },
            ],
        },
        {"role": "tool", "tool_call_id": "call_123", "content": "8"},
    ]

    # Convert messages
    converted, system_msg = backend.convert_messages_to_claude_format(messages)

    print(f"   Original messages: {len(messages)}")
    print(f"   Converted messages: {len(converted)}")
    print(f"   System message: {len(system_msg)} chars")

    # Check tool result conversion
    tool_result_found = False
    for msg in converted:
        if msg.get("role") == "user" and isinstance(msg.get("content"), list) and any(item.get("type") == "tool_result" for item in msg["content"]):
            tool_result_found = True
            print("   ✅ Tool result conversion successful")
            break

    return len(converted) >= 3 and tool_result_found


async def test_claude_error_handling():
    """Test Claude backend error handling."""
    print("\n🧪 Testing Claude Error Handling...")

    # Test with invalid API key
    backend = ClaudeBackend(api_key="invalid_key")

    messages = [{"role": "user", "content": "Test message"}]

    error_caught = False
    async for chunk in backend.stream_with_tools(messages, []):
        if chunk.type == "error":
            print(f"   ✅ Error properly caught: {chunk.error[:50]}...")
            error_caught = True
            break

    return error_caught


async def test_claude_token_pricing():
    """Test Claude token usage and pricing calculations."""
    print("\n🧪 Testing Claude Token Pricing...")

    backend = ClaudeBackend()

    # Test pricing calculation for different models
    models_to_test = ["claude-4-opus", "claude-4-sonnet", "claude-3.5-haiku"]

    for model in models_to_test:
        cost = backend.calculate_cost(1000, 500, model)
        print(f"   {model}: 1K input + 500 output = ${cost:.4f}")

    # Test tool pricing
    backend.search_count = 10
    backend.code_session_hours = 0.5
    tool_cost = backend.calculate_cost(0, 0, "claude-4-sonnet")
    print(f"   Tool costs: 10 searches + 0.5h code = ${tool_cost:.4f}")

    return True


async def main():
    """Run all Claude backend tests."""
    print("🚀 Starting Claude Backend Integration Tests\n")

    # Check API key
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("❌ ANTHROPIC_API_KEY not found. Skipping real API tests.")
        print("   Set ANTHROPIC_API_KEY to run integration tests.")

        # Run only offline tests
        await test_claude_message_conversion()
        await test_claude_token_pricing()
        return

    # Run all tests
    tests = [
        ("Basic Streaming", test_claude_basic_streaming),
        ("Tool Calling", test_claude_tool_calling),
        ("Multi-Tool Support", test_claude_multi_tool_support),
        ("Message Conversion", test_claude_message_conversion),
        ("Error Handling", test_claude_error_handling),
        ("Token Pricing", test_claude_token_pricing),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n❌ {test_name} failed with exception: {e}")
            results.append((test_name, False))

    # Summary
    print("\n📊 Test Results Summary:")
    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {status} {test_name}")

    print(f"\n🎯 Overall: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All Claude backend tests completed successfully!")
    else:
        print("⚠️  Some tests failed. Check the output above for details.")


if __name__ == "__main__":
    asyncio.run(main())
