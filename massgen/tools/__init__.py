"""
MassGen Tools Package

This package contains all tools and utilities for the MassGen system.
"""

from .file_context_manager import FileContextManager
from .python_tools import python_interpreter, calculator

# Global tool registry for backward compatibility
register_tool = {}
register_tool["python_interpreter"] = python_interpreter
register_tool["calculator"] = calculator

__all__ = [
    'FileContextManager',
    'python_interpreter', 
    'calculator',
    'register_tool'
] 