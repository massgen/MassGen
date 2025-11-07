# -*- coding: utf-8 -*-
"""
Common chat interface for MassGen agents.

Defines the standard interface that both individual agents and the orchestrator implement,
allowing seamless interaction regardless of whether you're talking to a single agent
or a coordinated multi-agent system.

# TODO: Consider how to best handle stateful vs stateless backends in this interface.
"""

import uuid
from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, List, Optional

from .backend.base import LLMBackend, StreamChunk
from .logger_config import logger
from .memory import ConversationMemory, PersistentMemoryBase
from .stream_chunk import ChunkType
from .utils import CoordinationStage


class ChatAgent(ABC):
    """
    Abstract base class defining the common chat interface.

    This interface is implemented by both individual agents and the MassGen orchestrator,
    providing a unified way to interact with any type of agent system.
    """

    def __init__(
        self,
        session_id: Optional[str] = None,
        conversation_memory: Optional[ConversationMemory] = None,
        persistent_memory: Optional[PersistentMemoryBase] = None,
    ):
        self.session_id = session_id or f"chat_session_{uuid.uuid4().hex[:8]}"
        self.conversation_history: List[Dict[str, Any]] = []

        # Memory components
        self.conversation_memory = conversation_memory
        self.persistent_memory = persistent_memory

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]] = None,
        reset_chat: bool = False,
        clear_history: bool = False,
        current_stage: CoordinationStage = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Enhanced chat interface supporting tool calls and responses.

        Args:
            messages: List of conversation messages including:
                - {"role": "user", "content": "..."}
                - {"role": "assistant", "content": "...", "tool_calls": [...]}
                - {"role": "tool", "tool_call_id": "...", "content": "..."}
                Or a single string for backwards compatibility
            tools: Optional tools to provide to the agent
            reset_chat: If True, reset the agent's conversation history to the provided messages
            clear_history: If True, clear history but keep system message before processing messages
            current_stage: Optional current coordination stage for orchestrator use

        Yields:
            StreamChunk: Streaming response chunks
        """

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

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        """Get current agent status and state."""

    @abstractmethod
    async def reset(self) -> None:
        """Reset agent state for new conversation."""

    @abstractmethod
    def get_configurable_system_message(self) -> Optional[str]:
        """
        Get the user-configurable part of the system message.

        Returns the domain expertise, role definition, or custom instructions
        that were configured for this agent, without backend-specific details.

        Returns:
            The configurable system message if available, None otherwise
        """

    # Common conversation management
    def get_conversation_history(self) -> List[Dict[str, Any]]:
        """Get full conversation history."""
        return self.conversation_history.copy()

    def add_to_history(self, role: str, content: str, **kwargs) -> None:
        """Add message to conversation history."""
        message = {"role": role, "content": content}
        message.update(kwargs)  # Support tool_calls, tool_call_id, etc.
        self.conversation_history.append(message)

    def add_tool_message(self, tool_call_id: str, result: str) -> None:
        """Add tool result to conversation history."""
        self.add_to_history("tool", result, tool_call_id=tool_call_id)

    def get_last_tool_calls(self) -> List[Dict[str, Any]]:
        """Get tool calls from the last assistant message."""
        for message in reversed(self.conversation_history):
            if message.get("role") == "assistant" and "tool_calls" in message:
                return message["tool_calls"]
        return []

    def get_session_id(self) -> str:
        """Get session identifier."""
        return self.session_id


class SingleAgent(ChatAgent):
    """
    Individual agent implementation with direct backend communication.

    This class wraps a single LLM backend and provides the standard chat interface,
    making it interchangeable with the MassGen orchestrator from the user's perspective.
    """

    def __init__(
        self,
        backend: LLMBackend,
        agent_id: Optional[str] = None,
        system_message: Optional[str] = None,
        session_id: Optional[str] = None,
        conversation_memory: Optional[ConversationMemory] = None,
        persistent_memory: Optional[PersistentMemoryBase] = None,
        context_monitor: Optional[Any] = None,
        record_all_tool_calls: bool = False,
        record_reasoning: bool = False,
    ):
        """
        Initialize single agent.

        Args:
            backend: LLM backend for this agent
            agent_id: Optional agent identifier
            system_message: Optional system message for the agent
            session_id: Optional session identifier
            conversation_memory: Optional conversation memory instance
            persistent_memory: Optional persistent memory instance
            context_monitor: Optional context window monitor for tracking token usage
            record_all_tool_calls: If True, record ALL tool calls to memory (including intermediate MCP tools)
            record_reasoning: If True, record reasoning/thinking chunks to memory
        """
        super().__init__(session_id, conversation_memory, persistent_memory)
        self.backend = backend
        self.agent_id = agent_id or f"agent_{uuid.uuid4().hex[:8]}"
        self.system_message = system_message
        self.context_monitor = context_monitor
        self._turn_number = 0

        # Track orchestrator turn number (for turn-aware memory)
        self._orchestrator_turn = None

        # Track if compression has occurred (for smart retrieval)
        self._compression_has_occurred = False

        # Retrieval configuration (defaults, can be overridden from config)
        self._retrieval_limit = 5  # Number of memory facts to retrieve from mem0
        self._retrieval_exclude_recent = True  # Don't retrieve before compression (avoid duplicates)

        # Track previous winning agents for shared memory retrieval
        # Format: [{"agent_id": "agent_b", "turn": 1}, {"agent_id": "agent_a", "turn": 2}]
        self._previous_winners = []

        # Memory recording configuration
        self._record_all_tool_calls = record_all_tool_calls  # Record ALL tools (not just workflow)
        self._record_reasoning = record_reasoning  # Record reasoning chunks

        # Create context compressor if monitor and conversation_memory exist
        self.context_compressor = None
        if self.context_monitor and self.conversation_memory:
            from .memory._compression import ContextCompressor
            from .token_manager.token_manager import TokenCostCalculator

            self.context_compressor = ContextCompressor(
                token_calculator=TokenCostCalculator(),
                conversation_memory=self.conversation_memory,
                persistent_memory=self.persistent_memory,
            )
            logger.info(f"🗜️  Context compressor created for {self.agent_id}")

        # Add system message to history if provided
        if self.system_message:
            self.conversation_history.append({"role": "system", "content": self.system_message})

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

    async def _process_stream(self, backend_stream, tools: List[Dict[str, Any]] = None) -> AsyncGenerator[StreamChunk, None]:
        """Common streaming logic for processing backend responses."""
        assistant_response = ""
        tool_calls = []
        complete_message = None
        messages_to_record = []

        # Optional accumulators (based on config)
        all_tool_calls_executed = [] if self._record_all_tool_calls else None
        reasoning_chunks = [] if self._record_reasoning else None
        reasoning_summaries = [] if self._record_reasoning else None

        try:
            async for chunk in backend_stream:
                chunk_type = self._get_chunk_type_value(chunk)
                if chunk_type == "content":
                    assistant_response += chunk.content
                    yield chunk
                elif chunk_type == "tool_calls":
                    chunk_tool_calls = getattr(chunk, "tool_calls", []) or []
                    tool_calls.extend(chunk_tool_calls)

                    # Optionally accumulate ALL tool calls for memory
                    if self._record_all_tool_calls and chunk_tool_calls:
                        all_tool_calls_executed.extend(chunk_tool_calls)
                        logger.debug(f"   🔧 [ALL mode] Accumulated {len(chunk_tool_calls)} tool(s), total: {len(all_tool_calls_executed)}")

                    yield chunk
                elif chunk_type == "reasoning":
                    # Optionally accumulate reasoning chunks for memory
                    if self._record_reasoning and hasattr(chunk, "content") and chunk.content:
                        reasoning_chunks.append(chunk.content)
                    yield chunk
                elif chunk_type == "reasoning_summary":
                    # Optionally accumulate reasoning summaries for memory
                    if self._record_reasoning and hasattr(chunk, "content") and chunk.content:
                        reasoning_summaries.append(chunk.content)
                    yield chunk
                elif chunk_type == "mcp_status":
                    # Optionally track MCP tool calls for memory (if record_all_tool_calls enabled)
                    if self._record_all_tool_calls and all_tool_calls_executed is not None:
                        import re

                        content = getattr(chunk, "content", "")
                        status = getattr(chunk, "status", "")

                        # Status 1: Tool call initiated - "🔧 [MCP Tool] Calling tool_name..."
                        if status == "mcp_tool_called" and "Calling " in content:
                            match = re.search(r"Calling ([^\s\.]+)", content)
                            if match:
                                tool_name = match.group(1)
                                all_tool_calls_executed.append(
                                    {
                                        "name": tool_name,
                                        "type": "mcp_tool",
                                        "arguments": "",  # Will be filled in next chunk
                                        "result": "",  # Will be filled in later chunk
                                    },
                                )
                                logger.debug(f"   🔧 [MCP tracking] Started tracking: {tool_name}")

                        # Status 2: Arguments - "Arguments for Calling tool_name: {...}"
                        elif status == "function_call" and "Arguments for Calling " in content:
                            match = re.search(r"Arguments for Calling ([^\s:]+): (.+)", content)
                            if match and all_tool_calls_executed:
                                tool_name = match.group(1)
                                args = match.group(2)
                                # Update the last tool call with arguments
                                for tool in reversed(all_tool_calls_executed):
                                    if tool.get("name") == tool_name and not tool.get("arguments"):
                                        tool["arguments"] = args
                                        logger.debug(f"   🔧 [MCP tracking] Added args for: {tool_name}")
                                        break

                        # Status 3: Results - "Results for Calling tool_name: [...]"
                        elif status == "function_call_output" and "Results for Calling " in content:
                            match = re.search(r"Results for Calling ([^\s:]+): (.+)", content, re.DOTALL)
                            if match and all_tool_calls_executed:
                                tool_name = match.group(1)
                                result = match.group(2)
                                # Update the last tool call with results (no truncation - send full data to mem0)
                                for tool in reversed(all_tool_calls_executed):
                                    if tool.get("name") == tool_name and not tool.get("result"):
                                        tool["result"] = result
                                        logger.debug(f"   🔧 [MCP tracking] Added result for: {tool_name}")
                                        break

                    yield chunk
                elif chunk_type == "complete_message":
                    # Backend provided the complete message structure
                    complete_message = chunk.complete_message
                    # Don't yield this - it's for internal use
                elif chunk_type == "complete_response":
                    # Backend provided the raw Responses API response
                    if chunk.response:
                        complete_message = chunk.response

                        # Extract and yield tool calls for orchestrator processing
                        if isinstance(chunk.response, dict) and "output" in chunk.response:
                            response_tool_calls = []
                            for output_item in chunk.response["output"]:
                                if output_item.get("type") == "function_call":
                                    response_tool_calls.append(output_item)
                                    tool_calls.append(output_item)  # Also store for fallback

                            # Yield tool calls so orchestrator can process them
                            if response_tool_calls:
                                yield StreamChunk(type="tool_calls", tool_calls=response_tool_calls)
                    # Complete response is for internal use - don't yield it
                elif chunk_type == "done":
                    # Debug: Log what we have before assembling
                    logger.debug(f"🔍 [done] assistant_response length: {len(assistant_response)}")

                    # Assemble messages for memory recording
                    # SIMPLIFIED: Just use accumulated assistant_response + optional reasoning + tool calls
                    # (We flatten everything to text in record() anyway, so complex parsing was unnecessary)
                    messages_to_record = []

                    # 1. Add reasoning if enabled and present
                    if self._record_reasoning and reasoning_chunks:
                        combined_reasoning = "\n".join(reasoning_chunks)
                        messages_to_record.append(
                            {
                                "role": "assistant",
                                "content": f"[Reasoning]\n{combined_reasoning}",
                            },
                        )
                        logger.debug(f"   ✅ Added reasoning ({len(combined_reasoning)} chars)")

                    # 2. Add reasoning summaries if enabled and present
                    if self._record_reasoning and reasoning_summaries:
                        combined_summary = "\n".join(reasoning_summaries)
                        messages_to_record.append(
                            {
                                "role": "assistant",
                                "content": f"[Reasoning Summary]\n{combined_summary}",
                            },
                        )
                        logger.debug(f"   ✅ Added reasoning summary ({len(combined_summary)} chars)")

                    # 3. Add main response text (accumulated from all content chunks)
                    if assistant_response.strip():
                        messages_to_record.append(
                            {
                                "role": "assistant",
                                "content": assistant_response.strip(),
                            },
                        )
                        logger.debug(f"   ✅ Added main response ({len(assistant_response)} chars)")

                    # 4. Add tool calls to memory
                    tool_calls_info = []

                    # Debug: Log which path we're taking
                    logger.debug(
                        f"🔍 [done] record_all_tool_calls={self._record_all_tool_calls}, all_tool_calls_executed={len(all_tool_calls_executed) if all_tool_calls_executed is not None else 'None'}",
                    )

                    # Option A: Record ALL tool calls (including intermediate MCP tools)
                    if self._record_all_tool_calls and all_tool_calls_executed is not None and len(all_tool_calls_executed) > 0:
                        for tool_call in all_tool_calls_executed:
                            tool_name = tool_call.get("name", "unknown")
                            tool_args = tool_call.get("arguments", {})
                            tool_result = tool_call.get("result", "")

                            tool_info = f"[Tool Call: {tool_name}]"
                            if tool_args:
                                # Arguments might be string (JSON) or dict
                                args_str = tool_args if isinstance(tool_args, str) else str(tool_args)
                                if args_str:  # Only add if not empty
                                    tool_info += f"\nArguments: {args_str}"
                            if tool_result:
                                # MCP tools captured from mcp_status chunks have results
                                tool_info += f"\nResult: {tool_result}"

                            tool_calls_info.append(tool_info)

                        logger.debug(f"   ✅ Captured {len(all_tool_calls_executed)} tool call(s) (ALL mode)")

                    # Option B: Default - only record workflow tools from complete_message
                    elif complete_message and isinstance(complete_message, dict) and "output" in complete_message:
                        # Store raw output for orchestrator (needs full format)
                        self.conversation_history.extend(complete_message["output"])

                        # Collect tool outputs by call_id
                        tool_outputs_map = {}
                        for output_item in complete_message["output"]:
                            if isinstance(output_item, dict) and output_item.get("type") == "function_call_output":
                                call_id = output_item.get("call_id")
                                output = output_item.get("output", "")
                                if call_id:
                                    tool_outputs_map[call_id] = output

                        # Extract workflow tool calls (new_answer, vote, etc.)
                        for output_item in complete_message["output"]:
                            if not isinstance(output_item, dict):
                                continue

                            if output_item.get("type") == "function_call":
                                tool_name = output_item.get("name", "unknown")
                                tool_args = output_item.get("arguments", {})
                                call_id = output_item.get("call_id", "")

                                # Get the output for this tool call
                                tool_output = tool_outputs_map.get(call_id, "")

                                # Format tool call with full data (no truncation)
                                tool_info = f"[Tool Call: {tool_name}]"
                                if tool_args:
                                    args_str = str(tool_args)
                                    tool_info += f"\nArguments: {args_str}"
                                if tool_output:
                                    output_str = str(tool_output)
                                    tool_info += f"\nResult: {output_str}"

                                tool_calls_info.append(tool_info)
                                logger.debug(f"   ✅ Captured workflow tool call: {tool_name}")

                        logger.debug(f"   ✅ Captured {len(tool_calls_info)} workflow tool call(s)")

                    elif complete_message:
                        # Fallback: add complete_message to conversation_history for orchestrator
                        self.conversation_history.append(complete_message)
                        if isinstance(complete_message, dict) and complete_message.get("content"):
                            messages_to_record.append(complete_message)

                    # Add tool calls message if any were captured (either mode)
                    if tool_calls_info:
                        tool_calls_message = "\n\n".join(tool_calls_info)
                        messages_to_record.append(
                            {
                                "role": "assistant",
                                "content": f"[Tool Usage]\n{tool_calls_message}",
                            },
                        )
                        logger.debug(f"   ✅ Added tool usage to memory ({len(tool_calls_info)} call(s))")

                    # Record to memories
                    logger.debug(f"📋 [done chunk] messages_to_record has {len(messages_to_record)} message(s)")

                    if messages_to_record:
                        logger.debug(f"✅ Will record {len(messages_to_record)} message(s) to memory")
                        # Add to conversation memory (use formatted messages, not raw output)
                        if self.conversation_memory:
                            try:
                                await self.conversation_memory.add(messages_to_record)
                                logger.debug(f"📝 Added {len(messages_to_record)} message(s) to conversation memory")
                            except Exception as e:
                                # Log but don't fail if memory add fails
                                logger.warning(f"⚠️  Failed to add response to conversation memory: {e}")
                        # Record to persistent memory with turn metadata
                        if self.persistent_memory:
                            try:
                                # Include turn number in metadata for temporal filtering
                                logger.debug(f"📝 Recording {len(messages_to_record)} messages to persistent memory (turn {self._orchestrator_turn})")
                                await self.persistent_memory.record(
                                    messages_to_record,
                                    metadata={"turn": self._orchestrator_turn} if self._orchestrator_turn else None,
                                )
                                logger.debug("✅ Successfully recorded to persistent memory")
                            except NotImplementedError:
                                # Memory backend doesn't support record
                                logger.warning("⚠️  Persistent memory doesn't support record()")
                            except Exception as e:
                                # Log but don't fail if memory record fails
                                logger.warning(f"⚠️  Failed to record to persistent memory: {e}")

                    # Log context usage after response (if monitor enabled)
                    if self.context_monitor:
                        # Use conversation history for accurate token count
                        current_history = self.conversation_history if not self.conversation_memory else await self.conversation_memory.get_messages()
                        usage_info = self.context_monitor.log_context_usage(current_history, turn_number=self._turn_number)

                        # Compress if needed
                        if self.context_compressor and usage_info.get("should_compress"):
                            logger.info(
                                f"🔄 Attempting compression for {self.agent_id} " f"({usage_info['current_tokens']:,} → {usage_info['target_tokens']:,} tokens)",
                            )
                            compression_stats = await self.context_compressor.compress_if_needed(
                                messages=current_history,
                                current_tokens=usage_info["current_tokens"],
                                target_tokens=usage_info["target_tokens"],
                                should_compress=True,
                            )

                            # Update conversation_history if compression occurred
                            if compression_stats and self.conversation_memory:
                                # Reload from conversation memory (it was updated by compressor)
                                self.conversation_history = await self.conversation_memory.get_messages()
                                # Mark that compression has occurred
                                self._compression_has_occurred = True
                                logger.info(
                                    f"✅ Conversation history updated after compression: " f"{len(self.conversation_history)} messages",
                                )
                        elif usage_info.get("should_compress") and not self.context_compressor:
                            logger.warning(
                                f"⚠️  Should compress but compressor not available " f"(monitor={self.context_monitor is not None}, " f"conv_mem={self.conversation_memory is not None})",
                            )
                    yield chunk
                else:
                    yield chunk

        except Exception as e:
            error_msg = f"Error: {str(e)}"
            self.add_to_history("assistant", error_msg)
            yield StreamChunk(type="content", content=error_msg)
            yield StreamChunk(type="error", error=str(e))

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]] = None,
        reset_chat: bool = False,
        clear_history: bool = False,
        current_stage: CoordinationStage = None,
        orchestrator_turn: Optional[int] = None,
        previous_winners: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Process messages through single backend with tool support.

        Args:
            orchestrator_turn: Current orchestrator turn number (for turn-aware memory)
            previous_winners: List of previous winning agents with turns
                             Format: [{"agent_id": "agent_b", "turn": 1}, ...]
        """
        # Update orchestrator turn if provided
        if orchestrator_turn is not None:
            logger.debug(f"🔍 [chat] Setting orchestrator_turn={orchestrator_turn} for {self.agent_id}")
            self._orchestrator_turn = orchestrator_turn

        # Update previous winners if provided
        if previous_winners is not None:
            logger.debug(f"🔍 [chat] Setting previous_winners={previous_winners} for {self.agent_id}")
            self._previous_winners = previous_winners
        else:
            logger.debug(f"🔍 [chat] No previous_winners provided to {self.agent_id} (current: {self._previous_winners})")
        if clear_history:
            # Clear history but keep system message if it exists
            system_messages = [msg for msg in self.conversation_history if msg.get("role") == "system"]
            self.conversation_history = system_messages.copy()
            # Clear backend history while maintaining session
            if self.backend.is_stateful():
                await self.backend.clear_history()
            # Clear conversation memory if available
            if self.conversation_memory:
                await self.conversation_memory.clear()

        if reset_chat:
            # Skip pre-restart recording - messages are already recorded via done chunks
            # Pre-restart would duplicate content and include orchestrator system prompts (noise)
            # The conversation_memory contains:
            # 1. User messages - will be in new conversation after reset
            # 2. Agent responses - already recorded to persistent_memory via done chunks
            # 3. System messages - orchestrator prompts, don't want in long-term memory
            logger.debug(f"🔄 Resetting chat for {self.agent_id} (skipping pre-restart recording - already captured via done chunks)")

            # Reset conversation history to the provided messages
            self.conversation_history = messages.copy()
            # Reset backend state completely
            if self.backend.is_stateful():
                await self.backend.reset_state()
            # Reset conversation memory
            if self.conversation_memory:
                await self.conversation_memory.clear()
                await self.conversation_memory.add(messages)
            backend_messages = self.conversation_history.copy()
        else:
            # Regular conversation - append new messages to agent's history
            self.conversation_history.extend(messages)
            # Add to conversation memory
            if self.conversation_memory:
                try:
                    await self.conversation_memory.add(messages)
                except Exception as e:
                    # Log but don't fail if memory add fails
                    logger.warning(f"Failed to add messages to conversation memory: {e}")
            backend_messages = self.conversation_history.copy()

        # Retrieve relevant persistent memories if available
        # ALWAYS retrieve on reset_chat (to restore recent context after restart)
        # Otherwise, only retrieve if compression has occurred (to avoid duplicating recent context)
        memory_context = ""
        should_retrieve = self.persistent_memory and (reset_chat or self._compression_has_occurred or not self._retrieval_exclude_recent)  # Always retrieve on reset to restore context

        if should_retrieve:
            try:
                # Log retrieval reason and scope
                if reset_chat:
                    logger.info(
                        f"🔄 Retrieving memories after reset for {self.agent_id} " f"(restoring recent context + {len(self._previous_winners) if self._previous_winners else 0} winner(s))...",
                    )
                elif self._previous_winners:
                    logger.info(
                        f"🔍 Retrieving memories for {self.agent_id} + {len(self._previous_winners)} previous winner(s) " f"(limit={self._retrieval_limit}/agent)...",
                    )
                    logger.debug(f"   Previous winners: {self._previous_winners}")
                else:
                    logger.info(
                        f"🔍 Retrieving memories for {self.agent_id} " f"(limit={self._retrieval_limit}, compressed={self._compression_has_occurred})...",
                    )

                memory_context = await self.persistent_memory.retrieve(
                    messages,
                    limit=self._retrieval_limit,
                    previous_winners=self._previous_winners if self._previous_winners else None,
                )

                if memory_context:
                    memory_lines = memory_context.strip().split("\n")
                    logger.info(
                        f"💭 Retrieved {len(memory_lines)} memory fact(s) from mem0",
                    )
                    # Show preview at INFO level (truncate to first 300 chars for readability)
                    preview = memory_context[:300] + "..." if len(memory_context) > 300 else memory_context
                    logger.info(f"   📝 Preview:\n{preview}")
                else:
                    logger.info("   ℹ️  No relevant memories found")
            except NotImplementedError:
                logger.debug("   Persistent memory doesn't support retrieval")
            except Exception as e:
                logger.warning(f"⚠️  Failed to retrieve from persistent memory: {e}")
        elif self.persistent_memory and self._retrieval_exclude_recent:
            logger.debug(
                f"⏭️  Skipping retrieval for {self.agent_id} " f"(no compression yet, all context in conversation_memory)",
            )

        # Handle stateful vs stateless backends differently
        if self.backend.is_stateful():
            # Stateful: only send new messages, backend maintains context
            backend_messages = messages.copy()
            # Inject memory context before user messages if available
            if memory_context:
                memory_msg = {
                    "role": "system",
                    "content": f"Relevant memories:\n{memory_context}",
                }
                backend_messages.insert(0, memory_msg)
        else:
            # Stateless: send full conversation history
            backend_messages = self.conversation_history.copy()
            # Inject memory context after system message but before conversation
            if memory_context:
                memory_msg = {
                    "role": "system",
                    "content": f"Relevant memories:\n{memory_context}",
                }
                # Insert after existing system messages
                system_count = sum(1 for msg in backend_messages if msg.get("role") == "system")
                backend_messages.insert(system_count, memory_msg)

        if current_stage:
            self.backend.set_stage(current_stage)

        # Log context usage before processing (if monitor enabled)
        self._turn_number += 1
        if self.context_monitor:
            self.context_monitor.log_context_usage(backend_messages, turn_number=self._turn_number)

        # Create backend stream and process it
        backend_stream = self.backend.stream_with_tools(
            messages=backend_messages,
            tools=tools,  # Use provided tools (for MassGen workflow)
            agent_id=self.agent_id,
            session_id=self.session_id,
            **self._get_backend_params(),
        )

        async for chunk in self._process_stream(backend_stream, tools):
            logger.info(f"🔹 [chat] Yielding chunk: {chunk}")
            yield chunk

    def _get_backend_params(self) -> Dict[str, Any]:
        """Get additional backend parameters. Override in subclasses."""
        return {}

    def get_status(self) -> Dict[str, Any]:
        """Get current agent status."""
        return {
            "agent_type": "single",
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "system_message": self.system_message,
            "conversation_length": len(self.conversation_history),
        }

    async def reset(self) -> None:
        """Reset conversation for new chat."""
        self.conversation_history.clear()

        # Reset stateful backend if needed
        if self.backend.is_stateful():
            await self.backend.reset_state()

        # Clear conversation memory (not persistent memory)
        if self.conversation_memory:
            await self.conversation_memory.clear()

        # Re-add system message if it exists
        if self.system_message:
            self.conversation_history.append({"role": "system", "content": self.system_message})

    def get_configurable_system_message(self) -> Optional[str]:
        """Get the user-configurable part of the system message."""
        return self.system_message

    def set_model(self, model: str) -> None:
        """Set the model for this agent."""
        self.model = model

    def set_system_message(self, system_message: str) -> None:
        """Set or update the system message."""
        self.system_message = system_message

        # Remove old system message if exists
        if self.conversation_history and self.conversation_history[0].get("role") == "system":
            self.conversation_history.pop(0)

        # Add new system message at the beginning
        self.conversation_history.insert(0, {"role": "system", "content": system_message})


