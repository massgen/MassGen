"""
Enhanced Orchestrator Implementation - Full MASS Reference Implementation

This implements the complete MASS orchestrator with real-time streaming,
graceful restart logic, tool validation, and comprehensive error handling.

Phases 2.1-2.4 Implementation:
- Phase 2.1: Real-time streaming during coordination
- Phase 2.2: Graceful restart logic with restart_pending
- Phase 2.3: Comprehensive tool call validation
- Phase 2.4: Full error handling and retry mechanisms
"""

from typing import Dict, List, Optional, Any, AsyncGenerator
from dataclasses import dataclass, field
import asyncio
import time
import logging
from datetime import datetime

from .chat_agent import ChatAgent, StreamChunk
from .message_templates import MessageTemplates


@dataclass 
class VoteRecord:
    """Record of a vote cast by an agent."""
    voter_id: str
    target_id: str
    reason: str
    timestamp: float
    phase: str = "coordination"


@dataclass
class AgentState:
    """Runtime state for an agent during coordination."""
    answer: Optional[str] = None
    has_voted: bool = False
    votes: Dict[str, Any] = field(default_factory=dict)
    restart_pending: bool = False

    voting_weight: float = 1.0  # Default weight for voting: 1.0 (can be adjusted per agent)
    
    # Enhanced tracking
    status: str = "working"  # working, voted, failed, completed
    execution_start_time: Optional[float] = None
    execution_end_time: Optional[float] = None
    answer_history: List[str] = field(default_factory=list)
    update_count: int = 0

    def __post_init__(self):
        """Validate voting weight after initialization."""
        if self.voting_weight <= 0:
            raise ValueError(f"voting_weight must be positive, got {self.voting_weight}")
    
    @property
    def execution_time(self) -> Optional[float]:
        """Calculate execution time if both start and end times are available."""
        if self.execution_start_time and self.execution_end_time:
            return self.execution_end_time - self.execution_start_time
        return None


