# -*- coding: utf-8 -*-
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..logger_config import logger
from ..mcp_tools.hooks import HookResult
from ._base import Permission


@dataclass
class ManagedPath:
    """Represents any managed path with its permissions and type."""

    path: Path
    permission: Permission
    path_type: str  # "workspace", "temp_workspace", "context", etc.
    will_be_writable: bool = False  # True if this path will become writable for final agent
    is_file: bool = False  # True if this is a file-specific context path (not directory)
    protected_paths: List[Path] = None  # Paths within this context that are immune from modification/deletion

    def __post_init__(self):
        """Initialize protected_paths as empty list if None."""
        if self.protected_paths is None:
            self.protected_paths = []

    def contains(self, check_path: Path) -> bool:
        """Check if this managed path contains the given path."""
        # If this is a file-specific path, only match the exact file
        if self.is_file:
            return check_path.resolve() == self.path.resolve()

        # Directory path: check if path is within directory
        try:
            check_path.resolve().relative_to(self.path.resolve())
            return True
        except ValueError:
            return False

    def is_protected(self, check_path: Path) -> bool:
        """Check if a path is in the protected paths list (immune from modification/deletion)."""
        if not self.protected_paths:
            return False

        resolved_check = check_path.resolve()
        for protected in self.protected_paths:
            resolved_protected = protected.resolve()
            # Check exact match or if check_path is within protected directory
            if resolved_check == resolved_protected:
                return True
            try:
                resolved_check.relative_to(resolved_protected)
                return True
            except ValueError:
                continue

        return False


