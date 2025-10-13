# -*- coding: utf-8 -*-
"""
Docker Container Manager for MassGen

Manages Docker containers that run MCP servers in isolated environments.
This provides strong filesystem isolation by running ALL MCP servers
(filesystem, workspace_tools, command_line) inside containers.
"""

import logging
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
    Manages Docker containers for isolated MCP server execution.

    Each agent can have its own Docker container with:
    - Volume mounts for workspace and context paths
    - Network isolation
    - Resource limits (CPU, memory)
    - All MCP servers running inside
    """

    def __init__(
        self,
        image: str = "massgen/mcp-runtime:latest",
        network_mode: str = "none",
        memory_limit: Optional[str] = None,
        cpu_limit: Optional[float] = None,
    ):
        """
        Initialize Docker manager.

        Args:
            image: Docker image to use for containers
            network_mode: Network mode (none/bridge/host)
            memory_limit: Memory limit (e.g., "2g", "512m")
            cpu_limit: CPU limit (e.g., 2.0 for 2 CPUs)

        Raises:
            RuntimeError: If Docker is not available
        """
        if not DOCKER_AVAILABLE:
            raise RuntimeError("Docker Python library not available. Install with: pip install docker")

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

            logger.info(f"🐳 [Docker] Client initialized successfully")
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
            logger.info(f"Docker image '{self.image}' found locally")
        except ImageNotFound:
            logger.info(f"Docker image '{self.image}' not found locally, pulling...")
            try:
                self.client.images.pull(self.image)
                logger.info(f"Successfully pulled image '{self.image}'")
            except DockerException as e:
                raise RuntimeError(f"Failed to pull Docker image '{self.image}': {e}")

    def create_container(
        self,
        agent_id: str,
        workspace_path: Path,
        temp_workspace_path: Optional[Path] = None,
        context_paths: Optional[List[Dict[str, Any]]] = None,
        massgen_package_path: Optional[Path] = None,
    ) -> str:
        """
        Create and start a Docker container for an agent.

        Args:
            agent_id: Unique identifier for the agent
            workspace_path: Path to agent's workspace (mounted as /workspace)
            temp_workspace_path: Path to shared reference workspace (mounted as /temp_workspaces)
            context_paths: List of context path dicts with 'path' and 'permission' keys
            massgen_package_path: Path to massgen package directory (mounted as /app/massgen for MCP servers)

        Returns:
            Container ID

        Raises:
            RuntimeError: If container creation fails
        """
        if agent_id in self.containers:
            logger.warning(f"Container for agent {agent_id} already exists")
            return self.containers[agent_id].id

        # Ensure image exists
        self.ensure_image_exists()

        # Check for and remove any existing container with the same name
        container_name = f"massgen-{agent_id}"
        try:
            existing = self.client.containers.get(container_name)
            logger.warning(
                f"🔄 [Docker] Found existing container '{container_name}' (id: {existing.short_id}), removing it"
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
        volumes = {}
        mount_info = []

        # Mount agent workspace (read-write)
        workspace_path = workspace_path.resolve()
        volumes[str(workspace_path)] = {"bind": "/workspace", "mode": "rw"}
        mount_info.append(f"      /workspace ← {workspace_path} (rw)")

        # Mount temp workspace (read-only)
        if temp_workspace_path:
            temp_workspace_path = temp_workspace_path.resolve()
            volumes[str(temp_workspace_path)] = {"bind": "/temp_workspaces", "mode": "ro"}
            mount_info.append(f"      /temp_workspaces ← {temp_workspace_path} (ro)")

        # Mount context paths
        if context_paths:
            for i, ctx_path_config in enumerate(context_paths):
                ctx_path = Path(ctx_path_config["path"]).resolve()
                permission = ctx_path_config.get("permission", "read")
                mode = "rw" if permission == "write" else "ro"

                # Use a sanitized name for the mount point
                mount_name = ctx_path_config.get("name", f"context_{i}")
                mount_point = f"/context/{mount_name}"

                volumes[str(ctx_path)] = {"bind": mount_point, "mode": mode}
                mount_info.append(f"      {mount_point} ← {ctx_path} ({mode})")

        # Mount massgen package (for MCP server scripts when running inside Docker)
        if massgen_package_path:
            massgen_package_path = massgen_package_path.resolve()
            volumes[str(massgen_package_path)] = {"bind": "/app/massgen", "mode": "ro"}
            mount_info.append(f"      /app/massgen ← {massgen_package_path} (ro)")

        # Log volume mounts
        if mount_info:
            logger.info(f"    Volume mounts:")
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
            "working_dir": "/workspace",
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

            logger.info(f"✅ [Docker] Container created successfully")
            logger.info(f"    Container ID: {container.short_id}")
            logger.info(f"    Container name: {container_name}")
            logger.info(f"    Status: {status}")

            # Show how to inspect the container
            logger.debug(f"💡 [Docker] Inspect container: docker inspect {container.short_id}")
            logger.debug(f"💡 [Docker] View logs: docker logs {container.short_id}")
            logger.debug(f"💡 [Docker] Execute commands: docker exec -it {container.short_id} /bin/bash")

            return container.id

        except DockerException as e:
            logger.error(f"❌ [Docker] Failed to create container for agent {agent_id}")
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
        command: List[str],
        workdir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute a command inside the container.

        Args:
            agent_id: Agent identifier
            command: Command to execute (as list of strings)
            workdir: Working directory inside container

        Returns:
            Dictionary with exit_code and output

        Raises:
            ValueError: If container not found
            RuntimeError: If execution fails
        """
        container = self.containers.get(agent_id)
        if not container:
            raise ValueError(f"No container found for agent {agent_id}")

        try:
            exec_config = {"cmd": command, "workdir": workdir or "/workspace"}

            cmd_str = " ".join(command)
            logger.debug(f"🔧 [Docker] Executing in container {container.short_id}: {cmd_str}")

            exit_code, output = container.exec_run(**exec_config)

            if exit_code != 0:
                logger.debug(f"⚠️ [Docker] Command exited with code {exit_code}")

            return {
                "exit_code": exit_code,
                "output": output.decode("utf-8") if isinstance(output, bytes) else output,
            }

        except DockerException as e:
            logger.error(f"❌ [Docker] Failed to execute command in container: {e}")
            raise RuntimeError(f"Failed to execute command in container: {e}")

    def stop_container(self, agent_id: str, timeout: int = 10) -> None:
        """
        Stop a container.

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
            logger.info(f"✅ [Docker] Container stopped successfully")
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
            logger.info(f"🗑️ [Docker] Removing container {container_id} for agent {agent_id}")
            container.remove(force=force)
            del self.containers[agent_id]
            logger.info(f"✅ [Docker] Container removed successfully")
        except DockerException as e:
            logger.error(f"❌ [Docker] Failed to remove container for agent {agent_id}: {e}")

    def save_container_logs(self, agent_id: str, log_path: Path) -> None:
        """
        Save container logs to a file for debugging.

        Args:
            agent_id: Agent identifier
            log_path: Path to save logs to
        """
        container = self.containers.get(agent_id)
        if not container:
            logger.warning(f"⚠️ [Docker] No container found for agent {agent_id} to save logs")
            return

        try:
            logger.info(f"📝 [Docker] Saving container logs to {log_path}")
            logs = container.logs(stdout=True, stderr=True, timestamps=True)

            log_path.parent.mkdir(parents=True, exist_ok=True)
            log_path.write_bytes(logs)

            logger.info(f"✅ [Docker] Container logs saved successfully")
        except DockerException as e:
            logger.warning(f"⚠️ [Docker] Failed to save container logs for agent {agent_id}: {e}")

    def cleanup(self, agent_id: Optional[str] = None, save_logs_to: Optional[Path] = None) -> None:
        """
        Clean up containers.

        Args:
            agent_id: If provided, cleanup specific agent. Otherwise cleanup all.
            save_logs_to: Optional path to save container logs before cleanup
        """
        if agent_id:
            # Cleanup specific agent
            if agent_id in self.containers:
                logger.info(f"🧹 [Docker] Cleaning up container for agent {agent_id}")
                try:
                    # Save logs if path provided
                    if save_logs_to:
                        self.save_container_logs(agent_id, save_logs_to)

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
                    # Save logs if path provided (construct agent-specific path)
                    if save_logs_to:
                        agent_log_path = save_logs_to.parent / f"{aid}_docker.log"
                        self.save_container_logs(aid, agent_log_path)

                    self.stop_container(aid)
                    self.remove_container(aid, force=True)
                except Exception as e:
                    logger.error(f"❌ [Docker] Error cleaning up container for agent {aid}: {e}")

    def get_container_stats(self, agent_id: str) -> Dict[str, Any]:
        """
        Get resource usage statistics for a container.

        Args:
            agent_id: Agent identifier

        Returns:
            Dictionary with CPU, memory, and network stats

        Raises:
            ValueError: If container not found
        """
        container = self.containers.get(agent_id)
        if not container:
            raise ValueError(f"No container found for agent {agent_id}")

        try:
            stats = container.stats(stream=False)
            return stats
        except DockerException as e:
            logger.error(f"❌ [Docker] Failed to get stats for container {agent_id}: {e}")
            return {}

    def get_container_info(self, agent_id: str) -> Dict[str, Any]:
        """
        Get detailed information about a container for display/logging.

        Args:
            agent_id: Agent identifier

        Returns:
            Dictionary with container information

        Raises:
            ValueError: If container not found
        """
        container = self.containers.get(agent_id)
        if not container:
            raise ValueError(f"No container found for agent {agent_id}")

        try:
            container.reload()  # Refresh state

            info = {
                "container_id": container.id,
                "short_id": container.short_id,
                "name": container.name,
                "status": container.status,
                "image": container.image.tags[0] if container.image.tags else self.image,
                "created": container.attrs.get("Created", "unknown"),
                "ports": container.ports,
                "network_mode": self.network_mode,
            }

            # Add resource limits if configured
            if self.memory_limit:
                info["memory_limit"] = self.memory_limit
            if self.cpu_limit:
                info["cpu_limit"] = f"{self.cpu_limit} cores"

            return info

        except DockerException as e:
            logger.error(f"❌ [Docker] Failed to get info for container {agent_id}: {e}")
            return {}

    def log_container_info(self, agent_id: str) -> None:
        """
        Log detailed container information (useful for debugging).

        Args:
            agent_id: Agent identifier
        """
        try:
            info = self.get_container_info(agent_id)
            if info:
                logger.info(f"📊 [Docker] Container information for agent '{agent_id}':")
                logger.info(f"    ID: {info['short_id']}")
                logger.info(f"    Name: {info['name']}")
                logger.info(f"    Status: {info['status']}")
                logger.info(f"    Image: {info['image']}")
                logger.info(f"    Network: {info['network_mode']}")
                if "memory_limit" in info:
                    logger.info(f"    Memory limit: {info['memory_limit']}")
                if "cpu_limit" in info:
                    logger.info(f"    CPU limit: {info['cpu_limit']}")
        except Exception as e:
            logger.warning(f"⚠️ [Docker] Could not log container info: {e}")

    def __del__(self):
        """Cleanup all containers on deletion."""
        try:
            self.cleanup()
        except Exception as e:
            logger.error(f"Error during DockerManager cleanup: {e}")
