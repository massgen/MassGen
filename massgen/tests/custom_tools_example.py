#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Example script demonstrating custom tools usage with ResponseBackend.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from massgen.backend.response import ResponseBackend
from massgen.tool import ExecutionResult
from massgen.tool._result import TextContent

# ============================================================================
# Define custom tool functions
# ============================================================================


def calculator(operation: str, x: float, y: float) -> ExecutionResult:
    """
    Perform basic math operations.

    Args:
        operation: The operation to perform (add, subtract, multiply, divide)
        x: First number
        y: Second number

    Returns:
        ExecutionResult with the calculation result
    """
    operations = {
        "add": lambda a, b: a + b,
        "subtract": lambda a, b: a - b,
        "multiply": lambda a, b: a * b,
        "divide": lambda a, b: a / b if b != 0 else "Cannot divide by zero",
    }

    if operation in operations:
        result = operations[operation](x, y)
        return ExecutionResult(
            output_blocks=[
                TextContent(data=f"{operation}({x}, {y}) = {result}"),
            ],
        )
    else:
        return ExecutionResult(
            output_blocks=[
                TextContent(data=f"Unknown operation: {operation}"),
            ],
        )


def text_analyzer(text: str, analysis_type: str = "basic") -> ExecutionResult:
    """
    Analyze text and return statistics.

    Args:
        text: The text to analyze
        analysis_type: Type of analysis (basic, detailed)

    Returns:
        ExecutionResult with text analysis
    """
    word_count = len(text.split())
    char_count = len(text)
    line_count = len(text.splitlines())

    if analysis_type == "basic":
        result = f"Words: {word_count}, Characters: {char_count}"
    else:
        unique_words = len(set(text.lower().split()))
        result = f"Words: {word_count}, Unique words: {unique_words}, " f"Characters: {char_count}, Lines: {line_count}"

    return ExecutionResult(
        output_blocks=[TextContent(data=result)],
    )


async def async_data_processor(data_type: str, count: int = 10) -> ExecutionResult:
    """
    Async function to simulate data processing.

    Args:
        data_type: Type of data to generate (numbers, strings)
        count: Number of items to generate

    Returns:
        ExecutionResult with generated data
    """
    await asyncio.sleep(0.5)  # Simulate processing time

    if data_type == "numbers":
        data = list(range(1, min(count + 1, 100)))
    elif data_type == "strings":
        data = [f"Item_{i}" for i in range(1, min(count + 1, 100))]
    else:
        data = ["Unknown data type"]

    return ExecutionResult(
        output_blocks=[
            TextContent(data=f"Generated {len(data)} {data_type}: {data[:5]}..."),
        ],
    )


# ============================================================================
# Demo functions
# ============================================================================


async def demo_basic_usage():
    """Demonstrate basic custom tools usage."""
    print("=" * 60)
    print("BASIC CUSTOM TOOLS DEMO")
    print("=" * 60)

    # Create ResponseBackend with custom tools
    backend = ResponseBackend(
        api_key=os.getenv("OPENAI_API_KEY", "test-key"),
        custom_tools=[
            {
                "func": calculator,
                "description": "Perform mathematical calculations",
                "category": "math",
            },
            {
                "func": text_analyzer,
                "description": "Analyze text content",
                "category": "text",
            },
            {
                "func": async_data_processor,
                "description": "Process data asynchronously",
                "category": "data",
            },
        ],
    )

    print(f"\nRegistered {len(backend._custom_tool_names)} custom tools:")
    for tool_name in backend._custom_tool_names:
        print(f"  - {tool_name}")

    # Get tool schemas
    schemas = backend._get_custom_tools_schemas()
    print(f"\nGenerated {len(schemas)} tool schemas")

    # Test tool execution
    print("\n" + "-" * 40)
    print("Testing tool execution:")
    print("-" * 40)

    # Test calculator
    calc_input = {
        "operation": "multiply",
        "x": 7,
        "y": 9,
    }
    call = {
        "name": "calculator",
        "call_id": "calc_1",
        "arguments": json.dumps(calc_input),
    }
    print(f"\nCalculator input: {calc_input}")
    result = await backend._execute_custom_tool(call)
    print(f"Calculator result: {result}")

    # Test text analyzer
    text_input = {
        "text": "This is a sample text for analysis. It has multiple words and sentences.",
        "analysis_type": "detailed",
    }
    call = {
        "name": "text_analyzer",
        "call_id": "text_1",
        "arguments": json.dumps(text_input),
    }
    print(f"\nText analyzer input: {text_input}")
    result = await backend._execute_custom_tool(call)
    print(f"Text analyzer result: {result}")

    # Test async data processor
    data_input = {
        "data_type": "numbers",
        "count": 20,
    }
    call = {
        "name": "async_data_processor",
        "call_id": "data_1",
        "arguments": json.dumps(data_input),
    }
    print(f"\nData processor input: {data_input}")
    result = await backend._execute_custom_tool(call)
    print(f"Data processor result: {result}")


