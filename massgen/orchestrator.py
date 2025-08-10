"""
MassGen Orchestrator Agent - Chat interface that manages sub-agents internally.

The orchestrator presents a unified chat interface to users while coordinating
multiple sub-agents using the proven binary decision framework behind the scenes.
"""

import asyncio
from typing import Dict, List, Optional, Any, AsyncGenerator
from dataclasses import dataclass, field
from .message_templates import MessageTemplates
from .agent_config import AgentConfig
from .backend.base import StreamChunk
from .chat_agent import ChatAgent


@dataclass
class AgentState:
    """Runtime state for an agent during coordination.

    Attributes:
        answer: The agent's current answer/summary, if any
        has_voted: Whether the agent has voted in the current round
        votes: Dictionary storing vote data for this agent
        restart_pending: Whether the agent should gracefully restart due to new answers
    """

    answer: Optional[str] = None
    has_voted: bool = False
    votes: Dict[str, Any] = field(default_factory=dict)
    restart_pending: bool = False


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
    ):
        """
        Initialize MassGen orchestrator.

        Args:
            agents: Dictionary of {agent_id: ChatAgent} - can be individual agents or other orchestrators
            orchestrator_id: Unique identifier for this orchestrator (default: "orchestrator")
            session_id: Optional session identifier
            config: Optional AgentConfig for customizing orchestrator behavior
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
            self.workflow_phase = "coordinating"

            async for chunk in self._coordinate_agents(conversation_context):
                yield chunk

        elif self.workflow_phase == "presenting":
            # Handle follow-up question with full conversation context
            async for chunk in self._handle_followup(
                user_message, conversation_context
            ):
                yield chunk
        else:
            # Already coordinating - provide status update
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

    async def _coordinate_agents(
        self, conversation_context: Optional[Dict[str, Any]] = None
    ) -> AsyncGenerator[StreamChunk, None]:
        """Execute unified MassGen coordination workflow with real-time streaming."""
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

        # Stream agent outputs in real-time until all have voted
        while not all(state.has_voted for state in self.agent_states.values()):
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

            # Process completed stream chunks
            for task in done:
                agent_id = next(aid for aid, t in active_tasks.items() if t is task)
                # Remove completed task from active_tasks
                del active_tasks[agent_id]

                try:
                    chunk_type, chunk_data = await task

                    if chunk_type == "content":
                        # Stream agent content in real-time with source info
                        yield StreamChunk(
                            type="content", content=chunk_data, source=agent_id
                        )

                    elif chunk_type == "reasoning":
                        # Stream reasoning content with proper attribution
                        yield chunk_data  # chunk_data is already a StreamChunk with source

                    elif chunk_type == "result":
                        # Agent completed with result
                        result_type, result_data = chunk_data

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
                            # Always record answers, even from restarting agents (orchestrator accepts them)
                            answered_agents[agent_id] = result_data
                            reset_signal = True
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
                                yield StreamChunk(
                                    type="content",
                                    content=f"🔄 Vote for [{voted_for}] ignored (reason: {reason}) - restarting due to new answers",
                                    source=agent_id,
                                )
                                # yield StreamChunk(type="content", content="🔄 Vote ignored - restarting due to new answers", source=agent_id)
                            else:
                                voted_agents[agent_id] = result_data
                                yield StreamChunk(
                                    type="content",
                                    content=f"✅ Vote recorded for [{result_data['agent_id']}]",
                                    source=agent_id,
                                )

                    elif chunk_type == "error":
                        # Agent error
                        yield StreamChunk(
                            type="content", content=f"❌ {chunk_data}", source=agent_id
                        )
                        # Emit agent completion status for errors too
                        yield StreamChunk(
                            type="agent_status",
                            source=agent_id,
                            status="completed",
                            content="",
                        )
                        await self._close_agent_stream(agent_id, active_streams)

                    elif chunk_type == "done":
                        # Stream completed - emit completion status for frontend
                        yield StreamChunk(
                            type="agent_status",
                            source=agent_id,
                            status="completed",
                            content="",
                        )
                        await self._close_agent_stream(agent_id, active_streams)

                except Exception as e:
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
                # Signal ALL agents to gracefully restart
                for agent_id in self.agent_states.keys():
                    self.agent_states[agent_id].restart_pending = True
            # Set has_voted = True for agents that voted (only if no reset signal)
            else:
                for agent_id, vote_data in voted_agents.items():
                    self.agent_states[agent_id].has_voted = True
                    votes[agent_id] = vote_data

            # Update answers for agents that provided them
            for agent_id, answer in answered_agents.items():
                self.agent_states[agent_id].answer = answer

        # Cancel any remaining tasks and close streams
        for task in active_tasks.values():
            task.cancel()
        for agent_id in list(active_streams.keys()):
            await self._close_agent_stream(agent_id, active_streams)

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
        """Check if agent should restart and yield restart message if needed."""
        return self.agent_states[agent_id].restart_pending

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

        # Clear restart pending flag at the beginning of agent execution
        self.agent_states[agent_id].restart_pending = False

        try:
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
                    agent_summaries=answers,
                    valid_agent_ids=list(answers.keys()) if answers else None,
                )
            else:
                # Fallback to standard conversation building
                conversation = self.message_templates.build_initial_conversation(
                    task=task,
                    agent_summaries=answers,
                    valid_agent_ids=list(answers.keys()) if answers else None,
                )

            # Clean startup without redundant messages

            # Build proper conversation messages with system + user messages
            max_attempts = 3
            conversation_messages = [
                {"role": "system", "content": conversation["system_message"]},
                {"role": "user", "content": conversation["user_message"]},
            ]
            enforcement_msg = self.message_templates.enforcement_message()

            for attempt in range(max_attempts):
                if self._check_restart_pending(agent_id):
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

                async for chunk in chat_stream:
                    if chunk.type == "content":
                        response_text += chunk.content
                        # Stream agent content directly - source field handles attribution
                        yield ("content", chunk.content)
                    elif chunk.type in ["reasoning", "reasoning_done", "reasoning_summary", "reasoning_summary_done"]:
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
                            summary_index=getattr(chunk, "summary_index", None)
                        )
                        yield ("reasoning", reasoning_chunk)
                    elif chunk.type == "backend_status":
                        pass
                    elif chunk.type == "tool_calls":
                        # Use the correct tool_calls field
                        chunk_tool_calls = getattr(chunk, "tool_calls", []) or []
                        tool_calls.extend(chunk_tool_calls)
                        # Stream tool calls to show agent actions
                        for tool_call in chunk_tool_calls:
                            tool_name = agent.backend.extract_tool_name(tool_call)
                            tool_args = agent.backend.extract_tool_arguments(tool_call)

                            if tool_name == "new_answer":
                                content = tool_args.get("content", "")
                                yield ("content", f'💡 Providing answer: "{content}"')
                            elif tool_name == "vote":
                                agent_voted_for = tool_args.get("agent_id", "")
                                reason = tool_args.get("reason", "")

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
                                    f"🗳️ Voting for [{real_agent_id}]: {reason}",
                                )
                            else:
                                yield ("content", f"🔧 Using {tool_name}")
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
                            for existing_agent_id, existing_content in answers.items():
                                if content.strip() == existing_content.strip():
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
        yield StreamChunk(type="content", content="## 🎯 Final Coordinated Answer\n")

        # Select the best agent based on current state
        if not self._selected_agent:
            self._selected_agent = self._determine_final_agent_from_states()
            if self._selected_agent:
                yield StreamChunk(
                    type="content",
                    content=f"🏆 Selected Agent: {self._selected_agent}\n",
                )

        if (
            self._selected_agent
            and self._selected_agent in self.agent_states
            and self.agent_states[self._selected_agent].answer
        ):
            final_answer = self.agent_states[self._selected_agent].answer

            # Add to conversation history
            self.add_to_history("assistant", final_answer)

            yield StreamChunk(
                type="content", content=f"🏆 Selected Agent: {self._selected_agent}\n"
            )
            yield StreamChunk(type="content", content=final_answer)
            yield StreamChunk(
                type="content",
                content=f"\n\n---\n*Coordinated by {len(self.agents)} agents via MassGen framework*",
            )
        else:
            error_msg = "❌ Unable to provide coordinated answer - no successful agents"
            self.add_to_history("assistant", error_msg)
            yield StreamChunk(type="content", content=error_msg)

        # Update workflow phase
        self.workflow_phase = "presenting"
        yield StreamChunk(type="done")

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
            else next(iter(agent_answers)) if agent_answers else None
        )

    async def get_final_presentation(
        self, selected_agent_id: str, vote_results: Dict[str, Any]
    ) -> AsyncGenerator[StreamChunk, None]:
        """Ask the winning agent to present their final answer with voting context."""
        if selected_agent_id not in self.agents:
            yield StreamChunk(
                type="error", error=f"Selected agent {selected_agent_id} not found"
            )
            return

        agent = self.agents[selected_agent_id]

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

        # Use MessageTemplates to build the presentation message
        presentation_content = self.message_templates.build_final_presentation_message(
            original_task=self.current_task or "Task coordination",
            vote_summary=voting_summary,
            all_answers=all_answers,
            selected_agent_id=selected_agent_id,
        )

        # Get agent's original system message if available
        agent_system_message = getattr(agent, "system_message", None)
        # Create conversation with system and user messages
        presentation_messages = [
            {
                "role": "system",
                "content": self.message_templates.final_presentation_system_message(
                    agent_system_message
                ),
            },
            {"role": "user", "content": presentation_content},
        ]
        yield StreamChunk(
            type="status",
            content=f"🎤  [{selected_agent_id}] presenting final answer\n",
        )

        # Use agent's chat method with proper system message (reset chat for clean presentation)
        async for chunk in agent.chat(presentation_messages, reset_chat=True):
            # Use the same streaming approach as regular coordination
            if chunk.type == "content" and chunk.content:
                yield StreamChunk(
                    type="content", content=chunk.content, source=selected_agent_id
                )
            elif chunk.type in ["reasoning", "reasoning_done", "reasoning_summary", "reasoning_summary_done"]:
                # Stream reasoning content with proper attribution (same as main coordination)
                reasoning_chunk = StreamChunk(
                    type=chunk.type,
                    content=chunk.content,
                    source=selected_agent_id,
                    reasoning_delta=getattr(chunk, "reasoning_delta", None),
                    reasoning_text=getattr(chunk, "reasoning_text", None),
                    reasoning_summary_delta=getattr(chunk, "reasoning_summary_delta", None),
                    reasoning_summary_text=getattr(chunk, "reasoning_summary_text", None),
                    item_id=getattr(chunk, "item_id", None),
                    content_index=getattr(chunk, "content_index", None),
                    summary_index=getattr(chunk, "summary_index", None)
                )
                # Use the same format as main coordination for consistency
                yield reasoning_chunk
            elif chunk.type == "backend_status":
                import json
                status_json = json.loads(chunk.content)
                cwd = status_json["cwd"]
                session_id = status_json["session_id"]
                content = f"""Final Temp Working directory: {cwd}. \n Final Session ID: {session_id}. \n"""

                yield StreamChunk(type="content", content=content, source=selected_agent_id)

            elif chunk.type == "done":
                yield StreamChunk(type="done", source=selected_agent_id)
            elif chunk.type == "error":
                yield StreamChunk(
                    type="error", error=chunk.error, source=selected_agent_id
                )
            # Pass through other chunk types as-is but with source
            else:
                if hasattr(chunk, "source"):
                    chunk.source = selected_agent_id
                yield chunk

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
            yield StreamChunk(
                type="content",
                content=f"🤔 Thank you for your follow-up question in our ongoing conversation. I understand you're asking: '{user_message}'. Currently, the coordination is complete, but I can help clarify the answer or coordinate a new task that takes our conversation history into account.",
            )
        else:
            yield StreamChunk(
                type="content",
                content=f"🤔 Thank you for your follow-up: '{user_message}'. The coordination is complete, but I can help clarify the answer or coordinate a new task if needed.",
            )

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
            "selected_agent": self._selected_agent,
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

    def reset(self) -> None:
        """Reset orchestrator state for new task."""
        self.conversation_history.clear()
        self.current_task = None
        self.workflow_phase = "idle"
        self._coordination_messages.clear()
        self._selected_agent = None

        # Reset agent states
        for state in self.agent_states.values():
            state.answer = None
            state.has_voted = False
            state.restart_pending = False


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def create_orchestrator(
    agents: List[tuple],
    orchestrator_id: str = "orchestrator",
    session_id: Optional[str] = None,
    config: Optional[AgentConfig] = None,
) -> Orchestrator:
    """
    Create a MassGen orchestrator with sub-agents.

    Args:
        agents: List of (agent_id, ChatAgent) tuples
        orchestrator_id: Unique identifier for this orchestrator (default: "orchestrator")
        session_id: Optional session ID
        config: Optional AgentConfig for orchestrator customization

    Returns:
        Configured Orchestrator
    """
    agents_dict = {agent_id: agent for agent_id, agent in agents}

    return Orchestrator(
        agents=agents_dict,
        orchestrator_id=orchestrator_id,
        session_id=session_id,
        config=config,
    )
