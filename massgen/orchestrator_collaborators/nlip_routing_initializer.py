"""NLIP routing initialization, extracted from Orchestrator."""

from __future__ import annotations

from typing import Any

from massgen.logger_config import logger


class NlipRoutingInitializer:
    """Stateless helper that enables NLIP routing across a set of agents.

    Takes the agents mapping and the shared nlip_config explicitly; it holds no
    mutable state of its own.
    """

    def initialize(self, agents: dict[str, Any], nlip_config: Any) -> None:
        """Initialize NLIP routing for all agents."""
        logger.info(
            f"[Orchestrator] Initializing NLIP routing for {len(agents)} agents",
        )

        nlip_enabled_count = 0
        nlip_skipped_count = 0

        for agent_id, agent in agents.items():
            # Check if agent has config
            if not hasattr(agent, "config"):
                logger.debug(
                    f"[Orchestrator] Agent {agent_id} has no config, skipping NLIP",
                )
                nlip_skipped_count += 1
                continue

            # Check if backend supports NLIP (has custom_tool_manager)
            backend = getattr(agent, "backend", None)
            if not backend:
                logger.debug(
                    f"[Orchestrator] Agent {agent_id} has no backend, skipping NLIP",
                )
                nlip_skipped_count += 1
                continue

            tool_manager = getattr(backend, "custom_tool_manager", None)
            if not tool_manager:
                logger.info(
                    f"[Orchestrator] Agent {agent_id} backend does not support NLIP (no custom_tool_manager), skipping",
                )
                nlip_skipped_count += 1
                continue

            # Backend supports NLIP, enable it
            agent.config.enable_nlip = True
            agent.config.nlip_config = nlip_config

            # Initialize NLIP router for the agent
            mcp_executor = getattr(backend, "_execute_mcp_function_with_retry", None)
            agent.config.init_nlip_router(
                tool_manager=tool_manager,
                mcp_executor=mcp_executor,
            )

            # Inject NLIP router into backend
            if hasattr(backend, "set_nlip_router"):
                backend.set_nlip_router(
                    nlip_router=agent.config.nlip_router,
                    enabled=True,
                )

            logger.info(f"[Orchestrator] NLIP routing enabled for agent: {agent_id}")
            nlip_enabled_count += 1

        logger.info(
            f"[Orchestrator] NLIP initialization complete: {nlip_enabled_count} enabled, {nlip_skipped_count} skipped",
        )
