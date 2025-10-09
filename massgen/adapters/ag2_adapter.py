# -*- coding: utf-8 -*-
"""
AG2 (AutoGen) adapter for MassGen.

Supports both single agents and GroupChat configurations.
"""
from typing import Any, AsyncGenerator, Dict, List

from massgen.logger_config import log_backend_activity, logger

from .base import AgentAdapter, StreamChunk
from .utils.ag2_utils import setup_agent_from_config, setup_api_keys


class AG2Adapter(AgentAdapter):
    """
    Adapter for AG2 (AutoGen) framework.

    Supports:
    - Single AG2 agents (ConversableAgent, AssistantAgent)
    - Function/tool calling
    - Code execution with multiple executor types:
      * LocalCommandLineCodeExecutor (local shell)
      * DockerCommandLineCodeExecutor (Docker containers)
      * JupyterCodeExecutor (Jupyter kernels)
      * YepCodeCodeExecutor (YepCode serverless)
    - Async execution with a_generate_reply
    - No human-in-the-loop (autonomous operation)

    Todos:
    - Group chat support with patterns (e.g., AutoPattern, DefaultPattern, etc.)
    - More tool support including MCP
    """

    def __init__(self, **kwargs):
        """
        Initialize AG2 adapter.

        The adapter receives the entire backend configuration from MassGen.
        It should contain EITHER 'agent_config' OR 'group_config' (not both).

        Args:
            **kwargs: Backend configuration containing either:
                - agent_config: Configuration for single AG2 agent
                - group_config: Configuration for AG2 GroupChat
        """
        super().__init__(**kwargs)

        # Set up API keys for AG2 compatibility
        setup_api_keys()

        # Extract agent_config or group_config from kwargs
        self.agent_config = kwargs.get("agent_config")
        self.group_config = kwargs.get("group_config")

        # Validate that we have exactly one of them
        if self.agent_config and self.group_config:
            raise ValueError(
                "Backend configuration should contain EITHER 'agent_config' OR 'group_config', not both.",
            )
        if not self.agent_config and not self.group_config:
            raise ValueError(
                "Backend configuration must contain either 'agent_config' for single agent " "or 'group_config' for GroupChat.",
            )

        # Initialize AG2 components
        self._setup_agents()

    def _setup_agents(self):
        """Set up AG2 agents based on configuration."""
        if self.group_config:
            # GroupChat setup
            self._setup_group_chat()
        else:
            # Single agent setup
            self._setup_single_agent()

    def _setup_single_agent(self):
        """Set up a single AG2 agent."""
        self.agent = setup_agent_from_config(self.agent_config)

        self.is_group_chat = False

    def _setup_group_chat(self):
        """Set up AG2 GroupChat with multiple agents."""
        agents = []

        # Create agents from configuration
        for agent_cfg in self.group_config.get("agents", []):
            agent = setup_agent_from_config(agent_cfg)
            agents.append(agent)

        if not agents:
            raise ValueError("No valid agents configured for group chat")

        # Todo: set up group chat patterns
        self.is_group_chat = True

    async def execute_streaming(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Stream response from AG2 agent(s).

        Since AG2 doesn't support streaming, we simulate it.
        """
        try:
            self._register_tools(tools)
            # Get agent_id for logging
            agent_id = kwargs.get("agent_id", "ag2_agent")

            # Log start
            log_backend_activity(
                "ag2",
                "Starting execute_streaming",
                {"num_messages": len(messages), "num_tools": len(tools) if tools else 0},
                agent_id=agent_id,
            )

            # Run AG2 conversation using async methods
            if not self.is_group_chat:
                result = await self.agent.a_generate_reply(messages)

                # Log received response
                log_backend_activity(
                    "ag2",
                    "Received response from AG2",
                    {"response_type": type(result).__name__},
                    agent_id=agent_id,
                )

                # Extract content and tool_calls from AG2 response
                # Massgen and AG2 use same format for tool calls
                content = result.get("content", "") if isinstance(result, dict) else str(result)
                tool_calls = result.get("tool_calls") if isinstance(result, dict) else None

                # Log extracted data
                log_backend_activity(
                    "ag2",
                    "Extracted response data",
                    {
                        "has_content": bool(content),
                        "content_length": len(content) if content else 0,
                        "has_tool_calls": bool(tool_calls),
                        "tool_count": len(tool_calls) if tool_calls else 0,
                    },
                    agent_id=agent_id,
                )

                # Use base class simulate_streaming method
                async for chunk in self.simulate_streaming(content, tool_calls):
                    yield chunk

            else:
                # TODO: Implement GroupChat logic
                raise NotImplementedError("GroupChat not yet implemented")

        except Exception as e:
            # Import logger if not already imported

            # Log error
            logger.error(f"[AG2Adapter] Error in execute_streaming: {e}", exc_info=True)

            agent_id = kwargs.get("agent_id", "ag2_agent")
            log_backend_activity(
                "ag2",
                "Error during execution",
                {"error": str(e), "error_type": type(e).__name__},
                agent_id=agent_id,
            )

            # Yield error chunk
            yield StreamChunk(type="error", error=f"AG2 execution error: {str(e)}")

    def _register_tools(self, tools: List[Dict[str, Any]]) -> None:
        """
        Register tools with the agent.

        Massgen and AG2 both use openai function format for tools,
        """

        if not tools:
            return

        if not self.is_group_chat:
            for tool in tools:
                self.agent.update_tool_signature(tool_sig=tool, is_remove=False, silent_override=True)

        else:
            # Todo:
            raise NotImplementedError("Tool registration for group chat not yet implemented")
