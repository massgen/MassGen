#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Test script for MassGen tool implementation."""

import asyncio
from massgen.tool._manager import ToolManager
from massgen.tool._result import ExecutionResult, TextContent
from massgen.tool._code_executors import run_python_script, run_shell_script
from massgen.tool._file_handlers import read_file_content, save_file_content
from massgen.tool._basic.sample_math_tool import sample_math_tool


async def test_tool_manager():
    """Test the tool manager functionality."""
    print("Testing MassGen Tool Manager\n" + "="*40)
    
    # Create manager
    manager = ToolManager()
    print("✓ Tool manager created")
    
    # Create categories
    manager.setup_category(
        category_name="math",
        description="Mathematical operations",
        enabled=True,
        usage_hints="Use these tools for calculations"
    )
    print("✓ Created 'math' category")
    
    manager.setup_category(
        category_name="file_ops",
        description="File operations",
        enabled=False
    )
    print("✓ Created 'file_ops' category")
    
    # Register tools
    manager.add_tool_function(
        func=sample_math_tool,
        category="math",
        description="Adds two numbers"
    )
    print("✓ Registered sample_math_tool")
    
    manager.add_tool_function(
        func=run_python_script,
        category="default",
        description="Execute Python code"
    )
    print("✓ Registered run_python_script")
    
    manager.add_tool_function(
        func=read_file_content,
        category="file_ops",
        description="Read file contents"
    )
    print("✓ Registered read_file_content")
    
    # Get schemas
    schemas = manager.fetch_tool_schemas()
    print(f"\n✓ Active tool schemas: {len(schemas)} tools")
    for schema in schemas:
        print(f"  - {schema['function']['name']}: {schema['function'].get('description', 'No description')}")
    
    # Test tool execution
    print("\nTesting tool execution:")
    
    # Test math tool
    tool_request = {
        "name": "sample_math_tool",
        "input": {"x": 5, "y": 3}
    }
    
    async for result in manager.execute_tool(tool_request):
        print(f"  Math result: {result.output_blocks[0].data}")
    
    # Test Python execution
    python_request = {
        "name": "run_python_script",
        "input": {
            "source_code": "print('Hello from MassGen!')\nprint(2 + 2)"
        }
    }
    
    async for result in manager.execute_tool(python_request):
        output = result.output_blocks[0].data
        if "<stdout>" in output:
            stdout_start = output.find("<stdout>") + 8
            stdout_end = output.find("</stdout>")
            stdout = output[stdout_start:stdout_end]
            print(f"  Python output: {stdout.strip()}")
    
    # Test enabling file_ops category
    print("\nEnabling file_ops category...")
    manager.modify_categories(["file_ops"], enabled=True)
    schemas_after = manager.fetch_tool_schemas()
    print(f"✓ Active tools after enabling: {len(schemas_after)}")
    
    # Get category hints
    hints = manager.fetch_category_hints()
    if hints:
        print(f"\nCategory hints:\n{hints}")
    
    print("\n" + "="*40)
    print("All tests completed successfully! ✓")


if __name__ == "__main__":
    asyncio.run(test_tool_manager())