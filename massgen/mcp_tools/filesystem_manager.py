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
        agent_temporary_workspace_parent: str = None
    ):
        """
        Initialize FilesystemManager.
        
        Args:
            cwd: Working directory path for the agent
            agent_temporary_workspace_parent: Parent directory for temporary workspaces
        """
        self.agent_id = None  # Will be set by orchestrator via setup_orchestration_paths
        
        # Setup main working directory
        self.cwd = self._setup_workspace(cwd)
        
        # Orchestration-specific paths (set by setup_orchestration_paths)
        self.snapshot_storage = None
        self.agent_temporary_workspace = None  # Full path for this specific agent's temporary workspace
        self.agent_temporary_workspace_parent = agent_temporary_workspace_parent
        # Get absolute path for temporary workspace parent if provided
        if self.agent_temporary_workspace_parent:
            temp_parent_path = Path(self.agent_temporary_workspace_parent)
            if not temp_parent_path.is_absolute():
                temp_parent_path = temp_parent_path.resolve()
            self.agent_temporary_workspace_parent = temp_parent_path
         
        # Track whether we're using a temporary workspace
        self._using_temporary = False
        self._original_cwd = self.cwd
    
    def setup_orchestration_paths(
        self,
        agent_id: str,
        snapshot_storage: Optional[str] = None,
        agent_temporary_workspace: Optional[str] = None
    ) -> None:
        """
        Setup orchestration-specific paths for snapshots and temporary workspace.
        Called by orchestrator to configure paths for this specific orchestration.
        
        Args:
            agent_id: The agent identifier for this orchestration
            snapshot_storage: Base path for storing workspace snapshots
            agent_temporary_workspace: Base path for temporary workspace during context sharing
        """
        self.agent_id = agent_id
        # Setup snapshot storage if provided
        if snapshot_storage and self.agent_id:
            self.snapshot_storage = Path(snapshot_storage) / self.agent_id
            self.snapshot_storage.mkdir(parents=True, exist_ok=True)
        
        # Setup temporary workspace for context sharing
        if agent_temporary_workspace and self.agent_id:
            temp_workspace_path = Path(agent_temporary_workspace) / self.agent_id
            # Convert to absolute path
            if not temp_workspace_path.is_absolute():
                temp_workspace_path = temp_workspace_path.resolve()
            self.agent_temporary_workspace = temp_workspace_path
            self.agent_temporary_workspace.mkdir(parents=True, exist_ok=True)
            
        # Also setup log directories if we have an agent_id
        if self.agent_id:
            log_session_dir = get_log_session_dir()
            if log_session_dir:
                agent_log_dir = log_session_dir / self.agent_id
                agent_log_dir.mkdir(parents=True, exist_ok=True)
    
    def _setup_workspace(self, cwd: str) -> Path:
        """Setup workspace directory, creating if needed and clearing existing files safely."""
        workspace = Path(cwd).resolve()

        # Safety checks
        if not workspace.is_absolute():
            raise AssertionError("Workspace must be absolute")
        if workspace == Path("/") or len(workspace.parts) < 3:
            raise AssertionError(f"Refusing unsafe workspace path: {workspace}")
        if self.agent_temporary_workspace_parent:
            parent = Path(self.agent_temporary_workspace_parent).resolve()
            try:
                workspace.relative_to(parent)
            except ValueError:
                raise AssertionError(f"Workspace must be under safe parent: {parent}")

        # Create if needed
        workspace.mkdir(parents=True, exist_ok=True)

        # Clear existing contents
        if workspace.exists() and workspace.is_dir():
            for item in workspace.iterdir():
                if item.is_symlink():
                    raise AssertionError(f"Refusing to clear symlink in workspace: {item}")
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
            "type": "stdio",
            "command": "npx",
            "args": [
                "-y",
                "@modelcontextprotocol/server-filesystem",
                str(self.cwd)  # Main workspace directory
            ]
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
        # Get existing mcp_servers configuration
        mcp_servers = backend_config.get("mcp_servers", {})
        
        # Convert list format to dict if needed
        if isinstance(mcp_servers, list):
            # Convert list of servers to dict format
            servers_dict = {}
            for server in mcp_servers:
                if isinstance(server, dict):
                    name = server.get("name", f"server_{len(servers_dict)}")
                    servers_dict[name] = server
            mcp_servers = servers_dict
        
        # Add filesystem server if not already present
        if "filesystem" not in mcp_servers:
            mcp_servers["filesystem"] = self.get_mcp_filesystem_config()
        
        # Update backend config
        backend_config["mcp_servers"] = mcp_servers
        
        return backend_config
    
    async def save_snapshot(self, source_dir: Optional[Path] = None, is_final: bool = False) -> None:
        """
        Save a snapshot of the workspace.
        
        Args:
            source_dir: Source directory to snapshot (defaults to current workspace)
            is_final: If True, save as final snapshot for presentation

        TODO: reimplement without 'shutil' and 'os' operations for true async 
        """

        if not self.snapshot_storage:
            logger.warning("No snapshot storage dir set — skipping save_snapshot")
            return

        # Use current workspace if no source specified
        if source_dir is None:
            source_dir = self.cwd
        
        source_path = Path(source_dir)
        
        if not source_path.exists() or not source_path.is_dir():
            logger.warning(f"[FilesystemManager] Source path invalid - exists: {source_path.exists()}, is_dir: {source_path.is_dir() if source_path.exists() else False}")
            return
        
        # Determine destination
        if is_final:
            dest_dir = self.snapshot_storage.parent / "final" / self.agent_id if self.agent_id else self.snapshot_storage / "final"
        else:
            dest_dir = self.snapshot_storage
        
        # Clear existing snapshot and copy new one
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy all contents
        items_copied = 0
        for item in source_path.iterdir():
            if item.is_file():
                shutil.copy2(item, dest_dir / item.name)
                items_copied += 1
                logger.debug(f"[FilesystemManager] Copied file: {item.name}")
            elif item.is_dir():
                shutil.copytree(item, dest_dir / item.name, dirs_exist_ok=True)
                items_copied += 1
                logger.debug(f"[FilesystemManager] Copied directory: {item.name}")
        
        # Also save timestamped snapshot to log directory
        log_session_dir = get_log_session_dir()
        if log_session_dir and self.agent_id:
            if is_final:
                log_dir = log_session_dir / "final_workspace" / self.agent_id
                log_dir.mkdir(parents=True, exist_ok=True)
            else:
                log_dir = log_session_dir / self.agent_id
            
            if any(source_path.iterdir()):
                # Create timestamped subdirectory
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                timestamped_dir = log_dir / timestamp
                timestamped_dir.mkdir(parents=True, exist_ok=True)
                
                # Copy snapshot contents
                for item in source_path.iterdir():
                    if item.is_file():
                        shutil.copy2(item, timestamped_dir / item.name)
                    elif item.is_dir():
                        shutil.copytree(item, timestamped_dir / item.name, dirs_exist_ok=True)
    
    async def restore_snapshots(self, all_snapshots: Dict[str, Path], agent_mapping: Dict[str, str]) -> Optional[Path]:
        """
        Restore snapshots from multiple agents to temporary workspace.

        This method is called by the orchestrator before starting an agent that needs context from others. This ensures it has all the necessary files in its temporary workspace.
        
        Args:
            all_snapshots: Dictionary mapping agent_id to snapshot path
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

        #Aggressive path-checking for validity 
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
