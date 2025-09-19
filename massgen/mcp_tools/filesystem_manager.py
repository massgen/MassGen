"""
Filesystem Manager for MassGen - Handles workspace and snapshot management.

This manager provides centralized filesystem operations for backends that support
filesystem access through MCP. It manages:
- Workspace directory creation and cleanup
- Permission management for various path types
- Snapshot storage for context sharing
- Temporary workspace restoration
- Additional context paths
- Path configuration for MCP filesystem server

The manager is backend-agnostic and works with any backend that has filesystem
MCP tools configured.
"""

import os
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List, Any, Tuple
from enum import Enum
from dataclasses import dataclass
from ..logger_config import logger, get_log_session_dir

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

class PathPermissionManager:
    """
    Manages all filesystem paths and implements PreToolUse hook functionality similar to Claude Code, allowing us to intercept and validate tool calls based on some predefined rules (here, permissions).

    This manager handles all types of paths with unified permission control:
    - Workspace paths (typically write)
    - Temporary workspace paths (typically read-only)
    - Context paths (user-specified permissions)
    - Tool call validation (PreToolUse hook)
    - Path access control
    """

    def __init__(self, context_write_access_enabled: bool = False):
        """
        Initialize path permission manager.

        Args:
            context_write_access_enabled: Whether write access is enabled for context paths (workspace paths always have write access). If False, we change all context paths to read-only. Can be later updated with set_context_write_access_enabled(), in which case all existing context paths will be updated accordingly so that those that were "write" in YAML become writable again.
        """
        self.managed_paths: List[ManagedPath] = []
        self.context_write_access_enabled = context_write_access_enabled

        # Cache for quick permission lookups
        self._permission_cache: Dict[Path, Permission] = {}

        logger.info(
            f"[PathPermissionManager] Initialized with context_write_access_enabled={context_write_access_enabled}"
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
            if mp.path_type == "context" and mp.original_permission:
                # Update permission based on new context_write_access_enabled setting
                if enabled:
                    mp.permission = mp.original_permission
                    logger.debug(f"[PathPermissionManager] Restored original permission for {mp.path}: {mp.permission.value}")
                else:
                    mp.permission = Permission.READ
                    logger.debug(f"[PathPermissionManager] Forced read-only for {mp.path}")

        logger.info(f"[PathPermissionManager] Updated context path permissions based on context_write_access_enabled={enabled}, now is {self.managed_paths=}")

        # Clear permission cache to force recalculation
        self._permission_cache.clear()

    def add_context_paths(self, context_paths: List[Dict[str, Any]]) -> None:
        """
        Add context paths from configuration.

        Args:
            context_paths: List of context path configurations
                Format: [{"path": "C:/project/src", "permission": "write"}, ...]

        Note: During coordination, all context paths are read-only regardless of YAML settings.
              Only the final agent with context_write_access_enabled=True can write to paths marked as "write".
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

            # For context paths: only final agent (context_write_access_enabled=True) gets original permissions
            # All coordination agents get read-only access regardless of YAML
            if self.context_write_access_enabled:
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
            logger.debug(f"[PathPermissionManager] Permission cache hit for {resolved_path}: {self._permission_cache[resolved_path].value}")
            return self._permission_cache[resolved_path]

        # Find containing managed path
        for managed_path in self.managed_paths:
            if managed_path.contains(resolved_path) or managed_path.path == resolved_path:
                logger.info(f"[PathPermissionManager] Found permission for {resolved_path}: {managed_path.permission.value} (from {managed_path.path}, type: {managed_path.path_type}, original: {managed_path.original_permission})")
                self._permission_cache[resolved_path] = managed_path.permission
                return managed_path.permission

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
            r".*[Cc]opy.*",       # copy_file, copy_files_batch, etc.
        ]

        for pattern in write_patterns:
            if re.match(pattern, tool_name):
                return True

        return False

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

        path = Path(file_path).resolve()
        permission = self.get_permission(path)
        logger.debug(f"[PathPermissionManager] Validating write tool '{tool_name}' for path: {path} with permission: {permission}")

        # No permission means not in context paths (workspace paths are always allowed)
        # We note that the filesystem MCP server will block access to paths not in its config, and we explicitly mark as read-only any paths that need to be read-only, so all else is fine.
        if permission is None:
            return (True, None)

        # Check write permission (permission is already set correctly based on context_write_access_enabled)
        if permission == Permission.WRITE:
            return (True, None)
        else:
            return (False, f"No write permission for '{path}' (read-only context path)")

    def _validate_copy_files_batch(self, tool_args: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Validate copy_files_batch by checking all destination paths after globbing."""
        try:
            logger.debug(f"[PathPermissionManager] copy_files_batch validation - context_write_access_enabled: {self.context_write_access_enabled}")
            # Import the helper function from workspace copy server
            from .workspace_copy_server import get_copy_file_pairs

            # Get all the file pairs that would be copied
            source_base_path = tool_args.get("source_base_path")
            destination_base_path = tool_args.get("destination_base_path", "")
            include_patterns = tool_args.get("include_patterns")
            exclude_patterns = tool_args.get("exclude_patterns")

            if not source_base_path:
                return (False, "copy_files_batch requires source_base_path")

            # Get all file pairs (this also validates path restrictions)
            file_pairs = get_copy_file_pairs(
                source_base_path, destination_base_path, include_patterns, exclude_patterns
            )

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
            "rm ", "rm -", "rmdir", "del ",
            "sudo ", "su ", "chmod ", "chown ",
            "format ", "fdisk", "mkfs",
        ]

        # File modification patterns to check when write access disabled
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
        # - Workspace copy: source_base_path, destination_base_path
        path_keys = ["file_path", "path", "filename", "file", "notebook_path", "target", "source", "destination", "source_base_path", "destination_base_path"]

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

        # For simple commands like touch, mkdir, echo (first argument after command)
        if pattern in ["touch ", "mkdir ", "echo "]:
            parts = command.split()
            try:
                idx = parts.index(pattern.strip())
                if idx + 1 < len(parts):
                    # The first argument is the target
                    return parts[idx + 1].strip('"\'')
            except (ValueError, IndexError):
                pass

        return None

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
        logger.info(f"[PathPermissionManager] PreToolUse hook called for tool_use_id={tool_use_id}, input_data={input_data}")

        tool_name = input_data.get('tool_name', '')
        tool_input = input_data.get('tool_input', {})

        # Use our existing validation logic
        allowed, reason = await self.pre_tool_use_hook(tool_name, tool_input)

        if not allowed:
            logger.warning(f"[PathPermissionManager] Blocked {tool_name}: {reason}")
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
        if not self.managed_paths:
            return {}

        # Import here to avoid dependency issues if SDK not available
        try:
            from claude_code_sdk import HookMatcher
        except ImportError:
            logger.warning("[PathPermissionManager] claude_code_sdk not available, hooks disabled")
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