class PathPermissionManager:
    """
    Manages all filesystem paths and implements PreToolUse hook functionality similar to Claude Code,
    allowing us to intercept and validate tool calls based on some predefined rules (here, permissions).

    This manager handles all types of paths with unified permission control:
    - Workspace paths (typically write)
    - Temporary workspace paths (typically read-only)
    - Context paths (user-specified permissions)
    - Tool call validation (PreToolUse hook)
    - Path access control
    """

    DEFAULT_EXCLUDED_PATTERNS = [
        ".massgen",
        ".env",
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".DS_Store",
        "massgen_logs",
    ]

    def __init__(self, context_write_access_enabled: bool = False):
        """
        Initialize path permission manager.

        Args:
            context_write_access_enabled: Whether write access is enabled for context paths (workspace paths always
                have write access). If False, we change all context paths to read-only. Can be later updated with
                set_context_write_access_enabled(), in which case all existing context paths will be updated
                accordingly so that those that were "write" in YAML become writable again.
        """
        self.managed_paths: List[ManagedPath] = []
        self.context_write_access_enabled = context_write_access_enabled

        # Cache for quick permission lookups
        self._permission_cache: Dict[Path, Permission] = {}

        logger.info(f"[PathPermissionManager] Initialized with context_write_access_enabled={context_write_access_enabled}")

    def add_path(self, path: Path, permission: Permission, path_type: str) -> None:
        """
        Add a managed path.

        Args:
            path: Path to manage
            permission: Permission level for this path
            path_type: Type of path ("workspace", "temp_workspace", "context", etc.)
        """
        if not path.exists():
            # For context paths, warn since user should provide existing paths
            # For workspace/temp paths, just debug since they'll be created by orchestrator
            if path_type == "context":
                logger.warning(f"[PathPermissionManager] Context path does not exist: {path}")
                return
            else:
                logger.debug(f"[PathPermissionManager] Path will be created later: {path} ({path_type})")

        managed_path = ManagedPath(path=path.resolve(), permission=permission, path_type=path_type)

        self.managed_paths.append(managed_path)
        # Clear cache when adding new paths
        self._permission_cache.clear()

        logger.info(f"[PathPermissionManager] Added {path_type} path: {path} ({permission.value})")

    def get_context_paths(self) -> List[Dict[str, str]]:
        """
        Get context paths in configuration format for system prompts.

        Returns:
            List of context path dictionaries with path, permission, and will_be_writable flag
        """
        context_paths = []
        for mp in self.managed_paths:
            if mp.path_type == "context":
                context_paths.append(
                    {
                        "path": str(mp.path),
                        "permission": mp.permission.value,
                        "will_be_writable": mp.will_be_writable,
                    },
                )
        return context_paths

    def set_context_write_access_enabled(self, enabled: bool) -> None:
        """
        Update write access setting for context paths and recalculate their permissions.
        Note: Workspace paths always have write access regardless of this setting.

        Args:
            enabled: Whether to enable write access for context paths
        """
        if self.context_write_access_enabled == enabled:
            return  # No change needed

        logger.info(f"[PathPermissionManager] Setting context_write_access_enabled to {enabled}")
        logger.info(f"[PathPermissionManager] Before update: {self.managed_paths=}")
        self.context_write_access_enabled = enabled

        # Recalculate permissions for existing context paths
        for mp in self.managed_paths:
            if mp.path_type == "context" and mp.will_be_writable:
                # Update permission based on new context_write_access_enabled setting
                if enabled:
                    mp.permission = Permission.WRITE
                    logger.debug(f"[PathPermissionManager] Enabled write access for {mp.path}")
                else:
                    mp.permission = Permission.READ
                    logger.debug(f"[PathPermissionManager] Keeping read-only for {mp.path}")

        logger.info(f"[PathPermissionManager] Updated context path permissions based on context_write_access_enabled={enabled}, now is {self.managed_paths=}")

        # Clear permission cache to force recalculation
        self._permission_cache.clear()

    def add_context_paths(self, context_paths: List[Dict[str, Any]]) -> None:
        """
        Add context paths from configuration.

        Now supports both files and directories as context paths, with optional protected paths.

        Args:
            context_paths: List of context path configurations
                Format: [
                    {
                        "path": "C:/project/src",
                        "permission": "write",
                        "protected_paths": ["tests/do-not-touch/", "config.yaml"]  # Optional
                    },
                    {"path": "C:/project/logo.png", "permission": "read"}
                ]

        Note: During coordination, all context paths are read-only regardless of YAML settings.
              Only the final agent with context_write_access_enabled=True can write to paths marked as "write".
              Protected paths are ALWAYS read-only and immune from deletion, even if parent has write permission.
        """
        for config in context_paths:
            path_str = config.get("path", "")
            permission_str = config.get("permission", "read")
            protected_paths_config = config.get("protected_paths", [])

            if not path_str:
                continue

            path = Path(path_str)

            # Check if path exists and whether it's a file or directory
            if not path.exists():
                logger.warning(f"[PathPermissionManager] Context path does not exist: {path}")
                continue

            is_file = path.is_file()

            # Parse protected paths - they can be relative to the context path or absolute
            protected_paths = []
            for protected_str in protected_paths_config:
                protected_path = Path(protected_str)
                # If relative, resolve relative to the context path
                if not protected_path.is_absolute():
                    if is_file:
                        # For file contexts, resolve relative to parent directory
                        protected_path = (path.parent / protected_str).resolve()
                    else:
                        # For directory contexts, resolve relative to the directory
                        protected_path = (path / protected_str).resolve()
                else:
                    protected_path = protected_path.resolve()

                # Validate that protected path is actually within the context path
                try:
                    if is_file:
                        # For file context, protected paths should be in same directory or subdirs
                        protected_path.relative_to(path.parent.resolve())
                    else:
                        # For directory context, protected paths should be within the directory
                        protected_path.relative_to(path.resolve())
                    protected_paths.append(protected_path)
                    logger.info(f"[PathPermissionManager] Added protected path: {protected_path}")
                except ValueError:
                    logger.warning(f"[PathPermissionManager] Protected path {protected_path} is not within context path {path}, skipping")

            # For file context paths, we need to add the parent directory to MCP allowed paths
            # but track only the specific file for permission purposes
            if is_file:
                logger.info(f"[PathPermissionManager] Detected file context path: {path}")
                # Add parent directory to allowed paths (needed for MCP filesystem access)
                parent_dir = path.parent
                if not any(mp.path == parent_dir.resolve() and mp.path_type == "file_context_parent" for mp in self.managed_paths):
                    # Add parent as a special type - not directly accessible, just for MCP
                    parent_managed = ManagedPath(path=parent_dir.resolve(), permission=Permission.READ, path_type="file_context_parent", will_be_writable=False, is_file=False)
                    self.managed_paths.append(parent_managed)
                    logger.debug(f"[PathPermissionManager] Added parent directory for file context: {parent_dir}")

            try:
                yaml_permission = Permission(permission_str.lower())
            except ValueError:
                logger.warning(f"[PathPermissionManager] Invalid permission '{permission_str}', using 'read'")
                yaml_permission = Permission.READ

            # Determine if this path will become writable for final agent
            will_be_writable = yaml_permission == Permission.WRITE

            # For context paths: only final agent (context_write_access_enabled=True) gets write permissions
            # All coordination agents get read-only access regardless of YAML
            if self.context_write_access_enabled and will_be_writable:
                actual_permission = Permission.WRITE
                logger.debug(f"[PathPermissionManager] Final agent: context path {path} gets write permission")
            else:
                actual_permission = Permission.READ if will_be_writable else yaml_permission
                if will_be_writable:
                    logger.debug(f"[PathPermissionManager] Coordination agent: context path {path} read-only (will be writable later)")

            # Create managed path with will_be_writable, is_file, and protected_paths
            managed_path = ManagedPath(
                path=path.resolve(),
                permission=actual_permission,
                path_type="context",
                will_be_writable=will_be_writable,
                is_file=is_file,
                protected_paths=protected_paths,
            )
            self.managed_paths.append(managed_path)
            self._permission_cache.clear()

            path_type_str = "file" if is_file else "directory"
            protected_count = len(protected_paths)
            logger.info(f"[PathPermissionManager] Added context {path_type_str}: {path} ({actual_permission.value}, will_be_writable: {will_be_writable}, protected_paths: {protected_count})")

    def add_previous_turn_paths(self, turn_paths: List[Dict[str, Any]]) -> None:
        """
        Add previous turn workspace paths for read access.
        These are tracked separately from regular context paths.

        Args:
            turn_paths: List of turn path configurations
                Format: [{"path": "/path/to/turn_1/workspace", "permission": "read"}, ...]
        """
        for config in turn_paths:
            path_str = config.get("path", "")
            if not path_str:
                continue

            path = Path(path_str).resolve()
            # Previous turn paths are always read-only
            managed_path = ManagedPath(path=path, permission=Permission.READ, path_type="previous_turn", will_be_writable=False)
            self.managed_paths.append(managed_path)
            self._permission_cache.clear()
            logger.info(f"[PathPermissionManager] Added previous turn path: {path} (read-only)")

    def _is_excluded_path(self, path: Path) -> bool:
        """
        Check if a path matches any default excluded patterns.

        System files like .massgen/, .env, .git/ are always excluded from write access,
        EXCEPT when they are within a managed workspace path (which has explicit permissions).

        Args:
            path: Path to check

        Returns:
            True if path should be excluded from write access
        """
        # First check if this path is inside a workspace - workspaces override exclusions
        for managed_path in self.managed_paths:
            if managed_path.path_type == "workspace" and managed_path.contains(path):
                return False

        # Now check if path contains any excluded patterns
        parts = path.parts
        for part in parts:
            if part in self.DEFAULT_EXCLUDED_PATTERNS:
                return True
        return False

    def get_permission(self, path: Path) -> Optional[Permission]:
        """
        Get permission level for a path.

        Now handles file-specific context paths correctly.

        Args:
            path: Path to check

        Returns:
            Permission level or None if path is not in context
        """
        resolved_path = path.resolve()

        # Check cache first
        if resolved_path in self._permission_cache:
            logger.debug(f"[PathPermissionManager] Permission cache hit for {resolved_path}: {self._permission_cache[resolved_path].value}")
            return self._permission_cache[resolved_path]

        # Check if this is an excluded path (always read-only)
        if self._is_excluded_path(resolved_path):
            logger.info(f"[PathPermissionManager] Path {resolved_path} matches excluded pattern, forcing read-only")
            self._permission_cache[resolved_path] = Permission.READ
            return Permission.READ

        # Check if this path is protected (always read-only, takes precedence over context permissions)
        for managed_path in self.managed_paths:
            if managed_path.contains(resolved_path) and managed_path.is_protected(resolved_path):
                logger.info(f"[PathPermissionManager] Path {resolved_path} is protected, forcing read-only")
                self._permission_cache[resolved_path] = Permission.READ
                return Permission.READ

        # Find containing managed path with priority system:
        # 1. File-specific paths (is_file=True) get highest priority - exact match only
        # 2. Deeper directory paths get higher priority than shallow ones
        # 3. file_context_parent type is lowest priority (used only for MCP access, not direct access)

        # Separate file-specific and directory paths
        file_paths = [mp for mp in self.managed_paths if mp.is_file]
        dir_paths = [mp for mp in self.managed_paths if not mp.is_file and mp.path_type != "file_context_parent"]
        # parent_paths are not used in permission checks - they're only for MCP allowed paths

        # Check file-specific paths first (highest priority, exact match only)
        for managed_path in file_paths:
            if managed_path.contains(resolved_path):  # contains() handles exact match for files
                logger.info(
                    f"[PathPermissionManager] Found file-specific permission for {resolved_path}: {managed_path.permission.value} "
                    f"(from {managed_path.path}, type: {managed_path.path_type}, "
                    f"will_be_writable: {managed_path.will_be_writable})",
                )
                self._permission_cache[resolved_path] = managed_path.permission
                return managed_path.permission

        # Check directory paths (sorted by depth, deeper = higher priority)
        sorted_dir_paths = sorted(dir_paths, key=lambda mp: len(mp.path.parts), reverse=True)
        for managed_path in sorted_dir_paths:
            if managed_path.contains(resolved_path) or managed_path.path == resolved_path:
                logger.info(
                    f"[PathPermissionManager] Found permission for {resolved_path}: {managed_path.permission.value} "
                    f"(from {managed_path.path}, type: {managed_path.path_type}, "
                    f"will_be_writable: {managed_path.will_be_writable})",
                )
                self._permission_cache[resolved_path] = managed_path.permission
                return managed_path.permission

        # Don't check parent_paths - they're only for MCP allowed paths, not for granting access
        # If we reach here, the path is either in a file_context_parent (denied) or not in any context path

        logger.debug(f"[PathPermissionManager] No permission found for {resolved_path} in managed paths: {[(str(mp.path), mp.permission.value, mp.path_type) for mp in self.managed_paths]}")
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

        # For all other tools (including Read, Grep, Glob, list_directory, etc.),
        # validate access to file context paths to prevent sibling file access
        return self._validate_file_context_access(tool_name, tool_args)

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
            r".*[Ww]rite.*",  # Write, write_file, NotebookWrite, etc.
            r".*[Ee]dit.*",  # Edit, edit_file, MultiEdit, NotebookEdit, etc.
            r".*[Cc]reate.*",  # create_directory, etc.
            r".*[Mm]ove.*",  # move_file, etc.
            r".*[Dd]elete.*",  # delete operations
            r".*[Rr]emove.*",  # remove operations
            r".*[Cc]opy.*",  # copy_file, copy_files_batch, etc.
        ]

        for pattern in write_patterns:
            if re.match(pattern, tool_name):
                return True

        return False

    def _validate_file_context_access(self, tool_name: str, tool_args: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate access for file context paths (prevents sibling file access).

        When a specific file is added as a context path, only that file should be accessible,
        not other files in the same directory. This method checks all tool calls to enforce this.
        """
        # Extract file path from arguments
        file_path = self._extract_file_path(tool_args)
        if not file_path:
            # Can't determine path - allow it (tool may not access files)
            return (True, None)

        # Resolve relative paths against workspace
        file_path = self._resolve_path_against_workspace(file_path)
        path = Path(file_path).resolve()
        permission = self.get_permission(path)
        logger.debug(f"[PathPermissionManager] Validating file context access for '{tool_name}' on path: {path} with permission: {permission}")

        # If permission is None, check if in file_context_parent directory
        if permission is None:
            parent_paths = [mp for mp in self.managed_paths if mp.path_type == "file_context_parent"]
            for parent_mp in parent_paths:
                if parent_mp.contains(path):
                    # Path is in a file context parent dir, but not the specific file
                    return (False, f"Access denied: '{path}' is not an explicitly allowed file in this directory")
            # Not in any managed paths - allow (likely workspace or other valid path)
            return (True, None)

        # Has explicit permission - allow
        return (True, None)

    def _validate_write_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate write tool access."""
        # Special handling for copy_files_batch - validate all destination paths after globbing
        if tool_name == "copy_files_batch":
            return self._validate_copy_files_batch(tool_args)

        # Extract file path from arguments
        file_path = self._extract_file_path(tool_args)
        if not file_path:
            # Can't determine path - allow it (likely workspace or other non-context path)
            return (True, None)

        # Resolve relative paths against workspace
        file_path = self._resolve_path_against_workspace(file_path)
        path = Path(file_path).resolve()
        permission = self.get_permission(path)
        logger.debug(f"[PathPermissionManager] Validating write tool '{tool_name}' for path: {path} with permission: {permission}")

        # No permission means not in context paths (workspace paths are always allowed)
        # IMPORTANT: Check if this path is in a file_context_parent directory
        # If so, access should be denied (only the specific file has access, not siblings)
        if permission is None:
            # Check if path is within a file_context_parent directory
            parent_paths = [mp for mp in self.managed_paths if mp.path_type == "file_context_parent"]
            for parent_mp in parent_paths:
                if parent_mp.contains(path):
                    # Path is in a file context parent dir, but not the specific file
                    # Deny access to prevent sibling file access
                    return (False, f"Access denied: '{path}' is not an explicitly allowed file in this directory")
            # Not in any managed paths - allow (likely workspace or other valid path)
            return (True, None)

        # Check write permission (permission is already set correctly based on context_write_access_enabled)
        if permission == Permission.WRITE:
            return (True, None)
        else:
            return (False, f"No write permission for '{path}' (read-only context path)")

    def _resolve_path_against_workspace(self, path_str: str) -> str:
        """
        Resolve a path string against the workspace directory if it's relative.

        When MCP servers run with cwd set to workspace, they resolve relative paths
        against the workspace. This function does the same for validation purposes.

        Args:
            path_str: Path string that may be relative or absolute

        Returns:
            Absolute path string (resolved against workspace if relative)
        """
        if not path_str:
            return path_str

        path = Path(path_str)
        if path.is_absolute():
            return path_str

        # Relative path - resolve against workspace
        mcp_paths = self.get_mcp_filesystem_paths()
        if mcp_paths:
            workspace_path = Path(mcp_paths[0])  # First path is always workspace
            resolved = workspace_path / path_str
            logger.debug(f"[PathPermissionManager] Resolved relative path '{path_str}' to '{resolved}'")
            return str(resolved)

        return path_str

    def _validate_copy_files_batch(self, tool_args: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate copy_files_batch by checking all destination paths after globbing."""
        try:
            logger.debug(f"[PathPermissionManager] copy_files_batch validation - context_write_access_enabled: {self.context_write_access_enabled}")
            # Import the helper function from workspace tools server
            from ._workspace_tools_server import get_copy_file_pairs

            # Get all the file pairs that would be copied
            source_base_path = tool_args.get("source_base_path")
            destination_base_path = tool_args.get("destination_base_path", "")
            include_patterns = tool_args.get("include_patterns")
            exclude_patterns = tool_args.get("exclude_patterns")

            if not source_base_path:
                return (False, "copy_files_batch requires source_base_path")

            # Resolve relative destination path against workspace
            destination_base_path = self._resolve_path_against_workspace(destination_base_path)

            # Get all file pairs (this also validates path restrictions)
            file_pairs = get_copy_file_pairs(self.get_mcp_filesystem_paths(), source_base_path, destination_base_path, include_patterns, exclude_patterns)

            # Check permissions for each destination path
            blocked_paths = []
            for source_file, dest_file in file_pairs:
                permission = self.get_permission(dest_file)
                logger.debug(f"[PathPermissionManager] copy_files_batch checking dest: {dest_file}, permission: {permission}")
                if permission == Permission.READ:
                    blocked_paths.append(str(dest_file))

            if blocked_paths:
                # Limit to first few blocked paths for readable error message
                example_paths = blocked_paths[:3]
                suffix = f" (and {len(blocked_paths) - 3} more)" if len(blocked_paths) > 3 else ""
                return (False, f"No write permission for destination paths: {', '.join(example_paths)}{suffix}")

            return (True, None)

        except Exception as e:
            return (False, f"copy_files_batch validation failed: {e}")

    def _validate_command_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate command tool access.

        As of v0.0.20, only Claude Code supports execution.

        """
        # Extract command from arguments
        command = tool_args.get("command", "") or tool_args.get("cmd", "")

        # Dangerous patterns to block
        dangerous_patterns = [
            "rm ",
            "rm -",
            "rmdir",
            "del ",
            "sudo ",
            "su ",
            "chmod ",
            "chown ",
            "format ",
            "fdisk",
            "mkfs",
        ]

        # File modification patterns to check when write access disabled
        write_patterns = [
            ">",
            ">>",  # Redirects
            "mv ",
            "move ",
            "cp ",
            "copy ",
            "touch ",
            "mkdir ",
            "echo ",
            "sed -i",
            "perl -i",  # In-place edits
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
        # - Workspace copy: source_path, destination_path, source_base_path, destination_base_path
        path_keys = [
            "file_path",
            "path",
            "filename",
            "file",
            "notebook_path",
            "target",
            "destination",
            "destination_path",
            "destination_base_path",
        ]  # source paths should NOT be checked bc they are always read from, not written to

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
                    return target.strip("\"'")

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

        # For simple commands like touch, mkdir, echo (first argument after command)
        if pattern in ["touch ", "mkdir ", "echo "]:
            parts = command.split()
            try:
                idx = parts.index(pattern.strip())
                if idx + 1 < len(parts):
                    # The first argument is the target
                    return parts[idx + 1].strip("\"'")
            except (ValueError, IndexError):
                pass

        return None

    def get_accessible_paths(self) -> List[Path]:
        """Get list of all accessible paths."""
        return [path.path for path in self.managed_paths]

    def get_mcp_filesystem_paths(self) -> List[str]:
        """
        Get all managed paths for MCP filesystem server configuration. Workspace path will be first.

        Only returns directories, as MCP filesystem server cannot accept file paths as arguments.
        For file context paths, the parent directory is already added with path_type="file_context_parent".

        Returns:
            List of directory path strings to include in MCP filesystem server args
        """
        # Only include directories - exclude file-type managed paths (is_file=True)
        # The parent directory for file contexts is already added separately
        workspace_paths = [str(mp.path) for mp in self.managed_paths if mp.path_type == "workspace"]
        other_paths = [str(mp.path) for mp in self.managed_paths if mp.path_type != "workspace" and not mp.is_file]
        out = workspace_paths + other_paths
        return out

    def get_permission_summary(self) -> str:
        """Get a human-readable summary of permissions."""
        if not self.managed_paths:
            return "No managed paths configured"

        lines = [f"Managed paths ({len(self.managed_paths)} total):"]
        for managed_path in self.managed_paths:
            emoji = "📝" if managed_path.permission == Permission.WRITE else "👁️"
            lines.append(f"  {emoji} {managed_path.path} ({managed_path.permission.value}, {managed_path.path_type})")

        return "\n".join(lines)

    async def validate_context_access(self, input_data: Dict[str, Any], tool_use_id: Optional[str], context: Any) -> Dict[str, Any]:  # HookContext from claude_code_sdk
        """
        Claude Code SDK compatible hook function for PreToolUse.

        Args:
            input_data: Tool input data with 'tool_name' and 'tool_input'
            tool_use_id: Tool use identifier
            context: HookContext from claude_code_sdk

        Returns:
            Hook response dict with permission decision
        """
        logger.info(f"[PathPermissionManager] PreToolUse hook called for tool_use_id={tool_use_id}, input_data={input_data}")

        tool_name = input_data.get("tool_name", "")
        tool_input = input_data.get("tool_input", {})

        # Use our existing validation logic
        allowed, reason = await self.pre_tool_use_hook(tool_name, tool_input)

        if not allowed:
            logger.warning(f"[PathPermissionManager] Blocked {tool_name}: {reason}")
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": reason or "Access denied based on context path permissions"}}

        return {}  # Empty response means allow

    def get_claude_code_hooks_config(self) -> Dict[str, Any]:
        """
        Get Claude Code SDK hooks configuration.

        Returns:
            Hooks configuration dict for ClaudeCodeOptions
        """
        if not self.managed_paths:
            return {}

        # Import here to avoid dependency issues if SDK not available
        try:
            from claude_code_sdk import HookMatcher
        except ImportError:
            logger.warning("[PathPermissionManager] claude_code_sdk not available, hooks disabled")
            return {}

        return {
            "PreToolUse": [
                # Apply context validation to write tools
                HookMatcher(matcher="Write", hooks=[self.validate_context_access]),
                HookMatcher(matcher="Edit", hooks=[self.validate_context_access]),
                HookMatcher(matcher="MultiEdit", hooks=[self.validate_context_access]),
                HookMatcher(matcher="NotebookEdit", hooks=[self.validate_context_access]),
                HookMatcher(matcher="Bash", hooks=[self.validate_context_access]),
            ],
        }


# Hook implementation for PathPermissionManager
class PathPermissionManagerHook:
    """
    Simple FunctionHook implementation that uses PathPermissionManager.

    This bridges the PathPermissionManager to the FunctionHook system.
    """

    def __init__(self, path_permission_manager):
        self.name = "path_permission_hook"
        self.path_permission_manager = path_permission_manager

    async def execute(self, function_name: str, arguments: str, context=None, **kwargs):
        """Execute permission check using PathPermissionManager."""
        try:
            # Import hook result here to avoid circular imports
            # Parse arguments from JSON string

            try:
                tool_args = json.loads(arguments) if arguments else {}
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"[PathPermissionManagerHook] Invalid JSON arguments for {function_name}: {e}")
                tool_args = {}

            # Call the existing pre_tool_use_hook method
            allowed, reason = await self.path_permission_manager.pre_tool_use_hook(function_name, tool_args)

            if not allowed:
                logger.info(f"[PathPermissionManagerHook] Blocked {function_name}: {reason}")

            return HookResult(allowed=allowed, metadata={"reason": reason} if reason else {})

        except Exception as e:
            logger.error(f"[PathPermissionManagerHook] Error checking permissions for {function_name}: {e}")
            # Fail closed - deny access on permission check errors
            return HookResult(allowed=False, metadata={"error": str(e), "reason": "Permission check failed"})
