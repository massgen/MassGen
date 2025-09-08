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
import os
import re
import time
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, AsyncGenerator
from dataclasses import dataclass, field
from .message_templates import MessageTemplates
from .agent_config import AgentConfig
from .backend.base import StreamChunk
from .chat_agent import ChatAgent
from .utils import ActionType, AgentStatus
from .coordination_tracker import CoordinationTracker
from .logger_config import (
    log_orchestrator_activity,
    log_orchestrator_agent_message,
    log_coordination_step,
    log_tool_call,
    log_stream_chunk,
    logger,  # Import logger directly for INFO logging
    get_log_session_dir  # Import to get log directory
)


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
        snapshot_storage: Optional[str] = None,
        agent_temporary_workspace: Optional[str] = None,
    ):
        """
        Initialize MassGen orchestrator.

        Args:
            agents: Dictionary of {agent_id: ChatAgent} - can be individual agents or other orchestrators
            orchestrator_id: Unique identifier for this orchestrator (default: "orchestrator")
            session_id: Optional session identifier
            config: Optional AgentConfig for customizing orchestrator behavior
            snapshot_storage: Optional path to store agent workspace snapshots
            agent_temporary_workspace: Optional path for agent temporary workspaces
        """
        super().__init__(session_id)
        self.orchestrator_id = orchestrator_id
        self.agents = agents
        self.agent_states = {aid: AgentState() for aid in agents.keys()}
        self.config = config or AgentConfig.create_openai_config()

        # Get message templates from config
        self.message_templates = self.config.message_templates or MessageTemplates()
        # Create workflow tools for agents (vote and new_answer)
        self.workflow_tools = self.message_templates.get_standard_tools(
            list(agents.keys())
        )

        # MassGen-specific state
        self.current_task: Optional[str] = None
        self.workflow_phase: str = "idle"  # idle, coordinating, presenting

        # Internal coordination state
        self._coordination_messages: List[Dict[str, str]] = []
        self._selected_agent: Optional[str] = None
        self._final_presentation_content: Optional[str] = None

        # Timeout and resource tracking
        self.total_tokens: int = 0
        self.coordination_start_time: float = 0
        self.is_orchestrator_timeout: bool = False
        self.timeout_reason: Optional[str] = None

        # Coordination state tracking for cleanup
        self._active_streams: Dict = {}
        self._active_tasks: Dict = {}
        
        # Context sharing for agents with filesystem support
        self._snapshot_storage: Optional[str] = snapshot_storage
        self._agent_temporary_workspace: Optional[str] = agent_temporary_workspace
        
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
                    agent_temporary_workspace=self._agent_temporary_workspace
                )

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
            yield StreamChunk(
                type="error", error="No user message found in conversation"
            )
            return

        # Add user message to history
        self.add_to_history("user", user_message)

        # Determine what to do based on current state and conversation context
        if self.workflow_phase == "idle":
            # New task - start MassGen coordination with full context
            self.current_task = user_message
            self.coordination_tracker.set_user_prompt(self.current_task)
            self.workflow_phase = "coordinating"

            async for chunk in self._coordinate_agents_with_timeout(
                conversation_context
            ):
                yield chunk

        elif self.workflow_phase == "presenting":
            # Handle follow-up question with full conversation context
            async for chunk in self._handle_followup(
                user_message, conversation_context
            ):
                yield chunk
        else:
            # Already coordinating - provide status update
            log_stream_chunk("orchestrator", "content", "🔄 Coordinating agents, please wait...")
            yield StreamChunk(
                type="content", content="🔄 Coordinating agents, please wait..."
            )
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

    def _build_conversation_context(
        self, messages: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
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

    async def _coordinate_agents_with_timeout(
        self, conversation_context: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[StreamChunk, None]:
        """Execute coordination with orchestrator-level timeout protection."""
        self.coordination_start_time = time.time()
        self.total_tokens = 0
        self.is_orchestrator_timeout = False
        self.timeout_reason = None
        
        log_orchestrator_activity(
            self.orchestrator_id,
            "Starting coordination with timeout",
            {
                "timeout_seconds": self.config.timeout_config.orchestrator_timeout_seconds,
                "agents": list(self.agents.keys())
            }
        )

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
                        self.total_tokens += len(
                            chunk.content.split()
                        )  # Rough token estimation

                    yield chunk

        except asyncio.TimeoutError:
            self.is_orchestrator_timeout = True
            elapsed = time.time() - self.coordination_start_time
            self.timeout_reason = (
                f"Time limit exceeded ({elapsed:.1f}s/{timeout_seconds}s)"
            )
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

    async def _coordinate_agents(
        self, conversation_context: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[StreamChunk, None]:
        """Execute unified MassGen coordination workflow with real-time streaming."""
        log_coordination_step(
            "Starting multi-agent coordination",
            {"agents": list(self.agents.keys()), "has_context": conversation_context is not None}
        )
        log_stream_chunk("orchestrator", "content", "🚀 Starting multi-agent coordination...\n\n", self.orchestrator_id)
        yield StreamChunk(
            type="content",
            content="🚀 Starting multi-agent coordination...\n\n",
            source=self.orchestrator_id,
        )

        votes = {}  # Track votes: voter_id -> {"agent_id": voted_for, "reason": reason}

        # Initialize all agents with has_voted = False and set restart flags
        for agent_id in self.agents.keys():
            self.agent_states[agent_id].has_voted = False
            self.agent_states[agent_id].restart_pending = True

        log_stream_chunk("orchestrator", "content", "## 📋 Agents Coordinating\n", self.orchestrator_id)
        yield StreamChunk(
            type="content",
            content="## 📋 Agents Coordinating\n",
            source=self.orchestrator_id,
        )

        # Start streaming coordination with real-time agent output
        async for chunk in self._stream_coordination_with_agents(
            votes, conversation_context
        ):
            yield chunk

        # Determine final agent based on votes
        current_answers = {
            aid: state.answer
            for aid, state in self.agent_states.items()
            if state.answer
        }
        self._selected_agent = self._determine_final_agent_from_votes(
            votes, current_answers
        )
        
        log_coordination_step(
            "Final agent selected",
            {"selected_agent": self._selected_agent, "votes": votes}
        )
        
        # Present final answer
        async for chunk in self._present_final_answer():
            yield chunk

        # Save coordination logs using the coordination tracker
        log_dir = get_log_session_dir()
        
        # End the coordination session
        self.coordination_tracker._end_session()
        
        self.coordination_tracker.save_coordination_logs(log_dir)

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
            current_answers = {
                aid: state.answer
                for aid, state in self.agent_states.items()
                if state.answer
            }
            for agent_id in self.agents.keys():
                if (
                    agent_id not in active_streams
                    and not self.agent_states[agent_id].has_voted
                    and not self.agent_states[agent_id].is_killed
                ):
                    active_streams[agent_id] = self._stream_agent_execution(
                        agent_id,
                        self.current_task,
                        current_answers,
                        conversation_context,
                    )

            if not active_streams:
                break

            # Create tasks only for streams that don't already have active tasks
            for agent_id, stream in active_streams.items():
                if agent_id not in active_tasks:
                    active_tasks[agent_id] = asyncio.create_task(
                        self._get_next_chunk(stream)
                    )

            if not active_tasks:
                break

            done, _ = await asyncio.wait(
                active_tasks.values(), return_when=asyncio.FIRST_COMPLETED
            )

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
                        yield StreamChunk(
                            type="content", content=chunk_data, source=agent_id
                        )

                    elif chunk_type == "reasoning":
                        # Stream reasoning content with proper attribution
                        log_stream_chunk("orchestrator", "reasoning", chunk_data, agent_id)
                        yield chunk_data  # chunk_data is already a StreamChunk with source

                    elif chunk_type == "result":
                        # Agent completed with result
                        result_type, result_data = chunk_data
                        # Result ends the agent's current stream
                        completed_agent_ids.add(agent_id)
                        log_stream_chunk("orchestrator", f"result.{result_type}", result_data, agent_id)

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
                            # Save snapshot (of workspace and answer) when agent provides new answer
                            await self._save_agent_snapshot(agent_id, answer_content=result_data)
                            if agent and agent.backend.filesystem_manager:
                                agent.backend.filesystem_manager.log_current_state("after providing answer")
                            # Always record answers, even from restarting agents (orchestrator accepts them)
                            
                            answered_agents[agent_id] = result_data
                            self.coordination_tracker.add_agent_answer(agent_id, result_data)
                            reset_signal = True
                            
                            # Track new answer event
                            log_stream_chunk("orchestrator", "content", "✅ Answer provided\n", agent_id)
                            yield StreamChunk(
                                type="content",
                                content=f"✅ Answer provided\n",
                                source=agent_id,
                            )

                        elif result_type == "vote":
                            # Agent voted for existing answer
                            # Ignore votes from agents with restart pending (votes are about current state)
                            if self.agent_states[agent_id].restart_pending:
                                voted_for = result_data.get("agent_id", "<unknown>")
                                reason = result_data.get("reason", "No reason provided")
                                # Track the ignored vote action
                                self.coordination_tracker.track_agent_action(agent_id, ActionType.VOTE_IGNORED, 
                                    f"Voted for {voted_for} but ignored due to restart")
                                # Save in coordination tracker that we waste a vote due to restart
                                log_stream_chunk("orchestrator", "content", f"🔄 Vote for [{voted_for}] ignored (reason: {reason}) - restarting due to new answers", agent_id)
                                yield StreamChunk(
                                    type="content",
                                    content=f"🔄 Vote for [{voted_for}] ignored (reason: {reason}) - restarting due to new answers",
                                    source=agent_id,
                                )
                                # yield StreamChunk(type="content", content="🔄 Vote ignored - restarting due to new answers", source=agent_id)
                            else:
                                # Log workspaces for current agent
                                agent = self.agents.get(agent_id)
                                if agent and agent.backend.filesystem_manager:
                                    self.agents.get(agent_id).backend.filesystem_manager.log_current_state("after voting")
                                voted_agents[agent_id] = result_data
                                self.coordination_tracker.add_agent_vote(agent_id, result_data)
                                # Track new vote event
                                voted_for = result_data.get("agent_id", "<unknown>")
                                reason = result_data.get("reason", "No reason provided")
                                log_stream_chunk("orchestrator", "content", f"✅ Vote recorded for [{result_data['agent_id']}]", agent_id)
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
                        yield StreamChunk(
                            type="content", content=f"❌ {chunk_data}", source=agent_id
                        )
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
                        yield StreamChunk(
                            type="debug", content=chunk_data, source=agent_id
                        )

                    elif chunk_type == "mcp_status":
                        # MCP status messages - forward with proper formatting
                        mcp_message = f"🔧 MCP: {chunk_data}"
                        log_stream_chunk("orchestrator", "mcp_status", chunk_data, agent_id)
                        yield StreamChunk(
                            type="content", content=mcp_message, source=agent_id
                        )

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
                restart_triggered_id = agent_id  # Last agent to provide new answer
                # Signal ALL agents to gracefully restart
                for agent_id in self.agent_states.keys():
                    self.agent_states[agent_id].restart_pending = True
                # Track restart signals
                self.coordination_tracker.track_restart_signal(restart_triggered_id, list(self.agent_states.keys()))
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
                self.coordination_tracker.track_agent_action(agent_id, ActionType.CANCELLED, "All agents voted - coordination complete")
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
    
    async def _save_agent_snapshot(self, agent_id: str, answer_content: str = None, is_final: bool = False) -> None:
        """
        Save a snapshot of an agent's working directory and answer with the same timestamp.
        
        Creates a timestamped directory structure:
        - agent_id/timestamp/workspace/ - Contains the workspace files
        - agent_id/timestamp/answer.txt - Contains the answer text
        
        Args:
            agent_id: ID of the agent
            answer_content: The answer content to save (if provided)
            is_final: If True, save as final snapshot for presentation
        """
        from datetime import datetime
        
        logger.info(f"[Orchestrator._save_agent_snapshot] Called for agent_id={agent_id}, has_answer={bool(answer_content)}, is_final={is_final}")
        
        agent = self.agents.get(agent_id)
        if not agent:
            logger.warning(f"[Orchestrator._save_agent_snapshot] Agent {agent_id} not found in agents dict")
            return
        
        # Generate single timestamp for both answer and workspace
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        
        # Save answer if provided
        if answer_content:
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
                    
                    # Write the answer content
                    answer_file.write_text(answer_content)
                    logger.info(f"[Orchestrator._save_agent_snapshot] Saved answer to {answer_file}")
            except Exception as e:
                logger.warning(f"[Orchestrator._save_agent_snapshot] Failed to save answer for {agent_id}: {e}")
        
        # Save workspace snapshot with the same timestamp
        if agent.backend.filesystem_manager:
            logger.info(f"[Orchestrator._save_agent_snapshot] Agent {agent_id} has filesystem_manager, calling save_snapshot with timestamp={timestamp if not is_final else None}")
            await agent.backend.filesystem_manager.save_snapshot(timestamp=timestamp if not is_final else None, is_final=is_final)
        else:
            logger.info(f"[Orchestrator._save_agent_snapshot] Agent {agent_id} does not have filesystem_manager")
    
    async def _close_agent_stream(
        self, agent_id: str, active_streams: Dict[str, AsyncGenerator]
    ) -> None:
        """Close and remove an agent stream safely."""
        if agent_id in active_streams:
            try:
                await active_streams[agent_id].aclose()
            except:
                pass  # Ignore cleanup errors
            del active_streams[agent_id]

    def _check_restart_pending(self, agent_id: str) -> bool:
        """Check if agent should restart and yield restart message if needed. This is only called to exit out of _stream_agent_execution()."""
        restart_pending = self.agent_states[agent_id].restart_pending
        # if restart_pending:
        #     self.coordination_tracker.agent_restarted(agent_id)
        return restart_pending

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
                logger.debug(f"[Orchestrator._normalize_workspace_paths_in_answers] Replacing {other_workspace} in answer from {agent_id} with path {replace_path}. original answer: {normalized_answer}")
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
        for agent_id, agent in self.agents.items():
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
        error_result_msg = agent.backend.create_tool_result_message(
            first_tool_call, primary_error_msg
        )
        enforcement_msgs.append(error_result_msg)

        # Send secondary error messages for any additional tool calls (API requires response to ALL calls)
        for additional_tool_call in tool_calls[1:]:
            neutral_msg = agent.backend.create_tool_result_message(
                additional_tool_call, secondary_error_msg
            )
            enforcement_msgs.append(neutral_msg)

        return enforcement_msgs

    async def _stream_agent_execution(
        self,
        agent_id: str,
        task: str,
        answers: Dict[str, str],
        conversation_context: Optional[Dict[str, Any]] = None,
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
        if hasattr(agent, 'backend') and hasattr(agent.backend, 'get_provider_name'):
            backend_name = agent.backend.get_provider_name()
        
        log_orchestrator_activity(
            self.orchestrator_id,
            f"Starting agent execution: {agent_id}",
            {
                "agent_id": agent_id,
                "backend": backend_name,
                "task": task if task else None,  # Full task for debug logging
                "has_answers": bool(answers),
                "num_answers": len(answers) if answers else 0
            }
        )
        
        # Initialize agent state
        self.agent_states[agent_id].is_killed = False
        self.agent_states[agent_id].timeout_reason = None

        # Clear restart pending flag at the beginning of agent execution
        self.agent_states[agent_id].restart_pending = False

        # Copy all agents' snapshots to temp workspace for context sharing
        workspace_path = await self._copy_all_snapshots_to_temp_workspace(agent_id)

        # Log workspace state before agent starts
        if agent.backend.filesystem_manager:
            agent.backend.filesystem_manager.log_current_state("before execution")

        try:
            # Get agent's custom system message if available
            agent_system_message = agent.get_configurable_system_message()

            # Append filesystem system message, if applicable
            if agent.backend.filesystem_manager:
                main_workspace = str(agent.backend.filesystem_manager.get_current_workspace())
                temp_workspace = str(agent.backend.filesystem_manager.agent_temporary_workspace) if agent.backend.filesystem_manager.agent_temporary_workspace else None
                filesystem_system_message = self.message_templates.filesystem_system_message(
                    main_workspace=main_workspace,
                    temp_workspace=temp_workspace
                )
                agent_system_message = f"{agent_system_message}\n\n{filesystem_system_message}" if agent_system_message else filesystem_system_message
            
            # Normalize workspace paths in agent answers for better comparison from this agent's perspective
            normalized_answers = self._normalize_workspace_paths_in_answers(answers, agent_id) if answers else answers
            
            # Log the normalized answers this agent will see
            if normalized_answers:
                logger.info(f"[Orchestrator] Agent {agent_id} sees normalized answers: {normalized_answers}")
            else:
                logger.info(f"[Orchestrator] Agent {agent_id} sees no existing answers")
            
            # Build conversation with context support
            if conversation_context and conversation_context.get(
                "conversation_history"
            ):
                # Use conversation context-aware building
                conversation = self.message_templates.build_conversation_with_context(
                    current_task=task,
                    conversation_history=conversation_context.get(
                        "conversation_history", []
                    ),
                    agent_summaries=normalized_answers,
                    valid_agent_ids=list(normalized_answers.keys()) if normalized_answers else None,
                    base_system_message=agent_system_message,
                )
            else:
                # Fallback to standard conversation building
                conversation = self.message_templates.build_initial_conversation(
                    task=task,
                    agent_summaries=normalized_answers,
                    valid_agent_ids=list(normalized_answers.keys()) if normalized_answers else None,
                    base_system_message=agent_system_message,
                )

            # Track the context used for this agent execution
            self.coordination_tracker.track_agent_context(agent_id, answers, conversation.get("conversation_history", []))
            
            # Log the messages being sent to the agent with backend info
            backend_name = None
            if hasattr(agent, 'backend') and hasattr(agent.backend, 'get_provider_name'):
                backend_name = agent.backend.get_provider_name()
            
            log_orchestrator_agent_message(
                agent_id,
                "SEND",
                {"system": conversation["system_message"], "user": conversation["user_message"]},
                backend_name=backend_name
            )

            # Clean startup without redundant messages

            # Build proper conversation messages with system + user messages
            max_attempts = 3
            conversation_messages = [
                {"role": "system", "content": conversation["system_message"]},
                {"role": "user", "content": conversation["user_message"]},
            ]
            enforcement_msg = self.message_templates.enforcement_message()

            # Update agent status to STREAMING
            self.coordination_tracker.change_status(agent_id, AgentStatus.STREAMING)

            for attempt in range(max_attempts):
                logger.info(f"[Orchestrator] Agent {agent_id} attempt {attempt + 1}/{max_attempts}")
                
                if self._check_restart_pending(agent_id):
                    logger.info(f"[Orchestrator] Agent {agent_id} restarting due to restart_pending flag")
                    # yield ("content", "🔄 Gracefully restarting due to new answers from other agents")
                    yield (
                        "content",
                        f"🔁 [{agent_id}] gracefully restarting due to new answer detected\n",
                    )
                    yield ("done", None)
                    return

                # Stream agent response with workflow tools
                if attempt == 0:
                    # First attempt: orchestrator provides initial conversation
                    # But we need the agent to have this in its history for subsequent calls
                    # First attempt: provide complete conversation and reset agent's history
                    chat_stream = agent.chat(
                        conversation_messages, self.workflow_tools, reset_chat=True
                    )
                else:
                    # Subsequent attempts: send enforcement message (set by error handling)

                    if isinstance(enforcement_msg, list):
                        # Tool message array
                        chat_stream = agent.chat(
                            enforcement_msg, self.workflow_tools, reset_chat=False
                        )
                    else:
                        # Single user message
                        enforcement_message = {
                            "role": "user",
                            "content": enforcement_msg,
                        }
                        chat_stream = agent.chat(
                            [enforcement_message], self.workflow_tools, reset_chat=False
                        )
                response_text = ""
                tool_calls = []
                workflow_tool_found = False
                
                logger.info(f"[Orchestrator] Agent {agent_id} starting to stream chat response...")

                async for chunk in chat_stream:
                    if chunk.type == "content":
                        response_text += chunk.content
                        # Stream agent content directly - source field handles attribution
                        yield ("content", chunk.content)
                        # Log received content
                        backend_name = None
                        if hasattr(agent, 'backend') and hasattr(agent.backend, 'get_provider_name'):
                            backend_name = agent.backend.get_provider_name()
                        log_orchestrator_agent_message(agent_id, "RECV", {"content": chunk.content}, backend_name=backend_name)
                    elif chunk.type in [
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
                            reasoning_summary_delta=getattr(
                                chunk, "reasoning_summary_delta", None
                            ),
                            reasoning_summary_text=getattr(
                                chunk, "reasoning_summary_text", None
                            ),
                            item_id=getattr(chunk, "item_id", None),
                            content_index=getattr(chunk, "content_index", None),
                            summary_index=getattr(chunk, "summary_index", None),
                        )
                        yield ("reasoning", reasoning_chunk)
                    elif chunk.type == "backend_status":
                        pass
                    elif chunk.type == "mcp_status":
                        # Forward MCP status messages with proper formatting
                        mcp_content = f"🔧 MCP: {chunk.content}"
                        yield ("content", mcp_content)
                    elif chunk.type == "debug":
                        # Forward debug chunks
                        yield ("debug", chunk.content)
                    elif chunk.type == "tool_calls":
                        # Use the correct tool_calls field
                        chunk_tool_calls = getattr(chunk, "tool_calls", []) or []
                        tool_calls.extend(chunk_tool_calls)
                        # Stream tool calls to show agent actions
                        # Get backend name for logging
                        backend_name = None
                        if hasattr(agent, 'backend') and hasattr(agent.backend, 'get_provider_name'):
                            backend_name = agent.backend.get_provider_name()
                        
                        for tool_call in chunk_tool_calls:
                            tool_name = agent.backend.extract_tool_name(tool_call)
                            tool_args = agent.backend.extract_tool_arguments(tool_call)

                            if tool_name == "new_answer":
                                content = tool_args.get("content", "")
                                yield ("content", f'💡 Providing answer: "{content}"')
                                log_tool_call(agent_id, "new_answer", {"content": content}, None, backend_name)  # Full content for debug logging
                            elif tool_name == "vote":
                                agent_voted_for = tool_args.get("agent_id", "")
                                reason = tool_args.get("reason", "")
                                log_tool_call(agent_id, "vote", {"agent_id": agent_voted_for, "reason": reason}, None, backend_name)  # Full reason for debug logging

                                # Convert anonymous agent ID to real agent ID for display
                                real_agent_id = agent_voted_for
                                if answers:  # Only do mapping if answers exist
                                    agent_mapping = {}
                                    for i, real_id in enumerate(
                                        sorted(answers.keys()), 1
                                    ):
                                        agent_mapping[f"agent{i}"] = real_id
                                    real_agent_id = agent_mapping.get(
                                        agent_voted_for, agent_voted_for
                                    )

                                yield (
                                    "content",
                                    f"🗳️ Voting for [{real_agent_id}] (options: {', '.join(sorted(answers.keys()))}) : {reason}",
                                )
                            else:
                                yield ("content", f"🔧 Using {tool_name}")
                                log_tool_call(agent_id, tool_name, tool_args, None, backend_name)
                    elif chunk.type == "error":
                        # Stream error information to user interface
                        error_msg = (
                            getattr(chunk, "error", str(chunk.content))
                            if hasattr(chunk, "error")
                            else str(chunk.content)
                        )
                        yield ("content", f"❌ Error: {error_msg}\n")

                # Check for multiple vote calls before processing
                vote_calls = [
                    tc
                    for tc in tool_calls
                    if agent.backend.extract_tool_name(tc) == "vote"
                ]
                if len(vote_calls) > 1:
                    if attempt < max_attempts - 1:
                        if self._check_restart_pending(agent_id):
                            yield (
                                "content",
                                f"🔁 [{agent_id}] gracefully restarting due to new answer detected\n",
                            )
                            yield ("done", None)
                            return
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
                new_answer_calls = [
                    tc
                    for tc in tool_calls
                    if agent.backend.extract_tool_name(tc) == "new_answer"
                ]
                if len(vote_calls) > 0 and len(new_answer_calls) > 0:
                    if attempt < max_attempts - 1:
                        if self._check_restart_pending(agent_id):
                            yield (
                                "content",
                                f"🔁 [{agent_id}] gracefully restarting due to new answer detected\n",
                            )
                            yield ("done", None)
                            return
                        error_msg = "Cannot use both 'vote' and 'new_answer' in same response. Choose one: vote for existing answer OR provide new answer."
                        yield ("content", f"❌ {error_msg}")

                        # Send tool error response for all tool calls that caused the violation
                        enforcement_msg = self._create_tool_error_messages(
                            agent, tool_calls, error_msg
                        )
                        continue  # Retry this attempt
                    else:
                        yield (
                            "error",
                            f"Agent used both vote and new_answer tools in single response after max attempts",
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
                            if self.agent_states[agent_id].restart_pending:
                                yield (
                                    "content",
                                    f"🔄 [{agent_id}] Vote invalid - restarting due to new answers",
                                )
                                yield ("done", None)
                                return

                            workflow_tool_found = True
                            # Vote for existing answer (requires existing answers)
                            if not answers:
                                # Invalid - can't vote when no answers exist
                                if attempt < max_attempts - 1:
                                    if self._check_restart_pending(agent_id):
                                        yield (
                                            "content",
                                            f"🔁 [{agent_id}] gracefully restarting due to new answer detected\n",
                                        )
                                        yield ("done", None)
                                        return
                                    error_msg = "Cannot vote when no answers exist. Use new_answer tool."
                                    yield ("content", f"❌ {error_msg}")
                                    # Create proper tool error message for retry
                                    enforcement_msg = self._create_tool_error_messages(
                                        agent, [tool_call], error_msg
                                    )
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
                            for i, real_agent_id in enumerate(
                                sorted(answers.keys()), 1
                            ):
                                agent_mapping[f"agent{i}"] = real_agent_id

                            voted_agent = agent_mapping.get(
                                voted_agent_anon, voted_agent_anon
                            )

                            # Handle invalid agent_id
                            if voted_agent not in answers:
                                if attempt < max_attempts - 1:
                                    if self._check_restart_pending(agent_id):
                                        yield (
                                            "content",
                                            f"🔁 [{agent_id}] gracefully restarting due to new answer detected\n",
                                        )
                                        yield ("done", None)
                                        return
                                    # Create reverse mapping for error message
                                    reverse_mapping = {
                                        real_id: f"agent{i}"
                                        for i, real_id in enumerate(
                                            sorted(answers.keys()), 1
                                        )
                                    }
                                    valid_anon_agents = [
                                        reverse_mapping[real_id]
                                        for real_id in answers.keys()
                                    ]
                                    error_msg = f"Invalid agent_id '{voted_agent_anon}'. Valid agents: {', '.join(valid_anon_agents)}"
                                    # Send tool error result back to agent
                                    yield ("content", f"❌ {error_msg}")
                                    # Create proper tool error message for retry
                                    enforcement_msg = self._create_tool_error_messages(
                                        agent, [tool_call], error_msg
                                    )
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

                            # Check for duplicate answer
                            # Normalize both new content and existing content to neutral paths for comparison
                            normalized_new_content = self._normalize_workspace_paths_for_comparison(content)
                            
                            for existing_agent_id, existing_content in answers.items():
                                normalized_existing_content = self._normalize_workspace_paths_for_comparison(existing_content)
                                if normalized_new_content.strip() == normalized_existing_content.strip():
                                    if attempt < max_attempts - 1:
                                        if self._check_restart_pending(agent_id):
                                            yield (
                                                "content",
                                                f"🔁 [{agent_id}] gracefully restarting due to new answer detected\n",
                                            )
                                            yield ("done", None)
                                            return
                                        error_msg = f"Answer already provided by {existing_agent_id}. Provide different answer or vote for existing one."
                                        yield ("content", f"❌ {error_msg}")
                                        # Create proper tool error message for retry
                                        enforcement_msg = (
                                            self._create_tool_error_messages(
                                                agent, [tool_call], error_msg
                                            )
                                        )
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
                            yield ("result", ("answer", content))
                            yield ("done", None)
                            return

                        else:
                            # Non-workflow tools not yet implemented
                            yield (
                                "content",
                                f"🔧 used {tool_name} tool (not implemented)",
                            )

                # Case 3: Non-workflow response, need enforcement (only if no workflow tool was found)
                if not workflow_tool_found:
                    if self._check_restart_pending(agent_id):
                        yield (
                            "content",
                            f"🔁 [{agent_id}] gracefully restarting due to new answer detected\n",
                        )
                        yield ("done", None)
                        return
                    if attempt < max_attempts - 1:
                        yield ("content", f"🔄 needs to use workflow tools...\n")
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
        """Present the final coordinated answer."""
        # Always start final round tracking
        self.coordination_tracker.start_final_round(self._selected_agent)
        
        log_stream_chunk("orchestrator", "content", "## 🎯 Final Coordinated Answer\n")
        yield StreamChunk(type="content", content="## 🎯 Final Coordinated Answer\n")

        # Select the best agent based on current state
        if not self._selected_agent:
            self._selected_agent = self._determine_final_agent_from_states()
            if self._selected_agent:
                log_stream_chunk("orchestrator", "content", f"🏆 Selected Agent: {self._selected_agent}\n")
                yield StreamChunk(
                    type="content",
                    content=f"🏆 Selected Agent: {self._selected_agent}\n",
                )

        if (
            self._selected_agent
            and self._selected_agent in self.agent_states
            and self.agent_states[self._selected_agent].answer
        ):
            final_answer = self.agent_states[self._selected_agent].answer  # NOTE: This is the raw answer from the winning agent, not the actual final answer.

            # Track iterations during final answer presentation (even for stored answers)
            self.coordination_tracker.start_new_iteration()  # Iteration for winner selection
            
            # Track final answer and set winner
            self.coordination_tracker.set_final_answer(self._selected_agent, final_answer)
            
            # Mark final presentation as completed
            self.coordination_tracker.change_status(self._selected_agent, AgentStatus.COMPLETED)

            # Add to conversation history
            self.add_to_history("assistant", final_answer)

            log_stream_chunk("orchestrator", "content", f"🏆 Selected Agent: {self._selected_agent}\n")
            yield StreamChunk(
                type="content", content=f"🏆 Selected Agent: {self._selected_agent}\n"
            )
            log_stream_chunk("orchestrator", "content", final_answer)
            yield StreamChunk(type="content", content=final_answer)
            log_stream_chunk("orchestrator", "content", f"\n\n---\n*Coordinated by {len(self.agents)} agents via MassGen framework*")
            yield StreamChunk(
                type="content",
                content=f"\n\n---\n*Coordinated by {len(self.agents)} agents via MassGen framework*",
            )
        else:
            error_msg = "❌ Unable to provide coordinated answer - no successful agents"
            self.add_to_history("assistant", error_msg)
            log_stream_chunk("orchestrator", "error", error_msg)
            yield StreamChunk(type="content", content=error_msg)

        # Update workflow phase
        self.workflow_phase = "presenting"
        log_stream_chunk("orchestrator", "done", None)
        yield StreamChunk(type="done")

    async def _handle_orchestrator_timeout(self) -> AsyncGenerator[StreamChunk, None]:
        """Handle orchestrator timeout by jumping directly to get_final_presentation."""
        # Output orchestrator timeout message first
        log_stream_chunk("orchestrator", "content", f"\n⚠️ **Orchestrator Timeout**: {self.timeout_reason}\n", self.orchestrator_id)
        yield StreamChunk(
            type="content",
            content=f"\n⚠️ **Orchestrator Timeout**: {self.timeout_reason}\n",
            source=self.orchestrator_id,
        )

        # Count available answers
        available_answers = {
            aid: state.answer
            for aid, state in self.agent_states.items()
            if state.answer and not state.is_killed
        }

        log_stream_chunk("orchestrator", "content", f"📊 Current state: {len(available_answers)} answers available\n", self.orchestrator_id)
        yield StreamChunk(
            type="content",
            content=f"📊 Current state: {len(available_answers)} answers available\n",
            source=self.orchestrator_id,
        )

        # If no answers available, provide fallback with timeout explanation
        if len(available_answers) == 0:
            log_stream_chunk("orchestrator", "error", "❌ No answers available from any agents due to timeout. No agents had enough time to provide responses.\n", self.orchestrator_id)
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
        current_votes = {
            aid: state.votes
            for aid, state in self.agent_states.items()
            if state.votes and not state.is_killed
        }

        self._selected_agent = self._determine_final_agent_from_votes(
            current_votes, available_answers
        )

        # Jump directly to get_final_presentation
        vote_results = self._get_vote_results()
        log_stream_chunk("orchestrator", "content", f"🎯 Jumping to final presentation with {self._selected_agent} (selected despite timeout)\n", self.orchestrator_id)
        yield StreamChunk(
            type="content",
            content=f"🎯 Jumping to final presentation with {self._selected_agent} (selected despite timeout)\n",
            source=self.orchestrator_id,
        )

        async for chunk in self.get_final_presentation(
            self._selected_agent, vote_results
        ):
            yield chunk

    def _determine_final_agent_from_votes(
        self, votes: Dict[str, Dict], agent_answers: Dict[str, str]
    ) -> str:
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
        tied_agents = [
            agent_id for agent_id, count in vote_counts.items() if count == max_votes
        ]

        # Break ties by agent registration order (order in agent_states dict)
        for agent_id in agent_answers.keys():
            if agent_id in tied_agents:
                return agent_id

        # Fallback to first tied agent
        return (
            tied_agents[0]
            if tied_agents
            else next(iter(agent_answers))
            if agent_answers
            else None
        )

    async def get_final_presentation(
        self, selected_agent_id: str, vote_results: Dict[str, Any]
    ) -> AsyncGenerator[StreamChunk, None]:
        """Ask the winning agent to present their final answer with voting context."""
        # Debug: Track that we entered final presentation
        self.coordination_tracker._add_event("debug", None, f"get_final_presentation called for {selected_agent_id}")
        
        # Start tracking the final round
        self.coordination_tracker.start_final_round(selected_agent_id)
        
        if selected_agent_id not in self.agents:
            log_stream_chunk("orchestrator", "error", f"Selected agent {selected_agent_id} not found")
            yield StreamChunk(
                type="error", error=f"Selected agent {selected_agent_id} not found"
            )
            return

        agent = self.agents[selected_agent_id]
        
        # Copy all agents' snapshots to temp workspace to preserve context from coordination phase
        # This allows the agent to reference and access previous work
        temp_workspace_path = await self._copy_all_snapshots_to_temp_workspace(selected_agent_id)
        yield StreamChunk(
            type="debug",
            content=f"Restored workspace context for final presentation: {temp_workspace_path}",
            source=selected_agent_id
        )

        # Prepare context about the voting
        vote_counts = vote_results.get("vote_counts", {})
        voter_details = vote_results.get("voter_details", {})
        is_tie = vote_results.get("is_tie", False)

        # Build voting summary
        voting_summary = f"You received {vote_counts.get(selected_agent_id, 0)} vote(s)"
        if voter_details.get(selected_agent_id):
            reasons = [v["reason"] for v in voter_details[selected_agent_id]]
            voting_summary += f" with feedback: {'; '.join(reasons)}"

        if is_tie:
            voting_summary += " (tie-broken by registration order)"

        # Get all answers for context
        all_answers = {
            aid: s.answer for aid, s in self.agent_states.items() if s.answer
        }

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
        
        # Build system message with workspace context if available
        base_system_message = self.message_templates.final_presentation_system_message(
            agent_system_message
        )

        # Change the status of all agents that were not selected to AgentStatus.COMPLETED
        for aid, state in self.agent_states.items():
            if aid != selected_agent_id:
                self.coordination_tracker.change_status(aid, AgentStatus.COMPLETED)
        self.coordination_tracker.set_final_agent(selected_agent_id, voting_summary, all_answers)
        
        # Add workspace context information to system message if workspace was restored
        if agent.backend.filesystem_manager and temp_workspace_path:
            main_workspace = str(agent.backend.filesystem_manager.get_current_workspace())
            temp_workspace = str(agent.backend.filesystem_manager.agent_temporary_workspace) if agent.backend.filesystem_manager.agent_temporary_workspace else None
            base_system_message += "\n\n" + self.message_templates.filesystem_system_message(
                main_workspace=main_workspace,
                temp_workspace=temp_workspace
            )
            # Add special note that we must not just cite answers from the temp workspace but instead create a synthesized final answer
            base_system_message += "\n\nNote: When presenting the final answer, it is not sufficient to just read from existing temporary workspace files. Instead, you must write to your main workspace so that everything needed for the final answer is contained in your main workspace. This ensures the final answer is complete and self-contained."
        
        # Create conversation with system and user messages
        presentation_messages = [
            {
                "role": "system",
                "content": base_system_message,
            },
            {"role": "user", "content": presentation_content},
        ]
        log_stream_chunk("orchestrator", "status", f"🎤  [{selected_agent_id}] presenting final answer\n")
        yield StreamChunk(
            type="status",
            content=f"🎤  [{selected_agent_id}] presenting final answer\n",
        )

        # Use agent's chat method with proper system message (reset chat for clean presentation)
        presentation_content = ""
        
        # Track final round iterations (each chunk is like an iteration)
        async for chunk in agent.chat(presentation_messages, reset_chat=True):
            # Start new iteration for this chunk
            self.coordination_tracker.start_new_iteration()
            # Use the same streaming approach as regular coordination
            if chunk.type == "content" and chunk.content:
                presentation_content += chunk.content
                log_stream_chunk("orchestrator", "content", chunk.content, selected_agent_id)
                yield StreamChunk(
                    type="content", content=chunk.content, source=selected_agent_id
                )
            elif chunk.type in [
                "reasoning",
                "reasoning_done",
                "reasoning_summary",
                "reasoning_summary_done",
            ]:
                # Stream reasoning content with proper attribution (same as main coordination)
                reasoning_chunk = StreamChunk(
                    type=chunk.type,
                    content=chunk.content,
                    source=selected_agent_id,
                    reasoning_delta=getattr(chunk, "reasoning_delta", None),
                    reasoning_text=getattr(chunk, "reasoning_text", None),
                    reasoning_summary_delta=getattr(
                        chunk, "reasoning_summary_delta", None
                    ),
                    reasoning_summary_text=getattr(
                        chunk, "reasoning_summary_text", None
                    ),
                    item_id=getattr(chunk, "item_id", None),
                    content_index=getattr(chunk, "content_index", None),
                    summary_index=getattr(chunk, "summary_index", None),
                )
                # Use the same format as main coordination for consistency
                log_stream_chunk("orchestrator", chunk.type, chunk.content, selected_agent_id)
                yield reasoning_chunk
            elif chunk.type == "backend_status":
                import json

                status_json = json.loads(chunk.content)
                cwd = status_json["cwd"]
                session_id = status_json["session_id"]
                content = f"""Final Temp Working directory: {cwd}.
Final Session ID: {session_id}.
"""

                log_stream_chunk("orchestrator", "content", content, selected_agent_id)
                yield StreamChunk(
                    type="content", content=content, source=selected_agent_id
                )
            elif chunk.type == "mcp_status":
                # Handle MCP status messages in final presentation
                mcp_content = f"🔧 MCP: {chunk.content}"
                log_stream_chunk("orchestrator", "content", mcp_content, selected_agent_id)
                yield StreamChunk(
                    type="content", content=mcp_content, source=selected_agent_id
                )

            elif chunk.type == "done":
                # Save the final workspace snapshot (from final workspace directory)
                final_answer = presentation_content.strip() if presentation_content.strip() else self.agent_states[selected_agent_id].answer  # fallback to stored answer if no content generated
                await self._save_agent_snapshot(self._selected_agent, answer_content=final_answer, is_final=True)
                log_stream_chunk("orchestrator", "done", None, selected_agent_id)
                yield StreamChunk(type="done", source=selected_agent_id)
            elif chunk.type == "error":
                log_stream_chunk("orchestrator", "error", chunk.error, selected_agent_id)
                yield StreamChunk(
                    type="error", error=chunk.error, source=selected_agent_id
                )
            # Pass through other chunk types as-is but with source
            else:
                if hasattr(chunk, "source"):
                    log_stream_chunk("orchestrator", chunk.type, getattr(chunk, "content", ""), selected_agent_id)
                    yield StreamChunk(
                        type=chunk.type,
                        content=getattr(chunk, "content", ""),
                        source=selected_agent_id,
                        **{
                            k: v
                            for k, v in chunk.__dict__.items()
                            if k not in ["type", "content", "source"]
                        },
                    )
                else:
                    log_stream_chunk("orchestrator", chunk.type, getattr(chunk, "content", ""), selected_agent_id)
                    yield StreamChunk(
                        type=chunk.type,
                        content=getattr(chunk, "content", ""),
                        source=selected_agent_id,
                        **{
                            k: v
                            for k, v in chunk.__dict__.items()
                            if k not in ["type", "content", "source"]
                        },
                    )

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
                log_stream_chunk("orchestrator", "error", "\n❌ No content generated for final presentation and no stored answer available.", selected_agent_id)
                yield StreamChunk(
                    type="content",
                    content="\n❌ No content generated for final presentation and no stored answer available.",
                    source=selected_agent_id,
                )
        
        # Mark final round as completed
        self.coordination_tracker.change_status(selected_agent_id, AgentStatus.COMPLETED)

    def _get_vote_results(self) -> Dict[str, Any]:
        """Get current vote results and statistics."""
        agent_answers = {
            aid: state.answer
            for aid, state in self.agent_states.items()
            if state.answer
        }
        votes = {
            aid: state.votes for aid, state in self.agent_states.items() if state.votes
        }

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
                    }
                )

        # Determine winner
        winner = None
        is_tie = False
        if vote_counts:
            max_votes = max(vote_counts.values())
            tied_agents = [
                agent_id
                for agent_id, count in vote_counts.items()
                if count == max_votes
            ]
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
        agents_with_answers = {
            aid: state.answer
            for aid, state in self.agent_states.items()
            if state.answer
        }

        if not agents_with_answers:
            return None

        # Return the first agent with an answer (by order in agent_states)
        return next(iter(agents_with_answers))

    async def _handle_followup(
        self, user_message: str, conversation_context: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[StreamChunk, None]:
        """Handle follow-up questions after presenting final answer with conversation context."""
        # For now, acknowledge with context awareness
        # Future: implement full re-coordination with follow-up context

        if (
            conversation_context
            and len(conversation_context.get("conversation_history", [])) > 0
        ):
            log_stream_chunk("orchestrator", "content", f"🤔 Thank you for your follow-up question in our ongoing conversation. I understand you're asking: '{user_message}'. Currently, the coordination is complete, but I can help clarify the answer or coordinate a new task that takes our conversation history into account.")
            yield StreamChunk(
                type="content",
                content=f"🤔 Thank you for your follow-up question in our ongoing conversation. I understand you're asking: '{user_message}'. Currently, the coordination is complete, but I can help clarify the answer or coordinate a new task that takes our conversation history into account.",
            )
        else:
            log_stream_chunk("orchestrator", "content", f"🤔 Thank you for your follow-up: '{user_message}'. The coordination is complete, but I can help clarify the answer or coordinate a new task if needed.")
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

    def get_status(self) -> Dict[str, Any]:
        """Get current orchestrator status."""
        # Calculate vote results
        vote_results = self._get_vote_results()

        return {
            "session_id": self.session_id,
            "workflow_phase": self.workflow_phase,
            "current_task": self.current_task,
            "selected_agent": self.coordination_tracker.final_winner if self.coordination_tracker else self._selected_agent,
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
        if self.config and hasattr(self.config, 'get_configurable_system_message'):
            return self.config.get_configurable_system_message()
        elif self.config and hasattr(self.config, 'custom_system_instruction'):
            return self.config.custom_system_instruction
        elif self.config and self.config.backend_params:
            # Check for backend-specific system prompts
            backend_params = self.config.backend_params
            if "system_prompt" in backend_params:
                return backend_params["system_prompt"]
            elif "append_system_prompt" in backend_params:
                return backend_params["append_system_prompt"]
        return None

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