class FilesystemManager:
    """
    Manages filesystem operations for backends with MCP filesystem support.

    This class handles:
    - Workspace directory lifecycle (creation, cleanup)
    - Snapshot storage and restoration for context sharing
    - Path management for MCP filesystem server configuration
    """

    def __init__(
        self,
        cwd: str,
        agent_temporary_workspace_parent: str = None,
        context_paths: List[Dict[str, Any]] = None,
        context_write_access_enabled: bool = False,
    ):
        """
        Initialize FilesystemManager.

        Args:
            cwd: Working directory path for the agent
            agent_temporary_workspace_parent: Parent directory for temporary workspaces
            context_paths: List of context path configurations for access control
            context_write_access_enabled: Whether write access is enabled for context paths
        """
        self.agent_id = (
            None  # Will be set by orchestrator via setup_orchestration_paths
        )

        # Initialize path permission manager
        self.path_permission_manager = PathPermissionManager(
            context_write_access_enabled=context_write_access_enabled
        )

        # Add context paths if provided
        if context_paths:
            self.path_permission_manager.add_context_paths(context_paths)

        # Set agent_temporary_workspace_parent first, before calling _setup_workspace
        self.agent_temporary_workspace_parent = agent_temporary_workspace_parent

        # Get absolute path for temporary workspace parent if provided
        if self.agent_temporary_workspace_parent:
            # Add parent directory prefix for temp workspaces if not already present
            temp_parent = self.agent_temporary_workspace_parent

            temp_parent_path = Path(temp_parent)
            if not temp_parent_path.is_absolute():
                temp_parent_path = temp_parent_path.resolve()
            self.agent_temporary_workspace_parent = temp_parent_path

        # Setup main working directory (now that agent_temporary_workspace_parent is set)
        self.cwd = self._setup_workspace(cwd)

        # Add workspace to path manager (workspace is typically writable)
        self.path_permission_manager.add_path(
            self.cwd, Permission.WRITE, "workspace"
        )
        # Add temporary workspace to path manager (read-only)
        self.path_permission_manager.add_path(
            self.agent_temporary_workspace_parent, Permission.READ, "temp_workspace"
        )

        # Orchestration-specific paths (set by setup_orchestration_paths)
        self.snapshot_storage = None  # Path for storing workspace snapshots
        self.agent_temporary_workspace = (
            None  # Full path for this specific agent's temporary workspace
        )

        # Track whether we're using a temporary workspace
        self._using_temporary = False
        self._original_cwd = self.cwd

    def setup_orchestration_paths(
        self,
        agent_id: str,
        snapshot_storage: Optional[str] = None,
        agent_temporary_workspace: Optional[str] = None,
    ) -> None:
        """
        Setup orchestration-specific paths for snapshots and temporary workspace.
        Called by orchestrator to configure paths for this specific orchestration.

        Args:
            agent_id: The agent identifier for this orchestration
            snapshot_storage: Base path for storing workspace snapshots
            agent_temporary_workspace: Base path for temporary workspace during context sharing
        """
        logger.info(
            f"[FilesystemManager.setup_orchestration_paths] Called for agent_id={agent_id}, snapshot_storage={snapshot_storage}, agent_temporary_workspace={agent_temporary_workspace}"
        )
        self.agent_id = agent_id

        # Setup snapshot storage if provided
        if snapshot_storage and self.agent_id:
            self.snapshot_storage = Path(snapshot_storage) / self.agent_id
            self.snapshot_storage.mkdir(parents=True, exist_ok=True)

        # Setup temporary workspace for context sharing
        if agent_temporary_workspace and self.agent_id:
            self.agent_temporary_workspace = self._setup_workspace(
                self.agent_temporary_workspace_parent / self.agent_id
            )

        # Also setup log directories if we have an agent_id
        if self.agent_id:
            log_session_dir = get_log_session_dir()
            if log_session_dir:
                agent_log_dir = log_session_dir / self.agent_id
                agent_log_dir.mkdir(parents=True, exist_ok=True)

    def _setup_workspace(self, cwd: str) -> Path:
        """Setup workspace directory, creating if needed and clearing existing files safely."""
        # Add parent directory prefix if not already present
        cwd_path = Path(cwd)
        workspace = Path(cwd).resolve()

        # Safety checks
        if not workspace.is_absolute():
            raise AssertionError("Workspace must be absolute")
        if workspace == Path("/") or len(workspace.parts) < 3:
            raise AssertionError(f"Refusing unsafe workspace path: {workspace}")

        # Create if needed
        workspace.mkdir(parents=True, exist_ok=True)

        # Clear existing contents
        if workspace.exists() and workspace.is_dir():
            for item in workspace.iterdir():
                if item.is_symlink():
                    logger.warning(
                        f"[FilesystemManager.save_snapshot] Skipping symlink during clear: {item}"
                    )
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)

        return workspace

    def get_mcp_filesystem_config(self) -> Dict[str, Any]:
        """
        Generate MCP filesystem server configuration.

        Returns:
            Dictionary with MCP server configuration for filesystem access
        """
        # Build MCP server configuration with all managed paths
        config = {
            "name": "filesystem",
            "type": "stdio",
            "command": "npx",
            "args": [
                "-y",
                "@modelcontextprotocol/server-filesystem",
            ],
        }

        # Add all managed paths from path permission manager
        config["args"].extend(self.path_permission_manager.get_mcp_filesystem_paths())

        return config

    def get_workspace_copy_mcp_config(self) -> Dict[str, Any]:
        """
        Generate workspace copy MCP server configuration.

        Returns:
            Dictionary with MCP server configuration for workspace copying
        """
        # Get context paths using the existing method
        context_paths = self.path_permission_manager.get_context_paths()
        context_paths_str = ",".join([cp["path"] for cp in context_paths])

        config = {
            "name": "workspace_copy",
            "type": "stdio",
            "command": "python",
            "args": ["-m", "massgen.mcp_tools.workspace_copy_server"],
            # "command": "fastmcp",
            # "args": ["run", "massgen/mcp_tools/workspace_copy_server.py"],
            # "env": {
            #     # "FASTMCP_SHOW_CLI_BANNER": "false",
            # }
        }

        # Add all managed paths from path permission manager
        config["args"].extend(self.path_permission_manager.get_mcp_filesystem_paths())

        return config

    def inject_filesystem_mcp(self, backend_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Inject filesystem and workspace copy MCP servers into backend configuration.

        Args:
            backend_config: Original backend configuration

        Returns:
            Modified configuration with MCP servers added
        """
        # Get existing mcp_servers configuration
        mcp_servers = backend_config.get("mcp_servers", [])
        existing_names = [server.get("name") for server in mcp_servers]

        try:
            # Add filesystem server if missing
            if "filesystem" not in existing_names:
                mcp_servers.append(self.get_mcp_filesystem_config())
            else:
                logger.warning(
                    "[FilesystemManager.inject_filesystem_mcp] Custom filesystem MCP server already present"
                )

            # Add workspace copy server if missing
            if "workspace_copy" not in existing_names:
                mcp_servers.append(self.get_workspace_copy_mcp_config())
            else:
                logger.warning(
                    "[FilesystemManager.inject_filesystem_mcp] Custom workspace_copy MCP server already present"
                )

        except Exception as e:
            logger.warning(
                f"[FilesystemManager.inject_filesystem_mcp] Error checking existing MCP servers: {e}"
            )

        # Update backend config
        backend_config["mcp_servers"] = mcp_servers

        return backend_config

    def get_pre_tool_hooks(self) -> Dict[str, List]:
        """
        Get pre-tool hooks configuration for MCP clients.

        Returns:
            Dict mapping hook types to lists of hook functions
        """
        from .client import HookType

        async def mcp_hook_wrapper(tool_name: str, tool_args: Dict[str, Any]) -> bool:
            """Wrapper to adapt our hook signature to MCP client expectations."""
            allowed, reason = await self.path_permission_manager.pre_tool_use_hook(tool_name, tool_args)
            if not allowed and reason:
                logger.warning(f"[FilesystemManager] Tool blocked: {tool_name} - {reason}")
            return allowed

        return {HookType.PRE_TOOL_USE: [mcp_hook_wrapper]}

    def get_claude_code_hooks_config(self) -> Dict[str, Any]:
        """
        Get Claude Code SDK hooks configuration.

        Returns:
            Hooks configuration dict for ClaudeCodeOptions
        """
        return self.path_permission_manager.get_claude_code_hooks_config()

    def enable_write_access(self) -> None:
        """
        Enable write access for this filesystem manager.

        This should be called for final agents to allow them to modify
        files with write permissions in their context paths.
        """
        self.path_permission_manager.context_write_access_enabled = True
        logger.info("[FilesystemManager] Context write access enabled - agent can now modify files with write permissions")

    async def save_snapshot(
        self, timestamp: Optional[str] = None, is_final: bool = False
    ) -> None:
        """
        Save a snapshot of the workspace. Always saves to snapshot_storage if available (keeping only most recent).
        Additionally saves to log directories if logging is enabled.
        Then, clear the workspace so it is ready for next execution.

        Args:
            timestamp: Optional timestamp to use for the snapshot directory (if not provided, generates one)
            is_final: If True, save as final snapshot for presentation

        TODO: reimplement without 'shutil' and 'os' operations for true async, though we may not need to worry about race conditions here since only one agent writes at a time
        """
        logger.info(
            f"[FilesystemManager.save_snapshot] Called for agent_id={self.agent_id}, is_final={is_final}, snapshot_storage={self.snapshot_storage}"
        )

        # Use current workspace as source
        source_dir = self.cwd
        source_path = Path(source_dir)

        if not source_path.exists() or not source_path.is_dir():
            logger.warning(
                f"[FilesystemManager] Source path invalid - exists: {source_path.exists()}, "
                f"is_dir: {source_path.is_dir() if source_path.exists() else False}"
            )
            return

        if not any(source_path.iterdir()):
            logger.warning(
                f"[FilesystemManager.save_snapshot] Source path {source_path} is empty, skipping snapshot"
            )
            return

        try:
            # --- 1. Save to snapshot_storage ---
            if self.snapshot_storage:
                if self.snapshot_storage.exists():
                    shutil.rmtree(self.snapshot_storage)
                self.snapshot_storage.mkdir(parents=True, exist_ok=True)

                items_copied = 0
                for item in source_path.iterdir():
                    if item.is_symlink():
                        logger.warning(
                            f"[FilesystemManager.save_snapshot] Skipping symlink: {item}"
                        )
                        continue
                    if item.is_file():
                        shutil.copy2(item, self.snapshot_storage / item.name)
                    elif item.is_dir():
                        shutil.copytree(item, self.snapshot_storage / item.name)
                    items_copied += 1

                logger.info(
                    f"[FilesystemManager] Saved snapshot with {items_copied} items to {self.snapshot_storage}"
                )

            # --- 2. Save to log directories ---
            log_session_dir = get_log_session_dir()
            if log_session_dir and self.agent_id:
                if is_final:
                    dest_dir = log_session_dir / "final" / self.agent_id / "workspace"
                    if dest_dir.exists():
                        shutil.rmtree(dest_dir)
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    logger.info(
                        f"[FilesystemManager.save_snapshot] Final log snapshot dest_dir: {dest_dir}"
                    )
                else:
                    if not timestamp:
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                    dest_dir = log_session_dir / self.agent_id / timestamp / "workspace"
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    logger.info(
                        f"[FilesystemManager.save_snapshot] Regular log snapshot dest_dir: {dest_dir}"
                    )

                items_copied = 0
                for item in source_path.iterdir():
                    if item.is_symlink():
                        logger.warning(
                            f"[FilesystemManager.save_snapshot] Skipping symlink: {item}"
                        )
                        continue
                    if item.is_file():
                        shutil.copy2(item, dest_dir / item.name)
                    elif item.is_dir():
                        shutil.copytree(item, dest_dir / item.name, dirs_exist_ok=True)
                    items_copied += 1

                logger.info(
                    f"[FilesystemManager] Saved {'final' if is_final else 'regular'} "
                    f"log snapshot with {items_copied} items to {dest_dir}"
                )

        except Exception as e:
            logger.exception(f"[FilesystemManager.save_snapshot] Snapshot failed: {e}")
            # On failure, DO NOT clear the workspace and exit
            return

        # --- 3. (TODO in future): Give option to clear the workspace, if snapshot succeeded ---
        # for item in source_path.iterdir():
        #     if item.is_symlink():
        #         logger.warning(f"[FilesystemManager.save_snapshot] Skipping symlink: {item}")
        #         continue
        #     if item.is_file():
        #         item.unlink()
        #     elif item.is_dir():
        #         shutil.rmtree(item)

        logger.info(f"[FilesystemManager] Cleared workspace after snapshot")

    async def copy_snapshots_to_temp_workspace(
        self, all_snapshots: Dict[str, Path], agent_mapping: Dict[str, str]
    ) -> Optional[Path]:
        """
        Copy snapshots from multiple agents to temporary workspace for context sharing.

        This method is called by the orchestrator before starting an agent that needs context from others.
        It copies the latest snapshots from log directories to a temporary workspace.

        Args:
            all_snapshots: Dictionary mapping agent_id to snapshot path (from log directories)
            agent_mapping: Dictionary mapping real agent_id to anonymous agent_id

        Returns:
            Path to the temporary workspace with restored snapshots

        TODO: reimplement without 'shutil' and 'os' operations for true async
        """
        if not self.agent_temporary_workspace:
            return None

        # Clear existing temporary workspace
        if self.agent_temporary_workspace.exists():
            shutil.rmtree(self.agent_temporary_workspace)
        self.agent_temporary_workspace.mkdir(parents=True, exist_ok=True)

        # Copy all snapshots using anonymous IDs
        for agent_id, snapshot_path in all_snapshots.items():
            if snapshot_path.exists() and snapshot_path.is_dir():
                # Use anonymous ID for destination directory
                anon_id = agent_mapping.get(agent_id, agent_id)
                dest_dir = self.agent_temporary_workspace / anon_id

                # Copy snapshot content if not empty
                if any(snapshot_path.iterdir()):
                    shutil.copytree(snapshot_path, dest_dir, dirs_exist_ok=True)

        return self.agent_temporary_workspace

    def _log_workspace_contents(
        self, workspace_path: Path, workspace_name: str, context: str = ""
    ) -> None:
        """
        Log the contents of a workspace directory for visibility.

        Args:
            workspace_path: Path to the workspace to log
            workspace_name: Human-readable name for the workspace
            context: Additional context (e.g., "before execution", "after execution")
        """
        if not workspace_path or not workspace_path.exists():
            logger.info(
                f"[FilesystemManager.{workspace_name}] {context} - Workspace does not exist: {workspace_path}"
            )
            return

        try:
            files = list(workspace_path.rglob("*"))
            file_paths = [
                str(f.relative_to(workspace_path)) for f in files if f.is_file()
            ]
            dir_paths = [
                str(f.relative_to(workspace_path)) for f in files if f.is_dir()
            ]

            logger.info(
                f"[FilesystemManager.{workspace_name}] {context} - Workspace: {workspace_path}"
            )
            if file_paths:
                logger.info(
                    f"[FilesystemManager.{workspace_name}] {context} - Files ({len(file_paths)}): {file_paths}"
                )
            if dir_paths:
                logger.info(
                    f"[FilesystemManager.{workspace_name}] {context} - Directories ({len(dir_paths)}): {dir_paths}"
                )
            if not file_paths and not dir_paths:
                logger.info(
                    f"[FilesystemManager.{workspace_name}] {context} - Empty workspace"
                )
        except Exception as e:
            logger.warning(
                f"[FilesystemManager.{workspace_name}] {context} - Error reading workspace: {e}"
            )

    def log_current_state(self, context: str = "") -> None:
        """
        Log the current state of both main and temp workspaces.

        Args:
            context: Context for the logging (e.g., "before execution", "after answer")
        """
        agent_context = (
            f"agent_id={self.agent_id}, {context}"
            if context
            else f"agent_id={self.agent_id}"
        )

        # Log main workspace
        self._log_workspace_contents(
            self.get_current_workspace(), "main_workspace", agent_context
        )

        # Log temp workspace if it exists
        if self.agent_temporary_workspace:
            self._log_workspace_contents(
                self.agent_temporary_workspace, "temp_workspace", agent_context
            )

    def set_temporary_workspace(self, use_temporary: bool = True) -> None:
        """
        Switch between main workspace and temporary workspace.

        Args:
            use_temporary: If True, use temporary workspace; if False, use main workspace
        """
        self._using_temporary = use_temporary

        # Update current working directory path
        if use_temporary and self.agent_temporary_workspace:
            self.cwd = self.agent_temporary_workspace
        else:
            self.cwd = self._original_cwd

    def get_current_workspace(self) -> Path:
        """
        Get the current active workspace path.

        Returns:
            Path to the current workspace
        """
        return self.cwd

    def cleanup(self) -> None:
        """Cleanup temporary resources (not the main workspace)."""

        p = self.agent_temporary_workspace

        # Aggressive path-checking for validity
        if not p:
            return
        try:
            p = p.resolve()
            if not p.exists():
                return
            assert p.is_absolute(), "Temporary workspace must be absolute"
            assert p.is_dir(), "Temporary workspace must be a directory"

            if self.agent_temporary_workspace_parent:
                parent = Path(self.agent_temporary_workspace_parent).resolve()
                try:
                    p.relative_to(parent)
                except ValueError:
                    raise AssertionError(
                        f"Refusing to delete workspace outside of parent: {p}"
                    )

            if p == Path("/") or len(p.parts) < 3:
                raise AssertionError(f"Unsafe path for deletion: {p}")

            shutil.rmtree(p)
        except Exception as e:
            logger.warning(f"[FilesystemManager] cleanup failed for {p}: {e}")


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
            from .hooks import HookResult

            # Parse arguments from JSON string
            import json
            try:
                tool_args = json.loads(arguments) if arguments else {}
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"[PathPermissionManagerHook] Invalid JSON arguments for {function_name}: {e}")
                tool_args = {}

            # Call the existing pre_tool_use_hook method
            allowed, reason = await self.path_permission_manager.pre_tool_use_hook(
                function_name, tool_args
            )

            if not allowed:
                logger.info(f"[PathPermissionManagerHook] Blocked {function_name}: {reason}")

            return HookResult(
                allowed=allowed,
                metadata={"reason": reason} if reason else {}
            )

        except Exception as e:
            logger.error(f"[PathPermissionManagerHook] Error checking permissions for {function_name}: {e}")
            # Fail closed - deny access on permission check errors
            return HookResult(
                allowed=False,
                metadata={"error": str(e), "reason": "Permission check failed"}
            )
