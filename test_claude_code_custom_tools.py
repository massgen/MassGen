#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Test Claude Code backend with custom tools support."""

import asyncio
import json

from massgen.backend.claude_code import ClaudeCodeBackend


async def test_claude_code_custom_tools():
    """Test custom tools functionality in Claude Code backend."""

    import tempfile

    # Create a temporary workspace directory
    temp_dir = tempfile.mkdtemp(prefix="claude_code_test_")

    # Custom tool configuration
    custom_tools = [
        {
            "name": "add_numbers",
            "category": "math",
            "path": None,  # Inline function
            "function": lambda a, b: f"The sum of {a} and {b} is {a + b}",
            "description": "Add two numbers together",
            "preset_args": {},
        },
    ]

    # Initialize backend with custom tools
    backend = ClaudeCodeBackend(
        model="claude-3-5-sonnet-20241022",
        custom_tools=custom_tools,
        cwd=temp_dir,
        agent_id="test_agent",
    )

    # Test messages
    messages = [
        {
            "role": "user",
            "content": "Please calculate 123 + 456 using the add_numbers custom tool.",
        },
    ]

    # Empty tools list (custom tools are handled via system prompt)
    tools = []

    print("Testing Claude Code with custom tools...")
    print("-" * 50)

    try:
        # Stream the response
        async for chunk in backend.stream_with_tools(messages, tools):
            if chunk.type == "content":
                print(chunk.content, end="", flush=True)
            elif chunk.type == "tool_calls":
                print(f"\n[Tool Calls]: {json.dumps(chunk.tool_calls, indent=2)}")
            elif chunk.type == "error":
                print(f"\n[Error]: {chunk.error}")
            elif chunk.type == "done":
                print("\n[Done]")
                break

    except Exception as e:
        print(f"\n[Error]: {e}")
    finally:
        # Clean up
        await backend.disconnect()

    print("-" * 50)
    print("Test completed.")


async def test_system_prompt_generation():
    """Test system prompt generation with custom tools."""

    import tempfile

    # Create a temporary workspace directory
    temp_dir = tempfile.mkdtemp(prefix="claude_code_test_")

    # Custom tool configuration
    custom_tools = [
        {
            "name": "calculate_area",
            "category": "geometry",
            "function": "calculate_area",
            "path": "dummy_path.py",
            "description": "Calculate the area of a shape",
        },
        {
            "name": "convert_temperature",
            "category": "conversion",
            "function": "convert_temperature",
            "path": "dummy_path.py",
            "description": "Convert temperature between units",
        },
    ]

    backend = ClaudeCodeBackend(
        model="claude-3-5-sonnet-20241022",
        custom_tools=custom_tools,
        cwd=temp_dir,
        agent_id="test_agent",
    )

    # Test system prompt building
    base_system = "You are a helpful assistant."
    tools = []  # No workflow tools

    system_prompt = backend._build_system_prompt_with_workflow_tools(tools, base_system)

    print("Generated System Prompt:")
    print("=" * 50)
    print(system_prompt)
    print("=" * 50)

    await backend.disconnect()


async def test_tool_parsing():
    """Test parsing of custom tool calls from response."""

    import tempfile

    # Create a temporary workspace directory
    temp_dir = tempfile.mkdtemp(prefix="claude_code_test_")

    backend = ClaudeCodeBackend(
        model="claude-3-5-sonnet-20241022",
        cwd=temp_dir,
        agent_id="test_agent",
    )

    # Test response with custom tool call
    test_response = """
    Let me calculate that for you using the custom tool.

    ```json
    {"tool_name": "add_numbers", "arguments": {"a": 123, "b": 456}}
    ```

    The tool should give us the result.
    """

    # Parse tool calls
    tool_calls = backend._parse_workflow_tool_calls(test_response)

    print("Parsed Tool Calls:")
    print("=" * 50)
    print(json.dumps(tool_calls, indent=2))
    print("=" * 50)

    await backend.disconnect()


async def main():
    """Run all tests."""
    print("Testing Claude Code Custom Tools Implementation")
    print("=" * 60)

    # Test 1: System prompt generation
    print("\n1. Testing System Prompt Generation:")
    await test_system_prompt_generation()

    # Test 2: Tool parsing
    print("\n2. Testing Tool Call Parsing:")
    await test_tool_parsing()

    # Test 3: Full integration (requires API key)
    print("\n3. Testing Full Integration (requires ANTHROPIC_API_KEY):")
    try:
        await test_claude_code_custom_tools()
    except Exception as e:
        print(f"Skipped: {e}")

    print("\nAll tests completed!")


if __name__ == "__main__":
    asyncio.run(main())
