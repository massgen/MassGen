# -*- coding: utf-8 -*-
"""
Workflow toolkits for MassGen coordination.
"""

from typing import Dict, List, Optional

from .base import BaseToolkit, ToolType
from .new_answer import NewAnswerToolkit
from .post_evaluation import PostEvaluationToolkit
from .vote import VoteToolkit

__all__ = [
    "BaseToolkit",
    "ToolType",
    "NewAnswerToolkit",
    "VoteToolkit",
    "PostEvaluationToolkit",
    "get_workflow_tools",
    "get_post_evaluation_tools",
]


def get_workflow_tools(
    valid_agent_ids: Optional[List[str]] = None,
    template_overrides: Optional[Dict] = None,
    api_format: str = "chat_completions",
) -> List[Dict]:
    """
    Get workflow tool definitions with proper formatting.

    Args:
        valid_agent_ids: List of valid agent IDs for voting
        template_overrides: Optional template overrides
        api_format: API format to use (chat_completions, claude, response)

    Returns:
        List of tool definitions
    """
    tools = []

    # Create config for tools
    config = {
        "api_format": api_format,
        "enable_workflow_tools": True,
        "valid_agent_ids": valid_agent_ids,
    }

    # Get new_answer tool
    new_answer_toolkit = NewAnswerToolkit(template_overrides=template_overrides)
    tools.extend(new_answer_toolkit.get_tools(config))

    # Get vote tool
    vote_toolkit = VoteToolkit(
        valid_agent_ids=valid_agent_ids,
        template_overrides=template_overrides,
    )
    tools.extend(vote_toolkit.get_tools(config))

    return tools


def get_post_evaluation_tools(
    template_overrides: Optional[Dict] = None,
    api_format: str = "chat_completions",
) -> List[Dict]:
    """
    Get post-evaluation tool definitions (submit and restart_orchestration).

    Args:
        template_overrides: Optional template overrides
        api_format: API format to use (chat_completions, claude, response)

    Returns:
        List of tool definitions [submit, restart_orchestration]
    """
    config = {
        "api_format": api_format,
        "enable_post_evaluation_tools": True,
    }

    post_eval_toolkit = PostEvaluationToolkit(template_overrides=template_overrides)
    return post_eval_toolkit.get_tools(config)
