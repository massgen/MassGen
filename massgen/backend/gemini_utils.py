# -*- coding: utf-8 -*-
"""
Gemini-specific structured output models for coordination actions (voting and answer submission).
"""

import enum
from typing import Optional

try:
    from pydantic import BaseModel, Field
except ImportError:
    BaseModel = None
    Field = None


class ActionType(enum.Enum):
    """Action types for structured output."""

    VOTE = "vote"
    NEW_ANSWER = "new_answer"


class PostEvaluationActionType(enum.Enum):
    """Action types for post-evaluation structured output."""

    SUBMIT = "submit"
    RESTART = "restart"


class VoteAction(BaseModel):
    """Structured output for voting action."""

    action: ActionType = Field(default=ActionType.VOTE, description="Action type")
    agent_id: str = Field(description="Anonymous agent ID to vote for (e.g., 'agent1', 'agent2')")
    reason: str = Field(description="Brief reason why this agent has the best answer")


class NewAnswerAction(BaseModel):
    """Structured output for new answer action."""

    action: ActionType = Field(default=ActionType.NEW_ANSWER, description="Action type")
    content: str = Field(description="Your improved answer. If any builtin tools like search or code execution were used, include how they are used here.")


class CoordinationResponse(BaseModel):
    """Structured response for coordination actions."""

    action_type: ActionType = Field(description="Type of action to take")
    vote_data: Optional[VoteAction] = Field(default=None, description="Vote data if action is vote")
    answer_data: Optional[NewAnswerAction] = Field(default=None, description="Answer data if action is new_answer")


class SubmitAction(BaseModel):
    """Structured output for submit action (post-evaluation)."""

    action: PostEvaluationActionType = Field(default=PostEvaluationActionType.SUBMIT, description="Action type")
    confirmed: bool = Field(default=True, description="Confirmation that answer is satisfactory")


class RestartAction(BaseModel):
    """Structured output for restart action (post-evaluation)."""

    action: PostEvaluationActionType = Field(default=PostEvaluationActionType.RESTART, description="Action type")
    reason: str = Field(description="Clear explanation of why the answer is insufficient")
    instructions: str = Field(description="Detailed, actionable guidance for agents on the next attempt")


class PostEvaluationResponse(BaseModel):
    """Structured response for post-evaluation actions."""

    action_type: PostEvaluationActionType = Field(description="Type of post-evaluation action to take")
    submit_data: Optional[SubmitAction] = Field(default=None, description="Submit data if action is submit")
    restart_data: Optional[RestartAction] = Field(default=None, description="Restart data if action is restart")
