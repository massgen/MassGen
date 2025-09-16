"""
Function call hook system for MCP tools.

Provides a unified way to intercept and validate MCP tool calls
across all backends through the Function.call() interface.
"""

import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from enum import Enum
try:
    from ..logger_config import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class HookType(Enum):
    """Types of function call hooks."""
    PRE_CALL = "pre_call"     # Before function execution - can block/modify
    # TODO: Add POST_CALL, ON_ERROR hooks later


class HookResult:
    """Result from hook execution."""

    def __init__(
        self,
        allowed: bool = True,
        modified_args: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        self.allowed = allowed
        self.modified_args = modified_args
        self.metadata = metadata or {}


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


class PermissionHook(FunctionHook):
    """Hook for permission checking."""

    def __init__(self, permission_manager, name: str = "permission_hook"):
        super().__init__(name)
        self.permission_manager = permission_manager

    async def execute(
        self,
        function_name: str,
        arguments: str,
        context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> HookResult:
        """Check if function call is permitted."""
        try:
            # Check permissions via permission manager
            allowed = await self.permission_manager.check_tool_access(
                function_name,
                arguments,
                context=context
            )

            if not allowed:
                logger.warning(
                    f"Permission denied for tool call: {function_name}",
                    extra={"context": context}
                )

            return HookResult(allowed=allowed)

        except Exception as e:
            logger.error(f"Permission check failed for {function_name}: {e}")
            # Fail closed - deny access on permission check errors
            return HookResult(allowed=False)