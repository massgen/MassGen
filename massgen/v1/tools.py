import inspect
import json
import random
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Union, Optional, Dict, List
import ast
import operator
import math

# Global tool registry
register_tool = {}

# Mock functions removed - actual functionality is implemented in agent classes


def python_interpreter(code: str, timeout: Optional[int] = 10) -> Dict[str, Any]:
    """
    Execute Python code in an isolated subprocess and return its output.

    Args:
        code: The Python code string to execute
        timeout: Maximum execution time in seconds (default: 10, Must be less than 60 seconds)

    Returns:
        A dictionary containing:
        - 'stdout': Standard output from the code execution
        - 'stderr': Standard error from the code execution
        - 'returncode': Exit code of the process (0 for success)
        - 'success': Boolean indicating if execution was successful
        - 'error': Error message if execution failed
    """
    # Ensure timeout is between 0 and 60 seconds
    timeout = max(min(timeout, 60), 0)
    try:
        # Run the code in a separate Python process
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        return json.dumps(
            {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "success": result.returncode == 0,
                "error": None,
            }
        )

    except subprocess.TimeoutExpired:
        return json.dumps(
            {
                "stdout": "",
                "stderr": "",
                "returncode": -1,
                "success": False,
                "error": f"Code execution timed out after {timeout} seconds",
            }
        )

    except Exception as e:
        return json.dumps(
            {
                "stdout": "",
                "stderr": "",
                "returncode": -1,
                "success": False,
                "error": f"Failed to execute code: {str(e)}",
            }
        )


def calculator(expression: str) -> float:
    """
    Mathematical expression to evaluate (e.g., '2 + 3 * 4', 'sqrt(16)', 'sin(pi/2)')
    """
    safe_operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
        ast.Mod: operator.mod,
    }

    # Safe functions
    safe_functions = {
        "abs": abs,
        "round": round,
        "max": max,
        "min": min,
        "sum": sum,
        "sqrt": math.sqrt,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "log": math.log,
        "log10": math.log10,
        "exp": math.exp,
        "pi": math.pi,
        "e": math.e,
    }

    def _safe_eval(node):
        """Safely evaluate an AST node"""
        if isinstance(node, ast.Constant):  # Numbers
            return node.value
        elif isinstance(node, ast.Name):  # Variables/constants
            if node.id in safe_functions:
                return safe_functions[node.id]
            else:
                raise ValueError(f"Unknown variable: {node.id}")
        elif isinstance(node, ast.BinOp):  # Binary operations
            left = _safe_eval(node.left)
            right = _safe_eval(node.right)
            if type(node.op) in safe_operators:
                return safe_operators[type(node.op)](left, right)
            else:
                raise ValueError(f"Unsupported operation: {type(node.op)}")
        elif isinstance(node, ast.UnaryOp):  # Unary operations
            operand = _safe_eval(node.operand)
            if type(node.op) in safe_operators:
                return safe_operators[type(node.op)](operand)
            else:
                raise ValueError(f"Unsupported unary operation: {type(node.op)}")
        elif isinstance(node, ast.Call):  # Function calls
            func = _safe_eval(node.func)
            args = [_safe_eval(arg) for arg in node.args]
            return func(*args)
        else:
            raise ValueError(f"Unsupported node type: {type(node)}")

    try:
        # Parse the expression
        tree = ast.parse(expression, mode="eval")

        # Evaluate safely
        result = _safe_eval(tree.body)

        return {"expression": expression, "result": result, "success": True}

    except Exception as e:
        return {"expression": expression, "error": str(e), "success": False}


# Register tools in the global registry
register_tool["python_interpreter"] = python_interpreter
register_tool["calculator"] = calculator

if __name__ == "__main__":
    print(calculator("24423 + 312 * log(10)"))
