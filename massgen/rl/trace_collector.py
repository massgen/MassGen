"""
Trace Collector for RL Data Collection

This module provides the TraceCollector class that collects
spans during agent execution and saves them as traces.
"""

import time
import uuid
from typing import Any, Dict, Optional

from .trace import Trace
from .spans import (
    PromptSpan,
    ToolSpan,
    RewardSpan,
    CoordinationSpan,
    ContentSpan,
    ReasoningSpan
)
from .store import LightningStore
from .config import StoreConfig


class TraceCollector:
    """
    Collects and manages agent execution traces.

    This class is used by agents to record their execution
    as a sequence of spans, which are then aggregated into traces.
    """

    def __init__(self, agent_id: str, store_config: StoreConfig):
        """
        Initialize trace collector.

        Args:
            agent_id: ID of the agent using this collector
            store_config: Configuration for the store
        """
        self.agent_id = agent_id
        self.store = LightningStore(store_config)
        self.active_traces: Dict[str, Trace] = {}

    def start_trace(self, task: str, metadata: Optional[Dict] = None) -> str:
        """
        Start a new trace.

        Args:
            task: Task description
            metadata: Optional metadata

        Returns:
            Trace ID
        """
        trace_id = str(uuid.uuid4())
        trace = Trace(
            trace_id=trace_id,
            agent_id=self.agent_id,
            task=task,
            metadata=metadata or {},
            start_time=time.time()
        )
        self.active_traces[trace_id] = trace
        return trace_id

    def start_coordination_trace(self, task: str, num_agents: int, metadata: Optional[Dict] = None) -> str:
        """
        Start a coordination trace for orchestrator.

        Args:
            task: Task description
            num_agents: Number of agents involved
            metadata: Optional metadata

        Returns:
            Trace ID
        """
        meta = metadata or {}
        meta['coordination'] = True
        meta['num_agents'] = num_agents
        return self.start_trace(task, meta)

    def emit_prompt_span(
        self,
        trace_id: str,
        prompt: str,
        response: str,
        model: str,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        reasoning: Optional[str] = None
    ):
        """
        Record an LLM prompt span.

        Args:
            trace_id: ID of the trace to add this span to
            prompt: Input prompt
            response: LLM response
            model: Model name
            input_tokens: Optional input token count
            output_tokens: Optional output token count
            reasoning: Optional reasoning text
        """
        if trace_id not in self.active_traces:
            return

        span = PromptSpan(
            span_id=str(uuid.uuid4()),
            span_type="prompt",
            timestamp=time.time(),
            input=prompt,
            output=response,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            reasoning=reasoning
        )
        self.active_traces[trace_id].add_span(span)

    def emit_tool_span(
        self,
        trace_id: str,
        tool_name: str,
        arguments: Dict[str, Any],
        result: Any = None,
        tool_call_id: Optional[str] = None,
        success: bool = True,
        execution_time: float = 0.0,
        error: Optional[str] = None
    ):
        """
        Record a tool call span.

        Args:
            trace_id: ID of the trace
            tool_name: Name of the tool
            arguments: Tool arguments
            result: Tool result
            tool_call_id: Optional tool call ID
            success: Whether tool call succeeded
            execution_time: Execution time in seconds
            error: Error message if failed
        """
        if trace_id not in self.active_traces:
            return

        span = ToolSpan(
            span_id=tool_call_id or str(uuid.uuid4()),
            span_type="tool",
            timestamp=time.time(),
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            success=success,
            execution_time=execution_time,
            error=error
        )
        self.active_traces[trace_id].add_span(span)

    def emit_reward_span(
        self,
        trace_id: str,
        reward: float,
        reward_type: str,
        reason: Optional[str] = None
    ):
        """
        Record a reward span.

        Args:
            trace_id: ID of the trace
            reward: Reward value
            reward_type: Type of reward (tool, answer_quality, coordination, human)
            reason: Optional explanation
        """
        if trace_id not in self.active_traces:
            return

        span = RewardSpan(
            span_id=str(uuid.uuid4()),
            span_type="reward",
            timestamp=time.time(),
            reward=reward,
            reward_type=reward_type,
            reason=reason
        )
        self.active_traces[trace_id].add_span(span)

    def emit_coordination_span(
        self,
        trace_id: str,
        action_type: str,
        action_data: Dict[str, Any],
        agent_states: Optional[Dict[str, Any]] = None,
        coordination_round: int = 0
    ):
        """
        Record a coordination span.

        Args:
            trace_id: ID of the trace
            action_type: Type of coordination action (vote, new_answer, restart)
            action_data: Data about the action
            agent_states: Current agent states
            coordination_round: Current coordination round
        """
        if trace_id not in self.active_traces:
            return

        span = CoordinationSpan(
            span_id=str(uuid.uuid4()),
            span_type="coordination",
            timestamp=time.time(),
            action_type=action_type,
            action_data=action_data,
            agent_states=agent_states,
            coordination_round=coordination_round
        )
        self.active_traces[trace_id].add_span(span)

    def emit_content_span(
        self,
        trace_id: str,
        content: str,
        source: Optional[str] = None
    ):
        """
        Record a content generation span.

        Args:
            trace_id: ID of the trace
            content: Generated content
            source: Source identifier (e.g., agent_id)
        """
        if trace_id not in self.active_traces:
            return

        span = ContentSpan(
            span_id=str(uuid.uuid4()),
            span_type="content",
            timestamp=time.time(),
            content=content,
            source=source or self.agent_id
        )
        self.active_traces[trace_id].add_span(span)

    def emit_reasoning_span(
        self,
        trace_id: str,
        reasoning: str,
        source: Optional[str] = None
    ):
        """
        Record a reasoning span.

        Args:
            trace_id: ID of the trace
            reasoning: Reasoning text
            source: Source identifier
        """
        if trace_id not in self.active_traces:
            return

        span = ReasoningSpan(
            span_id=str(uuid.uuid4()),
            span_type="reasoning",
            timestamp=time.time(),
            reasoning=reasoning,
            source=source or self.agent_id
        )
        self.active_traces[trace_id].add_span(span)

    async def end_trace(self, trace_id: str, status: str = "completed") -> bool:
        """
        End a trace and save it to storage.

        Args:
            trace_id: ID of the trace to end
            status: Final status (completed/failed)

        Returns:
            True if successfully saved
        """
        if trace_id not in self.active_traces:
            return False

        trace = self.active_traces.pop(trace_id)
        trace.status = status
        trace.end()

        # Save to store
        return await self.store.save_trace(trace)

    async def fail_trace(self, trace_id: str, error: Optional[str] = None) -> bool:
        """
        Mark a trace as failed and save it.

        Args:
            trace_id: ID of the trace
            error: Error message

        Returns:
            True if successfully saved
        """
        if trace_id not in self.active_traces:
            return False

        trace = self.active_traces.pop(trace_id)
        trace.mark_failed(error)

        # Save to store
        return await self.store.save_trace(trace)

    def get_active_trace(self, trace_id: str) -> Optional[Trace]:
        """Get an active trace by ID"""
        return self.active_traces.get(trace_id)

    def cancel_trace(self, trace_id: str):
        """Cancel a trace without saving it"""
        if trace_id in self.active_traces:
            del self.active_traces[trace_id]