async def demo_with_presets():
    """Demonstrate custom tools with preset arguments."""
    print("\n" + "=" * 60)
    print("CUSTOM TOOLS WITH PRESET ARGUMENTS")
    print("=" * 60)

    backend = ResponseBackend(
        api_key="test-key",
        custom_tools=[
            {
                "func": calculator,
                "description": "Addition calculator",
                "preset_args": {"operation": "add"},  # Preset the operation
                "category": "math",
            },
            {
                "func": text_analyzer,
                "description": "Detailed text analyzer",
                "preset_args": {"analysis_type": "detailed"},  # Always detailed
                "category": "text",
            },
        ],
    )

    # Now calculator only needs x and y
    calc_preset_input = {"x": 15, "y": 25}  # operation is preset
    call = {
        "name": "calculator",
        "call_id": "calc_2",
        "arguments": json.dumps(calc_preset_input),
    }
    print(f"\nAddition calculator input (operation preset to 'add'): {calc_preset_input}")
    result = await backend._execute_custom_tool(call)
    print(f"Addition calculator result: {result}")

    # Text analyzer only needs text
    text_preset_input = {"text": "Short text"}  # analysis_type is preset
    call = {
        "name": "text_analyzer",
        "call_id": "text_2",
        "arguments": json.dumps(text_preset_input),
    }
    print(f"\nDetailed analyzer input (analysis_type preset to 'detailed'): {text_preset_input}")
    result = await backend._execute_custom_tool(call)
    print(f"Detailed analyzer result: {result}")


async def demo_from_file():
    """Demonstrate loading custom tools from Python files."""
    print("\n" + "=" * 60)
    print("LOADING CUSTOM TOOLS FROM FILES")
    print("=" * 60)

    # Create a temporary Python file with custom functions
    custom_file = Path(__file__).parent / "my_custom_tools.py"
    custom_file.write_text(
        '''
def word_counter(text: str) -> str:
    """Count words in text."""
    from massgen.tool import ExecutionResult
    from massgen.tool._result import TextContent

    word_count = len(text.split())
    return ExecutionResult(
        output_blocks=[TextContent(data=f"Word count: {word_count}")]
    )

def list_processor(items: list, action: str = "join") -> str:
    """Process a list of items."""
    from massgen.tool import ExecutionResult
    from massgen.tool._result import TextContent

    if action == "join":
        result = ", ".join(str(item) for item in items)
    elif action == "reverse":
        result = str(items[::-1])
    elif action == "sort":
        result = str(sorted(items))
    else:
        result = str(items)

    return ExecutionResult(
        output_blocks=[TextContent(data=f"Result: {result}")]
    )
'''
    )

    try:
        backend = ResponseBackend(
            api_key="test-key",
            custom_tools=[
                {
                    "path": str(custom_file),
                    "func": "word_counter",  # Specific function
                    "description": "Count words in text",
                },
                {
                    "path": str(custom_file),
                    "func": "list_processor",  # Another function from same file
                    "description": "Process lists",
                },
            ],
        )

        print(f"\nLoaded tools from {custom_file.name}:")
        for tool_name in backend._custom_tool_names:
            print(f"  - {tool_name}")

        # Test word counter
        word_input = {"text": "This is a test sentence with seven words"}
        call = {
            "name": "word_counter",
            "call_id": "wc_1",
            "arguments": json.dumps(word_input),
        }
        print(f"\nWord counter input: {word_input}")
        result = await backend._execute_custom_tool(call)
        print(f"Word counter result: {result}")

        # Test list processor
        list_input = {
            "items": [3, 1, 4, 1, 5, 9, 2, 6],
            "action": "sort",
        }
        call = {
            "name": "list_processor",
            "call_id": "lp_1",
            "arguments": json.dumps(list_input),
        }
        print(f"\nList processor input: {list_input}")
        result = await backend._execute_custom_tool(call)
        print(f"List processor result: {result}")

    finally:
        # Cleanup
        if custom_file.exists():
            custom_file.unlink()
            print(f"\nCleaned up temporary file: {custom_file}")


async def demo_builtin_tools():
    """Demonstrate using built-in tools from the tool module."""
    print("\n" + "=" * 60)
    print("USING BUILT-IN TOOLS")
    print("=" * 60)

    backend = ResponseBackend(
        api_key="test-key",
        custom_tools=[
            {
                "func": "read_file_content",  # Built-in tool name
                "description": "Read file content",
            },
        ],
    )

    # This might fail if the built-in function isn't found
    # but demonstrates the concept
    if backend._custom_tool_names:
        print(f"\nFound built-in tools: {backend._custom_tool_names}")
    else:
        print("\nNote: Built-in tools require the tool module to be properly set up")


# ============================================================================
# Main execution
# ============================================================================


async def main():
    """Run all demos."""
    try:
        await demo_basic_usage()
        await demo_with_presets()
        await demo_from_file()
        await demo_builtin_tools()

        print("\n" + "=" * 60)
        print("ALL DEMOS COMPLETED SUCCESSFULLY!")
        print("=" * 60)

    except Exception as e:
        print(f"\nError during demo: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
