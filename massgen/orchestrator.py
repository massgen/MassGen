# -*- coding: utf-8 -*-
"""
MassGen Orchestrator Agent - Chat interface that manages sub-agents internally.

The orchestrator presents a unified chat interface to users while coordinating
multiple sub-agents using the proven binary decision framework behind the scenes.

TODOs:

- Move CLI's coordinate_with_context logic to orchestrator and simplify CLI to just use orchestrator
- Implement orchestrator system message functionality to customize coordination behavior:

  * Custom voting strategies (consensus, expertise-weighted, domain-specific)
  * Message construction templates for sub-agent instructions
  * Conflict resolution approaches (evidence-based, democratic, expert-priority)
  * Workflow preferences (thorough vs fast, iterative vs single-pass)
  * Domain-specific coordination (research teams, technical reviews, creative brainstorming)
  * Dynamic agent selection based on task requirements and orchestrator instructions
"""

import asyncio
import json
import os
import shutil
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncGenerator, Dict, List, Optional

from .agent_config import AgentConfig
from .backend.base import StreamChunk
from .chat_agent import ChatAgent
from .coordination_tracker import CoordinationTracker

if TYPE_CHECKING:
    from .dspy_paraphraser import QuestionParaphraser
from .logger_config import get_log_session_dir  # Import to get log directory
from .logger_config import logger  # Import logger directly for INFO logging
from .logger_config import (
    log_coordination_step,
    log_orchestrator_activity,
    log_orchestrator_agent_message,
    log_stream_chunk,
    log_tool_call,
    set_log_attempt,
)
from .memory import ConversationMemory, PersistentMemoryBase
from .message_templates import MessageTemplates
from .stream_chunk import ChunkType
from .tool import get_post_evaluation_tools, get_workflow_tools
from .utils import ActionType, AgentStatus, CoordinationStage


@dataclass
class AgentState:
    """Runtime state for an agent during coordination.

    Attributes:
        answer: The agent's current answer/summary, if any
        has_voted: Whether the agent has voted in the current round
        votes: Dictionary storing vote data for this agent
        restart_pending: Whether the agent should gracefully restart due to new answers
        is_killed: Whether this agent has been killed due to timeout/limits
        timeout_reason: Reason for timeout (if applicable)
    """

    answer: Optional[str] = None
    has_voted: bool = False
    votes: Dict[str, Any] = field(default_factory=dict)
    restart_pending: bool = False
    is_killed: bool = False
    timeout_reason: Optional[str] = None
    last_context: Optional[Dict[str, Any]] = None  # Store the context sent to this agent
    paraphrase: Optional[str] = None


