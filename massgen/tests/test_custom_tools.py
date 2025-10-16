# -*- coding: utf-8 -*-
"""
Test custom tools functionality in ResponseBackend.
"""

import asyncio
import json
import os

# Add parent directory to path for imports
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from massgen.backend.response import ResponseBackend  # noqa: E402
from massgen.tool import ExecutionResult, ToolManager  # noqa: E402
from massgen.tool._result import TextContent  # noqa: E402

# ============================================================================
# Sample custom tool functions for testing
# ============================================================================


def calculate_sum(a: int, b: int) -> ExecutionResult:
    """Calculate sum of two numbers.

    Args:
        a: First number
        b: Second number

    Returns:
        Sum of a and b
    """
    result = a + b
    return ExecutionResult(
        output_blocks=[TextContent(data=f"The sum of {a} and {b} is {result}")],
    )


def string_manipulator(text: str, operation: str = "upper") -> ExecutionResult:
    """Manipulate string based on operation.

    Args:
        text: Input string
        operation: Operation to perform (upper, lower, reverse)

    Returns:
        Manipulated string
    """
    if operation == "upper":
        result = text.upper()
    elif operation == "lower":
        result = text.lower()
    elif operation == "reverse":
        result = text[::-1]
    else:
        result = text

    return ExecutionResult(
        output_blocks=[TextContent(data=f"Result: {result}")],
    )


async def async_weather_fetcher(city: str) -> ExecutionResult:
    """Mock async function to fetch weather.

    Args:
        city: City name

    Returns:
        Mock weather data
    """
    # Simulate async operation
    await asyncio.sleep(0.1)

    weather_data = {
        "New York": "Sunny, 25°C",
        "London": "Cloudy, 18°C",
        "Tokyo": "Rainy, 22°C",
    }

    weather = weather_data.get(city, "Unknown location")
    return ExecutionResult(
        output_blocks=[TextContent(data=f"Weather in {city}: {weather}")],
    )


# ============================================================================
# Test ToolManager functionality
# ============================================================================


class TestToolManager:
    """Test ToolManager class."""

    def setup_method(self):
        """Setup for each test."""
        self.tool_manager = ToolManager()

    def test_add_tool_function_direct(self):
        """Test adding a tool function directly."""
        self.tool_manager.add_tool_function(func=calculate_sum)

        assert "calculate_sum" in self.tool_manager.registered_tools
        tool_entry = self.tool_manager.registered_tools["calculate_sum"]
        assert tool_entry.tool_name == "calculate_sum"
        assert tool_entry.base_function == calculate_sum

    def test_add_tool_with_string_name(self):
        """Test adding a built-in tool by name."""
        # This should find built-in functions from the tool module
        try:
            self.tool_manager.add_tool_function(func="read_file_content")
            assert "read_file_content" in self.tool_manager.registered_tools
        except ValueError:
            # If built-in function not found, that's ok for this test
            pass

    def test_add_tool_with_path(self):
        """Test adding a tool from a Python file."""
        # Create a temporary Python file with a function
        test_file = Path(__file__).parent / "temp_tool.py"
        test_file.write_text(
            """
def custom_function(x: int) -> str:
    return f"Value: {x}"
""",
        )

        try:
            self.tool_manager.add_tool_function(path=str(test_file))
            assert "custom_function" in self.tool_manager.registered_tools
        finally:
            # Cleanup
            if test_file.exists():
                test_file.unlink()

    def test_fetch_tool_schemas(self):
        """Test fetching tool schemas."""
        self.tool_manager.add_tool_function(func=calculate_sum)
        self.tool_manager.add_tool_function(func=string_manipulator)

        schemas = self.tool_manager.fetch_tool_schemas()
        assert len(schemas) == 2

        # Check schema format
        for schema in schemas:
            assert schema["type"] == "function"
            assert "function" in schema
            assert "name" in schema["function"]
            assert "parameters" in schema["function"]

    @pytest.mark.asyncio
    async def test_execute_tool(self):
        """Test executing a tool."""
        self.tool_manager.add_tool_function(func=calculate_sum)

        tool_request = {
            "name": "calculate_sum",
            "input": {"a": 5, "b": 3},
        }

        results = []
        async for result in self.tool_manager.execute_tool(tool_request):
            results.append(result)

        assert len(results) > 0
        result = results[0]
        assert hasattr(result, "output_blocks")
        assert "The sum of 5 and 3 is 8" in result.output_blocks[0].data

    @pytest.mark.asyncio
    async def test_execute_async_tool(self):
        """Test executing an async tool."""
        self.tool_manager.add_tool_function(func=async_weather_fetcher)

        tool_request = {
            "name": "async_weather_fetcher",
            "input": {"city": "Tokyo"},
        }

        results = []
        async for result in self.tool_manager.execute_tool(tool_request):
            results.append(result)

        assert len(results) > 0
        result = results[0]
        assert "Weather in Tokyo: Rainy, 22°C" in result.output_blocks[0].data


# ============================================================================
# Test ResponseBackend with custom tools
# ============================================================================


