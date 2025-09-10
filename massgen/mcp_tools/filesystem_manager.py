"""
Filesystem Manager for MassGen - Handles workspace and snapshot management.

This manager provides centralized filesystem operations for backends that support
filesystem access through MCP. It manages:
- Workspace directory creation and cleanup
- Snapshot storage for context sharing
- Temporary workspace restoration
- Path configuration for MCP filesystem server

The manager is backend-agnostic and works with any backend that has filesystem
MCP tools configured.
"""

import os
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List, Any
from ..logger_config import logger, get_log_session_dir


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
    ):
        """
        Initialize FilesystemManager.

        Args:
            cwd: Working directory path for the agent
            agent_temporary_workspace_parent: Parent directory for temporary workspaces
        """
        self.agent_id = (
            None  # Will be set by orchestrator via setup_orchestration_paths
        )

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
        # Build MCP server configuration with access to both workspaces
        config = {
            "name": "filesystem",
            "type": "stdio",
            "command": "npx",
            "args": [
                "-y",
                "@modelcontextprotocol/server-filesystem",
                str(self.cwd),  # Main workspace directory
            ],
        }

        # Add temporary workspace parent if it exists (for context sharing)
        if self.agent_temporary_workspace_parent:
            config["args"].append(str(self.agent_temporary_workspace_parent))

        return config

    def inject_filesystem_mcp(self, backend_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Inject filesystem MCP server into backend configuration.

        Args:
            backend_config: Original backend configuration

        Returns:
            Modified configuration with filesystem MCP server added
        """
        # Get existing mcp_servers configuration and add filesystem server if missing
        mcp_servers = backend_config.get("mcp_servers", [])
        try:
            if "filesystem" not in [server.get("name") for server in mcp_servers]:
                mcp_servers.append(self.get_mcp_filesystem_config())
            else:
                logger.warning(
                    "[FilesystemManager.inject_filesystem_mcp] Custom filesystem MCP server already present in configuration, continuing without changes"
                )
        except Exception as e:
            logger.warning(
                f"[FilesystemManager.inject_filesystem_mcp] Error checking existing MCP servers: {e}"
            )

        # Update backend config
        backend_config["mcp_servers"] = mcp_servers

        return backend_config

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
