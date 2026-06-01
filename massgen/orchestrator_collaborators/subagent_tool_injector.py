"""Subagent MCP tool injection, extracted from Orchestrator.

Owns the wiring that adds the per-agent subagent MCP server to each agent's
backend ``mcp_servers`` configuration and sets up TUI spawn callbacks.

Notes:

* ``_subagent_server_name`` is a SHARED NAME HELPER used by the orchestrator
  streaming loop, the :class:`SubagentLifecycleCoordinator` collaborator, and
  several tests. The orchestrator keeps a thin delegator so existing call
  sites continue to work.
* ``setup_subagent_spawn_callbacks`` is public and called externally
  (``CoordinationUI.set_orchestrator`` and ``test_checklist_criteria_presets``)
  — the orchestrator retains a thin delegator.
* ``_subagent_launch_watcher`` is OWNED here (started lazily) but STOPPED by
  :class:`ActiveCoordinationCleanup`. Both collaborators must touch the
  orchestrator attribute (``orch._subagent_launch_watcher``), not a local copy,
  so both see the same handle.
* Backend ``mcp_servers`` mutation follows the list-or-dict pattern already
  used by :class:`BroadcastToolInitializer`, :class:`CheckpointCoordinator`,
  and :class:`PlanningToolInjector`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from massgen.logger_config import logger

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


def _resolve_log_session_dir():
    """Look up ``get_log_session_dir`` through the orchestrator module so
    tests that patch ``massgen.orchestrator.get_log_session_dir`` keep working.
    """
    from massgen import orchestrator as _orch_mod

    return _orch_mod.get_log_session_dir()


class SubagentToolInjector:
    """Inject subagent MCP servers into agent backends and manage spawn callbacks."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    # ------------------------------------------------------------------
    # Shared name helper
    # ------------------------------------------------------------------
    def subagent_server_name(self, agent_id: str) -> str:
        """Return the anonymous MCP server name for this agent's subagent tools."""
        token = self._orchestrator.coordination_tracker.get_path_token(agent_id)
        return f"subagent_{token}"

    # ------------------------------------------------------------------
    # Injection
    # ------------------------------------------------------------------
    def inject_subagent_tools_for_all_agents(self) -> None:
        """Inject subagent MCP tools into all agents."""
        for agent_id, agent in self._orchestrator.agents.items():
            self.inject_subagent_tools_for_agent(agent_id, agent)

    def inject_subagent_tools_for_agent(self, agent_id: str, agent: Any) -> None:
        """Inject subagent MCP tools into a specific agent."""
        if not hasattr(agent, "backend") or not hasattr(
            agent.backend,
            "filesystem_manager",
        ):
            logger.warning(
                f"[Orchestrator] Agent {agent_id} has no filesystem_manager, skipping subagent tools",
            )
            return

        if not agent.backend.filesystem_manager:
            logger.warning(
                f"[Orchestrator] Agent {agent_id} filesystem_manager is None, skipping subagent tools",
            )
            return

        if not agent.backend.filesystem_manager.cwd:
            logger.warning(
                f"[Orchestrator] Agent {agent_id} filesystem_manager.cwd is None, skipping subagent tools",
            )
            return

        logger.info(f"[Orchestrator] Injecting subagent tools for agent: {agent_id}")

        subagent_mcp_config = self.create_subagent_mcp_config(agent_id, agent)
        logger.info(
            f"[Orchestrator] Created subagent MCP config: {subagent_mcp_config['name']}",
        )

        mcp_servers = agent.backend.config.get("mcp_servers", [])
        logger.info(
            f"[Orchestrator] Existing MCP servers for {agent_id}: {type(mcp_servers)} with " f"{len(mcp_servers) if isinstance(mcp_servers, (list, dict)) else 0} entries",
        )

        if isinstance(mcp_servers, dict):
            logger.info("[Orchestrator] Using dict format for MCP servers")
            mcp_servers[self.subagent_server_name(agent_id)] = subagent_mcp_config
        else:
            logger.info("[Orchestrator] Using list format for MCP servers")
            if not isinstance(mcp_servers, list):
                mcp_servers = []
            mcp_servers.append(subagent_mcp_config)

        agent.backend.config["mcp_servers"] = mcp_servers
        logger.info(
            f"[Orchestrator] Updated MCP servers for {agent_id}, now has " f"{len(mcp_servers) if isinstance(mcp_servers, (list, dict)) else 0} servers",
        )

    # ------------------------------------------------------------------
    # Spawn-callback setup
    # ------------------------------------------------------------------
    def setup_subagent_spawn_callbacks(self) -> None:
        """Set up subagent spawn callbacks for all agents.

        Must be called AFTER ``coordination_ui`` is set on the orchestrator,
        so callbacks can reach the TUI display.
        """
        orch = self._orchestrator
        if not hasattr(orch, "coordination_ui") or not orch.coordination_ui:
            logger.debug("[Orchestrator] No coordination_ui, skipping subagent spawn callback setup")
            return

        for agent_id, agent in orch.agents.items():
            if hasattr(agent, "backend") and hasattr(agent.backend, "set_subagent_spawn_callback"):
                self.setup_subagent_spawn_callback(agent_id, agent)

        # Cross-collaborator hooks via orchestrator back-ref
        orch._share_subagent_message_callback_with_display()
        orch._push_cached_criteria_to_display()

    def setup_subagent_spawn_callback(self, agent_id: str, agent: Any) -> None:
        """Wire a single agent's backend spawn callback to the TUI display."""
        orch = self._orchestrator
        display = None
        if hasattr(orch, "coordination_ui") and orch.coordination_ui:
            display = getattr(orch.coordination_ui, "display", None)

        if not display:
            logger.debug(f"[Orchestrator] No display available for subagent spawn callback on {agent_id}")
            return

        if not hasattr(display, "notify_subagent_spawn_started"):
            logger.debug(f"[Orchestrator] Display doesn't support notify_subagent_spawn_started for {agent_id}")
            return

        def spawn_callback(tool_name: str, args: dict[str, Any], call_id: str) -> None:
            """Forward spawn notification to TUI display."""
            try:
                display.notify_subagent_spawn_started(agent_id, tool_name, args, call_id)
                logger.debug(f"[Orchestrator] Notified TUI of subagent spawn for {agent_id}")
            except Exception as e:
                logger.debug(f"[Orchestrator] Failed to notify TUI of subagent spawn: {e}")

        if hasattr(agent.backend, "set_subagent_spawn_callback"):
            agent.backend.set_subagent_spawn_callback(spawn_callback)
            logger.info(f"[Orchestrator] Set subagent spawn callback for {agent_id}")
        else:
            logger.debug(f"[Orchestrator] Backend for {agent_id} doesn't support subagent spawn callback")

    # ------------------------------------------------------------------
    # Workspace SUBAGENT.md directory writer
    # ------------------------------------------------------------------
    def write_subagent_type_dirs(self, workspace_root: Any) -> None:
        """Write SUBAGENT.md dirs to ``workspace_root/.massgen/subagent_types/``."""
        orch = self._orchestrator
        try:
            from massgen.subagent.type_scanner import (
                DEFAULT_SUBAGENT_TYPES,
                scan_subagent_types,
            )

            _subagent_types_cfg = getattr(
                getattr(orch.config, "coordination_config", None),
                "subagent_types",
                None,
            )
            _allowed = _subagent_types_cfg if _subagent_types_cfg is not None else DEFAULT_SUBAGENT_TYPES
            specialized_types = scan_subagent_types(allowed_types=_allowed)
            if specialized_types:
                subagent_types_dir = Path(workspace_root) / ".massgen" / "subagent_types"
                subagent_types_dir.mkdir(parents=True, exist_ok=True)
                for t in specialized_types:
                    type_dir = subagent_types_dir / t.name
                    type_dir.mkdir(exist_ok=True)
                    frontmatter = f"---\nname: {t.name}\ndescription: {json.dumps(t.description)}\n"
                    if t.skills:
                        frontmatter += f"skills: {json.dumps(t.skills)}\n"
                    if t.expected_input:
                        frontmatter += f"expected_input: {json.dumps(t.expected_input)}\n"
                    frontmatter += "---\n"
                    (type_dir / "SUBAGENT.md").write_text(frontmatter + t.system_prompt)
                logger.info(
                    f"[Orchestrator] Wrote {len(specialized_types)} subagent type dirs to {subagent_types_dir}",
                )
        except ValueError as e:
            raise ValueError(f"Failed to discover specialized subagent types: {e}") from e
        except Exception as e:
            logger.warning(f"[Orchestrator] Failed to write subagent type dirs: {e}")

    # ------------------------------------------------------------------
    # Parent coordination config builder
    # ------------------------------------------------------------------
    def build_parent_coordination_config_for_subagents(self) -> dict[str, Any]:
        """Collect parent coordination fields that child subagent runs may inherit."""
        orch = self._orchestrator
        parent_coordination_config: dict[str, Any] = {}
        coord_cfg = getattr(orch.config, "coordination_config", None)
        if not coord_cfg:
            return parent_coordination_config

        if hasattr(coord_cfg, "enable_agent_task_planning"):
            parent_coordination_config["enable_agent_task_planning"] = coord_cfg.enable_agent_task_planning
        if hasattr(coord_cfg, "task_planning_filesystem_mode"):
            parent_coordination_config["task_planning_filesystem_mode"] = coord_cfg.task_planning_filesystem_mode
        if hasattr(coord_cfg, "learning_capture_mode"):
            parent_coordination_config["learning_capture_mode"] = coord_cfg.learning_capture_mode
        if hasattr(coord_cfg, "disable_final_only_round_capture_fallback"):
            parent_coordination_config["disable_final_only_round_capture_fallback"] = coord_cfg.disable_final_only_round_capture_fallback
        if hasattr(coord_cfg, "subagent_orchestrator"):
            so_cfg = coord_cfg.subagent_orchestrator
            if so_cfg:
                parent_coordination_config["subagent_orchestrator"] = so_cfg.to_dict()

        use_skills = getattr(coord_cfg, "use_skills", False)
        enabled_skill_names = getattr(coord_cfg, "enabled_skill_names", None)
        if use_skills or enabled_skill_names is not None:
            parent_coordination_config["use_skills"] = True
            parent_coordination_config["massgen_skills"] = getattr(coord_cfg, "massgen_skills", []) or []
            parent_coordination_config["skills_directory"] = getattr(
                coord_cfg,
                "skills_directory",
                ".agent/skills",
            )
            parent_coordination_config["load_previous_session_skills"] = getattr(
                coord_cfg,
                "load_previous_session_skills",
                False,
            )
            if enabled_skill_names is not None:
                parent_coordination_config["enabled_skill_names"] = enabled_skill_names

        if hasattr(coord_cfg, "subagent_round_timeouts") and coord_cfg.subagent_round_timeouts:
            parent_coordination_config["subagent_round_timeouts"] = coord_cfg.subagent_round_timeouts

        if hasattr(orch.config, "timeout_config") and orch.config.timeout_config:
            parent_coordination_config["parent_round_timeouts"] = {
                "initial_round_timeout_seconds": orch.config.timeout_config.initial_round_timeout_seconds,
                "subsequent_round_timeout_seconds": orch.config.timeout_config.subsequent_round_timeout_seconds,
                "round_timeout_grace_seconds": orch.config.timeout_config.round_timeout_grace_seconds,
            }

        for setting in (
            "voting_sensitivity",
            "voting_threshold",
            "checklist_require_gap_report",
            "gap_report_mode",
            "max_checklist_calls_per_round",
            "checklist_first_answer",
        ):
            value = getattr(orch.config, setting, None)
            if setting == "voting_threshold" and value is None:
                continue
            if value is not None:
                parent_coordination_config[setting] = value

        return parent_coordination_config

    # ------------------------------------------------------------------
    # MCP config builder
    # ------------------------------------------------------------------
    def create_subagent_mcp_config(self, agent_id: str, agent: Any) -> dict[str, Any]:
        """Create MCP server configuration for subagent tools."""
        orch = self._orchestrator

        import massgen.mcp_tools.subagent._subagent_mcp_server as subagent_module

        script_path = Path(subagent_module.__file__).resolve()

        fs_manager = agent.backend.filesystem_manager
        if hasattr(fs_manager, "get_workspace_root"):
            workspace_root = Path(fs_manager.get_workspace_root()).resolve()
        else:
            workspace_root = Path(fs_manager.cwd).resolve()
        workspace_path = str(workspace_root)
        agent_temporary_workspace_path = ""
        fs_temp_workspace = getattr(fs_manager, "agent_temporary_workspace", None)
        if fs_temp_workspace:
            agent_temporary_workspace_path = str(Path(fs_temp_workspace).resolve())
        else:
            orchestrator_temp_workspace = getattr(orch, "_agent_temporary_workspace", None)
            if orchestrator_temp_workspace:
                agent_temporary_workspace_path = str(Path(orchestrator_temp_workspace).resolve())

        mcp_temp_dir = workspace_root / ".massgen" / "subagent_mcp"
        mcp_temp_dir.mkdir(parents=True, exist_ok=True)

        agent_configs = []
        for aid, a in orch.agents.items():
            agent_cfg: dict[str, Any] = {"id": aid}
            if hasattr(a.backend, "config"):
                backend_cfg = {k: v for k, v in a.backend.config.items() if k not in ("mcp_servers", "_config_path")}
                if "model" not in backend_cfg and hasattr(a.backend, "model") and a.backend.model:
                    backend_cfg["model"] = a.backend.model
                agent_cfg["backend"] = backend_cfg
            runtime_agent_config = getattr(a, "config", None)
            subagent_agents = getattr(runtime_agent_config, "subagent_agents", None)
            if isinstance(subagent_agents, list) and subagent_agents:
                agent_cfg["subagent_agents"] = json.loads(json.dumps(subagent_agents))
            agent_configs.append(agent_cfg)

        _token = orch.coordination_tracker.get_path_token(agent_id)

        agent_configs_path = str(mcp_temp_dir / f"{_token}_agent_configs.json")
        with open(agent_configs_path, "w") as f:
            json.dump(agent_configs, f)

        context_paths_path = ""
        parent_context_paths = []
        if hasattr(orch, "config") and isinstance(getattr(orch.config, "__dict__", {}), dict):
            if hasattr(agent.backend, "config") and "context_paths" in agent.backend.config:
                parent_context_paths = agent.backend.config.get("context_paths", [])

        if parent_context_paths:
            context_paths_path = str(mcp_temp_dir / f"{_token}_context_paths.json")
            with open(context_paths_path, "w") as f:
                json.dump(parent_context_paths, f)
            logger.info(
                f"[Orchestrator] Passing {len(parent_context_paths)} context paths to subagent MCP",
            )

        coordination_config_path = ""
        if hasattr(orch.config, "coordination_config") and orch.config.coordination_config:
            parent_coordination_config = self.build_parent_coordination_config_for_subagents()
            if parent_coordination_config:
                coordination_config_path = str(mcp_temp_dir / f"{_token}_coordination_config.json")
                with open(coordination_config_path, "w") as f:
                    json.dump(parent_coordination_config, f)
                logger.info(
                    f"[Orchestrator] Passing coordination config to subagent MCP: " f"{list(parent_coordination_config.keys())}",
                )

        max_concurrent = 3
        default_timeout = 300
        min_timeout = 60
        max_timeout = 600
        subagent_runtime_mode = "isolated"
        subagent_runtime_fallback_mode = ""
        subagent_host_launch_prefix: list[str] = []
        subagent_orchestrator_config_json = "{}"
        subagent_orchestrator_config_path = ""
        if hasattr(orch.config, "coordination_config"):
            if hasattr(orch.config.coordination_config, "subagent_max_concurrent"):
                max_concurrent = orch.config.coordination_config.subagent_max_concurrent
            if hasattr(orch.config.coordination_config, "subagent_default_timeout"):
                default_timeout = orch.config.coordination_config.subagent_default_timeout
            if hasattr(orch.config.coordination_config, "subagent_min_timeout"):
                min_timeout = orch.config.coordination_config.subagent_min_timeout
            if hasattr(orch.config.coordination_config, "subagent_max_timeout"):
                max_timeout = orch.config.coordination_config.subagent_max_timeout
            if default_timeout > max_timeout:
                max_timeout = default_timeout
            if hasattr(orch.config.coordination_config, "subagent_orchestrator"):
                so_config = orch.config.coordination_config.subagent_orchestrator
                if so_config:
                    so_payload = so_config.to_dict()
                    subagent_orchestrator_config_json = json.dumps(so_payload)
                    subagent_orchestrator_config_path = str(
                        mcp_temp_dir / f"{_token}_orchestrator_config.json",
                    )
                    with open(subagent_orchestrator_config_path, "w") as f:
                        json.dump(so_payload, f)
            if hasattr(orch.config.coordination_config, "subagent_runtime_mode"):
                subagent_runtime_mode = orch.config.coordination_config.subagent_runtime_mode or "isolated"
            if hasattr(orch.config.coordination_config, "subagent_runtime_fallback_mode"):
                fallback_mode = orch.config.coordination_config.subagent_runtime_fallback_mode
                subagent_runtime_fallback_mode = fallback_mode if fallback_mode else ""
            if hasattr(orch.config.coordination_config, "subagent_host_launch_prefix"):
                host_launch_prefix = orch.config.coordination_config.subagent_host_launch_prefix
                if isinstance(host_launch_prefix, list):
                    subagent_host_launch_prefix = host_launch_prefix

        backend_cfg = None
        if hasattr(orch, "agents") and isinstance(orch.agents, dict):
            parent_agent = orch.agents.get(agent_id)
            if parent_agent is not None and hasattr(parent_agent, "backend") and hasattr(parent_agent.backend, "config") and isinstance(parent_agent.backend.config, dict):
                backend_cfg = parent_agent.backend.config
        if backend_cfg is None and hasattr(agent, "backend") and hasattr(agent.backend, "config"):
            backend_cfg = agent.backend.config
        if (
            isinstance(backend_cfg, dict)
            and str(backend_cfg.get("type", "")).lower() == "codex"
            and str(backend_cfg.get("command_line_execution_mode", "local")).lower() == "docker"
            and subagent_runtime_mode == "isolated"
            and not subagent_runtime_fallback_mode
            and orch._delegation_dir is not None
        ):
            subagent_runtime_mode = "delegated"
            logger.info(
                "[Orchestrator] Enabling delegated subagent mode for Codex Docker backend " f"(delegation_dir={orch._delegation_dir})",
            )
            # Start the SubagentLaunchWatcher on the host (first time only).
            # NOTE: read/write through orch attribute so ActiveCoordinationCleanup
            # sees the same handle when it stops the watcher.
            if orch._subagent_launch_watcher is None:
                try:
                    from massgen.subagent.launch_watcher import SubagentLaunchWatcher

                    orch._subagent_launch_watcher = SubagentLaunchWatcher(
                        delegation_dir=orch._delegation_dir,
                        allowed_workspace_roots=[orch._subagent_logs_dir.parent.parent],
                    )
                    import asyncio as _asyncio

                    _asyncio.get_event_loop().create_task(orch._subagent_launch_watcher.start())
                    logger.info("[Orchestrator] Started SubagentLaunchWatcher")
                except Exception as e:
                    logger.warning(
                        f"[Orchestrator] Failed to start SubagentLaunchWatcher: {e}. " "Falling back to inherited mode.",
                    )
                    subagent_runtime_mode = "inherited"
                    subagent_runtime_fallback_mode = "inherited"
            if orch._subagent_launch_watcher is not None:
                orch._subagent_launch_watcher.add_allowed_root(workspace_root)
        elif (
            isinstance(backend_cfg, dict)
            and str(backend_cfg.get("type", "")).lower() == "codex"
            and str(backend_cfg.get("command_line_execution_mode", "local")).lower() == "docker"
            and subagent_runtime_mode == "isolated"
            and not subagent_runtime_fallback_mode
        ):
            subagent_runtime_fallback_mode = "inherited"
            logger.info(
                "[Orchestrator] Defaulting subagent runtime fallback to 'inherited' for Codex Docker mode " "(delegation directory not available)",
            )

        # Discover specialized subagent types and write SUBAGENT.md dirs.
        self.write_subagent_type_dirs(workspace_root)

        log_directory = ""
        if orch._subagent_logs_dir is not None:
            log_directory = str(orch._subagent_logs_dir.resolve())
        else:
            try:
                log_dir = _resolve_log_session_dir()
                if log_dir:
                    log_directory = str(log_dir.resolve())
            except Exception:
                pass

        args = [
            "run",
            f"{script_path}:create_server",
            "--",
            "--agent-id",
            agent_id,
            "--orchestrator-id",
            orch.orchestrator_id,
            "--workspace-path",
            workspace_path,
            "--agent-temporary-workspace",
            agent_temporary_workspace_path,
            "--agent-configs-file",
            agent_configs_path,
            "--max-concurrent",
            str(max_concurrent),
            "--default-timeout",
            str(default_timeout),
            "--min-timeout",
            str(min_timeout),
            "--max-timeout",
            str(max_timeout),
            "--orchestrator-config-file",
            subagent_orchestrator_config_path,
            "--log-directory",
            log_directory,
            "--context-paths-file",
            context_paths_path,
            "--coordination-config-file",
            coordination_config_path,
            "--runtime-mode",
            subagent_runtime_mode,
            "--runtime-fallback-mode",
            subagent_runtime_fallback_mode,
            "--host-launch-prefix",
            json.dumps(subagent_host_launch_prefix),
            "--delegation-directory",
            str(orch._delegation_dir.resolve()) if orch._delegation_dir is not None else "",
        ]
        if not subagent_orchestrator_config_path:
            args.extend(
                [
                    "--orchestrator-config",
                    subagent_orchestrator_config_json,
                ],
            )

        if hasattr(agent.backend, "supports_mcp_server_hooks") and agent.backend.supports_mcp_server_hooks():
            hook_dir = agent.backend.get_hook_dir()
            args.extend(["--hook-dir", str(hook_dir)])

        mcp_env: dict[str, str] = {"FASTMCP_SHOW_CLI_BANNER": "false"}
        if hasattr(agent.backend, "_build_custom_tools_mcp_env"):
            mcp_env = agent.backend._build_custom_tools_mcp_env()

        config: dict[str, Any] = {
            "name": self.subagent_server_name(agent_id),
            "type": "stdio",
            "command": "fastmcp",
            "args": args,
            "env": mcp_env,
            "tool_timeout_sec": int(default_timeout) + 60,
        }

        logger.info(
            f"[Orchestrator] Created subagent MCP config for {agent_id} with workspace: {workspace_path}",
        )

        return config

    def rewrite_subagent_mcp_config_files(
        self,
        workspace_root,
        agent_id: str,
    ) -> None:
        """Re-write the subagent MCP JSON config files lost when the workspace
        was cleared between rounds (round-2+ counterpart of create_subagent_mcp_config)."""
        import json
        from pathlib import Path as PathlibPath
        from typing import Any

        orch = self._orchestrator
        mcp_temp_dir = PathlibPath(workspace_root) / ".massgen" / "subagent_mcp"
        mcp_temp_dir.mkdir(parents=True, exist_ok=True)
        _token = orch.coordination_tracker.get_path_token(agent_id)

        try:
            agent_configs = []
            for aid, a in orch.agents.items():
                agent_cfg: dict[str, Any] = {"id": aid}
                if hasattr(a.backend, "config"):
                    backend_cfg = {k: v for k, v in a.backend.config.items() if k not in ("mcp_servers", "_config_path")}
                    agent_cfg["backend"] = backend_cfg
                runtime_agent_config = getattr(a, "config", None)
                subagent_agents = getattr(runtime_agent_config, "subagent_agents", None)
                if isinstance(subagent_agents, list) and subagent_agents:
                    agent_cfg["subagent_agents"] = json.loads(json.dumps(subagent_agents))
                agent_configs.append(agent_cfg)
            with open(mcp_temp_dir / f"{_token}_agent_configs.json", "w") as f:
                json.dump(agent_configs, f)

            coord_cfg = getattr(orch.config, "coordination_config", None)
            if coord_cfg:
                parent_coordination_config = self.build_parent_coordination_config_for_subagents()
                if parent_coordination_config:
                    with open(mcp_temp_dir / f"{_token}_coordination_config.json", "w") as f:
                        json.dump(parent_coordination_config, f)

            if coord_cfg:
                so_cfg = getattr(coord_cfg, "subagent_orchestrator", None)
                if so_cfg:
                    with open(mcp_temp_dir / f"{_token}_orchestrator_config.json", "w") as f:
                        json.dump(so_cfg.to_dict(), f)

            from massgen.logger_config import logger

            logger.info(
                f"[Orchestrator] Re-wrote subagent MCP config files to {mcp_temp_dir}",
            )
        except Exception as e:
            from massgen.logger_config import logger

            logger.warning(f"[Orchestrator] Failed to re-write subagent MCP config files: {e}")
