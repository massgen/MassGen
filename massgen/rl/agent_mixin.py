"""
RL Agent Mixin

This module provides a mixin class to add RL trace collection
capabilities to existing ChatAgent classes.
"""

from typing import Any, AsyncGenerator, Dict, List, Optional
import time

from .config import RLConfig
from .trace_collector import TraceCollector
from .reward_computer import RewardComputer
from ..stream_chunk import ChunkType, TextStreamChunk


class RLAgentMixin:
    """
    Mixin to add RL trace collection capabilities to ChatAgent.

    This mixin can be combined with any ChatAgent subclass to enable
    automatic collection of execution traces for reinforcement learning.

    Usage:
        class RLSingleAgent(RLAgentMixin, SingleAgent):
            pass

        agent = RLSingleAgent(
            backend=backend,
            agent_id="agent_1",
            enable_rl=True,
            rl_config=RLConfig(...)
        )
    """

    def __init__(
        self,
        *args,
        enable_rl: bool = False,
        rl_config: Optional[RLConfig] = None,
        **kwargs
    ):
        """
        Initialize RL capabilities.

        Args:
            enable_rl: Whether to enable RL trace collection
            rl_config: RL configuration
            *args, **kwargs: Arguments for the parent class
        """
        # Initialize parent class first
        super().__init__(*args, **kwargs)

        # RL configuration
        self.enable_rl = enable_rl
        self.rl_config = rl_config or RLConfig()

        # Initialize RL components if enabled
        if self.enable_rl:
            # Get agent_id from self (set by parent class)
            agent_id = getattr(self, 'agent_id', 'unknown_agent')

            self.trace_collector = TraceCollector(
                agent_id=agent_id,
                store_config=self.rl_config.store_config
            )
            self.reward_computer = RewardComputer()
            self._current_trace_id = None
            self._current_tool_calls = {}  # Track ongoing tool calls

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]] = None,
        **kwargs
    ) -> AsyncGenerator[TextStreamChunk, None]:
        """
        Override chat method to add trace collection.

        This method wraps the parent's chat method and collects
        traces during execution.

        Args:
            messages: Conversation messages
            tools: Optional tools
            **kwargs: Additional arguments

        Yields:
            StreamChunk: Streaming response chunks
        """
        # Start trace if RL is enabled
        if self.enable_rl:
            # Extract task from messages
            task = self._extract_task_from_messages(messages)

            # Get backend info if available
            backend_name = getattr(
                getattr(self, 'backend', None),
                'get_provider_name',
                lambda: 'unknown'
            )()
            model = getattr(getattr(self, 'backend', None), 'model', 'unknown')

            self._current_trace_id = self.trace_collector.start_trace(
                task=task,
                metadata={
                    'agent_id': getattr(self, 'agent_id', 'unknown'),
                    'backend': backend_name,
                    'model': model,
                    'num_messages': len(messages),
                    'has_tools': tools is not None and len(tools) > 0
                }
            )

        # Call parent chat method and collect spans
        try:
            async for chunk in super().chat(messages, tools=tools, **kwargs):
                # Collect span from chunk
                if self.enable_rl:
                    await self._collect_span_from_chunk(chunk)

                yield chunk

            # Successfully completed
            if self.enable_rl and self._current_trace_id:
                await self.trace_collector.end_trace(self._current_trace_id)
                self._current_trace_id = None

        except Exception as e:
            # Handle errors
            if self.enable_rl and self._current_trace_id:
                await self.trace_collector.fail_trace(
                    self._current_trace_id,
                    error=str(e)
                )
                self._current_trace_id = None
            raise

    def _extract_task_from_messages(self, messages: List[Dict[str, Any]]) -> str:
        """
        Extract task description from messages.

        Args:
            messages: List of messages

        Returns:
            Task description (usually the last user message)
        """
        # Find last user message
        for message in reversed(messages):
            if message.get('role') == 'user':
                content = message.get('content', '')
                # Truncate if too long
                if len(content) > 500:
                    return content[:500] + "..."
                return content

        return "Unknown task"

    async def _collect_span_from_chunk(self, chunk: TextStreamChunk):
        """
        Extract information from StreamChunk and create spans.

        Args:
            chunk: Stream chunk from agent execution
        """
        if not self._current_trace_id:
            return

        # Handle different chunk types
        if chunk.type == ChunkType.TOOL_CALLS:
            # Record tool calls
            if chunk.tool_calls:
                for tool_call in chunk.tool_calls:
                    tool_call_id = tool_call.get('id')
                    tool_name = tool_call.get('function', {}).get('name', 'unknown')
                    arguments_str = tool_call.get('function', {}).get('arguments', '{}')

                    # Parse arguments
                    try:
                        import json
                        arguments = json.loads(arguments_str)
                    except:
                        arguments = {'raw': arguments_str}

                    # Emit tool span (without result yet)
                    self.trace_collector.emit_tool_span(
                        trace_id=self._current_trace_id,
                        tool_name=tool_name,
                        arguments=arguments,
                        tool_call_id=tool_call_id,
                        success=True  # Will be updated when result arrives
                    )

                    # Track for reward computation later
                    self._current_tool_calls[tool_call_id] = {
                        'name': tool_name,
                        'arguments': arguments,
                        'timestamp': time.time()
                    }

        elif chunk.type == ChunkType.CONTENT:
            # Record content generation
            if chunk.content:
                self.trace_collector.emit_content_span(
                    trace_id=self._current_trace_id,
                    content=chunk.content,
                    source=chunk.source
                )

        elif chunk.type == ChunkType.REASONING:
            # Record reasoning
            if chunk.reasoning_delta or chunk.reasoning_text:
                reasoning = chunk.reasoning_text or chunk.reasoning_delta
                self.trace_collector.emit_reasoning_span(
                    trace_id=self._current_trace_id,
                    reasoning=reasoning,
                    source=chunk.source
                )

        elif chunk.type == ChunkType.COMPLETE_MESSAGE:
            # When message is complete, we might have final answer
            # Compute answer quality reward if configured
            if self.rl_config.enable_answer_quality_rewards and chunk.complete_message:
                content = chunk.complete_message.get('content', '')
                if content:
                    answer_reward = self.reward_computer.compute_answer_quality_reward(
                        answer=content
                    )
                    self.trace_collector.emit_reward_span(
                        trace_id=self._current_trace_id,
                        reward=answer_reward,
                        reward_type="answer_quality",
                        reason="Answer quality based on structure and depth"
                    )

    async def _record_tool_result(
        self,
        tool_call_id: str,
        result: Any,
        success: bool = True,
        error: Optional[str] = None
    ):
        """
        Record tool execution result and compute reward.

        This method can be called after a tool execution completes
        to record the result and compute the reward.

        Args:
            tool_call_id: Tool call identifier
            result: Tool execution result
            success: Whether execution succeeded
            error: Error message if failed
        """
        if not self.enable_rl or not self._current_trace_id:
            return

        if tool_call_id not in self._current_tool_calls:
            return

        tool_info = self._current_tool_calls[tool_call_id]

        # Compute tool reward if configured
        if self.rl_config.enable_tool_rewards:
            reward = self.reward_computer.compute_tool_reward(
                tool_call=tool_info,
                result=result
            )

            self.trace_collector.emit_reward_span(
                trace_id=self._current_trace_id,
                reward=reward,
                reward_type="tool",
                reason=f"Tool {tool_info['name']} execution reward"
            )

    def get_rl_statistics(self) -> Dict[str, Any]:
        """
        Get RL collection statistics.

        Returns:
            Dictionary with statistics
        """
        if not self.enable_rl:
            return {"enabled": False}

        return {
            "enabled": True,
            "current_trace_active": self._current_trace_id is not None,
            "current_trace_id": self._current_trace_id,
            "config": {
                "enable_tool_rewards": self.rl_config.enable_tool_rewards,
                "enable_answer_quality_rewards": self.rl_config.enable_answer_quality_rewards,
                "collect_only": self.rl_config.collect_only
            }
        }
