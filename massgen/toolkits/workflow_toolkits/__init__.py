# -*- coding: utf-8 -*-
"""
Workflow toolkits for MassGen coordination.
"""

from typing import Dict, List, Optional

from ..registry import toolkit_registry
from .new_answer import NewAnswerToolkit
from .vote import VoteToolkit

__all__ = [
    "NewAnswerToolkit",
    "VoteToolkit",
    "register_workflow_toolkits",
    "get_workflow_tools",
]


def register_workflow_toolkits(providers: Optional[List[str]] = None):
    """
    Register workflow toolkits with specified providers.

    Args:
        providers: List of provider names that support workflow tools.
                  If None, registers for common providers.
    """
    if providers is None:
        # Default providers that commonly use workflow tools
        providers = [
            "openai",
            "azure_openai",
            "claude",
            "gemini",
            "grok",
            "chat_completions",
            "response",
        ]

    # Register new_answer toolkit
    new_answer_toolkit = NewAnswerToolkit()
    toolkit_registry.register(new_answer_toolkit, providers=providers)

    # Register vote toolkit (without specific agent IDs initially)
    vote_toolkit = VoteToolkit()
    toolkit_registry.register(vote_toolkit, providers=providers)


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
