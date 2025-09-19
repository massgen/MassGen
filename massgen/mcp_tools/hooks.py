"""
Hook system for MCP tool call interception.

This module provides the infrastructure for intercepting MCP tool calls
across different backend architectures:

1. Function-based backends (OpenAI, Claude, etc.) - use FunctionHook
2. Session-based backends (Gemini) - use PermissionClientSession

The actual permission logic is implemented in filesystem_manager.py
"""

import time
import json
from ..logger_config import logger
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List
from enum import Enum
from datetime import timedelta

# MCP imports for session-based backends
try:
    from mcp import ClientSession, types
    from mcp.client.session import ProgressFnT
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    ClientSession = object
    types = None
    ProgressFnT = None

class HookType(Enum):
    """Types of function call hooks."""
    PRE_CALL = "pre_call"
    # Future: POST_CALL = "post_call"


class HookResult:
    """Result of a hook execution."""

    def __init__(
        self,
        allowed: bool,
        metadata: Optional[Dict[str, Any]] = None,
        modified_args: Optional[str] = None
    ):
        self.allowed = allowed
        self.metadata = metadata or {}
        self.modified_args = modified_args


class FunctionHook(ABC):
    """Base class for function call hooks."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def execute(
        self,
        function_name: str,
        arguments: str,
        context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> HookResult:
        """
        Execute the hook.

        Args:
            function_name: Name of the function being called
            arguments: JSON string of arguments
            context: Additional context (backend, timestamp, etc.)

        Returns:
            HookResult with allowed flag and optional modifications
        """
        pass


class FunctionHookManager:
    """Manages registration and execution of function hooks."""

    def __init__(self):
        self._hooks: Dict[HookType, List[FunctionHook]] = {
            hook_type: [] for hook_type in HookType
        }
        self._global_hooks: Dict[HookType, List[FunctionHook]] = {
            hook_type: [] for hook_type in HookType
        }

    def register_hook(self, function_name: str, hook_type: HookType, hook: FunctionHook):
        """Register a hook for a specific function."""
        if function_name not in self._hooks:
            self._hooks[function_name] = {hook_type: [] for hook_type in HookType}

        if hook_type not in self._hooks[function_name]:
            self._hooks[function_name][hook_type] = []

        self._hooks[function_name][hook_type].append(hook)

    def register_global_hook(self, hook_type: HookType, hook: FunctionHook):
        """Register a hook that applies to all functions."""
        self._global_hooks[hook_type].append(hook)

    def get_hooks_for_function(self, function_name: str) -> Dict[HookType, List[FunctionHook]]:
        """Get all hooks (function-specific + global) for a function."""
        result = {hook_type: [] for hook_type in HookType}

        # Add global hooks first
        for hook_type in HookType:
            result[hook_type].extend(self._global_hooks[hook_type])

        # Add function-specific hooks
        if function_name in self._hooks:
            for hook_type in HookType:
                if hook_type in self._hooks[function_name]:
                    result[hook_type].extend(self._hooks[function_name][hook_type])

        return result

    def clear_hooks(self):
        """Clear all registered hooks."""
        self._hooks.clear()
        self._global_hooks = {hook_type: [] for hook_type in HookType}


class PermissionClientSession(ClientSession):
    """
    ClientSession subclass that intercepts tool calls to apply permission hooks.

    This inherits from ClientSession instead of wrapping it, which ensures
    compatibility with SDK type checking and attribute access.
    """

    def __init__(self, wrapped_session: ClientSession, permission_manager):
        """
        Initialize by copying state from an existing ClientSession.

        Args:
            wrapped_session: The actual ClientSession to copy state from
            permission_manager: Object with pre_tool_use_hook method for validation
        """
        # Store the permission manager
        self._permission_manager = permission_manager

        # Copy all attributes from the wrapped session to this instance
        # This is a bit hacky but necessary to preserve the session state
        self.__dict__.update(wrapped_session.__dict__)

        logger.debug(f"[PermissionClientSession] Created permission session from {id(wrapped_session)}")

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        read_timeout_seconds: timedelta | None = None,
        progress_callback: ProgressFnT | None = None,
    ) -> types.CallToolResult:
        """
        Override call_tool to apply permission hooks before calling the actual tool.
        """
        tool_args = arguments or {}

        # Log tool call for debugging
        logger.debug(f"[PermissionClientSession] Intercepted tool call: {name} with args: {tool_args}")

        # Apply permission hook if available
        if self._permission_manager and hasattr(self._permission_manager, 'pre_tool_use_hook'):
            try:
                allowed, reason = await self._permission_manager.pre_tool_use_hook(name, tool_args)

                if not allowed:
                    error_msg = f"Permission denied for tool '{name}'"
                    if reason:
                        error_msg += f": {reason}"
                    logger.warning(f"🚫 [PermissionClientSession] {error_msg}")

                    # Return an error result instead of calling the tool
                    return types.CallToolResult(
                        content=[
                            types.TextContent(
                                type="text",
                                text=f"Error: {error_msg}"
                            )
                        ],
                        isError=True
                    )
                else:
                    logger.debug(f"[PermissionClientSession] Tool '{name}' permission check passed")

            except Exception as e:
                logger.error(f"[PermissionClientSession] Error in permission hook: {e}")
                # Continue with the call if hook fails - don't break functionality

        # Call the parent's call_tool method
        try:
            result = await super().call_tool(
                name=name,
                arguments=arguments,
                read_timeout_seconds=read_timeout_seconds,
                progress_callback=progress_callback
            )
            logger.debug(f"[PermissionClientSession] Tool '{name}' completed successfully")
            return result
        except Exception as e:
            logger.error(f"[PermissionClientSession] Tool '{name}' failed: {e}")
            raise

def convert_sessions_to_permission_sessions(
    sessions: List[ClientSession],
    permission_manager
) -> List[PermissionClientSession]:
    """
    Convert a list of ClientSession objects to PermissionClientSession subclasses.

    Args:
        sessions: List of ClientSession objects to convert
        permission_manager: Object with pre_tool_use_hook method

    Returns:
        List of PermissionClientSession objects that apply permission hooks
    """
    logger.debug(f"[PermissionClientSession] Converting {len(sessions)} sessions to permission sessions")
    converted = []
    for session in sessions:
        # Create a new PermissionClientSession that inherits from ClientSession
        perm_session = PermissionClientSession(session, permission_manager)
        converted.append(perm_session)
    logger.debug(f"[PermissionClientSession] Successfully converted {len(converted)} sessions")
    return converted

__all__ = [
    "HookType",
    "HookResult",
    "FunctionHook",
    "FunctionHookManager",
    "PermissionClientSession",
    "convert_sessions_to_permission_sessions",
]
