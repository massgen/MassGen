"""Subagent lifecycle coordination, extracted from Orchestrator.

Owns the in-process queues for background subagent completion, the MCP
bridge for ``mcp__<server>__*`` subagent control tools, direct-spawn
fallback, cancellation flows, runtime-message delivery, and the TUI
continue-subagent status callback.

All shared state (``_pending_subagent_results``, ``_injected_subagents``,
``_background_trace_tasks``) is mutated via the orchestrator back-ref so
other collaborators (which still read these via the orchestrator) see a
single source of truth.

Cross-cluster dependency: ``schedule_background_wait_interrupt_for_agent``
calls back through ``orch._maybe_interrupt_background_wait_for_agent``,
which is itself a delegator into ``RuntimeInputDelivery``.
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import json
import secrets
import time
import uuid as _uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from massgen.logger_config import logger

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator
    from massgen.subagent.models import SubagentResult


class SubagentLifecycleCoordinator:
    """Coordinates background subagent completions, MCP bridge, direct spawn, and TUI hooks."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    # ------------------------------------------------------------------
    # Completion queue + background interruption scheduling
    # ------------------------------------------------------------------
    def on_subagent_complete(
        self,
        parent_agent_id: str,
        subagent_id: str,
        result: SubagentResult,
    ) -> None:
        orch = self._orchestrator
        if parent_agent_id not in orch._pending_subagent_results:
            orch._pending_subagent_results[parent_agent_id] = []
        orch._pending_subagent_results[parent_agent_id].append((subagent_id, result))
        logger.info(
            f"[Orchestrator] Background subagent {subagent_id} completed for {parent_agent_id} " f"(status={result.status}, success={result.success})",
        )
        self.schedule_background_wait_interrupt_for_agent(
            parent_agent_id,
            trigger="background_subagent_complete",
        )

    def on_background_subagent_complete(
        self,
        parent_agent_id: str,
        subagent_id: str,
        result: SubagentResult,
    ) -> None:
        self.on_subagent_complete(parent_agent_id, subagent_id, result)

    def schedule_background_wait_interrupt_for_agent(
        self,
        agent_id: str,
        trigger: str = "background_subagent_complete",
    ) -> None:
        orch = self._orchestrator
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return

        loop.create_task(
            orch._maybe_interrupt_background_wait_for_agent(
                agent_id,
                trigger=trigger,
            ),
        )

    # ------------------------------------------------------------------
    # Pending-result polling
    # ------------------------------------------------------------------
    async def get_pending_subagent_results_async(
        self,
        agent_id: str,
    ) -> list[tuple[str, SubagentResult]]:
        orch = self._orchestrator
        try:
            agent = orch.agents.get(agent_id)
            if not agent:
                return []

            if agent_id not in orch._injected_subagents:
                orch._injected_subagents[agent_id] = set()

            list_result = await self.call_subagent_mcp_tool_async(
                parent_agent_id=agent_id,
                tool_name="list_subagents",
                params={},
            )

            if not isinstance(list_result, dict):
                return []

            if not list_result.get("success") or not list_result.get("subagents"):
                return []

            from massgen.subagent.models import SubagentResult as RuntimeSubagentResult

            pending_results = []
            for subagent_info in list_result["subagents"]:
                subagent_id = subagent_info.get("subagent_id")
                status = subagent_info.get("status")

                if status != "completed" or subagent_id in orch._injected_subagents[agent_id]:
                    continue

                result_data = subagent_info.get("result")
                if not isinstance(result_data, dict):
                    continue

                try:
                    result = RuntimeSubagentResult.from_dict(result_data)
                except Exception:
                    result = RuntimeSubagentResult(
                        subagent_id=result_data.get("subagent_id", subagent_id),
                        success=result_data.get("success", False),
                        status=result_data.get("status", "error"),
                        answer=result_data.get("answer", ""),
                        error=result_data.get("error"),
                        workspace_path=result_data.get("workspace_path", result_data.get("workspace", "")),
                        execution_time_seconds=result_data.get("execution_time_seconds", 0.0),
                        token_usage=result_data.get("token_usage", {}),
                    )

                pending_results.append((subagent_id, result))
                orch._injected_subagents[agent_id].add(subagent_id)
                logger.debug(
                    f"[Orchestrator] Fetched completed subagent {subagent_id} for {agent_id} " f"(status={result.status})",
                )

            if pending_results:
                logger.debug(
                    f"[Orchestrator] Retrieved {len(pending_results)} completed subagent(s) for {agent_id}",
                )

            return pending_results

        except Exception as e:
            logger.error(f"[Orchestrator] Error polling for completed subagents: {e}", exc_info=True)
            return []

    async def collect_pending_subagent_results_async(
        self,
        agent_id: str,
    ) -> list[tuple[str, SubagentResult]]:
        orch = self._orchestrator
        pending_subagent_results: list[tuple[str, SubagentResult]] = []

        local_pending = list(orch._pending_subagent_results.get(agent_id, []))
        if local_pending:
            pending_subagent_results.extend(local_pending)

        polled_pending = await self.get_pending_subagent_results_async(agent_id)
        if polled_pending:
            pending_subagent_results.extend(polled_pending)

        if not pending_subagent_results:
            return []

        deduped_results: dict[str, SubagentResult] = {}
        for subagent_id, result in pending_subagent_results:
            deduped_results[subagent_id] = result

        return list(deduped_results.items())

    def get_pending_subagent_results(
        self,
        agent_id: str,
    ) -> list[tuple[str, SubagentResult]]:
        from massgen.utils import run_async_safely

        return run_async_safely(self.get_pending_subagent_results_async(agent_id))

    def consume_pending_subagent_results(
        self,
        agent_id: str,
        consumed_subagent_ids: set[str],
    ) -> None:
        """Remove only the just-delivered subagent results, preserving late appends.

        R2/R3 fix: the injection paths previously did
        ``_pending_subagent_results.pop(agent_id, None)`` after an ``await`` window,
        which discarded any result a background task appended during that window.
        This removes only the entries whose ``subagent_id`` was actually consumed,
        dropping the key only when nothing remains. A result that arrived
        concurrently survives for the next injection cycle.
        """
        orch = self._orchestrator
        existing = orch._pending_subagent_results.get(agent_id)
        if existing is None:
            return
        remaining = [entry for entry in existing if entry[0] not in consumed_subagent_ids]
        if remaining:
            orch._pending_subagent_results[agent_id] = remaining
        else:
            orch._pending_subagent_results.pop(agent_id, None)

    # ------------------------------------------------------------------
    # Cancellation flows
    # ------------------------------------------------------------------
    async def cancel_running_subagents_for_agent(self, agent_id: str) -> int:
        try:
            list_result = await self.call_subagent_mcp_tool_async(
                parent_agent_id=agent_id,
                tool_name="list_subagents",
                params={},
            )
        except Exception as exc:
            logger.debug(
                "[Orchestrator] Failed to list subagents for cancellation (%s): %s",
                agent_id,
                exc,
                exc_info=True,
            )
            return 0

        if not isinstance(list_result, dict) or not list_result.get("success"):
            return 0

        subagents = list_result.get("subagents")
        if not isinstance(subagents, list):
            return 0

        active_ids: set[str] = set()
        for entry in subagents:
            if not isinstance(entry, dict):
                continue
            subagent_id = str(entry.get("subagent_id") or "").strip()
            status = str(entry.get("status") or "").strip().lower()
            if subagent_id and status in {"running", "pending"}:
                active_ids.add(subagent_id)

        cancelled = 0
        for subagent_id in sorted(active_ids):
            try:
                cancel_result = await self.call_subagent_mcp_tool_async(
                    parent_agent_id=agent_id,
                    tool_name="cancel_subagent",
                    params={"subagent_id": subagent_id},
                )
            except Exception as exc:
                logger.debug(
                    "[Orchestrator] Failed to cancel subagent %s for %s: %s",
                    subagent_id,
                    agent_id,
                    exc,
                    exc_info=True,
                )
                continue

            if isinstance(cancel_result, dict) and cancel_result.get("success"):
                cancelled += 1

        return cancelled

    async def cancel_running_background_work_for_agent(self, agent_id: str) -> None:
        orch = self._orchestrator
        cancelled_subagents = await self.cancel_running_subagents_for_agent(agent_id)
        cancelled_background_jobs = False

        agent = orch.agents.get(agent_id)
        backend = getattr(agent, "backend", None) if agent else None
        cancel_background_jobs = getattr(backend, "_cancel_all_background_tool_jobs", None)
        if callable(cancel_background_jobs):
            try:
                maybe_awaitable = cancel_background_jobs()
                if inspect.isawaitable(maybe_awaitable):
                    await maybe_awaitable
                cancelled_background_jobs = True
            except Exception as exc:
                logger.debug(
                    "[Orchestrator] Failed to cancel background jobs for %s: %s",
                    agent_id,
                    exc,
                    exc_info=True,
                )

        cancelled_trace = False
        trace_task = orch._background_trace_tasks.pop(agent_id, None)
        if trace_task and not trace_task.done():
            trace_task.cancel()
            cancelled_trace = True

        if cancelled_subagents or cancelled_background_jobs or cancelled_trace:
            logger.info(
                "[Orchestrator] Round-end cleanup for %s: " "cancelled_subagents=%s, cancelled_background_jobs=%s, " "cancelled_trace_analyzer=%s",
                agent_id,
                cancelled_subagents,
                cancelled_background_jobs,
                cancelled_trace,
            )

    # ------------------------------------------------------------------
    # Pure helpers (static)
    # ------------------------------------------------------------------
    @staticmethod
    def try_parse_json_dict_from_text(raw_text: str | None) -> dict[str, Any] | None:
        if not isinstance(raw_text, str):
            return None
        payload = raw_text.strip()
        if not payload:
            return None
        try:
            parsed = json.loads(payload)
        except Exception:
            try:
                parsed = ast.literal_eval(payload)
            except Exception:
                return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def extract_text_from_mcp_content_payload(content: Any) -> str | None:
        if content is None:
            return None

        if isinstance(content, str):
            return content

        if isinstance(content, dict):
            if "text" in content:
                return str(content["text"])
            nested = content.get("content")
            return SubagentLifecycleCoordinator.extract_text_from_mcp_content_payload(nested)

        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    text_parts.append(item)
                    continue
                if hasattr(item, "text"):
                    text_parts.append(str(item.text))
                    continue
                if isinstance(item, dict):
                    if "text" in item:
                        text_parts.append(str(item["text"]))
                        continue
                    nested = SubagentLifecycleCoordinator.extract_text_from_mcp_content_payload(item)
                    if nested:
                        text_parts.append(nested)
            return "\n".join(part for part in text_parts if part) or None

        return None

    @staticmethod
    def normalize_subagent_mcp_result(raw_result: Any) -> dict[str, Any] | None:
        cls = SubagentLifecycleCoordinator
        if raw_result is None:
            return None

        if isinstance(raw_result, tuple) and len(raw_result) >= 2:
            tuple_obj = raw_result[1]
            if isinstance(tuple_obj, dict):
                return tuple_obj
            parsed_from_str = cls.try_parse_json_dict_from_text(
                raw_result[0] if isinstance(raw_result[0], str) else None,
            )
            if parsed_from_str is not None:
                return parsed_from_str
            raw_result = tuple_obj

        if isinstance(raw_result, dict):
            if "success" not in raw_result and "content" in raw_result:
                content_text = cls.extract_text_from_mcp_content_payload(
                    raw_result.get("content"),
                )
                parsed_content = cls.try_parse_json_dict_from_text(content_text)
                if parsed_content is not None:
                    return parsed_content
            for key in ("structuredContent", "structured_content"):
                structured = raw_result.get(key)
                if isinstance(structured, dict):
                    return structured
            return raw_result

        if isinstance(raw_result, str):
            return cls.try_parse_json_dict_from_text(raw_result)

        for attr_name in ("structuredContent", "structured_content"):
            structured = getattr(raw_result, attr_name, None)
            if isinstance(structured, dict):
                return structured
        if hasattr(raw_result, "content"):
            content_text = cls.extract_text_from_mcp_content_payload(
                getattr(raw_result, "content", None),
            )
            parsed_content = cls.try_parse_json_dict_from_text(content_text)
            if parsed_content is not None:
                return parsed_content
            is_error = bool(getattr(raw_result, "isError", False))
            if content_text:
                return {"success": not is_error, "output": content_text}
            return {"success": not is_error}

        return None

    @staticmethod
    def is_reconnectable_background_mcp_error(error: Exception | str) -> bool:
        normalized = str(error or "").strip().lower()
        if not normalized:
            return False
        reconnect_markers = (
            "not connected",
            "disconnected",
            "connection closed",
            "connection lost",
            "broken pipe",
        )
        return any(marker in normalized for marker in reconnect_markers)

    # ------------------------------------------------------------------
    # MCP bridge
    # ------------------------------------------------------------------
    async def call_subagent_mcp_tool_async(
        self,
        parent_agent_id: str,
        tool_name: str,
        params: dict[str, Any],
    ) -> dict[str, Any] | None:
        orch = self._orchestrator
        agent = orch.agents.get(parent_agent_id)
        if not agent:
            return None

        full_tool_name = f"mcp__{orch._subagent_server_name(parent_agent_id)}__{tool_name}"
        backend = getattr(agent, "backend", None)
        error_messages: list[str] = []
        attempted_path = False

        mcp_executor = getattr(backend, "_execute_mcp_function_with_retry", None)
        if callable(mcp_executor):
            attempted_path = True
            try:
                raw_result = await mcp_executor(full_tool_name, json.dumps(params))
                normalized = self.normalize_subagent_mcp_result(raw_result)
                if normalized is not None:
                    return normalized
                error_messages.append(
                    f"Unparseable MCP result from executor for {full_tool_name}",
                )
            except Exception as exc:
                logger.debug(
                    "[Orchestrator] Backend MCP executor call failed for %s (%s): %s",
                    full_tool_name,
                    parent_agent_id,
                    exc,
                )
                error_messages.append(str(exc))

        background_client_getter = getattr(backend, "_get_background_mcp_client", None)
        if callable(background_client_getter):
            attempted_path = True
            try:
                client = await background_client_getter()
                if not client:
                    init_error = str(getattr(backend, "_background_mcp_init_error", "") or "").strip()
                    error_messages.append(
                        init_error or f"Background MCP client unavailable for {full_tool_name}",
                    )
                    raw_result = None
                else:
                    raw_result = None
                    background_error: Exception | None = None
                    retry_error: Exception | None = None
                    retry_attempted = False

                    try:
                        raw_result = await client.call_tool(
                            tool_name=full_tool_name,
                            arguments=params,
                        )
                    except Exception as exc:
                        background_error = exc
                        reconnect = getattr(client, "reconnect", None)
                        should_retry = callable(reconnect) and self.is_reconnectable_background_mcp_error(exc)
                        if should_retry:
                            retry_attempted = True
                            logger.info(
                                "[Orchestrator] Retrying %s for %s after background MCP reconnect",
                                full_tool_name,
                                parent_agent_id,
                            )
                            try:
                                reconnect_result = reconnect(max_retries=1)
                                if inspect.isawaitable(reconnect_result):
                                    reconnect_result = await reconnect_result
                                if reconnect_result:
                                    raw_result = await client.call_tool(
                                        tool_name=full_tool_name,
                                        arguments=params,
                                    )
                                    background_error = None
                                else:
                                    retry_error = RuntimeError(
                                        "Background MCP reconnect returned False",
                                    )
                            except Exception as reconnect_exc:
                                retry_error = reconnect_exc

                    if background_error is not None and raw_result is None:
                        logger.debug(
                            "[Orchestrator] Background MCP client call failed for %s (%s): %s",
                            full_tool_name,
                            parent_agent_id,
                            background_error,
                        )
                        error_messages.append(str(background_error))
                        if retry_attempted and retry_error is not None:
                            error_messages.append(
                                f"Reconnect retry failed for {full_tool_name}: {retry_error}",
                            )
                normalized = self.normalize_subagent_mcp_result(raw_result)
                if normalized is not None:
                    return normalized
                if raw_result is not None:
                    error_messages.append(
                        f"Unparseable MCP result from background client for {full_tool_name}",
                    )
            except Exception as exc:
                logger.debug(
                    "[Orchestrator] Background MCP client call failed for %s (%s): %s",
                    full_tool_name,
                    parent_agent_id,
                    exc,
                )
                error_messages.append(str(exc))

        mcp_client = getattr(agent, "mcp_client", None)
        if mcp_client and hasattr(mcp_client, "call_tool"):
            attempted_path = True
            try:
                call_result = mcp_client.call_tool(full_tool_name, params)
                if inspect.isawaitable(call_result):
                    call_result = await call_result
                normalized = self.normalize_subagent_mcp_result(call_result)
                if normalized is not None:
                    return normalized
                error_messages.append(
                    f"Unparseable MCP result from legacy client for {full_tool_name}",
                )
            except Exception as exc:
                logger.debug(
                    "[Orchestrator] Legacy MCP client call failed for %s (%s): %s",
                    full_tool_name,
                    parent_agent_id,
                    exc,
                )
                error_messages.append(str(exc))

        if error_messages:
            deduped_messages = list(dict.fromkeys(msg for msg in error_messages if msg))
            return {
                "success": False,
                "operation": tool_name,
                "error": "; ".join(deduped_messages),
            }
        if attempted_path:
            return {
                "success": False,
                "operation": tool_name,
                "error": f"No usable MCP result returned for {full_tool_name}",
            }
        return {
            "success": False,
            "operation": tool_name,
            "error": f"No programmatic MCP client available for {full_tool_name}",
        }

    def call_subagent_mcp_tool(
        self,
        parent_agent_id: str,
        tool_name: str,
        params: dict[str, Any],
    ) -> dict[str, Any] | None:
        from massgen.utils import run_async_safely

        return run_async_safely(
            self.call_subagent_mcp_tool_async(parent_agent_id, tool_name, params),
        )

    def has_subagent_mcp_for_agent(self, agent_id: str) -> bool:
        orch = self._orchestrator
        agent = orch.agents.get(agent_id)
        if not agent:
            return False
        fs_mgr = getattr(getattr(agent, "backend", None), "filesystem_manager", None)
        return fs_mgr is not None

    # ------------------------------------------------------------------
    # Direct-spawn fallback
    # ------------------------------------------------------------------
    async def direct_spawn_subagents(
        self,
        parent_agent_id: str,
        tasks: list[dict[str, Any]],
        refine: bool = True,
    ) -> dict[str, Any]:
        orch = self._orchestrator
        from massgen.mcp_tools.subagent import _subagent_mcp_server as mcp_mod

        agent = orch.agents.get(parent_agent_id)
        fs_mgr = getattr(getattr(agent, "backend", None), "filesystem_manager", None)
        if fs_mgr and fs_mgr.cwd:
            ws_root = Path(fs_mgr.cwd).resolve()
        else:
            spawn_id = _uuid.uuid4().hex[:8]
            ws_root = (Path(".massgen") / "workspaces" / f"direct_spawn_{parent_agent_id}_{spawn_id}").resolve()
            ws_root.mkdir(parents=True, exist_ok=True)

        orch._write_subagent_type_dirs(ws_root)
        orch._ensure_context_md_for_round_evaluator(ws_root, parent_agent_id)

        agent_configs: list[dict[str, Any]] = []
        for aid, a in orch.agents.items():
            agent_cfg: dict[str, Any] = {"id": aid}
            if hasattr(a.backend, "config"):
                backend_cfg = {k: v for k, v in a.backend.config.items() if k not in ("mcp_servers", "_config_path")}
                if "type" not in backend_cfg and hasattr(a.backend, "get_provider_name"):
                    from massgen.backend.capabilities import normalize_backend_type

                    backend_cfg["type"] = normalize_backend_type(a.backend.get_provider_name())
                agent_cfg["backend"] = backend_cfg
            agent_configs.append(agent_cfg)

        coord_cfg = getattr(orch.config, "coordination_config", None)
        sub_orch_config = getattr(coord_cfg, "subagent_orchestrator", None)
        if isinstance(sub_orch_config, dict):
            from massgen.subagent.models import SubagentOrchestratorConfig as _SOC

            sub_orch_config = _SOC(**sub_orch_config)

        log_dir: str | None = None
        try:
            from massgen.logger_config import get_log_session_dir

            _log_session = get_log_session_dir()
            if _log_session:
                log_dir = str(_log_session)
        except Exception:
            pass
        if not log_dir:
            if hasattr(orch, "_log_dir") and orch._log_dir:
                log_dir = str(orch._log_dir)
            elif hasattr(orch, "log_directory") and orch.log_directory:
                log_dir = str(orch.log_directory)

        parent_context_paths: list[dict[str, str]] = []
        agent = orch.agents.get(parent_agent_id)
        if agent and hasattr(agent.backend, "config"):
            raw_ctx = agent.backend.config.get("context_paths", [])
            if isinstance(raw_ctx, list):
                for entry in raw_ctx:
                    if isinstance(entry, str):
                        parent_context_paths.append(
                            {"path": entry, "permission": "read"},
                        )
                    elif isinstance(entry, dict) and "path" in entry:
                        parent_context_paths.append(entry)

        orch_temp = getattr(orch, "_agent_temporary_workspace", None)
        orch_temp_resolved: str | None = None
        if orch_temp:
            _resolved = Path(orch_temp).resolve()
            if _resolved.exists():
                orch_temp_resolved = str(_resolved)
                parent_context_paths.append(
                    {"path": orch_temp_resolved, "permission": "read"},
                )

        configured_timeout = getattr(coord_cfg, "subagent_default_timeout", 600) if coord_cfg else 600

        lock = mcp_mod._get_direct_spawn_lock()
        async with lock:
            saved = mcp_mod.configure_direct_spawn(
                workspace_path=ws_root,
                parent_agent_id=parent_agent_id,
                orchestrator_id=getattr(orch, "orchestrator_id", "unknown"),
                parent_agent_configs=agent_configs,
                subagent_orchestrator_config=sub_orch_config,
                log_directory=log_dir,
                agent_temporary_workspace=orch_temp_resolved,
                parent_context_paths=parent_context_paths,
                parent_coordination_config=(coord_cfg.__dict__ if coord_cfg and hasattr(coord_cfg, "__dict__") else None),
                default_timeout=configured_timeout,
                max_timeout=int(configured_timeout * 1.5),
            )
            try:
                return await mcp_mod.spawn_subagents_direct(
                    tasks=tasks,
                    refine=refine,
                    timeout_override=configured_timeout,
                )
            finally:
                mcp_mod.reset_direct_spawn(saved)

    # ------------------------------------------------------------------
    # Runtime message delivery
    # ------------------------------------------------------------------
    def send_runtime_message_via_direct_inbox_write(
        self,
        parent_agent_id: str,
        subagent_id: str,
        content: str,
        target_agents: list[str] | None = None,
    ) -> bool:
        parent_workspace = self.resolve_subagent_parent_workspace(parent_agent_id)
        if parent_workspace is None or not parent_workspace.exists():
            return False

        subagent_workspace = parent_workspace / "subagents" / subagent_id / "workspace"
        if not subagent_workspace.exists() or not subagent_workspace.is_dir():
            return False

        inbox_dir = subagent_workspace / ".massgen" / "runtime_inbox"
        inbox_dir.mkdir(parents=True, exist_ok=True)

        msg_data = {
            "content": content,
            "source": "parent",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "target_agents": target_agents,
        }
        file_stem = f"msg_{int(time.time())}_{secrets.token_hex(4)}"
        tmp_path = inbox_dir / f"{file_stem}.json.tmp"
        final_path = inbox_dir / f"{file_stem}.json"
        tmp_path.write_text(json.dumps(msg_data, indent=2))
        tmp_path.rename(final_path)

        logger.info(
            f"[Orchestrator] Runtime message delivered via direct inbox fallback for subagent {subagent_id} " f"(parent={parent_agent_id}, target={target_agents})",
        )
        return True

    def resolve_subagent_parent_workspace(self, parent_agent_id: str) -> Path | None:
        orch = self._orchestrator
        agent = orch.agents.get(parent_agent_id)
        backend = getattr(agent, "backend", None) if agent else None
        filesystem_manager = getattr(backend, "filesystem_manager", None) if backend else None

        backend_workspace_path: Path | None = None
        get_workspace = getattr(filesystem_manager, "get_current_workspace", None) if filesystem_manager else None
        if callable(get_workspace):
            try:
                resolved = get_workspace()
                if resolved:
                    backend_workspace_path = Path(resolved)
            except Exception:
                backend_workspace_path = None

        if backend_workspace_path is None and filesystem_manager is not None:
            cwd = getattr(filesystem_manager, "cwd", None)
            if cwd:
                backend_workspace_path = Path(cwd)

        workspace_path: Path | None = None
        if orch._agent_temporary_workspace:
            temp_workspace = Path(orch._agent_temporary_workspace)
            if temp_workspace.name == "temp" and temp_workspace.parent:
                workspace_path = temp_workspace.parent
            elif temp_workspace.name == "temp_workspaces":
                workspace_path = None
            elif temp_workspace.parent.name == "temp_workspaces":
                workspace_path = temp_workspace

        if workspace_path is None:
            workspace_path = backend_workspace_path

        if workspace_path is None:
            return None

        if not (workspace_path / "subagents").exists():
            parent_candidate = workspace_path.parent
            if (parent_candidate / "subagents").exists():
                workspace_path = parent_candidate

        return workspace_path

    def send_runtime_message_to_subagent(
        self,
        subagent_id: str,
        content: str,
        target_agents: list[str] | None = None,
    ) -> bool:
        orch = self._orchestrator
        params: dict[str, Any] = {
            "subagent_id": subagent_id,
            "message": content,
        }
        if target_agents is not None:
            params["target_agents"] = target_agents

        for parent_agent_id in orch.agents:
            result = self.call_subagent_mcp_tool(
                parent_agent_id=parent_agent_id,
                tool_name="send_message_to_subagent",
                params=params,
            )
            if isinstance(result, dict) and result.get("success"):
                logger.info(
                    f"[Orchestrator] Runtime message delivered to subagent {subagent_id} via {parent_agent_id} " f"(target={target_agents})",
                )
                return True
            if self.send_runtime_message_via_direct_inbox_write(
                parent_agent_id=parent_agent_id,
                subagent_id=subagent_id,
                content=content,
                target_agents=target_agents,
            ):
                return True
            logger.debug(
                f"[Orchestrator] Runtime message delivery attempt via {parent_agent_id} " f"failed for subagent {subagent_id} (result={result})",
            )
        logger.warning(
            f"[Orchestrator] Failed to deliver runtime message to subagent {subagent_id} " f"after trying {len(orch.agents)} parent agent route(s)",
        )
        return False

    # ------------------------------------------------------------------
    # TUI continue + status callback + display wiring
    # ------------------------------------------------------------------
    def continue_subagent_from_tui(
        self,
        subagent_id: str,
        message: str,
        timeout_seconds: int | None = None,
        background: bool = True,
    ) -> bool:
        orch = self._orchestrator
        params: dict[str, Any] = {
            "subagent_id": subagent_id,
            "message": message,
            "background": bool(background),
        }
        if timeout_seconds is not None:
            params["timeout_seconds"] = timeout_seconds

        for parent_agent_id in orch.agents:
            result = self.call_subagent_mcp_tool(
                parent_agent_id=parent_agent_id,
                tool_name="continue_subagent",
                params=params,
            )
            if isinstance(result, dict) and result.get("success"):
                if background:
                    orch._injected_subagents.setdefault(parent_agent_id, set()).discard(subagent_id)

                    display = None
                    if hasattr(orch, "coordination_ui") and orch.coordination_ui:
                        display = getattr(orch.coordination_ui, "display", None)

                    continued_subagent_id = subagent_id
                    subagents_payload = result.get("subagents")
                    if isinstance(subagents_payload, list) and subagents_payload:
                        first = subagents_payload[0]
                        if isinstance(first, dict):
                            continued_subagent_id = str(first.get("subagent_id") or subagent_id)

                    if display and hasattr(display, "notify_runtime_subagent_started"):
                        try:
                            task_preview = message.strip() or f"Continue {continued_subagent_id}"
                            if len(task_preview) > 300:
                                task_preview = task_preview[:297] + "..."
                            timeout_for_display = int(
                                timeout_seconds or orch.config.coordination_config.subagent_default_timeout or 300,
                            )
                            call_id = f"continue_{continued_subagent_id}_{int(time.time() * 1000)}"
                            display.notify_runtime_subagent_started(
                                agent_id=parent_agent_id,
                                subagent_id=continued_subagent_id,
                                task=task_preview,
                                timeout_seconds=timeout_for_display,
                                call_id=call_id,
                                status_callback=self.build_tui_continue_status_callback(
                                    parent_agent_id=parent_agent_id,
                                    fallback_task=task_preview,
                                    fallback_timeout_seconds=timeout_for_display,
                                ),
                                log_path=None,
                            )
                        except Exception:
                            logger.opt(exception=True).warning(
                                f"[Orchestrator] Failed to notify TUI of continued subagent " f"{subagent_id} for parent {parent_agent_id}",
                            )

                logger.info(
                    f"[Orchestrator] Continue request dispatched for subagent {subagent_id} via {parent_agent_id}",
                )
                return True
            logger.debug(
                "[Orchestrator] Continue subagent attempt via %s failed for %s (result=%s)",
                parent_agent_id,
                subagent_id,
                result,
            )

        logger.warning(
            f"[Orchestrator] Failed to continue subagent {subagent_id} after trying {len(orch.agents)} parent agent route(s)",
        )
        return False

    def build_tui_continue_status_callback(
        self,
        parent_agent_id: str,
        fallback_task: str,
        fallback_timeout_seconds: int | None,
    ):
        from massgen.subagent.models import SubagentDisplayData

        def _map_status(raw_status: Any) -> tuple[str, int]:
            normalized = str(raw_status or "").lower().strip()
            if normalized == "completed":
                return "completed", 100
            if normalized in {"completed_but_timeout", "partial", "timeout"}:
                return "timeout", 100
            if normalized in {"failed", "error"}:
                return "failed", 0
            if normalized in {"cancelled", "canceled", "stopped"}:
                return "canceled", 0
            if normalized == "pending":
                return "pending", 0
            return "running", 0

        def _callback(subagent_id: str) -> SubagentDisplayData | None:
            payload = self.call_subagent_mcp_tool(
                parent_agent_id=parent_agent_id,
                tool_name="list_subagents",
                params={},
            )
            if not isinstance(payload, dict) or not payload.get("success"):
                return None

            subagents = payload.get("subagents")
            if not isinstance(subagents, list):
                return None

            matched_entry = None
            for entry in subagents:
                if not isinstance(entry, dict):
                    continue
                candidate_id = str(entry.get("subagent_id") or entry.get("id") or "").strip()
                if candidate_id == subagent_id:
                    matched_entry = entry
                    break

            if not isinstance(matched_entry, dict):
                return None

            result_payload = matched_entry.get("result")
            if not isinstance(result_payload, dict):
                result_payload = {}

            status_source = matched_entry.get("status", result_payload.get("status"))
            display_status, progress = _map_status(status_source)

            answer = result_payload.get("answer")
            answer_preview = None
            if isinstance(answer, str) and answer:
                answer_preview = answer[:200]

            error = result_payload.get("error")
            if not error:
                error = matched_entry.get("error")

            execution_time = result_payload.get("execution_time_seconds")
            if execution_time is None:
                execution_time = matched_entry.get("execution_time_seconds", 0.0)
            try:
                elapsed_seconds = float(execution_time or 0.0)
            except Exception:
                elapsed_seconds = 0.0

            timeout_seconds = matched_entry.get("timeout_seconds", fallback_timeout_seconds)
            try:
                timeout_value = float(timeout_seconds or fallback_timeout_seconds or 300)
            except Exception:
                timeout_value = float(fallback_timeout_seconds or 300)

            workspace = str(
                result_payload.get("workspace") or matched_entry.get("workspace") or "",
            )

            task = str(matched_entry.get("task") or fallback_task or "")

            return SubagentDisplayData(
                id=subagent_id,
                task=task,
                status=display_status,
                progress_percent=progress,
                elapsed_seconds=elapsed_seconds,
                timeout_seconds=timeout_value,
                workspace_path=workspace,
                workspace_file_count=0,
                last_log_line=str(error or ""),
                error=str(error) if isinstance(error, str) and error else None,
                answer_preview=answer_preview,
                log_path=result_payload.get("log_path"),
                context_paths=[],
                subagent_type=None,
            )

        return _callback

    def share_subagent_message_callback_with_display(self) -> None:
        orch = self._orchestrator
        display = None
        if hasattr(orch, "coordination_ui") and orch.coordination_ui:
            display = getattr(orch.coordination_ui, "display", None)
        if display and hasattr(display, "set_subagent_message_callback"):
            display.set_subagent_message_callback(orch.send_runtime_message_to_subagent)
            logger.info("[Orchestrator] Shared subagent message callback with TUI display")
        if display and hasattr(display, "set_subagent_continue_callback"):
            display.set_subagent_continue_callback(orch.continue_subagent_from_tui)
            logger.info("[Orchestrator] Shared subagent continue callback with TUI display")
        if display and hasattr(display, "set_answer_now_callback"):
            display.set_answer_now_callback(orch.request_answer_now)
            logger.info("[Orchestrator] Shared Answer Now callback with TUI display")

    def flush_pending_subagent_results(self) -> None:
        orch = self._orchestrator
        if not hasattr(orch, "_pending_subagent_results"):
            return

        for agent_id, pending in orch._pending_subagent_results.items():
            if pending:
                logger.warning(
                    f"[Orchestrator] {len(pending)} background subagent result(s) for {agent_id} " f"were not delivered (parent finished before injection). " f"IDs: {[p[0] for p in pending]}",
                )
                orch._pending_subagent_results[agent_id] = []
