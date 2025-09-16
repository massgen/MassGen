"""
Bridge between existing PathPermissionManager and new Function hook system.

This module provides adapters to connect the legacy filesystem permission
system with the new unified Function hook architecture.
"""

import json
from typing import Any, Dict, Optional
try:
    from .hooks import FunctionHook, HookResult
except ImportError:
    from hooks import FunctionHook, HookResult

try:
    from ..logger_config import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)


class PathPermissionBridge(FunctionHook):
    """
    Adapter that bridges PathPermissionManager to the new Function hook system.

    This allows existing filesystem permission logic to work seamlessly
    with the new unified hook architecture.
    """

    def __init__(self, path_permission_manager, name: str = "path_permission_bridge"):
        super().__init__(name)
        self.path_permission_manager = path_permission_manager
        logger.debug(f"[PathPermissionBridge] Initialized bridge for {name}")

    async def execute(
        self,
        function_name: str,
        arguments: str,
        context: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> HookResult:
        """
        Execute permission check using existing PathPermissionManager.

        Args:
            function_name: Name of the MCP tool being called
            arguments: JSON string of tool arguments
            context: Additional context from Function call

        Returns:
            HookResult with permission decision
        """
        try:
            # Parse arguments from JSON string
            try:
                tool_args = json.loads(arguments) if arguments else {}
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"[PathPermissionBridge] Invalid JSON arguments for {function_name}: {e}")
                tool_args = {}

            # Call the existing pre_tool_use_hook method
            allowed, reason = await self.path_permission_manager.pre_tool_use_hook(
                function_name, tool_args
            )

            if not allowed:
                logger.info(f"[PathPermissionBridge] Blocked {function_name}: {reason}")

            return HookResult(
                allowed=allowed,
                metadata={"reason": reason} if reason else {}
            )

        except Exception as e:
            logger.error(f"[PathPermissionBridge] Error checking permissions for {function_name}: {e}")
            # Fail closed - deny access on permission check errors
            return HookResult(
                allowed=False,
                metadata={"error": str(e), "reason": "Permission check failed"}
            )


class FilesystemManagerBridge:
    """
    Helper to automatically register filesystem permission hooks with Function hook system.
    """

    @staticmethod
    def register_filesystem_hooks(filesystem_manager, function_hook_manager):
        """
        Register filesystem permission hooks with the Function hook system.

        Args:
            filesystem_manager: FilesystemManager instance with PathPermissionManager
            function_hook_manager: Global FunctionHookManager instance
        """
        if not filesystem_manager or not function_hook_manager:
            logger.debug("[FilesystemManagerBridge] No filesystem manager or hook manager, skipping registration")
            return

        if not hasattr(filesystem_manager, 'path_permission_manager'):
            logger.debug("[FilesystemManagerBridge] No path_permission_manager, skipping registration")
            return

        try:
            # Import hook types
            try:
                from .hooks import HookType
            except ImportError:
                from hooks import HookType

            # Create bridge hook
            bridge_hook = PathPermissionBridge(
                filesystem_manager.path_permission_manager,
                name="filesystem_permission_bridge"
            )

            # Register as global hook for all functions
            function_hook_manager.register_global_hook(HookType.PRE_CALL, bridge_hook)

            logger.info("[FilesystemManagerBridge] Successfully registered filesystem permission hooks with Function hook system")

        except Exception as e:
            logger.error(f"[FilesystemManagerBridge] Failed to register filesystem hooks: {e}")

    @staticmethod
    def ensure_filesystem_hooks_registered(backend_instance):
        """
        Ensure filesystem permission hooks are registered for a backend instance.

        This is a convenience method that can be called during backend initialization
        to automatically bridge the permission systems.

        Args:
            backend_instance: Backend instance with filesystem_manager attribute
        """
        try:
            # Import the global hook manager
            try:
                from .hook_manager import function_hook_manager
            except ImportError:
                from hook_manager import function_hook_manager

            if hasattr(backend_instance, 'filesystem_manager') and backend_instance.filesystem_manager:
                FilesystemManagerBridge.register_filesystem_hooks(
                    backend_instance.filesystem_manager,
                    function_hook_manager
                )
                logger.debug(f"[FilesystemManagerBridge] Ensured hooks registered for backend {getattr(backend_instance, 'get_provider_name', lambda: 'unknown')()}")
            else:
                logger.debug(f"[FilesystemManagerBridge] No filesystem manager on backend {getattr(backend_instance, 'get_provider_name', lambda: 'unknown')()}")

        except Exception as e:
            logger.error(f"[FilesystemManagerBridge] Failed to ensure filesystem hooks: {e}")


# Convenience function for easy backend integration
async def setup_backend_permission_hooks(backend_instance):
    """
    Setup permission hooks for a backend instance.

    This function should be called during backend initialization to automatically
    bridge the existing filesystem permission system with the new Function hooks.

    Args:
        backend_instance: Backend instance to setup hooks for
    """
    try:
        FilesystemManagerBridge.ensure_filesystem_hooks_registered(backend_instance)
        logger.debug(f"[setup_backend_permission_hooks] Permission hooks setup complete for {getattr(backend_instance, 'get_provider_name', lambda: 'unknown')()}")
    except Exception as e:
        logger.error(f"[setup_backend_permission_hooks] Failed to setup permission hooks: {e}")