"""
Trace Data Structure for RL

This module defines the Trace class that aggregates spans
into a complete trajectory for a task execution.
"""

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Union
import time

from .spans import (
    PromptSpan,
    ToolSpan,
    RewardSpan,
    CoordinationSpan,
    ContentSpan,
    ReasoningSpan
)


@dataclass
class Trace:
    """
    A complete trace of agent execution for a single task.

    A trace contains a sequence of spans that record all events
    during task execution, including LLM calls, tool usage,
    coordination actions, and reward signals.
    """
    trace_id: str
    agent_id: str
    task: str

    # Spans sequence
    spans: List[Union[PromptSpan, ToolSpan, RewardSpan, CoordinationSpan, ContentSpan, ReasoningSpan]] = field(default_factory=list)

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None
    duration: Optional[float] = None

    # Total reward
    total_reward: Optional[float] = None

    # Trajectory status
    status: str = "running"  # "running", "completed", "failed"

    def add_span(self, span: Union[PromptSpan, ToolSpan, RewardSpan, CoordinationSpan, ContentSpan, ReasoningSpan]):
        """Add a span to the trace"""
        self.spans.append(span)

        # Update total reward if this is a reward span
        if isinstance(span, RewardSpan):
            if self.total_reward is None:
                self.total_reward = 0.0
            self.total_reward += span.reward

    def end(self):
        """Mark trace as completed and compute duration"""
        self.end_time = time.time()
        self.duration = self.end_time - self.start_time
        if self.status == "running":
            self.status = "completed"

    def mark_failed(self, error: Optional[str] = None):
        """Mark trace as failed"""
        self.status = "failed"
        if error:
            self.metadata['error'] = error
        self.end()

    def get_reward_spans(self) -> List[RewardSpan]:
        """Get all reward spans in this trace"""
        return [span for span in self.spans if isinstance(span, RewardSpan)]

    def get_tool_spans(self) -> List[ToolSpan]:
        """Get all tool spans in this trace"""
        return [span for span in self.spans if isinstance(span, ToolSpan)]

    def get_prompt_spans(self) -> List[PromptSpan]:
        """Get all prompt spans in this trace"""
        return [span for span in self.spans if isinstance(span, PromptSpan)]

    def get_coordination_spans(self) -> List[CoordinationSpan]:
        """Get all coordination spans in this trace"""
        return [span for span in self.spans if isinstance(span, CoordinationSpan)]

    def to_dict(self) -> Dict[str, Any]:
        """Convert trace to dictionary for serialization"""
        return {
            'trace_id': self.trace_id,
            'agent_id': self.agent_id,
            'task': self.task,
            'spans': [span.to_dict() for span in self.spans],
            'metadata': self.metadata,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'duration': self.duration,
            'total_reward': self.total_reward,
            'status': self.status
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Trace':
        """Create trace from dictionary"""
        # Reconstruct spans
        spans = []
        for span_data in data.get('spans', []):
            span_type = span_data.get('span_type')
            if span_type == 'prompt':
                spans.append(PromptSpan(**span_data))
            elif span_type == 'tool':
                spans.append(ToolSpan(**span_data))
            elif span_type == 'reward':
                spans.append(RewardSpan(**span_data))
            elif span_type == 'coordination':
                spans.append(CoordinationSpan(**span_data))
            elif span_type == 'content':
                spans.append(ContentSpan(**span_data))
            elif span_type == 'reasoning':
                spans.append(ReasoningSpan(**span_data))

        return cls(
            trace_id=data['trace_id'],
            agent_id=data['agent_id'],
            task=data['task'],
            spans=spans,
            metadata=data.get('metadata', {}),
            start_time=data.get('start_time', time.time()),
            end_time=data.get('end_time'),
            duration=data.get('duration'),
            total_reward=data.get('total_reward'),
            status=data.get('status', 'running')
        )
