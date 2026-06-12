"""Mid-stream injection / hook installer collaborator.

Owns mechanical helpers that manage agent stream lifecycle, restart-pending
state, framework MCP state clearing, plan progress computation, and the
mid-stream tool-result injection payload builder.

NOTE: This is the FIRST slice of a much larger cluster (the orchestrator's
"god-class core"). For safety, only six pure helpers are extracted in this
pass; the remaining hook-installation methods stay on Orchestrator for now
and will be moved in a follow-up. All shared state is touched via the
``self._orchestrator`` back-ref so Orchestrator + sibling collaborators
keep observing consistent state.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from massgen.logger_config import get_event_emitter, logger
from massgen.mcp_tools.hooks import (
    BackgroundToolCompleteHook,
    GeneralHookManager,
    HighPriorityTaskReminderHook,
    HookType,
    MediaCallLedgerHook,
    MidStreamInjectionHook,
    PythonCallableHook,
    RoundTimeoutPostHook,
    RoundTimeoutPreHook,
    RoundTimeoutState,
    SubagentCompleteHook,
)
from massgen.utils import ActionType

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class MidStreamInjectionHookInstaller:
    """Mid-stream injection helpers + (future) hook installation."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    async def close_agent_stream(
        self,
        agent_id: str,
        active_streams: dict[str, AsyncGenerator],
    ) -> None:
        """Close and remove an agent stream safely."""
        if agent_id in active_streams:
            try:
                await active_streams[agent_id].aclose()
            except Exception:
                pass  # Ignore cleanup errors
            del active_streams[agent_id]

    def check_restart_pending(self, agent_id: str) -> bool:
        """Check if agent should restart and yield restart message if needed. This will always be called when exiting out of _stream_agent_execution()."""
        restart_pending = self._orchestrator.agent_states[agent_id].restart_pending
        return restart_pending

    def should_defer_restart_for_first_answer(self, agent_id: str) -> bool:
        """Check if restart/injection should be deferred for first-answer protection.

        Each agent is guaranteed to complete at least one full round and produce
        an answer before being restarted or injected with other agents' work.
        """
        state = self._orchestrator.agent_states.get(agent_id)
        if state is None:
            return False
        return state.answer is None

    async def clear_framework_mcp_state(self, agent_id: str) -> None:
        """Clear in-memory state of framework MCP servers before agent restart.

        This ensures stateful MCPs like planning don't retain old data across
        answer submissions. Currently clears:
        - Task plans (planning MCP)
        """
        orch = self._orchestrator
        agent = orch.agents.get(agent_id)
        if not agent or not hasattr(agent.backend, "_mcp_client") or not agent.backend._mcp_client:
            return

        # Find the planning MCP tool name for this agent
        planning_tool_name = None
        for tool_name in agent.backend._mcp_functions.keys():
            if "clear_task_plan" in tool_name and orch._planning_server_name(agent_id) in tool_name:
                planning_tool_name = tool_name
                break

        if planning_tool_name:
            try:
                logger.info(
                    f"[Orchestrator] Clearing task plan for {agent_id} via {planning_tool_name}",
                )
                result, _ = await agent.backend._execute_mcp_function_with_retry(
                    planning_tool_name,
                    "{}",  # No arguments needed
                )
                logger.info(
                    f"[Orchestrator] Clear task plan result for {agent_id}: {result}",
                )
            except Exception as e:
                logger.warning(
                    f"[Orchestrator] Failed to clear task plan for {agent_id}: {e}",
                )

    def compute_plan_progress_stats(self, workspace_path: str) -> dict[str, Any] | None:
        """Compute task/requirement progress stats for an agent's workspace.

        Reads the agent's tasks/plan.json or tasks/spec.json and computes how
        many items are completed vs total.  Works in both plan-and-execute mode
        and spec execution mode.
        """
        try:
            workspace = Path(workspace_path)
            tasks_plan = workspace / "tasks" / "plan.json"
            tasks_spec = workspace / "tasks" / "spec.json"

            # Check for plan.json first, then spec.json
            if tasks_plan.exists():
                artifact_file = tasks_plan
                items_key = "tasks"
            elif tasks_spec.exists():
                artifact_file = tasks_spec
                items_key = "requirements"
            else:
                return None

            # Read artifact
            tasks_data = json.loads(artifact_file.read_text())
            tasks = tasks_data.get(items_key, [])
            total_tasks = len(tasks)

            if total_tasks == 0:
                return None

            # Count by status (verified tasks count as completed for progress)
            completed = sum(1 for t in tasks if t.get("status") in ("completed", "verified"))
            in_progress = sum(1 for t in tasks if t.get("status") == "in_progress")
            pending = sum(1 for t in tasks if t.get("status") == "pending")

            return {
                "total": total_tasks,
                "completed": completed,
                "in_progress": in_progress,
                "pending": pending,
                "percent_complete": round(100 * completed / total_tasks, 1) if total_tasks > 0 else 0,
            }
        except Exception as e:
            logger.debug(f"[Orchestrator] Could not compute plan progress: {e}")
            return None

    def _install_wait_interrupt_provider(self, agent: Any, agent_id: str) -> None:
        """Register the background-wait interrupt provider on the backend.

        Shared by every hook-setup path (GeneralHookManager, Codex MCP, native)
        so the cancellation / runtime-fallback contract cannot drift across
        backends. No-op when the backend does not support the hook.
        """
        orch = self._orchestrator
        if not hasattr(agent.backend, "set_background_wait_interrupt_provider"):
            return

        async def _wait_interrupt_provider(
            requested_agent_id: str,
            *,
            _agent_id: str = agent_id,
        ) -> dict[str, Any] | None:
            target_agent_id = requested_agent_id or _agent_id
            if hasattr(orch, "cancellation_manager") and orch.cancellation_manager and orch.cancellation_manager.is_cancelled:
                return {
                    "interrupt_reason": "turn_cancelled",
                    "injected_content": None,
                }

            runtime_sections = await orch._collect_no_hook_runtime_fallback_sections(
                target_agent_id,
            )
            if not runtime_sections:
                return None
            return {
                "interrupt_reason": "runtime_injection_available",
                "injected_content": "\n".join(runtime_sections),
            }

        agent.backend.set_background_wait_interrupt_provider(
            _wait_interrupt_provider,
        )

    def setup_hook_manager_for_agent(
        self,
        agent_id: str,
        agent: Any,
        answers: dict[str, str],
    ) -> None:
        """Route hook setup by backend capability (native / codex / GeneralHookManager).

        Dispatcher: Claude-Code-style native backends use the native adapter,
        Codex uses its hybrid or MCP path, everything else uses GeneralHookManager.
        """
        orch = self._orchestrator

        # Runtime human input must work for all backends, including those that
        # don't support hook registration (hookless fallback / Codex path).
        orch._ensure_runtime_human_input_hook_initialized()
        orch._ensure_runtime_inbox_poller_initialized()

        backend = getattr(agent, "backend", None)
        backend_provider = backend.get_provider_name() if backend and hasattr(backend, "get_provider_name") else ""

        # Codex uses a hybrid path: native Bash hooks plus MCP/file payload delivery.
        if (
            backend_provider == "codex"
            and hasattr(agent.backend, "supports_native_hooks")
            and agent.backend.supports_native_hooks()
            and hasattr(agent.backend, "supports_mcp_server_hooks")
            and agent.backend.supports_mcp_server_hooks()
        ):
            orch._setup_codex_hybrid_hooks(agent_id, agent, answers)
            return

        # Native hooks (e.g., Claude Code)
        if hasattr(agent.backend, "supports_native_hooks") and agent.backend.supports_native_hooks():
            orch._setup_native_hooks_for_agent(agent_id, agent, answers)
            return

        # MCP server-level hooks (e.g., Codex)
        if hasattr(agent.backend, "supports_mcp_server_hooks") and agent.backend.supports_mcp_server_hooks():
            orch._setup_codex_mcp_hooks(agent_id, agent, answers)
            return

        # Fall back to GeneralHookManager for standard backends
        if not hasattr(agent.backend, "set_general_hook_manager"):
            return

        manager = GeneralHookManager()
        mid_stream_hook = MidStreamInjectionHook()

        # A1: both the GeneralHookManager and native paths route through the
        # single unified installer method so they can no longer drift.
        async def get_injection_content() -> str | None:
            return await orch._build_midstream_injection(agent_id, answers, native=False)

        mid_stream_hook.set_callback(get_injection_content)

        # Register mid-stream injection hook first (maintains current behavior order)
        manager.register_global_hook(HookType.POST_TOOL_USE, mid_stream_hook)

        if orch._is_round_learning_capture_enabled():
            reminder_hook = HighPriorityTaskReminderHook()
            manager.register_global_hook(HookType.POST_TOOL_USE, reminder_hook)

        manager.register_global_hook(HookType.POST_TOOL_USE, MediaCallLedgerHook())

        # Register human input hook (shared across all agents)
        manager.register_global_hook(HookType.POST_TOOL_USE, orch._human_input_hook)

        # Register subagent completion hook for background result injection
        if orch._background_subagents_enabled:
            subagent_hook = SubagentCompleteHook(
                injection_strategy=orch._background_subagent_injection_strategy,
            )

            def make_pending_getter(aid: str):
                return lambda: orch._get_pending_subagent_results_async(aid)

            subagent_hook.set_pending_results_getter(make_pending_getter(agent_id))
            manager.register_global_hook(HookType.POST_TOOL_USE, subagent_hook)
            logger.debug(f"[Orchestrator] Registered SubagentCompleteHook for {agent_id}")

            # Wire background tool delegate so list/status/result/cancel route to subagents
            if hasattr(agent.backend, "register_background_delegate"):
                from massgen.subagent.background_delegate import (
                    SubagentBackgroundDelegate,
                )

                def _make_call_tool(aid: str):
                    return lambda tool_name, params: orch._call_subagent_mcp_tool_async(
                        aid,
                        tool_name,
                        params,
                    )

                delegate = SubagentBackgroundDelegate(
                    call_tool=_make_call_tool(agent_id),
                    agent_id=agent_id,
                )
                agent.backend.register_background_delegate(delegate)
                logger.debug(f"[Orchestrator] Registered SubagentBackgroundDelegate for {agent_id}")

        # Register background tool completion hook for async tool result injection
        if hasattr(agent.backend, "get_pending_background_tool_results"):
            background_tool_hook = BackgroundToolCompleteHook()
            background_tool_hook.set_completed_jobs_getter(
                agent.backend.get_pending_background_tool_results,
            )
            manager.register_global_hook(HookType.POST_TOOL_USE, background_tool_hook)
            logger.debug(
                f"[Orchestrator] Registered BackgroundToolCompleteHook for {agent_id}",
            )
        # Register per-round timeout hooks if configured
        orch._register_round_timeout_hooks(agent_id, manager)

        # Register user-configured hooks from agent backend config
        if hasattr(agent.backend, "config") and agent.backend.config:
            agent_hooks = agent.backend.config.get("hooks")
            if agent_hooks:
                manager.register_hooks_from_config(agent_hooks, agent_id=agent_id)
                logger.debug(
                    f"[Orchestrator] Registered user-configured hooks for {agent_id}",
                )

        # Register the permissions system (hardline blocklist + composite engine) and
        # the approval coordinator, when a `permissions:` block opts in.
        self._install_permission_hooks(agent, agent_id, manager)

        # Set manager on backend
        agent.backend.set_general_hook_manager(manager)
        self._install_wait_interrupt_provider(agent, agent_id)
        logger.debug(
            f"[Orchestrator] Set up hook manager for {agent_id} with mid-stream and reminder hooks",
        )

    def _install_permission_hooks(self, agent: Any, agent_id: str, manager: Any) -> None:
        """Wire the permissions system onto this agent's hook manager when opted in.

        Opt-in via a `permissions:` block on the backend config. Registers the
        hardline blocklist (catastrophic-command floor) + the composite permission
        engine (risk → allow/ask), and installs a PermissionCoordinator with the
        automation policy provider (the interactive TUI swaps in a modal provider).
        """
        cfg = getattr(agent.backend, "config", None)
        perms = cfg.get("permissions") if isinstance(cfg, dict) else None
        # Opt-in is PRESENCE-based: the system is OFF unless a `permissions` block is
        # present and not explicitly disabled. A config with no `permissions` key is
        # 100% unchanged (no hooks, no coordinator).
        if perms is None or perms is False:
            return
        if isinstance(perms, dict) and perms.get("enabled", True) is False:
            return

        from massgen.mcp_tools.hooks import HookType
        from massgen.permissions.approval_provider import PolicyApprovalProvider
        from massgen.permissions.coordinator import PermissionCoordinator
        from massgen.permissions.hooks import (
            HardlineBlocklistHook,
            PermissionEngineHook,
        )
        from massgen.permissions.models import AutomationDefault

        # Per-agent rules = role preset (higher-precedence scope) merged with the
        # agent's own allow/ask/deny rules, deny-wins across scopes. Each agent gets
        # its OWN engine hook (own manager), so this is naturally per-agent scoping.
        from massgen.permissions.rules import PermissionRuleSet, role_rule_set

        role = perms.get("role") if isinstance(perms, dict) else None
        rules_cfg = perms.get("rules") if isinstance(perms, dict) else None
        scopes = []
        role_rs = role_rule_set(role)
        if role_rs is not None:
            scopes.append(role_rs)
        if rules_cfg:
            scopes.append(PermissionRuleSet.from_config(rules_cfg))
        rule_set = PermissionRuleSet.merge(scopes) if scopes else None

        # Hardline first (catastrophic floor), then the composite engine (rules → risk).
        manager.register_global_hook(HookType.PRE_TOOL_USE, HardlineBlocklistHook())
        manager.register_global_hook(HookType.PRE_TOOL_USE, PermissionEngineHook(rules=rule_set))

        default_raw = str((perms.get("automation_default") if isinstance(perms, dict) else None) or "risk-based")
        try:
            automation_default = AutomationDefault(default_raw)
        except ValueError:
            automation_default = AutomationDefault.RISK_BASED

        # Approval transport: 'policy' (automation default; interactive TUI swaps in a
        # modal) or 'file' (request/response JSON for headless/remote approval — e.g.
        # a Slack bot or `/approve <id>`; not overridden by the TUI swap).
        approval_mode = str((perms.get("approval_mode") if isinstance(perms, dict) else None) or "policy").lower()
        if approval_mode == "file":
            from pathlib import Path as _Path

            from massgen.permissions.approval_provider import FileApprovalProvider

            appr_dir = (perms.get("approval_dir") if isinstance(perms, dict) else None) or ".massgen/approvals"
            provider = FileApprovalProvider(_Path(appr_dir) / (agent_id or "agent"))
        else:
            provider = PolicyApprovalProvider(automation_default)
        coordinator = PermissionCoordinator(provider=provider)
        if hasattr(agent.backend, "set_permission_coordinator"):
            agent.backend.set_permission_coordinator(coordinator)
        logger.info(
            f"[Orchestrator] Permissions system enabled for {agent_id} " f"(automation_default={automation_default.value}, approval_mode={approval_mode})",
        )

    def setup_codex_mcp_hooks(
        self,
        agent_id: str,
        agent: Any,
        answers: dict[str, str],
    ) -> None:
        """Set up MCP server-level hook delivery for Codex backends.

        Instead of registering hooks on a GeneralHookManager, this stores a
        reference (on the orchestrator) so the streaming loop can call
        ``_flush_codex_hook_payloads()`` to write injection files the MCP
        middleware consumes.
        """
        orch = self._orchestrator

        # Mark this agent as using MCP server hooks (stored on the orchestrator so
        # the streaming loop and tests observe it there).
        if not hasattr(orch, "_codex_mcp_hook_agents"):
            orch._codex_mcp_hook_agents = {}

        orch._codex_mcp_hook_agents[agent_id] = {
            "agent": agent,
            "answers": answers,
        }

        # Set up the background wait interrupt provider (reuse existing pattern)
        self._install_wait_interrupt_provider(agent, agent_id)

        logger.info(
            "[Orchestrator] Set up MCP server-level hook delivery for %s",
            agent_id,
        )

    def setup_codex_hybrid_hooks(
        self,
        agent_id: str,
        agent: Any,
        answers: dict[str, str],
    ) -> None:
        """Set up Codex's hybrid delivery path (native Bash bridge + MCP/file payloads)."""
        orch = self._orchestrator

        adapter = agent.backend.get_native_hook_adapter()
        if not adapter:
            logger.warning(
                "[Orchestrator] Codex backend reported native hooks but no adapter was available for %s",
                agent_id,
            )
            orch._setup_codex_mcp_hooks(agent_id, agent, answers)
            return

        manager = GeneralHookManager()
        manager.register_global_hook(
            HookType.POST_TOOL_USE,
            PythonCallableHook(
                name="codex_post_tool_bridge",
                handler=lambda _event: None,
                matcher="Bash",
            ),
        )

        native_config = adapter.build_native_hooks_config(
            manager,
            agent_id=agent_id,
        )
        agent.backend.set_native_hooks_config(native_config)
        # Codex's native hook surface is Bash-only, but the TUI and manual
        # wrap-up flow still need real timeout hook objects in agent state.
        timeout_manager = GeneralHookManager()
        orch._register_round_timeout_hooks(agent_id, timeout_manager)
        orch._setup_codex_mcp_hooks(agent_id, agent, answers)

        hooks = native_config.get("hooks", {}) if isinstance(native_config, dict) else {}
        logger.info(
            "[Orchestrator] Set up Codex hybrid hooks for %s: PreToolUse=%d, PostToolUse=%d",
            agent_id,
            len(hooks.get("PreToolUse", [])),
            len(hooks.get("PostToolUse", [])),
        )

    def setup_native_hooks_for_agent(
        self,
        agent_id: str,
        agent: Any,
        answers: dict[str, str],
    ) -> None:
        """Set up native hooks for backends that support them (e.g., Claude Code).

        Converts MassGen hooks to the backend's native format via the
        NativeHookAdapter; the backend then executes them natively rather than
        through MassGen's GeneralHookManager.
        """
        orch = self._orchestrator

        adapter = agent.backend.get_native_hook_adapter()
        if not adapter:
            logger.warning(
                f"[Orchestrator] Backend supports native hooks but adapter unavailable for {agent_id}",
            )
            return

        # Create a GeneralHookManager to hold MassGen hooks (converted to native).
        manager = GeneralHookManager()

        mid_stream_hook = MidStreamInjectionHook()

        # A1: unified with the GeneralHookManager path via the single installer
        # method; native=True only changes log wording and the debug listing.
        async def get_injection_content() -> str | None:
            return await orch._build_midstream_injection(agent_id, answers, native=True)

        mid_stream_hook.set_callback(get_injection_content)
        manager.register_global_hook(HookType.POST_TOOL_USE, mid_stream_hook)

        if orch._is_round_learning_capture_enabled():
            reminder_hook = HighPriorityTaskReminderHook()
            manager.register_global_hook(HookType.POST_TOOL_USE, reminder_hook)

        manager.register_global_hook(HookType.POST_TOOL_USE, MediaCallLedgerHook())

        # Register human input hook (shared across all agents)
        orch._ensure_runtime_human_input_hook_initialized()
        manager.register_global_hook(HookType.POST_TOOL_USE, orch._human_input_hook)

        # Register subagent completion hook for background result injection
        if orch._background_subagents_enabled:
            subagent_hook = SubagentCompleteHook(
                injection_strategy=orch._background_subagent_injection_strategy,
            )

            def make_pending_getter(aid: str):
                return lambda: orch._get_pending_subagent_results_async(aid)

            subagent_hook.set_pending_results_getter(make_pending_getter(agent_id))
            manager.register_global_hook(HookType.POST_TOOL_USE, subagent_hook)
            logger.debug(f"[Orchestrator] Registered SubagentCompleteHook (native) for {agent_id}")

            # Wire background tool delegate so list/status/result/cancel route to subagents
            if hasattr(agent.backend, "register_background_delegate"):
                from massgen.subagent.background_delegate import (
                    SubagentBackgroundDelegate,
                )

                def _make_call_tool(aid: str):
                    return lambda tool_name, params: orch._call_subagent_mcp_tool_async(
                        aid,
                        tool_name,
                        params,
                    )

                delegate = SubagentBackgroundDelegate(
                    call_tool=_make_call_tool(agent_id),
                    agent_id=agent_id,
                )
                agent.backend.register_background_delegate(delegate)
                logger.debug(f"[Orchestrator] Registered SubagentBackgroundDelegate (native) for {agent_id}")

        # Register background tool completion hook for async tool result injection
        if hasattr(agent.backend, "get_pending_background_tool_results"):
            background_tool_hook = BackgroundToolCompleteHook()
            background_tool_hook.set_completed_jobs_getter(
                agent.backend.get_pending_background_tool_results,
            )
            manager.register_global_hook(HookType.POST_TOOL_USE, background_tool_hook)
            logger.debug(
                f"[Orchestrator] Registered BackgroundToolCompleteHook (native) for {agent_id}",
            )
        # Register per-round timeout hooks if configured
        orch._register_round_timeout_hooks(agent_id, manager)

        # Register user-configured hooks from agent backend config
        agent_hooks = agent.backend.config.get("hooks")
        if agent_hooks:
            manager.register_hooks_from_config(agent_hooks, agent_id=agent_id)

        # Register PathPermissionManagerHook for PRE_TOOL_USE validation.
        # Native backends like Copilot need MassGen-level path validation.
        # Claude Code already handles permissions via add_dirs, so skip it.
        backend_provider = agent.backend.get_provider_name() if hasattr(agent.backend, "get_provider_name") else ""
        if backend_provider != "claude_code":
            _fm = getattr(agent.backend, "filesystem_manager", None)
            if _fm:
                _ppm = getattr(_fm, "path_permission_manager", None)
                if _ppm:
                    from massgen.filesystem_manager import PathPermissionManagerHook

                    ppm_hook = PathPermissionManagerHook(_ppm)
                    manager.register_global_hook(HookType.PRE_TOOL_USE, ppm_hook)
                    logger.debug(
                        f"[Orchestrator] Registered PathPermissionManagerHook (PRE_TOOL_USE) for {agent_id}",
                    )

        # Create context factory for hooks
        def context_factory() -> dict[str, Any]:
            workspace_path = None
            filesystem_manager = getattr(agent.backend, "filesystem_manager", None)
            if filesystem_manager and hasattr(filesystem_manager, "get_current_workspace"):
                try:
                    workspace_path = str(filesystem_manager.get_current_workspace())
                except Exception:
                    workspace_path = None
            return {
                "session_id": getattr(orch, "session_id", ""),
                "orchestrator_id": getattr(orch, "orchestrator_id", ""),
                "agent_id": agent_id,
                "workspace_path": workspace_path,
            }

        # Convert to native format using adapter
        native_config = adapter.build_native_hooks_config(
            manager,
            agent_id=agent_id,
            context_factory=context_factory,
        )

        # Set native hooks config on backend
        agent.backend.set_native_hooks_config(native_config)
        self._install_wait_interrupt_provider(agent, agent_id)
        logger.info(
            f"[Orchestrator] Set up native hooks for {agent_id}: " f"PreToolUse={len(native_config.get('PreToolUse', []))}, " f"PostToolUse={len(native_config.get('PostToolUse', []))} hooks",
        )

    def register_round_timeout_hooks(
        self,
        agent_id: str,
        manager: GeneralHookManager,
    ) -> None:
        """Register per-round timeout hooks if configured.

        Creates a soft RoundTimeoutPostHook (injects a warning after tool calls)
        and a hard RoundTimeoutPreHook (blocks non-terminal tools after the grace
        period), storing both on the agent state for per-round reset.
        """
        orch = self._orchestrator

        timeout_config = orch.config.timeout_config
        initial_timeout = timeout_config.initial_round_timeout_seconds
        subsequent_timeout = timeout_config.subsequent_round_timeout_seconds
        grace_seconds = timeout_config.round_timeout_grace_seconds

        # Skip if no round timeouts configured
        if initial_timeout is None and subsequent_timeout is None:
            return

        logger.info(
            f"[Orchestrator] Registering round timeout hooks for {agent_id}: " f"initial={initial_timeout}s, subsequent={subsequent_timeout}s, grace={grace_seconds}s",
        )

        # Create closures that read from agent state
        def get_round_start_time() -> float:
            """Get the current round start time from agent state."""
            start_time = orch.agent_states[agent_id].round_start_time
            if start_time is None:
                # Fallback to current time if not set (shouldn't happen)
                logger.warning(
                    f"[Orchestrator] round_start_time is None for {agent_id}, using current time as fallback",
                )
                return time.time()
            return start_time

        def get_agent_round() -> int:
            """Get the current round number from coordination tracker."""
            return orch.coordination_tracker.get_agent_round(agent_id)

        # Create shared state for coordinating soft -> hard timeout progression
        # This ensures hard timeout only fires AFTER soft timeout has been injected
        timeout_state = RoundTimeoutState()

        # Get two-tier workspace setting from coordination config
        # Suppressed when write_mode is active (write_mode replaces the old two-tier structure)
        coordination_config = getattr(orch.config, "coordination_config", None)
        write_mode = getattr(coordination_config, "write_mode", None) if coordination_config else None
        use_two_tier_workspace = False
        if not (write_mode and write_mode != "legacy"):
            use_two_tier_workspace = bool(
                getattr(coordination_config, "use_two_tier_workspace", False),
            )

        # Create soft timeout hook (POST_TOOL_USE - injects warning)
        post_hook = RoundTimeoutPostHook(
            name=f"round_timeout_soft_{agent_id}",
            get_round_start_time=get_round_start_time,
            get_agent_round=get_agent_round,
            initial_timeout_seconds=initial_timeout,
            subsequent_timeout_seconds=subsequent_timeout,
            grace_seconds=grace_seconds,
            agent_id=agent_id,
            shared_state=timeout_state,
            use_two_tier_workspace=use_two_tier_workspace,
        )

        # Create hard timeout hook (PRE_TOOL_USE - blocks non-terminal tools)
        pre_hook = RoundTimeoutPreHook(
            name=f"round_timeout_hard_{agent_id}",
            get_round_start_time=get_round_start_time,
            get_agent_round=get_agent_round,
            initial_timeout_seconds=initial_timeout,
            subsequent_timeout_seconds=subsequent_timeout,
            grace_seconds=grace_seconds,
            agent_id=agent_id,
            shared_state=timeout_state,
        )

        # Register hooks
        manager.register_global_hook(HookType.POST_TOOL_USE, post_hook)
        manager.register_global_hook(HookType.PRE_TOOL_USE, pre_hook)

        # Store hook references so we can reset them on new rounds
        orch.agent_states[agent_id].round_timeout_hooks = (post_hook, pre_hook)
        # Store the shared state so we can check force_terminate in the orchestrator loop
        orch.agent_states[agent_id].round_timeout_state = timeout_state

        logger.debug(f"[Orchestrator] Registered round timeout hooks for {agent_id}")

    async def build_midstream_injection(
        self,
        agent_id: str,
        answers: dict[str, str],
        *,
        native: bool,
    ) -> str | None:
        """Unified mid-stream peer-answer injection callback (A1).

        Replaces the two near-identical ``get_injection_content`` closures that
        lived inline in ``_setup_hook_manager_for_agent`` (GeneralHookManager
        path) and ``_setup_native_hooks_for_agent`` (native path). Keeping them
        separate was a backend-parity hazard — a fix to one path silently skipped
        the other.

        ``native`` only affects log/track wording and the (non-native) debug
        workspace-listing output. The side-effect sequence is canonical and
        preserves the load-bearing invariant shared by both original closures:
        ``update_agent_context_with_new_answers`` runs BEFORE
        ``refresh_checklist_state_for_agent`` so ``available_agent_labels``
        reflect the newly-injected labels. (The prior inter-path divergence in
        the position of the ``restart_pending`` recompute and the emitter/track
        calls was verified inert — the recompute reads only ``seen_answer_counts``,
        which is set at the same relative position in both paths.)

        Mutates the caller's ``answers`` dict in place so re-entrant callbacks do
        not re-inject the same updates.
        """
        orch = self._orchestrator
        label = "native " if native else ""
        track_suffix = " (native)" if native else ""

        # Skip injection if disabled (multi-agent refinement OFF mode).
        if orch.config.disable_injection:
            return None

        if not orch._check_restart_pending(agent_id):
            return None

        # First-answer protection: don't inject before the agent's first answer.
        if orch._should_defer_restart_for_first_answer(agent_id):
            orch.agent_states[agent_id].restart_pending = False
            return None

        # In vote-only mode, force a full restart instead (mid-stream injection
        # can't update the fixed vote tool schema).
        if orch._is_vote_only_mode(agent_id):
            return None

        if orch._should_defer_peer_updates_until_restart(agent_id):
            if orch._has_unseen_answer_updates(agent_id):
                orch.agent_states[agent_id].restart_pending = True
                logger.info(
                    "[Orchestrator] Deferring %speer answer update injection until restart for %s",
                    label,
                    agent_id,
                )
            else:
                orch.agent_states[agent_id].restart_pending = False
            return None

        # Get CURRENT answers (includes virtual agents in step mode).
        current_answers = orch._get_current_answers_snapshot()
        selected_answers, had_unseen_updates = orch._select_midstream_answer_updates(
            agent_id,
            current_answers,
        )

        if not selected_answers:
            if had_unseen_updates:
                # Keep restart pending when unseen updates still exist.
                orch.agent_states[agent_id].restart_pending = True
                cap = getattr(orch.config, "max_midstream_injections_per_round", 2)
                logger.info(
                    "[Orchestrator] Skipping %smid-stream injection for %s: per-round cap reached (%s)",
                    label,
                    agent_id,
                    cap,
                )
            else:
                # No unseen updates remain: this was a stale restart_pending flag.
                orch.agent_states[agent_id].restart_pending = False
            return None

        # R1: capture peer revision counts as-of selection, before the
        # snapshot-copy await below can let a peer publish a new revision that
        # would otherwise be silently marked "seen".
        captured_revision_counts = orch._capture_answer_revision_counts(list(selected_answers.keys()))

        # TIMING CONSTRAINT: skip injection if too close to soft timeout.
        if orch._should_skip_injection_due_to_timeout(agent_id):
            return None

        # Copy snapshots from new-answer agents to temp workspace BEFORE building
        # the injection, so the workspace files are available to the agent.
        logger.info(
            "[Orchestrator] Copying snapshots for mid-stream injection to %s",
            agent_id,
        )
        await orch._copy_all_snapshots_to_temp_workspace(agent_id)

        # Build injection content (pass existing answers to detect updates vs new).
        injection = orch._build_tool_result_injection(
            agent_id,
            selected_answers,
            existing_answers=answers,
        )

        # Debug: log temp-workspace contents per injected agent (non-native path
        # only, preserved from the original GeneralHookManager closure).
        if not native:
            viewing_agent = orch.agents.get(agent_id)
            if viewing_agent and viewing_agent.backend.filesystem_manager:
                temp_workspace_base = str(
                    viewing_agent.backend.filesystem_manager.agent_temporary_workspace,
                )
                agent_mapping = orch.coordination_tracker.get_reverse_agent_mapping()
                for aid in selected_answers.keys():
                    anon_id = agent_mapping.get(aid, f"agent_{aid}")
                    workspace_path = os.path.join(temp_workspace_base, anon_id)
                    if os.path.exists(workspace_path):
                        try:
                            files = os.listdir(workspace_path)
                            logger.debug(
                                f"[Orchestrator] Injection workspace {workspace_path} contains: {files}",
                            )
                        except OSError as e:
                            logger.debug(
                                f"[Orchestrator] Could not list workspace {workspace_path}: {e}",
                            )
                    else:
                        logger.debug(
                            f"[Orchestrator] Injection workspace {workspace_path} does NOT exist!",
                        )

        # Increment injection counters.
        orch.agent_states[agent_id].injection_count += 1
        orch.agent_states[agent_id].midstream_injections_this_round += len(selected_answers)

        # Update answers so future callbacks don't re-inject the same updates.
        answers.update(selected_answers)

        # Update known_answer_ids so vote validation knows the agent saw these.
        orch.agent_states[agent_id].known_answer_ids.update(selected_answers.keys())
        orch._register_injected_answer_updates(
            agent_id,
            list(selected_answers.keys()),
            seen_counts=captured_revision_counts,
        )
        orch._mark_pending_checklist_recheck_labels(agent_id, list(selected_answers.keys()))

        # Update agent context labels BEFORE refreshing checklist state so
        # available_agent_labels reflects the newly-injected labels (e.g.
        # agent1.2 replacing agent1.1). Load-bearing ordering — both original
        # closures preserved it.
        orch.coordination_tracker.update_agent_context_with_new_answers(
            agent_id,
            list(selected_answers.keys()),
        )
        orch._refresh_checklist_state_for_agent(agent_id)

        # Keep restart pending if additional unseen revisions still remain.
        orch.agent_states[agent_id].restart_pending = orch._has_unseen_answer_updates(agent_id)

        logger.info(
            "[Orchestrator] Mid-stream injection%s for %s: %d answer update(s)",
            track_suffix,
            agent_id,
            len(selected_answers),
        )
        if not native:
            preview = injection[:2000] + ("..." if len(injection) > 2000 else "")
            logger.debug(f"[Orchestrator] Injection content (truncated):\n{preview}")

        _inj_emitter = get_event_emitter()
        if _inj_emitter:
            _inj_emitter.emit_injection_received(
                agent_id=agent_id,
                source_agents=list(selected_answers.keys()),
                injection_type="mid_stream",
            )

        orch.coordination_tracker.track_agent_action(
            agent_id,
            ActionType.UPDATE_INJECTED,
            f"Mid-stream{track_suffix}: {len(selected_answers)} answer(s)",
        )

        return injection

    def build_tool_result_injection(
        self,
        agent_id: str,
        new_answers: dict[str, str],
        existing_answers: dict[str, str] | None = None,
    ) -> str:
        """Build compact injection content for appending to tool results.

        This creates a lighter-weight update message designed to be embedded
        in tool result content rather than sent as a separate user message.
        Used for mid-stream injection of peer updates during agent execution.
        """
        orch = self._orchestrator
        existing_answers = existing_answers or {}

        # Normalize workspace paths for this agent's perspective
        normalized = orch._normalize_workspace_paths_in_answers(
            new_answers,
            viewing_agent_id=agent_id,
        )

        # Get viewing agent's temporary workspace path
        temp_workspace_base = None
        viewing_agent = orch.agents.get(agent_id)
        if viewing_agent and viewing_agent.backend.filesystem_manager:
            temp_workspace_base = str(
                viewing_agent.backend.filesystem_manager.agent_temporary_workspace,
            )

        # Create anonymous mapping (consistent with CURRENT ANSWERS format across all agents)
        agent_mapping = orch.coordination_tracker.get_reverse_agent_mapping()
        context_labels = orch.coordination_tracker.get_agent_context_labels(agent_id)

        # Format answers with workspace paths
        lines = []
        updated_agents = []
        new_agents = []
        updated_header_entries = []
        new_header_entries = []
        transition_lines = []

        for aid, answer in normalized.items():
            anon_id = agent_mapping.get(aid, f"agent_{aid}")
            is_update = aid in existing_answers

            if is_update:
                updated_agents.append(anon_id)
            else:
                new_agents.append(anon_id)

            # Build explicit answer-label transitions so agents can score newest labels.
            latest_revisions = orch.coordination_tracker.answers_by_agent.get(aid, [])
            latest_label = str(getattr(latest_revisions[-1], "label", "")) if latest_revisions else ""
            old_label = ""
            if latest_label and "." in latest_label:
                label_prefix = latest_label.split(".", 1)[0] + "."
                old_label = next((lbl for lbl in context_labels if lbl.startswith(label_prefix)), "")

            if is_update and old_label and latest_label and old_label != latest_label:
                updated_header_entries.append(f"{anon_id} ({old_label} -> {latest_label})")
                transition_lines.append(
                    f"  - {anon_id}: {old_label} -> {latest_label}",
                )
            elif not is_update and latest_label:
                new_header_entries.append(f"{anon_id} ({latest_label})")
                transition_lines.append(
                    f"  - {anon_id}: now available as {latest_label}",
                )
            elif is_update:
                # Fallback if labels are unavailable in edge cases
                updated_header_entries.append(anon_id)
            else:
                new_header_entries.append(anon_id)

            # Truncate long answers for injection context
            truncated = answer[:500] + "..." if len(answer) > 500 else answer

            # Include workspace path for file access
            workspace_path = os.path.join(temp_workspace_base, anon_id) if temp_workspace_base else f"temp_workspaces/{anon_id}"
            lines.append(f"  [{anon_id}] (workspace: {workspace_path}):")

            # Compute and include progress stats if in plan execution mode
            progress = self.compute_plan_progress_stats(workspace_path)
            if progress:
                lines.append(
                    f"    📊 Progress: {progress['completed']}/{progress['total']} tasks completed "
                    f"({progress['percent_complete']}%) | {progress['in_progress']} in progress | {progress['pending']} pending",
                )
                lines.append("    ⚠️  Note: Progress stats are INFORMATIONAL - evaluate the DELIVERABLE quality, not task count")

            lines.append(f"    {truncated}")
            lines.append("")

        # Build header based on what changed
        if updated_agents and new_agents:
            header = f"[UPDATE: {', '.join(new_header_entries)} submitted new answer(s); " f"{', '.join(updated_header_entries)} updated their answer(s)]"
        elif updated_agents:
            header = f"[UPDATE: {', '.join(updated_header_entries)} updated their answer(s)]"
        else:
            header = f"[UPDATE: {', '.join(new_header_entries)} submitted new answer(s)]"

        # Use different framing for decomposition mode vs voting mode
        is_decomposition = getattr(orch.config, "coordination_mode", "voting") == "decomposition"
        is_checklist_mode = getattr(orch.config, "voting_sensitivity", "balanced") == "checklist_gated"

        if is_decomposition:
            injection_parts = [
                "",
                "=" * 60,
                "UPDATE: ANOTHER AGENT SUBMITTED WORK",
                "=" * 60,
                "",
                header,
                "",
                "ANSWER LABEL UPDATES:",
                *(transition_lines or ["  - (no label change details available)"]),
                "",
                *lines,
                "=" * 60,
            ]
            if is_checklist_mode:
                injection_parts.extend(
                    [
                        "CHECKLIST-GATED ACTIONS (REQUIRED):",
                        "=" * 60,
                        "",
                        "1. Read and understand their full work — maintain awareness of the entire project state",
                        "2. Keep ownership-first: spend most effort on your subtask; touch other areas only for adjacent integration",
                        "3. Integrate boundary dependencies (interfaces/contracts/shared assets) without taking over unrelated scopes",
                        "4. Use submit_checklist with the newest labels shown above before deciding to `stop` or continue iterating",
                        "5. If checklist was already accepted this round and this update is new:",
                        "   - Preferred: submit only the injected newest labels (delta recheck)",
                        "   - Also allowed: submit all latest labels in your current context",
                        "6. If submit_checklist returns a validation error, fix payload/report and call submit_checklist again",
                        "7. If checklist returns iterate (new_answer), call draft_approach, implement, then call new_answer",
                        "8. Call `stop` only after the latest checklist result supports stopping and you have no new work to share",
                        "",
                        "DO NOT ignore this update - checklist flow must be re-run on newest labels.",
                        "=" * 60,
                    ],
                )
            else:
                injection_parts.extend(
                    [
                        "RECOMMENDED ACTIONS:",
                        "=" * 60,
                        "",
                        "1. Read and understand their full work — maintain awareness of the entire project state",
                        "2. Keep ownership-first: spend most effort on your subtask; touch other areas only for adjacent integration",
                        "3. Integrate boundary dependencies (interfaces/contracts/shared assets) without taking over unrelated scopes",
                        "4. Continue refining your own work — fix issues, improve quality, incorporate insights",
                        "5. If you submit `new_answer`, include concrete deliverables + validation evidence + integration notes",
                        "6. Call `stop` only when you've reviewed everything and are satisfied — no new work to share",
                        "",
                        "=" * 60,
                    ],
                )
        else:
            injection_parts = [
                "",
                "=" * 60,
                "⚠️  IMPORTANT: NEW ANSWER RECEIVED - ACTION REQUIRED",
                "=" * 60,
                "",
                header,
                "",
                "ANSWER LABEL UPDATES:",
                *(transition_lines or ["  - (no label change details available)"]),
                "",
                *lines,
                "=" * 60,
            ]
            if is_checklist_mode:
                injection_parts.extend(
                    [
                        "CHECKLIST-GATED ACTIONS (REQUIRED):",
                        "=" * 60,
                        "",
                        "1. Add a task: 'Evaluate injected answer label updates and re-run checklist'",
                        "2. Read injected workspace files, then compare to your current work",
                        "3. Use submit_checklist with the newest labels shown above",
                        "4. If checklist was already accepted this round and this update is new:",
                        "   - Preferred: submit only the injected newest labels (delta recheck)",
                        "   - Also allowed: submit all latest labels in your current context",
                        "5. If submit_checklist returns a validation error, fix payload/report and call submit_checklist again",
                        "6. If checklist returns iterate (new_answer), call draft_approach, implement, then call new_answer",
                        "DO NOT ignore this update - checklist flow must be re-run on newest labels.",
                        "=" * 60,
                    ],
                )
            else:
                injection_parts.extend(
                    [
                        "REQUIRED ACTION - You MUST do one of the following:",
                        "=" * 60,
                        "",
                        "1. **ADD A TASK** to your plan: 'Evaluate agent answer(s) and decide next action'",
                        "   - Use update_task_status or create a new task to track this evaluation",
                        "   - Read their workspace files (paths above) to understand their solution",
                        "   - Compare their approach to yours",
                        "",
                        "2. **THEN CHOOSE ONE**:",
                        "   a) VOTE for their answer if it's complete and correct (use vote tool)",
                        "   b) BUILD on their work - improve/extend it and submit YOUR enhanced answer",
                        "   c) MERGE approaches - combine the best parts of their work with yours",
                        "   d) CONTINUE your own approach if you believe it's better",
                        "",
                        "DO NOT ignore this update - you must explicitly evaluate and decide!",
                        "=" * 60,
                    ],
                )

        # Append essential files from injected agents so the receiving agent
        # can evaluate without re-reading from workspace
        essential_files_block = orch._build_essential_files_for_injection(
            agent_id,
            list(new_answers.keys()),
        )
        if essential_files_block:
            injection_parts.extend(["", essential_files_block])

        return "\n".join(injection_parts)
