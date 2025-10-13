# -*- coding: utf-8 -*-
"""
AG2 (AutoGen) adapter for MassGen.

Supports both single agents and GroupChat configurations.
"""
from typing import Any, AsyncGenerator, Dict, List

from autogen import ConversableAgent
from autogen.agentchat import a_run_group_chat
from autogen.agentchat.group.patterns import AutoPattern, RoundRobinPattern

from massgen.logger_config import log_backend_activity, logger

from ..utils import CoordinationStage
from .base import AgentAdapter, StreamChunk
from .utils.ag2_utils import (
    create_llm_config,
    get_group_initial_message,
    get_user_agent_initial_system_message,
    postprocess_group_chat_results,
    setup_agent_from_config,
    setup_api_keys,
)

DEFAULT_MAX_ROUNDS = 20
SUPPORTED_GROUPCHAT_PATTERNS = ["auto", "round_robin"]


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
        """Set up AG2 GroupChat with multiple agents and pattern."""
        # Validate group_config has required fields
        if "pattern" not in self.group_config:
            raise ValueError("group_config must include 'pattern' configuration")

        # Get default llm_config from group_config (required)
        default_llm_config = self.group_config.get("llm_config")
        if not default_llm_config:
            raise ValueError("group_config must include 'llm_config' as default for all agents")

        # Create sub-agents from configuration
        agents = []
        agent_name_map = {}

        for agent_cfg in self.group_config.get("agents", []):
            agent = setup_agent_from_config(agent_cfg, default_llm_config=default_llm_config)
            agents.append(agent)
            agent_name_map[agent.name] = agent

        if not agents:
            raise ValueError("No valid agents configured for group chat")

        # Get pattern configuration
        pattern_config = self.group_config["pattern"]
        pattern_type = pattern_config.get("type")

        if not pattern_type:
            raise ValueError("pattern configuration must include 'type' field")

        if pattern_type not in SUPPORTED_GROUPCHAT_PATTERNS:
            raise NotImplementedError(
                f"Pattern type '{pattern_type}' not supported. Supported types: 'auto', 'round_robin'",
            )

        # Set up user_agent
        self.user_agent = self._setup_user_agent(
            user_agent_config=self.group_config.get("user_agent"),
            default_llm_config=default_llm_config,
        )

        # Set up group_manager_args
        group_manager_args = self._setup_group_manager_args(pattern_config, default_llm_config)

        # Create pattern based on type
        self.pattern = self._create_pattern(pattern_type, pattern_config, agents, agent_name_map, group_manager_args)

        # Store agents and pattern info
        self.agents = agents
        self.group_max_rounds = self.group_config.get("max_rounds", DEFAULT_MAX_ROUNDS)
        self.is_group_chat = True

        logger.info(f"[AG2Adapter] GroupChat setup complete with {len(agents)} agents and {pattern_type} pattern")

    def _setup_user_agent(self, user_agent_config: Any, default_llm_config: Any) -> ConversableAgent:
        """
        Set up user_agent for group chat.

        User agent makes final decisions and calls workflow tools.
        Its name MUST be "User" for termination condition to work.

        Args:
            user_agent_config: Optional user agent configuration from YAML
            default_llm_config: Default llm_config to use if not specified

        Returns:
            ConversableAgent with name "User"
        """
        if user_agent_config:
            # User provided custom user_agent configuration
            user_agent = setup_agent_from_config(user_agent_config, default_llm_config=default_llm_config)

            # Validate name is "User"
            if user_agent.name != "User":
                raise ValueError(
                    f"user_agent name must be 'User', got '{user_agent.name}'. " "This is required for group chat termination condition.",
                )
            return user_agent
        else:
            # Create default user_agent
            return ConversableAgent(
                name="User",
                description="Oversees the process. Should NEVER be selected to speak.",
                human_input_mode="NEVER",
                code_execution_config=False,
                llm_config=create_llm_config(default_llm_config),
            )

    def _setup_group_manager_args(self, pattern_config: Dict[str, Any], default_llm_config: Any) -> Dict[str, Any]:
        """
        Set up group_manager_args for pattern.

        Args:
            pattern_config: Pattern configuration from YAML
            default_llm_config: Default llm_config to use if not specified

        Returns:
            Dict with llm_config and termination condition
        """
        group_manager_args = pattern_config.get("group_manager_args", {})

        # Ensure group_manager_args has llm_config (use default if not provided)
        if "llm_config" not in group_manager_args:
            group_manager_args["llm_config"] = create_llm_config(default_llm_config)
        else:
            group_manager_args["llm_config"] = create_llm_config(group_manager_args["llm_config"])

        # Add termination condition: terminate when User generates tool_calls
        group_manager_args["is_termination_msg"] = lambda msg: (msg.get("name") == self.user_agent.name and "tool_calls" in msg)

        return group_manager_args

    def _create_pattern(
        self,
        pattern_type: str,
        pattern_config: Dict[str, Any],
        agents: List[ConversableAgent],
        agent_name_map: Dict[str, ConversableAgent],
        group_manager_args: Dict[str, Any],
    ) -> Any:
        """
        Create AG2 pattern based on type.

        Args:
            pattern_type: Type of pattern ("auto" or "round_robin")
            pattern_config: Pattern configuration from YAML
            agents: List of expert agents
            agent_name_map: Mapping from agent names to agent objects
            group_manager_args: Group manager configuration

        Returns:
            Pattern instance (AutoPattern or RoundRobinPattern)
        """
        # Get initial agent
        initial_agent_name = pattern_config.get("initial_agent")
        if not initial_agent_name:
            raise ValueError("initial_agent must be specified in pattern configuration")

        if initial_agent_name not in agent_name_map:
            raise ValueError(f"initial_agent '{initial_agent_name}' not found in agents list")

        initial_agent = agent_name_map[initial_agent_name]

        # Create pattern
        if pattern_type == "auto":
            return AutoPattern(
                initial_agent=initial_agent,
                agents=agents,
                user_agent=self.user_agent,
                group_manager_args=group_manager_args,
            )
        elif pattern_type == "round_robin":
            return RoundRobinPattern(
                initial_agent=initial_agent,
                agents=agents,
                user_agent=self.user_agent,
                group_manager_args=group_manager_args,
            )
        else:
            raise NotImplementedError(f"Pattern type '{pattern_type}' not supported")

    async def _execute_single_agent(self, messages: List[Dict[str, Any]], agent: ConversableAgent) -> AsyncGenerator[StreamChunk, None]:
        """
        Execute single AG2 agent.

        Args:
            messages: Conversation messages
            agent_id: Agent ID for logging

        Returns:
            Tuple of (content, tool_calls)
        """
        result = await agent.a_generate_reply(messages)

        # # Log received response
        # log_backend_activity(
        #     "ag2",
        #     "Received response from AG2",
        #     {"response_type": type(result).__name__},
        #     agent_id=self.agent_id,
        # )

        # Extract content and tool_calls from AG2 response
        # MassGen and AG2 use same format for tool calls
        content = result.get("content", "") if isinstance(result, dict) else str(result)
        tool_calls = result.get("tool_calls") if isinstance(result, dict) else None

        # Log extracted data
        log_backend_activity(
            "ag2",
            "Received response data from AG2",
            {
                "has_content": bool(content),
                "content_length": len(content) if content else 0,
                "has_tool_calls": bool(tool_calls),
                "tool_count": len(tool_calls) if tool_calls else 0,
            },
            agent_id=self.agent_id,
        )

        # Use base class simulate_streaming method
        async for chunk in self.simulate_streaming(content, tool_calls):
            yield chunk

    async def _execute_group_chat(self, messages: List[Dict[str, Any]]) -> AsyncGenerator[str, None]:
        """
        Execute AG2 group chat with pattern.

        Args:
            messages: Conversation messages
            agent_id: Agent ID for logging

        Returns:
            Tuple of (content, tool_calls)
        """
        # Add name field to all messages so the conversation will start correctly from user agent
        for message in messages:
            message["name"] = "User"

        # The pattern will coordinate agents until user_agent generates tool_calls
        response = await a_run_group_chat(
            pattern=self.pattern,
            messages=messages,
            max_rounds=self.group_max_rounds,
        )

        last_group_chat_event_msgs = []  # Store messages from the last event

        def process_and_log_event(*args, **kwargs) -> None:
            """Process and log AG2 event, returning string representation."""
            line = " ".join(str(arg) for arg in args)
            last_group_chat_event_msgs.append(line)

        async for event in response.events:
            last_group_chat_event_msgs.clear()
            event.print(f=process_and_log_event)
            formatted_message = "\n".join(last_group_chat_event_msgs)

            log_backend_activity(
                "ag2",
                "Received response from AG2",
                {"message": formatted_message},
                agent_id=self.agent_id,
            )
            yield formatted_message

    async def _execute_group_chat_with_user_agent(self, messages: List[Dict[str, Any]]) -> AsyncGenerator[StreamChunk, None]:
        messages_to_execute = []
        if self.coordination_stage == CoordinationStage.INITIAL_ANSWER:
            messages[0] = get_group_initial_message()
            async for event_msg in self._execute_group_chat(messages):
                yield StreamChunk(type="content", content=event_msg)

            self._register_workflow_tools_to_user_agent()
            self.user_agent.update_system_message(get_user_agent_initial_system_message())

            results = list(self.user_agent._oai_messages.values())[0]

            messages_to_execute = postprocess_group_chat_results(results)

        elif self.coordination_stage == CoordinationStage.ENFORCEMENT:
            messages_to_execute = messages

        elif self.coordination_stage == CoordinationStage.PRESENTATION:
            self.user_agent.update_system_message(messages[0]["content"])
            messages_to_execute = [messages[1]]

        async for chunk in self._execute_single_agent(messages=messages_to_execute, agent=self.user_agent):
            yield chunk

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
            agent_id = kwargs.get("agent_id")
            if agent_id:
                self.agent_id = agent_id

            # Log start
            log_backend_activity(
                "ag2",
                "Starting execute_streaming",
                {"num_messages": len(messages), "num_tools": len(tools) if tools else 0},
                agent_id=agent_id,
            )

            # Execute agent or group chat
            if self.is_group_chat:
                async for chunk in self._execute_group_chat_with_user_agent(messages):
                    yield chunk
            else:
                async for chunk in self._execute_single_agent(messages, self.user_agent):
                    yield chunk

        except Exception as e:
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

    # =============================================================================
    # TOOL REGISTRATION METHODS
    # =============================================================================

    def _register_tools(self, tools: List[Dict[str, Any]]) -> None:
        """
        Register tools with the agent(s).

        For single agent: Register all tools to the agent.

        For group chat:
        - Workflow tools (new_answer, vote) → register ONLY to user_agent
        - Other tools (MCP, etc.) → register to ALL expert agents (not user_agent)

        MassGen and AG2 both use OpenAI function format for tools.
        """
        if not tools:
            return

        if self.is_group_chat:
            self._register_tools_for_group_chat(tools)
        else:
            self._register_tools_for_single_agent(tools)

    def _register_tools_for_single_agent(self, tools: List[Dict[str, Any]]) -> None:
        """Register all tools to single agent."""
        for tool in tools:
            self.agent.update_tool_signature(tool_sig=tool, is_remove=False, silent_override=True)

    def _register_tools_for_group_chat(self, tools: List[Dict[str, Any]]) -> None:
        """Register tools to group chat agents based on type."""
        workflow_tools, other_tools = self._separate_workflow_and_other_tools(tools)

        # Register other tools to ALL expert agents (not user_agent)
        for agent in self.agents:
            for tool in other_tools:
                agent.update_tool_signature(tool_sig=tool, is_remove=False)
            if other_tools:
                logger.info(f"[AG2Adapter] Registered {len(other_tools)} non-workflow tools to agent '{agent.name}'")

    def _separate_workflow_and_other_tools(self, tools: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Separate workflow tools from other tools.

        Args:
            tools: List of all tools

        Returns:
            Tuple of (workflow_tools, other_tools)
        """
        workflow_tools = []
        other_tools = []

        for tool in tools:
            tool_name = self._get_tool_name(tool)
            if tool_name in ["new_answer", "vote"]:
                workflow_tools.append(tool)
            else:
                other_tools.append(tool)

        if "new_answer" in workflow_tools and "vote" not in workflow_tools:
            raise ValueError("Both 'new_answer' and 'vote' workflow tools must be provided.")
        self.workflow_tools = workflow_tools

        return workflow_tools, other_tools

    def _register_workflow_tools_to_user_agent(self) -> None:
        """Register workflow tools to user_agent."""
        for tool in self.workflow_tools:
            self.user_agent.update_tool_signature(tool_sig=tool, is_remove=False)

        logger.info(f"[AG2Adapter] Registered {len(self.workflow_tools)} workflow tools to user_agent '{self.user_agent.name}'")
