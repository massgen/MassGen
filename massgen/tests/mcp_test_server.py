#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple MCP test server for testing MCP integration.

This server provides basic tools for testing MCP functionality.
It implements the MCP protocol over stdio transport.
"""

import asyncio
import json
import sys
from typing import Any, Dict


class SimpleMCPServer:
    """Simple MCP server implementation for testing."""

    def __init__(self):
        self.tools = {
            "mcp_echo": {
                "name": "mcp_echo",
                "description": "Echo back the input text",
                "inputSchema": {
                    "type": "object",
                    "properties": {"text": {"type": "string", "description": "Text to echo back"}},
                    "required": ["text"],
                },
            },
            "add_numbers": {
                "name": "add_numbers",
                "description": "Add two numbers together",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "a": {"type": "number", "description": "First number"},
                        "b": {"type": "number", "description": "Second number"},
                    },
                    "required": ["a", "b"],
                },
            },
            "get_current_time": {
                "name": "get_current_time",
                "description": "Get the current timestamp",
                "inputSchema": {"type": "object", "properties": {}},
            },
        }

    async def handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle initialize request."""
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {"listChanged": True},
                "resources": {"subscribe": False, "listChanged": False},
                "prompts": {"listChanged": False},
            },
            "serverInfo": {"name": "simple-test-server", "version": "1.0.0"},
        }

    async def handle_tools_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tools/list request."""
        return {"tools": list(self.tools.values())}

    async def handle_tools_call(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tools/call request."""
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if tool_name == "mcp_echo":
            text = arguments.get("text", "")
            return {"content": [{"type": "text", "text": f"Echo: {text}"}]}

        elif tool_name == "add_numbers":
            a = arguments.get("a", 0)
            b = arguments.get("b", 0)
            result = a + b
            return {"content": [{"type": "text", "text": f"Result: {a} + {b} = {result}"}]}

        elif tool_name == "get_current_time":
            import datetime

            now = datetime.datetime.now().isoformat()
            return {"content": [{"type": "text", "text": f"Current time: {now}"}]}

        else:
            raise ValueError(f"Unknown tool: {tool_name}")

    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming JSON-RPC request."""
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")

        try:
            if method == "initialize":
                result = await self.handle_initialize(params)
            elif method == "tools/list":
                result = await self.handle_tools_list(params)
            elif method == "tools/call":
                result = await self.handle_tools_call(params)
            else:
                raise ValueError(f"Unknown method: {method}")

            return {"jsonrpc": "2.0", "id": request_id, "result": result}

        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32000, "message": str(e)},
            }

    async def run(self):
        """Run the MCP server."""
        while True:
            try:
                # Read line from stdin
                line = sys.stdin.readline()
                if not line:
                    break

                # Parse JSON-RPC request
                request = json.loads(line.strip())

                # Handle request
                response = await self.handle_request(request)

                # Send response to stdout
                json.dump(response, sys.stdout)
                sys.stdout.write("\n")
                sys.stdout.flush()

            except KeyboardInterrupt:
                break
            except Exception as e:
                # Send error response
                error_response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32603, "message": f"Internal error: {str(e)}"},
                }
                json.dump(error_response, sys.stdout)
                sys.stdout.write("\n")
                sys.stdout.flush()


if __name__ == "__main__":
    server = SimpleMCPServer()
    asyncio.run(server.run())
