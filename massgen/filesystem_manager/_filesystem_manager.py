# -*- coding: utf-8 -*-
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

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..logger_config import get_log_session_dir, logger
from ..mcp_tools.client import HookType
from . import _workspace_tools_server as wc_module
from ._base import Permission
from ._path_permission_manager import PathPermissionManager


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
        self.agent_id = None  # Will be set by orchestrator via setup_orchestration_paths

        # Initialize path permission manager
        self.path_permission_manager = PathPermissionManager(context_write_access_enabled=context_write_access_enabled)

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
            # Clear existing temp workspace parent if it exists, else we would only clear those with the exact agent_ids in the config.
            self.clear_temp_workspace()

        # Setup main working directory (now that agent_temporary_workspace_parent is set)
        self.cwd = self._setup_workspace(cwd)

        # Add workspace to path manager (workspace is typically writable)
        self.path_permission_manager.add_path(self.cwd, Permission.WRITE, "workspace")
        # Add temporary workspace to path manager (read-only)
        self.path_permission_manager.add_path(self.agent_temporary_workspace_parent, Permission.READ, "temp_workspace")

        # Orchestration-specific paths (set by setup_orchestration_paths)
        self.snapshot_storage = None  # Path for storing workspace snapshots
        self.agent_temporary_workspace = None  # Full path for this specific agent's temporary workspace

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
        logger.info(f"[FilesystemManager.setup_orchestration_paths] Called for agent_id={agent_id}, snapshot_storage={snapshot_storage}, agent_temporary_workspace={agent_temporary_workspace}")
        self.agent_id = agent_id

        # Setup snapshot storage if provided
        if snapshot_storage and self.agent_id:
            self.snapshot_storage = Path(snapshot_storage) / self.agent_id
            self.snapshot_storage.mkdir(parents=True, exist_ok=True)

        # Setup temporary workspace for context sharing
        if agent_temporary_workspace and self.agent_id:
            self.agent_temporary_workspace = self._setup_workspace(self.agent_temporary_workspace_parent / self.agent_id)

        # Also setup log directories if we have an agent_id
        if self.agent_id:
            log_session_dir = get_log_session_dir()
            if log_session_dir:
                agent_log_dir = log_session_dir / self.agent_id
                agent_log_dir.mkdir(parents=True, exist_ok=True)

    def _setup_workspace(self, cwd: str) -> Path:
        """Setup workspace directory, creating if needed and clearing existing files safely."""
        # Add parent directory prefix if not already present
        Path(cwd)
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
                    logger.warning(f"[FilesystemManager.save_snapshot] Skipping symlink during clear: {item}")
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
            "cwd": str(self.cwd),  # Set working directory for filesystem server (important for relative paths)
        }

        # Add all managed paths from path permission manager
        config["args"].extend(self.path_permission_manager.get_mcp_filesystem_paths())

        return config

    def get_workspace_tools_mcp_config(self) -> Dict[str, Any]:
        """
        Generate workspace tools MCP server configuration.

        Returns:
            Dictionary with MCP server configuration for workspace tools (copy, delete, compare)
        """
        # Get context paths using the existing method
        context_paths = self.path_permission_manager.get_context_paths()
        ",".join([cp["path"] for cp in context_paths])

        # Get absolute path to the workspace tools server script
        script_path = Path(wc_module.__file__).resolve()

        # Pass allowed paths via environment variable to avoid fastmcp argument parsing issues
        paths = self.path_permission_manager.get_mcp_filesystem_paths()
        env = {
            "FASTMCP_SHOW_CLI_BANNER": "false",
        }

        config = {
            "name": "workspace_tools",
            "type": "stdio",
            "command": "fastmcp",
            "args": ["run", f"{script_path}:create_server"] + ["--", "--allowed-paths"] + paths,
            "env": env,
            "cwd": str(self.cwd),
        }

        return config

    def inject_filesystem_mcp(self, backend_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Inject filesystem and workspace tools MCP servers into backend configuration.

        Args:
            backend_config: Original backend configuration

        Returns:
            Modified configuration with MCP servers added
        """
        # Get existing mcp_servers configuration
        mcp_servers = backend_config.get("mcp_servers", [])

        # Handle both list format and Claude Code dict format
        if isinstance(mcp_servers, dict):
            # Claude Code format: {"playwright": {...}, "filesystem": {...}}
            existing_names = list(mcp_servers.keys())
            # Convert to list format for append operations
            converted_servers = []
            for name, server_config in mcp_servers.items():
                if isinstance(server_config, dict):
                    server = server_config.copy()
                    server["name"] = name
                    converted_servers.append(server)
            mcp_servers = converted_servers
        elif isinstance(mcp_servers, list):
            # List format: [{"name": "playwright", ...}, ...]
            existing_names = [server.get("name") for server in mcp_servers if isinstance(server, dict)]
        else:
            existing_names = []
            mcp_servers = []

        try:
            # Add filesystem server if missing
            if "filesystem" not in existing_names:
                mcp_servers.append(self.get_mcp_filesystem_config())
            else:
                logger.warning("[FilesystemManager.inject_filesystem_mcp] Custom filesystem MCP server already present")

            # Add workspace tools server if missing
            if "workspace_tools" not in existing_names:
                mcp_servers.append(self.get_workspace_tools_mcp_config())
            else:
                logger.warning("[FilesystemManager.inject_filesystem_mcp] Custom workspace_tools MCP server already present")

        except Exception as e:
            logger.warning(f"[FilesystemManager.inject_filesystem_mcp] Error checking existing MCP servers: {e}")

        # Update backend config
        backend_config["mcp_servers"] = mcp_servers

        return backend_config

    def get_pre_tool_hooks(self) -> Dict[str, List]:
        """
        Get pre-tool hooks configuration for MCP clients.

        Returns:
            Dict mapping hook types to lists of hook functions
        """

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

    async def save_snapshot(self, timestamp: Optional[str] = None, is_final: bool = False) -> None:
        """
        Save a snapshot of the workspace. Always saves to snapshot_storage if available (keeping only most recent).
        Additionally saves to log directories if logging is enabled.
        Then, clear the workspace so it is ready for next execution.

        Args:
            timestamp: Optional timestamp to use for the snapshot directory (if not provided, generates one)
            is_final: If True, save as final snapshot for presentation

        TODO: reimplement without 'shutil' and 'os' operations for true async, though we may not need to worry about race conditions here since only one agent writes at a time
        """
        logger.info(f"[FilesystemManager.save_snapshot] Called for agent_id={self.agent_id}, is_final={is_final}, snapshot_storage={self.snapshot_storage}")

        # Use current workspace as source
        source_dir = self.cwd
        source_path = Path(source_dir)

        if not source_path.exists() or not source_path.is_dir():
            logger.warning(f"[FilesystemManager] Source path invalid - exists: {source_path.exists()}, " f"is_dir: {source_path.is_dir() if source_path.exists() else False}")
            return

        if not any(source_path.iterdir()):
            logger.warning(f"[FilesystemManager.save_snapshot] Source path {source_path} is empty, skipping snapshot")
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
                        logger.warning(f"[FilesystemManager.save_snapshot] Skipping symlink: {item}")
                        continue
                    if item.is_file():
                        shutil.copy2(item, self.snapshot_storage / item.name)
                    elif item.is_dir():
                        shutil.copytree(item, self.snapshot_storage / item.name)
                    items_copied += 1

                logger.info(f"[FilesystemManager] Saved snapshot with {items_copied} items to {self.snapshot_storage}")

            # --- 2. Save to log directories ---
            log_session_dir = get_log_session_dir()
            if log_session_dir and self.agent_id:
                if is_final:
                    dest_dir = log_session_dir / "final" / self.agent_id / "workspace"
                    if dest_dir.exists():
                        shutil.rmtree(dest_dir)
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    logger.info(f"[FilesystemManager.save_snapshot] Final log snapshot dest_dir: {dest_dir}")
                else:
                    if not timestamp:
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                    dest_dir = log_session_dir / self.agent_id / timestamp / "workspace"
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    logger.info(f"[FilesystemManager.save_snapshot] Regular log snapshot dest_dir: {dest_dir}")

                items_copied = 0
                for item in source_path.iterdir():
                    if item.is_symlink():
                        logger.warning(f"[FilesystemManager.save_snapshot] Skipping symlink: {item}")
                        continue
                    if item.is_file():
                        shutil.copy2(item, dest_dir / item.name)
                    elif item.is_dir():
                        shutil.copytree(item, dest_dir / item.name, dirs_exist_ok=True)
                    items_copied += 1

                logger.info(f"[FilesystemManager] Saved {'final' if is_final else 'regular'} " f"log snapshot with {items_copied} items to {dest_dir}")

        except Exception as e:
            logger.exception(f"[FilesystemManager.save_snapshot] Snapshot failed: {e}")
            return

        logger.info("[FilesystemManager] Snapshot saved successfully, workspace preserved for logs and debugging")

    def clear_workspace(self) -> None:
        """
        Clear the current workspace to prepare for a new agent execution.

        This should be called at the START of agent execution, not at the end,
        to preserve workspace contents for logging and debugging.
        """
        workspace_path = self.get_current_workspace()

        if not workspace_path.exists() or not workspace_path.is_dir():
            logger.debug(f"[FilesystemManager] Workspace does not exist or is not a directory: {workspace_path}")
            return

        # Safety checks
        if workspace_path == Path("/") or len(workspace_path.parts) < 3:
            logger.error(f"[FilesystemManager] Refusing to clear unsafe workspace path: {workspace_path}")
            return

        try:
            logger.info("[FilesystemManager] Clearing workspace at agent startup. Current contents:")
            items_to_clear = list(workspace_path.iterdir())

            for item in items_to_clear:
                logger.info(f" - {item}")
                if item.is_symlink():
                    logger.warning(f"[FilesystemManager] Skipping symlink during clear: {item}")
                    continue
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)

            logger.info("[FilesystemManager] Workspace cleared successfully, ready for new agent execution")

        except Exception as e:
            logger.error(f"[FilesystemManager] Failed to clear workspace: {e}")
            # Don't raise - agent can still work with non-empty workspace

    def clear_temp_workspace(self) -> None:
        """
        Clear the temporary workspace parent directory at orchestration startup.

        This clears the entire temp workspace parent (e.g., temp_workspaces/),
        removing all agent directories from previous runs to prevent cross-contamination.
        """
        if not self.agent_temporary_workspace_parent:
            logger.debug("[FilesystemManager] No temp workspace parent configured to clear")
            return

        if not self.agent_temporary_workspace_parent.exists():
            logger.debug(f"[FilesystemManager] Temp workspace parent does not exist: {self.agent_temporary_workspace_parent}")
            return

        # Safety checks
        if self.agent_temporary_workspace_parent == Path("/") or len(self.agent_temporary_workspace_parent.parts) < 3:
            logger.error(f"[FilesystemManager] Refusing to clear unsafe temp workspace parent path: {self.agent_temporary_workspace_parent}")
            return

        try:
            logger.info(f"[FilesystemManager] Clearing temp workspace parent at orchestration startup: {self.agent_temporary_workspace_parent}")

            items_to_clear = list(self.agent_temporary_workspace_parent.iterdir())
            for item in items_to_clear:
                logger.info(f" - Removing temp workspace item: {item}")
                if item.is_symlink():
                    logger.warning(f"[FilesystemManager] Skipping symlink during temp clear: {item}")
                    continue
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)

            logger.info("[FilesystemManager] Temp workspace parent cleared successfully")

        except Exception as e:
            logger.error(f"[FilesystemManager] Failed to clear temp workspace parent: {e}")
            # Don't raise - orchestration can continue without clean temp workspace

    async def copy_snapshots_to_temp_workspace(self, all_snapshots: Dict[str, Path], agent_mapping: Dict[str, str]) -> Optional[Path]:
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

    def _log_workspace_contents(self, workspace_path: Path, workspace_name: str, context: str = "") -> None:
        """
        Log the contents of a workspace directory for visibility.

        Args:
            workspace_path: Path to the workspace to log
            workspace_name: Human-readable name for the workspace
            context: Additional context (e.g., "before execution", "after execution")
        """
        if not workspace_path or not workspace_path.exists():
            logger.info(f"[FilesystemManager.{workspace_name}] {context} - Workspace does not exist: {workspace_path}")
            return

        try:
            files = list(workspace_path.rglob("*"))
            file_paths = [str(f.relative_to(workspace_path)) for f in files if f.is_file()]
            dir_paths = [str(f.relative_to(workspace_path)) for f in files if f.is_dir()]

            logger.info(f"[FilesystemManager.{workspace_name}] {context} - Workspace: {workspace_path}")
            if file_paths:
                logger.info(f"[FilesystemManager.{workspace_name}] {context} - Files ({len(file_paths)}): {file_paths}")
            if dir_paths:
                logger.info(f"[FilesystemManager.{workspace_name}] {context} - Directories ({len(dir_paths)}): {dir_paths}")
            if not file_paths and not dir_paths:
                logger.info(f"[FilesystemManager.{workspace_name}] {context} - Empty workspace")
        except Exception as e:
            logger.warning(f"[FilesystemManager.{workspace_name}] {context} - Error reading workspace: {e}")

    def log_current_state(self, context: str = "") -> None:
        """
        Log the current state of both main and temp workspaces.

        Args:
            context: Context for the logging (e.g., "before execution", "after answer")
        """
        agent_context = f"agent_id={self.agent_id}, {context}" if context else f"agent_id={self.agent_id}"

        # Log main workspace
        self._log_workspace_contents(self.get_current_workspace(), "main_workspace", agent_context)

        # Log temp workspace if it exists
        if self.agent_temporary_workspace:
            self._log_workspace_contents(self.agent_temporary_workspace, "temp_workspace", agent_context)

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
                    raise AssertionError(f"Refusing to delete workspace outside of parent: {p}")

            if p == Path("/") or len(p.parts) < 3:
                raise AssertionError(f"Unsafe path for deletion: {p}")

            shutil.rmtree(p)
        except Exception as e:
            logger.warning(f"[FilesystemManager] cleanup failed for {p}: {e}")