class Orchestrator(ChatAgent):
    """
    Enhanced MASS Orchestrator - Full reference implementation with real-time streaming.
    
    Implements the complete MASS coordination workflow with:
    - Real-time streaming during agent execution
    - Graceful restart logic when new answers arrive
    - Comprehensive tool call validation and error handling
    - Retry mechanisms with enforcement messages
    """
    
    def __init__(self, 
                 agents: Dict[str, ChatAgent], 
                 agent_weights: Optional[Dict[str, float]] = None, # Weights for agent voting
                 orchestrator_id: str = "orchestrator", 
                 session_id: Optional[str] = None,
                 config: Optional[Dict[str, Any]] = None,
                 max_duration: int = 600,
                 log_manager=None):
        """
        Initialize enhanced orchestrator.
        
        Args:
            agents: Dictionary of {agent_id: ChatAgent} instances
            agent_weights: Optional dictionary of {agent_id: weight} for weighted voting
            orchestrator_id: Unique identifier for this orchestrator
            session_id: Optional session identifier
            config: Optional configuration dictionary
            max_duration: Maximum duration for coordination in seconds
            log_manager: Optional logging manager instance
        """
        super().__init__(session_id)
        self.orchestrator_id = orchestrator_id
        self.agents = agents

        # Validate agent weight
        self.agent_weights = agent_weights or {}
        self._validate_agent_weights(self.agent_weights)

        # Initialize agent states with weights
        self.agent_states = {}
        for agent_id in agents.keys():
            weight = self.agent_weights.get(agent_id, 1.0)
            try:
                state = AgentState(voting_weight=weight)
                self.agent_states[agent_id] = state
            except ValueError as e:
                raise ValueError(f"Invalid weight for agent {agent_id}: {e}")

        
        self.config = config or {}
        
        # Enhanced configuration
        self.max_duration = max_duration
        self.max_attempts = self.config.get("max_attempts", 3)
        
        # Voting configuration (for future enhancements)
        self.voting_config = self.config.get("voting", {
            "include_vote_counts": False,  # Whether to show current vote counts to agents
            "include_vote_reasons": False,  # Whether to show vote reasons to agents
            "anonymous_voting": True,      # Use anonymous agent IDs in voting
            "voting_strategy": "weighted_vote" if agent_weights else "simple_majority", # Select voting strategy automatically
            "tie_breaking": "registration_order"   # registration_order, random, oldest_answer, etc.
        })

        self._validate_voting_configuration()
        
        # Session and tracking
        self.session_id = session_id or f"session_{int(time.time())}"
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.votes: List[VoteRecord] = []
        self.communication_log: List[Dict[str, Any]] = []
        
        # Logging
        self.log_manager = log_manager
        self.logger = logging.getLogger(f"{__name__}.{orchestrator_id}")
        
        # Initialize message templates and workflow tools
        self.message_templates = MessageTemplates()
        self.workflow_tools = self.message_templates.get_standard_tools(list(agents.keys()))
        
        # Orchestrator state
        self.current_task: Optional[str] = None
        self.workflow_phase: str = "idle"  # idle, coordinating, presenting, completed, timeout
        self._selected_agent: Optional[str] = None
        
        # Initialize agent states with execution tracking
        for agent_id in self.agents.keys():
            self.agent_states[agent_id].execution_start_time = None

    def _validate_agent_weights(self, agent_weights: Dict[str, float]) -> None:
        """Validate agent weights for proper numeric values and existence in agents."""
        for agent_id, weight in agent_weights.items():
            if agent_id not in self.agents:
                raise ValueError(f"Agent weight specified for unknown agent: {agent_id}")
            if not isinstance(weight, (int, float)):
                raise ValueError(f"Agent weight must be numeric, got {type(weight)} for {agent_id}")
            if weight <= 0:
                raise ValueError(f"Agent weight must be positive, got {weight} for {agent_id}")

    def _validate_voting_configuration(self) -> None:
        """validate voting configuration for supported strategies."""
        strategy = self.voting_config["voting_strategy"]

        if strategy == "weighted_vote":
            if not self.agent_weights:
                self.logger.warning("weighted_vote strategy selected but no agent_weights provided, all agents will have equal weight (1.0)")

            # Check weight distribution
            total_weight = sum(state.voting_weight for state in self.agent_states.values())
            if total_weight == 0:
                raise ValueError("Total voting weight cannot be zero")
        elif strategy == "simple_majority":
            pass
        else:
            raise ValueError(f"Unsupported voting strategy: {strategy}")

    async def chat(self, 
                   messages: List[Dict[str, Any]], 
                   tools: Optional[List[Dict[str, Any]]] = None,
                   reset_chat: bool = False, 
                   clear_history: bool = False) -> AsyncGenerator[StreamChunk, None]:
        """
        Main chat interface - coordinates sub-agents with real-time streaming.
        
        Args:
            messages: List of conversation messages
            tools: Ignored by orchestrator (uses internal workflow tools)
            reset_chat: If True, reset conversation history
            clear_history: If True, clear conversation history
            
        Yields:
            StreamChunk: Streaming response chunks from coordination
        """
        # Extract user message from messages
        user_message = None
        for message in messages:
            if message.get("role") == "user":
                user_message = message.get("content", "")
                self.add_to_history("user", user_message)
        
        if not user_message:
            yield StreamChunk(type="error", error="No user message found in conversation")
            return
        
        # Start coordination
        if self.workflow_phase == "idle":
            self.current_task = user_message
            self.workflow_phase = "coordinating"
            self.start_time = time.time()
            
            # Log task start
            self._log_event("task_started", {
                "task": user_message,
                "session_id": self.session_id,
                "agent_count": len(self.agents)
            })
            
            # Initialize agent execution times
            for agent_id in self.agents.keys():
                self.agent_states[agent_id].execution_start_time = time.time()
                self.agent_states[agent_id].status = "working"
            
            self.logger.info(f"Starting coordination for task: {user_message[:100]}...")
            
            async for chunk in self._coordinate_agents():
                yield chunk
        else:
            yield StreamChunk(type="content", content="🔄 Already coordinating agents, please wait...")
    
    async def _coordinate_agents(self) -> AsyncGenerator[StreamChunk, None]:
        """Execute full MASS coordination workflow with real-time streaming and timeout handling."""
        yield StreamChunk(
            type="content", 
            content="🚀 Starting multi-agent coordination...\n\n",
            source=self.orchestrator_id
        )
        
        votes = {}  # Track votes: voter_id -> {"agent_id": voted_for, "reason": reason}
        
        # Initialize all agents with has_voted = False and set restart flags
        for agent_id in self.agents.keys():
            self.agent_states[agent_id].has_voted = False
            self.agent_states[agent_id].restart_pending = True
        
        yield StreamChunk(type="content", content="## 📋 Agents Coordinating\n", source=self.orchestrator_id)
        
        try:
            # Create timeout task
            timeout_task = asyncio.create_task(asyncio.sleep(self.max_duration))
            coordination_completed = False
            
            # Stream coordination with timeout checking
            coordination_stream = self._stream_coordination_with_agents(votes)
            
            async for chunk in coordination_stream:
                # Check if timeout occurred during streaming
                if timeout_task.done():
                    yield StreamChunk(type="content", content=f"⏰ **Timeout reached ({self.max_duration}s)** - forcing consensus\n", source=self.orchestrator_id)
                    self.workflow_phase = "timeout"
                    self._log_event("timeout_reached", {"duration": self.max_duration})
                    self.logger.warning(f"Coordination timeout after {self.max_duration}s")
                    
                    # Force consensus with available votes
                    current_answers = {aid: state.answer for aid, state in self.agent_states.items() if state.answer}
                    if current_answers:
                        self._selected_agent = self._force_consensus_by_timeout(votes, current_answers)
                        yield StreamChunk(type="content", content=f"🔧 Selected agent {self._selected_agent} by timeout consensus\n", source=self.orchestrator_id)
                    else:
                        yield StreamChunk(type="content", content="❌ No answers available for timeout consensus\n", source=self.orchestrator_id)
                        return
                    break
                else:
                    yield chunk
            else:
                # Coordination completed normally
                coordination_completed = True
                timeout_task.cancel()
                
                # Determine final agent based on votes  
                current_answers = {aid: state.answer for aid, state in self.agent_states.items() if state.answer}
                self._selected_agent = self._determine_final_agent_from_votes(votes, current_answers)
        
        except Exception as e:
            self.logger.error(f"Coordination error: {e}")
            yield StreamChunk(type="error", error=f"Coordination failed: {str(e)}", source=self.orchestrator_id)
            return
        
        # Present final answer
        async for chunk in self._present_final_answer():
            yield chunk
    
    async def _stream_coordination_with_agents(self, votes: Dict[str, Dict]) -> AsyncGenerator[StreamChunk, None]:
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
            current_answers = {aid: state.answer for aid, state in self.agent_states.items() if state.answer}
            for agent_id in self.agents.keys():
                if (agent_id not in active_streams and 
                    not self.agent_states[agent_id].has_voted):
                    active_streams[agent_id] = self._stream_agent_execution(agent_id, self.current_task, current_answers)
            
            if not active_streams:
                break
                
            # Create tasks only for streams that don't already have active tasks
            for agent_id, stream in active_streams.items():
                if agent_id not in active_tasks:
                    active_tasks[agent_id] = asyncio.create_task(self._get_next_chunk(stream))
            
            if not active_tasks:
                break
                
            done, _ = await asyncio.wait(
                active_tasks.values(),
                return_when=asyncio.FIRST_COMPLETED
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
                        yield StreamChunk(type="content", content=chunk_data, source=agent_id)
                        
                    elif chunk_type == "result":
                        # Agent completed with result
                        result_type, result_data = chunk_data
                        
                        # Emit agent completion status immediately upon result
                        yield StreamChunk(type="agent_status", source=agent_id, status="completed", content="")
                        await self._close_agent_stream(agent_id, active_streams)
                        
                        if result_type == "answer":
                            # Agent provided an answer (initial or improved)
                            # Always record answers, even from restarting agents (orchestrator accepts them)
                            answered_agents[agent_id] = result_data
                            reset_signal = True
                            yield StreamChunk(type="content", content="✅ Answer provided", source=agent_id)
                            
                        elif result_type == "vote":
                            # Agent voted for existing answer
                            # Ignore votes from agents with restart pending (votes are about current state)
                            if self.agent_states[agent_id].restart_pending:
                                yield StreamChunk(type="content", content="🔄 Vote ignored - restarting due to new answers", source=agent_id)
                            else:
                                voted_agents[agent_id] = result_data
                                yield StreamChunk(type="content", content=f"✅ Vote recorded for {result_data['agent_id']}", source=agent_id)
                    
                    elif chunk_type == "error":
                        # Agent error
                        yield StreamChunk(type="content", content=f"❌ {chunk_data}", source=agent_id)
                        # Emit agent completion status for errors too
                        yield StreamChunk(type="agent_status", source=agent_id, status="completed", content="")
                        await self._close_agent_stream(agent_id, active_streams)
                    
                    elif chunk_type == "done":
                        # Stream completed - emit completion status for frontend
                        yield StreamChunk(type="agent_status", source=agent_id, status="completed", content="")
                        await self._close_agent_stream(agent_id, active_streams)
                
                except Exception as e:
                    yield StreamChunk(type="content", content=f"❌ Stream error - {e}", source=agent_id)
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
    
    async def _close_agent_stream(self, agent_id: str, active_streams: Dict[str, AsyncGenerator]) -> None:
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
    
    def _create_tool_error_messages(self, agent: ChatAgent, tool_calls: List[Dict[str, Any]], 
                                   primary_error_msg: str, secondary_error_msg: str = None) -> List[Dict[str, Any]]:
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
        error_result_msg = self._create_tool_result_message(agent, first_tool_call, primary_error_msg)
        enforcement_msgs.append(error_result_msg)
        
        # Send secondary error messages for any additional tool calls (API requires response to ALL calls)
        for additional_tool_call in tool_calls[1:]:
            neutral_msg = self._create_tool_result_message(agent, additional_tool_call, secondary_error_msg)
            enforcement_msgs.append(neutral_msg)
        
        return enforcement_msgs
    
    def _create_tool_result_message(self, agent: ChatAgent, tool_call: Dict[str, Any], result_content: str) -> Dict[str, Any]:
        """Create tool result message for a tool call."""
        # Use agent's backend if available, otherwise create generic message
        if hasattr(agent, 'backend') and hasattr(agent.backend, 'create_tool_result_message'):
            return agent.backend.create_tool_result_message(tool_call, result_content)
        else:
            # Generic tool result message
            tool_call_id = self._extract_tool_call_id(tool_call)
            return {"role": "tool", "tool_call_id": tool_call_id, "content": result_content}
    
    async def _stream_agent_execution(self, agent_id: str, task: str, answers: Dict[str, str]) -> AsyncGenerator[tuple, None]:
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
            # Use proper conversation building
            conversation = self.message_templates.build_initial_conversation(
                task=task, 
                agent_summaries=answers,
                valid_agent_ids=list(answers.keys()) if answers else None
            )
            
            # Build proper conversation messages with system + user messages
            conversation_messages = [
                {"role": "system", "content": conversation["system_message"]},
                {"role": "user", "content": conversation["user_message"]}
            ]
            enforcement_msg = self.message_templates.enforcement_message()
            
            for attempt in range(self.max_attempts):
                if self._check_restart_pending(agent_id):
                    yield ("content", "🔄 Gracefully restarting due to new answers from other agents")
                    yield ("done", None)
                    return
                
                # Stream agent response with workflow tools
                if attempt == 0:
                    # First attempt: provide complete conversation and reset agent's history
                    chat_stream = agent.chat(conversation_messages, self.workflow_tools, reset_chat=True)
                else:
                    # Subsequent attempts: send enforcement message
                    if isinstance(enforcement_msg, list):
                        # Tool message array
                        chat_stream = agent.chat(enforcement_msg, self.workflow_tools, reset_chat=False)
                    else:
                        # Single user message
                        enforcement_message = {"role": "user", "content": enforcement_msg}
                        chat_stream = agent.chat([enforcement_message], self.workflow_tools, reset_chat=False)
                
                response_text = ""
                tool_calls = []
                workflow_tool_found = False
                
                async for chunk in chat_stream:
                    if chunk.type == "content":
                        response_text += chunk.content
                        # Stream agent content directly - source field handles attribution
                        yield ("content", chunk.content)
                    elif chunk.type == "tool_calls":
                        if hasattr(chunk, 'content') and chunk.content:
                            tool_calls.extend(chunk.content)
                        elif hasattr(chunk, 'tool_calls') and chunk.tool_calls:
                            tool_calls.extend(chunk.tool_calls)
                        
                        # Stream tool calls to show agent actions
                        for tool_call in (chunk.content if hasattr(chunk, 'content') and chunk.content else 
                                        chunk.tool_calls if hasattr(chunk, 'tool_calls') and chunk.tool_calls else []):
                            tool_name = self._extract_tool_name(tool_call)
                            tool_args = self._extract_tool_arguments(tool_call)
                            
                            if tool_name == "new_answer":
                                content = tool_args.get("content", "")
                                yield ("content", f"💡 Providing answer: \"{content[:100]}{'...' if len(content) > 100 else ''}\"")
                            elif tool_name == "vote":
                                agent_voted_for = tool_args.get("agent_id", "")
                                reason = tool_args.get("reason", "")
                                yield ("content", f"🗳️ Voting for {agent_voted_for}: {reason}")
                            else:
                                yield ("content", f"🔧 Using {tool_name}")
                    elif chunk.type == "error":
                        # Stream error information to user interface
                        error_msg = getattr(chunk, 'error', str(chunk.content)) if hasattr(chunk, 'error') else str(chunk.content)
                        yield ("content", f"❌ Error: {error_msg}")
                
                # Validate and process tool calls
                validation_result = self._validate_tool_calls(tool_calls, answers, agent_id, attempt)
                
                if validation_result["valid"]:
                    workflow_tool_found = True
                    result_type = validation_result["result_type"]
                    result_data = validation_result["result_data"]
                    
                    yield ("result", (result_type, result_data))
                    yield ("done", None)
                    return
                elif validation_result["retry"] and attempt < self.max_attempts - 1:
                    # Validation failed but we can retry
                    if self._check_restart_pending(agent_id):
                        yield ("content", "🔄 Gracefully restarting due to new answers from other agents")
                        yield ("done", None)
                        return
                    
                    error_msg = validation_result["error_msg"]
                    yield ("content", f"❌ {error_msg}")
                    
                    # Set enforcement message for retry
                    enforcement_msg = validation_result.get("enforcement_msg", self.message_templates.enforcement_message())
                    continue  # Retry this attempt
                elif not workflow_tool_found:
                    # No workflow tool found
                    if self._check_restart_pending(agent_id):
                        yield ("content", "🔄 Gracefully restarting due to new answers from other agents")
                        yield ("done", None)
                        return
                    if attempt < self.max_attempts - 1:
                        yield ("content", f"🔄 needs to use workflow tools...")
                        enforcement_msg = self.message_templates.enforcement_message()
                        continue  # Retry with updated conversation
                    else:
                        # Last attempt failed, agent did not provide proper workflow response
                        yield ("error", f"Agent failed to use workflow tools after {self.max_attempts} attempts")
                        yield ("done", None)
                        return
                else:
                    # Validation failed on final attempt
                    yield ("error", validation_result["error_msg"])
                    yield ("done", None)
                    return
                    
        except Exception as e:
            yield ("error", f"Agent execution failed: {str(e)}")
            yield ("done", None)
    
    def _validate_tool_calls(self, tool_calls: List[Dict[str, Any]], answers: Dict[str, str], 
                           agent_id: str, attempt: int) -> Dict[str, Any]:
        """
        Comprehensive tool call validation with detailed error handling.
        
        Returns:
            Dict with validation results:
            - valid: bool - whether tool calls are valid
            - retry: bool - whether to retry on failure
            - result_type: str - "vote" or "answer" if valid
            - result_data: Any - the result data if valid
            - error_msg: str - error message if invalid
            - enforcement_msg: Any - enforcement message for retry
        """
        if not tool_calls:
            return {
                "valid": False,
                "retry": True,
                "error_msg": "No tool calls found. Must use vote or new_answer tool.",
                "enforcement_msg": self.message_templates.enforcement_message()
            }
        
        # Check for multiple vote calls
        vote_calls = [tc for tc in tool_calls if self._extract_tool_name(tc) == "vote"]
        new_answer_calls = [tc for tc in tool_calls if self._extract_tool_name(tc) == "new_answer"]
        
        if len(vote_calls) > 1:
            error_msg = f"Multiple vote calls not allowed. Made {len(vote_calls)} calls but must make exactly 1. Call vote tool once with chosen agent."
            enforcement_msg = self._create_tool_error_messages_simple(tool_calls, error_msg, "Vote rejected due to multiple votes.")
            return {
                "valid": False,
                "retry": attempt < self.max_attempts - 1,
                "error_msg": error_msg,
                "enforcement_msg": enforcement_msg
            }
        
        # Check for mixed new_answer and vote calls - violates binary decision framework
        if len(vote_calls) > 0 and len(new_answer_calls) > 0:
            error_msg = "Cannot use both 'vote' and 'new_answer' in same response. Choose one: vote for existing answer OR provide new answer."
            enforcement_msg = self._create_tool_error_messages_simple(tool_calls, error_msg)
            return {
                "valid": False,
                "retry": attempt < self.max_attempts - 1,
                "error_msg": error_msg,
                "enforcement_msg": enforcement_msg
            }
        
        # Process tool calls
        for tool_call in tool_calls:
            tool_name = self._extract_tool_name(tool_call)
            tool_args = self._extract_tool_arguments(tool_call)
            
            if tool_name == "vote":
                # Check if agent should restart - votes invalid during restart
                if self.agent_states[agent_id].restart_pending:
                    return {
                        "valid": False,
                        "retry": False,
                        "error_msg": "Vote invalid - restarting due to new answers"
                    }
                
                # Vote for existing answer (requires existing answers)
                if not answers:
                    error_msg = "Cannot vote when no answers exist. Use new_answer tool."
                    enforcement_msg = self._create_tool_error_messages_simple([tool_call], error_msg)
                    return {
                        "valid": False,
                        "retry": attempt < self.max_attempts - 1,
                        "error_msg": error_msg,
                        "enforcement_msg": enforcement_msg
                    }
                
                voted_agent_anon = tool_args.get("agent_id")
                reason = tool_args.get("reason", "")
                
                # Convert anonymous agent ID back to real agent ID
                voted_agent = self._convert_anonymous_to_real(voted_agent_anon, answers)
                
                # Handle invalid agent_id
                if voted_agent not in answers:
                    # Create reverse mapping for error message
                    reverse_mapping = {real_id: f"agent{i}" for i, real_id in enumerate(sorted(answers.keys()), 1)}
                    valid_anon_agents = [reverse_mapping[real_id] for real_id in answers.keys()]
                    error_msg = f"Invalid agent_id '{voted_agent_anon}'. Valid agents: {', '.join(valid_anon_agents)}"
                    enforcement_msg = self._create_tool_error_messages_simple([tool_call], error_msg)
                    return {
                        "valid": False,
                        "retry": attempt < self.max_attempts - 1,
                        "error_msg": error_msg,
                        "enforcement_msg": enforcement_msg
                    }
                
                # Valid vote - record it
                vote_record = VoteRecord(
                    voter_id=agent_id,
                    target_id=voted_agent,
                    reason=reason,
                    timestamp=time.time(),
                    phase=self.workflow_phase
                )
                self.votes.append(vote_record)
                self.agent_states[agent_id].votes = {"agent_id": voted_agent, "reason": reason}
                
                # Log the vote
                self._log_event("vote_cast", {
                    "voter_id": agent_id,
                    "target_id": voted_agent,
                    "reason": reason
                })
                
                if self.log_manager:
                    self.log_manager.log_vote_cast(
                        voter_id=agent_id,
                        target_id=voted_agent,
                        reason=reason,
                        phase=self.workflow_phase
                    )
                
                return {
                    "valid": True,
                    "result_type": "vote",
                    "result_data": {"agent_id": voted_agent, "reason": reason}
                }
            
            elif tool_name == "new_answer":
                # Agent provided new answer
                content = tool_args.get("content", "").strip()
                
                if not content:
                    error_msg = "Answer content cannot be empty. Provide meaningful answer content."
                    enforcement_msg = self._create_tool_error_messages_simple([tool_call], error_msg)
                    return {
                        "valid": False,
                        "retry": attempt < self.max_attempts - 1,
                        "error_msg": error_msg,
                        "enforcement_msg": enforcement_msg
                    }
                
                # Check for duplicate answer
                for existing_agent_id, existing_content in answers.items():
                    if content.strip() == existing_content.strip():
                        error_msg = f"Answer already provided by {existing_agent_id}. Provide different answer or vote for existing one."
                        enforcement_msg = self._create_tool_error_messages_simple([tool_call], error_msg)
                        return {
                            "valid": False,
                            "retry": attempt < self.max_attempts - 1,
                            "error_msg": error_msg,
                            "enforcement_msg": enforcement_msg
                        }
                
                # Valid new answer - record it
                self.agent_states[agent_id].answer_history.append(content)
                self.agent_states[agent_id].update_count += 1
                
                # Log the answer update
                self._log_event("answer_updated", {
                    "agent_id": agent_id,
                    "answer_length": len(content),
                    "update_count": self.agent_states[agent_id].update_count
                })
                
                if self.log_manager:
                    self.log_manager.log_agent_answer_update(
                        agent_id=agent_id,
                        answer=content,
                        phase=self.workflow_phase,
                        orchestrator=self
                    )
                
                return {
                    "valid": True,
                    "result_type": "answer",
                    "result_data": content
                }
        
        # No workflow tools found
        return {
            "valid": False,
            "retry": True,
            "error_msg": "Must use vote or new_answer tool",
            "enforcement_msg": self.message_templates.enforcement_message()
        }
    
    def _create_tool_error_messages_simple(self, tool_calls: List[Dict[str, Any]], primary_error_msg: str, 
                                         secondary_error_msg: str = None) -> List[Dict[str, Any]]:
        """Create simple tool error messages for validation failures."""
        if not tool_calls:
            return [{"role": "user", "content": primary_error_msg}]
        
        if secondary_error_msg is None:
            secondary_error_msg = primary_error_msg
            
        enforcement_msgs = []
        
        # Send primary error for the first tool call
        first_tool_call = tool_calls[0]
        tool_call_id = self._extract_tool_call_id(first_tool_call)
        error_result_msg = {"role": "tool", "tool_call_id": tool_call_id, "content": primary_error_msg}
        enforcement_msgs.append(error_result_msg)
        
        # Send secondary error messages for any additional tool calls
        for additional_tool_call in tool_calls[1:]:
            tool_call_id = self._extract_tool_call_id(additional_tool_call)
            neutral_msg = {"role": "tool", "tool_call_id": tool_call_id, "content": secondary_error_msg}
            enforcement_msgs.append(neutral_msg)
        
        return enforcement_msgs
    
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
                yield StreamChunk(type="content", content=f"🏆 Selected Agent: {self._selected_agent}\n")
        
        if (self._selected_agent and 
            self._selected_agent in self.agent_states and 
            self.agent_states[self._selected_agent].answer):
            final_answer = self.agent_states[self._selected_agent].answer
            
            # Add to conversation history
            self.add_to_history("assistant", final_answer)
            
            yield StreamChunk(type="content", content=final_answer)
            yield StreamChunk(type="content", content=f"\n\n---\n*Coordinated by {len(self.agents)} agents via MASS framework*")
        else:
            error_msg = "❌ Unable to provide coordinated answer - no successful agents"
            self.add_to_history("assistant", error_msg)
            yield StreamChunk(type="content", content=error_msg)
        
        # Update workflow phase
        self.workflow_phase = "presenting"
        yield StreamChunk(type="done")
    
    def _determine_final_agent_from_votes(self, votes: Dict[str, Dict], agent_answers: Dict[str, str]) -> str:
        """Determine which agent should present the final answer based on votes (simple majority & weighted vote)."""
        if not votes:
            # No votes yet, return first agent with an answer (earliest by generation time)
            return next(iter(agent_answers)) if agent_answers else None
        
        voting_strategy = self.voting_config.get("voting_strategy", "simple_majority")

        if voting_strategy == "weighted_vote":
            vote_weights = {}
            for voter_id, vote_data in votes.items():
                voted_for = vote_data.get("agent_id")
                if voted_for and voter_id in self.agent_states:
                    voter_weight = self.agent_states[voter_id].voting_weight
                    vote_weights[voted_for] = vote_weights.get(voted_for, 0) + voter_weight

            if not vote_weights:
                return next(iter(agent_answers)) if agent_answers else None
            
            # Select agent with maximum weighted votes
            max_weight = max(vote_weights.values())
            tied_agents = [agent_id for agent_id, weight in vote_weights.items() if weight == max_weight]

            # Handle ties according to configuration
            if len(tied_agents) > 1:
                selected_agent = self._break_tie(tied_agents, agent_answers)
                tie_broken = True
            else:
                selected_agent = tied_agents[0]
                tie_broken = False

            # Log the selected agent and voting details
            if selected_agent:
                total_weight = sum(vote_weights.values())
                self.logger.info(f"Selected {selected_agent} with weight {vote_weights[selected_agent]:.2f}/{total_weight:.2f}{' (tie-broken)' if tie_broken else ''}")
                self._log_event("agent_selected", {
                    "selected_agent": selected_agent,
                    "weighted_score": vote_weights[selected_agent],
                    "total_weighted_votes": total_weight,
                    "weight_distribution": vote_weights,
                    "voting_strategy": "weighted_vote",
                    "tie_broken": tie_broken,
                    "tie_breaking_method": self.voting_config["tie_breaking"] if tie_broken else None
                })

            return selected_agent
        else:
            # Count votes for each agent
            vote_counts = {}
            for vote_data in votes.values():
                voted_for = vote_data.get("agent_id")
                if voted_for:
                    vote_counts[voted_for] = vote_counts.get(voted_for, 0) + 1
            
            if not vote_counts:
                return next(iter(agent_answers)) if agent_answers else None
            
            # Simple majority: select agent with most votes
            max_votes = max(vote_counts.values())
            tied_agents = [agent_id for agent_id, count in vote_counts.items() if count == max_votes]
            
            # Handle ties according to configuration
            if len(tied_agents) > 1:
                selected_agent = self._break_tie(tied_agents, agent_answers)
                tie_broken = True
            else:
                selected_agent = tied_agents[0]
                tie_broken = False
        
            if selected_agent:
                self.logger.info(f"Selected {selected_agent} with {vote_counts[selected_agent]}/{len(votes)} votes{' (tie-broken)' if tie_broken else ''}")
                self._log_event("agent_selected", {
                    "selected_agent": selected_agent,
                    "votes_received": vote_counts[selected_agent],
                    "total_voters": len(votes),
                    "vote_distribution": vote_counts,
                    "tie_broken": tie_broken,
                    "tie_breaking_method": self.voting_config["tie_breaking"] if tie_broken else None
                })
            
            return selected_agent
    
    def _determine_final_agent_from_states(self) -> Optional[str]:
        """Determine final agent based on current agent states."""
        # Find agents with answers
        agents_with_answers = {aid: state.answer for aid, state in self.agent_states.items() if state.answer}
        
        if not agents_with_answers:
            return None
        
        # Return the first agent with an answer (by order in agent_states)
        return next(iter(agents_with_answers))
    
    # Tool call utility methods
    def _extract_tool_name(self, tool_call: Dict[str, Any]) -> str:
        """Extract tool name from tool call."""
        if "function" in tool_call:
            return tool_call.get("function", {}).get("name", "")
        return tool_call.get("name", "")
    
    def _extract_tool_arguments(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """Extract tool arguments from tool call."""
        if "function" in tool_call:
            args = tool_call.get("function", {}).get("arguments", {})
        else:
            args = tool_call.get("arguments", {})
        
        # Handle string arguments (need to parse JSON)
        if isinstance(args, str):
            try:
                import json
                return json.loads(args)
            except:
                return {}
        
        return args if isinstance(args, dict) else {}
    
    def _extract_tool_call_id(self, tool_call: Dict[str, Any]) -> str:
        """Extract tool call ID from tool call."""
        return tool_call.get("id", tool_call.get("call_id", ""))
    
    def _convert_anonymous_to_real(self, anon_agent_id: str, agent_answers: Dict[str, str]) -> Optional[str]:
        """Convert anonymous agent ID (agent1, agent2) back to real agent ID."""
        if not anon_agent_id or not agent_answers:
            return None
        
        # Create mapping from anonymous to real IDs
        agent_mapping = {}
        for i, real_agent_id in enumerate(sorted(agent_answers.keys()), 1):
            agent_mapping[f"agent{i}"] = real_agent_id
        
        return agent_mapping.get(anon_agent_id)
    
    def _break_tie(self, tied_agents: List[str], agent_answers: Dict[str, str]) -> str:
        """Break ties according to voting configuration."""
        tie_breaking_method = self.voting_config["tie_breaking"]
        
        if tie_breaking_method == "registration_order":
            # Break ties by agent registration order (order in agent_states dict)
            for agent_id in self.agent_states.keys():
                if agent_id in tied_agents:
                    return agent_id
            return tied_agents[0]  # Fallback
        
        elif tie_breaking_method == "random":
            # Random selection among tied agents
            import random
            return random.choice(tied_agents)
        
        elif tie_breaking_method == "oldest_answer":
            # Select agent who provided answer first (earliest execution start time)
            earliest_agent = None
            earliest_time = float('inf')
            
            for agent_id in tied_agents:
                state = self.agent_states[agent_id]
                if state.execution_start_time and state.execution_start_time < earliest_time:
                    earliest_time = state.execution_start_time
                    earliest_agent = agent_id
            
            return earliest_agent or tied_agents[0]
        
        elif tie_breaking_method == "newest_answer":
            # Select agent who provided answer last (latest execution start time)
            latest_agent = None
            latest_time = 0
            
            for agent_id in tied_agents:
                state = self.agent_states[agent_id]
                if state.execution_start_time and state.execution_start_time > latest_time:
                    latest_time = state.execution_start_time
                    latest_agent = agent_id
            
            return latest_agent or tied_agents[0]
        
        elif tie_breaking_method == "longest_answer":
            # Select agent with longest answer
            longest_agent = None
            max_length = 0
            
            for agent_id in tied_agents:
                if agent_id in agent_answers:
                    answer_length = len(agent_answers[agent_id])
                    if answer_length > max_length:
                        max_length = answer_length
                        longest_agent = agent_id
            
            return longest_agent or tied_agents[0]
        
        else:
            # Unknown method - fallback to registration order
            self.logger.warning(f"Unknown tie-breaking method '{tie_breaking_method}', using registration_order")
            for agent_id in self.agent_states.keys():
                if agent_id in tied_agents:
                    return agent_id
            return tied_agents[0]
    
    # =============================================================================
    # LOGGING AND SESSION MANAGEMENT
    # =============================================================================
    
    def _log_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Log an orchestrator event to communication log."""
        self.communication_log.append({
            "timestamp": time.time(),
            "event_type": event_type,
            "data": data
        })
        
        # Also log to Python logging system
        self.logger.info(f"{event_type}: {data}")
    
    def _force_consensus_by_timeout(self, votes: Dict[str, Dict], agent_answers: Dict[str, str]) -> Optional[str]:
        """Force consensus selection when timeout is reached."""
        self._log_event("consensus_forced_by_timeout", {
            "available_votes": len(votes),
            "available_answers": len(agent_answers)
        })
        
        if votes:
            # Use existing voting logic
            selected = self._determine_final_agent_from_votes(votes, agent_answers)
        elif agent_answers:
            # Fallback to first available answer
            selected = next(iter(agent_answers))
        else:
            selected = None
        
        if selected and self.log_manager:
            self.log_manager.log_consensus_reached(
                winning_agent_id=selected,
                vote_distribution=dict(votes) if votes else {},
                is_fallback=True,
                phase="timeout"
            )
        
        return selected
    
    def export_session_log(self) -> Dict[str, Any]:
        """Export comprehensive session information for analysis."""
        if self.end_time is None:
            self.end_time = time.time()
        
        session_log = {
            "session_metadata": {
                "session_id": self.session_id,
                "orchestrator_id": self.orchestrator_id,
                "start_time": self.start_time,
                "end_time": self.end_time,
                "total_duration": (self.end_time - self.start_time) if self.start_time and self.end_time else None,
                "timestamp": datetime.now().isoformat(),
                "system_version": "MassGen v0.0.2"
            },
            "task_information": {
                "question": self.current_task,
                "workflow_phase": self.workflow_phase,
                "selected_agent": self._selected_agent
            },
            "system_configuration": {
                "max_duration": self.max_duration,
                "max_attempts": self.max_attempts,
                "voting_config": self.voting_config,
                "agent_count": len(self.agents),
                "agent_ids": list(self.agents.keys())
            },
            "agent_details": {
                agent_id: {
                    "status": state.status,
                    "voting_weight": state.voting_weight, # Weight used in weighted voting
                    "has_answer": state.answer is not None,
                    "has_voted": state.has_voted,
                    "answer_length": len(state.answer) if state.answer else 0,
                    "update_count": state.update_count,
                    "answer_history_count": len(state.answer_history),
                    "execution_time": state.execution_time,
                    "execution_start_time": state.execution_start_time,
                    "execution_end_time": state.execution_end_time,
                    "restart_pending": state.restart_pending
                }
                for agent_id, state in self.agent_states.items()
            },
            "voting_analysis": {
                "voting_strategy": self.voting_config.get("voting_strategy", "simple_majority"), # add voting strategy
                "total_votes": len(self.votes),
                "vote_records": [
                    {
                        "voter_id": vote.voter_id,
                        "target_id": vote.target_id,
                        "reason_length": len(vote.reason),
                        "timestamp": vote.timestamp,
                        "phase": vote.phase
                    }
                    for vote in self.votes
                ],
                "vote_distribution": self._get_vote_distribution(),
                "consensus_reached": self._selected_agent is not None
            },
            "communication_log": self.communication_log,
            "system_events_summary": {
                event_type: len([e for e in self.communication_log if e["event_type"] == event_type])
                for event_type in set(e["event_type"] for e in self.communication_log)
            }
        }
        
        return session_log
    
    def _get_vote_distribution(self) -> Dict[str, Any]:
      """Get current vote distribution (supports both simple and weighted voting)."""
      voting_strategy = self.voting_config.get("voting_strategy", "simple_majority")

      if voting_strategy == "weighted_vote":
          # Return weighted distribution
          vote_weights = {}
          for vote in self.votes:
              target = vote.target_id
              voter_weight = self.agent_states[vote.voter_id].voting_weight
              vote_weights[target] = vote_weights.get(target, 0) + voter_weight
          return vote_weights
      else:
          # Return simple count distribution
          vote_counts = {}
          for vote in self.votes:
              target = vote.target_id
              vote_counts[target] = vote_counts.get(target, 0) + 1
          return vote_counts
    
    def get_status(self) -> Dict[str, Any]:
        """Get current orchestrator status with enhanced tracking."""
        runtime = (time.time() - self.start_time) if self.start_time else 0
        vote_distribution = self._get_vote_distribution()
        
        return {
            "orchestrator_id": self.orchestrator_id,
            "session_id": self.session_id,
            "sub_agents": list(self.agents.keys()),
            "workflow_phase": self.workflow_phase,
            "current_task": self.current_task,
            "selected_agent": self._selected_agent,
            "runtime": runtime,
            "max_duration": self.max_duration,
            "voting_config": self.voting_config,
            "total_votes": len(self.votes),
            "vote_distribution": vote_distribution,
            "agent_states": {
                agent_id: {
                    "status": state.status,
                    "voting_weight": state.voting_weight, # Weight used in weighted voting
                    "has_answer": state.answer is not None,
                    "has_voted": state.has_voted,
                    "restart_pending": state.restart_pending,
                    "update_count": state.update_count,
                    "execution_time": state.execution_time,
                    "answer_length": len(state.answer) if state.answer else 0
                }
                for agent_id, state in self.agent_states.items()
            }
        }
    
    def reset(self) -> None:
        """Reset orchestrator state for new conversation."""
        self.conversation_history.clear()
        self.current_task = None
        self.workflow_phase = "idle"
        self._selected_agent = None
        
        # Reset session tracking
        self.start_time = None
        self.end_time = None
        self.votes.clear()
        self.communication_log.clear()
        
        # Reset agent states (preserve voting weights)
        for agent_id in self.agents.keys():
            original_weight = self.agent_states[agent_id].voting_weight
            self.agent_states[agent_id] = AgentState(voting_weight=original_weight)
                
        # Reset sub-agents
        for agent in self.agents.values():
            if hasattr(agent, 'reset'):
                agent.reset()
        
        self._log_event("session_reset", {"session_id": self.session_id})


# Factory function for creating orchestrators
def create_orchestrator(agents: Dict[str, ChatAgent], 
                        agent_weights: Optional[Dict[str, float]] = None,
                       orchestrator_id: str = "orchestrator",
                       config: Optional[Dict[str, Any]] = None,
                       session_id: Optional[str] = None,
                       max_duration: int = 600,
                       log_manager=None) -> Orchestrator:
    """
    Create an enhanced orchestrator with sub-agents.
    
    Args:
        agents: Dictionary of agent_id -> ChatAgent instances
        agent_weights: Optional dictionary of {agent_id: weight} for weighted voting
        orchestrator_id: Unique identifier for the orchestrator
        config: Optional configuration dictionary
        session_id: Optional session ID
        max_duration: Maximum duration for coordination in seconds
        log_manager: Optional logging manager instance
        
    Returns:
        Orchestrator: Enhanced orchestrator instance with full MASS features,
                      logging, timeout handling, and session export
    """
    return Orchestrator(
        agents=agents,
        agent_weights=agent_weights,
        orchestrator_id=orchestrator_id,
        config=config,
        session_id=session_id,
        max_duration=max_duration,
        log_manager=log_manager
    )