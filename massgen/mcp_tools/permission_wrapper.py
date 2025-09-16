"""
MCP ClientSession permission wrapper for filesystem access control.

This module provides PermissionClientSession, a subclass of ClientSession that
intercepts tool calls to apply permission validation. This works with both
manual tool calling and SDK auto-calling (like Gemini's built-in MCP support).
"""
from typing import Any, Dict, Optional, List
from datetime import timedelta
import logging
from mcp import ClientSession, types
from mcp.client.session import ProgressFnT

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


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
