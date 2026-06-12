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

import asyncio
import json
import os
import shutil
import stat
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from ..logger_config import get_log_session_dir, logger
from ..mcp_tools.client import HookType
from . import _code_execution_server as ce_module
from . import _workspace_tools_server as wc_module
from ._base import Permission
from ._constants import FRAMEWORK_MCPS
from ._path_permission_manager import PathPermissionManager
from ._snapshot_version_store import SnapshotVersionStore


def _remove_readonly(func, path, _exc_unused):
    """Error handler for shutil.rmtree to handle read-only files on Windows (e.g. .git/objects).

    Signature accepts three args so it works with both the ``onerror``
    callback (func, path, exc_info) and the ``onexc`` callback
    (func, path, exc) introduced in Python 3.12.
    """
    os.chmod(path, stat.S_IRWXU)
    func(path)


def _safe_rmtree(path):
    """shutil.rmtree that handles read-only files on Windows."""
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=_remove_readonly)
    else:
        shutil.rmtree(path, onerror=_remove_readonly)


def git_commit_if_changed(workspace: Path, message: str) -> bool:
    """Commit any uncommitted changes in the workspace.

    This is a standalone function that can be called from anywhere to create
    a git commit in an agent workspace. It's isolated from parent git repos
    using explicit GIT_DIR and GIT_WORK_TREE environment variables.

    Args:
        workspace: The workspace root path (must contain a .git directory)
        message: Commit message (should use semantic prefixes like [TASK], [SNAPSHOT], etc.)

    Returns:
        True if a commit was made, False otherwise (no changes or not a git repo)
    """
    import subprocess

    logger.info(f"[git_commit_if_changed] Called with workspace={workspace}, message={message[:50]}...")

    # Check if this is a git repo
    git_dir = workspace / ".git"
    if not git_dir.exists():
        logger.info(f"[git_commit_if_changed] No .git directory at {git_dir}, skipping")
        return False

    try:
        # Sandboxed git environment to isolate from parent repos
        git_env = {
            "GIT_DIR": str(git_dir),
            "GIT_WORK_TREE": str(workspace),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TEMPLATE_DIR": "",
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(workspace),
        }

        # Check if there are any changes
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=workspace,
            capture_output=True,
            check=True,
            env=git_env,
        )

        if not result.stdout.strip():
            return False  # No changes to commit

        # Stage all changes
        subprocess.run(
            ["git", "add", "-A"],
            cwd=workspace,
            capture_output=True,
            check=True,
            env=git_env,
        )

        # Commit with --no-verify to skip any hooks
        subprocess.run(
            ["git", "commit", "--no-verify", "-m", message],
            cwd=workspace,
            capture_output=True,
            check=True,
            env=git_env,
        )

        logger.info(f"[git_commit_if_changed] Committed: {message}")
        return True

    except subprocess.CalledProcessError as e:
        logger.warning(f"[git_commit_if_changed] Git commit failed: {e.stderr.decode() if e.stderr else e}")
        return False


_WORKSPACE_METADATA_DIRS = frozenset(
    {".git", ".codex", ".gemini", ".antigravity", ".antigravitycli", ".massgen", "memory"},
)


