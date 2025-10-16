# -*- coding: utf-8 -*-
"""
Sample math tool for testing purposes.
"""

from massgen.tool._result import ExecutionResult, TextContent


async def two_num_tool(x: int, y: int) -> ExecutionResult:
    """Add two numbers together.
    
    Args:
        x: First number
        y: Second number
        
    Returns:
        Sum of the two numbers
    """
    result = x + y
    return ExecutionResult(
        output_blocks=[
            TextContent(data=f"The sum of {x} and {y} is {result}")
        ],
    )