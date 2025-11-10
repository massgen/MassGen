# -*- coding: utf-8 -*-
"""
Docker Container Manager for MassGen

Manages Docker containers for isolated command execution.
Provides strong filesystem isolation by executing commands inside containers
while keeping MCP servers on the host.
"""

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..logger_config import logger

# Check if docker is available
try:
    import docker
    from docker.errors import DockerException, ImageNotFound, NotFound
    from docker.models.containers import Container

    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False
    logger.warning("Docker Python library not available. Install with: pip install docker")


class DockerManager:
    """
    Manages Docker containers for isolated command execution.

    Each agent gets a persistent container for the orchestration session:
    - Volume mounts for workspace and context paths
    - Network isolation (configurable)
    - Resource limits (CPU, memory)
    - Commands executed via docker exec
    - State persists across turns (packages stay installed)
    """

    def __init__(
        self,
        image: str = "massgen/mcp-runtime:latest",
        network_mode: str = "none",
        memory_limit: Optional[str] = None,
        cpu_limit: Optional[float] = None,
        enable_sudo: bool = False,
        credentials: Optional[Dict[str, Any]] = None,
        packages: Optional[Dict[str, Any]] = None,
        instance_id: Optional[str] = None,
    ):
        """
        Initialize Docker manager.

        Args:
            image: Docker image to use for containers
            network_mode: Network mode (none/bridge/host)
            memory_limit: Memory limit (e.g., "2g", "512m")
            cpu_limit: CPU limit (e.g., 2.0 for 2 CPUs)
            enable_sudo: Enable sudo access in containers (isolated from host system)
            credentials: Credential management configuration:
                mount: List of credential types to mount ["ssh_keys", "git_config", "gh_config", "npm_config", "pypi_config"]
                additional_mounts: Custom volume mounts {host_path: {bind: container_path, mode: ro/rw}}
                env_file: Path to .env file to load
                env_vars: List of environment variables to pass from host
                env_vars_from_file: List of specific variables to load from env_file (filters env_file)
                pass_all_env: Pass all host environment variables (DANGEROUS)
            packages: Package management configuration:
                preinstall: Dict with python/npm/system keys containing package lists
            instance_id: Optional unique instance ID for parallel execution (prevents container name collisions)

        Raises:
            RuntimeError: If Docker is not available or cannot connect
        """
        if not DOCKER_AVAILABLE:
            raise RuntimeError("Docker Python library not available. Install with: pip install docker")

        self.instance_id = instance_id  # Unique instance ID for parallel execution

        # If sudo is enabled and user is using default image, switch to sudo variant
        self.enable_sudo = enable_sudo
        if enable_sudo and image == "massgen/mcp-runtime:latest":
            self.image = "massgen/mcp-runtime-sudo:latest"
            logger.info(
                "ℹ️ [Docker] Sudo access enabled in container (isolated from host) - using 'massgen/mcp-runtime-sudo:latest' image.",
            )
        elif enable_sudo:
            logger.info(
                "ℹ️ [Docker] Sudo access enabled in container (isolated from host) with custom image.",
            )
        else:
            self.image = image

        self.network_mode = network_mode
        self.memory_limit = memory_limit
        self.cpu_limit = cpu_limit

        # Extract credential configuration from nested dict
        credentials = credentials or {}
        mount_list = credentials.get("mount", [])
        self.mount_ssh_keys = "ssh_keys" in mount_list
        self.mount_git_config = "git_config" in mount_list
        self.mount_gh_config = "gh_config" in mount_list
        self.mount_npm_config = "npm_config" in mount_list
        self.mount_pypi_config = "pypi_config" in mount_list
        self.additional_mounts = credentials.get("additional_mounts", {})
        self.env_file_path = credentials.get("env_file")
        self.pass_env_vars = credentials.get("env_vars", [])
        self.env_vars_from_file = credentials.get("env_vars_from_file", [])
        self.pass_all_env = credentials.get("pass_all_env", False)

        # Extract package configuration from nested dict
        packages = packages or {}
        preinstall = packages.get("preinstall", {})
        self.preinstall_python = preinstall.get("python", [])
        self.preinstall_npm = preinstall.get("npm", [])
        self.preinstall_system = preinstall.get("system", [])

        # Warning for dangerous options
        if self.pass_all_env:
            logger.warning("⚠️ [Docker] pass_all_env is enabled - all host environment variables will be passed to containers")

        try:
            self.client = docker.from_env()
            # Test connection
            self.client.ping()

            # Get Docker version info for logging
            version_info = self.client.version()
            docker_version = version_info.get("Version", "unknown")
            api_version = version_info.get("ApiVersion", "unknown")

            logger.info("🐳 [Docker] Client initialized successfully")
            logger.info(f"    Docker version: {docker_version}")
            logger.info(f"    API version: {api_version}")
        except DockerException as e:
            logger.error(f"❌ [Docker] Failed to connect to Docker daemon: {e}")
            raise RuntimeError(f"Failed to connect to Docker: {e}")

        self.containers: Dict[str, Container] = {}  # agent_id -> container

    def ensure_image_exists(self) -> None:
        """
        Ensure the Docker image exists locally.

        Pulls the image if not found locally.

        Raises:
            RuntimeError: If image cannot be pulled
        """
        try:
            self.client.images.get(self.image)
            logger.info(f"✅ [Docker] Image '{self.image}' found locally")
        except ImageNotFound:
            logger.info(f"📥 [Docker] Image '{self.image}' not found locally, pulling...")
            try:
                self.client.images.pull(self.image)
                logger.info(f"✅ [Docker] Successfully pulled image '{self.image}'")
            except DockerException as e:
                # Special handling for sudo image - it's built locally, not pulled
                if "mcp-runtime-sudo" in self.image:
                    raise RuntimeError(
                        f"Failed to pull Docker image '{self.image}': {e}\n" f"The sudo image must be built locally. Run:\n" f"    bash massgen/docker/build.sh --sudo",
                    )
                raise RuntimeError(f"Failed to pull Docker image '{self.image}': {e}")

    def _load_env_file(self, env_file_path: str) -> Dict[str, str]:
        """
        Load environment variables from a .env file.

        Args:
            env_file_path: Path to .env file

        Returns:
            Dictionary of environment variables

        Raises:
            RuntimeError: If file cannot be read or parsed
        """
        env_vars = {}
        env_path = Path(env_file_path).expanduser().resolve()

        if not env_path.exists():
            raise RuntimeError(f"Environment file not found: {env_file_path}")

        logger.info(f"📄 [Docker] Loading environment variables from: {env_path}")

        try:
            with open(env_path, "r") as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    # Skip empty lines and comments
                    if not line or line.startswith("#"):
                        continue

                    # Parse KEY=VALUE format
                    if "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip()

                        # Remove quotes if present
                        if value.startswith('"') and value.endswith('"'):
                            value = value[1:-1]
                        elif value.startswith("'") and value.endswith("'"):
                            value = value[1:-1]

                        env_vars[key] = value
                    else:
                        logger.warning(f"⚠️ [Docker] Skipping invalid line {line_num} in {env_file_path}: {line}")

            logger.info(f"    Loaded {len(env_vars)} environment variable(s)")
            return env_vars

        except Exception as e:
            raise RuntimeError(f"Failed to read environment file {env_file_path}: {e}")

    def _build_environment(self) -> Dict[str, str]:
        """
        Build environment variables dict to pass to container.

        Returns:
            Dictionary of environment variables
        """
        env_vars = {}

        # Option 1: Load from .env file
        if self.env_file_path:
            try:
                file_env = self._load_env_file(self.env_file_path)
                # Filter to only specific vars if env_vars_from_file is specified
                if self.env_vars_from_file:
                    filtered_env = {k: v for k, v in file_env.items() if k in self.env_vars_from_file}
                    logger.info(f"    Filtered to {len(filtered_env)} of {len(file_env)} variables from .env file")
                    env_vars.update(filtered_env)
                else:
                    # Load all variables from file
                    env_vars.update(file_env)
            except Exception as e:
                logger.error(f"❌ [Docker] Failed to load env file: {e}")
                raise

        # Option 2: Pass all host environment variables
        if self.pass_all_env:
            env_vars.update(os.environ.copy())
            logger.info("    Passing all host environment variables to container")

        # Option 3: Pass specific environment variables
        if self.pass_env_vars:
            for var_name in self.pass_env_vars:
                if var_name in os.environ:
                    env_vars[var_name] = os.environ[var_name]
                    logger.debug(f"    Passing env var: {var_name}")
                else:
                    logger.warning(f"⚠️ [Docker] Requested env var '{var_name}' not found in host environment")

        return env_vars

    def _build_credential_mounts(self) -> Dict[str, Dict[str, str]]:
        """
        Build volume mounts for credential files.

        Returns:
            Dictionary of volume mounts {host_path: {bind: container_path, mode: ro/rw}}
        """
        mounts = {}
        home_dir = Path.home()

        # Mount SSH keys (read-only)
        if self.mount_ssh_keys:
            ssh_dir = home_dir / ".ssh"
            if ssh_dir.exists():
                mounts[str(ssh_dir)] = {"bind": "/home/massgen/.ssh", "mode": "ro"}
                logger.info(f"🔐 [Docker] Mounting SSH keys: {ssh_dir} → /home/massgen/.ssh (ro)")
            else:
                logger.warning(f"⚠️ [Docker] SSH directory not found: {ssh_dir}")

        # Mount git config (read-only)
        if self.mount_git_config:
            git_config = home_dir / ".gitconfig"
            if git_config.exists():
                mounts[str(git_config)] = {"bind": "/home/massgen/.gitconfig", "mode": "ro"}
                logger.info(f"🔐 [Docker] Mounting git config: {git_config} → /home/massgen/.gitconfig (ro)")
            else:
                logger.warning(f"⚠️ [Docker] Git config not found: {git_config}")

        # Mount GitHub CLI config (read-only)
        if self.mount_gh_config:
            gh_config = home_dir / ".config" / "gh"
            if gh_config.exists():
                mounts[str(gh_config)] = {"bind": "/home/massgen/.config/gh", "mode": "ro"}
                logger.info(f"🔐 [Docker] Mounting GitHub CLI config: {gh_config} → /home/massgen/.config/gh (ro)")
            else:
                logger.warning(f"⚠️ [Docker] GitHub CLI config not found: {gh_config}")

        # Mount npm config (read-only)
        if self.mount_npm_config:
            npm_config = home_dir / ".npmrc"
            if npm_config.exists():
                mounts[str(npm_config)] = {"bind": "/home/massgen/.npmrc", "mode": "ro"}
                logger.info(f"🔐 [Docker] Mounting npm config: {npm_config} → /home/massgen/.npmrc (ro)")
            else:
                logger.warning(f"⚠️ [Docker] npm config not found: {npm_config}")

        # Mount pypi config (read-only)
        if self.mount_pypi_config:
            pypi_config = home_dir / ".pypirc"
            if pypi_config.exists():
                mounts[str(pypi_config)] = {"bind": "/home/massgen/.pypirc", "mode": "ro"}
                logger.info(f"🔐 [Docker] Mounting PyPI config: {pypi_config} → /home/massgen/.pypirc (ro)")
            else:
                logger.warning(f"⚠️ [Docker] PyPI config not found: {pypi_config}")

        # Additional custom mounts
        if self.additional_mounts:
            for host_path, mount_config in self.additional_mounts.items():
                host_path_obj = Path(host_path).expanduser().resolve()
                if host_path_obj.exists():
                    mounts[str(host_path_obj)] = mount_config
                    container_path = mount_config.get("bind", host_path)
                    mode = mount_config.get("mode", "ro")
                    logger.info(f"🔐 [Docker] Mounting custom path: {host_path_obj} → {container_path} ({mode})")
                else:
                    logger.warning(f"⚠️ [Docker] Custom mount path not found: {host_path}")

        return mounts

    def preinstall_packages(
        self,
        agent_id: str,
    ) -> bool:
        """
        Pre-install user-specified packages in the container.

        Runs BEFORE auto-dependency detection to provide a consistent base environment.

        Args:
            agent_id: Agent identifier

        Returns:
            True if all installations succeeded, False otherwise
        """
        if not self.preinstall_python and not self.preinstall_npm and not self.preinstall_system:
            return True  # Nothing to install

        logger.info(f"📦 [Docker] Pre-installing user-specified packages for agent {agent_id}")
        print(f"📦 [Docker] Pre-installing user-specified packages for agent {agent_id}", flush=True)

        # Log what will be installed
        if self.preinstall_system:
            logger.info(f"    • System: {', '.join(self.preinstall_system)}")
            print(f"    • System: {', '.join(self.preinstall_system)}", flush=True)
        if self.preinstall_python:
            logger.info(f"    • Python: {', '.join(self.preinstall_python)}")
            print(f"    • Python: {', '.join(self.preinstall_python)}", flush=True)
        if self.preinstall_npm:
            logger.info(f"    • npm: {', '.join(self.preinstall_npm)}")
            print(f"    • npm: {', '.join(self.preinstall_npm)}", flush=True)

        logger.info("⏳ [Docker] Installing packages (this may take a few minutes)...")
        print("⏳ [Docker] Installing packages (this may take a few minutes)...", flush=True)
        success = True

        # Install system packages first (may be needed by Python/npm packages)
        if self.preinstall_system:
            if not self.enable_sudo:
                logger.warning("⚠️ [Docker] System package pre-install requires sudo mode, skipping")
            else:
                packages_str = " ".join(self.preinstall_system)
                cmd = f"sudo apt-get update && sudo apt-get install -y {packages_str}"
                logger.info(f"    Installing system packages: {', '.join(self.preinstall_system)}")

                try:
                    result = self.exec_command(
                        agent_id=agent_id,
                        command=cmd,
                        timeout=600,  # 10 minute timeout for system packages
                    )
                    if result["success"]:
                        logger.info("✅ [Docker] System packages installed successfully")
                        print("✅ [Docker] System packages installed successfully", flush=True)
                    else:
                        logger.warning("⚠️ [Docker] System package installation failed")
                        logger.warning(f"    Exit code: {result['exit_code']}")
                        print(f"⚠️ [Docker] System package installation failed (exit code: {result['exit_code']})", flush=True)
                        success = False
                except Exception as e:
                    logger.error(f"❌ [Docker] Error installing system packages: {e}")
                    success = False

        # Install Python packages
        if self.preinstall_python:
            packages_str = " ".join(self.preinstall_python)
            cmd = f"pip install {packages_str}"
            logger.info(f"    Installing Python packages: {', '.join(self.preinstall_python)}")

            try:
                result = self.exec_command(
                    agent_id=agent_id,
                    command=cmd,
                    timeout=600,  # 10 minute timeout
                )
                if result["success"]:
                    logger.info("✅ [Docker] Python packages installed successfully")
                    print("✅ [Docker] Python packages installed successfully", flush=True)
                else:
                    logger.warning("⚠️ [Docker] Python package installation failed")
                    logger.warning(f"    Exit code: {result['exit_code']}")
                    logger.warning(f"    Output: {result.get('stdout', '')[:500]}")
                    print(f"⚠️ [Docker] Python package installation failed (exit code: {result['exit_code']})", flush=True)
                    success = False
            except Exception as e:
                logger.error(f"❌ [Docker] Error installing Python packages: {e}")
                logger.exception("Full traceback:")
                success = False

        # Install npm packages
        if self.preinstall_npm:
            packages_str = " ".join(self.preinstall_npm)
            # Use sudo for global npm install if sudo is enabled
            npm_cmd = "sudo npm" if self.enable_sudo else "npm"
            cmd = f"{npm_cmd} install -g {packages_str}"
            logger.info(f"    Installing npm packages (global): {', '.join(self.preinstall_npm)}")

            try:
                result = self.exec_command(
                    agent_id=agent_id,
                    command=cmd,
                    timeout=600,  # 10 minute timeout
                )
                if result["success"]:
                    logger.info("✅ [Docker] npm packages installed successfully")
                    print("✅ [Docker] npm packages installed successfully", flush=True)
                else:
                    logger.warning("⚠️ [Docker] npm package installation failed")
                    logger.warning(f"    Exit code: {result['exit_code']}")
                    logger.warning(f"    Output: {result.get('stdout', '')[:500]}")
                    print(f"⚠️ [Docker] npm package installation failed (exit code: {result['exit_code']})", flush=True)
                    success = False
            except Exception as e:
                logger.error(f"❌ [Docker] Error installing npm packages: {e}")
                logger.exception("Full traceback:")
                success = False

        if success:
            logger.info("✅ [Docker] All pre-install packages installed successfully")
            print("✅ [Docker] All pre-install packages installed successfully", flush=True)
        else:
            logger.warning("⚠️ [Docker] Some pre-install packages failed (continuing anyway)")
            print("⚠️ [Docker] Some pre-install packages failed (continuing anyway)", flush=True)

        return success

    def create_container(
        self,
        agent_id: str,
        workspace_path: Path,
        temp_workspace_path: Optional[Path] = None,
        context_paths: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        Create and start a persistent Docker container for an agent.

        The container runs for the entire orchestration session and maintains state
        across command executions (installed packages, generated files, etc.).

        IMPORTANT: Paths are mounted at the SAME location as on the host to maintain
        path transparency. The LLM sees identical paths whether in Docker or local mode.

        Args:
            agent_id: Unique identifier for the agent
            workspace_path: Path to agent's workspace (mounted at same path, read-write)
            temp_workspace_path: Path to shared temp workspace (mounted at same path, read-only)
            context_paths: List of context path dicts with 'path', 'permission', and optional 'name' keys
                          (each mounted at its host path)

        Returns:
            Container ID

        Raises:
            RuntimeError: If container creation fails
        """
        if agent_id in self.containers:
            logger.warning(f"⚠️ [Docker] Container for agent {agent_id} already exists")
            return self.containers[agent_id].id

        # Ensure image exists
        self.ensure_image_exists()

        # Check for and remove any existing container with the same name
        # Include instance_id to prevent collisions when running parallel instances
        if self.instance_id:
            container_name = f"massgen-{agent_id}-{self.instance_id}"
        else:
            container_name = f"massgen-{agent_id}"
        try:
            existing = self.client.containers.get(container_name)
            logger.warning(
                f"🔄 [Docker] Found existing container '{container_name}' (id: {existing.short_id}), removing it",
            )
            existing.remove(force=True)
        except NotFound:
            # No existing container, this is expected
            pass
        except DockerException as e:
            logger.warning(f"⚠️ [Docker] Error checking for existing container '{container_name}': {e}")

        logger.info(f"🐳 [Docker] Creating container for agent '{agent_id}'")
        logger.info(f"    Image: {self.image}")
        logger.info(f"    Network: {self.network_mode}")
        if self.memory_limit:
            logger.info(f"    Memory limit: {self.memory_limit}")
        if self.cpu_limit:
            logger.info(f"    CPU limit: {self.cpu_limit} cores")

        # Build environment variables
        env_vars = self._build_environment()
        if env_vars:
            logger.info(f"    Environment variables: {len(env_vars)} variable(s)")

        # Build volume mounts
        # IMPORTANT: Mount paths at the SAME location as on host to avoid path confusion
        # This makes Docker completely transparent to the LLM - it sees identical paths
        volumes = {}
        mount_info = []

        # Mount agent workspace (read-write) at the SAME path as host
        workspace_path = workspace_path.resolve()
        volumes[str(workspace_path)] = {"bind": str(workspace_path), "mode": "rw"}
        mount_info.append(f"      {workspace_path} ← {workspace_path} (rw)")

        # Mount temp workspace (read-only) at the SAME path as host
        if temp_workspace_path:
            temp_workspace_path = temp_workspace_path.resolve()
            volumes[str(temp_workspace_path)] = {"bind": str(temp_workspace_path), "mode": "ro"}
            mount_info.append(f"      {temp_workspace_path} ← {temp_workspace_path} (ro)")

        # Mount context paths at the SAME paths as host
        if context_paths:
            for ctx_path_config in context_paths:
                ctx_path = Path(ctx_path_config["path"]).resolve()
                permission = ctx_path_config.get("permission", "read")
                mode = "rw" if permission == "write" else "ro"

                volumes[str(ctx_path)] = {"bind": str(ctx_path), "mode": mode}
                mount_info.append(f"      {ctx_path} ← {ctx_path} ({mode})")

        # Add credential file mounts
        credential_mounts = self._build_credential_mounts()
        volumes.update(credential_mounts)

        # Log volume mounts
        if mount_info:
            logger.info("    Volume mounts:")
            for mount_line in mount_info:
                logger.info(mount_line)

        # Build resource limits
        resource_config = {}
        if self.memory_limit:
            resource_config["mem_limit"] = self.memory_limit
        if self.cpu_limit:
            resource_config["nano_cpus"] = int(self.cpu_limit * 1e9)

        # Container configuration
        container_config = {
            "image": self.image,
            "name": container_name,
            "command": ["tail", "-f", "/dev/null"],  # Keep container running
            "detach": True,
            "volumes": volumes,
            "working_dir": str(workspace_path),  # Use host workspace path
            "network_mode": self.network_mode,
            "auto_remove": False,  # Manual cleanup for better control
            "stdin_open": True,
            "tty": True,
            **resource_config,
        }

        # Add environment variables if any
        if env_vars:
            container_config["environment"] = env_vars

        try:
            # Create and start container
            container = self.client.containers.run(**container_config)
            self.containers[agent_id] = container

            # Get container info for logging
            container.reload()  # Refresh container state
            status = container.status

            logger.info("✅ [Docker] Container created successfully")
            logger.info(f"    Container ID: {container.short_id}")
            logger.info(f"    Container name: {container_name}")
            logger.info(f"    Status: {status}")

            # Show how to inspect the container
            logger.debug(f"💡 [Docker] Inspect container: docker inspect {container.short_id}")
            logger.debug(f"💡 [Docker] View logs: docker logs {container.short_id}")
            logger.debug(f"💡 [Docker] Execute commands: docker exec -it {container.short_id} /bin/bash")

            # Pre-install user-specified packages (base environment)
            if self.preinstall_python or self.preinstall_npm or self.preinstall_system:
                try:
                    self.preinstall_packages(agent_id=agent_id)
                except Exception as e:
                    logger.warning(f"⚠️ [Docker] Failed to pre-install packages: {e}")
                    # Don't fail container creation if pre-install fails

            return container.id

        except DockerException as e:
            logger.error(f"❌ [Docker] Failed to create container for agent {agent_id}: {e}")
            raise RuntimeError(f"Failed to create Docker container for agent {agent_id}: {e}")

    def get_container(self, agent_id: str) -> Optional[Container]:
        """
        Get container for an agent.

        Args:
            agent_id: Agent identifier

        Returns:
            Container object or None if not found
        """
        return self.containers.get(agent_id)

    def exec_command(
        self,
        agent_id: str,
        command: str,
        workdir: Optional[str] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Execute a command inside the agent's container.

        Args:
            agent_id: Agent identifier
            command: Command to execute (as string, will be run in shell)
            workdir: Working directory (uses host path - same path is mounted in container)
            timeout: Command timeout in seconds (implemented using threading)

        Returns:
            Dictionary with:
            - success: bool (True if exit_code == 0)
            - exit_code: int
            - stdout: str
            - stderr: str (combined with stdout in Docker exec)
            - execution_time: float
            - command: str
            - work_dir: str

        Raises:
            ValueError: If container not found
            RuntimeError: If execution fails
        """
        container = self.containers.get(agent_id)
        if not container:
            raise ValueError(f"No container found for agent {agent_id}")

        # Default workdir is the container's default working dir (set to workspace_path at creation)
        effective_workdir = workdir if workdir else None

        try:
            # Run command through shell to support pipes, redirects, etc.
            exec_config = {
                "cmd": ["/bin/sh", "-c", command],
                "stdout": True,
                "stderr": True,
            }

            if effective_workdir:
                exec_config["workdir"] = effective_workdir

            logger.debug(f"🔧 [Docker] Executing in container {container.short_id}: {command}")

            start_time = time.time()

            # Handle timeout using threading
            if timeout:
                import threading

                result_container = {}
                exception_container = {}

                def run_exec():
                    try:
                        result_container["data"] = container.exec_run(**exec_config)
                    except Exception as e:
                        exception_container["error"] = e

                thread = threading.Thread(target=run_exec)
                thread.daemon = True
                thread.start()
                thread.join(timeout=timeout)

                execution_time = time.time() - start_time

                if thread.is_alive():
                    # Thread is still running - timeout occurred
                    logger.warning(f"⚠️ [Docker] Command timed out after {timeout} seconds")
                    return {
                        "success": False,
                        "exit_code": -1,
                        "stdout": "",
                        "stderr": f"Command timed out after {timeout} seconds",
                        "execution_time": execution_time,
                        "command": command,
                        "work_dir": effective_workdir or "(container default)",
                    }

                if "error" in exception_container:
                    raise exception_container["error"]

                if "data" not in result_container:
                    raise RuntimeError("Command execution failed - no result data")

                exit_code, output = result_container["data"]
            else:
                # No timeout - execute directly
                exit_code, output = container.exec_run(**exec_config)
                execution_time = time.time() - start_time

            # Docker exec_run combines stdout and stderr
            output_str = output.decode("utf-8") if isinstance(output, bytes) else output

            if exit_code != 0:
                logger.debug(f"⚠️ [Docker] Command exited with code {exit_code}")

            return {
                "success": exit_code == 0,
                "exit_code": exit_code,
                "stdout": output_str,
                "stderr": "",  # Docker exec_run combines stdout/stderr
                "execution_time": execution_time,
                "command": command,
                "work_dir": effective_workdir or "(container default)",
            }

        except DockerException as e:
            logger.error(f"❌ [Docker] Failed to execute command in container: {e}")
            raise RuntimeError(f"Failed to execute command in container: {e}")

    def stop_container(self, agent_id: str, timeout: int = 10) -> None:
        """
        Stop a container gracefully.

        Args:
            agent_id: Agent identifier
            timeout: Seconds to wait before killing

        Raises:
            ValueError: If container not found
        """
        container = self.containers.get(agent_id)
        if not container:
            raise ValueError(f"No container found for agent {agent_id}")

        try:
            logger.info(f"🛑 [Docker] Stopping container {container.short_id} for agent {agent_id}")
            container.stop(timeout=timeout)
            logger.info("✅ [Docker] Container stopped successfully")
        except DockerException as e:
            logger.error(f"❌ [Docker] Failed to stop container for agent {agent_id}: {e}")

    def remove_container(self, agent_id: str, force: bool = False) -> None:
        """
        Remove a container.

        Args:
            agent_id: Agent identifier
            force: Force removal even if running

        Raises:
            ValueError: If container not found
        """
        container = self.containers.get(agent_id)
        if not container:
            raise ValueError(f"No container found for agent {agent_id}")

        try:
            container_id = container.short_id
            logger.info(f"🗑️  [Docker] Removing container {container_id} for agent {agent_id}")
            container.remove(force=force)
            del self.containers[agent_id]
            logger.info("✅ [Docker] Container removed successfully")
        except DockerException as e:
            logger.error(f"❌ [Docker] Failed to remove container for agent {agent_id}: {e}")

    def cleanup(self, agent_id: Optional[str] = None) -> None:
        """
        Clean up containers.

        Args:
            agent_id: If provided, cleanup specific agent. Otherwise cleanup all.
        """
        if agent_id:
            # Cleanup specific agent
            if agent_id in self.containers:
                logger.info(f"🧹 [Docker] Cleaning up container for agent {agent_id}")
                try:
                    self.stop_container(agent_id)
                    self.remove_container(agent_id, force=True)
                except Exception as e:
                    logger.error(f"❌ [Docker] Error cleaning up container for agent {agent_id}: {e}")
        else:
            # Cleanup all containers
            if self.containers:
                logger.info(f"🧹 [Docker] Cleaning up {len(self.containers)} container(s)")
            for aid in list(self.containers.keys()):
                try:
                    self.stop_container(aid)
                    self.remove_container(aid, force=True)
                except Exception as e:
                    logger.error(f"❌ [Docker] Error cleaning up container for agent {aid}: {e}")

    def log_container_info(self, agent_id: str) -> None:
        """
        Log detailed container information (useful for debugging).

        Args:
            agent_id: Agent identifier
        """
        container = self.containers.get(agent_id)
        if not container:
            logger.warning(f"⚠️ [Docker] No container found for agent {agent_id}")
            return

        try:
            container.reload()  # Refresh state

            logger.info(f"📊 [Docker] Container information for agent '{agent_id}':")
            logger.info(f"    ID: {container.short_id}")
            logger.info(f"    Name: {container.name}")
            logger.info(f"    Status: {container.status}")
            logger.info(f"    Network: {self.network_mode}")
            if self.memory_limit:
                logger.info(f"    Memory limit: {self.memory_limit}")
            if self.cpu_limit:
                logger.info(f"    CPU limit: {self.cpu_limit} cores")
        except Exception as e:
            logger.warning(f"⚠️ [Docker] Could not log container info: {e}")

    def __del__(self):
        """Cleanup all containers on deletion."""
        try:
            if hasattr(self, "containers") and self.containers:
                self.cleanup()
        except Exception:
            # Silently fail during cleanup - already logged in cleanup()
            pass
