"""
Context Path Manager - Manages permissions for context paths and validates tool access.

This module implements a hook-like system similar to Claude Code's PreToolUse hook,
allowing us to intercept and validate tool calls based on context path permissions.
"""

from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from dataclasses import dataclass
from ..logger_config import logger


class Permission(Enum):
    """File access permission types."""
    READ = "read"
    WRITE = "write"


@dataclass
class ManagedPath:
    """Represents any managed path with its permissions and type."""
    path: Path
    permission: Permission
    path_type: str  # "workspace", "temp_workspace", "context", etc.
    original_permission: Optional[Permission] = None  # Original YAML permission for context paths

    def contains(self, check_path: Path) -> bool:
        """Check if this managed path contains the given path."""
        try:
            check_path.resolve().relative_to(self.path.resolve())
            return True
        except ValueError:
            return False


# Backwards compatibility alias
ContextPath = ManagedPath


class PathPermissionManager:
    """
    Manages all filesystem paths and implements PreToolUse hook functionality.

    This manager handles all types of paths with unified permission control:
    - Workspace paths (typically write)
    - Temporary workspace paths (typically read-only)
    - Context paths (user-specified permissions)
    - Tool call validation (PreToolUse hook)
    - Path access control
    """

    def __init__(self, write_access_enabled: bool = False):
        """
        Initialize path permission manager.

        Args:
            write_access_enabled: Whether write access is enabled for this agent
        """
        self.managed_paths: List[ManagedPath] = []
        self.write_access_enabled = write_access_enabled

        # Cache for quick permission lookups
        self._permission_cache: Dict[Path, Permission] = {}

        logger.info(
            f"[PathPermissionManager] Initialized with write_access_enabled={write_access_enabled}"
        )

    def add_path(self, path: Path, permission: Permission, path_type: str) -> None:
        """
        Add a managed path.

        Args:
            path: Path to manage
            permission: Permission level for this path
            path_type: Type of path ("workspace", "temp_workspace", "context", etc.)
        """
        if not path.exists():
            logger.warning(f"[PathPermissionManager] Path does not exist: {path}")
            return

        managed_path = ManagedPath(
            path=path.resolve(),
            permission=permission,
            path_type=path_type
        )

        self.managed_paths.append(managed_path)
        # Clear cache when adding new paths
        self._permission_cache.clear()

        logger.info(f"[PathPermissionManager] Added {path_type} path: {path} ({permission.value})")

    def get_context_paths(self) -> List[Dict[str, str]]:
        """
        Get context paths in configuration format for system prompts.

        Returns:
            List of context path dictionaries with path and permission
        """
        context_paths = []
        for mp in self.managed_paths:
            if mp.path_type == "context":
                context_paths.append({
                    "path": str(mp.path),
                    "permission": mp.permission.value
                })
        return context_paths

    def set_write_access_enabled(self, enabled: bool) -> None:
        """
        Update write access setting and recalculate context path permissions.

        Args:
            enabled: Whether to enable write access
        """
        if self.write_access_enabled == enabled:
            return  # No change needed

        logger.info(f"[PathPermissionManager] Setting write_access_enabled to {enabled}")
        self.write_access_enabled = enabled

        # Recalculate permissions for existing context paths
        for mp in self.managed_paths:
            if mp.path_type == "context" and mp.original_permission:
                # Update permission based on new write_access_enabled setting
                if enabled:
                    mp.permission = mp.original_permission
                    logger.debug(f"[PathPermissionManager] Restored original permission for {mp.path}: {mp.permission.value}")
                else:
                    mp.permission = Permission.READ
                    logger.debug(f"[PathPermissionManager] Forced read-only for {mp.path}")

        # Clear permission cache to force recalculation
        self._permission_cache.clear()

    def add_context_paths(self, context_paths: List[Dict[str, Any]]) -> None:
        """
        Add context paths from configuration.

        Args:
            context_paths: List of context path configurations
                Format: [{"path": "C:/project/src", "permission": "write"}, ...]

        Note: During coordination, all context paths are read-only regardless of YAML settings.
              Only the final agent with write_access_enabled=True can write to paths marked as "write".
        """
        for config in context_paths:
            path_str = config.get("path", "")
            permission_str = config.get("permission", "read")

            if not path_str:
                continue

            path = Path(path_str)

            try:
                yaml_permission = Permission(permission_str.lower())
            except ValueError:
                logger.warning(f"[PathPermissionManager] Invalid permission '{permission_str}', using 'read'")
                yaml_permission = Permission.READ

            # For context paths: only final agent (write_access_enabled=True) gets original permissions
            # All coordination agents get read-only access regardless of YAML
            if self.write_access_enabled:
                actual_permission = yaml_permission
                logger.debug(f"[PathPermissionManager] Final agent: context path {path} gets {actual_permission.value} permission")
            else:
                actual_permission = Permission.READ
                if yaml_permission == Permission.WRITE:
                    logger.debug(f"[PathPermissionManager] Coordination agent: forcing context path {path} to read-only (YAML had write)")

            # Create managed path with original permission stored for context paths
            managed_path = ManagedPath(
                path=path.resolve(),
                permission=actual_permission,
                path_type="context",
                original_permission=yaml_permission
            )
            self.managed_paths.append(managed_path)
            self._permission_cache.clear()
            logger.info(f"[PathPermissionManager] Added context path: {path} ({actual_permission.value}, original: {yaml_permission.value})")


    def get_permission(self, path: Path) -> Optional[Permission]:
        """
        Get permission level for a path.

        Args:
            path: Path to check

        Returns:
            Permission level or None if path is not in context
        """
        resolved_path = path.resolve()

        # Check cache first
        if resolved_path in self._permission_cache:
            return self._permission_cache[resolved_path]

        # Find containing managed path
        for managed_path in self.managed_paths:
            if managed_path.contains(resolved_path) or managed_path.path == resolved_path:
                self._permission_cache[resolved_path] = managed_path.permission
                return managed_path.permission

        return None

    async def pre_tool_use_hook(self, tool_name: str, tool_args: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        PreToolUse hook to validate tool calls based on permissions.

        This can be used directly with Claude Code SDK hooks or as validation
        for other backends that need manual tool call filtering.

        Args:
            tool_name: Name of the tool being called
            tool_args: Arguments passed to the tool

        Returns:
            Tuple of (allowed: bool, reason: Optional[str])
            - allowed: Whether the tool call should proceed
            - reason: Explanation if blocked (None if allowed)
        """
        # Check if this is a write operation using pattern matching
        if self._is_write_tool(tool_name):
            return self._validate_write_tool(tool_name, tool_args)

        # Tools that can potentially modify through commands
        command_tools = {"Bash", "bash", "shell", "exec"}

        # Check command tools for dangerous operations
        if tool_name in command_tools:
            return self._validate_command_tool(tool_name, tool_args)

        # All other tools are allowed
        return (True, None)

    def _is_write_tool(self, tool_name: str) -> bool:
        """
        Check if a tool is a write operation using pattern matching.

        Main Claude Code tools: Bash, Glob, Grep, Read, Edit, MultiEdit, Write, WebFetch, WebSearch

        This catches various write tools including:
        - Claude Code: Write, Edit, MultiEdit, NotebookEdit, etc.
        - MCP filesystem: write_file, edit_file, create_directory, move_file
        - Any other tools with write/edit/create/move in the name
        """
        import re

        # Pattern matches tools that modify files/directories
        write_patterns = [
            r".*[Ww]rite.*",      # Write, write_file, NotebookWrite, etc.
            r".*[Ee]dit.*",       # Edit, edit_file, MultiEdit, NotebookEdit, etc.
            r".*[Cc]reate.*",     # create_directory, etc.
            r".*[Mm]ove.*",       # move_file, etc.
            r".*[Dd]elete.*",     # delete operations
            r".*[Rr]emove.*",     # remove operations
        ]

        for pattern in write_patterns:
            if re.match(pattern, tool_name):
                return True

        return False

    def _validate_write_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate write tool access."""
        # Extract file path from arguments
        file_path = self._extract_file_path(tool_args)
        if not file_path:
            # Can't determine path, err on the side of caution
            if not self.write_access_enabled:
                return (False, f"Write tool '{tool_name}' blocked (write access not enabled)")
            return (True, None)

        path = Path(file_path).resolve()
        permission = self.get_permission(path)

        # No permission means not in context paths
        if permission is None:
            # Check if it's in the workspace (always allowed)
            # This will be handled by checking if path is under workspace root
            return (True, None)

        # Check write permission
        if permission == Permission.WRITE:
            if self.write_access_enabled:
                return (True, None)
            else:
                return (False, f"Write to '{path}' blocked (write access not enabled for this agent)")
        else:
            return (False, f"No write permission for '{path}' (read-only context path)")

    def _validate_command_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate command tool access."""
        # Extract command from arguments
        command = tool_args.get("command", "") or tool_args.get("cmd", "")

        # Dangerous patterns to block
        dangerous_patterns = [
            "rm ", "rm -", "rmdir", "del ",
            "sudo ", "su ", "chmod ", "chown ",
            "format ", "fdisk", "mkfs",
        ]

        # File modification patterns to check when write access disabled
        if not self.write_access_enabled:
            write_patterns = [
                ">", ">>",  # Redirects
                "mv ", "move ", "cp ", "copy ",
                "touch ", "mkdir ", "echo ",
                "sed -i", "perl -i",  # In-place edits
            ]

            for pattern in write_patterns:
                if pattern in command:
                    # Try to extract the target file
                    target_file = self._extract_file_from_command(command, pattern)
                    if target_file:
                        path = Path(target_file).resolve()
                        permission = self.get_permission(path)
                        if permission and permission == Permission.READ:
                            return (False, f"Command would modify read-only context path: {path}")

                    if not self._has_write_permissions():
                        return (False, f"File modification commands blocked (write access not enabled)")

        # Always block dangerous commands
        for pattern in dangerous_patterns:
            if pattern in command.lower():
                return (False, f"Dangerous command pattern '{pattern}' is not allowed")

        return (True, None)

    def _extract_file_path(self, tool_args: Dict[str, Any]) -> Optional[str]:
        """Extract file path from tool arguments."""
        # Common argument names for file paths:
        # - Claude Code: file_path, notebook_path
        # - MCP filesystem: path, source, destination
        path_keys = ["file_path", "path", "filename", "file", "notebook_path", "target", "source", "destination"]

        for key in path_keys:
            if key in tool_args:
                return tool_args[key]

        return None

    def _extract_file_from_command(self, command: str, pattern: str) -> Optional[str]:
        """Try to extract target file from a command string."""
        # This is a simplified extraction - could be enhanced
        # For redirects like > or >>
        if pattern in [">", ">>"]:
            parts = command.split(pattern)
            if len(parts) > 1:
                # Get the part after redirect, strip whitespace and quotes
                target = parts[1].strip().split()[0] if parts[1].strip() else None
                if target:
                    return target.strip('"\'')

        # For commands like mv, cp
        if pattern in ["mv ", "cp ", "move ", "copy "]:
            parts = command.split()
            try:
                idx = parts.index(pattern.strip())
                if idx + 2 < len(parts):
                    # The second argument is typically the destination
                    return parts[idx + 2]
            except (ValueError, IndexError):
                pass

        return None

    def _has_write_permissions(self) -> bool:
        """Check if any managed paths have write permission."""
        return any(path.permission == Permission.WRITE for path in self.managed_paths)

    def get_accessible_paths(self) -> List[Path]:
        """Get list of all accessible paths."""
        return [path.path for path in self.managed_paths]

    def get_mcp_filesystem_paths(self) -> List[str]:
        """
        Get all managed paths for MCP filesystem server configuration.

        Returns:
            List of path strings to include in MCP filesystem server args
        """
        return [str(managed_path.path) for managed_path in self.managed_paths]

    def get_permission_summary(self) -> str:
        """Get a human-readable summary of permissions."""
        if not self.managed_paths:
            return "No managed paths configured"

        lines = [f"Managed paths ({len(self.managed_paths)} total):"]
        for managed_path in self.managed_paths:
            emoji = "📝" if managed_path.permission == Permission.WRITE else "👁️"
            lines.append(f"  {emoji} {managed_path.path} ({managed_path.permission.value}, {managed_path.path_type})")

        if not self.write_access_enabled:
            if self._has_write_permissions():
                lines.append("\n⚠️  Write operations are blocked (write access not enabled)")
                lines.append("    Files will be modifiable when write access is enabled")
            else:
                lines.append("\nℹ️  All managed paths are read-only")

        return "\n".join(lines)

    async def validate_context_access(
        self,
        input_data: Dict[str, Any],
        tool_use_id: Optional[str],
        context: Any  # HookContext from claude_code_sdk
    ) -> Dict[str, Any]:
        """
        Claude Code SDK compatible hook function for PreToolUse.

        Args:
            input_data: Tool input data with 'tool_name' and 'tool_input'
            tool_use_id: Tool use identifier
            context: HookContext from claude_code_sdk

        Returns:
            Hook response dict with permission decision
        """
        tool_name = input_data.get('tool_name', '')
        tool_input = input_data.get('tool_input', {})

        # Use our existing validation logic
        allowed, reason = self.pre_tool_use_hook(tool_name, tool_input)

        if not allowed:
            logger.warning(f"[ContextPathManager] Blocked {tool_name}: {reason}")
            return {
                'hookSpecificOutput': {
                    'hookEventName': 'PreToolUse',
                    'permissionDecision': 'deny',
                    'permissionDecisionReason': reason or 'Access denied based on context path permissions'
                }
            }

        return {}  # Empty response means allow

    def get_claude_code_hooks_config(self) -> Dict[str, Any]:
        """
        Get Claude Code SDK hooks configuration.

        Returns:
            Hooks configuration dict for ClaudeCodeOptions
        """
        if not self.context_paths:
            return {}

        # Import here to avoid dependency issues if SDK not available
        try:
            from claude_code_sdk import HookMatcher
        except ImportError:
            logger.warning("[ContextPathManager] claude_code_sdk not available, hooks disabled")
            return {}

        return {
            'PreToolUse': [
                # Apply context validation to write tools
                HookMatcher(
                    matcher='Write',
                    hooks=[self.validate_context_access]
                ),
                HookMatcher(
                    matcher='Edit',
                    hooks=[self.validate_context_access]
                ),
                HookMatcher(
                    matcher='MultiEdit',
                    hooks=[self.validate_context_access]
                ),
                HookMatcher(
                    matcher='NotebookEdit',
                    hooks=[self.validate_context_access]
                ),
                HookMatcher(
                    matcher='Bash',
                    hooks=[self.validate_context_access]
                ),
            ]
        }


# Backwards compatibility alias
ContextPathManager = PathPermissionManager