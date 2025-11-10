"""
Span Data Structures for RL Trace Collection

This module defines different types of spans that record events
during agent execution, following the design from
massgen_rl_integration_design.md
"""

from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


@dataclass
class PromptSpan:
    """Records an LLM prompt/response interaction"""
    span_id: str
    span_type: str = "prompt"
    timestamp: float = 0.0

    # LLM call information
    input: str = ""  # Complete prompt
    output: str = ""  # LLM response
    model: str = ""

    # Optional: token usage
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None

    # Optional: reasoning process
    reasoning: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return asdict(self)


@dataclass
class ToolSpan:
    """Records a tool call event"""
    span_id: str
    span_type: str = "tool"
    timestamp: float = 0.0

    # Tool information
    tool_name: str = ""
    arguments: Dict[str, Any] = None
    result: Any = None

    # Execution information
    success: bool = True
    execution_time: float = 0.0
    error: Optional[str] = None

    def __post_init__(self):
        if self.arguments is None:
            self.arguments = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        data = asdict(self)
        # Convert result to string if it's not JSON serializable
        if self.result is not None and not isinstance(self.result, (str, int, float, bool, list, dict, type(None))):
            data['result'] = str(self.result)
        return data


@dataclass
class RewardSpan:
    """Records a reward signal"""
    span_id: str
    span_type: str = "reward"
    timestamp: float = 0.0

    # Reward information
    reward: float = 0.0
    reward_type: str = ""  # "tool", "answer_quality", "coordination", "human"
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return asdict(self)


@dataclass
class CoordinationSpan:
    """Records a coordination event in multi-agent orchestration"""
    span_id: str
    span_type: str = "coordination"
    timestamp: float = 0.0

    # Coordination action
    action_type: str = ""  # "vote", "new_answer", "restart"
    action_data: Dict[str, Any] = None

    # State information
    agent_states: Optional[Dict[str, Any]] = None
    coordination_round: int = 0

    def __post_init__(self):
        if self.action_data is None:
            self.action_data = {}
        if self.agent_states is None:
            self.agent_states = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        data = asdict(self)
        # Simplify agent_states to avoid circular references
        if self.agent_states:
            simplified_states = {}
            for agent_id, state in self.agent_states.items():
                if hasattr(state, '__dict__'):
                    simplified_states[agent_id] = {
                        'has_voted': getattr(state, 'has_voted', False),
                        'has_answer': getattr(state, 'answer', None) is not None,
                    }
                else:
                    simplified_states[agent_id] = str(state)
            data['agent_states'] = simplified_states
        return data


@dataclass
class ContentSpan:
    """Records content generation (text, reasoning, etc.)"""
    span_id: str
    span_type: str = "content"
    timestamp: float = 0.0

    # Content information
    content: str = ""
    source: Optional[str] = None  # agent_id or source identifier

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return asdict(self)


@dataclass
class ReasoningSpan:
    """Records reasoning process"""
    span_id: str
    span_type: str = "reasoning"
    timestamp: float = 0.0

    # Reasoning information
    reasoning: str = ""
    source: Optional[str] = None  # agent_id

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return asdict(self)
