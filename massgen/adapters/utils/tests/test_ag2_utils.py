# -*- coding: utf-8 -*-
"""
Unit tests for AG2 utility functions.
"""
from unittest.mock import MagicMock

from massgen.adapters.utils.ag2_utils import (
    create_llm_config,
    get_group_initial_message,
    get_user_agent_initial_system_message,
    postprocess_group_chat_results,
    register_tools_for_agent,
    unregister_tools_for_agent,
)


def test_create_llm_config_from_dict():
    """Test creating LLMConfig from dictionary."""
    config_dict = {
        "api_type": "openai",
        "model": "gpt-4o",
        "temperature": 0.7,
    }

    llm_config = create_llm_config(config_dict)

    # Should create LLMConfig instance
    assert llm_config is not None
    # Should contain config_list
    assert hasattr(llm_config, "config_list")


def test_create_llm_config_from_list():
    """Test creating LLMConfig from list of configs."""
    config_list = [
        {"api_type": "openai", "model": "gpt-4o"},
        {"api_type": "google", "model": "gemini-pro"},
    ]

    llm_config = create_llm_config(config_list)

    # Should create LLMConfig instance
    assert llm_config is not None
    assert hasattr(llm_config, "config_list")


def test_postprocess_group_chat_results():
    """Test postprocessing of group chat results."""
    messages = [
        {"name": "Agent1", "content": "Hello", "role": "user"},
        {"name": "Agent2", "content": "Hi there", "role": "user"},
    ]

    result = postprocess_group_chat_results(messages)

    # Should add sender tags to content
    assert "<SENDER>: Agent1 </SENDER>" in result[0]["content"]
    assert "<SENDER>: Agent2 </SENDER>" in result[1]["content"]

    # Should change role to assistant
    assert result[0]["role"] == "assistant"
    assert result[1]["role"] == "assistant"


def test_postprocess_group_chat_results_empty_content():
    """Test postprocessing with empty content."""
    messages = [
        {"name": "Agent1", "content": "", "role": "user"},
        {"name": "Agent2", "content": None, "role": "user"},
    ]

    result = postprocess_group_chat_results(messages)

    # Should not add sender tags for empty content
    assert result[0]["content"] == ""
    assert result[1]["content"] is None

    # Should still change role
    assert result[0]["role"] == "assistant"
    assert result[1]["role"] == "assistant"


def test_get_group_initial_message():
    """Test getting initial message for group chat."""
    message = get_group_initial_message()

    # Should return a dict with role and content
    assert isinstance(message, dict)
    assert "role" in message
    assert "content" in message

    # Should be system role
    assert message["role"] == "system"

    # Content should mention key concepts
    assert "CURRENT ANSWER" in message["content"]
    assert "ORIGINAL MESSAGE" in message["content"]


def test_get_user_agent_initial_system_message():
    """Test getting user agent system message."""
    message = get_user_agent_initial_system_message()

    # Should return a string
    assert isinstance(message, str)

    # Should mention workflow tools
    assert "vote" in message.lower() or "new_answer" in message.lower()

    # Should mention the User agent role
    assert "User" in message


def test_register_tools_for_agent():
    """Test registering tools with agent."""
    mock_agent = MagicMock()
    tools = [
        {
            "type": "function",
            "function": {"name": "search", "description": "Search tool"},
        },
        {
            "type": "function",
            "function": {"name": "calc", "description": "Calculator tool"},
        },
    ]

    register_tools_for_agent(tools, mock_agent)

    # Should call update_tool_signature for each tool
    assert mock_agent.update_tool_signature.call_count == len(tools)

    # Should be called with is_remove=False
    for call in mock_agent.update_tool_signature.call_args_list:
        assert call[1]["is_remove"] is False


def test_unregister_tools_for_agent():
    """Test unregistering tools from agent."""
    mock_agent = MagicMock()
    tools = [
        {
            "type": "function",
            "function": {"name": "search", "description": "Search tool"},
        },
    ]

    unregister_tools_for_agent(tools, mock_agent)

    # Should call update_tool_signature with is_remove=True
    mock_agent.update_tool_signature.assert_called_once()
    call_kwargs = mock_agent.update_tool_signature.call_args[1]
    assert call_kwargs["is_remove"] is True
