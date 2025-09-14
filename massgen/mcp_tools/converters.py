"""
MCP format conversion utilities for different Backends.
Provides consistent format conversion across all backend implementations.
"""
from __future__ import annotations
from typing import Dict, List, Any, Tuple
from ..logger_config import logger

# Import Function class
try:
    from .backend_utils import Function
except ImportError:
    Function = None


class MCPConverters:
    """Format conversion utilities for different Backends."""

    @staticmethod
    def to_chat_completions_format(
        functions: Dict[str, Function]
    ) -> List[Dict[str, Any]]:
        """Convert Function objects to Chat Completions format.

        Args:
            functions: Dictionary mapping function names to Function objects

        Returns:
            List of tools in Chat Completions API format
        """
        if not functions or Function is None:
            return []

        converted_tools = []
        for function in functions.values():
            try:
                tool = function.to_chat_completions_format()
                converted_tools.append(tool)
            except Exception as e:
                logger.error(
                    f"Failed to convert function {function.name} to Chat Completions format: {e}"
                )

        logger.debug(
            f"Converted {len(converted_tools)} functions to Chat Completions format"
        )
        return converted_tools

    @staticmethod
    def to_response_api_format(functions: Dict[str, Function]) -> List[Dict[str, Any]]:
        """Convert Function objects to Response API format.

        Args:
            functions: Dictionary mapping function names to Function objects

        Returns:
            List of tools in Response API format
        """
        if not functions or Function is None:
            return []

        converted_tools = []
        for function in functions.values():
            try:
                tool = function.to_openai_format()
                converted_tools.append(tool)
            except Exception as e:
                logger.error(
                    f"Failed to convert function {function.name} to Response API format: {e}"
                )

        logger.debug(
            f"Converted {len(converted_tools)} functions to Response API format"
        )
        return converted_tools

    @staticmethod
    def to_claude_format(functions: Dict[str, Function]) -> List[Dict[str, Any]]:
        """Convert Function objects to Claude format.

        Args:
            functions: Dictionary mapping function names to Function objects

        Returns:
            List of tools in Claude API format
        """
        if not functions or Function is None:
            return []

        converted_tools = []
        for function in functions.values():
            try:
                tool = function.to_claude_format()
                converted_tools.append(tool)
            except Exception as e:
                logger.error(
                    f"Failed to convert function {function.name} to Claude format: {e}"
                )

        logger.debug(f"Converted {len(converted_tools)} functions to Claude format")
        return converted_tools

    @staticmethod
    def get_supported_formats() -> List[str]:
        """Get list of supported format conversion types.

        Returns:
            List of supported format names
        """
        return ["chat_completions", "response_api", "claude"]

    @staticmethod
    def convert_to_format(
        functions: Dict[str, Function], format_type: str
    ) -> List[Dict[str, Any]]:
        """Convert functions to specified format.

        Args:
            functions: Dictionary mapping function names to Function objects
            format_type: Target format type

        Returns:
            List of tools in specified format

        Raises:
            ValueError: If format_type is not supported
        """
        format_type = format_type.lower()

        if format_type == "chat_completions":
            return MCPConverters.to_chat_completions_format(functions)
        elif format_type == "response_api":
            return MCPConverters.to_response_api_format(functions)
        elif format_type == "claude":
            return MCPConverters.to_claude_format(functions)
        else:
            supported = MCPConverters.get_supported_formats()
            raise ValueError(
                f"Unsupported format type: {format_type}. Supported: {supported}"
            )

    @staticmethod
    def validate_function_dict(functions: Any) -> bool:
        """Validate that functions parameter is a proper dictionary of Function objects.

        Args:
            functions: Object to validate

        Returns:
            True if valid, False otherwise
        """
        if not isinstance(functions, dict):
            return False

        if Function is None:
            return False

        for name, func in functions.items():
            if not isinstance(name, str):
                return False
            if not isinstance(func, Function):
                return False

        return True

    @staticmethod
    def get_conversion_summary(functions: Dict[str, Function]) -> Dict[str, Any]:
        """Get summary of function conversion capabilities.

        Args:
            functions: Dictionary mapping function names to Function objects

        Returns:
            Dictionary with conversion summary
        """
        if not MCPConverters.validate_function_dict(functions):
            return {
                "valid": False,
                "function_count": 0,
                "supported_formats": [],
                "error": "Invalid functions dictionary",
            }

        return {
            "valid": True,
            "function_count": len(functions),
            "function_names": list(functions.keys()),
            "supported_formats": MCPConverters.get_supported_formats(),
            "error": None,
        }


class MCPFormatValidator:
    """Validates MCP tool formats for different APIs."""

    @staticmethod
    def validate_chat_completions_tool(tool: Dict[str, Any]) -> bool:
        """Validate tool format for Chat Completions API.

        Args:
            tool: Tool dictionary to validate

        Returns:
            True if format is valid
        """
        if not isinstance(tool, dict):
            return False

        if tool.get("type") != "function":
            return False

        function = tool.get("function")
        if not isinstance(function, dict):
            return False

        required_fields = ["name", "description", "parameters"]
        return all(field in function for field in required_fields)

    @staticmethod
    def validate_response_api_tool(tool: Dict[str, Any]) -> bool:
        """Validate tool format for Response API.

        Args:
            tool: Tool dictionary to validate

        Returns:
            True if format is valid
        """
        if not isinstance(tool, dict):
            return False

        if tool.get("type") != "function":
            return False

        required_fields = ["name", "description", "parameters"]
        return all(field in tool for field in required_fields)

    @staticmethod
    def validate_claude_tool(tool: Dict[str, Any]) -> bool:
        """Validate tool format for Claude API.

        Args:
            tool: Tool dictionary to validate

        Returns:
            True if format is valid
        """
        if not isinstance(tool, dict):
            return False

        required_fields = ["name", "description", "parameters"]
        return all(field in tool for field in required_fields)

    @staticmethod
    def validate_tools_for_format(
        tools: List[Dict[str, Any]], format_type: str
    ) -> Tuple[bool, List[str]]:
        """Validate list of tools for specified format.

        Args:
            tools: List of tool dictionaries
            format_type: Target format type

        Returns:
            Tuple of (all_valid, list_of_errors)
        """
        if not isinstance(tools, list):
            return False, ["Tools must be a list"]

        format_type = format_type.lower()
        errors = []

        for i, tool in enumerate(tools):
            valid = False

            if format_type == "chat_completions":
                valid = MCPFormatValidator.validate_chat_completions_tool(tool)
            elif format_type == "response_api":
                valid = MCPFormatValidator.validate_response_api_tool(tool)
            elif format_type == "claude":
                valid = MCPFormatValidator.validate_claude_tool(tool)
            else:
                errors.append(f"Unsupported format type: {format_type}")
                break

            if not valid:
                tool_name = tool.get("name", f"tool_{i}")
                errors.append(
                    f"Invalid {format_type} format for tool '{tool_name}' at index {i}"
                )

        return len(errors) == 0, errors
