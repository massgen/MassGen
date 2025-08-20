#!/usr/bin/env python3
"""
Test MCP error handling scenarios.
"""

import asyncio
from massgen.mcp import MCPClient, MCPConnectionError, MCPError


async def test_connection_errors():
    """Test connection error handling."""
    print("=== Testing Connection Errors ===")

    # Test invalid command
    invalid_config = {
        "name": "invalid",
        "type": "stdio",
        "command": ["nonexistent_command"],
    }

    client = MCPClient(invalid_config)

    try:
        await client.connect()
        print("❌ Should have failed to connect")
    except MCPConnectionError as e:
        print(f"✓ Correctly caught connection error: {e}")

    # Test invalid tool call
    valid_config = {
        "name": "test",
        "type": "stdio",
        "command": ["python3", "../mcp_servers/simple_test_server.py"],
    }

    client = MCPClient(valid_config)

    try:
        await client.connect()

        # Call non-existent tool
        try:
            await client.call_tool("nonexistent_tool", {})
            print("❌ Should have failed to call invalid tool")
        except MCPError as e:
            print(f"✓ Correctly caught server error: {e}")

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    finally:
        await client.disconnect()


async def test_malformed_requests():
    """Test malformed request handling."""
    print("\n=== Testing Malformed Requests ===")

    config = {
        "name": "test",
        "type": "stdio",
        "command": ["python3", "../mcp_servers/simple_test_server.py"],
    }

    client = MCPClient(config)

    try:
        await client.connect()

        # Test tool call with missing arguments
        try:
            await client.call_tool("add_numbers", {"a": 5})  # Missing 'b'
            print("❌ Should have failed with missing argument")
        except MCPError as e:
            print(f"✓ Correctly handled missing argument: {e}")

        # Test tool call with wrong argument types
        try:
            await client.call_tool("add_numbers", {"a": "not_a_number", "b": 5})
            print("❌ Should have failed with wrong type")
        except MCPError as e:
            print(f"✓ Correctly handled wrong argument type: {e}")

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    print("🧪 Testing MCP Error Handling\n")
    asyncio.run(test_connection_errors())
    asyncio.run(test_malformed_requests())
    print("\n✅ Error handling tests completed")
