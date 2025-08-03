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

# Model mappings and constants
MODEL_MAPPINGS = {
    "openai": [
        # GPT-4.1 variants
        "gpt-4.1",
        "gpt-4.1-mini",
        # GPT-4o variants
        "gpt-4o-mini",
        "gpt-4o",
        # o1
        "o1",  # -> o1-2024-12-17
        # o3
        "o3",
        "o3-low",
        "o3-medium",
        "o3-high",
        # o3 mini
        "o3-mini",
        "o3-mini-low",
        "o3-mini-medium",
        "o3-mini-high",
        # o4 mini
        "o4-mini",
        "o4-mini-low",
        "o4-mini-medium",
        "o4-mini-high",
    ],
    "gemini": [
        "gemini-2.5-flash",
        "gemini-2.5-pro",
    ],
    "grok": [
        "grok-3-mini",
        "grok-3",
        "grok-4",
    ]
}


def get_agent_type_from_model(model: str) -> str:
    """
    Determine the agent type based on the model name.
    
    Args:
        model: The model name (e.g., "gpt-4", "gemini-pro", "grok-1")
        
    Returns:
        Agent type string ("openai", "gemini", "grok")
    """
    if not model:
        return "openai"  # Default to OpenAI
    
    model_lower = model.lower()
    
    for key, models in MODEL_MAPPINGS.items():
        if model_lower in models:
            return key
    raise ValueError(f"Unknown model: {model}")


def get_available_models() -> list:
    """Get a flat list of all available model names."""
    all_models = []
    for models in MODEL_MAPPINGS.values():
        all_models.extend(models)
    return all_models

def generate_random_id(length: int = 24) -> str:
    """Generate a random ID string."""
    characters = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
    return ''.join(random.choice(characters) for _ in range(length))

# Utility functions (originally from util.py)
def execute_function_calls(function_calls, tool_mapping):
    """Execute function calls and return formatted outputs for the conversation."""
    function_outputs = []
    for function_call in function_calls:
        try:
            # Get the function from tool mapping
            target_function = None
            function_name = function_call.get('name')
            
            # Look up function in tool_mapping
            if function_name in tool_mapping:
                target_function = tool_mapping[function_name]
            else:
                # Handle error case
                error_output = {
                    "type": "function_call_output",
                    "call_id": function_call.get('call_id'),
                    "output": f"Error: Function '{function_name}' not found in tool mapping"
                }
                function_outputs.append(error_output)
                continue
            
            # Parse arguments and execute function
            if isinstance(function_call.get('arguments', {}), str):
                arguments = json.loads(function_call.get('arguments', '{}'))
            elif isinstance(function_call.get('arguments', {}), dict):
                arguments = function_call.get('arguments', {})
            else:
                raise ValueError(f"Unknown arguments type: {type(function_call.get('arguments', {}))}")
            result = target_function(**arguments)
            
            # Format the output according to Responses API requirements
            function_output = {
                "type": "function_call_output",
                "call_id": function_call.get('call_id'),
                "output": str(result)
            }
            function_outputs.append(function_output)
            
            # print(f"Executed function: {function_name}({arguments}) -> {result}")
            
        except Exception as e:
            # Handle execution errors
            error_output = {
                "type": "function_call_output", 
                "call_id": function_call.get('call_id'),
                "output": f"Error executing function: {str(e)}"
            }
            function_outputs.append(error_output)
            # print(f"Error executing function {function_name}: {e}")
            
    return function_outputs


def function_to_json(func) -> dict:
    """
    Converts a Python function into a JSON-serializable dictionary
    that describes the function's signature, including its name,
    description, and parameters.

    Args:
        func: The function to be converted.

    Returns:
        A dictionary representing the function's signature in JSON format.
    """
    type_map = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
        type(None): "null",
    }

    try:
        signature = inspect.signature(func)
    except ValueError as e:
        raise ValueError(f"Failed to get signature for function {func.__name__}: {str(e)}")

    parameters = {}
    for param in signature.parameters.values():
        try:
            param_type = type_map.get(param.annotation, "string")
        except KeyError as e:
            raise KeyError(f"Unknown type annotation {param.annotation} for parameter {param.name}: {str(e)}")
        parameters[param.name] = {"type": param_type}

    required = [param.name for param in signature.parameters.values() if param.default == inspect._empty]

    return {
        "type": "function",
        "name": func.__name__,
        "description": func.__doc__ or "",
        "parameters": {
            "type": "object",
            "properties": parameters,
            "required": required,
        },
    } 