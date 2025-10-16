# -*- coding: utf-8 -*-
"""Exception classes for tool operations."""


class ToolException(Exception):
    """Base exception for tool-related errors."""


class InvalidToolArgumentsException(ToolException):
    """Raised when tool receives invalid arguments."""

    def __init__(self, error_msg: str):
        self.error_msg = error_msg
        super().__init__(self.error_msg)


class ToolNotFoundException(ToolException):
    """Raised when requested tool is not found."""

    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        super().__init__(f"Tool '{tool_name}' not found in registry")


class ToolExecutionException(ToolException):
    """Raised when tool execution fails."""

    def __init__(self, tool_name: str, error_details: str):
        self.tool_name = tool_name
        self.error_details = error_details
        super().__init__(f"Tool '{tool_name}' execution failed: {error_details}")


class CategoryNotFoundException(ToolException):
    """Raised when tool category is not found."""

    def __init__(self, category_name: str):
        self.category_name = category_name
        super().__init__(f"Category '{category_name}' not found")
