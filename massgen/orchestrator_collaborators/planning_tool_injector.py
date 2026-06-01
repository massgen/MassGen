"""Planning MCP tool injection, extracted from Orchestrator.

Mutates backend ``mcp_servers`` (list-or-dict, same pattern as
:class:`BroadcastToolInitializer` / :class:`CheckpointCoordinator`) and is the
SOLE WRITER of ``orchestrator._planning_injection_dirs``. The future
ChecklistGateManager reads that dict, so the orchestrator back-ref is the
single source of truth.

Test-compat note: ``massgen.orchestrator.get_log_session_dir`` is patched in
several tests. We resolve it lazily from the orchestrator module at call time
so monkeypatches keep working after extraction.
"""

from __future__ import annotations

import tempfile as _tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from massgen.logger_config import logger

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


def _resolve_log_session_dir():
    """Look up ``get_log_session_dir`` through the orchestrator module so
    existing ``patch('massgen.orchestrator.get_log_session_dir', ...)`` calls
    in the test suite continue to take effect after extraction.
    """
    from massgen import orchestrator as _orch_mod

    return _orch_mod.get_log_session_dir()


class PlanningToolInjector:
    """Inject the planning MCP server into each agent's backend config."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    def inject_planning_tools_for_all_agents(self) -> None:
        for agent_id, agent in self._orchestrator.agents.items():
            self.inject_planning_tools_for_agent(agent_id, agent)

    def planning_server_name(self, agent_id: str) -> str:
        token = self._orchestrator.coordination_tracker.get_path_token(agent_id)
        return f"planning_{token}"

    def inject_planning_tools_for_agent(self, agent_id: str, agent: Any) -> None:
        logger.info(f"[Orchestrator] Injecting planning tools for agent: {agent_id}")

        planning_mcp_config = self.create_planning_mcp_config(agent_id, agent)
        logger.info(
            f"[Orchestrator] Created planning MCP config: {planning_mcp_config['name']}",
        )

        mcp_servers = agent.backend.config.get("mcp_servers", [])
        logger.info(
            f"[Orchestrator] Existing MCP servers for {agent_id}: {type(mcp_servers)} with " f"{len(mcp_servers) if isinstance(mcp_servers, (list, dict)) else 0} entries",
        )

        if isinstance(mcp_servers, dict):
            logger.info("[Orchestrator] Using dict format for MCP servers")
            mcp_servers[self.planning_server_name(agent_id)] = planning_mcp_config
        else:
            logger.info("[Orchestrator] Using list format for MCP servers")
            if not isinstance(mcp_servers, list):
                mcp_servers = []
            mcp_servers.append(planning_mcp_config)

        agent.backend.config["mcp_servers"] = mcp_servers
        logger.info(
            f"[Orchestrator] Updated MCP servers for {agent_id}, now has " f"{len(mcp_servers) if isinstance(mcp_servers, (list, dict)) else 0} servers",
        )

    def create_planning_mcp_config(self, agent_id: str, agent: Any) -> dict[str, Any]:
        orch = self._orchestrator
        from pathlib import Path as PathlibPath

        import massgen.mcp_tools.planning._planning_mcp_server as planning_module

        script_path = PathlibPath(planning_module.__file__).resolve()

        args = [
            "run",
            f"{script_path}:create_server",
            "--",
            "--agent-id",
            agent_id,
            "--orchestrator-id",
            orch.orchestrator_id,
        ]

        logger.info(
            f"[Orchestrator] Checking task_planning_filesystem_mode for {agent_id}",
        )
        has_coord_config = hasattr(orch.config, "coordination_config")
        logger.info(f"[Orchestrator] Has coordination_config: {has_coord_config}")

        if has_coord_config:
            has_filesystem_mode = hasattr(
                orch.config.coordination_config,
                "task_planning_filesystem_mode",
            )
            logger.info(
                f"[Orchestrator] Has task_planning_filesystem_mode attr: {has_filesystem_mode}",
            )
            if has_filesystem_mode:
                value = orch.config.coordination_config.task_planning_filesystem_mode
                logger.info(
                    f"[Orchestrator] task_planning_filesystem_mode value: {value}",
                )

        filesystem_mode_enabled = (
            hasattr(orch.config, "coordination_config")
            and hasattr(
                orch.config.coordination_config,
                "task_planning_filesystem_mode",
            )
            and orch.config.coordination_config.task_planning_filesystem_mode
        )

        if filesystem_mode_enabled:
            logger.info("[Orchestrator] task_planning_filesystem_mode is enabled")
            if hasattr(agent, "backend") and hasattr(agent.backend, "filesystem_manager") and agent.backend.filesystem_manager:
                if agent.backend.filesystem_manager.cwd:
                    workspace_path = str(agent.backend.filesystem_manager.cwd)
                    args.extend(["--workspace-path", workspace_path])
                    logger.info(
                        f"[Orchestrator] Enabling filesystem mode for task planning: {workspace_path}",
                    )
                    _tracker = getattr(orch, "coordination_tracker", None)
                    if _tracker is not None and hasattr(_tracker, "get_path_token"):
                        workspace_token = _tracker.get_path_token(agent_id)
                        args.extend(["--workspace-token", workspace_token])
                else:
                    logger.warning(
                        f"[Orchestrator] Agent {agent_id} filesystem_manager.cwd is None",
                    )
            else:
                logger.warning(
                    f"[Orchestrator] Agent {agent_id} has no filesystem_manager",
                )

        skills_enabled = hasattr(orch.config, "coordination_config") and hasattr(orch.config.coordination_config, "use_skills") and orch.config.coordination_config.use_skills
        if skills_enabled:
            args.append("--skills-enabled")

        round_learning_capture_enabled = orch._is_round_learning_capture_enabled()

        auto_discovery_enabled = False
        if hasattr(agent, "backend") and hasattr(agent.backend, "config"):
            auto_discovery_enabled = agent.backend.config.get(
                "auto_discover_custom_tools",
                False,
            )
        if auto_discovery_enabled and round_learning_capture_enabled:
            args.append("--auto-discovery-enabled")

        memory_enabled = (
            hasattr(orch.config, "coordination_config")
            and hasattr(
                orch.config.coordination_config,
                "enable_memory_filesystem_mode",
            )
            and orch.config.coordination_config.enable_memory_filesystem_mode
        )
        if memory_enabled and round_learning_capture_enabled:
            args.append("--memory-enabled")
        if memory_enabled and orch._is_round_verification_capture_enabled() and not round_learning_capture_enabled:
            args.append("--verification-memory-enabled")

        coordination_config = getattr(orch.config, "coordination_config", None)
        write_mode = getattr(coordination_config, "write_mode", None) if coordination_config else None
        use_two_tier_workspace = False
        if not (write_mode and write_mode != "legacy"):
            use_two_tier_workspace = bool(
                getattr(coordination_config, "use_two_tier_workspace", False),
            )
        logger.info(
            f"[Orchestrator] use_two_tier_workspace value for {agent_id}: " f"{use_two_tier_workspace} (write_mode={write_mode})",
        )
        if use_two_tier_workspace:
            args.append("--use-two-tier-workspace")
            logger.info(
                f"[Orchestrator] Adding --use-two-tier-workspace flag to planning MCP for {agent_id}",
            )

        _is_docker = hasattr(agent, "backend") and hasattr(agent.backend, "_is_docker_mode") and agent.backend._is_docker_mode
        if _is_docker and hasattr(agent, "backend") and hasattr(agent.backend, "filesystem_manager") and agent.backend.filesystem_manager and agent.backend.filesystem_manager.cwd:
            ws_root = Path(agent.backend.filesystem_manager.cwd)
            injection_dir = (ws_root / ".massgen_scratch" / "planning_injection" / agent_id).resolve()
        else:
            log_dir = _resolve_log_session_dir()
            if log_dir:
                injection_dir = (log_dir / "planning_injection" / agent_id).resolve()
            else:
                injection_dir = Path(_tempfile.mkdtemp(prefix=f"massgen_plan_inject_{agent_id}_"))
        injection_dir.mkdir(parents=True, exist_ok=True)
        if not hasattr(orch, "_planning_injection_dirs"):
            orch._planning_injection_dirs = {}
        orch._planning_injection_dirs[agent_id] = injection_dir
        args.extend(["--injection-dir", str(injection_dir)])

        if hasattr(agent, "backend") and hasattr(agent.backend, "supports_mcp_server_hooks") and agent.backend.supports_mcp_server_hooks() and hasattr(agent.backend, "get_hook_dir"):
            hook_dir = agent.backend.get_hook_dir()
            args.extend(["--hook-dir", str(hook_dir)])

        logger.info(f"[Orchestrator] Planning MCP args for {agent_id}: {args}")

        config = {
            "name": self.planning_server_name(agent_id),
            "type": "stdio",
            "command": "fastmcp",
            "args": args,
            "env": {
                "FASTMCP_SHOW_CLI_BANNER": "false",
            },
        }

        return config

    def write_planning_injection(self, agent_id: str, task_plan: list[dict]) -> None:
        orch = self._orchestrator
        if agent_id not in orch._planning_injection_dirs:
            return

        from massgen.mcp_tools.checklist_tools_server import _write_inject_file

        _write_inject_file(orch._planning_injection_dirs[agent_id], task_plan)
        logger.info(
            f"[Orchestrator] Wrote planning injection for {agent_id}: {len(task_plan)} tasks",
        )