class Orchestrator(ChatAgent):
    """
    Orchestrator Agent - Unified chat interface with sub-agent coordination.

    The orchestrator acts as a single agent from the user's perspective, but internally
    coordinates multiple sub-agents using the proven binary decision framework.

    Key Features:
    - Unified chat interface (same as any individual agent)
    - Automatic sub-agent coordination and conflict resolution
    - Transparent MassGen workflow execution
    - Real-time streaming with proper source attribution
    - Graceful restart mechanism for dynamic case transitions
    - Session management

    TODO - Missing Configuration Options:
    - Option to include/exclude voting details in user messages
    - Configurable timeout settings for agent responses
    - Configurable retry limits and backoff strategies
    - Custom voting strategies beyond simple majority
    - Configurable presentation formats for final answers
    - Advanced coordination workflows (hierarchical, weighted voting, etc.)

    TODO (v0.0.14 Context Sharing Enhancement - See docs/dev_notes/v0.0.14-context.md):
    - Add permission validation logic for agent workspace access
    - Implement validate_agent_access() method to check if agent has required permission for resource
    - Replace current prompt-based access control with explicit system-level enforcement
    - Add PermissionManager integration for managing agent access rules
    - Implement audit logging for all access attempts to workspace resources
    - Support dynamic permission negotiation during runtime
    - Add configurable policy framework for permission management
    - Integrate with workspace snapshot mechanism for controlled context sharing

    Restart Behavior:
    When an agent provides new_answer, all agents gracefully restart to ensure
    consistent coordination state. This allows all agents to transition to Case 2
    evaluation with the new answers available.
    """

    def __init__(
        self,
        agents: Dict[str, ChatAgent],
        orchestrator_id: str = "orchestrator",
        session_id: Optional[str] = None,
        config: Optional[AgentConfig] = None,
        dspy_paraphraser: Optional["QuestionParaphraser"] = None,
        snapshot_storage: Optional[str] = None,
        agent_temporary_workspace: Optional[str] = None,
        previous_turns: Optional[List[Dict[str, Any]]] = None,
        winning_agents_history: Optional[List[Dict[str, Any]]] = None,
        shared_conversation_memory: Optional[ConversationMemory] = None,
        shared_persistent_memory: Optional[PersistentMemoryBase] = None,
        enable_nlip: bool = False,
        nlip_config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize MassGen orchestrator.

        Args:
            agents: Dictionary of {agent_id: ChatAgent} - can be individual agents or other orchestrators
            orchestrator_id: Unique identifier for this orchestrator (default: "orchestrator")
            session_id: Optional session identifier
            config: Optional AgentConfig for customizing orchestrator behavior
            dspy_paraphraser: Optional DSPy paraphraser for multi-agent question diversity
            snapshot_storage: Optional path to store agent workspace snapshots
            agent_temporary_workspace: Optional path for agent temporary workspaces
            previous_turns: List of previous turn metadata for multi-turn conversations (loaded by CLI)
            winning_agents_history: List of previous winning agents for memory sharing
                                   Format: [{"agent_id": "agent_b", "turn": 1}, ...]
                                   Loaded from session storage to persist across orchestrator recreations
            shared_conversation_memory: Optional shared conversation memory for all agents
            shared_persistent_memory: Optional shared persistent memory for all agents
            enable_nlip: Enable NLIP (Natural Language Interaction Protocol) support
            nlip_config: Optional NLIP configuration
        """
        super().__init__(session_id, shared_conversation_memory, shared_persistent_memory)
        self.orchestrator_id = orchestrator_id
        self.agents = agents
        self.agent_states = {aid: AgentState() for aid in agents.keys()}
        self.config = config or AgentConfig.create_openai_config()
        self.dspy_paraphraser = dspy_paraphraser

        # Shared memory for all agents
        self.shared_conversation_memory = shared_conversation_memory
        self.shared_persistent_memory = shared_persistent_memory

        # Get message templates from config
        self.message_templates = self.config.message_templates or MessageTemplates(
            voting_sensitivity=self.config.voting_sensitivity,
            answer_novelty_requirement=self.config.answer_novelty_requirement,
        )
        # Create workflow tools for agents (vote and new_answer) using new toolkit system
        self.workflow_tools = get_workflow_tools(
            valid_agent_ids=list(agents.keys()),
            template_overrides=getattr(self.message_templates, "_template_overrides", {}),
            api_format="chat_completions",  # Default format, will be overridden per backend
        )

        # MassGen-specific state
        self.current_task: Optional[str] = None
        self.workflow_phase: str = "idle"  # idle, coordinating, presenting

        # Internal coordination state
        self._coordination_messages: List[Dict[str, str]] = []
        self._selected_agent: Optional[str] = None
        self._final_presentation_content: Optional[str] = None

        # Track winning agents by turn for memory sharing
        # Format: [{"agent_id": "agent_b", "turn": 1}, {"agent_id": "agent_a", "turn": 2}]
        # Restore from session storage if provided (for multi-turn persistence)
        self._winning_agents_history: List[Dict[str, Any]] = winning_agents_history or []
        if self._winning_agents_history:
            logger.info(f"📚 Restored {len(self._winning_agents_history)} winning agent(s) from session: {self._winning_agents_history}")
        self._current_turn: int = 0

        # Timeout and resource tracking
        self.total_tokens: int = 0
        self.coordination_start_time: float = 0
        self.is_orchestrator_timeout: bool = False
        self.timeout_reason: Optional[str] = None

        # Restart feature state tracking
        self.current_attempt: int = 0
        max_restarts = self.config.coordination_config.max_orchestration_restarts
        self.max_attempts: int = 1 + max_restarts
        self.restart_pending: bool = False
        self.restart_reason: Optional[str] = None
        self.restart_instructions: Optional[str] = None
        self.previous_attempt_answer: Optional[str] = None  # Store previous winner's answer for restart context

        # Coordination state tracking for cleanup
        self._active_streams: Dict = {}
        self._active_tasks: Dict = {}

        # Context sharing for agents with filesystem support
        self._snapshot_storage: Optional[str] = snapshot_storage
        self._agent_temporary_workspace: Optional[str] = agent_temporary_workspace

        # DSPy paraphrase tracking
        self._agent_paraphrases: Dict[str, str] = {}
        self._paraphrase_generation_errors: int = 0

        # Multi-turn session tracking (loaded by CLI, not managed by orchestrator)
        self._previous_turns: List[Dict[str, Any]] = previous_turns or []

        # Coordination tracking - always enabled for analysis/debugging
        self.coordination_tracker = CoordinationTracker()
        self.coordination_tracker.initialize_session(list(agents.keys()))

        # Create snapshot storage and workspace directories if specified
        if snapshot_storage:
            self._snapshot_storage = snapshot_storage
            snapshot_path = Path(self._snapshot_storage)
            # Clean existing directory if it exists and has contents
            if snapshot_path.exists() and any(snapshot_path.iterdir()):
                shutil.rmtree(snapshot_path)
            snapshot_path.mkdir(parents=True, exist_ok=True)

        # Configure orchestration paths for each agent with filesystem support
        for agent_id, agent in self.agents.items():
            if agent.backend.filesystem_manager:
                agent.backend.filesystem_manager.setup_orchestration_paths(
                    agent_id=agent_id,
                    snapshot_storage=self._snapshot_storage,
                    agent_temporary_workspace=self._agent_temporary_workspace,
                )
                # Update MCP config with agent_id for Docker mode (must be after setup_orchestration_paths)
                agent.backend.filesystem_manager.update_backend_mcp_config(agent.backend.config)

        # Inject planning tools if enabled
        logger.info(f"[Orchestrator] Checking planning config: coordination_config exists={hasattr(self.config, 'coordination_config')}")
        if hasattr(self.config, "coordination_config") and hasattr(self.config.coordination_config, "enable_agent_task_planning"):
            logger.info(f"[Orchestrator] enable_agent_task_planning={self.config.coordination_config.enable_agent_task_planning}")
            if self.config.coordination_config.enable_agent_task_planning:
                logger.info(f"[Orchestrator] Injecting planning tools for {len(self.agents)} agents")
                self._inject_planning_tools_for_all_agents()
                logger.info("[Orchestrator] Planning tools injection complete")
        else:
            logger.info("[Orchestrator] Planning config not found or disabled")

        # NLIP Configuration
        self.enable_nlip = enable_nlip
        self.nlip_config = nlip_config or {}

        # Initialize NLIP routers for agents if enabled
        if self.enable_nlip:
            self._init_nlip_routing()

    def _init_nlip_routing(self) -> None:
        """Initialize NLIP routing for all agents."""
        logger.info(f"[Orchestrator] Initializing NLIP routing for {len(self.agents)} agents")

        for agent_id, agent in self.agents.items():
            # Check if agent is a ConfigurableAgent with NLIP config
            if hasattr(agent, 'config'):
                agent.config.enable_nlip = True
                agent.config.nlip_config = self.nlip_config

                # Initialize NLIP router for the agent
                tool_manager = getattr(agent, '_tool_manager', None)
                agent.config.init_nlip_router(tool_manager=tool_manager)

                logger.info(f"[Orchestrator] NLIP routing enabled for agent: {agent_id}")

    async def _prepare_paraphrases_for_agents(self, question: str) -> None:
        """Generate and assign DSPy paraphrases for the current question."""

        # Reset paraphrases before regenerating
        self._agent_paraphrases = {}
        for state in self.agent_states.values():
            state.paraphrase = None

        if not self.dspy_paraphraser:
            return

        if not question:
            return

        try:
            variants = await asyncio.to_thread(
                self.dspy_paraphraser.generate_variants,
                question,
            )
        except Exception as exc:
            self._paraphrase_generation_errors += 1
            logger.warning(f"Failed to generate DSPy paraphrases: {exc}")
            return

        if not variants:
            logger.warning("DSPy paraphraser returned no variants; proceeding with original question for all agents.")
            return

        agent_ids = list(self.agents.keys())
        if not agent_ids:
            return

        for idx, agent_id in enumerate(agent_ids):
            paraphrase = variants[idx % len(variants)]
            self._agent_paraphrases[agent_id] = paraphrase
            self.agent_states[agent_id].paraphrase = paraphrase

        # Log at INFO level so users know paraphrasing is active
        logger.info(f" DSPy paraphrasing enabled: {len(variants)} variant(s) generated and assigned to {len(agent_ids)} agent(s)")

        log_coordination_step(
            "DSPy paraphrases prepared",
            {
                "variants": len(variants),
                "assigned_agents": self._agent_paraphrases,
            },
        )

    def get_paraphrase_status(self) -> Dict[str, Any]:
        """Return current DSPy paraphrase assignments and metrics for observability."""

        status = {
            "paraphrases": self._agent_paraphrases.copy(),
            "generation_errors": self._paraphrase_generation_errors,
            "metrics": None,
        }

        if self.dspy_paraphraser:
            try:
                status["metrics"] = self.dspy_paraphraser.get_metrics()
            except Exception as exc:  # pragma: no cover - defensive guard
                logger.debug(f"Unable to fetch DSPy paraphraser metrics: {exc}")

        return status

    def _inject_planning_tools_for_all_agents(self) -> None:
        """
        Inject planning MCP tools into all agents.

        This method adds the planning MCP server to each agent's backend
        configuration, enabling them to create and manage task plans.
        """
        for agent_id, agent in self.agents.items():
            self._inject_planning_tools_for_agent(agent_id, agent)

    def _inject_planning_tools_for_agent(self, agent_id: str, agent: Any) -> None:
        """
        Inject planning MCP tools into a specific agent.

        Args:
            agent_id: ID of the agent
            agent: Agent instance
        """
        logger.info(f"[Orchestrator] Injecting planning tools for agent: {agent_id}")

        # Create planning MCP config
        planning_mcp_config = self._create_planning_mcp_config(agent_id)
        logger.info(f"[Orchestrator] Created planning MCP config: {planning_mcp_config['name']}")

        # Get existing mcp_servers configuration
        mcp_servers = agent.backend.config.get("mcp_servers", [])
        logger.info(f"[Orchestrator] Existing MCP servers for {agent_id}: {type(mcp_servers)} with {len(mcp_servers) if isinstance(mcp_servers, (list, dict)) else 0} entries")

        # Handle both list format and dict format (Claude Code)
        if isinstance(mcp_servers, dict):
            # Claude Code dict format
            logger.info("[Orchestrator] Using dict format for MCP servers")
            mcp_servers[f"planning_{agent_id}"] = planning_mcp_config
        else:
            # Standard list format
            logger.info("[Orchestrator] Using list format for MCP servers")
            if not isinstance(mcp_servers, list):
                mcp_servers = []
            mcp_servers.append(planning_mcp_config)

        # Update backend config
        agent.backend.config["mcp_servers"] = mcp_servers
        logger.info(f"[Orchestrator] Updated MCP servers for {agent_id}, now has {len(mcp_servers) if isinstance(mcp_servers, (list, dict)) else 0} servers")

    def _create_planning_mcp_config(self, agent_id: str) -> Dict[str, Any]:
        """
        Create MCP server configuration for planning tools.

        Args:
            agent_id: ID of the agent

        Returns:
            MCP server configuration dictionary
        """
        from pathlib import Path as PathlibPath

        import massgen.mcp_tools.planning._planning_mcp_server as planning_module

        script_path = PathlibPath(planning_module.__file__).resolve()

        config = {
            "name": f"planning_{agent_id}",
            "type": "stdio",
            "command": "fastmcp",
            "args": [
                "run",
                f"{script_path}:create_server",
                "--",
                "--agent-id",
                agent_id,
                "--orchestrator-id",
                self.orchestrator_id,
            ],
            "env": {
                "FASTMCP_SHOW_CLI_BANNER": "false",
            },
        }

        return config

    @staticmethod
    def _get_chunk_type_value(chunk) -> str:
        """
        Extract chunk type as string, handling both legacy and typed chunks.

        Args:
            chunk: StreamChunk, TextStreamChunk, or MultimodalStreamChunk

        Returns:
            String representation of chunk type (e.g., "content", "tool_calls")
        """
        chunk_type = chunk.type

        if isinstance(chunk_type, ChunkType):
            return chunk_type.value

        return str(chunk_type)

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]] = None,
        reset_chat: bool = False,
        clear_history: bool = False,
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Main chat interface - handles user messages and coordinates sub-agents.

        Args:
            messages: List of conversation messages
            tools: Ignored by orchestrator (uses internal workflow tools)
            reset_chat: If True, reset conversation and start fresh
            clear_history: If True, clear history before processing

        Yields:
            StreamChunk: Streaming response chunks
        """
        _ = tools  # Unused parameter

        # Handle conversation management
        if clear_history:
            self.conversation_history.clear()
        if reset_chat:
            self.reset()

        # Process all messages to build conversation context
        conversation_context = self._build_conversation_context(messages)
        user_message = conversation_context.get("current_message")

        if not user_message:
            log_stream_chunk("orchestrator", "error", "No user message found in conversation")
            yield StreamChunk(type="error", error="No user message found in conversation")
            return

        # Add user message to history
        self.add_to_history("user", user_message)

        # Determine what to do based on current state and conversation context
        if self.workflow_phase == "idle":
            # New task - start MassGen coordination with full context
            self.current_task = user_message
            await self._prepare_paraphrases_for_agents(self.current_task)
            # Reinitialize session with user prompt now that we have it
            self.coordination_tracker.initialize_session(list(self.agents.keys()), self.current_task)
            self.workflow_phase = "coordinating"

            # Reset restart_pending flag at start of coordination (will be set again if restart needed)
            self.restart_pending = False

            # Clear agent workspaces for new turn (if this is a multi-turn conversation with history)
            if conversation_context and conversation_context.get("conversation_history"):
                self._clear_agent_workspaces()

            # Check if planning mode is enabled in config
            planning_mode_config_exists = (
                self.config.coordination_config and self.config.coordination_config.enable_planning_mode if self.config and hasattr(self.config, "coordination_config") else False
            )

            if planning_mode_config_exists:
                # Analyze question for irreversibility and set planning mode accordingly
                # This happens silently - users don't see this analysis
                analysis_result = await self._analyze_question_irreversibility(user_message, conversation_context)
                has_irreversible = analysis_result["has_irreversible"]
                blocked_tools = analysis_result["blocked_tools"]

                # Set planning mode and blocked tools for all agents based on analysis
                for agent_id, agent in self.agents.items():
                    if hasattr(agent.backend, "set_planning_mode"):
                        agent.backend.set_planning_mode(has_irreversible)
                        if hasattr(agent.backend, "set_planning_mode_blocked_tools"):
                            agent.backend.set_planning_mode_blocked_tools(blocked_tools)
                        log_orchestrator_activity(
                            self.orchestrator_id,
                            f"Set planning mode for {agent_id}",
                            {
                                "planning_mode_enabled": has_irreversible,
                                "blocked_tools_count": len(blocked_tools),
                                "reason": "irreversibility analysis",
                            },
                        )

            async for chunk in self._coordinate_agents_with_timeout(conversation_context):
                yield chunk

        elif self.workflow_phase == "presenting":
            # Handle follow-up question with full conversation context
            async for chunk in self._handle_followup(user_message, conversation_context):
                yield chunk
        else:
            # Already coordinating - provide status update
            log_stream_chunk("orchestrator", "content", "🔄 Coordinating agents, please wait...")
            yield StreamChunk(type="content", content="🔄 Coordinating agents, please wait...")
            # Note: In production, you might want to queue follow-up questions

    async def chat_simple(self, user_message: str) -> AsyncGenerator[StreamChunk, None]:
        """
        Backwards compatible simple chat interface.

        Args:
            user_message: Simple string message from user

        Yields:
            StreamChunk: Streaming response chunks
        """
        messages = [{"role": "user", "content": user_message}]
        async for chunk in self.chat(messages):
            yield chunk

    def _build_conversation_context(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Build conversation context from message list."""
        conversation_history = []
        current_message = None

        # Process messages to extract conversation history and current message
        for message in messages:
            role = message.get("role")
            content = message.get("content", "")

            if role == "user":
                current_message = content
                # Add to history (excluding the current message)
                if len(conversation_history) > 0 or len(messages) > 1:
                    conversation_history.append(message.copy())
            elif role == "assistant":
                conversation_history.append(message.copy())
            elif role == "system":
                # System messages are typically not part of conversation history
                pass

        # Remove the last user message from history since that's the current message
        if conversation_history and conversation_history[-1].get("role") == "user":
            conversation_history.pop()

        return {
            "current_message": current_message,
            "conversation_history": conversation_history,
            "full_messages": messages,
        }

    async def _inject_shared_memory_context(
        self,
        messages: List[Dict[str, Any]],
        agent_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Inject shared memory context into agent messages.

        This allows all agents to see shared memories including what other agents
        have stored in the shared memory.

        Args:
            messages: Original messages to send to agent
            agent_id: ID of the agent receiving the messages

        Returns:
            Messages with shared memory context injected
        """
        if not self.shared_conversation_memory and not self.shared_persistent_memory:
            # No shared memory configured, return original messages
            return messages

        memory_context_parts = []

        # Get conversation memory content
        if self.shared_conversation_memory:
            try:
                conv_messages = await self.shared_conversation_memory.get_messages()
                if conv_messages:
                    memory_context_parts.append("=== SHARED CONVERSATION MEMORY ===")
                    for msg in conv_messages[-10:]:  # Last 10 messages
                        role = msg.get("role", "unknown")
                        content = msg.get("content", "")
                        agent_source = msg.get("agent_id", "unknown")
                        memory_context_parts.append(f"[{agent_source}] {role}: {content}")
            except Exception as e:
                logger.warning(f"Failed to retrieve shared conversation memory: {e}")

        # Get persistent memory content
        if self.shared_persistent_memory:
            try:
                # Extract user message for retrieval
                user_messages = [msg for msg in messages if msg.get("role") == "user"]
                if user_messages:
                    retrieved = await self.shared_persistent_memory.retrieve(user_messages)
                    if retrieved:
                        memory_context_parts.append("\n=== SHARED PERSISTENT MEMORY ===")
                        memory_context_parts.append(retrieved)
            except NotImplementedError:
                # Memory backend doesn't support retrieve
                pass
            except Exception as e:
                logger.warning(f"Failed to retrieve shared persistent memory: {e}")

        # Inject memory context if we have any
        if memory_context_parts:
            memory_message = {
                "role": "system",
                "content": ("You have access to shared memory that all agents can see and contribute to.\n" + "\n".join(memory_context_parts)),
            }

            # Insert after existing system messages but before user messages
            system_count = sum(1 for msg in messages if msg.get("role") == "system")
            modified_messages = messages.copy()
            modified_messages.insert(system_count, memory_message)
            return modified_messages

        return messages

    async def _record_to_shared_memory(
        self,
        agent_id: str,
        content: str,
        role: str = "assistant",
    ) -> None:
        """
        Record agent's contribution to shared memory.

        Args:
            agent_id: ID of the agent contributing
            content: Content to record
            role: Role of the message (default: "assistant")
        """
        message = {
            "role": role,
            "content": content,
            "agent_id": agent_id,
            "timestamp": time.time(),
        }

        # Add to conversation memory
        if self.shared_conversation_memory:
            try:
                await self.shared_conversation_memory.add(message)
            except Exception as e:
                logger.warning(f"Failed to add to shared conversation memory: {e}")

        # Record to persistent memory
        if self.shared_persistent_memory:
            try:
                await self.shared_persistent_memory.record([message])
            except NotImplementedError:
                # Memory backend doesn't support record
                pass
            except Exception as e:
                logger.warning(f"Failed to record to shared persistent memory: {e}")

    def save_coordination_logs(self):
        """Public method to save coordination logs after final presentation is complete."""
        # End the coordination session
        self.coordination_tracker._end_session()

        # Save coordination logs using the coordination tracker
        log_session_dir = get_log_session_dir()
        if log_session_dir:
            self.coordination_tracker.save_coordination_logs(log_session_dir)

    def _format_planning_mode_ui(
        self,
        has_irreversible: bool,
        blocked_tools: set,
        has_isolated_workspaces: bool,
        user_question: str,
    ) -> str:
        """
        Format a nice UI box for planning mode status.

        Args:
            has_irreversible: Whether irreversible operations were detected
            blocked_tools: Set of specific blocked tool names
            has_isolated_workspaces: Whether agents have isolated workspaces
            user_question: The user's question for context

        Returns:
            Formatted string with nice box UI
        """
        if not has_irreversible:
            # Planning mode disabled - brief message
            box = "\n╭─ Coordination Mode ────────────────────────────────────────╮\n"
            box += "│ ✅ Planning Mode: DISABLED                                │\n"
            box += "│                                                            │\n"
            box += "│ All tools available during coordination.                  │\n"
            box += "│ No irreversible operations detected.                      │\n"
            box += "╰────────────────────────────────────────────────────────────╯\n"
            return box

        # Planning mode enabled
        box = "\n╭─ Coordination Mode ────────────────────────────────────────╮\n"
        box += "│ 🧠 Planning Mode: ENABLED                                  │\n"
        box += "│                                                            │\n"

        if has_isolated_workspaces:
            box += "│ 🔒 Workspace: Isolated (filesystem ops allowed)           │\n"
            box += "│                                                            │\n"

        # Description
        box += "│ Agents will plan and coordinate without executing         │\n"
        box += "│ irreversible actions. The winning agent will implement    │\n"
        box += "│ the plan during final presentation.                       │\n"
        box += "│                                                            │\n"

        # Blocked tools section
        if blocked_tools:
            box += "│ 🚫 Blocked Tools:                                          │\n"
            # Format tools into nice columns
            sorted_tools = sorted(blocked_tools)
            for i, tool in enumerate(sorted_tools[:5], 1):  # Show max 5 tools
                # Shorten tool name if too long
                display_tool = tool if len(tool) <= 50 else tool[:47] + "..."
                box += f"│   {i}. {display_tool:<54} │\n"

            if len(sorted_tools) > 5:
                remaining = len(sorted_tools) - 5
                box += f"│   ... and {remaining} more tool(s)                              │\n"
            box += "│                                                            │\n"
        else:
            box += "│ 🚫 Blocking: ALL MCP tools                                 │\n"
            box += "│                                                            │\n"

        # Add brief analysis summary
        box += "│ 📊 Analysis:                                               │\n"
        # Create a brief summary from the question
        summary = user_question[:50] + "..." if len(user_question) > 50 else user_question
        # Wrap text to fit in box
        words = summary.split()
        line = "│   "
        for word in words:
            if len(line) + len(word) + 1 > 60:
                box += line.ljust(61) + "│\n"
                line = "│   " + word + " "
            else:
                line += word + " "
        if len(line) > 4:  # If there's content
            box += line.ljust(61) + "│\n"

        box += "╰────────────────────────────────────────────────────────────╯\n"
        return box

    async def _analyze_question_irreversibility(self, user_question: str, conversation_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze if the user's question involves MCP tools with irreversible outcomes.

        This method randomly selects an available agent to analyze whether executing
        the user's question would involve MCP tool operations with irreversible outcomes
        (e.g., sending Discord messages, posting tweets, deleting files) vs reversible
        read operations (e.g., reading Discord messages, searching tweets, listing files).

        Args:
            user_question: The user's question/request
            conversation_context: Full conversation context including history

        Returns:
            Dict with:
                - has_irreversible (bool): True if irreversible operations detected
                - blocked_tools (set): Set of MCP tool names to block (e.g., {'mcp__discord__discord_send'})
                                      Empty set means block ALL MCP tools
        """
        import random

        print("=" * 80, flush=True)
        print("🔍 [INTELLIGENT PLANNING MODE] Analyzing question for irreversibility...", flush=True)
        print(f"📝 Question: {user_question[:100]}{'...' if len(user_question) > 100 else ''}", flush=True)
        print("=" * 80, flush=True)

        # Select a random agent for analysis
        available_agents = [aid for aid, agent in self.agents.items() if agent.backend is not None]
        if not available_agents:
            # No agents available, default to safe mode (planning enabled, block ALL)
            log_orchestrator_activity(
                self.orchestrator_id,
                "No agents available for irreversibility analysis, defaulting to planning mode",
                {},
            )
            return {"has_irreversible": True, "blocked_tools": set()}

        analyzer_agent_id = random.choice(available_agents)
        analyzer_agent = self.agents[analyzer_agent_id]

        print(f"🤖 Selected analyzer agent: {analyzer_agent_id}", flush=True)

        # Check if agents have isolated workspaces
        has_isolated_workspaces = False
        workspace_info = []
        for agent_id, agent in self.agents.items():
            if agent.backend and agent.backend.filesystem_manager:
                cwd = agent.backend.filesystem_manager.cwd
                if cwd and "workspace" in os.path.basename(cwd).lower():
                    has_isolated_workspaces = True
                    workspace_info.append(f"{agent_id}: {cwd}")

        if has_isolated_workspaces:
            print("🔒 Detected isolated agent workspaces - filesystem ops will be allowed", flush=True)

        log_orchestrator_activity(
            self.orchestrator_id,
            "Analyzing question irreversibility",
            {
                "analyzer_agent": analyzer_agent_id,
                "question_preview": user_question[:100] + "..." if len(user_question) > 100 else user_question,
                "has_isolated_workspaces": has_isolated_workspaces,
            },
        )

        # Build analysis prompt - now asking for specific tool names
        workspace_context = ""
        if has_isolated_workspaces:
            workspace_context = """
IMPORTANT - ISOLATED WORKSPACES:
The agents are working in isolated temporary workspaces (directories containing "workspace" in their name).
Filesystem operations (read_file, write_file, delete_file, list_files, etc.) within these isolated workspaces are SAFE and REVERSIBLE.
They should NOT be blocked because:
- These are temporary directories specific to this coordination session
- Files created/modified are isolated from external systems
- Changes are contained within the agent's sandbox
- The workspace can be cleared after coordination

Only block filesystem operations if they explicitly target paths OUTSIDE the isolated workspace.
"""

        analysis_prompt = f"""You are analyzing whether a user's request involves operations with irreversible outcomes.

USER REQUEST:
{user_question}
{workspace_context}
CONTEXT:
Your task is to determine if executing this request would involve MCP (Model Context Protocol) tools that have irreversible outcomes, and if so, identify which specific tools should be blocked.

MCP tools follow the naming convention: mcp__<server>__<tool_name>
Examples:
- mcp__discord__discord_send (irreversible - sends messages)
- mcp__discord__discord_read_channel (reversible - reads messages)
- mcp__twitter__post_tweet (irreversible - posts publicly)
- mcp__twitter__search_tweets (reversible - searches)
- mcp__filesystem__write_file (SAFE in isolated workspace - writes to temporary files)
- mcp__filesystem__read_file (reversible - reads files)

IRREVERSIBLE OPERATIONS:
- Sending messages (discord_send, slack_send, etc.)
- Posting content publicly (post_tweet, create_post, etc.)
- Deleting files or data OUTSIDE isolated workspace (delete_file on external paths, remove_data, etc.)
- Modifying external systems (write_file to external paths, update_record, etc.)
- Creating permanent records (create_issue, add_comment, etc.)
- Executing commands that change state (run_command, execute_script, etc.)

REVERSIBLE OPERATIONS (DO NOT BLOCK):
- Reading messages or data (read_channel, get_messages, etc.)
- Searching or querying information (search_tweets, query_data, etc.)
- Listing files or resources (list_files, list_channels, etc.)
- Fetching data from APIs (get_user, fetch_data, etc.)
- Viewing information (view_channel, get_info, etc.)
- Filesystem operations IN ISOLATED WORKSPACE (write_file, read_file, delete_file, list_files when in workspace*)

Respond in this EXACT format:
IRREVERSIBLE: YES/NO
BLOCKED_TOOLS: tool1, tool2, tool3

If IRREVERSIBLE is NO, leave BLOCKED_TOOLS empty.
If IRREVERSIBLE is YES, list the specific MCP tool names that should be blocked (e.g., mcp__discord__discord_send).

Your answer:"""

        # Create messages for the analyzer
        analysis_messages = [
            {"role": "user", "content": analysis_prompt},
        ]

        try:
            # Stream response from analyzer agent (but don't show to user)
            response_text = ""
            async for chunk in analyzer_agent.backend.stream_with_tools(
                messages=analysis_messages,
                tools=[],  # No tools needed for simple analysis
                agent_id=analyzer_agent_id,
            ):
                if chunk.type == "content" and chunk.content:
                    response_text += chunk.content

            # Parse response
            response_clean = response_text.strip()
            has_irreversible = False
            blocked_tools = set()

            # Parse IRREVERSIBLE line
            found_irreversible_line = False
            for line in response_clean.split("\n"):
                line = line.strip()
                if line.startswith("IRREVERSIBLE:"):
                    found_irreversible_line = True
                    # Extract the value after the colon
                    value = line.split(":", 1)[1].strip().upper()
                    # Check if the first word is YES
                    has_irreversible = value.startswith("YES")
                elif line.startswith("BLOCKED_TOOLS:"):
                    # Extract tool names after the colon
                    tools_part = line.split(":", 1)[1].strip()
                    if tools_part:
                        # Split by comma and clean up whitespace
                        blocked_tools = {tool.strip() for tool in tools_part.split(",") if tool.strip()}

            # Fallback: If no structured format found, look for YES/NO in the response
            if not found_irreversible_line:
                print("⚠️  [WARNING] No 'IRREVERSIBLE:' line found, using fallback parsing", flush=True)
                response_upper = response_clean.upper()
                # Look for clear YES/NO indicators
                if "YES" in response_upper and "NO" not in response_upper:
                    has_irreversible = True
                elif "NO" in response_upper:
                    has_irreversible = False
                else:
                    # Default to safe mode if unclear
                    has_irreversible = True

            log_orchestrator_activity(
                self.orchestrator_id,
                "Irreversibility analysis complete",
                {
                    "analyzer_agent": analyzer_agent_id,
                    "response": response_clean[:100],
                    "has_irreversible": has_irreversible,
                    "blocked_tools_count": len(blocked_tools),
                },
            )

            # Display nice UI box for planning mode status
            ui_box = self._format_planning_mode_ui(
                has_irreversible=has_irreversible,
                blocked_tools=blocked_tools,
                has_isolated_workspaces=has_isolated_workspaces,
                user_question=user_question,
            )
            print(ui_box, flush=True)

            return {"has_irreversible": has_irreversible, "blocked_tools": blocked_tools}

        except Exception as e:
            # On error, default to safe mode (planning enabled, block ALL)
            log_orchestrator_activity(
                self.orchestrator_id,
                "Irreversibility analysis failed, defaulting to planning mode",
                {"error": str(e)},
            )
            return {"has_irreversible": True, "blocked_tools": set()}

    async def _continuous_status_updates(self):
        """Background task to continuously update status.json during coordination.

        This task runs every 2 seconds to provide real-time status monitoring
        for automation tools and LLM agents.
        """
        try:
            while True:
                await asyncio.sleep(2)  # Update every 2 seconds
                log_session_dir = get_log_session_dir()
                if log_session_dir:
                    try:
                        self.coordination_tracker.save_status_file(log_session_dir, orchestrator=self)
                    except Exception as e:
                        logger.debug(f"Failed to update status file in background: {e}")
        except asyncio.CancelledError:
            # Task was cancelled, this is expected behavior
            pass
        except Exception as e:
            logger.warning(f"Background status update task encountered error: {e}")

    async def _coordinate_agents_with_timeout(self, conversation_context: Optional[Dict[str, Any]] = None) -> AsyncGenerator[StreamChunk, None]:
        """Execute coordination with orchestrator-level timeout protection.

        When restart is needed, this method completes and returns control to CLI,
        which will call coordinate() again (similar to multiturn pattern).
        """
        # Reset timing and state for this attempt
        self.coordination_start_time = time.time()
        self.total_tokens = 0
        self.is_orchestrator_timeout = False
        self.timeout_reason = None

        log_orchestrator_activity(
            self.orchestrator_id,
            f"Starting coordination attempt {self.current_attempt + 1}/{self.max_attempts}",
            {
                "timeout_seconds": self.config.timeout_config.orchestrator_timeout_seconds,
                "agents": list(self.agents.keys()),
                "has_restart_context": bool(self.restart_reason),
            },
        )

        # Set log attempt for directory organization (only if restart feature is enabled)
        if self.config.coordination_config.max_orchestration_restarts > 0:
            set_log_attempt(self.current_attempt + 1)

        # Track active coordination state for cleanup
        self._active_streams = {}
        self._active_tasks = {}

        timeout_seconds = self.config.timeout_config.orchestrator_timeout_seconds

        try:
            # Use asyncio.timeout for timeout protection
            async with asyncio.timeout(timeout_seconds):
                async for chunk in self._coordinate_agents(conversation_context):
                    # Track tokens if this is a content chunk
                    if hasattr(chunk, "content") and chunk.content:
                        self.total_tokens += len(chunk.content.split())  # Rough token estimation

                    yield chunk

        except asyncio.TimeoutError:
            self.is_orchestrator_timeout = True
            elapsed = time.time() - self.coordination_start_time
            self.timeout_reason = f"Time limit exceeded ({elapsed:.1f}s/{timeout_seconds}s)"
            # Track timeout for all agents that were still working
            for agent_id in self.agent_states.keys():
                if not self.agent_states[agent_id].has_voted:
                    self.coordination_tracker.track_agent_action(agent_id, ActionType.TIMEOUT, self.timeout_reason)

            # Force cleanup of any active agent streams and tasks
            await self._cleanup_active_coordination()

        # Handle timeout by jumping to final presentation
        if self.is_orchestrator_timeout:
            async for chunk in self._handle_orchestrator_timeout():
                yield chunk

        # Exit here - if restart is needed, CLI will call coordinate() again

    async def _coordinate_agents(self, conversation_context: Optional[Dict[str, Any]] = None) -> AsyncGenerator[StreamChunk, None]:
        """Execute unified MassGen coordination workflow with real-time streaming."""
        log_coordination_step(
            "Starting multi-agent coordination",
            {
                "agents": list(self.agents.keys()),
                "has_context": conversation_context is not None,
            },
        )

        # Check if we should skip coordination rounds (debug/test mode)
        if self.config.skip_coordination_rounds:
            log_stream_chunk(
                "orchestrator",
                "content",
                "⚡ [DEBUG MODE] Skipping coordination rounds, going straight to final presentation...\n\n",
                self.orchestrator_id,
            )
            yield StreamChunk(
                type="content",
                content="⚡ [DEBUG MODE] Skipping coordination rounds, going straight to final presentation...\n\n",
                source=self.orchestrator_id,
            )

            # Select first agent as winner (or random if needed)
            self._selected_agent = list(self.agents.keys())[0]
            log_coordination_step(
                "Skipped coordination, selected first agent",
                {"selected_agent": self._selected_agent},
            )

            # Present final answer immediately
            async for chunk in self._present_final_answer():
                yield chunk
            return

        log_stream_chunk(
            "orchestrator",
            "content",
            "🚀 Starting multi-agent coordination...\n\n",
            self.orchestrator_id,
        )
        yield StreamChunk(
            type="content",
            content="🚀 Starting multi-agent coordination...\n\n",
            source=self.orchestrator_id,
        )

        # Start background status update task for real-time monitoring
        status_update_task = asyncio.create_task(self._continuous_status_updates())

        votes = {}  # Track votes: voter_id -> {"agent_id": voted_for, "reason": reason}

        # Initialize all agents with has_voted = False and set restart flags
        for agent_id in self.agents.keys():
            self.agent_states[agent_id].has_voted = False
            self.agent_states[agent_id].restart_pending = True

        log_stream_chunk(
            "orchestrator",
            "content",
            "## 📋 Agents Coordinating\n",
            self.orchestrator_id,
        )
        yield StreamChunk(
            type="content",
            content="## 📋 Agents Coordinating\n",
            source=self.orchestrator_id,
        )

        # Start streaming coordination with real-time agent output
        async for chunk in self._stream_coordination_with_agents(votes, conversation_context):
            yield chunk

        # Determine final agent based on votes
        current_answers = {aid: state.answer for aid, state in self.agent_states.items() if state.answer}
        self._selected_agent = self._determine_final_agent_from_votes(votes, current_answers)

        # Track winning agent for memory sharing in future turns
        self._current_turn += 1
        if self._selected_agent:
            winner_entry = {
                "agent_id": self._selected_agent,
                "turn": self._current_turn,
            }
            self._winning_agents_history.append(winner_entry)
            logger.info(
                f"🏆 Turn {self._current_turn} winner: {self._selected_agent} " f"(tracked for memory sharing)",
            )

        log_coordination_step(
            "Final agent selected",
            {"selected_agent": self._selected_agent, "votes": votes},
        )

        # Cancel background status update task
        status_update_task.cancel()
        try:
            await status_update_task
        except asyncio.CancelledError:
            pass  # Expected

        # Present final answer
        async for chunk in self._present_final_answer():
            yield chunk

    async def _stream_coordination_with_agents(
        self,
        votes: Dict[str, Dict],
        conversation_context: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Coordinate agents with real-time streaming of their outputs.

        Processes agent stream signals:
        - "content": Streams real-time agent output to user
        - "result": Records votes/answers, triggers restart_pending for other agents
        - "error": Displays error and closes agent stream (self-terminating)
        - "done": Closes agent stream gracefully

        Restart Mechanism:
        When any agent provides new_answer, all other agents get restart_pending=True
        and gracefully terminate their current work before restarting.
        """
        active_streams = {}
        active_tasks = {}  # Track active tasks to prevent duplicate task creation

        # Store references for timeout cleanup
        self._active_streams = active_streams
        self._active_tasks = active_tasks

        # Stream agent outputs in real-time until all have voted
        while not all(state.has_voted for state in self.agent_states.values()):
            # Start new coordination iteration
            self.coordination_tracker.start_new_iteration()

            # Check for orchestrator timeout - stop spawning new agents
            if self.is_orchestrator_timeout:
                break
            # Start any agents that aren't running and haven't voted yet
            current_answers = {aid: state.answer for aid, state in self.agent_states.items() if state.answer}
            for agent_id in self.agents.keys():
                if agent_id not in active_streams and not self.agent_states[agent_id].has_voted and not self.agent_states[agent_id].is_killed:
                    active_streams[agent_id] = self._stream_agent_execution(
                        agent_id,
                        self.current_task,
                        current_answers,
                        conversation_context,
                        self._agent_paraphrases.get(agent_id),
                    )

            if not active_streams:
                break

            # Create tasks only for streams that don't already have active tasks
            for agent_id, stream in active_streams.items():
                if agent_id not in active_tasks:
                    active_tasks[agent_id] = asyncio.create_task(self._get_next_chunk(stream))

            if not active_tasks:
                break

            done, _ = await asyncio.wait(active_tasks.values(), return_when=asyncio.FIRST_COMPLETED)

            # Collect results from completed agents
            reset_signal = False
            voted_agents = {}
            answered_agents = {}
            completed_agent_ids = set()  # Track all agents whose tasks completed, i.e., done, error, result.

            # Process completed stream chunks
            for task in done:
                agent_id = next(aid for aid, t in active_tasks.items() if t is task)
                # Remove completed task from active_tasks
                del active_tasks[agent_id]

                try:
                    chunk_type, chunk_data = await task

                    if chunk_type == "content":
                        # Stream agent content in real-time with source info
                        log_stream_chunk("orchestrator", "content", chunk_data, agent_id)
                        yield StreamChunk(type="content", content=chunk_data, source=agent_id)

                    elif chunk_type == "reasoning":
                        # Stream reasoning content with proper attribution
                        log_stream_chunk("orchestrator", "reasoning", chunk_data, agent_id)
                        yield chunk_data  # chunk_data is already a StreamChunk with source

                    elif chunk_type == "result":
                        # Agent completed with result
                        result_type, result_data = chunk_data
                        # Result ends the agent's current stream
                        completed_agent_ids.add(agent_id)
                        log_stream_chunk(
                            "orchestrator",
                            f"result.{result_type}",
                            result_data,
                            agent_id,
                        )

                        # Emit agent completion status immediately upon result
                        yield StreamChunk(
                            type="agent_status",
                            source=agent_id,
                            status="completed",
                            content="",
                        )
                        await self._close_agent_stream(agent_id, active_streams)

                        if result_type == "answer":
                            # Agent provided an answer (initial or improved)
                            agent = self.agents.get(agent_id)
                            # Get the context that was sent to this agent
                            agent_context = self.get_last_context(agent_id)
                            # Save snapshot (of workspace and answer) when agent provides new answer
                            answer_timestamp = await self._save_agent_snapshot(
                                agent_id,
                                answer_content=result_data,
                                context_data=agent_context,
                            )
                            if agent and agent.backend.filesystem_manager:
                                agent.backend.filesystem_manager.log_current_state("after providing answer")
                            # Always record answers, even from restarting agents (orchestrator accepts them)

                            answered_agents[agent_id] = result_data
                            # Pass timestamp to coordination_tracker for mapping
                            self.coordination_tracker.add_agent_answer(
                                agent_id,
                                result_data,
                                snapshot_timestamp=answer_timestamp,
                            )
                            # Update status file for real-time monitoring
                            log_session_dir = get_log_session_dir()
                            if log_session_dir:
                                self.coordination_tracker.save_status_file(log_session_dir, orchestrator=self)
                            restart_triggered_id = agent_id  # Last agent to provide new answer
                            reset_signal = True
                            log_stream_chunk(
                                "orchestrator",
                                "content",
                                "✅ Answer provided\n",
                                agent_id,
                            )

                            # Track new answer event
                            log_stream_chunk(
                                "orchestrator",
                                "content",
                                "✅ Answer provided\n",
                                agent_id,
                            )
                            yield StreamChunk(
                                type="content",
                                content="✅ Answer provided\n",
                                source=agent_id,
                            )

                        elif result_type == "vote":
                            # Agent voted for existing answer
                            # Ignore votes from agents with restart pending (votes are about current state)
                            if self._check_restart_pending(agent_id):
                                voted_for = result_data.get("agent_id", "<unknown>")
                                reason = result_data.get("reason", "No reason provided")
                                # Track the ignored vote action
                                self.coordination_tracker.track_agent_action(
                                    agent_id,
                                    ActionType.VOTE_IGNORED,
                                    f"Voted for {voted_for} but ignored due to restart",
                                )
                                # Save in coordination tracker that we waste a vote due to restart
                                log_stream_chunk(
                                    "orchestrator",
                                    "content",
                                    f"🔄 Vote for [{voted_for}] ignored (reason: {reason}) - restarting due to new answers",
                                    agent_id,
                                )
                                yield StreamChunk(
                                    type="content",
                                    content=f"🔄 Vote for [{voted_for}] ignored (reason: {reason}) - restarting due to new answers",
                                    source=agent_id,
                                )
                                # yield StreamChunk(type="content", content="🔄 Vote ignored - restarting due to new answers", source=agent_id)
                            else:
                                # Save vote snapshot (includes workspace)
                                vote_timestamp = await self._save_agent_snapshot(
                                    agent_id=agent_id,
                                    vote_data=result_data,
                                    context_data=self.get_last_context(agent_id),
                                )
                                # Log workspaces for current agent
                                agent = self.agents.get(agent_id)
                                if agent and agent.backend.filesystem_manager:
                                    self.agents.get(agent_id).backend.filesystem_manager.log_current_state("after voting")
                                voted_agents[agent_id] = result_data
                                # Pass timestamp to coordination_tracker for mapping
                                self.coordination_tracker.add_agent_vote(
                                    agent_id,
                                    result_data,
                                    snapshot_timestamp=vote_timestamp,
                                )
                                # Update status file for real-time monitoring
                                log_session_dir = get_log_session_dir()
                                if log_session_dir:
                                    self.coordination_tracker.save_status_file(log_session_dir, orchestrator=self)

                                # Track new vote event
                                voted_for = result_data.get("agent_id", "<unknown>")
                                reason = result_data.get("reason", "No reason provided")
                                log_stream_chunk(
                                    "orchestrator",
                                    "content",
                                    f"✅ Vote recorded for [{result_data['agent_id']}]",
                                    agent_id,
                                )
                                yield StreamChunk(
                                    type="content",
                                    content=f"✅ Vote recorded for [{result_data['agent_id']}]",
                                    source=agent_id,
                                )

                    elif chunk_type == "error":
                        # Agent error
                        self.coordination_tracker.track_agent_action(agent_id, ActionType.ERROR, chunk_data)
                        # Error ends the agent's current stream
                        completed_agent_ids.add(agent_id)
                        log_stream_chunk("orchestrator", "error", chunk_data, agent_id)
                        yield StreamChunk(type="content", content=f"❌ {chunk_data}", source=agent_id)
                        log_stream_chunk("orchestrator", "agent_status", "completed", agent_id)
                        yield StreamChunk(
                            type="agent_status",
                            source=agent_id,
                            status="completed",
                            content="",
                        )
                        await self._close_agent_stream(agent_id, active_streams)

                    elif chunk_type == "debug":
                        # Debug information - forward as StreamChunk for logging
                        log_stream_chunk("orchestrator", "debug", chunk_data, agent_id)
                        yield StreamChunk(type="debug", content=chunk_data, source=agent_id)

                    elif chunk_type == "mcp_status":
                        # MCP status messages - forward with proper formatting
                        mcp_message = f"🔧 MCP: {chunk_data}"
                        log_stream_chunk("orchestrator", "mcp_status", chunk_data, agent_id)
                        yield StreamChunk(type="content", content=mcp_message, source=agent_id)

                    elif chunk_type == "done":
                        # Stream completed - emit completion status for frontend
                        completed_agent_ids.add(agent_id)
                        log_stream_chunk("orchestrator", "done", None, agent_id)
                        yield StreamChunk(
                            type="agent_status",
                            source=agent_id,
                            status="completed",
                            content="",
                        )
                        await self._close_agent_stream(agent_id, active_streams)

                except Exception as e:
                    self.coordination_tracker.track_agent_action(agent_id, ActionType.ERROR, f"Stream error - {e}")
                    completed_agent_ids.add(agent_id)
                    log_stream_chunk("orchestrator", "error", f"❌ Stream error - {e}", agent_id)
                    yield StreamChunk(
                        type="content",
                        content=f"❌ Stream error - {e}",
                        source=agent_id,
                    )
                    await self._close_agent_stream(agent_id, active_streams)

            # Apply all state changes atomically after processing all results
            if reset_signal:
                # Reset all agents' has_voted to False (any new answer invalidates all votes)
                for state in self.agent_states.values():
                    state.has_voted = False
                votes.clear()

                for agent_id in self.agent_states.keys():
                    self.agent_states[agent_id].restart_pending = True

                # Track restart signals
                self.coordination_tracker.track_restart_signal(restart_triggered_id, list(self.agent_states.keys()))
                # Note that the agent that sent the restart signal had its stream end so we should mark as completed. NOTE the below breaks it.
                self.coordination_tracker.complete_agent_restart(restart_triggered_id)
            # Set has_voted = True for agents that voted (only if no reset signal)
            else:
                for agent_id, vote_data in voted_agents.items():
                    self.agent_states[agent_id].has_voted = True
                    votes[agent_id] = vote_data

            # Update answers for agents that provided them
            for agent_id, answer in answered_agents.items():
                self.agent_states[agent_id].answer = answer

            # Update status based on what actions agents took
            for agent_id in completed_agent_ids:
                if agent_id in answered_agents:
                    self.coordination_tracker.change_status(agent_id, AgentStatus.ANSWERED)
                elif agent_id in voted_agents:
                    self.coordination_tracker.change_status(agent_id, AgentStatus.VOTED)
                # Errors and timeouts are already tracked via track_agent_action

        # Cancel any remaining tasks and close streams, as all agents have voted (no more new answers)
        for agent_id, task in active_tasks.items():
            if not task.done():
                self.coordination_tracker.track_agent_action(
                    agent_id,
                    ActionType.CANCELLED,
                    "All agents voted - coordination complete",
                )
            task.cancel()
        for agent_id in list(active_streams.keys()):
            await self._close_agent_stream(agent_id, active_streams)

    async def _copy_all_snapshots_to_temp_workspace(self, agent_id: str) -> Optional[str]:
        """Copy all agents' latest workspace snapshots to a temporary workspace for context sharing.

        TODO (v0.0.14 Context Sharing Enhancement - See docs/dev_notes/v0.0.14-context.md):
        - Validate agent permissions before restoring snapshots
        - Check if agent has read access to other agents' workspaces
        - Implement fine-grained control over which snapshots can be accessed
        - Add audit logging for snapshot access attempts

        Args:
            agent_id: ID of the Claude Code agent receiving the context

        Returns:
            Path to the agent's workspace directory if successful, None otherwise
        """
        agent = self.agents.get(agent_id)
        if not agent:
            return None

        # Check if agent has filesystem support
        if not agent.backend.filesystem_manager:
            return None

        # Create anonymous mapping for agent IDs (same logic as in message_templates.py)
        # This ensures consistency with the anonymous IDs shown to agents
        agent_mapping = {}
        sorted_agent_ids = sorted(self.agents.keys())
        for i, real_agent_id in enumerate(sorted_agent_ids, 1):
            agent_mapping[real_agent_id] = f"agent{i}"

        # Collect snapshots from snapshot_storage directory
        all_snapshots = {}
        if self._snapshot_storage:
            snapshot_base = Path(self._snapshot_storage)
            for source_agent_id in self.agents.keys():
                source_snapshot = snapshot_base / source_agent_id
                if source_snapshot.exists() and source_snapshot.is_dir():
                    all_snapshots[source_agent_id] = source_snapshot

        # Use the filesystem manager to copy snapshots to temp workspace
        workspace_path = await agent.backend.filesystem_manager.copy_snapshots_to_temp_workspace(all_snapshots, agent_mapping)
        return str(workspace_path) if workspace_path else None

    async def _save_agent_snapshot(
        self,
        agent_id: str,
        answer_content: str = None,
        vote_data: Dict[str, Any] = None,
        is_final: bool = False,
        context_data: Any = None,
    ) -> str:
        """
        Save a snapshot of an agent's working directory and answer/vote with the same timestamp.

        Creates a timestamped directory structure:
        - agent_id/timestamp/workspace/ - Contains the workspace files
        - agent_id/timestamp/answer.txt - Contains the answer text (if provided)
        - agent_id/timestamp/vote.json - Contains the vote data (if provided)
        - agent_id/timestamp/context.txt - Contains the context used (if provided)

        Args:
            agent_id: ID of the agent
            answer_content: The answer content to save (if provided)
            vote_data: The vote data to save (if provided)
            is_final: If True, save as final snapshot for presentation
            context_data: The context data to save (conversation, answers, etc.)

        Returns:
            The timestamp used for this snapshot
        """
        logger.info(f"[Orchestrator._save_agent_snapshot] Called for agent_id={agent_id}, has_answer={bool(answer_content)}, has_vote={bool(vote_data)}, is_final={is_final}")

        agent = self.agents.get(agent_id)
        if not agent:
            logger.warning(f"[Orchestrator._save_agent_snapshot] Agent {agent_id} not found in agents dict")
            return None

        # Generate single timestamp for answer/vote and workspace
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

        # Save answer if provided (or create final directory structure even if empty)
        if answer_content is not None or is_final:
            try:
                log_session_dir = get_log_session_dir()
                if log_session_dir:
                    if is_final:
                        # For final, save to final directory
                        timestamped_dir = log_session_dir / "final" / agent_id
                    else:
                        # For regular snapshots, create timestamped directory
                        timestamped_dir = log_session_dir / agent_id / timestamp
                    timestamped_dir.mkdir(parents=True, exist_ok=True)
                    answer_file = timestamped_dir / "answer.txt"

                    # Write the answer content (even if empty for final snapshots)
                    content_to_write = answer_content if answer_content is not None else ""
                    answer_file.write_text(content_to_write)
                    logger.info(f"[Orchestrator._save_agent_snapshot] Saved answer to {answer_file}")

            except Exception as e:
                logger.warning(f"[Orchestrator._save_agent_snapshot] Failed to save answer for {agent_id}: {e}")

        # Save vote if provided
        if vote_data:
            try:
                log_session_dir = get_log_session_dir()
                if log_session_dir:
                    # Create timestamped directory for vote
                    timestamped_dir = log_session_dir / agent_id / timestamp
                    timestamped_dir.mkdir(parents=True, exist_ok=True)
                    vote_file = timestamped_dir / "vote.json"

                    # Get current state for context
                    current_answers = {aid: state.answer for aid, state in self.agent_states.items() if state.answer}

                    # Create anonymous agent mapping
                    agent_mapping = {}
                    for i, real_id in enumerate(sorted(self.agents.keys()), 1):
                        agent_mapping[f"agent{i}"] = real_id

                    # Build comprehensive vote data
                    comprehensive_vote_data = {
                        "voter_id": agent_id,
                        "voter_anon_id": next(
                            (anon for anon, real in agent_mapping.items() if real == agent_id),
                            agent_id,
                        ),
                        "voted_for": vote_data.get("agent_id", "unknown"),
                        "voted_for_anon": next(
                            (anon for anon, real in agent_mapping.items() if real == vote_data.get("agent_id")),
                            "unknown",
                        ),
                        "reason": vote_data.get("reason", ""),
                        "timestamp": timestamp,
                        "unix_timestamp": time.time(),
                        "iteration": self.coordination_tracker.current_iteration if self.coordination_tracker else None,
                        "coordination_round": self.coordination_tracker.max_round if self.coordination_tracker else None,
                        "available_options": list(current_answers.keys()),
                        "available_options_anon": [
                            next(
                                (anon for anon, real in agent_mapping.items() if real == aid),
                                aid,
                            )
                            for aid in sorted(current_answers.keys())
                        ],
                        "agent_mapping": agent_mapping,
                        "vote_context": {
                            "total_agents": len(self.agents),
                            "agents_with_answers": len(current_answers),
                            "current_task": self.current_task,
                        },
                    }

                    # Write the comprehensive vote data
                    with open(vote_file, "w", encoding="utf-8") as f:
                        json.dump(comprehensive_vote_data, f, indent=2)
                    logger.info(f"[Orchestrator._save_agent_snapshot] Saved comprehensive vote to {vote_file}")

            except Exception as e:
                logger.error(f"[Orchestrator._save_agent_snapshot] Failed to save vote for {agent_id}: {e}")
                logger.error(f"[Orchestrator._save_agent_snapshot] Traceback: {traceback.format_exc()}")

        # Save workspace snapshot with the same timestamp
        if agent.backend.filesystem_manager:
            logger.info(f"[Orchestrator._save_agent_snapshot] Agent {agent_id} has filesystem_manager, calling save_snapshot with timestamp={timestamp if not is_final else None}")
            await agent.backend.filesystem_manager.save_snapshot(timestamp=timestamp if not is_final else None, is_final=is_final)

            # Clear workspace after saving snapshot (but not for final snapshots)
            if not is_final:
                agent.backend.filesystem_manager.clear_workspace()
                logger.info(f"[Orchestrator._save_agent_snapshot] Cleared workspace for {agent_id} after saving snapshot")
        else:
            logger.info(f"[Orchestrator._save_agent_snapshot] Agent {agent_id} does not have filesystem_manager")

        # Save context if provided (unified context saving)
        if context_data:
            try:
                log_session_dir = get_log_session_dir()
                if log_session_dir:
                    if is_final:
                        timestamped_dir = log_session_dir / "final" / agent_id
                    else:
                        timestamped_dir = log_session_dir / agent_id / timestamp

                    # Ensure directory exists (may not have been created if no answer/vote)
                    timestamped_dir.mkdir(parents=True, exist_ok=True)
                    context_file = timestamped_dir / "context.txt"

                    # Handle different types of context data
                    if isinstance(context_data, dict):
                        # Pretty print dict/JSON data
                        context_file.write_text(json.dumps(context_data, indent=2, default=str))
                    else:
                        # Save as string
                        context_file.write_text(str(context_data))

                    logger.info(f"[Orchestrator._save_agent_snapshot] Saved context to {context_file}")
            except Exception as ce:
                logger.warning(f"[Orchestrator._save_agent_snapshot] Failed to save context for {agent_id}: {ce}")

        # Return the timestamp for tracking
        return timestamp if not is_final else "final"

    def get_last_context(self, agent_id: str) -> Any:
        """Get the last context for an agent, or None if not available."""
        return self.agent_states[agent_id].last_context if agent_id in self.agent_states else None

    async def _close_agent_stream(self, agent_id: str, active_streams: Dict[str, AsyncGenerator]) -> None:
        """Close and remove an agent stream safely."""
        if agent_id in active_streams:
            try:
                await active_streams[agent_id].aclose()
            except Exception:
                pass  # Ignore cleanup errors
            del active_streams[agent_id]

    def _check_restart_pending(self, agent_id: str) -> bool:
        """Check if agent should restart and yield restart message if needed. This will always be called when exiting out of _stream_agent_execution()."""
        restart_pending = self.agent_states[agent_id].restart_pending
        return restart_pending

    async def _save_partial_work_on_restart(self, agent_id: str) -> Optional[str]:
        """
        Save partial work snapshot when agent is restarting due to new answers from others.
        This ensures that any work done before the restart is preserved and shared with other agents.

        Args:
            agent_id: ID of the agent being restarted

        Returns:
            The timestamp of the saved snapshot, or None if no snapshot was saved
        """
        agent = self.agents.get(agent_id)
        if not agent or not agent.backend.filesystem_manager:
            return None

        logger.info(f"[Orchestrator._save_partial_work_on_restart] Saving partial work for {agent_id} before restart")

        # Save the partial work snapshot with context
        timestamp = await self._save_agent_snapshot(
            agent_id,
            answer_content=None,  # No complete answer yet
            context_data=self.get_last_context(agent_id),
            is_final=False,
        )

        agent.backend.filesystem_manager.log_current_state("after saving partial work on restart")
        return timestamp

    def _build_update_message(self, agent_id: str, answers: Dict[str, str]) -> Dict[str, str]:
        """Build update message to inject when new answers arrive.

        Args:
            agent_id: The agent receiving the update
            answers: Dict mapping agent_id to their answer content

        Returns:
            Dict with role="user" and formatted update content
        """
        # Get normalized answers for this agent
        normalized_answers = self._normalize_workspace_paths_in_answers(
            answers,
            viewing_agent_id=agent_id,
        )

        # Create anonymous mapping (same logic as CURRENT ANSWERS)
        agent_mapping = {}
        for i, real_id in enumerate(sorted(answers.keys()), 1):
            agent_mapping[real_id] = f"agent{i}"

        # Format answers
        answers_section = []
        for real_id, answer in normalized_answers.items():
            anon_id = agent_mapping[real_id]
            answers_section.append(f"<{anon_id}> {answer} </{anon_id}>")

        answers_text = "\n".join(answers_section)

        # Check if this agent has workspace/filesystem enabled
        agent = self.agents.get(agent_id)
        has_workspace = agent and agent.backend.filesystem_manager is not None

        # Build update content (conditionally include workspace info)
        update_parts = [
            "UPDATE: While you were working, new answers were provided.",
            "",
            "<NEW ANSWERS>",
            answers_text,
            "</NEW ANSWERS>",
            "",
        ]

        # Only mention workspace if agent has filesystem access
        if has_workspace:
            # Build list of which agents provided the new answers (with their anonymous IDs)
            agent_workspace_list = []
            for real_id in sorted(answers.keys()):
                anon_id = agent_mapping[real_id]
                # Get the temp workspace path for this agent
                temp_ws_base = agent.backend.filesystem_manager.agent_temporary_workspace
                agent_workspace_path = f"{temp_ws_base}/{real_id}/"
                agent_workspace_list.append(f"  - {anon_id}'s work: {agent_workspace_path}")

            workspace_details = "\n".join(agent_workspace_list)

            update_parts.extend(
                [
                    "WORKSPACE UPDATE:",
                    "- Your workspace files are preserved",
                    f"- New workspace snapshots available from {len(answers)} agent(s):",
                    workspace_details,
                    "",
                ],
            )

        update_parts.extend(
            [
                "You can now:",
                "1. Continue your current approach if you think it's better or different",
                "2. Build upon or refine the new answers",
                "3. Vote for an existing answer if you agree with it",
                "",
                "Proceed with your decision (continue working, vote, or provide new_answer).",
            ],
        )

        return {"role": "user", "content": "\n".join(update_parts)}

    async def _inject_update_and_continue(
        self,
        agent_id: str,
        answers: Dict[str, str],
        conversation_messages: List[Dict],
    ) -> bool:
        """Inject update message and prepare agent to continue.

        Args:
            agent_id: The agent receiving the update
            answers: Dict of answers the agent had when it started (for comparison)
            conversation_messages: The conversation history to append the update to

        Returns:
            bool: True if injection succeeded and agent can continue, False if should restart
        """
        # Get CURRENT answers from agent_states
        current_answers = {aid: state.answer for aid, state in self.agent_states.items() if state.answer}

        # Filter to only NEW answers (ones that didn't exist when this agent started)
        new_answers = {aid: ans for aid, ans in current_answers.items() if aid not in answers}

        logger.info(f"[Orchestrator] Agent {agent_id} started with {len(answers)} answer(s), now has {len(current_answers)} answer(s)")
        logger.info(f"[Orchestrator] NEW answers since agent started: {list(new_answers.keys())}")

        # If no new answers, skip injection - agent already has all context
        if not new_answers:
            logger.info(f"[Orchestrator] No new answers to inject for {agent_id}, skipping update")
            # Clear both restart flags since agent already has full context
            if hasattr(self.coordination_tracker, "pending_agent_restarts"):
                self.coordination_tracker.pending_agent_restarts[agent_id] = False
            self.agent_states[agent_id].restart_pending = False
            return False  # Don't continue, let normal flow handle this

        logger.info(f"[Orchestrator] Injecting update for {agent_id}")

        # Save any partial work before injecting update
        snapshot_timestamp = await self._save_partial_work_on_restart(agent_id)

        # Build and inject update message with ONLY the new answers
        update_message = self._build_update_message(agent_id, new_answers)
        conversation_messages.append(update_message)

        # Save the update message to disk for observability
        if snapshot_timestamp:
            try:
                log_session_dir = get_log_session_dir()
                if log_session_dir:
                    update_message_file = log_session_dir / agent_id / snapshot_timestamp / "update_message.txt"
                    update_message_file.write_text(json.dumps(update_message, indent=2, default=str))
                    logger.info(f"[Orchestrator] Saved update message to {update_message_file}")
            except Exception as e:
                logger.warning(f"[Orchestrator] Failed to save update message for {agent_id}: {e}")

        # Track the update injection in coordination tracker
        answer_providers = ", ".join(sorted(new_answers.keys()))
        self.coordination_tracker.track_agent_action(
            agent_id,
            ActionType.UPDATE_INJECTED,
            f"Received update with {len(new_answers)} NEW answer(s) from: {answer_providers}",
        )

        # Clear the coordination tracker's pending restart flag (injection satisfies the need for update)
        if hasattr(self.coordination_tracker, "pending_agent_restarts"):
            self.coordination_tracker.pending_agent_restarts[agent_id] = False

        # Clear restart_pending so we don't re-inject
        self.agent_states[agent_id].restart_pending = False

        return True  # Injection successful, continue

    def _normalize_workspace_paths_in_answers(self, answers: Dict[str, str], viewing_agent_id: Optional[str] = None) -> Dict[str, str]:
        """Normalize absolute workspace paths in agent answers to accessible temporary workspace paths.

        This addresses the issue where agents working in separate workspace directories
        reference the same logical files using different absolute paths, causing them
        to think they're working on different tasks when voting.

        Converts workspace paths to temporary workspace paths where the viewing agent can actually
        access other agents' files for verification during context sharing.

        TODO: Replace with Docker volume mounts to ensure consistent paths across agents.

        Args:
            answers: Dict mapping agent_id to their answer content
            viewing_agent_id: The agent who will be reading these answers.
                            If None, normalizes to generic "workspace/" prefix.

        Returns:
            Dict with same keys but normalized answer content with accessible paths
        """
        normalized_answers = {}

        # Get viewing agent's temporary workspace path for context sharing (full absolute path)
        temp_workspace_base = None
        if viewing_agent_id:
            viewing_agent = self.agents.get(viewing_agent_id)
            if viewing_agent and viewing_agent.backend.filesystem_manager:
                temp_workspace_base = str(viewing_agent.backend.filesystem_manager.agent_temporary_workspace)
        # Create anonymous agent mapping for consistent directory names
        agent_mapping = {}
        sorted_agent_ids = sorted(self.agents.keys())
        for i, real_agent_id in enumerate(sorted_agent_ids, 1):
            agent_mapping[real_agent_id] = f"agent{i}"

        for agent_id, answer in answers.items():
            normalized_answer = answer

            # Replace all workspace paths found in the answer with accessible paths
            for other_agent_id, other_agent in self.agents.items():
                if not other_agent.backend.filesystem_manager:
                    continue

                anon_agent_id = agent_mapping.get(other_agent_id, f"agent_{other_agent_id}")
                replace_path = os.path.join(temp_workspace_base, anon_agent_id) if temp_workspace_base else anon_agent_id
                other_workspace = str(other_agent.backend.filesystem_manager.get_current_workspace())
                logger.debug(
                    f"[Orchestrator._normalize_workspace_paths_in_answers] Replacing {other_workspace} in answer from {agent_id} with path {replace_path}. original answer: {normalized_answer}",
                )
                normalized_answer = normalized_answer.replace(other_workspace, replace_path)
                logger.debug(f"[Orchestrator._normalize_workspace_paths_in_answers] Intermediate normalized answer: {normalized_answer}")

            normalized_answers[agent_id] = normalized_answer

        return normalized_answers

    def _normalize_workspace_paths_for_comparison(self, content: str, replacement_path: str = "/workspace") -> str:
        """
        Normalize all workspace paths in content to a canonical form for equality comparison.

        Unlike _normalize_workspace_paths_in_answers which normalizes paths for specific agents,
        this method normalizes ALL workspace paths to a neutral canonical form (like '/workspace')
        so that content can be compared for equality regardless of which agent workspace it came from.

        Args:
            content: Content that may contain workspace paths

        Returns:
            Content with all workspace paths normalized to canonical form
        """
        normalized_content = content

        # Replace all agent workspace paths with canonical '/workspace/'
        for _, agent in self.agents.items():
            if not agent.backend.filesystem_manager:
                continue

            # Get this agent's workspace path
            workspace_path = str(agent.backend.filesystem_manager.get_current_workspace())
            normalized_content = normalized_content.replace(workspace_path, replacement_path)

        return normalized_content

    async def _cleanup_active_coordination(self) -> None:
        """Force cleanup of active coordination streams and tasks on timeout."""
        # Cancel and cleanup active tasks
        if hasattr(self, "_active_tasks") and self._active_tasks:
            for agent_id, task in self._active_tasks.items():
                if not task.done():
                    # Only track if not already tracked by timeout above
                    if not self.is_orchestrator_timeout:
                        self.coordination_tracker.track_agent_action(agent_id, ActionType.CANCELLED, "Coordination cleanup")
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):
                        pass  # Ignore cleanup errors
            self._active_tasks.clear()

        # Close active streams
        if hasattr(self, "_active_streams") and self._active_streams:
            for agent_id in list(self._active_streams.keys()):
                await self._close_agent_stream(agent_id, self._active_streams)

    # TODO (v0.0.14 Context Sharing Enhancement - See docs/dev_notes/v0.0.14-context.md):
    # Add the following permission validation methods:
    # async def validate_agent_access(self, agent_id: str, resource_path: str, access_type: str) -> bool:
    #     """Check if agent has required permission for resource.
    #
    #     Args:
    #         agent_id: ID of the agent requesting access
    #         resource_path: Path to the resource being accessed
    #         access_type: Type of access (read, write, read-write, execute)
    #
    #     Returns:
    #         bool: True if access is allowed, False otherwise
    #     """
    #     # Implementation will check against PermissionManager
    #     pass

    def _calculate_jaccard_similarity(self, text1: str, text2: str) -> float:
        """Calculate Jaccard similarity between two texts based on word tokens.

        Args:
            text1: First text to compare
            text2: Second text to compare

        Returns:
            Similarity score between 0.0 and 1.0
        """
        # Tokenize and normalize - simple word-based approach
        words1 = set(text1.lower().split())
        words2 = set(text2.lower().split())

        if not words1 and not words2:
            return 1.0  # Both empty, consider identical
        if not words1 or not words2:
            return 0.0  # One empty, one not

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    def _check_answer_novelty(self, new_answer: str, existing_answers: Dict[str, str]) -> tuple[bool, Optional[str]]:
        """Check if a new answer is sufficiently different from existing answers.

        Args:
            new_answer: The proposed new answer
            existing_answers: Dictionary of existing answers {agent_id: answer_content}

        Returns:
            Tuple of (is_novel, error_message). is_novel=True if answer passes novelty check.
        """
        # Lenient mode: no checks (current behavior)
        if self.config.answer_novelty_requirement == "lenient":
            return (True, None)

        # Determine threshold based on setting
        if self.config.answer_novelty_requirement == "strict":
            threshold = 0.50  # Reject if >50% overlap (strict)
            error_msg = (
                "Your answer is too similar to existing answers (>50% overlap). Please use a fundamentally different approach, employ different tools/techniques, or vote for an existing answer."
            )
        else:  # balanced
            threshold = 0.70  # Reject if >70% overlap (balanced)
            error_msg = (
                "Your answer is too similar to existing answers (>70% overlap). "
                "Please provide a meaningfully different solution with new insights, "
                "approaches, or tools, or vote for an existing answer."
            )

        # Check similarity against all existing answers
        for agent_id, existing_answer in existing_answers.items():
            similarity = self._calculate_jaccard_similarity(new_answer, existing_answer)
            if similarity > threshold:
                logger.info(f"[Orchestrator] Answer rejected: {similarity:.2%} similar to {agent_id}'s answer (threshold: {threshold:.0%})")
                return (False, error_msg)

        # Answer is sufficiently novel
        return (True, None)

    def _check_answer_count_limit(self, agent_id: str) -> tuple[bool, Optional[str]]:
        """Check if agent has reached their answer count limit.

        Args:
            agent_id: The agent attempting to provide a new answer

        Returns:
            Tuple of (can_answer, error_message). can_answer=True if agent can provide another answer.
        """
        # No limit set
        if self.config.max_new_answers_per_agent is None:
            return (True, None)

        # Count how many answers this agent has provided
        answer_count = len(self.coordination_tracker.answers_by_agent.get(agent_id, []))

        if answer_count >= self.config.max_new_answers_per_agent:
            error_msg = f"You've reached the maximum of {self.config.max_new_answers_per_agent} new answer(s). Please vote for the best existing answer using the `vote` tool."
            logger.info(f"[Orchestrator] Answer rejected: {agent_id} has reached limit ({answer_count}/{self.config.max_new_answers_per_agent})")
            return (False, error_msg)

        return (True, None)

    def _create_tool_error_messages(
        self,
        agent: "ChatAgent",
        tool_calls: List[Dict[str, Any]],
        primary_error_msg: str,
        secondary_error_msg: str = None,
    ) -> List[Dict[str, Any]]:
        """
        Create tool error messages for all tool calls in a response.

        Args:
            agent: The ChatAgent instance for backend access
            tool_calls: List of tool calls that need error responses
            primary_error_msg: Error message for the first tool call
            secondary_error_msg: Error message for additional tool calls (defaults to primary_error_msg)

        Returns:
            List of tool result messages that can be sent back to the agent
        """
        if not tool_calls:
            return []

        if secondary_error_msg is None:
            secondary_error_msg = primary_error_msg

        enforcement_msgs = []

        # Send primary error for the first tool call
        first_tool_call = tool_calls[0]
        error_result_msg = agent.backend.create_tool_result_message(first_tool_call, primary_error_msg)
        enforcement_msgs.append(error_result_msg)

        # Send secondary error messages for any additional tool calls (API requires response to ALL calls)
        for additional_tool_call in tool_calls[1:]:
            neutral_msg = agent.backend.create_tool_result_message(additional_tool_call, secondary_error_msg)
            enforcement_msgs.append(neutral_msg)

        return enforcement_msgs

    async def _stream_agent_execution(
        self,
        agent_id: str,
        task: str,
        answers: Dict[str, str],
        conversation_context: Optional[Dict[str, Any]] = None,
        paraphrase: Optional[str] = None,
    ) -> AsyncGenerator[tuple, None]:
        """
        Stream agent execution with real-time content and final result.

        Yields:
            ("content", str): Real-time agent output (source attribution added by caller)
            ("result", (type, data)): Final result - ("vote", vote_data) or ("answer", content)
            ("error", str): Error message (self-terminating)
            ("done", None): Graceful completion signal

        Restart Behavior:
            If restart_pending is True, agent gracefully terminates with "done" signal.
            restart_pending is cleared at the beginning of execution.
        """
        agent = self.agents[agent_id]

        # Get backend name for logging
        backend_name = None
        if hasattr(agent, "backend") and hasattr(agent.backend, "get_provider_name"):
            backend_name = agent.backend.get_provider_name()

        log_orchestrator_activity(
            self.orchestrator_id,
            f"Starting agent execution: {agent_id}",
            {
                "agent_id": agent_id,
                "backend": backend_name,
                "task": task if task else None,
                "paraphrased_task": paraphrase,
                "agent_view_task": paraphrase or task,
                "has_answers": bool(answers),
                "num_answers": len(answers) if answers else 0,
            },
        )

        # Add periodic heartbeat logging for stuck agents
        paraphrase_note = " (with DSPy paraphrased question)" if paraphrase else ""
        logger.info(f"[Orchestrator] Agent {agent_id} starting execution loop...{paraphrase_note}")

        # Initialize agent state
        self.agent_states[agent_id].is_killed = False
        self.agent_states[agent_id].timeout_reason = None

        # Note: Do NOT clear restart_pending here - let the injection logic inside the iteration
        # loop handle it (see line ~1969). This ensures agents receive updates via injection
        # instead of restarting from scratch, even if they haven't started streaming yet.
        # The injection logic will:
        # - Inject new answers if they exist (and continue working)
        # - Clear the flag if no new answers exist (agent already has full context)

        # Copy all agents' snapshots to temp workspace for context sharing
        await self._copy_all_snapshots_to_temp_workspace(agent_id)

        # Clear the agent's workspace to prepare for new execution
        # This preserves the previous agent's output for logging while giving a clean slate
        if agent.backend.filesystem_manager:
            # agent.backend.filesystem_manager.clear_workspace()  # Don't clear for now.
            agent.backend.filesystem_manager.log_current_state("before execution")

        try:
            # Get agent's custom system message if available
            agent_system_message = agent.get_configurable_system_message()

            # Append filesystem system message, if applicable
            if agent.backend.filesystem_manager:
                main_workspace = str(agent.backend.filesystem_manager.get_current_workspace())
                temp_workspace = str(agent.backend.filesystem_manager.agent_temporary_workspace) if agent.backend.filesystem_manager.agent_temporary_workspace else None
                # Get context paths if available
                context_paths = agent.backend.filesystem_manager.path_permission_manager.get_context_paths() if agent.backend.filesystem_manager.path_permission_manager else []

                # Add previous turns as read-only context paths (only n-2 and earlier)
                previous_turns_context = self._get_previous_turns_context_paths()

                # Filter to only show turn n-2 and earlier (agents start with n-1 in their workspace)
                # Get current turn from previous_turns list
                current_turn_num = len(previous_turns_context) + 1 if previous_turns_context else 1
                turns_to_show = [t for t in previous_turns_context if t["turn"] < current_turn_num - 1]

                # Previous turn paths already registered in orchestrator constructor

                # Check if workspace was pre-populated (has any previous turns)
                workspace_prepopulated = len(previous_turns_context) > 0

                # Check if image generation is enabled for this agent
                enable_image_generation = False
                if hasattr(agent, "config") and agent.config:
                    enable_image_generation = agent.config.backend_params.get("enable_image_generation", False)
                elif hasattr(agent, "backend") and hasattr(agent.backend, "backend_params"):
                    enable_image_generation = agent.backend.backend_params.get("enable_image_generation", False)

                # Extract command execution parameters
                enable_command_execution = False
                docker_mode = False
                enable_sudo = False
                if hasattr(agent, "config") and agent.config:
                    enable_command_execution = agent.config.backend_params.get("enable_mcp_command_line", False)
                    docker_mode = agent.config.backend_params.get("command_line_execution_mode", "local") == "docker"
                    enable_sudo = agent.config.backend_params.get("command_line_docker_enable_sudo", False)
                elif hasattr(agent, "backend") and hasattr(agent.backend, "backend_params"):
                    enable_command_execution = agent.backend.backend_params.get("enable_mcp_command_line", False)
                    docker_mode = agent.backend.backend_params.get("command_line_execution_mode", "local") == "docker"
                    enable_sudo = agent.backend.backend_params.get("command_line_docker_enable_sudo", False)

                filesystem_system_message = self.message_templates.filesystem_system_message(
                    main_workspace=main_workspace,
                    temp_workspace=temp_workspace,
                    context_paths=context_paths,
                    previous_turns=turns_to_show,
                    workspace_prepopulated=workspace_prepopulated,
                    enable_image_generation=enable_image_generation,
                    agent_answers=answers,
                    enable_command_execution=enable_command_execution,
                    docker_mode=docker_mode,
                    enable_sudo=enable_sudo,
                )
                agent_system_message = f"{agent_system_message}\n\n{filesystem_system_message}" if agent_system_message else filesystem_system_message

            # Normalize workspace paths in agent answers for better comparison from this agent's perspective
            normalized_answers = self._normalize_workspace_paths_in_answers(answers, agent_id) if answers else answers

            # Log the normalized answers this agent will see
            if normalized_answers:
                logger.info(f"[Orchestrator] Agent {agent_id} sees normalized answers: {normalized_answers}")
            else:
                logger.info(f"[Orchestrator] Agent {agent_id} sees no existing answers")

            # Check if planning mode is enabled for coordination phase
            # Use the ACTUAL backend planning mode status (set by intelligent analysis)
            # instead of the static config setting
            is_coordination_phase = self.workflow_phase == "coordinating"
            planning_mode_enabled = agent.backend.is_planning_mode_enabled() if is_coordination_phase else False

            # Add planning mode instructions to system message if enabled
            # Only add instructions if we have a coordination config with planning instruction
            if planning_mode_enabled and self.config and hasattr(self.config, "coordination_config") and self.config.coordination_config and self.config.coordination_config.planning_mode_instruction:
                planning_instructions = f"\n\n{self.config.coordination_config.planning_mode_instruction}"
                agent_system_message = f"{agent_system_message}{planning_instructions}" if agent_system_message else planning_instructions.strip()
                print(f"📝 [{agent_id}] Adding planning mode instructions to system message", flush=True)

            # Build conversation with context support
            if conversation_context and conversation_context.get("conversation_history"):
                # Use conversation context-aware building
                conversation = self.message_templates.build_conversation_with_context(
                    current_task=task,
                    conversation_history=conversation_context.get("conversation_history", []),
                    agent_summaries=normalized_answers,
                    valid_agent_ids=list(normalized_answers.keys()) if normalized_answers else None,
                    base_system_message=agent_system_message,
                    paraphrase=paraphrase,
                )
            else:
                # Fallback to standard conversation building
                conversation = self.message_templates.build_initial_conversation(
                    task=task,
                    agent_summaries=normalized_answers,
                    valid_agent_ids=list(normalized_answers.keys()) if normalized_answers else None,
                    base_system_message=agent_system_message,
                    paraphrase=paraphrase,
                )

            # Inject restart context if this is a restart attempt (like multi-turn context)
            if self.restart_reason and self.restart_instructions:
                restart_context = self.message_templates.format_restart_context(
                    self.restart_reason,
                    self.restart_instructions,
                    previous_answer=self.previous_attempt_answer,
                )
                # Prepend restart context to user message
                conversation["user_message"] = restart_context + "\n\n" + conversation["user_message"]

            # Track all the context used for this agent execution
            self.coordination_tracker.track_agent_context(
                agent_id,
                answers,
                conversation.get("conversation_history", []),
                conversation,
            )

            # Store the context in agent state for later use when saving snapshots
            self.agent_states[agent_id].last_context = conversation

            # Log the messages being sent to the agent with backend info
            backend_name = None
            if hasattr(agent, "backend") and hasattr(agent.backend, "get_provider_name"):
                backend_name = agent.backend.get_provider_name()

            log_orchestrator_agent_message(
                agent_id,
                "SEND",
                {
                    "system": conversation["system_message"],
                    "user": conversation["user_message"],
                },
                backend_name=backend_name,
            )

            # Clean startup without redundant messages
            # Set planning mode on the agent's backend to control MCP tool execution
            if hasattr(agent.backend, "set_planning_mode"):
                agent.backend.set_planning_mode(planning_mode_enabled)
                if planning_mode_enabled:
                    logger.info(f"[Orchestrator] Backend planning mode ENABLED for {agent_id} - MCP tools blocked")
                else:
                    logger.info(f"[Orchestrator] Backend planning mode DISABLED for {agent_id} - MCP tools allowed")

            # Build proper conversation messages with system + user messages
            max_attempts = 3
            # Add planning guidance if enabled
            system_message = conversation["system_message"]
            if self.config.coordination_config.enable_agent_task_planning:
                planning_guidance = self.message_templates.get_planning_guidance()
                system_message = system_message + planning_guidance

            conversation_messages = [
                {"role": "system", "content": system_message},
                {"role": "user", "content": conversation["user_message"]},
            ]

            # Inject shared memory context
            conversation_messages = await self._inject_shared_memory_context(
                conversation_messages,
                agent_id,
            )

            enforcement_msg = self.message_templates.enforcement_message()

            # Update agent status to STREAMING
            self.coordination_tracker.change_status(agent_id, AgentStatus.STREAMING)

            for attempt in range(max_attempts):
                logger.info(f"[Orchestrator] Agent {agent_id} attempt {attempt + 1}/{max_attempts}")

                if self._check_restart_pending(agent_id):
                    logger.info(f"[Orchestrator] Agent {agent_id} has restart_pending flag")
                    # Inject update and continue instead of restarting
                    should_continue = await self._inject_update_and_continue(
                        agent_id,
                        answers,
                        conversation_messages,
                    )
                    if should_continue:
                        # Has new answers, inject update and continue
                        yield ("content", f"📨 [{agent_id}] receiving update with new answers\n")
                        continue  # Agent continues working with update
                    # else: No new answers (already has all context), just clear flag and proceed normally

                # Stream agent response with workflow tools
                # TODO: Need to still log this redo enforcement msg in the context.txt, and this & others in the coordination tracker.
                if attempt == 0:
                    # First attempt: orchestrator provides initial conversation
                    # But we need the agent to have this in its history for subsequent calls
                    # First attempt: provide complete conversation and reset agent's history
                    # Pass current turn and previous winners for memory sharing
                    chat_stream = agent.chat(
                        conversation_messages,
                        self.workflow_tools,
                        reset_chat=True,
                        current_stage=CoordinationStage.INITIAL_ANSWER,
                        orchestrator_turn=self._current_turn + 1,  # Next turn number
                        previous_winners=self._winning_agents_history.copy(),
                    )
                else:
                    # Subsequent attempts: send enforcement message (set by error handling)

                    if isinstance(enforcement_msg, list):
                        # Tool message array
                        chat_stream = agent.chat(
                            enforcement_msg,
                            self.workflow_tools,
                            reset_chat=False,
                            current_stage=CoordinationStage.ENFORCEMENT,
                            orchestrator_turn=self._current_turn + 1,
                            previous_winners=self._winning_agents_history.copy(),
                        )
                    else:
                        # Single user message
                        enforcement_message = {
                            "role": "user",
                            "content": enforcement_msg,
                        }
                        chat_stream = agent.chat(
                            [enforcement_message],
                            self.workflow_tools,
                            reset_chat=False,
                            current_stage=CoordinationStage.ENFORCEMENT,
                            orchestrator_turn=self._current_turn + 1,
                            previous_winners=self._winning_agents_history.copy(),
                        )
                response_text = ""
                tool_calls = []
                workflow_tool_found = False

                logger.info(f"[Orchestrator] Agent {agent_id} starting to stream chat response...")

                async for chunk in chat_stream:
                    chunk_type = self._get_chunk_type_value(chunk)
                    if chunk_type == "content":
                        response_text += chunk.content
                        # Stream agent content directly - source field handles attribution
                        yield ("content", chunk.content)
                        # Log received content
                        backend_name = None
                        if hasattr(agent, "backend") and hasattr(agent.backend, "get_provider_name"):
                            backend_name = agent.backend.get_provider_name()
                        log_orchestrator_agent_message(
                            agent_id,
                            "RECV",
                            {"content": chunk.content},
                            backend_name=backend_name,
                        )
                    elif chunk_type in [
                        "reasoning",
                        "reasoning_done",
                        "reasoning_summary",
                        "reasoning_summary_done",
                    ]:
                        # Stream reasoning content as tuple format
                        reasoning_chunk = StreamChunk(
                            type=chunk.type,
                            content=chunk.content,
                            source=agent_id,
                            reasoning_delta=getattr(chunk, "reasoning_delta", None),
                            reasoning_text=getattr(chunk, "reasoning_text", None),
                            reasoning_summary_delta=getattr(chunk, "reasoning_summary_delta", None),
                            reasoning_summary_text=getattr(chunk, "reasoning_summary_text", None),
                            item_id=getattr(chunk, "item_id", None),
                            content_index=getattr(chunk, "content_index", None),
                            summary_index=getattr(chunk, "summary_index", None),
                        )
                        yield ("reasoning", reasoning_chunk)
                    elif chunk_type == "backend_status":
                        pass
                    elif chunk_type == "mcp_status":
                        # Forward MCP status messages with proper formatting
                        mcp_content = f"🔧 MCP: {chunk.content}"
                        yield ("content", mcp_content)
                    elif chunk_type == "custom_tool_status":
                        # Forward custom tool status messages with proper formatting
                        custom_tool_content = f"🔧 Custom Tool: {chunk.content}"
                        yield ("content", custom_tool_content)
                    elif chunk_type == "debug":
                        # Forward debug chunks
                        yield ("debug", chunk.content)
                    elif chunk_type == "tool_calls":
                        # Use the correct tool_calls field
                        chunk_tool_calls = getattr(chunk, "tool_calls", []) or []
                        tool_calls.extend(chunk_tool_calls)
                        # Stream tool calls to show agent actions
                        # Get backend name for logging
                        backend_name = None
                        if hasattr(agent, "backend") and hasattr(agent.backend, "get_provider_name"):
                            backend_name = agent.backend.get_provider_name()

                        for tool_call in chunk_tool_calls:
                            tool_name = agent.backend.extract_tool_name(tool_call)
                            tool_args = agent.backend.extract_tool_arguments(tool_call)

                            if tool_name == "new_answer":
                                content = tool_args.get("content", "")
                                yield ("content", f'💡 Providing answer: "{content}"')
                                log_tool_call(
                                    agent_id,
                                    "new_answer",
                                    {"content": content},
                                    None,
                                    backend_name,
                                )  # Full content for debug logging
                            elif tool_name == "vote":
                                agent_voted_for = tool_args.get("agent_id", "")
                                reason = tool_args.get("reason", "")
                                log_tool_call(
                                    agent_id,
                                    "vote",
                                    {"agent_id": agent_voted_for, "reason": reason},
                                    None,
                                    backend_name,
                                )  # Full reason for debug logging

                                # Convert anonymous agent ID to real agent ID for display
                                real_agent_id = agent_voted_for
                                if answers:  # Only do mapping if answers exist
                                    agent_mapping = {}
                                    for i, real_id in enumerate(sorted(answers.keys()), 1):
                                        agent_mapping[f"agent{i}"] = real_id
                                    real_agent_id = agent_mapping.get(agent_voted_for, agent_voted_for)

                                yield (
                                    "content",
                                    f"🗳️ Voting for [{real_agent_id}] (options: {', '.join(sorted(answers.keys()))}) : {reason}",
                                )
                            else:
                                yield ("content", f"🔧 Using {tool_name}")
                                log_tool_call(agent_id, tool_name, tool_args, None, backend_name)
                    elif chunk_type == "error":
                        # Stream error information to user interface
                        error_msg = getattr(chunk, "error", str(chunk.content)) if hasattr(chunk, "error") else str(chunk.content)
                        yield ("content", f"❌ Error: {error_msg}\n")

                # Check for multiple vote calls before processing
                vote_calls = [tc for tc in tool_calls if agent.backend.extract_tool_name(tc) == "vote"]
                if len(vote_calls) > 1:
                    if attempt < max_attempts - 1:
                        if self._check_restart_pending(agent_id):
                            should_continue = await self._inject_update_and_continue(
                                agent_id,
                                answers,
                                conversation_messages,
                            )
                            if should_continue:
                                yield ("content", f"📨 [{agent_id}] receiving update with new answers\n")
                                continue  # Agent continues working with update
                            # else: No new answers, proceed with normal error handling
                        error_msg = f"Multiple vote calls not allowed. Made {len(vote_calls)} calls but must make exactly 1. Call vote tool once with chosen agent."
                        yield ("content", f"❌ {error_msg}")

                        # Send tool error response for all tool calls
                        enforcement_msg = self._create_tool_error_messages(
                            agent,
                            tool_calls,
                            error_msg,
                            "Vote rejected due to multiple votes.",
                        )
                        continue  # Retry this attempt
                    else:
                        yield (
                            "error",
                            f"Agent made {len(vote_calls)} vote calls in single response after max attempts",
                        )
                        yield ("done", None)
                        return

                # Check for mixed new_answer and vote calls - violates binary decision framework
                new_answer_calls = [tc for tc in tool_calls if agent.backend.extract_tool_name(tc) == "new_answer"]
                if len(vote_calls) > 0 and len(new_answer_calls) > 0:
                    if attempt < max_attempts - 1:
                        if self._check_restart_pending(agent_id):
                            should_continue = await self._inject_update_and_continue(
                                agent_id,
                                answers,
                                conversation_messages,
                            )
                            if should_continue:
                                yield ("content", f"📨 [{agent_id}] receiving update with new answers\n")
                                continue  # Agent continues working with update
                            # else: No new answers, proceed with normal error handling
                        error_msg = "Cannot use both 'vote' and 'new_answer' in same response. Choose one: vote for existing answer OR provide new answer."
                        yield ("content", f"❌ {error_msg}")

                        # Send tool error response for all tool calls that caused the violation
                        enforcement_msg = self._create_tool_error_messages(agent, tool_calls, error_msg)
                        continue  # Retry this attempt
                    else:
                        yield (
                            "error",
                            "Agent used both vote and new_answer tools in single response after max attempts",
                        )
                        yield ("done", None)
                        return

                # Process all tool calls
                if tool_calls:
                    for tool_call in tool_calls:
                        tool_name = agent.backend.extract_tool_name(tool_call)
                        tool_args = agent.backend.extract_tool_arguments(tool_call)

                        if tool_name == "vote":
                            # Log which agents we are choosing from
                            logger.info(f"[Orchestrator] Agent {agent_id} voting from options: {list(answers.keys()) if answers else 'No answers available'}")
                            # Check if agent should restart - votes invalid during restart
                            if self._check_restart_pending(agent_id):
                                should_continue = await self._inject_update_and_continue(
                                    agent_id,
                                    answers,
                                    conversation_messages,
                                )
                                if should_continue:
                                    yield ("content", f"📨 [{agent_id}] receiving update with new answers\n")
                                    continue  # Agent continues working with update
                                # else: No new answers, proceed with normal error handling

                            workflow_tool_found = True
                            # Vote for existing answer (requires existing answers)
                            if not answers:
                                # Invalid - can't vote when no answers exist
                                if attempt < max_attempts - 1:
                                    if self._check_restart_pending(agent_id):
                                        should_continue = await self._inject_update_and_continue(
                                            agent_id,
                                            answers,
                                            conversation_messages,
                                        )
                                        if should_continue:
                                            yield ("content", f"📨 [{agent_id}] receiving update with new answers\n")
                                            continue  # Agent continues working with update
                                        # else: No new answers, proceed with normal error handling
                                    error_msg = "Cannot vote when no answers exist. Use new_answer tool."
                                    yield ("content", f"❌ {error_msg}")
                                    # Create proper tool error message for retry
                                    enforcement_msg = self._create_tool_error_messages(agent, [tool_call], error_msg)
                                    continue
                                else:
                                    yield (
                                        "error",
                                        "Cannot vote when no answers exist after max attempts",
                                    )
                                    yield ("done", None)
                                    return

                            voted_agent_anon = tool_args.get("agent_id")
                            reason = tool_args.get("reason", "")

                            # Convert anonymous agent ID back to real agent ID
                            agent_mapping = {}
                            for i, real_agent_id in enumerate(sorted(answers.keys()), 1):
                                agent_mapping[f"agent{i}"] = real_agent_id

                            voted_agent = agent_mapping.get(voted_agent_anon, voted_agent_anon)

                            # Handle invalid agent_id
                            if voted_agent not in answers:
                                if attempt < max_attempts - 1:
                                    if self._check_restart_pending(agent_id):
                                        should_continue = await self._inject_update_and_continue(
                                            agent_id,
                                            answers,
                                            conversation_messages,
                                        )
                                        if should_continue:
                                            yield ("content", f"📨 [{agent_id}] receiving update with new answers\n")
                                            continue  # Agent continues working with update
                                        # else: No new answers, proceed with normal error handling
                                    # Create reverse mapping for error message
                                    reverse_mapping = {real_id: f"agent{i}" for i, real_id in enumerate(sorted(answers.keys()), 1)}
                                    valid_anon_agents = [reverse_mapping[real_id] for real_id in answers.keys()]
                                    error_msg = f"Invalid agent_id '{voted_agent_anon}'. Valid agents: {', '.join(valid_anon_agents)}"
                                    # Send tool error result back to agent
                                    yield ("content", f"❌ {error_msg}")
                                    # Create proper tool error message for retry
                                    enforcement_msg = self._create_tool_error_messages(agent, [tool_call], error_msg)
                                    continue  # Retry with updated conversation
                                else:
                                    yield (
                                        "error",
                                        f"Invalid agent_id after {max_attempts} attempts",
                                    )
                                    yield ("done", None)
                                    return
                            # Record the vote locally (but orchestrator may still ignore it)
                            self.agent_states[agent_id].votes = {
                                "agent_id": voted_agent,
                                "reason": reason,
                            }

                            # Record vote to shared memory
                            vote_message = f"Voted for {voted_agent}. Reason: {reason}"
                            await self._record_to_shared_memory(
                                agent_id=agent_id,
                                content=vote_message,
                                role="assistant",
                            )

                            # Send tool result - orchestrator will decide if vote is accepted
                            # Vote submitted (result will be shown by orchestrator)
                            yield (
                                "result",
                                ("vote", {"agent_id": voted_agent, "reason": reason}),
                            )
                            yield ("done", None)
                            return

                        elif tool_name == "new_answer":
                            workflow_tool_found = True
                            # Agent provided new answer
                            content = tool_args.get("content", response_text.strip())

                            # Check answer count limit
                            can_answer, count_error = self._check_answer_count_limit(agent_id)
                            if not can_answer:
                                if attempt < max_attempts - 1:
                                    if self._check_restart_pending(agent_id):
                                        should_continue = await self._inject_update_and_continue(
                                            agent_id,
                                            answers,
                                            conversation_messages,
                                        )
                                        if should_continue:
                                            yield ("content", f"📨 [{agent_id}] receiving update with new answers\n")
                                            continue  # Agent continues working with update
                                        # else: No new answers, proceed with normal error handling
                                    yield ("content", f"❌ {count_error}")
                                    # Create proper tool error message for retry
                                    enforcement_msg = self._create_tool_error_messages(agent, [tool_call], count_error)
                                    continue
                                else:
                                    yield (
                                        "error",
                                        f"Answer count limit reached after {max_attempts} attempts",
                                    )
                                    yield ("done", None)
                                    return

                            # Check answer novelty (similarity to existing answers)
                            is_novel, novelty_error = self._check_answer_novelty(content, answers)
                            if not is_novel:
                                if attempt < max_attempts - 1:
                                    if self._check_restart_pending(agent_id):
                                        should_continue = await self._inject_update_and_continue(
                                            agent_id,
                                            answers,
                                            conversation_messages,
                                        )
                                        if should_continue:
                                            yield ("content", f"📨 [{agent_id}] receiving update with new answers\n")
                                            continue  # Agent continues working with update
                                        # else: No new answers, proceed with normal error handling
                                    yield ("content", f"❌ {novelty_error}")
                                    # Create proper tool error message for retry
                                    enforcement_msg = self._create_tool_error_messages(agent, [tool_call], novelty_error)
                                    continue
                                else:
                                    yield (
                                        "error",
                                        f"Answer novelty requirement not met after {max_attempts} attempts",
                                    )
                                    yield ("done", None)
                                    return

                            # Check for duplicate answer
                            # Normalize both new content and existing content to neutral paths for comparison
                            normalized_new_content = self._normalize_workspace_paths_for_comparison(content)

                            for existing_agent_id, existing_content in answers.items():
                                normalized_existing_content = self._normalize_workspace_paths_for_comparison(existing_content)
                                if normalized_new_content.strip() == normalized_existing_content.strip():
                                    if attempt < max_attempts - 1:
                                        if self._check_restart_pending(agent_id):
                                            should_continue = await self._inject_update_and_continue(
                                                agent_id,
                                                answers,
                                                conversation_messages,
                                            )
                                            if should_continue:
                                                yield ("content", f"📨 [{agent_id}] receiving update with new answers\n")
                                                continue  # Agent continues working with update
                                            else:
                                                yield ("content", f"🔁 [{agent_id}] gracefully restarting due to new answer detected\n")
                                                yield ("done", None)
                                                return
                                        error_msg = f"Answer already provided by {existing_agent_id}. Provide different answer or vote for existing one."
                                        yield ("content", f"❌ {error_msg}")
                                        # Create proper tool error message for retry
                                        enforcement_msg = self._create_tool_error_messages(agent, [tool_call], error_msg)
                                        continue
                                    else:
                                        yield (
                                            "error",
                                            f"Duplicate answer provided after {max_attempts} attempts",
                                        )
                                        yield ("done", None)
                                        return
                            # Send successful tool result back to agent
                            # Answer recorded (result will be shown by orchestrator)

                            # Record to shared memory
                            await self._record_to_shared_memory(
                                agent_id=agent_id,
                                content=content,
                                role="assistant",
                            )

                            yield ("result", ("answer", content))
                            yield ("done", None)
                            return
                        elif tool_name.startswith("mcp"):
                            pass
                        elif tool_name.startswith("custom_tool"):
                            # Custom tools are handled by the backend and their results are streamed separately
                            pass
                        else:
                            # Non-workflow tools not yet implemented
                            yield (
                                "content",
                                f"🔧 used {tool_name} tool (not implemented)",
                            )

                # Case 3: Non-workflow response, need enforcement (only if no workflow tool was found)
                if not workflow_tool_found:
                    if self._check_restart_pending(agent_id):
                        should_continue = await self._inject_update_and_continue(
                            agent_id,
                            answers,
                            conversation_messages,
                        )
                        if should_continue:
                            yield ("content", f"📨 [{agent_id}] receiving update with new answers\n")
                            continue  # Agent continues working with update
                        # else: No new answers, proceed with normal error handling
                    if attempt < max_attempts - 1:
                        yield ("content", "🔄 needs to use workflow tools...\n")
                        # Reset to default enforcement message for this case
                        enforcement_msg = self.message_templates.enforcement_message()
                        continue  # Retry with updated conversation
                    else:
                        # Last attempt failed, agent did not provide proper workflow response
                        yield (
                            "error",
                            f"Agent failed to use workflow tools after {max_attempts} attempts",
                        )
                        yield ("done", None)
                        return

        except Exception as e:
            yield ("error", f"Agent execution failed: {str(e)}")
            yield ("done", None)

    async def _get_next_chunk(self, stream: AsyncGenerator[tuple, None]) -> tuple:
        """Get the next chunk from an agent stream."""
        try:
            return await stream.__anext__()
        except StopAsyncIteration:
            return ("done", None)
        except Exception as e:
            return ("error", str(e))

    async def _present_final_answer(self) -> AsyncGenerator[StreamChunk, None]:
        """Present the final coordinated answer with optional post-evaluation and restart loop."""

        # Select the best agent based on current state
        if not self._selected_agent:
            self._selected_agent = self._determine_final_agent_from_states()

        if not self._selected_agent:
            error_msg = "❌ Unable to provide coordinated answer - no successful agents"
            self.add_to_history("assistant", error_msg)
            log_stream_chunk("orchestrator", "error", error_msg)
            yield StreamChunk(type="content", content=error_msg)
            self.workflow_phase = "presenting"
            log_stream_chunk("orchestrator", "done", None)
            yield StreamChunk(type="done")
            return

        # Get vote results for presentation
        vote_results = self._get_vote_results()

        log_stream_chunk("orchestrator", "content", "## 🎯 Final Coordinated Answer\n")
        yield StreamChunk(type="content", content="## 🎯 Final Coordinated Answer\n")

        # Stream final presentation from winning agent
        log_stream_chunk("orchestrator", "content", f"🏆 Selected Agent: {self._selected_agent}\n")
        yield StreamChunk(type="content", content=f"🏆 Selected Agent: {self._selected_agent}\n")

        # Stream the final presentation (with full tool support)
        presentation_content = ""
        async for chunk in self.get_final_presentation(self._selected_agent, vote_results):
            if chunk.type == "content" and chunk.content:
                presentation_content += chunk.content
            yield chunk

        # Check if post-evaluation should run
        # Skip post-evaluation on final attempt (user clarification #4)
        is_final_attempt = self.current_attempt >= (self.max_attempts - 1)
        should_evaluate = self.max_attempts > 1 and not is_final_attempt

        if should_evaluate:
            # Run post-evaluation
            final_answer_to_evaluate = self._final_presentation_content or presentation_content
            async for chunk in self.post_evaluate_answer(self._selected_agent, final_answer_to_evaluate):
                yield chunk

            # Check if restart was requested
            if self.restart_pending and self.current_attempt < (self.max_attempts - 1):
                # Show restart banner
                restart_banner = f"""

🔄 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
   ORCHESTRATION RESTART (Attempt {self.current_attempt + 2}/{self.max_attempts})
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

REASON:
{self.restart_reason}

INSTRUCTIONS FOR NEXT ATTEMPT:
{self.restart_instructions}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"""
                log_stream_chunk("orchestrator", "status", restart_banner)
                yield StreamChunk(type="restart_banner", content=restart_banner, source="orchestrator")

                # Reset state for restart (prepare for next coordinate() call)
                self.handle_restart()

                # Don't add to history or set workflow phase - restart is pending
                # Exit here - CLI will detect restart_pending and call coordinate() again
                return

        # No restart - add final answer to conversation history
        if self._final_presentation_content:
            self.add_to_history("assistant", self._final_presentation_content)

        # Update workflow phase
        self.workflow_phase = "presenting"
        log_stream_chunk("orchestrator", "done", None)
        yield StreamChunk(type="done")

    async def _handle_orchestrator_timeout(self) -> AsyncGenerator[StreamChunk, None]:
        """Handle orchestrator timeout by jumping directly to get_final_presentation."""
        # Output orchestrator timeout message first
        log_stream_chunk(
            "orchestrator",
            "content",
            f"\n⚠️ **Orchestrator Timeout**: {self.timeout_reason}\n",
            self.orchestrator_id,
        )
        yield StreamChunk(
            type="content",
            content=f"\n⚠️ **Orchestrator Timeout**: {self.timeout_reason}\n",
            source=self.orchestrator_id,
        )

        # Count available answers
        available_answers = {aid: state.answer for aid, state in self.agent_states.items() if state.answer and not state.is_killed}

        log_stream_chunk(
            "orchestrator",
            "content",
            f"📊 Current state: {len(available_answers)} answers available\n",
            self.orchestrator_id,
        )
        yield StreamChunk(
            type="content",
            content=f"📊 Current state: {len(available_answers)} answers available\n",
            source=self.orchestrator_id,
        )

        # If no answers available, provide fallback with timeout explanation
        if len(available_answers) == 0:
            log_stream_chunk(
                "orchestrator",
                "error",
                "❌ No answers available from any agents due to timeout. No agents had enough time to provide responses.\n",
                self.orchestrator_id,
            )
            yield StreamChunk(
                type="content",
                content="❌ No answers available from any agents due to timeout. No agents had enough time to provide responses.\n",
                source=self.orchestrator_id,
            )
            self.workflow_phase = "presenting"
            log_stream_chunk("orchestrator", "done", None)
            yield StreamChunk(type="done")
            return

        # Determine best available agent for presentation
        current_votes = {aid: state.votes for aid, state in self.agent_states.items() if state.votes and not state.is_killed}

        self._selected_agent = self._determine_final_agent_from_votes(current_votes, available_answers)

        # Jump directly to get_final_presentation
        vote_results = self._get_vote_results()
        log_stream_chunk(
            "orchestrator",
            "content",
            f"🎯 Jumping to final presentation with {self._selected_agent} (selected despite timeout)\n",
            self.orchestrator_id,
        )
        yield StreamChunk(
            type="content",
            content=f"🎯 Jumping to final presentation with {self._selected_agent} (selected despite timeout)\n",
            source=self.orchestrator_id,
        )

        async for chunk in self.get_final_presentation(self._selected_agent, vote_results):
            yield chunk

    def _determine_final_agent_from_votes(self, votes: Dict[str, Dict], agent_answers: Dict[str, str]) -> str:
        """Determine which agent should present the final answer based on votes."""
        if not votes:
            # No votes yet, return first agent with an answer (earliest by generation time)
            return next(iter(agent_answers)) if agent_answers else None

        # Count votes for each agent
        vote_counts = {}
        for vote_data in votes.values():
            voted_for = vote_data.get("agent_id")
            if voted_for:
                vote_counts[voted_for] = vote_counts.get(voted_for, 0) + 1

        if not vote_counts:
            return next(iter(agent_answers)) if agent_answers else None

        # Find agents with maximum votes
        max_votes = max(vote_counts.values())
        tied_agents = [agent_id for agent_id, count in vote_counts.items() if count == max_votes]

        # Break ties by agent registration order (order in agent_states dict)
        for agent_id in agent_answers.keys():
            if agent_id in tied_agents:
                return agent_id

        # Fallback to first tied agent
        return tied_agents[0] if tied_agents else next(iter(agent_answers)) if agent_answers else None

    async def get_final_presentation(self, selected_agent_id: str, vote_results: Dict[str, Any]) -> AsyncGenerator[StreamChunk, None]:
        """Ask the winning agent to present their final answer with voting context."""
        # Start tracking the final round
        self.coordination_tracker.start_final_round(selected_agent_id)

        if selected_agent_id not in self.agents:
            log_stream_chunk("orchestrator", "error", f"Selected agent {selected_agent_id} not found")
            yield StreamChunk(type="error", error=f"Selected agent {selected_agent_id} not found")
            return

        agent = self.agents[selected_agent_id]

        # Enable write access for final agent on context paths. This ensures that those paths marked `write` by the user are now writable (as all previous agents were read-only).
        if agent.backend.filesystem_manager:
            agent.backend.filesystem_manager.path_permission_manager.set_context_write_access_enabled(True)

        # Reset backend planning mode to allow MCP tool execution during final presentation
        if hasattr(agent.backend, "set_planning_mode"):
            agent.backend.set_planning_mode(False)
            logger.info(f"[Orchestrator] Backend planning mode DISABLED for final presentation: {selected_agent_id} - MCP tools now allowed")

        # Copy all agents' snapshots to temp workspace to preserve context from coordination phase
        # This allows the agent to reference and access previous work
        temp_workspace_path = await self._copy_all_snapshots_to_temp_workspace(selected_agent_id)
        yield StreamChunk(
            type="debug",
            content=f"Restored workspace context for final presentation: {temp_workspace_path}",
            source=selected_agent_id,
        )

        # Prepare context about the voting
        vote_counts = vote_results.get("vote_counts", {})
        voter_details = vote_results.get("voter_details", {})
        is_tie = vote_results.get("is_tie", False)

        # Build voting summary -- note we only include the number of votes and reasons for the selected agent. There is no information about the distribution of votes beyond this.
        voting_summary = f"You received {vote_counts.get(selected_agent_id, 0)} vote(s)"
        if voter_details.get(selected_agent_id):
            reasons = [v["reason"] for v in voter_details[selected_agent_id]]
            voting_summary += f" with feedback: {'; '.join(reasons)}"

        if is_tie:
            voting_summary += " (tie-broken by registration order)"

        # Get all answers for context
        all_answers = {aid: s.answer for aid, s in self.agent_states.items() if s.answer}

        # Normalize workspace paths in both voting summary and all answers for final presentation. Use same function for consistency.
        normalized_voting_summary = self._normalize_workspace_paths_in_answers({selected_agent_id: voting_summary}, selected_agent_id)[selected_agent_id]
        normalized_all_answers = self._normalize_workspace_paths_in_answers(all_answers, selected_agent_id)

        # Use MessageTemplates to build the presentation message
        presentation_content = self.message_templates.build_final_presentation_message(
            original_task=self.current_task or "Task coordination",
            vote_summary=normalized_voting_summary,
            all_answers=normalized_all_answers,
            selected_agent_id=selected_agent_id,
        )

        # Get agent's configurable system message using the standard interface
        agent_system_message = agent.get_configurable_system_message()

        # Check if image generation is enabled for this agent
        enable_image_generation = False
        if hasattr(agent, "config") and agent.config:
            enable_image_generation = agent.config.backend_params.get("enable_image_generation", False)
        elif hasattr(agent, "backend") and hasattr(agent.backend, "backend_params"):
            enable_image_generation = agent.backend.backend_params.get("enable_image_generation", False)

        # Extract command execution parameters
        enable_command_execution = False
        docker_mode = False
        enable_sudo = False
        if hasattr(agent, "config") and agent.config:
            enable_command_execution = agent.config.backend_params.get("enable_mcp_command_line", False)
            docker_mode = agent.config.backend_params.get("command_line_execution_mode", "local") == "docker"
            enable_sudo = agent.config.backend_params.get("command_line_docker_enable_sudo", False)
        elif hasattr(agent, "backend") and hasattr(agent.backend, "backend_params"):
            enable_command_execution = agent.backend.backend_params.get("enable_mcp_command_line", False)
            docker_mode = agent.backend.backend_params.get("command_line_execution_mode", "local") == "docker"
            enable_sudo = agent.backend.backend_params.get("command_line_docker_enable_sudo", False)
        # Check if audio generation is enabled for this agent
        enable_audio_generation = False
        if hasattr(agent, "config") and agent.config:
            enable_audio_generation = agent.config.backend_params.get("enable_audio_generation", False)
        elif hasattr(agent, "backend") and hasattr(agent.backend, "backend_params"):
            enable_audio_generation = agent.backend.backend_params.get("enable_audio_generation", False)

        # Check if file generation is enabled for this agent
        enable_file_generation = False
        if hasattr(agent, "config") and agent.config:
            enable_file_generation = agent.config.backend_params.get("enable_file_generation", False)
        elif hasattr(agent, "backend") and hasattr(agent.backend, "backend_params"):
            enable_file_generation = agent.backend.backend_params.get("enable_file_generation", False)

        # Check if video generation is enabled for this agent
        enable_video_generation = False
        if hasattr(agent, "config") and agent.config:
            enable_video_generation = agent.config.backend_params.get("enable_video_generation", False)
        elif hasattr(agent, "backend") and hasattr(agent.backend, "backend_params"):
            enable_video_generation = agent.backend.backend_params.get("enable_video_generation", False)

        # Check if agent has write access to context paths (requires file delivery)
        has_irreversible_actions = False
        if agent.backend.filesystem_manager:
            context_paths = agent.backend.filesystem_manager.path_permission_manager.get_context_paths()
            # Check if any context path has write permission
            has_irreversible_actions = any(cp.get("permission") == "write" for cp in context_paths)

        # Build system message with workspace context if available
        base_system_message = self.message_templates.final_presentation_system_message(
            agent_system_message,
            enable_image_generation,
            enable_audio_generation,
            enable_file_generation,
            enable_video_generation,
            has_irreversible_actions,
            enable_command_execution,
        )

        # Change the status of all agents that were not selected to AgentStatus.COMPLETED
        for aid, _ in self.agent_states.items():
            if aid != selected_agent_id:
                self.coordination_tracker.change_status(aid, AgentStatus.COMPLETED)

        self.coordination_tracker.set_final_agent(selected_agent_id, voting_summary, all_answers)
        # Update status file for real-time monitoring
        log_session_dir = get_log_session_dir()
        if log_session_dir:
            self.coordination_tracker.save_status_file(log_session_dir, orchestrator=self)

        # Add workspace context information to system message if workspace was restored
        if agent.backend.filesystem_manager and temp_workspace_path:
            main_workspace = str(agent.backend.filesystem_manager.get_current_workspace())
            temp_workspace = str(agent.backend.filesystem_manager.agent_temporary_workspace) if agent.backend.filesystem_manager.agent_temporary_workspace else None
            # Get context paths if available
            context_paths = agent.backend.filesystem_manager.path_permission_manager.get_context_paths() if agent.backend.filesystem_manager.path_permission_manager else []

            # Add previous turns as read-only context paths (only n-2 and earlier)
            previous_turns_context = self._get_previous_turns_context_paths()

            # Filter to only show turn n-2 and earlier
            current_turn_num = len(previous_turns_context) + 1 if previous_turns_context else 1
            turns_to_show = [t for t in previous_turns_context if t["turn"] < current_turn_num - 1]

            # Check if workspace was pre-populated
            workspace_prepopulated = len(previous_turns_context) > 0

            base_system_message = (
                self.message_templates.filesystem_system_message(
                    main_workspace=main_workspace,
                    temp_workspace=temp_workspace,
                    context_paths=context_paths,
                    previous_turns=turns_to_show,
                    workspace_prepopulated=workspace_prepopulated,
                    enable_image_generation=enable_image_generation,
                    agent_answers=all_answers,
                    enable_command_execution=enable_command_execution,
                    docker_mode=docker_mode,
                    enable_sudo=enable_sudo,
                )
                + "\n\n## Instructions\n"
                + base_system_message
            )

        # Create conversation with system and user messages
        presentation_messages = [
            {
                "role": "system",
                "content": base_system_message,
            },
            {"role": "user", "content": presentation_content},
        ]

        # Store the final context in agent state for saving
        self.agent_states[selected_agent_id].last_context = {
            "messages": presentation_messages,
            "is_final": True,
            "vote_summary": voting_summary,
            "all_answers": all_answers,
            "complete_vote_results": vote_results,  # Include ALL vote data
            "vote_counts": vote_counts,
            "voter_details": voter_details,
            "all_votes": {aid: state.votes for aid, state in self.agent_states.items() if state.votes},  # All individual votes
        }

        log_stream_chunk(
            "orchestrator",
            "status",
            f"🎤  [{selected_agent_id}] presenting final answer\n",
        )
        yield StreamChunk(
            type="status",
            content=f"🎤  [{selected_agent_id}] presenting final answer\n",
        )

        # Use agent's chat method with proper system message (reset chat for clean presentation)
        presentation_content = ""
        final_snapshot_saved = False  # Track whether snapshot was saved during stream

        try:
            # Track final round iterations (each chunk is like an iteration)
            async for chunk in agent.chat(
                presentation_messages,
                reset_chat=True,
                current_stage=CoordinationStage.PRESENTATION,
                orchestrator_turn=self._current_turn,
                previous_winners=self._winning_agents_history.copy(),
            ):
                chunk_type = self._get_chunk_type_value(chunk)
                # Start new iteration for this chunk
                self.coordination_tracker.start_new_iteration()
                # Use the same streaming approach as regular coordination
                if chunk_type == "content" and chunk.content:
                    presentation_content += chunk.content
                    log_stream_chunk("orchestrator", "content", chunk.content, selected_agent_id)
                    yield StreamChunk(type="content", content=chunk.content, source=selected_agent_id)
                elif chunk_type in [
                    "reasoning",
                    "reasoning_done",
                    "reasoning_summary",
                    "reasoning_summary_done",
                ]:
                    # Stream reasoning content with proper attribution (same as main coordination)
                    reasoning_chunk = StreamChunk(
                        type=chunk_type,
                        content=chunk.content,
                        source=selected_agent_id,
                        reasoning_delta=getattr(chunk, "reasoning_delta", None),
                        reasoning_text=getattr(chunk, "reasoning_text", None),
                        reasoning_summary_delta=getattr(chunk, "reasoning_summary_delta", None),
                        reasoning_summary_text=getattr(chunk, "reasoning_summary_text", None),
                        item_id=getattr(chunk, "item_id", None),
                        content_index=getattr(chunk, "content_index", None),
                        summary_index=getattr(chunk, "summary_index", None),
                    )
                    # Use the same format as main coordination for consistency
                    log_stream_chunk("orchestrator", chunk.type, chunk.content, selected_agent_id)
                    yield reasoning_chunk
                elif chunk_type == "backend_status":
                    import json

                    status_json = json.loads(chunk.content)
                    cwd = status_json["cwd"]
                    session_id = status_json["session_id"]
                    content = f"""Final Temp Working directory: {cwd}.
    Final Session ID: {session_id}.
    """

                    log_stream_chunk("orchestrator", "content", content, selected_agent_id)
                    yield StreamChunk(type="content", content=content, source=selected_agent_id)
                elif chunk_type == "mcp_status":
                    # Handle MCP status messages in final presentation
                    mcp_content = f"🔧 MCP: {chunk.content}"
                    log_stream_chunk("orchestrator", "content", mcp_content, selected_agent_id)
                    yield StreamChunk(type="content", content=mcp_content, source=selected_agent_id)
                elif chunk_type == "done":
                    # Save the final workspace snapshot (from final workspace directory)
                    final_answer = presentation_content.strip() if presentation_content.strip() else self.agent_states[selected_agent_id].answer  # fallback to stored answer if no content generated
                    final_context = self.get_last_context(selected_agent_id)
                    await self._save_agent_snapshot(
                        self._selected_agent,
                        answer_content=final_answer,
                        is_final=True,
                        context_data=final_context,
                    )

                    # Track the final answer in coordination tracker
                    self.coordination_tracker.set_final_answer(selected_agent_id, final_answer, snapshot_timestamp="final")

                    # Mark snapshot as saved
                    final_snapshot_saved = True

                    log_stream_chunk("orchestrator", "done", None, selected_agent_id)
                    yield StreamChunk(type="done", source=selected_agent_id)
                elif chunk_type == "error":
                    log_stream_chunk("orchestrator", "error", chunk.error, selected_agent_id)
                    yield StreamChunk(type="error", error=chunk.error, source=selected_agent_id)
                # Pass through other chunk types as-is but with source
                else:
                    if hasattr(chunk, "source"):
                        log_stream_chunk(
                            "orchestrator",
                            chunk_type,
                            getattr(chunk, "content", ""),
                            selected_agent_id,
                        )
                        yield StreamChunk(
                            type=chunk_type,
                            content=getattr(chunk, "content", ""),
                            source=selected_agent_id,
                            **{k: v for k, v in chunk.__dict__.items() if k not in ["type", "content", "source", "timestamp", "sequence_number"]},
                        )
                    else:
                        log_stream_chunk(
                            "orchestrator",
                            chunk_type,
                            getattr(chunk, "content", ""),
                            selected_agent_id,
                        )
                        yield StreamChunk(
                            type=chunk_type,
                            content=getattr(chunk, "content", ""),
                            source=selected_agent_id,
                            **{k: v for k, v in chunk.__dict__.items() if k not in ["type", "content", "source", "timestamp", "sequence_number"]},
                        )

        finally:
            # Ensure final snapshot is always saved (even if "done" chunk wasn't yielded)
            if not final_snapshot_saved:
                final_answer = presentation_content.strip() if presentation_content.strip() else self.agent_states[selected_agent_id].answer
                final_context = self.get_last_context(selected_agent_id)
                await self._save_agent_snapshot(
                    self._selected_agent,
                    answer_content=final_answer,
                    is_final=True,
                    context_data=final_context,
                )

                # Track the final answer in coordination tracker
                self.coordination_tracker.set_final_answer(selected_agent_id, final_answer, snapshot_timestamp="final")

            # Store the final presentation content for logging
            if presentation_content.strip():
                # Store the synthesized final answer
                self._final_presentation_content = presentation_content.strip()
            else:
                # If no content was generated, use the stored answer as fallback
                stored_answer = self.agent_states[selected_agent_id].answer
                if stored_answer:
                    fallback_content = f"\n📋 Using stored answer as final presentation:\n\n{stored_answer}"
                    log_stream_chunk("orchestrator", "content", fallback_content, selected_agent_id)
                    yield StreamChunk(
                        type="content",
                        content=fallback_content,
                        source=selected_agent_id,
                    )
                    self._final_presentation_content = stored_answer
                else:
                    log_stream_chunk(
                        "orchestrator",
                        "error",
                        "\n❌ No content generated for final presentation and no stored answer available.",
                        selected_agent_id,
                    )
                    yield StreamChunk(
                        type="content",
                        content="\n❌ No content generated for final presentation and no stored answer available.",
                        source=selected_agent_id,
                    )

            # Mark final round as completed
            self.coordination_tracker.change_status(selected_agent_id, AgentStatus.COMPLETED)

            # Save logs
            self.save_coordination_logs()

        # Don't yield done here - let _present_final_answer handle final done after post-evaluation

    async def post_evaluate_answer(self, selected_agent_id: str, final_answer: str) -> AsyncGenerator[StreamChunk, None]:
        """Post-evaluation phase where winning agent evaluates its own answer.

        The agent reviews the final answer and decides whether to submit or restart
        with specific improvement instructions.

        Args:
            selected_agent_id: The agent that won the vote and presented the answer
            final_answer: The final answer that was presented

        Yields:
            StreamChunk: Stream chunks from the evaluation process
        """
        if selected_agent_id not in self.agents:
            log_stream_chunk("orchestrator", "error", f"Selected agent {selected_agent_id} not found for post-evaluation")
            yield StreamChunk(type="error", error=f"Selected agent {selected_agent_id} not found")
            return

        agent = self.agents[selected_agent_id]

        # Use debug override on first attempt if configured
        eval_answer = final_answer
        if self.config.debug_final_answer and self.current_attempt == 0:
            eval_answer = self.config.debug_final_answer
            log_stream_chunk("orchestrator", "debug", f"Using debug override for post-evaluation: {self.config.debug_final_answer}")
            yield StreamChunk(
                type="debug",
                content=f"[DEBUG MODE] Overriding answer for evaluation: {self.config.debug_final_answer}",
                source="orchestrator",
            )

        # Build evaluation message
        evaluation_content = f"""{self.message_templates.format_original_message(self.current_task or "Task")}

FINAL ANSWER TO EVALUATE:
{eval_answer}

Review this answer carefully and determine if it fully addresses the original task. Use your available tools to verify claims and check files as needed.
Then call either submit(confirmed=True) if the answer is satisfactory, or restart_orchestration(reason, instructions) if improvements are needed."""

        # Get agent's configurable system message
        agent_system_message = agent.get_configurable_system_message()

        # Build post-evaluation system message
        base_system_message = self.message_templates.post_evaluation_system_message(agent_system_message)

        # Add filesystem context if available (same as final presentation)
        if agent.backend.filesystem_manager:
            main_workspace = str(agent.backend.filesystem_manager.get_current_workspace())
            temp_workspace = str(agent.backend.filesystem_manager.agent_temporary_workspace) if agent.backend.filesystem_manager.agent_temporary_workspace else None
            context_paths = agent.backend.filesystem_manager.path_permission_manager.get_context_paths() if agent.backend.filesystem_manager.path_permission_manager else []
            previous_turns_context = self._get_previous_turns_context_paths()
            current_turn_num = len(previous_turns_context) + 1 if previous_turns_context else 1
            turns_to_show = [t for t in previous_turns_context if t["turn"] < current_turn_num - 1]
            workspace_prepopulated = len(previous_turns_context) > 0

            # Get all answers for context
            all_answers = {aid: s.answer for aid, s in self.agent_states.items() if s.answer}

            base_system_message = (
                self.message_templates.filesystem_system_message(
                    main_workspace=main_workspace,
                    temp_workspace=temp_workspace,
                    context_paths=context_paths,
                    previous_turns=turns_to_show,
                    workspace_prepopulated=workspace_prepopulated,
                    enable_image_generation=False,
                    agent_answers=all_answers,
                    enable_command_execution=False,
                    docker_mode=False,
                    enable_sudo=False,
                )
                + "\n\n## Post-Evaluation Task\n"
                + base_system_message
            )

        # Create evaluation messages
        evaluation_messages = [
            {"role": "system", "content": base_system_message},
            {"role": "user", "content": evaluation_content},
        ]

        # Get post-evaluation tools
        api_format = "chat_completions"  # Default format
        if hasattr(agent.backend, "api_format"):
            api_format = agent.backend.api_format
        post_eval_tools = get_post_evaluation_tools(api_format=api_format)

        log_stream_chunk("orchestrator", "status", "🔍 Post-evaluation: Reviewing final answer\n")
        yield StreamChunk(type="status", content="🔍 Post-evaluation: Reviewing final answer\n", source="orchestrator")

        # Stream evaluation with tools (with timeout protection)
        evaluation_complete = False
        tool_call_detected = False

        try:
            timeout_seconds = self.config.timeout_config.orchestrator_timeout_seconds
            async with asyncio.timeout(timeout_seconds):
                async for chunk in agent.chat(
                    messages=evaluation_messages,
                    tools=post_eval_tools,
                    reset_chat=True,
                    current_stage=CoordinationStage.POST_EVALUATION,
                    orchestrator_turn=self._current_turn,
                    previous_winners=self._winning_agents_history.copy(),
                ):
                    chunk_type = self._get_chunk_type_value(chunk)

                    if chunk_type == "content" and chunk.content:
                        log_stream_chunk("orchestrator", "content", chunk.content, selected_agent_id)
                        yield StreamChunk(type="content", content=chunk.content, source=selected_agent_id)
                    elif chunk_type in ["reasoning", "reasoning_done", "reasoning_summary", "reasoning_summary_done"]:
                        reasoning_chunk = StreamChunk(
                            type=chunk_type,
                            content=chunk.content,
                            source=selected_agent_id,
                            reasoning_delta=getattr(chunk, "reasoning_delta", None),
                            reasoning_text=getattr(chunk, "reasoning_text", None),
                            reasoning_summary_delta=getattr(chunk, "reasoning_summary_delta", None),
                            reasoning_summary_text=getattr(chunk, "reasoning_summary_text", None),
                            item_id=getattr(chunk, "item_id", None),
                            content_index=getattr(chunk, "content_index", None),
                            summary_index=getattr(chunk, "summary_index", None),
                        )
                        log_stream_chunk("orchestrator", chunk.type, chunk.content, selected_agent_id)
                        yield reasoning_chunk
                    elif chunk_type == "tool_calls":
                        # Post-evaluation tool call detected
                        tool_call_detected = True
                        if hasattr(chunk, "tool_calls") and chunk.tool_calls:
                            for tool_call in chunk.tool_calls:
                                # Use backend's tool extraction (same as regular coordination)
                                tool_name = agent.backend.extract_tool_name(tool_call)
                                tool_args = agent.backend.extract_tool_arguments(tool_call)

                                if tool_name == "submit":
                                    log_stream_chunk("orchestrator", "status", "✅ Evaluation complete - answer approved\n")
                                    yield StreamChunk(type="status", content="✅ Evaluation complete - answer approved\n", source="orchestrator")
                                    evaluation_complete = True
                                elif tool_name == "restart_orchestration":
                                    # Parse restart parameters from extracted args
                                    self.restart_reason = tool_args.get("reason", "No reason provided")
                                    self.restart_instructions = tool_args.get("instructions", "No instructions provided")
                                    self.restart_pending = True

                                    # Save the current winning answer for next attempt's context
                                    if self._selected_agent and self._selected_agent in self.agent_states:
                                        self.previous_attempt_answer = self.agent_states[self._selected_agent].answer
                                        logger.info(f"Saved previous attempt answer from {self._selected_agent} for restart context")

                                    log_stream_chunk("orchestrator", "status", "🔄 Restart requested\n")
                                    yield StreamChunk(type="status", content="🔄 Restart requested\n", source="orchestrator")
                                    evaluation_complete = True
                    elif chunk_type == "done":
                        log_stream_chunk("orchestrator", "done", None, selected_agent_id)
                        yield StreamChunk(type="done", source=selected_agent_id)
                    elif chunk_type == "error":
                        log_stream_chunk("orchestrator", "error", chunk.error, selected_agent_id)
                        yield StreamChunk(type="error", error=chunk.error, source=selected_agent_id)
                    else:
                        # Pass through other chunk types
                        log_stream_chunk("orchestrator", chunk_type, getattr(chunk, "content", ""), selected_agent_id)
                        yield StreamChunk(
                            type=chunk_type,
                            content=getattr(chunk, "content", ""),
                            source=selected_agent_id,
                            **{k: v for k, v in chunk.__dict__.items() if k not in ["type", "content", "source", "timestamp", "sequence_number"]},
                        )
        except asyncio.TimeoutError:
            log_stream_chunk("orchestrator", "status", "⏱️ Post-evaluation timed out - auto-submitting answer\n")
            yield StreamChunk(type="status", content="⏱️ Post-evaluation timed out - auto-submitting answer\n", source="orchestrator")
            evaluation_complete = True
            # Don't set restart_pending - let it default to False (auto-submit)
        finally:
            # If no tool was called and evaluation didn't complete, auto-submit
            if not evaluation_complete and not tool_call_detected:
                log_stream_chunk("orchestrator", "status", "✅ Auto-submitting answer (no tool call detected)\n")
                yield StreamChunk(type="status", content="✅ Auto-submitting answer (no tool call detected)\n", source="orchestrator")

    def handle_restart(self):
        """Reset orchestration state for restart attempt.

        Clears agent states and coordination messages while preserving
        restart reason and instructions for the next attempt.
        """
        log_orchestrator_activity("handle_restart", f"Resetting state for restart attempt {self.current_attempt + 1}")

        # Reset agent states
        for agent_id in self.agent_states:
            self.agent_states[agent_id] = AgentState()

        # Clear coordination messages
        self._coordination_messages = []
        self._selected_agent = None
        self._final_presentation_content = None

        # Reset coordination tracker for new attempt
        self.coordination_tracker = CoordinationTracker()
        self.coordination_tracker.initialize_session(list(self.agents.keys()))

        # Reset workflow phase to idle so next coordinate() call starts fresh
        self.workflow_phase = "idle"

        # Increment attempt counter
        self.current_attempt += 1

        log_orchestrator_activity("handle_restart", f"State reset complete - starting attempt {self.current_attempt + 1}")

    def _get_vote_results(self) -> Dict[str, Any]:
        """Get current vote results and statistics."""
        agent_answers = {aid: state.answer for aid, state in self.agent_states.items() if state.answer}
        votes = {aid: state.votes for aid, state in self.agent_states.items() if state.votes}

        # Count votes for each agent
        vote_counts = {}
        voter_details = {}

        for voter_id, vote_data in votes.items():
            voted_for = vote_data.get("agent_id")
            if voted_for:
                vote_counts[voted_for] = vote_counts.get(voted_for, 0) + 1
                if voted_for not in voter_details:
                    voter_details[voted_for] = []
                voter_details[voted_for].append(
                    {
                        "voter": voter_id,
                        "reason": vote_data.get("reason", "No reason provided"),
                    },
                )

        # Determine winner
        winner = None
        is_tie = False
        if vote_counts:
            max_votes = max(vote_counts.values())
            tied_agents = [agent_id for agent_id, count in vote_counts.items() if count == max_votes]
            is_tie = len(tied_agents) > 1

            # Break ties by agent registration order
            for agent_id in agent_answers.keys():
                if agent_id in tied_agents:
                    winner = agent_id
                    break

            if not winner:
                winner = tied_agents[0] if tied_agents else None

        # Create agent mapping for anonymous display
        agent_mapping = {}
        for i, real_id in enumerate(sorted(agent_answers.keys()), 1):
            agent_mapping[f"agent{i}"] = real_id

        return {
            "vote_counts": vote_counts,
            "voter_details": voter_details,
            "winner": winner,
            "is_tie": is_tie,
            "total_votes": len(votes),
            "agents_with_answers": len(agent_answers),
            "agents_voted": len([v for v in votes.values() if v.get("agent_id")]),
            "agent_mapping": agent_mapping,
        }

    def _determine_final_agent_from_states(self) -> Optional[str]:
        """Determine final agent based on current agent states."""
        # Find agents with answers
        agents_with_answers = {aid: state.answer for aid, state in self.agent_states.items() if state.answer}

        if not agents_with_answers:
            return None

        # Return the first agent with an answer (by order in agent_states)
        return next(iter(agents_with_answers))

    async def _handle_followup(self, user_message: str, conversation_context: Optional[Dict[str, Any]] = None) -> AsyncGenerator[StreamChunk, None]:
        """Handle follow-up questions after presenting final answer with conversation context."""
        # Analyze the follow-up question for irreversibility before re-coordinating
        has_irreversible = await self._analyze_question_irreversibility(user_message, conversation_context or {})

        # Set planning mode for all agents based on analysis
        for agent_id, agent in self.agents.items():
            if hasattr(agent.backend, "set_planning_mode"):
                agent.backend.set_planning_mode(has_irreversible)
                log_orchestrator_activity(
                    self.orchestrator_id,
                    f"Set planning mode for {agent_id} (follow-up)",
                    {"planning_mode_enabled": has_irreversible, "reason": "follow-up irreversibility analysis"},
                )

        # For now, acknowledge with context awareness
        # Future: implement full re-coordination with follow-up context

        if conversation_context and len(conversation_context.get("conversation_history", [])) > 0:
            log_stream_chunk(
                "orchestrator",
                "content",
                f"🤔 Thank you for your follow-up question in our ongoing conversation. I understand you're asking: "
                f"'{user_message}'. Currently, the coordination is complete, but I can help clarify the answer or "
                f"coordinate a new task that takes our conversation history into account.",
            )
            yield StreamChunk(
                type="content",
                content=f"🤔 Thank you for your follow-up question in our ongoing conversation. I understand you're "
                f"asking: '{user_message}'. Currently, the coordination is complete, but I can help clarify the answer "
                f"or coordinate a new task that takes our conversation history into account.",
            )
        else:
            log_stream_chunk(
                "orchestrator",
                "content",
                f"🤔 Thank you for your follow-up: '{user_message}'. The coordination is complete, but I can help clarify the answer or coordinate a new task if needed.",
            )
            yield StreamChunk(
                type="content",
                content=f"🤔 Thank you for your follow-up: '{user_message}'. The coordination is complete, but I can help clarify the answer or coordinate a new task if needed.",
            )

        log_stream_chunk("orchestrator", "done", None)
        yield StreamChunk(type="done")

    # =============================================================================
    # PUBLIC API METHODS
    # =============================================================================

    def add_agent(self, agent_id: str, agent: ChatAgent) -> None:
        """Add a new sub-agent to the orchestrator."""
        self.agents[agent_id] = agent
        self.agent_states[agent_id] = AgentState()

    def remove_agent(self, agent_id: str) -> None:
        """Remove a sub-agent from the orchestrator."""
        if agent_id in self.agents:
            del self.agents[agent_id]
        if agent_id in self.agent_states:
            del self.agent_states[agent_id]

    def get_final_result(self) -> Optional[Dict[str, Any]]:
        """
        Get final result for session persistence.

        Returns:
            Dict with final_answer, winning_agent_id, workspace_path, and winning_agents_history,
            or None if not available
        """
        if not self._selected_agent or not self._final_presentation_content:
            return None

        winning_agent = self.agents.get(self._selected_agent)
        workspace_path = None
        if winning_agent and winning_agent.backend.filesystem_manager:
            workspace_path = str(winning_agent.backend.filesystem_manager.get_current_workspace())

        return {
            "final_answer": self._final_presentation_content,
            "winning_agent_id": self._selected_agent,
            "workspace_path": workspace_path,
            "winning_agents_history": self._winning_agents_history.copy(),  # For cross-turn memory sharing
        }

    def get_status(self) -> Dict[str, Any]:
        """Get current orchestrator status."""
        # Calculate vote results
        vote_results = self._get_vote_results()

        return {
            "session_id": self.session_id,
            "workflow_phase": self.workflow_phase,
            "current_task": self.current_task,
            "selected_agent": self._selected_agent,
            "final_presentation_content": self._final_presentation_content,
            "vote_results": vote_results,
            "agents": {
                aid: {
                    "agent_status": agent.get_status(),
                    "coordination_state": {
                        "answer": state.answer,
                        "has_voted": state.has_voted,
                    },
                }
                for aid, (agent, state) in zip(
                    self.agents.keys(),
                    zip(self.agents.values(), self.agent_states.values()),
                )
            },
            "conversation_length": len(self.conversation_history),
        }

    def get_configurable_system_message(self) -> Optional[str]:
        """
        Get the configurable system message for the orchestrator.

        This can define how the orchestrator should coordinate agents, construct messages,
        handle conflicts, make decisions, etc. For example:
        - Custom voting strategies
        - Message construction templates
        - Conflict resolution approaches
        - Coordination workflow preferences

        Returns:
            Orchestrator's configurable system message if available, None otherwise
        """
        if self.config and hasattr(self.config, "get_configurable_system_message"):
            return self.config.get_configurable_system_message()
        elif self.config and hasattr(self.config, "_custom_system_instruction"):
            # Access private attribute to avoid deprecation warning
            return self.config._custom_system_instruction
        elif self.config and self.config.backend_params:
            # Check for backend-specific system prompts
            backend_params = self.config.backend_params
            if "system_prompt" in backend_params:
                return backend_params["system_prompt"]
            elif "append_system_prompt" in backend_params:
                return backend_params["append_system_prompt"]
        return None

    def _clear_agent_workspaces(self) -> None:
        """
        Clear all agent workspaces and pre-populate with previous turn's results.

        This creates a WRITABLE copy of turn n-1 in each agent's workspace.
        Note: CLI separately provides turn n-1 as a READ-ONLY context path, allowing
        agents to both modify files (in workspace) and reference originals (via context path).
        """
        # Get previous turn (n-1) workspace for pre-population
        previous_turn_workspace = None
        if self._previous_turns:
            # Get the most recent turn (last in list)
            latest_turn = self._previous_turns[-1]
            previous_turn_workspace = Path(latest_turn["path"])

        for agent_id, agent in self.agents.items():
            if agent.backend.filesystem_manager:
                workspace_path = agent.backend.filesystem_manager.get_current_workspace()
                if workspace_path and Path(workspace_path).exists():
                    # Clear workspace contents but keep the directory
                    for item in Path(workspace_path).iterdir():
                        if item.is_file():
                            item.unlink()
                        elif item.is_dir():
                            shutil.rmtree(item)
                    logger.info(f"[Orchestrator] Cleared workspace for {agent_id}: {workspace_path}")

                    # Pre-populate with previous turn's results if available (creates writable copy)
                    if previous_turn_workspace and previous_turn_workspace.exists():
                        logger.info(f"[Orchestrator] Pre-populating {agent_id} workspace with writable copy of turn n-1 from {previous_turn_workspace}")
                        for item in previous_turn_workspace.iterdir():
                            dest = Path(workspace_path) / item.name
                            if item.is_file():
                                shutil.copy2(item, dest)
                            elif item.is_dir():
                                shutil.copytree(item, dest, dirs_exist_ok=True)
                        logger.info(f"[Orchestrator] Pre-populated {agent_id} workspace with writable copy of turn n-1")

    def _get_previous_turns_context_paths(self) -> List[Dict[str, Any]]:
        """
        Get previous turns as context paths for current turn's agents.

        Returns:
            List of previous turn information with path, turn number, and task
        """
        return self._previous_turns

    async def reset(self) -> None:
        """Reset orchestrator state for new task."""
        self.conversation_history.clear()
        self.current_task = None
        self.workflow_phase = "idle"
        self._coordination_messages.clear()
        self._selected_agent = None
        self._final_presentation_content = None

        # Reset agent states
        for state in self.agent_states.values():
            state.answer = None
            state.has_voted = False
            state.restart_pending = False
            state.is_killed = False
            state.timeout_reason = None

        # Reset orchestrator timeout tracking
        self.total_tokens = 0
        self.coordination_start_time = 0
        self.is_orchestrator_timeout = False
        self.timeout_reason = None

        # Clear coordination state
        self._active_streams = {}
        self._active_tasks = {}

        if self.dspy_paraphraser:
            self.dspy_paraphraser.clear_cache()


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def create_orchestrator(
    agents: List[tuple],
    orchestrator_id: str = "orchestrator",
    session_id: Optional[str] = None,
    config: Optional[AgentConfig] = None,
    snapshot_storage: Optional[str] = None,
    agent_temporary_workspace: Optional[str] = None,
) -> Orchestrator:
    """
    Create a MassGen orchestrator with sub-agents.

    Args:
        agents: List of (agent_id, ChatAgent) tuples
        orchestrator_id: Unique identifier for this orchestrator (default: "orchestrator")
        session_id: Optional session ID
        config: Optional AgentConfig for orchestrator customization
        snapshot_storage: Optional path to store agent workspace snapshots
        agent_temporary_workspace: Optional path for agent temporary workspaces (for Claude Code context sharing)

    Returns:
        Configured Orchestrator
    """
    agents_dict = {agent_id: agent for agent_id, agent in agents}

    return Orchestrator(
        agents=agents_dict,
        orchestrator_id=orchestrator_id,
        session_id=session_id,
        config=config,
        snapshot_storage=snapshot_storage,
        agent_temporary_workspace=agent_temporary_workspace,
    )
