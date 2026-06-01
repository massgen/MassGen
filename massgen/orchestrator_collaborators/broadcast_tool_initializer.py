"""Broadcast workflow-tool initialization, extracted from Orchestrator.

Reassigns ``orchestrator.workflow_tools`` (shared with streaming/agent-turn
code).  All mutation routes through the orchestrator back-ref so there is a
single source of truth.

``BroadcastToolkit`` is constructed with ``orchestrator=<orchestrator>`` —
NOT this collaborator — so toolkit callbacks land back on the orchestrator
exactly as they did before extraction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from massgen.logger_config import logger

if TYPE_CHECKING:
    from massgen.orchestrator import Orchestrator


class BroadcastToolInitializer:
    """Initialize broadcast tools + register them as custom tools per-backend."""

    def __init__(self, orchestrator: Orchestrator) -> None:
        self._orchestrator = orchestrator

    def init_broadcast_tools(self) -> None:
        """Initialize broadcast tools if enabled in coordination config."""
        orch = self._orchestrator
        # Local imports to avoid widening orchestrator import surface.
        from massgen.tool import get_workflow_tools

        has_coord = hasattr(orch.config, "coordination_config")
        has_broadcast = hasattr(orch.config.coordination_config, "broadcast") if has_coord else False
        logger.info(
            f"[Orchestrator] Checking broadcast config: has_coord={has_coord}, has_broadcast={has_broadcast}",
        )
        if hasattr(orch.config, "coordination_config") and hasattr(
            orch.config.coordination_config,
            "broadcast",
        ):
            broadcast_mode = orch.config.coordination_config.broadcast
            logger.info(
                f"[Orchestrator] Broadcast mode value: {broadcast_mode}, type: {type(broadcast_mode)}",
            )
            if broadcast_mode and broadcast_mode is not False:
                logger.info(
                    f"[Orchestrator] Broadcasting enabled (mode: {broadcast_mode}). Adding broadcast tools to workflow",
                )

                wait_by_default = True
                logger.info(
                    "[Orchestrator] Using blocking broadcasts (wait=True) with priority system to prevent deadlocks",
                )

                broadcast_sensitivity = getattr(
                    orch.config.coordination_config,
                    "broadcast_sensitivity",
                    "medium",
                )
                logger.info(
                    f"[Orchestrator] Broadcast sensitivity: {broadcast_sensitivity}",
                )

                _is_decomposition = getattr(orch.config, "coordination_mode", "voting") == "decomposition"
                # Mutate SHARED-MUTABLE workflow_tools back on the orchestrator.
                orch.workflow_tools = get_workflow_tools(
                    valid_agent_ids=sorted(orch.agents.keys()),
                    template_overrides=getattr(
                        orch.message_templates,
                        "_template_overrides",
                        {},
                    ),
                    api_format="chat_completions",
                    orchestrator=orch,
                    broadcast_mode=broadcast_mode,
                    broadcast_wait_by_default=wait_by_default,
                    decomposition_mode=_is_decomposition,
                )
                tool_names = [t.get("function", {}).get("name", "unknown") for t in orch.workflow_tools]
                logger.info(
                    f"[Orchestrator] Broadcast tools added to workflow ({len(orch.workflow_tools)} total tools): {tool_names}",
                )

                self.register_broadcast_custom_tools(
                    broadcast_mode,
                    wait_by_default,
                    broadcast_sensitivity,
                )
            else:
                logger.info("[Orchestrator] Broadcasting disabled")
        else:
            logger.info("[Orchestrator] Broadcast config not found")

    def register_broadcast_custom_tools(
        self,
        broadcast_mode: str,
        wait_by_default: bool,
        sensitivity: str = "medium",
    ) -> None:
        """Register broadcast tools as custom tools with all agent backends."""
        orch = self._orchestrator
        from massgen.tool.workflow_toolkits.broadcast import BroadcastToolkit

        # BroadcastToolkit must receive the ORCHESTRATOR (not this collaborator)
        # so toolkit callbacks land back on the orchestrator unchanged.
        broadcast_toolkit = BroadcastToolkit(
            orchestrator=orch,
            broadcast_mode=broadcast_mode,
            wait_by_default=wait_by_default,
            sensitivity=sensitivity,
        )

        for agent_id, agent in orch.agents.items():
            backend = agent.backend

            has_tool_manager = hasattr(backend, "custom_tool_manager") or hasattr(
                backend,
                "_custom_tool_manager",
            )
            if not has_tool_manager:
                logger.warning(
                    f"[Orchestrator] Agent {agent_id} backend doesn't support custom tool manager - broadcast tools will use orchestrator handling",
                )
                continue

            if not hasattr(backend, "_broadcast_toolkit"):
                backend._broadcast_toolkit = broadcast_toolkit
                if not hasattr(backend, "_custom_tool_names"):
                    backend._custom_tool_names = set()
                backend._custom_tool_names.add("ask_others")
                logger.info(
                    f"[Orchestrator] Registered ask_others as custom tool for agent {agent_id}",
                )

            if broadcast_mode == "agents":
                backend._custom_tool_names.add("respond_to_broadcast")
                logger.info(
                    f"[Orchestrator] Registered respond_to_broadcast as custom tool for agent {agent_id}",
                )

            if not wait_by_default:
                backend._custom_tool_names.add("check_broadcast_status")
                backend._custom_tool_names.add("get_broadcast_responses")
                logger.info(
                    f"[Orchestrator] Registered polling broadcast tools for agent {agent_id}",
                )
