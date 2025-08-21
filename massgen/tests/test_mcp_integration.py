#!/usr/bin/env python3
"""
Test script for MCP integration with Claude Code backend.

This script provides comprehensive testing of the MCP integration,
including unit tests, integration tests, and end-to-end tests.
"""

import asyncio
import unittest
import tempfile
import os
from pathlib import Path
from massgen.mcp import MCPClient, StdioTransport
from massgen.backend.claude_code import ClaudeCodeBackend


class TestMCPIntegration(unittest.TestCase):
    """Test suite for MCP integration."""

    def get_simple_server_config(self):
        """Configuration for simple test MCP server."""
        return {
            "name": "test",
            "type": "stdio",
            "command": ["python3", "../mcp_servers/simple_test_server.py"],
            "description": "Simple test server",
        }

    async def async_test_mcp_client_basic(self):
        """Test basic MCP client functionality."""
        simple_server_config = self.get_simple_server_config()
        client = MCPClient(simple_server_config)

        try:
            # Test connection
            await client.connect()
            self.assertTrue(client.is_connected())

            # Test tool discovery
            tools = client.get_available_tools()
            self.assertIn("echo", tools)
            self.assertIn("add_numbers", tools)
            self.assertIn("get_current_time", tools)

            # Test tool calls
            echo_result = await client.call_tool("echo", {"text": "Hello MCP"})
            self.assertIn("Hello MCP", str(echo_result))

            math_result = await client.call_tool("add_numbers", {"a": 5, "b": 3})
            self.assertIn("8", str(math_result))

        finally:
            await client.disconnect()

    def test_mcp_client_basic(self):
        """Test basic MCP client functionality."""
        asyncio.run(self.async_test_mcp_client_basic())

    async def async_test_claude_code_mcp_integration(self):
        """Test MCP integration with Claude Code backend."""
        simple_server_config = self.get_simple_server_config()
        with tempfile.TemporaryDirectory() as temp_dir:
            backend = ClaudeCodeBackend(
                cwd=temp_dir, mcp_servers=[simple_server_config]
            )

            try:
                # Test backend initialization with MCP
                await backend._init_mcp_servers()

                # Verify MCP tools are available
                tools = backend.get_supported_builtin_tools()
                mcp_tools = [t for t in tools if t.startswith("mcp__test__")]
                self.assertGreaterEqual(
                    len(mcp_tools), 3
                )  # echo, add_numbers, get_current_time

                # Test MCP tool call handling
                result = await backend._handle_mcp_tool_call(
                    "mcp__test__echo", {"text": "Integration test"}
                )
                self.assertTrue(result["success"])
                self.assertIn("Integration test", str(result["result"]))

            finally:
                await backend.disconnect()

    def test_claude_code_mcp_integration(self):
        """Test MCP integration with Claude Code backend."""
        asyncio.run(self.async_test_claude_code_mcp_integration())

    def test_configuration_validation(self):
        """Test MCP configuration validation."""
        # Test valid config
        valid_config = {
            "name": "test",
            "type": "stdio",
            "command": ["python3", "test_server.py"],
        }
        client = MCPClient(valid_config)
        self.assertEqual(client.name, "test")

        # Test invalid config
        with self.assertRaises(ValueError):
            invalid_config = {"name": "test", "type": "invalid"}
            MCPClient(invalid_config)


async def manual_test_simple_server():
    """Manual test function for the simple MCP server."""
    print("=== Testing Simple MCP Server ===")

    server_config = {
        "name": "test",
        "type": "stdio",
        "command": ["python3", "../mcp_servers/simple_test_server.py"],
        "cwd": os.getcwd(),
    }

    client = MCPClient(server_config)

    try:
        print("1. Connecting to MCP server...")
        await client.connect()
        print(f"✓ Connected! Available tools: {client.get_available_tools()}")

        print("\n2. Testing echo tool...")
        result = await client.call_tool("echo", {"text": "Hello from MCP!"})
        print(f"✓ Echo result: {result}")

        print("\n3. Testing add_numbers tool...")
        result = await client.call_tool("add_numbers", {"a": 10, "b": 25})
        print(f"✓ Math result: {result}")

        print("\n4. Testing get_current_time tool...")
        result = await client.call_tool("get_current_time", {})
        print(f"✓ Time result: {result}")

        print("\n✅ All MCP tests passed!")

    except Exception as e:
        print(f"❌ Test failed: {e}")

    finally:
        await client.disconnect()
        print("🔌 Disconnected from MCP server")


async def manual_test_claude_code_integration():
    """Manual test for Claude Code + MCP integration."""
    print("\n=== Testing Claude Code + MCP Integration ===")

    server_config = {
        "name": "test",
        "type": "stdio",
        "command": ["python3", "../mcp_servers/simple_test_server.py"],
        "cwd": os.getcwd(),
    }

    with tempfile.TemporaryDirectory() as temp_dir:
        backend = ClaudeCodeBackend(cwd=temp_dir, mcp_servers=[server_config])

        try:
            print("1. Initializing MCP servers...")
            await backend._init_mcp_servers()

            print("2. Checking available tools...")
            tools = backend.get_supported_builtin_tools()
            mcp_tools = [t for t in tools if t.startswith("mcp__")]
            print(f"✓ Found {len(mcp_tools)} MCP tools: {mcp_tools}")

            print("\n3. Testing MCP tool call...")
            result = await backend._handle_mcp_tool_call(
                "mcp__test__echo", {"text": "Claude Code + MCP works!"}
            )
            print(f"✓ Tool call result: {result}")

            print("\n✅ Claude Code + MCP integration test passed!")

        except Exception as e:
            print(f"❌ Integration test failed: {e}")

        finally:
            await backend.disconnect()


if __name__ == "__main__":
    print("🚀 Starting MCP Integration Tests\n")

    # Run manual tests
    asyncio.run(manual_test_simple_server())
    asyncio.run(manual_test_claude_code_integration())

    print("\n" + "=" * 50)
    print("📋 Running unittest suite:")

    # Run unittest tests
    unittest.main(verbosity=2, exit=False)

    print("\n📋 To test with MassGen CLI:")
    print(
        "uv run python -m massgen.cli --config massgen/configs/claude_code_simple_mcp.yaml \"Test MCP tools: echo 'hello', add 5+3, get time\""
    )