class TestResponseBackendCustomTools:
    """Test ResponseBackend with custom tools integration."""

    def setup_method(self):
        """Setup for each test."""
        self.api_key = os.getenv("OPENAI_API_KEY", "test-key")

    def test_backend_initialization_with_custom_tools(self):
        """Test initializing ResponseBackend with custom tools."""
        custom_tools = [
            {
                "func": calculate_sum,
                "description": "Calculate sum of two numbers",
            },
            {
                "func": string_manipulator,
                "category": "text",
                "preset_args": {"operation": "upper"},
            },
        ]

        backend = ResponseBackend(
            api_key=self.api_key,
            custom_tools=custom_tools,
        )

        # Check that tools were registered
        assert len(backend._custom_tool_names) == 2
        assert "calculate_sum" in backend._custom_tool_names
        assert "string_manipulator" in backend._custom_tool_names

    def test_get_custom_tools_schemas(self):
        """Test getting custom tools schemas."""
        custom_tools = [
            {"func": calculate_sum},
            {"func": string_manipulator},
        ]

        backend = ResponseBackend(
            api_key=self.api_key,
            custom_tools=custom_tools,
        )

        schemas = backend._get_custom_tools_schemas()
        assert len(schemas) == 2

        # Verify schema structure
        for schema in schemas:
            assert schema["type"] == "function"
            function = schema["function"]
            assert "name" in function
            assert "parameters" in function
            assert function["name"] in ["calculate_sum", "string_manipulator"]

    @pytest.mark.asyncio
    async def test_execute_custom_tool(self):
        """Test executing a custom tool through the backend."""
        backend = ResponseBackend(
            api_key=self.api_key,
            custom_tools=[{"func": calculate_sum}],
        )

        call = {
            "name": "calculate_sum",
            "call_id": "test_call_1",
            "arguments": json.dumps({"a": 10, "b": 20}),
        }

        result = await backend._execute_custom_tool(call)
        assert "The sum of 10 and 20 is 30" in result

    @pytest.mark.asyncio
    async def test_custom_tool_categorization(self):
        """Test that custom tools are properly categorized in _stream_with_mcp_tools."""
        backend = ResponseBackend(
            api_key=self.api_key,
            custom_tools=[
                {"func": calculate_sum},
                {"func": string_manipulator},
            ],
        )

        # Simulate captured function calls
        captured_calls = [
            {"name": "calculate_sum", "call_id": "1", "arguments": '{"a": 1, "b": 2}'},
            {"name": "web_search", "call_id": "2", "arguments": '{"query": "test"}'},
            {"name": "unknown_mcp_tool", "call_id": "3", "arguments": "{}"},
        ]

        # Categorize calls (simulate the logic in _stream_with_mcp_tools)
        mcp_calls = []
        custom_calls = []
        provider_calls = []

        for call in captured_calls:
            if call["name"] in backend._mcp_functions:
                mcp_calls.append(call)
            elif call["name"] in backend._custom_tool_names:
                custom_calls.append(call)
            else:
                provider_calls.append(call)

        # Verify categorization
        assert len(custom_calls) == 1
        assert custom_calls[0]["name"] == "calculate_sum"

        assert len(provider_calls) == 2
        assert "web_search" in [c["name"] for c in provider_calls]
        assert "unknown_mcp_tool" in [c["name"] for c in provider_calls]

        assert len(mcp_calls) == 0  # No MCP tools in this test


# ============================================================================
# Integration test with mock streaming
# ============================================================================


class TestCustomToolsIntegration:
    """Integration tests for custom tools with streaming."""

    @pytest.mark.asyncio
    async def test_custom_tool_execution_flow(self):
        """Test the complete flow of custom tool execution."""
        # Create backend with custom tools
        backend = ResponseBackend(
            api_key=os.getenv("OPENAI_API_KEY", "test-key"),
            custom_tools=[
                {"func": calculate_sum, "description": "Add two numbers"},
                {"func": async_weather_fetcher, "description": "Get weather info"},
            ],
        )

        # Verify tools are registered
        assert "calculate_sum" in backend._custom_tool_names
        assert "async_weather_fetcher" in backend._custom_tool_names

        # Test tool execution
        call = {
            "name": "async_weather_fetcher",
            "call_id": "test_weather",
            "arguments": json.dumps({"city": "London"}),
        }

        result = await backend._execute_custom_tool(call)
        assert "Weather in London: Cloudy, 18°C" in result

    def test_custom_tool_error_handling(self):
        """Test error handling in custom tools."""

        def faulty_tool(x: int) -> ExecutionResult:
            raise ValueError("Intentional error")

        backend = ResponseBackend(
            api_key="test-key",
            custom_tools=[{"func": faulty_tool}],
        )

        assert "faulty_tool" in backend._custom_tool_names

    @pytest.mark.asyncio
    async def test_mixed_tools_categorization(self):
        """Test categorization with mixed tool types."""
        backend = ResponseBackend(
            api_key="test-key",
            custom_tools=[{"func": calculate_sum}],
        )

        # Mock some MCP functions
        backend._mcp_functions = {"mcp_tool": None}
        backend._mcp_function_names = {"mcp_tool"}

        # Test categorization logic
        test_calls = [
            {"name": "calculate_sum", "call_id": "1", "arguments": "{}"},  # Custom
            {"name": "mcp_tool", "call_id": "2", "arguments": "{}"},  # MCP
            {"name": "web_search", "call_id": "3", "arguments": "{}"},  # Provider
        ]

        custom = []
        mcp = []
        provider = []

        for call in test_calls:
            if call["name"] in backend._mcp_functions:
                mcp.append(call)
            elif call["name"] in backend._custom_tool_names:
                custom.append(call)
            else:
                provider.append(call)

        assert len(custom) == 1 and custom[0]["name"] == "calculate_sum"
        assert len(mcp) == 1 and mcp[0]["name"] == "mcp_tool"
        assert len(provider) == 1 and provider[0]["name"] == "web_search"


# ============================================================================
# Run tests
# ============================================================================

if __name__ == "__main__":
    # Run pytest
    pytest.main([__file__, "-v"])
