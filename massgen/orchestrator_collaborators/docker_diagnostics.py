"""Docker diagnostics, extracted from Orchestrator.

Two stateless helpers for Docker-mode MCP failures:

- ``save_docker_logs_on_mcp_failure``: capture container state and logs to the
  session log directory when a Docker-based MCP server disconnects.
- ``get_docker_health``: read container health metrics for reliability tracing.

Both methods are tolerant of agents that don't use Docker mode (they no-op
when ``filesystem_manager.docker_manager`` is absent).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from massgen.logger_config import logger

if TYPE_CHECKING:
    from massgen.chat_agent import ChatAgent
    from massgen.orchestrator import Orchestrator


class DockerDiagnostics:
    """Capture Docker container state on MCP failures and read health metrics."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator  # back-ref kept for the standard pattern

    def save_docker_logs_on_mcp_failure(
        self,
        agent: ChatAgent,
        agent_id: str,
        mcp_status: str,
    ) -> None:
        """Save Docker container logs when MCP failure is detected."""
        try:
            if not hasattr(agent, "backend") or not hasattr(agent.backend, "filesystem_manager"):
                return

            fm = agent.backend.filesystem_manager
            if not fm or not hasattr(fm, "docker_manager") or not fm.docker_manager:
                return

            docker_manager = fm.docker_manager
            health = docker_manager.get_container_health(agent_id)
            if not health.get("exists"):
                logger.warning(
                    f"[Docker] Container not found for {agent_id} during MCP failure - may have been cleaned up",
                )
                return

            logger.info(
                f"[Docker] Container health for {agent_id} during MCP failure ({mcp_status}): "
                f"status={health.get('status')}, running={health.get('running')}, "
                f"exit_code={health.get('exit_code')}, oom_killed={health.get('oom_killed')}, "
                f"error={health.get('error')}",
            )

            # Lazy lookup via massgen.orchestrator so test patches at that namespace fire.
            from massgen import orchestrator as _orch_mod

            log_dir = _orch_mod.get_log_session_dir()
            if log_dir:
                timestamp = time.strftime("%H%M%S")
                log_filename = f"docker_logs_{agent_id}_{mcp_status}_{timestamp}.txt"
                log_path = log_dir / log_filename
                docker_manager.save_container_logs(agent_id, log_path, tail=500)

        except (OSError, AttributeError, KeyError) as e:
            logger.warning(
                f"[Docker] Failed to save container logs on MCP failure: {e}",
            )

    def get_docker_health(
        self,
        agent: ChatAgent,
        agent_id: str,
    ) -> dict[str, Any] | None:
        """Get Docker container health info for reliability metrics."""
        try:
            if not hasattr(agent, "backend") or not hasattr(agent.backend, "filesystem_manager"):
                return None

            fm = agent.backend.filesystem_manager
            if not fm or not hasattr(fm, "docker_manager") or not fm.docker_manager:
                return None

            return fm.docker_manager.get_container_health(agent_id)
        except (AttributeError, KeyError) as e:
            logger.debug(f"[Docker] Failed to get container health: {e}")
            return None