def has_meaningful_content(path: Path | None) -> bool:
    """Check if a directory contains meaningful deliverable content.

    Excludes symlinks and workspace/backend metadata directories
    that are not agent-produced deliverables.
    """
    if not path or not path.exists() or not path.is_dir():
        return False
    return any(not item.is_symlink() and item.name not in _WORKSPACE_METADATA_DIRS for item in path.iterdir())


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
        context_paths: list[dict[str, Any]] = None,
        context_write_access_enabled: bool = False,
        enforce_read_before_delete: bool = True,
        enable_image_generation: bool = False,
        enable_mcp_command_line: bool = False,
        command_line_allowed_commands: list[str] = None,
        command_line_blocked_commands: list[str] = None,
        command_line_execution_mode: str = "local",
        command_line_docker_image: str = "ghcr.io/massgen/mcp-runtime:latest",
        command_line_docker_memory_limit: str | None = None,
        command_line_docker_cpu_limit: float | None = None,
        command_line_docker_network_mode: str = "none",
        command_line_docker_enable_sudo: bool = False,
        command_line_docker_credentials: dict[str, Any] | None = None,
        command_line_docker_packages: dict[str, Any] | None = None,
        command_line_srt_network_allowed_domains: list[str] | None = None,
        command_line_srt_deny_read: list[str] | None = None,
        command_line_srt_allow_unix_sockets: list[str] | None = None,
        command_line_srt_read_mode: str = "confined",
        command_line_srt_allow_read: list[str] | None = None,
        command_line_srt_read_only: bool = False,
        enable_audio_generation: bool = False,
        enable_file_generation: bool = False,
        exclude_file_operation_mcps: bool = False,
        use_mcpwrapped_for_tool_filtering: bool = False,
        use_no_roots_wrapper: bool = False,
        enable_code_based_tools: bool = False,
        custom_tools_path: str | None = None,
        auto_discover_custom_tools: bool = False,
        exclude_custom_tools: list[str] | None = None,
        direct_mcp_servers: list[str] | None = None,
        shared_tools_directory: str | None = None,
        instance_id: str | None = None,
        filesystem_session_id: str | None = None,
        session_storage_base: str | None = None,
        use_two_tier_workspace: bool = False,
        write_mode: str | None = None,
    ):
        """
        Initialize FilesystemManager.

        Args:
            cwd: Working directory path for the agent
            agent_temporary_workspace_parent: Parent directory for temporary workspaces
            context_paths: List of context path configurations for access control
            context_write_access_enabled: Whether write access is enabled for context paths
            enforce_read_before_delete: Whether to enforce read-before-delete policy for workspace files
            enable_image_generation: Whether to enable image generation tools
            enable_mcp_command_line: Whether to enable MCP command line execution tool
            command_line_allowed_commands: Whitelist of allowed command patterns (regex)
            command_line_blocked_commands: Blacklist of blocked command patterns (regex)
            command_line_execution_mode: Execution mode - "local" or "docker"
            command_line_docker_image: Docker image to use for containers
            command_line_docker_memory_limit: Memory limit for Docker containers (e.g., "2g")
            command_line_docker_cpu_limit: CPU limit for Docker containers (e.g., 2.0 for 2 CPUs)
            command_line_docker_network_mode: Network mode for Docker containers (none/bridge/host)
            command_line_docker_enable_sudo: Enable sudo access in Docker containers (isolated from host system)
            command_line_docker_credentials: Credential management configuration dict
            command_line_docker_packages: Package management configuration dict
            exclude_file_operation_mcps: If True, exclude file operation MCP tools (filesystem and workspace_tools file ops).
                                         Agents use command-line tools instead. Keeps command execution, media generation, and planning MCPs.
            use_mcpwrapped_for_tool_filtering: If True, use mcpwrapped to filter MCP tools at protocol level.
                                              Required for Claude Code backend which doesn't support allowed_tools for MCP tools.
                                              See: https://github.com/anthropics/claude-code/issues/7328
                                              Requires: npm i -g mcpwrapped (https://github.com/VitoLin/mcpwrapped)
            use_no_roots_wrapper: If True, wrap MCP filesystem server with no-roots wrapper that intercepts
                                  and removes the MCP roots protocol. This prevents clients (like Claude Code SDK)
                                  from overriding our command-line paths with their own roots.
                                  Required for Claude Code backend to access temp_workspaces.
            enable_code_based_tools: If True, generate Python wrapper code for MCP tools in servers/ directory.
                                     Agents discover and call tools via filesystem (CodeAct paradigm).
            custom_tools_path: Optional path to custom tools directory to copy into workspace
            auto_discover_custom_tools: If True and custom_tools_path is not set, automatically use default path 'massgen/tool/'
            exclude_custom_tools: Optional list of directory names to exclude when copying custom tools (e.g., ['_claude_computer_use', '_gemini_computer_use'])
            direct_mcp_servers: Optional list of MCP server names to keep as direct protocol tools when enable_code_based_tools is True.
                               These servers remain callable as native tools in the prompt rather than being filtered to code-only access.
                               Example: ['logfire', 'context7']
            shared_tools_directory: Optional shared directory for code-based tools (servers/, custom_tools/, .mcp/).
                                    If provided, tools are generated once in shared location (read-only for all agents).
                                    If None, tools are generated in each agent's workspace (per-agent, in snapshots).
            instance_id: Optional unique instance ID for parallel execution (used in Docker container naming)
            filesystem_session_id: Optional session ID for multi-turn support. When provided with session_storage_base,
                       enables session directory pre-mounting for Docker containers.
            session_storage_base: Base directory for session storage (e.g., ".massgen/sessions").
                                 Required along with filesystem_session_id for session pre-mounting.
            use_two_tier_workspace: If True, create scratch/ and deliverable/ subdirectories in workspace
                                   and initialize git versioning for audit trails.
            write_mode: Isolation mode for agent writes - "auto", "worktree", "isolated", or "legacy".
                       When set (not None or "legacy"), creates isolated write contexts for context paths.
        """
        self.agent_id = None  # Will be set by orchestrator via setup_orchestration_paths
        self.write_mode = write_mode
        # write_mode replaces the old two-tier workspace — suppress it when write_mode is active
        if write_mode and write_mode != "legacy":
            self.use_two_tier_workspace = False
        else:
            self.use_two_tier_workspace = use_two_tier_workspace
        self.instance_id = instance_id  # Unique instance ID for parallel execution
        self.enable_image_generation = enable_image_generation
        self.enable_mcp_command_line = enable_mcp_command_line
        self.exclude_file_operation_mcps = exclude_file_operation_mcps
        self.use_mcpwrapped_for_tool_filtering = use_mcpwrapped_for_tool_filtering
        self.use_no_roots_wrapper = use_no_roots_wrapper
        self.enable_code_based_tools = enable_code_based_tools
        self.exclude_custom_tools = exclude_custom_tools if exclude_custom_tools else []
        self.direct_mcp_servers = direct_mcp_servers if direct_mcp_servers else []

        # Handle custom_tools_path with auto-discovery
        if custom_tools_path:
            # Explicit path takes precedence
            self.custom_tools_path = Path(custom_tools_path)
        elif auto_discover_custom_tools:
            # Auto-discover from default location (massgen/tool/)
            # Use package directory to find tools, not current working directory
            package_dir = Path(__file__).parent.parent  # massgen/filesystem_manager -> massgen
            default_path = package_dir / "tool"
            if default_path.exists():
                self.custom_tools_path = default_path
                logger.info(f"[FilesystemManager] Auto-discovered custom tools at {default_path}")
            else:
                logger.warning(f"[FilesystemManager] auto_discover_custom_tools enabled but default path does not exist: {default_path}")
                self.custom_tools_path = None
        else:
            self.custom_tools_path = None

        # Convert shared_tools_directory to absolute path if provided
        # For code-based tools, we'll append a config hash subdirectory later
        if shared_tools_directory:
            shared_tools_path = Path(shared_tools_directory)
            if not shared_tools_path.is_absolute():
                shared_tools_path = shared_tools_path.resolve()
            self.shared_tools_base = shared_tools_path  # Base directory
            self.shared_tools_directory = None  # Will be set with hash in setup_code_based_tools
        else:
            self.shared_tools_base = None
            self.shared_tools_directory = None
        self.command_line_allowed_commands = command_line_allowed_commands
        self.command_line_blocked_commands = command_line_blocked_commands

        # Auto-detect if running inside Docker and switch to local execution
        # The outer container already provides isolation, so local execution is safe
        import os

        if command_line_execution_mode == "docker" and os.path.exists("/.dockerenv"):
            logger.info(
                "[FilesystemManager] Already running inside Docker container - " "switching to local execution mode. The container provides isolation.",
            )
            command_line_execution_mode = "local"

        self.command_line_execution_mode = command_line_execution_mode
        self.command_line_docker_image = command_line_docker_image
        self.command_line_docker_memory_limit = command_line_docker_memory_limit
        self.command_line_docker_cpu_limit = command_line_docker_cpu_limit
        self.command_line_docker_network_mode = command_line_docker_network_mode
        self.command_line_docker_enable_sudo = command_line_docker_enable_sudo
        self.command_line_docker_credentials = command_line_docker_credentials
        self.command_line_docker_packages = command_line_docker_packages
        self.command_line_srt_network_allowed_domains = command_line_srt_network_allowed_domains or []
        self.command_line_srt_deny_read = command_line_srt_deny_read or []
        self.command_line_srt_allow_unix_sockets = command_line_srt_allow_unix_sockets or []
        self.command_line_srt_read_mode = command_line_srt_read_mode or "confined"
        self.command_line_srt_allow_read = command_line_srt_allow_read or []
        self.command_line_srt_read_only = bool(command_line_srt_read_only)

        # Initialize Docker manager if Docker mode enabled
        self.docker_manager = None
        if enable_mcp_command_line and command_line_execution_mode == "docker":
            from ._docker_manager import DockerManager

            self.docker_manager = DockerManager(
                image=command_line_docker_image,
                network_mode=command_line_docker_network_mode,
                memory_limit=command_line_docker_memory_limit,
                cpu_limit=command_line_docker_cpu_limit,
                enable_sudo=command_line_docker_enable_sudo,
                credentials=command_line_docker_credentials,
                packages=command_line_docker_packages,
                instance_id=instance_id,
            )

        # Initialize session mount manager for multi-turn Docker support
        # This pre-mounts the session directory so all turn workspaces are
        # automatically visible without container recreation between turns
        self.session_mount_manager = None
        if filesystem_session_id and session_storage_base and self.docker_manager:
            from ._session_mount_manager import SessionMountManager

            self.session_mount_manager = SessionMountManager(Path(session_storage_base))
            self.session_mount_manager.initialize_session(filesystem_session_id)
            logger.info(f"[FilesystemManager] Session mount manager initialized for session {filesystem_session_id}")

        self.enable_audio_generation = enable_audio_generation

        # Store merged skills directory path for local mode
        self.local_skills_directory = None

        # Store user MCP servers for code-based tools (excludes framework MCPs)
        self.user_mcp_servers = []

        # Initialize path permission manager
        self.path_permission_manager = PathPermissionManager(
            context_write_access_enabled=context_write_access_enabled,
            enforce_read_before_delete=enforce_read_before_delete,
        )

        # Add context paths if provided
        if context_paths:
            self.path_permission_manager.add_context_paths(context_paths)

        # Initialize SRT (OS-level sandbox-runtime) manager if SRT mode enabled.
        # Reads managed_paths lazily at settings-build time, so it's safe to
        # construct here before workspace/temp paths are added below. Settings
        # live OUTSIDE the sandbox's writable set so the agent can't tamper with
        # its own policy.
        self.srt_manager = None
        if enable_mcp_command_line and self.command_line_execution_mode == "srt":
            import tempfile

            from ._srt_manager import SrtManager

            self.srt_manager = SrtManager(
                self.path_permission_manager,
                network_allowed_domains=self.command_line_srt_network_allowed_domains,
                extra_deny_read=self.command_line_srt_deny_read,
                allow_unix_sockets=self.command_line_srt_allow_unix_sockets,
                read_mode=self.command_line_srt_read_mode,
                allow_read=self.command_line_srt_allow_read,
                read_only=self.command_line_srt_read_only,
                settings_dir=Path(tempfile.gettempdir()) / "massgen_srt",
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
            # Clear existing temp workspace parent if it exists, else we would only clear those with the exact agent_ids in the config.
            self.clear_temp_workspace()

        # Setup main working directory (now that agent_temporary_workspace_parent is set)
        # Pass init_two_tier=True for main workspace to create scratch/deliverable if enabled
        self.cwd = self._setup_workspace(cwd, init_two_tier=True)

        # Add workspace to path manager (workspace is typically writable)
        self.path_permission_manager.add_path(self.cwd, Permission.WRITE, "workspace")
        # Add temporary workspace to path manager (read-only)
        # Create the directory if it doesn't exist - MCP filesystem server requires
        # directories to exist when validating allowed paths
        if self.agent_temporary_workspace_parent:
            if not self.agent_temporary_workspace_parent.exists():
                self.agent_temporary_workspace_parent.mkdir(parents=True, exist_ok=True)
                logger.info(f"[FilesystemManager] Created temp workspace parent directory: {self.agent_temporary_workspace_parent}")
            self.path_permission_manager.add_path(self.agent_temporary_workspace_parent, Permission.READ, "temp_workspace")

        # Orchestration-specific paths (set by setup_orchestration_paths)
        self.snapshot_storage = None  # Path for storing workspace snapshots
        self.agent_temporary_workspace = None  # Full path for this specific agent's temporary workspace

        # Track whether we're using a temporary workspace
        self._using_temporary = False
        self._original_cwd = self.cwd

        # Initialize isolation context manager if write_mode is set (and not legacy)
        self.isolation_manager = None
        if write_mode and write_mode != "legacy":
            from ._isolation_context_manager import IsolationContextManager

            # Use filesystem_session_id if available, otherwise generate one
            session_id = filesystem_session_id or f"fm_{id(self)}"
            self.isolation_manager = IsolationContextManager(
                session_id=session_id,
                write_mode=write_mode,
            )
            logger.info(f"[FilesystemManager] IsolationContextManager initialized: mode={write_mode}")

    def setup_orchestration_paths(
        self,
        agent_id: str,
        snapshot_storage: str | None = None,
        agent_temporary_workspace: str | None = None,
        skills_directory: str | None = None,
        massgen_skills: list[str] | None = None,
        load_previous_session_skills: bool = False,
        workspace_token: str | None = None,
    ) -> None:
        """
        Setup orchestration-specific paths for snapshots and temporary workspace.
        Called by orchestrator to configure paths for this specific orchestration.

        Args:
            agent_id: The agent identifier for this orchestration
            snapshot_storage: Base path for storing workspace snapshots
            agent_temporary_workspace: Base path for temporary workspace during context sharing
            skills_directory: Path to skills directory to mount in Docker (e.g., .agent/skills)
            load_previous_session_skills: If True, include evolving skills from previous sessions
            workspace_token: Anonymous token for temp workspace path to hide real agent_id (MAS-338)
        """
        logger.info(
            f"[FilesystemManager.setup_orchestration_paths] Called for agent_id={agent_id}, snapshot_storage={snapshot_storage}, "
            f"agent_temporary_workspace={agent_temporary_workspace}, skills_directory={skills_directory}",
        )
        self.agent_id = agent_id
        # Use token for temp workspace path to avoid leaking real agent_id (MAS-338)
        self.workspace_token = workspace_token or agent_id

        # Setup snapshot storage if provided
        if snapshot_storage and self.agent_id:
            self.snapshot_storage = Path(snapshot_storage) / self.agent_id
            self.snapshot_storage.mkdir(parents=True, exist_ok=True)

        # Setup temporary workspace for context sharing (uses token to hide real agent_id)
        if agent_temporary_workspace and self.agent_id:
            self.agent_temporary_workspace = self._setup_workspace(self.agent_temporary_workspace_parent / self.workspace_token)

        # Note: Agent log directories are created on-demand when save_snapshot() is called,
        # not preemptively here. This avoids creating empty directories for agents that
        # don't produce any workspace content.

        # Create Docker container if Docker mode enabled
        if self.docker_manager and self.agent_id:
            context_paths = self.path_permission_manager.get_context_paths()

            # When write_mode is active, worktrees (inside workspace) replace original
            # context paths. Don't mount the originals — mount only .git/ dirs so
            # worktree git operations (commit, branch) can resolve references.
            extra_mount_paths = None
            if self.write_mode and self.write_mode != "legacy" and context_paths:
                extra_mount_paths = []
                preserved_context_paths = []
                suppressed_repo_paths = []
                for ctx_path_config in context_paths:
                    ctx_path = ctx_path_config.get("path", "")
                    permission = ctx_path_config.get("permission", "read")
                    git_dir = os.path.join(ctx_path, ".git")
                    if ctx_path and os.path.isdir(git_dir) and permission != "read":
                        # Only suppress writable git repo paths (they use worktree
                        # isolation). Read-only context paths (e.g., parent workspace
                        # mounted for subagents) must stay mounted in Docker so the
                        # agent can access deliverable files.
                        suppressed_repo_paths.append(ctx_path)
                        extra_mount_paths.append((git_dir, git_dir, "rw"))
                        logger.info(
                            f"[FilesystemManager] write_mode: mounting .git/ dir for worktree refs: {git_dir}",
                        )
                    else:
                        # Preserve read-only context paths and non-git paths (e.g.,
                        # log/session directories, parent workspaces) so agents can
                        # still read external artifacts in Docker.
                        preserved_context_paths.append(ctx_path_config)
                context_paths = preserved_context_paths
                logger.info(
                    "[FilesystemManager] write_mode: suppressed {} repo context path mounts, preserved {} non-repo context paths, added {} .git/ mounts",
                    len(suppressed_repo_paths),
                    len(context_paths),
                    len(extra_mount_paths),
                )

            # Get session mount config if session manager is initialized
            session_mount = None
            if self.session_mount_manager:
                session_mount = self.session_mount_manager.get_mount_config()
                logger.info(f"[FilesystemManager] Session mount configured: {session_mount}")

            docker_skills_dir = self.docker_manager.create_container(
                agent_id=self.agent_id,
                workspace_path=self.cwd,
                temp_workspace_path=self.agent_temporary_workspace_parent if self.agent_temporary_workspace_parent else None,
                context_paths=context_paths,
                session_mount=session_mount,
                skills_directory=skills_directory,
                massgen_skills=massgen_skills,
                shared_tools_directory=self.shared_tools_base,
                load_previous_session_skills=load_previous_session_skills,
                extra_mount_paths=extra_mount_paths,
            )
            logger.info(f"[FilesystemManager] Docker container created for agent {self.agent_id}")

            # Log context path mount summary for debugging
            original_context_paths = self.path_permission_manager.get_context_paths() if self.path_permission_manager else []
            logger.info(
                f"[FilesystemManager] Docker mount summary for {self.agent_id}: "
                f"original_context_paths={[p.get('path', '') for p in original_context_paths]}, "
                f"mounted_context_paths={[p.get('path', '') for p in context_paths]}, "
                f"extra_mount_paths={extra_mount_paths}, "
                f"write_mode={self.write_mode}",
            )

            # Add Docker skills directory to allowed paths if created
            if docker_skills_dir:
                from ._base import Permission

                self.path_permission_manager.add_path(docker_skills_dir, Permission.READ, "docker_skills")
                logger.info(f"[Docker] Added skills directory to allowed paths: {docker_skills_dir}")

        # Setup local skills if local mode enabled and skills configured
        if self.enable_mcp_command_line and self.command_line_execution_mode == "local" and (skills_directory or massgen_skills):
            self.setup_local_skills(
                skills_directory,
                massgen_skills,
                load_previous_session_skills=load_previous_session_skills,
            )
        # For agents without command-line execution (non-Docker),
        # still add the skills directory to allowed paths for filesystem MCP read access
        elif not self.docker_manager and skills_directory:
            from ._base import Permission

            skills_path = Path(skills_directory).resolve()
            if skills_path.exists() and skills_path.is_dir():
                self.path_permission_manager.add_path(skills_path, Permission.READ, "skills_read")
                self.local_skills_directory = skills_path

    def recreate_container_for_write_access(
        self,
        skills_directory: str | None = None,
        massgen_skills: list[str] | None = None,
        load_previous_session_skills: bool = False,
        extra_mount_paths: list[tuple] | None = None,
    ) -> None:
        """
        Recreate the Docker container with write access enabled for context paths.

        This is called before final presentation to allow the winning agent's Docker
        container to have write access to context paths. The original container was
        created with read-only mounts for context paths (to prevent race conditions
        during coordination), so we need to recreate it with write-enabled mounts.

        Args:
            skills_directory: Path to skills directory to mount in Docker
            massgen_skills: List of MassGen built-in skills to enable
            load_previous_session_skills: If True, include evolving skills from previous sessions
            extra_mount_paths: Optional list of (host_path, container_path, mode) tuples
                for additional volume mounts (e.g., worktree paths for isolation)

        Note:
            This method preserves the agent's workspace and other state - only the
            Docker container is recreated. The PathPermissionManager must also have
            its context_write_access_enabled set to True separately.
        """
        if not self.docker_manager or not self.agent_id:
            logger.debug(
                "[FilesystemManager] No Docker manager or agent_id - skipping container recreation",
            )
            return

        logger.info(
            f"[FilesystemManager] Recreating Docker container for {self.agent_id} with write access to context paths",
        )

        # Get context paths - these will now be mounted with write access
        # because we'll mark write paths as writable in the config we pass
        context_paths = self.path_permission_manager.get_context_paths()

        # Update context paths to have write permission for those marked will_be_writable
        # This ensures the Docker mount is created with 'rw' mode
        write_enabled_context_paths = []
        for ctx_path in context_paths:
            ctx_path_copy = ctx_path.copy()
            # Check if this path should be writable (will_be_writable flag from ManagedPath)
            for mp in self.path_permission_manager.managed_paths:
                if mp.path_type == "context" and str(mp.path) == ctx_path.get("path"):
                    if mp.will_be_writable:
                        ctx_path_copy["permission"] = "write"
                        logger.info(
                            f"[FilesystemManager] Enabling write access in Docker for: {ctx_path.get('path')}",
                        )
                    break
            write_enabled_context_paths.append(ctx_path_copy)

        # Remove the existing container
        try:
            self.docker_manager.remove_container(self.agent_id, force=True)
            logger.info(f"[FilesystemManager] Removed old container for {self.agent_id}")
        except ValueError:
            # Container doesn't exist - that's fine
            logger.debug(f"[FilesystemManager] No existing container to remove for {self.agent_id}")
        except Exception as e:
            logger.warning(f"[FilesystemManager] Error removing container for {self.agent_id}: {e}")

        # Get session mount config if session manager is initialized
        session_mount = None
        if self.session_mount_manager:
            session_mount = self.session_mount_manager.get_mount_config()

        # Recreate the container with write-enabled context paths and writable skills dir.
        # skills_writable=True mounts the actual project skills dir with rw access instead
        # of creating a read-only temp merged copy, so the agent can persist skill changes.
        docker_skills_dir = self.docker_manager.create_container(
            agent_id=self.agent_id,
            workspace_path=self.cwd,
            temp_workspace_path=self.agent_temporary_workspace_parent if self.agent_temporary_workspace_parent else None,
            context_paths=write_enabled_context_paths,
            session_mount=session_mount,
            skills_directory=skills_directory,
            massgen_skills=massgen_skills,
            shared_tools_directory=self.shared_tools_base,
            load_previous_session_skills=load_previous_session_skills,
            extra_mount_paths=extra_mount_paths,
            skills_writable=True,
        )

        logger.info(
            f"[FilesystemManager] Docker container recreated for {self.agent_id} with write access to context paths",
        )

        # Update Docker skills directory path if it was created
        if docker_skills_dir:
            from ._base import Permission

            # Check if already added (avoid duplicates)
            existing_paths = [str(mp.path) for mp in self.path_permission_manager.managed_paths]
            if str(docker_skills_dir) not in existing_paths:
                self.path_permission_manager.add_path(docker_skills_dir, Permission.READ, "docker_skills")
                logger.info(f"[Docker] Added skills directory to allowed paths: {docker_skills_dir}")

    def setup_local_skills(
        self,
        skills_directory: str | None = None,
        massgen_skills: list[str] | None = None,
        load_previous_session_skills: bool = False,
    ) -> None:
        """
        Setup merged skills directory for local command line execution mode.

        This mirrors Docker mode's skills merging logic, creating a temporary directory
        that combines user's external skills with MassGen's built-in skills.

        Args:
            skills_directory: Path to user's skills directory (e.g., .agent/skills)
            massgen_skills: List of MassGen built-in skills to enable
            load_previous_session_skills: If True, include evolving skills from
                previous sessions in the merged local skills directory.
        """
        import shutil
        import tempfile

        if not (skills_directory or massgen_skills):
            logger.debug("[FilesystemManager] No skills configured for local mode")
            return

        # Create temp directory for merged skills
        temp_skills_dir = Path(tempfile.mkdtemp(prefix="massgen-skills-local-"))
        logger.info(f"[Local] Creating temp merged skills directory: {temp_skills_dir}")

        # Copy skills from home directory (~/.agent/skills/) first - this is where openskills installs
        home_skills_path = Path.home() / ".agent" / "skills"
        if home_skills_path.exists():
            logger.info(f"[Local] Copying home skills from: {home_skills_path}")
            shutil.copytree(home_skills_path, temp_skills_dir, dirs_exist_ok=True)

        # Copy project skills (.agent/skills if it exists) - these override home skills
        if skills_directory:
            skills_path = Path(skills_directory).resolve()
            if skills_path.exists():
                logger.info(f"[Local] Copying project skills from: {skills_path}")
                shutil.copytree(skills_path, temp_skills_dir, dirs_exist_ok=True)
            else:
                logger.debug(f"[Local] Project skills directory does not exist: {skills_path}")

        # Copy massgen built-in skills (flat structure in massgen/skills/)
        massgen_skills_base = Path(__file__).parent.parent / "skills"

        # Track which skills have been added to avoid duplicates
        added_skills = set()

        # If specific skills are requested, copy only those
        if massgen_skills:
            for skill_name in massgen_skills:
                skill_source = massgen_skills_base / skill_name
                if skill_source.exists() and skill_source.is_dir():
                    skill_dest = temp_skills_dir / skill_name
                    logger.info(f"[Local] Adding MassGen skill: {skill_name}")
                    shutil.copytree(skill_source, skill_dest, dirs_exist_ok=True)
                    added_skills.add(skill_name)
                else:
                    logger.warning(f"[Local] MassGen skill not found: {skill_name} at {skill_source}")
        else:
            # If no specific skills requested, copy all built-in skills
            if massgen_skills_base.exists():
                for skill_dir in massgen_skills_base.iterdir():
                    if skill_dir.is_dir() and not skill_dir.name.startswith("."):
                        skill_dest = temp_skills_dir / skill_dir.name
                        logger.info(f"[Local] Adding MassGen skill: {skill_dir.name}")
                        shutil.copytree(skill_dir, skill_dest, dirs_exist_ok=True)
                        added_skills.add(skill_dir.name)

        if load_previous_session_skills:
            from .skills_manager import scan_previous_session_skills

            logs_dir = Path(".massgen/massgen_logs")
            logger.info(f"[Local] load_previous_session_skills enabled, scanning: {logs_dir}")
            prev_skills = scan_previous_session_skills(logs_dir)
            logger.info(f"[Local] Found {len(prev_skills)} previous session skills")

            for skill in prev_skills:
                source_path = skill.get("source_path")
                if not source_path:
                    continue
                source = Path(source_path)
                if not source.exists():
                    continue
                skill_name = str(skill.get("name", "unknown")).strip() or "unknown"
                skill_dest = temp_skills_dir / skill_name
                skill_dest.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, skill_dest / "SKILL.md")
                logger.info(f"[Local] Added previous session skill: {skill_name} from {source}")

        # Store the merged skills directory path
        self.local_skills_directory = temp_skills_dir

        # Add skills directory to allowed paths (read-only)
        from ._base import Permission

        self.path_permission_manager.add_path(temp_skills_dir, Permission.READ, "local_skills")
        logger.info(f"[Local] Added skills directory to allowed paths: {temp_skills_dir}")

        # Scan and enumerate all skills in the merged directory
        from .skills_manager import scan_skills

        all_skills = scan_skills(temp_skills_dir)
        logger.info(f"[Local] Merged skills directory ready at: {temp_skills_dir}")
        logger.info(f"[Local] Total skills loaded: {len(all_skills)}")
        for skill in all_skills:
            title = skill.get("title", skill.get("name", "Unknown"))
            logger.info(f"[Local]   - {skill['name']}: {title}")

    def add_turn_context_path(self, turn_path: Path) -> None:
        """Register a turn workspace as available context.

        When session directory is pre-mounted in Docker, this method registers
        a new turn's workspace path with the permission manager so agents can
        access it. No container restart is needed because the parent session
        directory is already mounted.

        Args:
            turn_path: Path to the turn's workspace directory
        """
        resolved_path = turn_path.resolve()
        self.path_permission_manager.add_path(
            resolved_path,
            Permission.READ,
            f"session_turn_{turn_path.parent.name}",
        )
        logger.info(f"[FilesystemManager] Added turn context path: {resolved_path}")

    def has_session_mount(self) -> bool:
        """Check if session directory is pre-mounted for this filesystem manager.

        Returns:
            True if session mount manager is initialized, False otherwise.
        """
        return self.session_mount_manager is not None

    def setup_massgen_skill_directories(self, massgen_skills: list) -> None:
        """
        Setup workspace directories based on enabled MassGen skills.

        Creates directories only for skills that need them:
        - "file_search": No directory needed

        Note: The old "memory" skill has been removed. Use enable_memory_filesystem_mode
        config option instead for filesystem-based memory.

        When any skill directory is created, also creates workspace/ for main working files.

        Args:
            massgen_skills: List of MassGen skills to enable (e.g., ["file_search"])
        """
        if not massgen_skills:
            logger.debug("[FilesystemManager] No MassGen skills configured, skipping directory setup")
            return

        # Define which skills need directories
        SKILL_DIRECTORIES = {
            # "file_search": no directory needed
            # Note: "memory" skill removed - use enable_memory_filesystem_mode instead
        }

        # Determine which directories to create
        dirs_to_create = []
        for skill in massgen_skills:
            if skill in SKILL_DIRECTORIES:
                dirs_to_create.append(SKILL_DIRECTORIES[skill])

        if not dirs_to_create:
            logger.debug(f"[FilesystemManager] MassGen skills {massgen_skills} don't need directories")
            return

        logger.info(f"[FilesystemManager] Setting up directories for MassGen skills: {massgen_skills}")

        # Create skill directories in current workspace
        for dir_name in dirs_to_create:
            skill_dir = self.cwd / dir_name
            skill_dir.mkdir(exist_ok=True)
            logger.info(f"[FilesystemManager] Created {dir_name}/ directory")

        # Also create workspace/ directory for main working files
        workspace_dir = self.cwd / "workspace"
        workspace_dir.mkdir(exist_ok=True)
        logger.info("[FilesystemManager] Created workspace/ directory")

        # Also create in agent's temporary workspace if it exists
        # This ensures other agents can see the organized structure
        if self.agent_temporary_workspace:
            for dir_name in dirs_to_create:
                temp_dir = self.agent_temporary_workspace / dir_name
                temp_dir.mkdir(exist_ok=True)

            temp_workspace = self.agent_temporary_workspace / "workspace"
            temp_workspace.mkdir(exist_ok=True)

            logger.info(f"[FilesystemManager] Created organized structure in temp workspace: {self.agent_temporary_workspace}")

    def setup_memory_directories(self) -> None:
        """
        Setup memory directories for filesystem-based memory mode.

        Creates memory/short_term/ and memory/long_term/ directories in the workspace.
        Called when enable_memory_filesystem_mode is enabled in coordination config.

        Note: Only creates directories in main workspace (cwd). Temporary workspaces
        will have memory directories from snapshots of other agents' workspaces.
        """
        logger.info("[FilesystemManager] Setting up memory directories for filesystem mode")

        # Create memory directories in current workspace only
        memory_base = self.cwd / "memory"
        memory_base.mkdir(exist_ok=True)

        short_term_dir = memory_base / "short_term"
        short_term_dir.mkdir(exist_ok=True)
        logger.info(f"[FilesystemManager] Created memory/short_term/ directory at {short_term_dir}")

        long_term_dir = memory_base / "long_term"
        long_term_dir.mkdir(exist_ok=True)
        logger.info(f"[FilesystemManager] Created memory/long_term/ directory at {long_term_dir}")

    def restore_memories_from_previous_turn(self, previous_turn_workspace: Path) -> None:
        """
        Restore memory files from a previous turn's workspace.

        This enables memory persistence across turns by copying memory/ directory
        from the previous turn's final workspace into the current workspace.

        Args:
            previous_turn_workspace: Path to previous turn's workspace (e.g., logs/turn_1/final/agent_a/workspace)
        """
        source_memory = previous_turn_workspace / "memory"
        if not source_memory.exists():
            logger.info(f"[FilesystemManager] No memory directory in previous turn workspace: {previous_turn_workspace}")
            return

        dest_memory = self.cwd / "memory"
        dest_memory.mkdir(parents=True, exist_ok=True)

        restored_count = 0
        for tier in ["short_term", "long_term"]:
            source_tier = source_memory / tier
            if not source_tier.exists():
                continue

            dest_tier = dest_memory / tier
            dest_tier.mkdir(parents=True, exist_ok=True)

            # Copy all .md files from previous turn
            for memory_file in source_tier.glob("*.md"):
                try:
                    dest_file = dest_tier / memory_file.name
                    shutil.copy2(memory_file, dest_file)
                    logger.info(f"[FilesystemManager] Restored {tier}/{memory_file.name} from previous turn")
                    restored_count += 1
                except Exception as e:
                    logger.warning(f"[FilesystemManager] Failed to restore {memory_file.name}: {e}")

        logger.info(f"[FilesystemManager] Restored {restored_count} memory files from previous turn")

    def _compute_tools_config_hash(self, servers_with_tools: list[dict[str, Any]]) -> str:
        """Compute hash of tool configuration for shared_tools directory naming.

        Args:
            servers_with_tools: List of server configs with tools

        Returns:
            8-character hex hash of configuration
        """
        import hashlib
        import json

        # Build config dict with all relevant parameters
        config = {
            "servers": sorted([s["name"] for s in servers_with_tools]),  # Server names
            "exclude_custom_tools": sorted(self.exclude_custom_tools),
            "custom_tools_path": str(self.custom_tools_path) if self.custom_tools_path else None,
        }

        # Compute hash
        config_str = json.dumps(config, sort_keys=True)
        hash_obj = hashlib.md5(config_str.encode())
        return hash_obj.hexdigest()[:8]  # First 8 chars

    async def setup_code_based_tools_from_mcp_client(self, mcp_client) -> None:
        """Setup code-based tools by extracting schemas from connected MCP client.

        Connects to MCP servers, extracts tool schemas, and generates Python wrappers.

        Args:
            mcp_client: Connected MCPClient instance with tool schemas
        """
        if not self.enable_code_based_tools:
            return

        if not mcp_client:
            logger.warning("[FilesystemManager] No MCP client provided for code-based tools")
            return

        logger.info("[FilesystemManager] Extracting tool schemas from MCP client")

        # Extract tool schemas organized by server
        servers_with_tools = self._extract_mcp_tool_schemas(mcp_client)

        if not servers_with_tools:
            logger.info("[FilesystemManager] No tools found in MCP client")
            return

        logger.info(f"[FilesystemManager] Extracted {len(servers_with_tools)} server(s) with tools")

        from ._tool_code_writer import ToolCodeWriter

        writer = ToolCodeWriter()

        # Determine where to generate tools
        if self.shared_tools_base:
            # Shared location: create hash-based subdirectory for this config
            config_hash = self._compute_tools_config_hash(servers_with_tools)
            target_path = self.shared_tools_base / config_hash

            # Set the actual shared_tools_directory (with hash)
            self.shared_tools_directory = target_path

            # Check if tools already exist (optimization: skip regeneration)
            tools_already_exist = target_path.exists() and (target_path / "servers").exists() and (target_path / ".mcp").exists()

            if tools_already_exist:
                logger.info(
                    f"[FilesystemManager] Shared tools already exist at {target_path}, skipping regeneration",
                )
            else:
                # Create directory and generate tools
                target_path.mkdir(parents=True, exist_ok=True)
                logger.info(
                    f"[FilesystemManager] Generating code-based tools in shared location: {target_path} (hash: {config_hash})",
                )

                try:
                    # Auto-exclude tools based on missing API keys
                    auto_excluded = []
                    if self.custom_tools_path:
                        auto_excluded = self._get_auto_excluded_tools_by_api_keys(self.custom_tools_path)

                    # Combine manual exclusions with auto-generated ones
                    all_exclusions = list(set(self.exclude_custom_tools + auto_excluded))

                    writer.setup_code_based_tools(
                        workspace_path=target_path,
                        mcp_servers=servers_with_tools,
                        custom_tools_path=self.custom_tools_path,
                        exclude_custom_tools=all_exclusions,
                    )
                    logger.info(f"[FilesystemManager] Code-based tools setup complete in {target_path}")

                except Exception as e:
                    logger.error(f"[FilesystemManager] Error setting up code-based tools: {e}", exc_info=True)
                    raise

            # ALWAYS add to allowed paths for this agent's workspace (creates symlinks)
            # This must happen for every agent, even if tools were already generated
            self._add_shared_tools_to_allowed_paths(target_path)

        else:
            # Per-agent location: generate in workspace (included in snapshots)
            target_path = self.cwd
            logger.info(f"[FilesystemManager] Generating code-based tools in agent workspace: {target_path}")

            try:
                # Auto-exclude tools based on missing API keys
                auto_excluded = []
                if self.custom_tools_path:
                    auto_excluded = self._get_auto_excluded_tools_by_api_keys(self.custom_tools_path)

                # Combine manual exclusions with auto-generated ones
                all_exclusions = list(set(self.exclude_custom_tools + auto_excluded))

                writer.setup_code_based_tools(
                    workspace_path=target_path,
                    mcp_servers=servers_with_tools,
                    custom_tools_path=self.custom_tools_path,
                    exclude_custom_tools=all_exclusions,
                )
                logger.info(f"[FilesystemManager] Code-based tools setup complete in {target_path}")

            except Exception as e:
                logger.error(f"[FilesystemManager] Error setting up code-based tools: {e}", exc_info=True)
                raise

    def _get_auto_excluded_tools_by_api_keys(
        self,
        custom_tools_path: Path,
    ) -> list[str]:
        """Automatically exclude tools based on unavailable API keys.

        Reads TOOL.md files to check requires_api_keys, compares against
        configured Docker credentials to determine which tools to exclude.

        Args:
            custom_tools_path: Path to custom tools directory

        Returns:
            List of tool directory names to exclude
        """
        import yaml

        if not custom_tools_path or not custom_tools_path.exists():
            return []

        # Get list of available API keys
        available_keys = self._get_available_api_keys()

        # If no credential config, assume all env vars available (local mode or pass_all_env)
        if available_keys is None:
            logger.debug("[FilesystemManager] No credential filtering - all API keys assumed available")
            return []

        excluded = []

        # Check each subdirectory for TOOL.md
        for tool_dir in custom_tools_path.iterdir():
            if not tool_dir.is_dir() or tool_dir.name.startswith("."):
                continue

            tool_md = tool_dir / "TOOL.md"
            if not tool_md.exists():
                continue

            try:
                # Parse TOOL.md YAML frontmatter
                content = tool_md.read_text()
                if not content.startswith("---"):
                    continue

                parts = content.split("---", 2)
                if len(parts) < 3:
                    continue

                metadata = yaml.safe_load(parts[1])
                required_keys = metadata.get("requires_api_keys", [])

                # Skip if tool doesn't require any keys
                if not required_keys:
                    continue

                # Check if all required keys are available
                missing_keys = [key for key in required_keys if key not in available_keys]

                if missing_keys:
                    excluded.append(tool_dir.name)
                    logger.info(
                        f"[FilesystemManager] Excluding {tool_dir.name}: " f"missing API keys: {', '.join(missing_keys)}",
                    )

            except Exception as e:
                logger.warning(f"[FilesystemManager] Error reading {tool_md}: {e}")
                continue

        return excluded

    def _get_available_api_keys(self) -> set | None:
        """Get set of API keys that will be available in Docker container.

        Returns:
            Set of available API key names, or None if no filtering needed
        """
        if not self.command_line_docker_credentials:
            # No credentials config - can't filter
            return None

        creds = self.command_line_docker_credentials
        available = set()

        # Check pass_all_env - if true, all keys available
        if creds.get("pass_all_env"):
            return None  # No filtering needed

        # Get keys from env_file
        if creds.get("env_file"):
            env_file_path = Path(creds["env_file"]).expanduser().resolve()
            if env_file_path.exists():
                # Parse .env file
                with open(env_file_path) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key = line.split("=", 1)[0].strip()
                            # Check if filtering by env_vars_from_file
                            filter_list = creds.get("env_vars_from_file")
                            if filter_list:
                                if key in filter_list:
                                    available.add(key)
                            else:
                                # All keys from env file
                                available.add(key)

        # Add keys from env_vars (host environment)
        if creds.get("env_vars"):
            for var in creds["env_vars"]:
                if var in os.environ:
                    available.add(var)

        return available

    def _extract_mcp_tool_schemas(self, mcp_client) -> list[dict[str, Any]]:
        """Extract tool schemas from MCP client, organized by server.

        Only extracts user-added MCP servers. Framework MCPs (defined in FRAMEWORK_MCPS
        constant) are excluded as they're handled separately.

        Args:
            mcp_client: MCPClient instance with connected tools

        Returns:
            List of server configs with tool schemas:
            [
                {
                    "name": "weather",
                    "type": "stdio",
                    "command": "npx",
                    "args": [...],
                    "tools": [
                        {
                            "name": "get_forecast",
                            "description": "Get weather forecast",
                            "inputSchema": {...}
                        },
                        ...
                    ]
                },
                ...
            ]
        """
        servers_with_tools = {}

        # Group tools by server
        for tool_name, tool_obj in mcp_client.tools.items():
            # Get server name for this tool
            server_name = mcp_client._tool_to_server.get(tool_name)
            if not server_name:
                logger.warning(f"[FilesystemManager] Tool {tool_name} has no associated server")
                continue

            # Skip framework MCPs - they're not user tools
            # Check exact match or prefix match (e.g., "planning_agent_a" matches "planning")
            is_framework_mcp = server_name in FRAMEWORK_MCPS or any(server_name.startswith(f"{fmcp}_") for fmcp in FRAMEWORK_MCPS)
            if is_framework_mcp:
                logger.debug(f"[FilesystemManager] Skipping framework MCP: {server_name}")
                continue

            # Skip direct MCP servers - they remain as protocol tools, not code-based
            is_direct_mcp = server_name in (self.direct_mcp_servers or [])
            if is_direct_mcp:
                logger.debug(f"[FilesystemManager] Skipping direct MCP (kept as protocol tool): {server_name}")
                continue

            # Initialize server entry if needed
            if server_name not in servers_with_tools:
                # Find server config
                server_config = next(
                    (cfg for cfg in mcp_client._server_configs if cfg["name"] == server_name),
                    None,
                )
                if not server_config:
                    logger.warning(f"[FilesystemManager] No config found for server {server_name}")
                    continue

                servers_with_tools[server_name] = {
                    "name": server_name,
                    "type": server_config.get("type"),
                    "command": server_config.get("command"),
                    "args": server_config.get("args"),
                    "env": server_config.get("env", {}),
                    "url": server_config.get("url"),
                    "tools": [],
                }

            # Extract tool schema (remove mcp__ prefix from name)
            original_tool_name = tool_name
            if tool_name.startswith(f"mcp__{server_name}__"):
                original_tool_name = tool_name[len(f"mcp__{server_name}__") :]

            tool_schema = {
                "name": original_tool_name,
                "description": tool_obj.description or f"{original_tool_name} from {server_name}",
                "inputSchema": tool_obj.inputSchema or {},
            }

            servers_with_tools[server_name]["tools"].append(tool_schema)

        # Convert to list
        result = list(servers_with_tools.values())

        # Log summary
        for server in result:
            logger.info(f"[FilesystemManager] Server '{server['name']}': {len(server['tools'])} tools")

        return result

    def _add_shared_tools_to_allowed_paths(self, shared_tools_path: Path) -> None:
        """Add shared tools directory to allowed paths as read-only.

        Makes shared code-based tools (servers/, custom_tools/, .mcp/) accessible
        to the agent without write permissions. Creates symlinks in workspace for
        Python imports to work correctly.

        Args:
            shared_tools_path: Path to shared tools directory
        """
        # Add shared tools directory to path manager (read-only)
        self.path_permission_manager.add_path(
            shared_tools_path,
            Permission.READ,
            "shared_tools",
        )
        logger.info(f"[FilesystemManager] Added shared tools directory to read-only paths: {shared_tools_path}")

        # Create symlinks in workspace for Python imports
        # This allows agents to import from servers/, custom_tools/ as if they were local
        workspace = self.cwd

        # Directories to symlink (utils/ NOT included - agents create that in their workspace)
        tool_dirs = ["servers", "custom_tools", ".mcp", "massgen"]

        for dir_name in tool_dirs:
            source_dir = shared_tools_path / dir_name
            target_link = workspace / dir_name

            # Only create symlink if source exists and target doesn't
            if source_dir.exists() and not target_link.exists():
                try:
                    target_link.symlink_to(source_dir, target_is_directory=True)
                    logger.info(f"[FilesystemManager] Created symlink: {target_link} -> {source_dir}")
                except Exception as e:
                    logger.warning(f"[FilesystemManager] Failed to create symlink for {dir_name}: {e}")

    def update_backend_mcp_config(self, backend_config: dict[str, Any]) -> dict[str, Any]:
        """
        Update MCP server configuration with agent_id and skills directory after they're available.

        This should be called by the backend after setup_orchestration_paths() sets agent_id
        and local_skills_directory.

        Args:
            backend_config: Backend configuration dict containing mcp_servers

        Returns:
            Updated backend configuration
        """
        if not self.enable_mcp_command_line:
            return backend_config

        if not self.agent_id:
            logger.warning("[FilesystemManager] agent_id not set, cannot update MCP config")
            return backend_config

        # Update command_line MCP server config
        mcp_servers = backend_config.get("mcp_servers", [])

        # Handle both list format and Claude Code dict format
        if isinstance(mcp_servers, dict):
            # Claude Code dict format: {"command_line": {...}, "filesystem": {...}}
            if "command_line" in mcp_servers:
                server = mcp_servers["command_line"]
                args = server.get("args", [])

                # For Docker mode: add agent-id and instance-id
                if self.command_line_execution_mode == "docker":
                    if "--agent-id" not in args:
                        args.extend(["--agent-id", self.agent_id])
                        logger.info(f"[FilesystemManager] Updated command_line MCP server config with agent_id: {self.agent_id}")
                    if self.instance_id and "--instance-id" not in args:
                        args.extend(["--instance-id", self.instance_id])
                        logger.info(f"[FilesystemManager] Updated command_line MCP server config with instance_id: {self.instance_id}")

                # For local mode: add local-skills-directory if set
                if self.command_line_execution_mode == "local" and self.local_skills_directory:
                    if "--local-skills-directory" not in args:
                        args.extend(["--local-skills-directory", str(self.local_skills_directory)])
                        logger.info(f"[FilesystemManager] Updated command_line MCP server config with local_skills_directory: {self.local_skills_directory}")

                server["args"] = args

        elif isinstance(mcp_servers, list):
            # List format: [{"name": "command_line", ...}, ...]
            for server in mcp_servers:
                if isinstance(server, dict) and server.get("name") == "command_line":
                    args = server.get("args", [])

                    # For Docker mode: add agent-id and instance-id
                    if self.command_line_execution_mode == "docker":
                        if "--agent-id" not in args:
                            args.extend(["--agent-id", self.agent_id])
                            logger.info(f"[FilesystemManager] Updated command_line MCP server config with agent_id: {self.agent_id}")
                        if self.instance_id and "--instance-id" not in args:
                            args.extend(["--instance-id", self.instance_id])
                            logger.info(f"[FilesystemManager] Updated command_line MCP server config with instance_id: {self.instance_id}")

                    # For local mode: add local-skills-directory if set
                    if self.command_line_execution_mode == "local" and self.local_skills_directory:
                        if "--local-skills-directory" not in args:
                            args.extend(["--local-skills-directory", str(self.local_skills_directory)])
                            logger.info(f"[FilesystemManager] Updated command_line MCP server config with local_skills_directory: {self.local_skills_directory}")

                    server["args"] = args
                    break

        return backend_config

    def _setup_workspace(self, cwd: str, init_two_tier: bool = False) -> Path:
        """Setup workspace directory, creating if needed and clearing existing files safely.

        Args:
            cwd: Working directory path
            init_two_tier: If True, create scratch/ and deliverable/ subdirectories and init git.
                          Only used for main workspace, not temp workspaces.
        """
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
                    # Symlinks must be unlinked directly - rmtree fails on symlinks to directories
                    item.unlink()
                elif item.is_file():
                    item.unlink()
                elif item.is_dir():
                    _safe_rmtree(item)

        # Setup two-tier workspace structure if enabled
        if init_two_tier and self.use_two_tier_workspace:
            self._setup_two_tier_structure(workspace)

        return workspace

    def _setup_two_tier_structure(self, workspace: Path) -> None:
        """Setup scratch/ and deliverable/ directories and initialize git.

        Args:
            workspace: The workspace root path
        """
        # Create tier directories
        scratch_dir = workspace / "scratch"
        deliverable_dir = workspace / "deliverable"

        scratch_dir.mkdir(exist_ok=True)
        deliverable_dir.mkdir(exist_ok=True)

        logger.info(f"[FilesystemManager] Created two-tier workspace: scratch/ and deliverable/ in {workspace}")

        # Initialize git repository
        self._init_git_repo(workspace)

    def _init_git_repo(self, workspace: Path) -> None:
        """Initialize a git repository in the workspace for version tracking.

        Args:
            workspace: The workspace root path
        """
        import subprocess

        from ._constants import PATTERNS_TO_IGNORE_FOR_TRACKING

        try:
            # Initialize git repo
            subprocess.run(
                ["git", "init"],
                cwd=workspace,
                capture_output=True,
                check=True,
            )

            # After init, set up environment to isolate from parent repos
            git_dir = workspace / ".git"
            git_env = {**os.environ, "GIT_DIR": str(git_dir), "GIT_WORK_TREE": str(workspace)}

            # Configure git user identity using agent_id if available
            agent_name = self.agent_id if self.agent_id else "massgen-agent"
            subprocess.run(
                ["git", "config", "user.name", agent_name],
                cwd=workspace,
                capture_output=True,
                check=True,
                env=git_env,
            )
            subprocess.run(
                ["git", "config", "user.email", f"{agent_name}@massgen.local"],
                cwd=workspace,
                capture_output=True,
                check=True,
                env=git_env,
            )

            # Create .gitignore from centralized patterns
            gitignore_path = workspace / ".gitignore"
            gitignore_content = "\n".join(PATTERNS_TO_IGNORE_FOR_TRACKING) + "\n"
            gitignore_path.write_text(gitignore_content)

            # Make initial commit with --no-verify to skip any inherited hooks
            subprocess.run(
                ["git", "add", "-A"],
                cwd=workspace,
                capture_output=True,
                check=True,
                env=git_env,
            )
            subprocess.run(
                ["git", "commit", "--no-verify", "-m", f"[INIT] Workspace initialized for {agent_name}"],
                cwd=workspace,
                capture_output=True,
                check=True,
                env=git_env,
            )

            logger.info(f"[FilesystemManager] Initialized git repository in {workspace}")

        except subprocess.CalledProcessError as e:
            logger.warning(f"[FilesystemManager] Failed to initialize git repo: {e.stderr.decode() if e.stderr else e}")
        except FileNotFoundError:
            logger.warning("[FilesystemManager] Git not found - skipping git initialization")

    def _git_commit_if_changed(self, workspace: Path, message: str) -> bool:
        """Commit any uncommitted changes in the workspace.

        Args:
            workspace: The workspace root path
            message: Commit message (should use semantic prefixes like [SNAPSHOT], [ANSWER], etc.)

        Returns:
            True if a commit was made, False otherwise
        """
        # Delegate to standalone function for single source of truth
        return git_commit_if_changed(workspace, message)

    def get_mcp_filesystem_config(
        self,
        include_only_write_tools: bool = False,
        use_mcpwrapped: bool = False,
        use_no_roots_wrapper: bool = False,
    ) -> dict[str, Any]:
        """
        Generate MCP filesystem server configuration.

        Args:
            include_only_write_tools: If True, only include write_file and edit_file tools.
                                     Used with code-based tools to provide clean file creation
                                     without shell escaping issues, while using command-line
                                     for other file operations.
            use_mcpwrapped: If True, wrap the server with mcpwrapped to filter tools at the
                           MCP protocol level. This hides tools from Claude's context entirely.
                           Required for Claude Code backend since it doesn't support allowed_tools
                           for MCP tools. See: https://github.com/anthropics/claude-code/issues/7328
                           Uses: https://github.com/VitoLin/mcpwrapped
            use_no_roots_wrapper: If True, wrap the server with our no-roots wrapper that
                                  intercepts and removes the MCP roots protocol. This prevents
                                  clients (like Claude Code SDK) from overriding our command-line
                                  paths with their own roots. Required for Claude Code backend.

        Returns:
            Dictionary with MCP server configuration for filesystem access
        """
        # Get all managed paths
        paths = self.path_permission_manager.get_mcp_filesystem_paths()
        logger.debug(f"[FilesystemManager.get_mcp_filesystem_config] MCP filesystem paths for agent: {paths}")

        # Check if we should use globally installed package (Docker) vs npx (local)
        # In Docker, we pre-install with the zod-to-json-schema fix
        import shutil

        use_global = shutil.which("mcp-server-filesystem") is not None

        # Build base MCP server configuration
        if use_global:
            base_command = "mcp-server-filesystem"
            base_args = paths
        else:
            base_command = "npx"
            base_args = ["-y", "@modelcontextprotocol/server-filesystem"] + paths

        # When filtering tools and using mcpwrapped, wrap the command
        if include_only_write_tools and use_mcpwrapped:
            # Use mcpwrapped to filter tools at the MCP protocol level
            # This prevents filtered tools from appearing in Claude's context
            # See: https://github.com/VitoLin/mcpwrapped
            # We use npx to auto-download if not installed (like we do for server-filesystem)
            visible_tools = "write_file,edit_file"
            config = {
                "name": "filesystem",
                "type": "stdio",
                "command": "npx",
                "args": ["-y", "mcpwrapped@1.0.4", f"--visible_tools={visible_tools}", base_command] + base_args,
                "cwd": str(self.cwd),
            }
            logger.info(
                f"[FilesystemManager] Using mcpwrapped (via npx) to filter filesystem tools to: {visible_tools}",
            )
        else:
            # Standard configuration without mcpwrapped
            # Note: ALLOWED_PATHS env var is NOT supported by @modelcontextprotocol/server-filesystem
            # (it's only a proposal: https://github.com/modelcontextprotocol/servers/issues/1879)
            # Paths MUST be passed as command-line args

            # Use no-roots wrapper to prevent MCP roots protocol from overriding our paths
            # The MCP filesystem server supports "roots" protocol where client-provided roots
            # completely replace command-line args. Claude Code SDK uses this, which breaks our
            # multi-path setup (workspace + temp_workspaces). The wrapper intercepts and removes
            # roots capability, forcing the server to use our command-line args.
            if use_no_roots_wrapper:
                wrapper_path = Path(__file__).parent.parent / "mcp_tools" / "filesystem_no_roots.py"
                config = {
                    "name": "filesystem",
                    "type": "stdio",
                    "command": "python3",
                    "args": [str(wrapper_path)] + paths,
                    "cwd": str(self.cwd),
                }
                logger.info(f"[FilesystemManager] Using no-roots wrapper for filesystem: {paths}")
            else:
                config = {
                    "name": "filesystem",
                    "type": "stdio",
                    "command": base_command,
                    "args": base_args,  # base_args includes the paths
                    "cwd": str(self.cwd),
                }
                logger.info(f"[FilesystemManager] MCP filesystem config: {paths}")

            if include_only_write_tools:
                # Code-based tools mode: Only include write_file and edit_file
                # Note: This sets allowed_tools in config, but Claude Code SDK doesn't respect it
                # for MCP tools. Use use_mcpwrapped=True for Claude Code backend.
                config["allowed_tools"] = ["write_file", "edit_file"]
            else:
                # Normal mode: Exclude read_media_file since we have our own implementation
                config["exclude_tools"] = ["read_media_file"]

        # Defense in depth: OS-sandbox the filesystem (write_file/edit_file) server
        # too. Self-skips npx/npm launchers (they need registry + ~/.npm writes the
        # sandbox blocks) — those keep the npm server's own --allowed-paths + the hook.
        if self.command_line_execution_mode == "srt" and self.srt_manager:
            config = self._wrap_stdio_config_with_srt(config)

        return config

    def get_workspace_tools_mcp_config(self, backend_type: str | None = None) -> dict[str, Any]:
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

        # Pass allowed paths
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

        # Conditionally exclude file operation tools if flag is set
        if self.exclude_file_operation_mcps:
            config["exclude_tools"] = [
                "copy_file",
                "copy_files_batch",
                "delete_file",
                "delete_files_batch",
                "compare_directories",
                "compare_files",
            ]

        # Conditionally exclude image generation tools if not enabled
        if not self.enable_image_generation:
            if "exclude_tools" not in config:
                config["exclude_tools"] = []
            config["exclude_tools"].extend(
                [
                    "generate_and_store_image_with_input_images",
                    "generate_and_store_image_no_input_images",
                ],
            )
        if not self.enable_audio_generation:
            if "exclude_tools" not in config:
                config["exclude_tools"] = []
            config["exclude_tools"].extend(
                [
                    "generate_and_store_audio_with_input_audios",
                    "generate_and_store_audio_no_input_audios",
                ],
            )

        # Defense in depth: OS-sandbox the filesystem-tools SERVER itself so a
        # flawed/injected/permission-hook-bypassing file op is OS-denied, not just
        # app-denied. (Command execution is already OS-sandboxed by the command_line
        # srt mode; this closes the same hole for the file-manipulation MCP tools.)
        if self.command_line_execution_mode == "srt" and self.srt_manager:
            config = self._wrap_stdio_config_with_srt(config)

        return config

    def _wrap_stdio_config_with_srt(self, config: dict[str, Any]) -> dict[str, Any]:
        """Wrap a stdio MCP server launch with `srt` using the fs_tools profile.

        Transforms ``{command: "fastmcp", args: ["run", srv, "--", "--allowed-paths", …]}``
        into ``{command: "srt", args: ["--settings", <cfg>, "sh", "-c", "<orig cmdline>"]}``.

        CRITICAL: the original command line (including its ``--`` option separator)
        is passed via ``sh -c`` so that `srt`'s own argv parser cannot consume the
        ``--`` (which would strip the server's ``--allowed-paths`` and crash it).
        Verified: the direct-argv form breaks the MCP handshake; the sh -c form works.
        """
        import shlex

        # Skip launchers that need network + cache writes at STARTUP. `npx`/`npm`
        # fetch the package from registry.npmjs.org and write to ~/.npm/_cacache —
        # both blocked by the tight sandbox (E403 / EPERM), so wrapping them crashes
        # the server. Also skip the no-roots filesystem wrapper, which is launched as
        # `python3 filesystem_no_roots.py …` but INTERNALLY spawns `npx …` (so it has
        # the same network/cache need). These servers keep their app-layer protections
        # (each server's own --allowed-paths + PathPermissionManager). For full OS-level
        # coverage, install the server as a global binary (no npx).
        command = config.get("command", "")
        args = config.get("args", [])
        # Token-based detection (not a fragile substring): any whole token == npx/npm,
        # or the launched script is the npx-spawning no-roots wrapper.
        tokens = [str(command), *[str(a) for a in args]]
        needs_network = any(t in ("npx", "npm") or t.endswith("/npx") or t.endswith("/npm") or "filesystem_no_roots" in t for t in tokens)
        if needs_network:
            logger.info(
                f"[SrtManager] Not srt-wrapping network-dependent MCP launcher "
                f"('{command}' …); it keeps its app-layer permission enforcement. "
                "Install the server as a global binary for OS-level sandboxing.",
            )
            return config

        extra_writable = []
        if self.snapshot_storage:
            extra_writable.append(self.snapshot_storage)
        if self.agent_temporary_workspace_parent:
            extra_writable.append(self.agent_temporary_workspace_parent)
        self.srt_manager.fs_tools_extra_writable = [Path(p).resolve() for p in extra_writable]

        fs_settings = self.srt_manager.write_settings_file(profile="fs_tools", agent_id=self.agent_id)
        inner_cmdline = shlex.join([str(config["command"]), *[str(a) for a in config["args"]]])
        config["command"] = self.srt_manager.srt_path
        config["args"] = ["--settings", str(fs_settings), "sh", "-c", inner_cmdline]
        return config

    def get_command_line_mcp_config(self) -> dict[str, Any]:
        """
        Generate command line execution MCP server configuration.

        Returns:
            Dictionary with MCP server configuration for command execution
            (supports bash on Unix/Mac, cmd/PowerShell on Windows, and Docker isolation)
        """
        # Get absolute path to the code execution server script
        script_path = Path(ce_module.__file__).resolve()

        # Pass allowed paths
        paths = self.path_permission_manager.get_mcp_filesystem_paths()

        env = {
            "FASTMCP_SHOW_CLI_BANNER": "false",
        }

        # Pass DOCKER_HOST environment variable if present
        if "DOCKER_HOST" in os.environ:
            env["DOCKER_HOST"] = os.environ["DOCKER_HOST"]

        # Note: PYTHONPATH not needed - workspace is already cwd and has symlinks to shared_tools
        # Python imports work: `from servers.weather import get_weather`

        config = {
            "name": "command_line",
            "type": "stdio",
            "command": "fastmcp",
            "args": ["run", f"{script_path}:create_server", "--", "--allowed-paths"] + paths,
            "env": env,
            "cwd": str(self.cwd),
        }

        # Add execution mode
        config["args"].extend(["--execution-mode", self.command_line_execution_mode])

        # Add agent ID for Docker mode
        if self.command_line_execution_mode == "docker" and self.agent_id:
            config["args"].extend(["--agent-id", self.agent_id])

        # Add instance ID for Docker parallel execution
        if self.command_line_execution_mode == "docker" and self.instance_id:
            config["args"].extend(["--instance-id", self.instance_id])

        # Add sudo flag for Docker mode
        if self.command_line_execution_mode == "docker" and self.command_line_docker_enable_sudo:
            config["args"].append("--enable-sudo")

        # SRT mode: generate the per-agent settings file (derived from the SAME
        # PathPermissionManager policy as the app layer) and point the server at it.
        if self.command_line_execution_mode == "srt" and self.srt_manager:
            settings_path = self.srt_manager.write_settings_file(profile="execution", agent_id=self.agent_id)
            config["args"].extend(["--srt-settings", str(settings_path)])

        # Add command filters if specified
        if self.command_line_allowed_commands:
            config["args"].extend(["--allowed-commands"] + self.command_line_allowed_commands)

        if self.command_line_blocked_commands:
            config["args"].extend(["--blocked-commands"] + self.command_line_blocked_commands)

        # Note: --local-skills-directory is added later in update_backend_mcp_config()
        # after setup_orchestration_paths() sets self.local_skills_directory

        return config

    def inject_filesystem_mcp(self, backend_config: dict[str, Any]) -> dict[str, Any]:
        """
        Inject filesystem and workspace tools MCP servers into backend configuration.

        When exclude_file_operation_mcps is True, skips filesystem and workspace file operation
        tools, keeping only command execution, media generation, and planning MCPs.

        When enable_code_based_tools is True, filters out user MCP servers (they're accessible
        via generated Python code instead), keeping only framework MCPs.

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

        # Note: We do NOT filter user MCP servers here when code-based tools are enabled
        # The servers need to connect so we can extract their tool schemas for code generation
        # Tool filtering happens later in the backend after conversion to Function objects

        # Validate direct_mcp_servers - warn if any aren't in configured mcp_servers
        if self.direct_mcp_servers:
            configured_server_names = set(existing_names)
            for direct_server in self.direct_mcp_servers:
                if direct_server not in configured_server_names:
                    logger.warning(
                        f"[FilesystemManager] direct_mcp_servers contains '{direct_server}' " f"but no MCP server with that name is configured in mcp_servers",
                    )

        try:
            # Add filesystem server if missing
            if "filesystem" not in existing_names:
                # When exclude_file_operation_mcps is True, only include write_file and edit_file
                # This provides clean file creation without shell escaping issues
                mcp_servers.append(
                    self.get_mcp_filesystem_config(
                        include_only_write_tools=self.exclude_file_operation_mcps,
                        use_mcpwrapped=self.use_mcpwrapped_for_tool_filtering,
                        use_no_roots_wrapper=self.use_no_roots_wrapper,
                    ),
                )
                if self.exclude_file_operation_mcps:
                    wrapper_note = " (using mcpwrapped)" if self.use_mcpwrapped_for_tool_filtering else ""
                    logger.info(f"[FilesystemManager.inject_filesystem_mcp] Added filesystem MCP with write_file and edit_file only{wrapper_note}")
            else:
                logger.warning("[FilesystemManager.inject_filesystem_mcp] Custom filesystem MCP server already present")

            # Add workspace tools server based on configuration
            if "workspace_tools" not in existing_names:
                # If file ops excluded, only add workspace_tools if media generation is enabled
                if self.exclude_file_operation_mcps:
                    if self.enable_image_generation or self.enable_audio_generation:
                        mcp_servers.append(self.get_workspace_tools_mcp_config(backend_type=backend_config.get("type")))
                        logger.info("[FilesystemManager.inject_filesystem_mcp] Added workspace_tools MCP with media tools only (exclude_file_operation_mcps=True)")
                    else:
                        logger.info("[FilesystemManager.inject_filesystem_mcp] Skipping workspace_tools MCP entirely (exclude_file_operation_mcps=True, no media enabled)")
                else:
                    # Normal case - add all workspace tools
                    mcp_servers.append(self.get_workspace_tools_mcp_config(backend_type=backend_config.get("type")))
            else:
                logger.warning("[FilesystemManager.inject_filesystem_mcp] Custom workspace_tools MCP server already present")

            # Add command line server if enabled and missing
            if self.enable_mcp_command_line and "command_line" not in existing_names:
                mcp_servers.append(self.get_command_line_mcp_config())
            elif self.enable_mcp_command_line:
                logger.warning("[FilesystemManager.inject_filesystem_mcp] Custom command_line MCP server already present")

        except Exception as e:
            logger.warning(f"[FilesystemManager.inject_filesystem_mcp] Error checking existing MCP servers: {e}")

        # Update backend config
        backend_config["mcp_servers"] = mcp_servers

        # Log the final MCP server configs for debugging
        for server in mcp_servers:
            if isinstance(server, dict):
                server_name = server.get("name", "unknown")
                server_args = server.get("args", [])
                logger.debug(f"[FilesystemManager.inject_filesystem_mcp] Server '{server_name}' args: {server_args}")

        return backend_config

    def inject_command_line_mcp(self, backend_config: dict[str, Any]) -> dict[str, Any]:
        """
        Inject only the command_line MCP server into backend configuration.

        Used for NATIVE backends (like Claude Code) that have built-in filesystem tools
        but need the execute_command MCP tool when using docker mode for code execution.

        Args:
            backend_config: Original backend configuration

        Returns:
            Modified configuration with command_line MCP server added
        """
        # Get existing mcp_servers configuration
        mcp_servers = backend_config.get("mcp_servers", [])

        # Handle both list format and Claude Code dict format
        if isinstance(mcp_servers, dict):
            # Claude Code format: {"playwright": {...}, "command_line": {...}}
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
            # Add command line server if missing (only called for docker mode)
            if "command_line" not in existing_names:
                mcp_servers.append(self.get_command_line_mcp_config())
                logger.info("[FilesystemManager.inject_command_line_mcp] Added command_line MCP server for docker mode")
            else:
                logger.warning("[FilesystemManager.inject_command_line_mcp] Custom command_line MCP server already present")

        except Exception as e:
            logger.warning(f"[FilesystemManager.inject_command_line_mcp] Error adding command_line MCP server: {e}")

        # Update backend config
        backend_config["mcp_servers"] = mcp_servers

        return backend_config

    def get_pre_tool_hooks(self) -> dict[str, list]:
        """
        Get pre-tool hooks configuration for MCP clients.

        Returns:
            Dict mapping hook types to lists of hook functions
        """

        async def mcp_hook_wrapper(tool_name: str, tool_args: dict[str, Any]) -> bool:
            """Wrapper to adapt our hook signature to MCP client expectations."""
            allowed, reason = await self.path_permission_manager.pre_tool_use_hook(tool_name, tool_args)
            if not allowed and reason:
                logger.warning(f"[FilesystemManager] Tool blocked: {tool_name} - {reason}")
            return allowed

        return {HookType.PRE_TOOL_USE: [mcp_hook_wrapper]}

    def get_claude_code_hooks_config(self) -> dict[str, Any]:
        """
        Get Claude Agent SDK hooks configuration.

        Returns:
            Hooks configuration dict for ClaudeAgentOptions
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

    async def save_snapshot(self, timestamp: str | None = None, is_final: bool = False, preserve_existing_snapshot: bool = False) -> None:
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

        # Auto-commit any changes before taking snapshot (if git is enabled)
        if self.use_two_tier_workspace:
            commit_prefix = "[FINAL]" if is_final else "[SNAPSHOT]"
            self._git_commit_if_changed(self.cwd, f"{commit_prefix} Auto-commit before snapshot")

        # Use current workspace as source
        source_path = Path(self.cwd)

        if not source_path.exists() or not source_path.is_dir():
            logger.warning(f"[FilesystemManager] Source path invalid - exists: {source_path.exists()}, " f"is_dir: {source_path.is_dir() if source_path.exists() else False}")
            return

        workspace_has_content = has_meaningful_content(source_path)

        # Check if snapshot_storage already has content (used for preservation logic)
        snapshot_storage_has_content = has_meaningful_content(self.snapshot_storage)

        use_snapshot_storage_for_logs = not workspace_has_content and snapshot_storage_has_content
        source_for_logs = self.snapshot_storage if use_snapshot_storage_for_logs else source_path

        if not workspace_has_content and not snapshot_storage_has_content:
            logger.warning(f"[FilesystemManager.save_snapshot] Source path {source_for_logs} is empty, skipping snapshot")
            return

        if use_snapshot_storage_for_logs:
            logger.info(f"[FilesystemManager.save_snapshot] Workspace is empty but snapshot_storage has content, using snapshot_storage as source for logs: {self.snapshot_storage}")

        try:
            # --- 1. Save to snapshot_storage ---
            if self.snapshot_storage:
                if preserve_existing_snapshot and snapshot_storage_has_content:
                    # Interrupted save: never overwrite a submitted answer's snapshot
                    logger.info(f"[FilesystemManager] Preserving existing snapshot during interrupted save ({self.snapshot_storage})")
                elif not workspace_has_content and snapshot_storage_has_content:
                    logger.info(f"[FilesystemManager] Skipping snapshot_storage update - workspace is empty but snapshot_storage has content ({self.snapshot_storage})")
                else:
                    # Normal case: publish the current workspace as a new
                    # IMMUTABLE snapshot version and atomically repoint
                    # <base>/<agent_id> at it. A peer copying the previous version
                    # keeps a consistent, never-deleted-underneath view -- this is
                    # the B1 race fix (see SnapshotVersionStore). The old in-place
                    # rmtree+rebuild raced the offloaded peer-context copytree.
                    items_copied = {"n": 0}

                    def _populate_snapshot_version(version_dir: Path) -> None:
                        for item in source_path.iterdir():
                            if item.is_symlink():
                                logger.debug(f"[FilesystemManager.save_snapshot] Skipping symlink: {item}")
                                continue
                            if item.is_file():
                                shutil.copy2(item, version_dir / item.name)
                            elif item.is_dir():
                                # Use symlinks=True to copy symlinks as symlinks, not follow them
                                # Use ignore_dangling_symlinks=True to handle broken symlinks in subdirectories (e.g., from subagent workspaces)
                                shutil.copytree(
                                    item,
                                    version_dir / item.name,
                                    symlinks=True,
                                    ignore_dangling_symlinks=True,
                                )
                            items_copied["n"] += 1

                    # Key on the snapshot_storage basename (== agent_id in
                    # production, where snapshot_storage is <base>/<agent_id>) so
                    # the published symlink lands exactly at self.snapshot_storage.
                    store = SnapshotVersionStore.for_base(self.snapshot_storage.parent)
                    store.publish_version(self.snapshot_storage.name, _populate_snapshot_version)

                    logger.info(f"[FilesystemManager] Saved snapshot with {items_copied['n']} items to {self.snapshot_storage}")

            # --- 2. Save to log directories ---
            log_session_dir = get_log_session_dir()
            if log_session_dir and self.agent_id:
                if is_final:
                    dest_dir = log_session_dir / "final" / self.agent_id / "workspace"
                    if dest_dir.exists():
                        _safe_rmtree(dest_dir)
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    logger.info(f"[FilesystemManager.save_snapshot] Final log snapshot dest_dir: {dest_dir}")
                else:
                    if not timestamp:
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                    dest_dir = log_session_dir / self.agent_id / timestamp / "workspace"
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    logger.info(f"[FilesystemManager.save_snapshot] Regular log snapshot dest_dir: {dest_dir}")

                items_copied = 0
                for item in source_for_logs.iterdir():
                    if item.is_symlink():
                        logger.debug(f"[FilesystemManager.save_snapshot] Skipping symlink: {item}")
                        continue
                    if item.is_file():
                        shutil.copy2(item, dest_dir / item.name)
                    elif item.is_dir():
                        # Use symlinks=True to copy symlinks as symlinks, not follow them
                        # Use ignore_dangling_symlinks=True to handle broken symlinks in subdirectories (e.g., from subagent workspaces)
                        shutil.copytree(
                            item,
                            dest_dir / item.name,
                            dirs_exist_ok=True,
                            symlinks=True,
                            ignore_dangling_symlinks=True,
                        )
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
                    logger.debug(f"[FilesystemManager] Skipping symlink during clear: {item}")
                    continue
                # Preserve .git directory to maintain commit history across turns
                if item.name == ".git":
                    logger.debug(f"[FilesystemManager] Preserving .git directory during clear: {item}")
                    continue
                # Preserve .massgen directory — it holds subagent MCP config
                # files written at session start that must survive across rounds.
                if item.name == ".massgen":
                    logger.debug(f"[FilesystemManager] Preserving .massgen directory during clear: {item}")
                    continue
                # Preserve memory directory — short_term and long_term memories
                # must accumulate across rounds (trace analysis, learnings, etc.).
                if item.name == "memory":
                    logger.debug(f"[FilesystemManager] Preserving memory directory during clear: {item}")
                    continue
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    _safe_rmtree(item)

            logger.info("[FilesystemManager] Workspace cleared successfully, ready for new agent execution")

        except Exception as e:
            logger.error(f"[FilesystemManager] Failed to clear workspace: {e}")
            # Don't raise - agent can still work with non-empty workspace

    def restore_from_snapshot_storage(self) -> None:
        """Restore workspace from snapshot_storage (used before post-evaluation).

        After save_snapshot clears the workspace, this restores files from
        snapshot_storage back into the live workspace so the post-evaluator
        can see them.
        """
        if not self.snapshot_storage or not self.snapshot_storage.exists():
            logger.info("[FilesystemManager] No snapshot_storage to restore from")
            return

        workspace_path = self.get_current_workspace()
        if not workspace_path or not workspace_path.exists():
            logger.warning("[FilesystemManager] No workspace to restore into")
            return

        items_restored = 0
        for item in self.snapshot_storage.iterdir():
            if item.is_symlink():
                continue
            dest = workspace_path / item.name
            if dest.exists():
                continue  # Don't overwrite existing files
            try:
                if item.is_file():
                    shutil.copy2(item, dest)
                    items_restored += 1
                elif item.is_dir():
                    shutil.copytree(item, dest, symlinks=True, ignore_dangling_symlinks=True)
                    items_restored += 1
            except Exception as e:
                logger.warning(f"[FilesystemManager] Failed to restore {item.name}: {e}")

        logger.info(f"[FilesystemManager] Restored {items_restored} items from snapshot_storage to workspace")

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

            shutil.rmtree(self.agent_temporary_workspace_parent)
            self.agent_temporary_workspace_parent.mkdir(parents=True, exist_ok=True)

            logger.info("[FilesystemManager] Temp workspace parent cleared successfully")

        except Exception as e:
            logger.error(f"[FilesystemManager] Failed to clear temp workspace parent: {e}")
            # Last resort: try to recreate it fresh even if rmtree partially failed
            try:
                self.agent_temporary_workspace_parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

        # Prune stale workspaces from .massgen/workspaces/ (left over from previous runs)
        try:
            workspaces_dir = self.agent_temporary_workspace_parent.parent / "workspaces"
            if workspaces_dir.exists() and workspaces_dir.is_dir():
                for child in list(workspaces_dir.iterdir()):
                    if child.is_dir():
                        logger.info(f"[FilesystemManager] Pruning stale workspace: {child}")
                        _safe_rmtree(child)
                # Remove empty workspaces dir
                if workspaces_dir.exists() and not any(workspaces_dir.iterdir()):
                    workspaces_dir.rmdir()
        except Exception as e:
            logger.warning(f"[FilesystemManager] Failed to prune stale workspaces: {e}")

    @staticmethod
    def _rewrite_temp_workspace_path(raw_value: str, source_snapshot_root: Path, temp_snapshot_root: Path) -> str:
        """Rewrite an absolute workspace path to the copied temp workspace path."""
        if not isinstance(raw_value, str):
            return raw_value

        candidate = raw_value.strip()
        if not candidate:
            return raw_value

        source_root = str(source_snapshot_root.resolve())
        temp_root = str(temp_snapshot_root.resolve())

        if candidate.startswith(source_root):
            suffix = candidate[len(source_root) :]
            return f"{temp_root}{suffix}"

        try:
            source_path = Path(candidate).resolve(strict=False)
        except Exception:
            return raw_value

        markers = (
            "/.massgen_scratch/",
            "/scratch/",
            "/deliverable/",
            "/memory/",
        )
        normalized = str(source_path).replace("\\", "/")
        for marker in markers:
            marker_index = normalized.find(marker)
            if marker_index < 0:
                continue
            rel_suffix = normalized[marker_index + 1 :]  # drop leading slash
            source_candidate = source_snapshot_root / rel_suffix
            if source_candidate.exists():
                return str((temp_snapshot_root / rel_suffix).resolve())

        try:
            rel = source_path.relative_to(source_snapshot_root.resolve())
            return str((temp_snapshot_root / rel).resolve())
        except Exception:
            return raw_value

    @classmethod
    def _rewrite_media_ledger_value(cls, value: Any, source_snapshot_root: Path, temp_snapshot_root: Path) -> Any:
        """Recursively rewrite absolute paths in media ledger values."""
        if isinstance(value, dict):
            return {
                key: cls._rewrite_media_ledger_value(
                    nested,
                    source_snapshot_root,
                    temp_snapshot_root,
                )
                for key, nested in value.items()
            }

        if isinstance(value, list):
            return [
                cls._rewrite_media_ledger_value(
                    nested,
                    source_snapshot_root,
                    temp_snapshot_root,
                )
                for nested in value
            ]

        if not isinstance(value, str):
            return value

        raw = value.strip()
        if raw and raw[0] in ("{", "["):
            try:
                parsed = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                parsed = None
            if parsed is not None:
                rewritten = cls._rewrite_media_ledger_value(
                    parsed,
                    source_snapshot_root,
                    temp_snapshot_root,
                )
                return json.dumps(rewritten, ensure_ascii=False, separators=(",", ":"))

        return cls._rewrite_temp_workspace_path(
            value,
            source_snapshot_root,
            temp_snapshot_root,
        )

    def _normalize_media_call_ledger_paths(
        self,
        source_snapshot_root: Path,
        temp_snapshot_root: Path,
    ) -> None:
        """Rewrite copied media ledger paths so they are valid in temp workspace."""
        ledger_path = temp_snapshot_root / ".massgen_scratch" / "verification" / "media_call_ledger.json"
        if not ledger_path.exists():
            return

        try:
            payload = json.loads(ledger_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.debug(f"[FilesystemManager] Failed to parse media ledger for rewrite: {ledger_path} ({e})")
            return

        if not isinstance(payload, dict):
            return

        entries = payload.get("entries")
        if not isinstance(entries, list):
            return

        changed = False
        for entry in entries:
            if not isinstance(entry, dict):
                continue

            tool_arguments = entry.get("tool_arguments")
            if tool_arguments is not None:
                rewritten_args = self._rewrite_media_ledger_value(
                    tool_arguments,
                    source_snapshot_root,
                    temp_snapshot_root,
                )
                if rewritten_args != tool_arguments:
                    entry["tool_arguments"] = rewritten_args
                    changed = True

            mappings = entry.get("file_mappings")
            if not isinstance(mappings, list):
                continue

            rewritten_mappings: list[Any] = []
            mapping_changed = False
            for item in mappings:
                if not isinstance(item, str):
                    rewritten_mappings.append(item)
                    continue

                if "->" in item:
                    left, _, right = item.partition("->")
                    rewritten_right = self._rewrite_temp_workspace_path(
                        right.strip(),
                        source_snapshot_root,
                        temp_snapshot_root,
                    )
                    rewritten_item = f"{left.strip()} -> {rewritten_right}"
                else:
                    rewritten_item = self._rewrite_temp_workspace_path(
                        item,
                        source_snapshot_root,
                        temp_snapshot_root,
                    )

                rewritten_mappings.append(rewritten_item)
                if rewritten_item != item:
                    mapping_changed = True

            if mapping_changed:
                entry["file_mappings"] = rewritten_mappings
                changed = True

        if not changed:
            return

        try:
            ledger_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except Exception as e:
            logger.debug(f"[FilesystemManager] Failed to persist normalized media ledger: {ledger_path} ({e})")

    async def copy_snapshots_to_temp_workspace(self, all_snapshots: dict[str, Path], agent_mapping: dict[str, str]) -> Path | None:
        """
        Copy snapshots from multiple agents to temporary workspace for context sharing.

        This method is called by the orchestrator before starting an agent that needs context from others.
        It copies the latest snapshots from log directories to a temporary workspace.

        Args:
            all_snapshots: Dictionary mapping agent_id to snapshot path (from log directories)
            agent_mapping: Dictionary mapping real agent_id to anonymous agent_id

        Returns:
            Path to the temporary workspace with restored snapshots

        B1: the blocking filesystem work (rmtree/copytree/scrub) is offloaded to a
        worker thread via ``asyncio.to_thread`` so it does not stall the
        orchestrator event loop. While one agent's snapshots are copied, the other
        agents' streams keep being consumed. Each agent owns a distinct
        ``agent_temporary_workspace`` directory, so concurrent offloaded copies
        write to disjoint paths — there is no shared-state race.
        """
        if not self.agent_temporary_workspace:
            return None

        return await asyncio.to_thread(
            self._copy_snapshots_to_temp_workspace_sync,
            all_snapshots,
            agent_mapping,
        )

    def _copy_snapshots_to_temp_workspace_sync(self, all_snapshots: dict[str, Path], agent_mapping: dict[str, str]) -> Path | None:
        """Synchronous body of :meth:`copy_snapshots_to_temp_workspace`.

        Runs on a worker thread (see that method). Each agent's
        ``agent_temporary_workspace`` is distinct, so concurrent invocations on
        different FilesystemManager instances touch disjoint directories.
        """
        if not self.agent_temporary_workspace:
            return None

        # Clear existing temporary workspace
        if self.agent_temporary_workspace.exists():
            _safe_rmtree(self.agent_temporary_workspace)
        self.agent_temporary_workspace.mkdir(parents=True, exist_ok=True)

        # Framework metadata dirs to exclude from temp workspace copies.
        # These contain agent IDs in filenames/content and backend-identifying
        # artifacts — agents don't need them for evaluating others' work.
        _snapshot_exclude_dirs = {".massgen", ".codex", ".gemini", ".antigravity", ".antigravitycli", ".claude", ".git"}

        # Copy all snapshots using anonymous IDs
        for agent_id, snapshot_path in all_snapshots.items():
            if snapshot_path.exists() and snapshot_path.is_dir():
                # Use anonymous ID for destination directory
                anon_id = agent_mapping.get(agent_id, agent_id)
                dest_dir = self.agent_temporary_workspace / anon_id

                # Copy snapshot content if not empty
                # Use symlinks=True to copy symlinks as symlinks, not follow them
                # Use ignore_dangling_symlinks=True to handle broken symlinks in subdirectories
                if any(snapshot_path.iterdir()):
                    shutil.copytree(
                        snapshot_path,
                        dest_dir,
                        dirs_exist_ok=True,
                        symlinks=True,
                        ignore_dangling_symlinks=True,
                        ignore=shutil.ignore_patterns(*_snapshot_exclude_dirs),
                    )
                    self._normalize_media_call_ledger_paths(
                        source_snapshot_root=snapshot_path,
                        temp_snapshot_root=dest_dir,
                    )

                    # Scrub remaining agent IDs from framework metadata files
                    from ._path_rewriter import scrub_agent_ids_in_snapshot

                    scrub_agent_ids_in_snapshot(dest_dir, agent_mapping)

        return self.agent_temporary_workspace

    def _log_workspace_contents(self, workspace_path: Path, workspace_name: str, context: str = "") -> None:
        """
        Log the contents of a workspace directory for visibility.

        Args:
            workspace_path: Path to the workspace to log
            workspace_name: Human-readable name for the workspace
            context: Additional context (e.g., "before execution", "after execution")
        """
        from ._constants import MAX_LOG_DEPTH, MAX_LOG_ITEMS, SKIP_DIRS_FOR_LOGGING

        if not workspace_path or not workspace_path.exists():
            logger.info(f"[FilesystemManager.{workspace_name}] {context} - Workspace does not exist: {workspace_path}")
            return

        try:
            # Collect paths while skipping large dependency directories
            file_paths: list[str] = []
            dir_paths: list[str] = []
            skipped_dirs: list[str] = []

            def collect_paths(base: Path, rel_prefix: str = "") -> None:
                try:
                    for item in base.iterdir():
                        rel_path = f"{rel_prefix}/{item.name}" if rel_prefix else item.name
                        if item.is_dir():
                            if item.name in SKIP_DIRS_FOR_LOGGING:
                                skipped_dirs.append(rel_path)
                            else:
                                dir_paths.append(rel_path)
                                # Recurse but limit depth to avoid explosion
                                if rel_path.count("/") < MAX_LOG_DEPTH:
                                    collect_paths(item, rel_path)
                        else:
                            file_paths.append(rel_path)
                except PermissionError:
                    pass

            collect_paths(workspace_path)

            logger.info(f"[FilesystemManager.{workspace_name}] {context} - Workspace: {workspace_path}")

            # Truncate lists if too large
            if file_paths:
                display_files = file_paths[:MAX_LOG_ITEMS]
                suffix = f" ... and {len(file_paths) - MAX_LOG_ITEMS} more" if len(file_paths) > MAX_LOG_ITEMS else ""
                logger.info(f"[FilesystemManager.{workspace_name}] {context} - Files ({len(file_paths)}): {display_files}{suffix}")
            if dir_paths:
                display_dirs = dir_paths[:MAX_LOG_ITEMS]
                suffix = f" ... and {len(dir_paths) - MAX_LOG_ITEMS} more" if len(dir_paths) > MAX_LOG_ITEMS else ""
                logger.info(f"[FilesystemManager.{workspace_name}] {context} - Directories ({len(dir_paths)}): {display_dirs}{suffix}")
            if skipped_dirs:
                logger.info(f"[FilesystemManager.{workspace_name}] {context} - Skipped large dirs: {skipped_dirs}")
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

    def get_workspace_root(self) -> Path:
        """
        Get the persistent workspace root that was created at initialization.

        This is the path that subagent MCP servers and other long-lived
        metadata should use, even if the active workspace (`cwd`) temporarily
        switches to a worktree/temporary directory during restarts.
        """
        return self._original_cwd

    @staticmethod
    def _is_massgen_workspace(path: Path) -> bool:
        """Check if a path is under a .massgen/workspaces/ directory."""
        try:
            parts = path.resolve().parts
            for i, part in enumerate(parts):
                if part == ".massgen" and i + 1 < len(parts) and parts[i + 1] == "workspaces":
                    return True
        except Exception:
            pass
        return False

    def cleanup(self) -> None:
        """Cleanup temporary resources and Docker containers.

        Also removes the main workspace directory if it's under .massgen/workspaces/.
        """
        # Cleanup isolation contexts if manager is active
        if self.isolation_manager:
            try:
                logger.info("[FilesystemManager] Cleaning up isolation contexts")
                self.isolation_manager.cleanup_all()
            except Exception as e:
                logger.warning(f"[FilesystemManager] Failed to cleanup isolation contexts: {e}")

        # Cleanup Docker container if Docker mode enabled
        if self.docker_manager and self.agent_id:
            self.docker_manager.cleanup(self.agent_id)

        # Cleanup shared_tools directory if it was created for this run
        if self.shared_tools_directory and self.shared_tools_directory.exists():
            try:
                logger.info(f"[FilesystemManager] Cleaning up shared tools directory: {self.shared_tools_directory}")
                _safe_rmtree(self.shared_tools_directory)
            except Exception as e:
                logger.warning(f"[FilesystemManager] Failed to cleanup shared tools directory: {e}")

        # Cleanup local skills directory if it exists
        if self.local_skills_directory and self.local_skills_directory.exists():
            try:
                logger.info(f"[FilesystemManager] Cleaning up local skills directory: {self.local_skills_directory}")
                _safe_rmtree(self.local_skills_directory)
            except Exception as e:
                logger.warning(f"[FilesystemManager] Failed to cleanup local skills directory: {e}")

        # Cleanup main workspace if it's under .massgen/workspaces/
        if hasattr(self, "cwd") and self.cwd and self._is_massgen_workspace(self.cwd):
            try:
                ws = self.cwd.resolve()
                if ws.exists() and ws.is_dir() and len(ws.parts) >= 4:
                    logger.info(f"[FilesystemManager] Cleaning up workspace: {ws}")
                    _safe_rmtree(ws)
                    # Prune empty parent dirs up to .massgen/workspaces/
                    parent = ws.parent
                    if parent.exists() and parent.name == "workspaces" and not any(parent.iterdir()):
                        parent.rmdir()
            except Exception as e:
                logger.warning(f"[FilesystemManager] Failed to cleanup workspace: {e}")

        # Cleanup temporary workspace
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

            _safe_rmtree(p)
        except Exception as e:
            logger.warning(f"[FilesystemManager] cleanup failed for {p}: {e}")
