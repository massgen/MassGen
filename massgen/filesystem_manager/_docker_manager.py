# -*- coding: utf-8 -*-
"""
Docker Container Manager for MassGen

Manages Docker containers for isolated command execution.
Provides strong filesystem isolation by executing commands inside containers
while keeping MCP servers on the host.
"""

import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

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
    ):
        """
        Initialize Docker manager.

        Args:
            image: Docker image to use for containers
            network_mode: Network mode (none/bridge/host)
            memory_limit: Memory limit (e.g., "2g", "512m")
            cpu_limit: CPU limit (e.g., 2.0 for 2 CPUs)
            enable_sudo: Enable sudo access in containers (WARNING: less secure, see docs)

        Raises:
            RuntimeError: If Docker is not available or cannot connect
        """
        if not DOCKER_AVAILABLE:
            raise RuntimeError("Docker Python library not available. Install with: pip install docker")

        # If sudo is enabled and user is using default image, switch to sudo variant
        self.enable_sudo = enable_sudo
        if enable_sudo and image == "massgen/mcp-runtime:latest":
            self.image = "massgen/mcp-runtime-sudo:latest"
            logger.warning(
                "⚠️ [Docker] SECURITY WARNING: Sudo enabled - using 'massgen/mcp-runtime-sudo:latest' image.",
            )
            logger.warning(
                "    This reduces security compared to the default image. " "Prefer building custom images with pre-installed packages.",
            )
            logger.warning(
                "    See: https://docs.massgen.ai/docker-security for best practices.",
            )
        elif enable_sudo:
            logger.warning(
                "⚠️ [Docker] SECURITY WARNING: Sudo enabled with custom image. " "Ensure your image properly configures sudo access.",
            )
        else:
            self.image = image

        self.network_mode = network_mode
        self.memory_limit = memory_limit
        self.cpu_limit = cpu_limit

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
                    # Timeout occurred
                    logger.warning(f"⚠️ [Docker] Command timed out after {timeout}s: {command}")
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
