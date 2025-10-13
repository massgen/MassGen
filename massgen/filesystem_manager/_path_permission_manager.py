# -*- coding: utf-8 -*-
import fnmatch
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..logger_config import logger
from ..mcp_tools.hooks import HookResult
from ._base import Permission
from ._file_operation_tracker import FileOperationTracker
from ._workspace_tools_server import get_copy_file_pairs


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

    def __init__(self, context_write_access_enabled: bool = False, enforce_read_before_delete: bool = True):
        """
        Initialize path permission manager.

        Args:
            context_write_access_enabled: Whether write access is enabled for context paths (workspace paths always
                have write access). If False, we change all context paths to read-only. Can be later updated with
                set_context_write_access_enabled(), in which case all existing context paths will be updated
                accordingly so that those that were "write" in YAML become writable again.
            enforce_read_before_delete: Whether to enforce read-before-delete policy for workspace files
        """
        self.managed_paths: List[ManagedPath] = []
        self.context_write_access_enabled = context_write_access_enabled

        # Cache for quick permission lookups
        self._permission_cache: Dict[Path, Permission] = {}

        # File operation tracker for read-before-delete enforcement
        self.file_operation_tracker = FileOperationTracker(enforce_read_before_delete=enforce_read_before_delete)

        logger.info(f"[PathPermissionManager] Initialized with context_write_access_enabled={context_write_access_enabled}, enforce_read_before_delete={enforce_read_before_delete}")

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
        # Track read operations for read-before-delete enforcement
        if self._is_read_tool(tool_name):
            self._track_read_operation(tool_name, tool_args)

        # Check if this is a write operation using pattern matching
        if self._is_write_tool(tool_name):
            result = self._validate_write_tool(tool_name, tool_args)
            # Track file creation for write tools that succeed
            if result[0] and self._is_create_tool(tool_name):
                self._track_create_operation(tool_name, tool_args)
            return result

        # Check if this is a delete operation
        if self._is_delete_tool(tool_name):
            return self._validate_delete_tool(tool_name, tool_args)

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

        Note: Delete operations are handled separately by _is_delete_tool
        """
        # Pattern matches tools that modify files/directories (excluding deletes)
        write_patterns = [
            r".*[Ww]rite.*",  # Write, write_file, NotebookWrite, etc.
            r".*[Ee]dit.*",  # Edit, edit_file, MultiEdit, NotebookEdit, etc.
            r".*[Cc]reate.*",  # create_directory, etc.
            r".*[Mm]ove.*",  # move_file, etc.
            r".*[Cc]opy.*",  # copy_file, copy_files_batch, etc.
        ]

        for pattern in write_patterns:
            if re.match(pattern, tool_name):
                return True

        return False

    def _is_read_tool(self, tool_name: str) -> bool:
        """
        Check if a tool is a read operation that should be tracked.

        Uses substring matching to handle MCP prefixes (e.g., mcp__workspace_tools__compare_files)

        Tools that read file contents:
        - read/Read: File content reading (matches: Read, read_text_file, read_multimodal_files, etc.)
        - compare_files: File comparison
        - compare_directories: Directory comparison
        """
        # Use lowercase for case-insensitive matching
        tool_lower = tool_name.lower()

        # Check if tool name contains any read operation keywords
        read_keywords = [
            # "read",  # Matches: read, Read, read_multimodal_files, mcp__filesystem__read_text_file
            "compare_files",  # Matches: compare_files
            "compare_directories",  # Matches: compare_directories
        ]

        return any(keyword in tool_lower for keyword in read_keywords)

    def _is_delete_tool(self, tool_name: str) -> bool:
        """
        Check if a tool is a delete operation.

        Tools that delete files:
        - delete_file: Single file deletion
        - delete_files_batch: Batch file deletion
        - Any tool with delete/remove in the name
        """
        delete_patterns = [
            r".*[Dd]elete.*",  # delete_file, delete_files_batch, etc.
            r".*[Rr]emove.*",  # remove operations
        ]

        for pattern in delete_patterns:
            if re.match(pattern, tool_name):
                return True

        return False

    def _is_create_tool(self, tool_name: str) -> bool:
        """
        Check if a tool creates new files (for tracking created files).

        Tools that create files:
        - Write: Creates new files
        - write_file: MCP filesystem write
        - create_directory: Creates directories
        """
        create_patterns = [
            r".*[Ww]rite.*",  # Write, write_file, etc.
            r".*[Cc]reate.*",  # create_directory, etc.
        ]

        for pattern in create_patterns:
            if re.match(pattern, tool_name):
                return True

        return False

    def _track_read_operation(self, tool_name: str, tool_args: Dict[str, Any]) -> None:
        """
        Track files that are read by the agent.

        Uses substring matching to handle MCP prefixes consistently.

        Args:
            tool_name: Name of the read tool
            tool_args: Arguments passed to the tool
        """
        tool_lower = tool_name.lower()

        # Extract file path(s) from arguments based on tool type
        if "compare_files" in tool_lower:
            # Compare files reads both files
            file1 = tool_args.get("file1") or tool_args.get("file_path1")
            file2 = tool_args.get("file2") or tool_args.get("file_path2")
            if file1:
                path1 = self._resolve_path_against_workspace(file1)
                self.file_operation_tracker.mark_as_read(Path(path1))
            if file2:
                path2 = self._resolve_path_against_workspace(file2)
                self.file_operation_tracker.mark_as_read(Path(path2))
        elif "compare_directories" in tool_lower:
            # Only track if show_content_diff is True (otherwise no content is read)
            if tool_args.get("show_content_diff"):
                # Note: We can't track specific files here, but comparison counts as viewing
                # The validation will happen on delete anyway
                pass
        elif "read_multiple_files" in tool_lower:
            # Read multiple files takes an array of paths
            paths = tool_args.get("paths", [])
            for file_path in paths:
                resolved_path = self._resolve_path_against_workspace(file_path)
                self.file_operation_tracker.mark_as_read(Path(resolved_path))
        else:
            # Single file read operations (Read, read_text_file, read_multimodal_files, etc.)
            file_path = self._extract_file_path(tool_args)
            if file_path:
                resolved_path = self._resolve_path_against_workspace(file_path)
                self.file_operation_tracker.mark_as_read(Path(resolved_path))

    def _track_create_operation(self, tool_name: str, tool_args: Dict[str, Any]) -> None:
        """
        Track files that are created by the agent.

        Args:
            tool_name: Name of the create tool
            tool_args: Arguments passed to the tool
        """
        file_path = self._extract_file_path(tool_args)
        if file_path:
            resolved_path = self._resolve_path_against_workspace(file_path)
            self.file_operation_tracker.mark_as_created(Path(resolved_path))

    def _validate_delete_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate delete tool operations using read-before-delete policy.

        Args:
            tool_name: Name of the delete tool
            tool_args: Arguments passed to the tool

        Returns:
            Tuple of (allowed: bool, reason: Optional[str])
        """
        # First check normal write permissions
        permission_result = self._validate_write_tool(tool_name, tool_args)
        if not permission_result[0]:
            return permission_result

        # Special handling for batch delete operations
        if tool_name == "delete_files_batch":
            return self._validate_delete_files_batch(tool_args)

        # Extract file path
        file_path = self._extract_file_path(tool_args)
        if not file_path:
            # Can't determine path - allow (will fail elsewhere if invalid)
            return (True, None)

        # Resolve path
        resolved_path = self._resolve_path_against_workspace(file_path)
        path = Path(resolved_path)

        # Check if it's a directory or file
        if path.is_dir():
            # Check directory deletion
            can_delete, reason = self.file_operation_tracker.can_delete_directory(path)
            if not can_delete:
                return (False, reason)
        else:
            # Check file deletion
            can_delete, reason = self.file_operation_tracker.can_delete(path)
            if not can_delete:
                return (False, reason)

        return (True, None)

    def _validate_delete_files_batch(self, tool_args: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate batch delete operations by checking all files that would be deleted.

        Args:
            tool_args: Arguments for delete_files_batch

        Returns:
            Tuple of (allowed: bool, reason: Optional[str])
        """
        try:
            base_path = tool_args.get("base_path")
            include_patterns = tool_args.get("include_patterns") or ["*"]
            exclude_patterns = tool_args.get("exclude_patterns") or []

            if not base_path:
                return (False, "delete_files_batch requires base_path")

            # Resolve base path
            resolved_base = self._resolve_path_against_workspace(base_path)
            base = Path(resolved_base)

            if not base.exists():
                # Path doesn't exist - will fail in actual tool, allow validation to pass
                return (True, None)

            # Collect files that would be deleted
            unread_files = []
            for item in base.rglob("*"):
                if not item.is_file():
                    continue

                # Get relative path from base
                rel_path = item.relative_to(base)
                rel_path_str = str(rel_path)

                # Check include patterns
                included = any(fnmatch.fnmatch(rel_path_str, pattern) for pattern in include_patterns)
                if not included:
                    continue

                # Check exclude patterns
                excluded = any(fnmatch.fnmatch(rel_path_str, pattern) for pattern in exclude_patterns)
                if excluded:
                    continue

                # Check if file was read
                if not self.file_operation_tracker.was_read(item):
                    unread_files.append(rel_path_str)

            if unread_files:
                # Limit to first 3 unread files for readable error message
                example_files = unread_files[:3]
                suffix = f" (and {len(unread_files) - 3} more)" if len(unread_files) > 3 else ""
                reason = (
                    f"Cannot delete {len(unread_files)} unread file(s). " f"Examples: {', '.join(example_files)}{suffix}. " f"Please read files before deletion using Read or read_multimodal_files."
                )
                logger.info(f"[PathPermissionManager] Blocking batch delete: {reason}")
                return (False, reason)

            return (True, None)

        except Exception as e:
            logger.error(f"[PathPermissionManager] Error validating batch delete: {e}")
            return (False, f"Batch delete validation failed: {e}")

    def _is_path_within_allowed_directories(self, path: Path) -> bool:
        """
        Check if a path is within any allowed directory (workspace or context paths).

        This enforces directory boundaries - paths outside managed directories are not allowed.

        Args:
            path: Path to check

        Returns:
            True if path is within allowed directories, False otherwise
        """
        resolved_path = path.resolve()

        # Check if path is within any managed path (excluding file_context_parent)
        for managed_path in self.managed_paths:
            # file_context_parent paths don't grant access, only their specific files do
            if managed_path.path_type == "file_context_parent":
                continue

            if managed_path.contains(resolved_path) or managed_path.path == resolved_path:
                return True

        return False

    def _validate_file_context_access(self, tool_name: str, tool_args: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate access for all file operations - enforces directory boundaries and permissions.

        This method ensures that:
        1. ALL file operations are restricted to workspace + context paths (directory boundary)
        2. Read/write permissions are enforced within allowed directories
        3. Sibling file access is prevented for file-specific context paths

        Args:
            tool_name: Name of the tool being called
            tool_args: Arguments passed to the tool

        Returns:
            Tuple of (allowed: bool, reason: Optional[str])
        """
        # Extract file path from arguments
        file_path = self._extract_file_path(tool_args)
        if not file_path:
            # Can't determine path - allow it (tool may not access files, or uses different args)
            return (True, None)

        # Resolve relative paths against workspace
        file_path = self._resolve_path_against_workspace(file_path)
        path = Path(file_path).resolve()

        # SECURITY: Check directory boundary - path must be within allowed directories
        if not self._is_path_within_allowed_directories(path):
            logger.warning(f"[PathPermissionManager] BLOCKED: '{tool_name}' attempted to access path outside allowed directories: {path}")
            return (False, f"Access denied: '{path}' is outside allowed directories. Only workspace and context paths are accessible.")

        permission = self.get_permission(path)
        logger.debug(f"[PathPermissionManager] Validating '{tool_name}' on path: {path} with permission: {permission}")

        # If permission is None but we're within allowed directories, check for file_context_parent edge case
        if permission is None:
            parent_paths = [mp for mp in self.managed_paths if mp.path_type == "file_context_parent"]
            for parent_mp in parent_paths:
                if parent_mp.contains(path):
                    # Path is in a file context parent dir, but not the specific file
                    return (False, f"Access denied: '{path}' is not an explicitly allowed file in this directory")
            # Within allowed directories and has no specific restrictions - allow
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

        # Handle tilde expansion (home directory)
        if path_str.startswith("~"):
            path = Path(path_str).expanduser()
            return str(path)

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

        For Claude Code: Validates directory boundaries for all paths in Bash commands.
        This prevents access to paths outside workspace + context paths.

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

        # Block command injection techniques that can bypass path validation
        # Environment variables: $HOME, $TMPDIR, ${VAR}, etc.
        if "$" in command:
            # Allow common safe variables like $?, $#, $$, $0-$9
            # Block everything else including $HOME, $USER, $(command), ${var}
            safe_vars = ["$?", "$#", "$$"]
            has_unsafe_var = False
            if "$(" in command or "${" in command:
                has_unsafe_var = True
            elif any(c in command for c in ["$HOME", "$USER", "$TMPDIR", "$PWD", "$OLDPWD", "$PATH"]):
                has_unsafe_var = True
            else:
                # Check for $VAR pattern (dollar followed by letters)
                import re

                if re.search(r"\$[A-Za-z_][A-Za-z0-9_]*", command):
                    # Allow only the safe ones
                    for safe in safe_vars:
                        command = command.replace(safe, "")
                    if re.search(r"\$[A-Za-z_][A-Za-z0-9_]*", command):
                        has_unsafe_var = True

            if has_unsafe_var:
                return (False, "Environment variables in Bash commands are not allowed (security risk: can reference paths outside workspace)")

        # Block command substitution (can execute arbitrary commands and use output as paths)
        if "`" in command:
            return (False, "Backtick command substitution is not allowed (security risk)")

        # Block process substitution (can access arbitrary paths)
        if "<(" in command or ">(" in command:
            return (False, "Process substitution is not allowed (security risk)")

        # CLAUDE CODE SPECIFIC: Extract and validate all paths (absolute and relative) in the command
        # This prevents Bash commands from accessing paths outside allowed directories (e.g., ../../)
        paths = self._extract_paths_from_command(command)
        for path_str in paths:
            try:
                # Resolve relative paths against workspace
                resolved_path_str = self._resolve_path_against_workspace(path_str)
                path = Path(resolved_path_str).resolve()

                # Check if this path is within allowed directories
                if not self._is_path_within_allowed_directories(path):
                    logger.warning(f"[PathPermissionManager] BLOCKED Bash command accessing path outside allowed directories: {path} (from: {path_str})")
                    return (False, f"Access denied: Bash command references '{path_str}' which resolves to '{path}' outside allowed directories")
            except Exception as e:
                logger.debug(f"[PathPermissionManager] Could not validate path '{path_str}' in Bash command: {e}")
                # If we can't parse it, allow it - might not be a real path
                continue

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

    def _extract_paths_from_command(self, command: str) -> List[str]:
        """
        Extract all potential file/directory paths from a Bash command for validation.

        This is Claude Code specific - extracts paths to validate directory boundaries.
        Looks for both absolute paths (starting with /) and relative paths (including ../).

        Args:
            command: Bash command string

        Returns:
            List of path strings found in the command
        """
        import shlex

        paths = []

        try:
            # Split command into tokens, handling quoted strings properly
            tokens = shlex.split(command)
        except ValueError:
            # If shlex fails (malformed quotes), fall back to simple split
            tokens = command.split()

        for token in tokens:
            # Strip common decorations
            cleaned = token.strip("\"'").strip()

            # Skip obvious non-paths (flags, empty strings, etc.)
            if not cleaned:
                continue
            if cleaned.startswith("-"):  # Flags like -la, --help
                continue
            if cleaned in ["&&", "||", "|", ";", ">"]:  # Operators
                continue

            # Check if it looks like a path:
            # 1. Absolute paths (starts with /)
            # 2. Home directory paths (starts with ~ - including single char ~)
            # 3. Relative parent paths (starts with ../ or is ..)
            # 4. Relative current paths (starts with ./)
            if cleaned.startswith("/") or cleaned.startswith("~") or cleaned.startswith("../") or cleaned == ".." or cleaned.startswith("./"):
                # Handle wildcards - extract base directory before wildcard
                if "*" in cleaned or "?" in cleaned or "[" in cleaned:
                    # Split on wildcard and take the directory part
                    base = cleaned.split("*")[0].split("?")[0].split("[")[0]
                    # If base ends with /, remove it
                    if base.endswith("/"):
                        base = base[:-1]
                    # Validate the base directory instead
                    if base:
                        paths.append(base)
                else:
                    paths.append(cleaned)

        return paths

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
        Get Claude Agent SDK hooks configuration.

        Returns:
            Hooks configuration dict for ClaudeAgentOptions
        """
        if not self.managed_paths:
            return {}

        # Import here to avoid dependency issues if SDK not available
        try:
            from claude_agent_sdk import HookMatcher
        except ImportError:
            logger.warning("[PathPermissionManager] claude_agent_sdk not available, hooks disabled")
            return {}

        return {
            "PreToolUse": [
                # Apply directory boundary + permission validation to ALL file-access tools
                # This ensures Claude cannot access files outside workspace + context paths
                HookMatcher(matcher="Read", hooks=[self.validate_context_access]),
                HookMatcher(matcher="Write", hooks=[self.validate_context_access]),
                HookMatcher(matcher="Edit", hooks=[self.validate_context_access]),
                HookMatcher(matcher="MultiEdit", hooks=[self.validate_context_access]),
                HookMatcher(matcher="NotebookEdit", hooks=[self.validate_context_access]),
                HookMatcher(matcher="Grep", hooks=[self.validate_context_access]),
                HookMatcher(matcher="Glob", hooks=[self.validate_context_access]),
                HookMatcher(matcher="LS", hooks=[self.validate_context_access]),
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
