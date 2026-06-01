"""Checkpoint-coordination tooling, extracted from Orchestrator.

Owns the lifecycle of the checkpoint workflow tool, the standalone
checkpoint MCP injection (single-agent only), and ``_activate_checkpoint``
(spawn subprocess + relay events). All checkpoint state lives on the
orchestrator (``_main_agent_id``, ``_checkpoint_active``, ``_checkpoint_task``,
``_checkpoint_number``, ``_checkpoint_participants``) and is mutated via the
back-ref so the streaming/AgentOrchestrationSetup paths continue to read a
single source of truth.

Backend ``mcp_servers`` mutations follow the same dual-write pattern used by
:class:`BroadcastToolInitializer`: we update ``backend.config['mcp_servers']``
*and* the runtime ``backend.mcp_servers`` list, because the backend often binds
the latter to a separate list at its own ``__init__``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from massgen.coordination_tracker import EventType
from massgen.logger_config import get_event_emitter, logger

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


_STANDALONE_CHECKPOINT_SERVER_NAME = "massgen_checkpoint_standalone"


class CheckpointCoordinator:
    """Checkpoint-mode tooling + subprocess orchestration."""

    STANDALONE_CHECKPOINT_SERVER_NAME = _STANDALONE_CHECKPOINT_SERVER_NAME

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    def init_checkpoint_tool(self) -> None:
        """Set up checkpoint tool for the main agent.

        The checkpoint tool schema is provided by the CheckpointToolkit
        (workflow toolkit) -- no MCP server needed. Execution is handled by
        the orchestrator's streaming loop interception which spawns a
        subprocess via CheckpointSubprocessManager.
        """
        orch = self._orchestrator
        if not orch._main_agent_id:
            return
        logger.info(
            f"[Checkpoint] Checkpoint tool active for main agent " f"'{orch._main_agent_id}' (via workflow toolkit + interception)",
        )

    def strip_standalone_checkpoint_from_all_agents(self) -> None:
        """Remove the standalone checkpoint MCP from every agent's backend."""
        orch = self._orchestrator
        name = self.STANDALONE_CHECKPOINT_SERVER_NAME
        for agent in orch.agents.values():
            backend = getattr(agent, "backend", None)
            if backend is None or not hasattr(backend, "config") or not isinstance(backend.config, dict):
                continue
            servers = backend.config.get("mcp_servers")
            if isinstance(servers, list):
                backend.config["mcp_servers"] = [s for s in servers if not (isinstance(s, dict) and s.get("name") == name)]
            elif isinstance(servers, dict):
                servers.pop(name, None)
            if hasattr(backend, "mcp_servers"):
                runtime = backend.mcp_servers
                if isinstance(runtime, list):
                    backend.mcp_servers = [s for s in runtime if not (isinstance(s, dict) and s.get("name") == name)]
                elif isinstance(runtime, dict):
                    runtime.pop(name, None)

    def init_standalone_checkpoint_tool(self) -> None:
        """Inject the standalone checkpoint MCP into a single agent's backend."""
        orch = self._orchestrator
        config = getattr(orch, "config", None)
        coord = getattr(config, "coordination_config", None) if config is not None else None
        if coord is None or not getattr(coord, "standalone_checkpoint_enabled", False):
            return
        if len(orch.agents) != 1:
            self.strip_standalone_checkpoint_from_all_agents()
            logger.warning(
                "[StandaloneCheckpoint] enabled but parent has %d agents; this mode is " "single-agent only — skipping injection (any prior registration stripped)",
                len(orch.agents),
            )
            return
        team_config = getattr(coord, "standalone_checkpoint_team_config", None)
        if not team_config:
            logger.warning(
                "[StandaloneCheckpoint] enabled but no team_config provided; skipping injection",
            )
            return

        from massgen.mcp_tools.subrun_utils import (
            build_standalone_checkpoint_mcp_config,
        )

        agent = next(iter(orch.agents.values()))
        default_workspace_dir: str | None = None
        default_trajectory_path: str | None = None
        try:
            fs = getattr(agent.backend, "filesystem_manager", None)
            if fs is not None and hasattr(fs, "get_current_workspace"):
                ws = fs.get_current_workspace()
                if ws:
                    default_workspace_dir = str(ws)
        except Exception as e:
            logger.debug(f"[StandaloneCheckpoint] could not resolve workspace_dir: {e}")
        try:
            from massgen.logger_config import get_log_session_dir

            log_dir = get_log_session_dir()
            if log_dir:
                default_trajectory_path = str(Path(log_dir) / "events.jsonl")
        except Exception as e:
            logger.debug(f"[StandaloneCheckpoint] could not resolve trajectory_path: {e}")

        server_cfg = build_standalone_checkpoint_mcp_config(
            team_config_path=str(team_config),
            mode=getattr(coord, "standalone_checkpoint_mode", "generate"),
            single_checkpoint=getattr(coord, "standalone_checkpoint_single", False),
            include_workspace_context=getattr(coord, "standalone_checkpoint_include_workspace_context", False),
            default_workspace_dir=default_workspace_dir,
            default_trajectory_path=default_trajectory_path,
        )
        backend = getattr(agent, "backend", None)
        if backend is None or not hasattr(backend, "config") or not isinstance(backend.config, dict):
            logger.warning(
                "[StandaloneCheckpoint] agent backend has no dict config; skipping injection",
            )
            return
        servers = backend.config.setdefault("mcp_servers", [])
        if isinstance(servers, list):
            if any(isinstance(s, dict) and s.get("name") == server_cfg["name"] for s in servers):
                return
            servers.append(server_cfg)
        elif isinstance(servers, dict):
            if server_cfg["name"] in servers:
                return
            servers[server_cfg["name"]] = server_cfg
        else:
            logger.warning(
                "[StandaloneCheckpoint] unexpected mcp_servers type %s; skipping injection",
                type(servers).__name__,
            )
            return
        if hasattr(backend, "mcp_servers"):
            runtime = backend.mcp_servers
            if isinstance(runtime, list):
                if not any(isinstance(s, dict) and s.get("name") == server_cfg["name"] for s in runtime):
                    runtime.append(server_cfg)
            elif isinstance(runtime, dict):
                runtime.setdefault(server_cfg["name"], server_cfg)
        logger.info(
            "[StandaloneCheckpoint] Registered massgen_checkpoint_standalone for sole agent (team_config=%s)",
            team_config,
        )

    def set_main_agent(self, agent_id: str) -> None:
        """Designate an agent as the main orchestrating agent."""
        orch = self._orchestrator
        if agent_id not in orch.agents:
            raise ValueError(
                f"Cannot set main_agent '{agent_id}': " f"not found in agents {list(orch.agents.keys())}",
            )
        orch._main_agent_id = agent_id
        logger.info(f"[Checkpoint] Main agent set to '{agent_id}'")
        self.init_checkpoint_tool()
        self.init_standalone_checkpoint_tool()

    def is_checkpoint_mode(self) -> bool:
        return self._orchestrator._main_agent_id is not None

    def is_agent_active_in_current_mode(self, agent_id: str) -> bool:
        orch = self._orchestrator
        if not self.is_checkpoint_mode():
            return True
        if orch._checkpoint_active:
            return True
        return agent_id == orch._main_agent_id

    async def activate_checkpoint(self, signal: dict[str, Any]) -> str:
        orch = self._orchestrator
        from massgen.mcp_tools.checkpoint._subprocess_manager import (
            CheckpointSubprocessManager,
        )

        orch._checkpoint_active = True
        orch._checkpoint_number += 1
        orch._checkpoint_task = signal.get("task", "")

        orch.coordination_tracker._add_event(
            EventType.CHECKPOINT_CALLED,
            agent_id=orch._main_agent_id,
            details=f"Checkpoint #{orch._checkpoint_number}: {orch._checkpoint_task[:100]}",
            context={
                "task": orch._checkpoint_task,
                "context": signal.get("context", ""),
            },
        )

        orch._checkpoint_participants = {}
        for aid in orch.agents:
            display_id = f"{aid}-ckpt{orch._checkpoint_number}"
            model_name = ""
            if hasattr(orch.agents[aid].backend, "get_model_name"):
                try:
                    model_name = orch.agents[aid].backend.get_model_name()
                except Exception:
                    pass
            orch._checkpoint_participants[display_id] = {
                "real_agent_id": aid,
                "model": model_name,
            }

        _emitter = get_event_emitter()
        if _emitter:
            _emitter.emit_checkpoint_activated(
                checkpoint_number=orch._checkpoint_number,
                task=orch._checkpoint_task,
                participants=orch._checkpoint_participants,
                main_agent_id=orch._main_agent_id,
            )

        main_agent = orch.agents.get(orch._main_agent_id)
        parent_workspace = None
        if main_agent:
            parent_workspace = getattr(
                getattr(main_agent.backend, "filesystem_manager", None),
                "cwd",
                None,
            )

        if not parent_workspace:
            logger.error("[Checkpoint] No parent workspace for subprocess")
            orch._checkpoint_active = False
            return "Checkpoint failed: no workspace available"

        async def _relay_event(event):
            if _emitter:
                _emitter.emit(event)

        manager = CheckpointSubprocessManager(
            parent_config=orch._raw_config_dict,
            parent_workspace=parent_workspace,
            checkpoint_number=orch._checkpoint_number,
        )

        result = await manager.spawn(
            signal=signal,
            on_event=_relay_event,
        )

        consensus = result.get("output", "")
        workspace_changes = result.get("workspace_changes", [])

        manager._copy_subprocess_logs()

        if result.get("success"):
            manager.cleanup()
        else:
            error = result.get("error", "Unknown error")
            consensus = f"Checkpoint failed: {error}"
            ws_path = manager._checkpoint_workspace
            logger.error(
                f"[Checkpoint] Subprocess failed: {error}. " f"Workspace preserved at: {ws_path}",
            )

        orch.coordination_tracker._add_event(
            EventType.CHECKPOINT_COMPLETED,
            agent_id=orch._main_agent_id,
            details=f"Checkpoint #{orch._checkpoint_number} completed",
            context={
                "consensus_preview": consensus[:200] if consensus else "",
                "files_changed": len(workspace_changes),
            },
        )

        if _emitter:
            _emitter.emit_checkpoint_completed(
                checkpoint_number=orch._checkpoint_number,
                consensus=consensus,
                main_agent_id=orch._main_agent_id,
            )

        orch._checkpoint_active = False
        orch._checkpoint_participants = {}

        logger.info(
            f"[Checkpoint] Completed checkpoint #{orch._checkpoint_number}: " f"{orch._checkpoint_task[:80]}",
        )

        return consensus