class ConfigurableAgent(SingleAgent):
    """
    Single agent that uses AgentConfig for advanced configuration.

    This bridges the gap between SingleAgent and the MassGen system by supporting
    all the advanced configuration options (web search, code execution, etc.)
    while maintaining the simple chat interface.

    TODO: Consider merging with SingleAgent. The main difference is:
    - SingleAgent: backend parameters passed directly to constructor/methods
    - ConfigurableAgent: backend parameters come from AgentConfig object

    Could be unified by making SingleAgent accept an optional config parameter
    and using _get_backend_params() pattern for all parameter sources.
    """

    def __init__(
        self,
        config,  # AgentConfig - avoid circular import
        backend: LLMBackend,
        session_id: Optional[str] = None,
        conversation_memory: Optional[ConversationMemory] = None,
        persistent_memory: Optional[PersistentMemoryBase] = None,
        context_monitor: Optional[Any] = None,
        record_all_tool_calls: bool = False,
        record_reasoning: bool = False,
    ):
        """
        Initialize configurable agent.

        Args:
            config: AgentConfig with all settings
            backend: LLM backend
            session_id: Optional session identifier
            conversation_memory: Optional conversation memory instance
            persistent_memory: Optional persistent memory instance
            context_monitor: Optional context window monitor for tracking token usage
            record_all_tool_calls: If True, record ALL tool calls to memory (including intermediate MCP tools)
            record_reasoning: If True, record reasoning/thinking chunks to memory
        """
        # Extract system message without triggering deprecation warning
        system_message = None
        if hasattr(config, "_custom_system_instruction"):
            system_message = config._custom_system_instruction

        super().__init__(
            backend=backend,
            agent_id=config.agent_id,
            system_message=system_message,
            session_id=session_id,
            conversation_memory=conversation_memory,
            persistent_memory=persistent_memory,
            context_monitor=context_monitor,
            record_all_tool_calls=record_all_tool_calls,
            record_reasoning=record_reasoning,
        )
        self.config = config

        # ConfigurableAgent relies on backend_params for model configuration

    def _get_backend_params(self) -> Dict[str, Any]:
        """Get backend parameters from config."""
        return self.config.get_backend_params()

    def get_status(self) -> Dict[str, Any]:
        """Get current agent status with config details."""
        status = super().get_status()
        status.update(
            {
                "agent_type": "configurable",
                "config": self.config.to_dict(),
                "capabilities": {
                    "web_search": self.config.backend_params.get("enable_web_search", False),
                    "code_execution": self.config.backend_params.get("enable_code_interpreter", False),
                },
            },
        )
        return status

    def get_configurable_system_message(self) -> Optional[str]:
        """Get the user-configurable part of the system message for ConfigurableAgent."""
        # Try multiple sources in order of preference

        # First check if backend has system prompt configuration
        if self.config and self.config.backend_params:
            backend_params = self.config.backend_params

            # For Claude Code: prefer system_prompt (complete override)
            if "system_prompt" in backend_params:
                return backend_params["system_prompt"]

            # Then append_system_prompt (additive)
            if "append_system_prompt" in backend_params:
                return backend_params["append_system_prompt"]

        # Fall back to custom_system_instruction (deprecated but still supported)
        # Access private attribute directly to avoid deprecation warning
        if self.config and hasattr(self.config, "_custom_system_instruction") and self.config._custom_system_instruction:
            return self.config._custom_system_instruction

        # Finally fall back to parent class implementation
        return super().get_configurable_system_message()


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def create_simple_agent(backend: LLMBackend, system_message: str = None, agent_id: str = None) -> SingleAgent:
    """Create a simple single agent."""
    # Use MassGen evaluation system message if no custom system message provided
    if system_message is None:
        from .message_templates import MessageTemplates

        templates = MessageTemplates()
        system_message = templates.evaluation_system_message()
    return SingleAgent(backend=backend, agent_id=agent_id, system_message=system_message)


def create_expert_agent(domain: str, backend: LLMBackend, model: str = "gpt-4o-mini") -> ConfigurableAgent:
    """Create an expert agent for a specific domain."""
    from .agent_config import AgentConfig

    config = AgentConfig.for_expert_domain(domain, model=model)
    return ConfigurableAgent(config=config, backend=backend)


def create_research_agent(backend: LLMBackend, model: str = "gpt-4o-mini") -> ConfigurableAgent:
    """Create a research agent with web search capabilities."""
    from .agent_config import AgentConfig

    config = AgentConfig.for_research_task(model=model)
    return ConfigurableAgent(config=config, backend=backend)


def create_computational_agent(backend: LLMBackend, model: str = "gpt-4o-mini") -> ConfigurableAgent:
    """Create a computational agent with code execution."""
    from .agent_config import AgentConfig

    config = AgentConfig.for_computational_task(model=model)
    return ConfigurableAgent(config=config, backend=backend)
