# -*- coding: utf-8 -*-
"""
Unit tests for AG2Adapter (single agent case only).
"""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from massgen.adapters.ag2_adapter import AG2Adapter
from massgen.adapters.utils.ag2_utils import setup_agent_from_config, setup_api_keys


def test_setup_api_keys_copies_gemini_key():
    """Test that GEMINI_API_KEY is copied to GOOGLE_GEMINI_API_KEY."""
    # Setup
    os.environ["GEMINI_API_KEY"] = "test_key"
    if "GOOGLE_GEMINI_API_KEY" in os.environ:
        del os.environ["GOOGLE_GEMINI_API_KEY"]

    # Execute
    setup_api_keys()

    # Verify
    assert os.environ["GOOGLE_GEMINI_API_KEY"] == "test_key"

    # Cleanup
    del os.environ["GEMINI_API_KEY"]
    del os.environ["GOOGLE_GEMINI_API_KEY"]


@patch("massgen.adapters.utils.ag2_utils.AssistantAgent")
def test_setup_agent_from_config_assistant(mock_assistant):
    """Test setting up AssistantAgent from config."""
    config = {
        "type": "assistant",
        "name": "test_agent",
        "system_message": "You are helpful",
        "llm_config": {
            "api_type": "openai",
            "model": "gpt-4o",
        },
    }

    setup_agent_from_config(config)

    # Verify AssistantAgent was called with correct params
    mock_assistant.assert_called_once()
    call_kwargs = mock_assistant.call_args[1]
    assert call_kwargs["name"] == "test_agent"
    assert call_kwargs["system_message"] == "You are helpful"
    assert call_kwargs["human_input_mode"] == "NEVER"


@patch("massgen.adapters.utils.ag2_utils.ConversableAgent")
def test_setup_agent_from_config_conversable(mock_conversable):
    """Test setting up ConversableAgent from config."""
    config = {
        "type": "conversable",
        "name": "test_agent",
        "llm_config": [{"api_type": "openai", "model": "gpt-4o"}],
    }

    setup_agent_from_config(config)

    # Verify ConversableAgent was called
    mock_conversable.assert_called_once()
    call_kwargs = mock_conversable.call_args[1]
    assert call_kwargs["name"] == "test_agent"
    assert call_kwargs["human_input_mode"] == "NEVER"


def test_setup_agent_missing_llm_config():
    """Test that missing llm_config raises error."""
    config = {
        "type": "assistant",
        "name": "test_agent",
    }

    with pytest.raises(ValueError) as exc_info:
        setup_agent_from_config(config)

    assert "llm_config" in str(exc_info.value)


def test_setup_agent_missing_name():
    """Test that missing name raises error."""
    config = {
        "type": "assistant",
        "llm_config": [{"api_type": "openai", "model": "gpt-4o"}],
    }

    with pytest.raises(ValueError) as exc_info:
        setup_agent_from_config(config)

    assert "name" in str(exc_info.value)


@patch("massgen.adapters.ag2_adapter.setup_agent_from_config")
def test_adapter_init_single_agent(mock_setup):
    """Test adapter initialization with single agent config."""
    mock_agent = MagicMock()
    mock_setup.return_value = mock_agent

    agent_config = {
        "type": "assistant",
        "name": "test",
        "llm_config": {"api_type": "openai", "model": "gpt-4o"},
    }

    adapter = AG2Adapter(agent_config=agent_config)

    # Verify single agent setup
    assert adapter.is_group_chat is False
    assert adapter.agent == mock_agent
    mock_setup.assert_called_once_with(agent_config)


def test_adapter_init_requires_config():
    """Test that adapter requires either agent_config or group_config."""
    with pytest.raises(ValueError) as exc_info:
        AG2Adapter()

    assert "agent_config" in str(exc_info.value) or "group_config" in str(exc_info.value)


def test_adapter_init_rejects_both_configs():
    """Test that adapter rejects both agent_config and group_config."""
    with pytest.raises(ValueError) as exc_info:
        AG2Adapter(
            agent_config={"name": "test", "llm_config": []},
            group_config={"agents": []},
        )

    assert "not both" in str(exc_info.value).lower()


@patch("massgen.adapters.ag2_adapter.setup_agent_from_config")
@pytest.mark.asyncio
async def test_execute_streaming_single_agent(mock_setup):
    """Test streaming execution with single agent."""
    # Setup mock agent
    mock_agent = MagicMock()
    mock_agent.a_generate_reply = AsyncMock(
        return_value={"content": "Test response", "tool_calls": None},
    )
    mock_setup.return_value = mock_agent

    # Create adapter
    agent_config = {
        "type": "assistant",
        "name": "test",
        "llm_config": {"api_type": "openai", "model": "gpt-4o"},
    }
    adapter = AG2Adapter(agent_config=agent_config)

    # Execute streaming
    messages = [{"role": "user", "content": "Hello"}]
    tools = []

    chunks = []
    async for chunk in adapter.execute_streaming(messages, tools):
        chunks.append(chunk)

    # Verify response
    assert len(chunks) > 0
    assert any(c.type == "content" for c in chunks)
    assert any(c.type == "done" for c in chunks)

    # Verify agent was called
    mock_agent.a_generate_reply.assert_called_once_with(messages)


@patch("massgen.adapters.ag2_adapter.setup_agent_from_config")
def test_register_tools_single_agent(mock_setup):
    """Test tool registration with single agent."""
    mock_agent = MagicMock()
    mock_setup.return_value = mock_agent

    agent_config = {
        "type": "assistant",
        "name": "test",
        "llm_config": {"api_type": "openai", "model": "gpt-4o"},
    }
    adapter = AG2Adapter(agent_config=agent_config)

    # Register tools
    tools = [
        {
            "type": "function",
            "function": {"name": "search", "description": "Search tool"},
        },
    ]

    adapter._register_tools(tools)

    # Verify update_tool_signature was called for each tool
    assert mock_agent.update_tool_signature.call_count == len(tools)


@patch("massgen.adapters.ag2_adapter.setup_agent_from_config")
def test_register_tools_empty_list(mock_setup):
    """Test that empty tool list doesn't call update_tool_signature."""
    mock_agent = MagicMock()
    mock_setup.return_value = mock_agent

    agent_config = {
        "type": "assistant",
        "name": "test",
        "llm_config": {"api_type": "openai", "model": "gpt-4o"},
    }
    adapter = AG2Adapter(agent_config=agent_config)

    # Register empty tools
    adapter._register_tools([])

    # Verify update_tool_signature was not called
    mock_agent.update_tool_signature.assert_not_called()


@patch("autogen.coding.LocalCommandLineCodeExecutor")
@patch("massgen.adapters.utils.ag2_utils.AssistantAgent")
def test_setup_agent_with_local_code_executor(mock_assistant, mock_executor):
    """Test setting up agent with LocalCommandLineCodeExecutor."""
    config = {
        "type": "assistant",
        "name": "coder",
        "llm_config": [{"api_type": "openai", "model": "gpt-4o"}],
        "code_execution_config": {
            "executor": {
                "type": "LocalCommandLineCodeExecutor",
                "timeout": 60,
                "work_dir": "./workspace",
            },
        },
    }

    setup_agent_from_config(config)

    # Verify executor was created without 'type' in params
    mock_executor.assert_called_once_with(timeout=60, work_dir="./workspace")

    # Verify AssistantAgent was called with code_execution_config
    call_kwargs = mock_assistant.call_args[1]
    assert "code_execution_config" in call_kwargs
    assert "executor" in call_kwargs["code_execution_config"]


@patch("autogen.coding.DockerCommandLineCodeExecutor")
@patch("massgen.adapters.utils.ag2_utils.ConversableAgent")
def test_setup_agent_with_docker_executor(mock_conversable, mock_executor):
    """Test setting up agent with DockerCommandLineCodeExecutor."""
    config = {
        "type": "conversable",
        "name": "docker_coder",
        "llm_config": [{"api_type": "openai", "model": "gpt-4o"}],
        "code_execution_config": {
            "executor": {
                "type": "DockerCommandLineCodeExecutor",
                "image": "python:3.10",
                "timeout": 120,
            },
        },
    }

    setup_agent_from_config(config)

    # Verify executor was created with correct params
    mock_executor.assert_called_once_with(image="python:3.10", timeout=120)

    # Verify ConversableAgent has code_execution_config
    call_kwargs = mock_conversable.call_args[1]
    assert "code_execution_config" in call_kwargs


def test_setup_agent_invalid_executor_type():
    """Test that invalid executor type raises error."""
    config = {
        "type": "assistant",
        "name": "coder",
        "llm_config": [{"api_type": "openai", "model": "gpt-4o"}],
        "code_execution_config": {
            "executor": {
                "type": "InvalidExecutor",
                "timeout": 60,
            },
        },
    }

    with pytest.raises(ValueError) as exc_info:
        setup_agent_from_config(config)

    assert "Unsupported code executor type" in str(exc_info.value)
    assert "InvalidExecutor" in str(exc_info.value)


def test_setup_agent_missing_executor_type():
    """Test that missing executor type raises error."""
    config = {
        "type": "assistant",
        "name": "coder",
        "llm_config": [{"api_type": "openai", "model": "gpt-4o"}],
        "code_execution_config": {
            "executor": {
                "timeout": 60,
            },
        },
    }

    with pytest.raises(ValueError) as exc_info:
        setup_agent_from_config(config)

    assert "must include 'type' field" in str(exc_info.value)


@patch("massgen.adapters.ag2_adapter.ConversableAgent")
@patch("massgen.adapters.ag2_adapter.setup_agent_from_config")
@patch("massgen.adapters.ag2_adapter.AutoPattern")
def test_adapter_init_group_chat(mock_pattern, mock_setup, mock_conversable):
    """Test adapter initialization with group chat config."""
    mock_agent1 = MagicMock()
    mock_agent1.name = "Agent1"
    mock_agent2 = MagicMock()
    mock_agent2.name = "Agent2"
    mock_user_agent = MagicMock()
    mock_user_agent.name = "User"

    mock_setup.side_effect = [mock_agent1, mock_agent2]
    mock_conversable.return_value = mock_user_agent

    group_config = {
        "llm_config": {"api_type": "openai", "model": "gpt-4o"},
        "agents": [
            {"type": "assistant", "name": "Agent1", "llm_config": {"api_type": "openai", "model": "gpt-4o"}},
            {"type": "assistant", "name": "Agent2", "llm_config": {"api_type": "openai", "model": "gpt-4o"}},
        ],
        "pattern": {
            "type": "auto",
            "initial_agent": "Agent1",
            "group_manager_args": {"llm_config": {"api_type": "openai", "model": "gpt-4o"}},
        },
    }

    adapter = AG2Adapter(group_config=group_config)

    # Verify group chat setup
    assert adapter.is_group_chat is True
    assert len(adapter.agents) == 2
    assert adapter.user_agent is not None
    mock_pattern.assert_called_once()


@patch("massgen.adapters.ag2_adapter.setup_agent_from_config")
def test_adapter_separate_workflow_and_other_tools(mock_setup):
    """Test separation of workflow and other tools."""
    mock_agent = MagicMock()
    mock_setup.return_value = mock_agent

    agent_config = {
        "type": "assistant",
        "name": "test",
        "llm_config": {"api_type": "openai", "model": "gpt-4o"},
    }
    adapter = AG2Adapter(agent_config=agent_config)

    # Test tools with workflow and other tools
    tools = [
        {"type": "function", "function": {"name": "new_answer", "description": "Submit answer"}},
        {"type": "function", "function": {"name": "vote", "description": "Vote for answer"}},
        {"type": "function", "function": {"name": "search", "description": "Search tool"}},
    ]

    workflow_tools, other_tools = adapter._separate_workflow_and_other_tools(tools)

    # Verify separation
    assert len(workflow_tools) == 2
    assert len(other_tools) == 1
    assert any(t["function"]["name"] == "new_answer" for t in workflow_tools)
    assert any(t["function"]["name"] == "vote" for t in workflow_tools)
    assert other_tools[0]["function"]["name"] == "search"


@patch("massgen.adapters.ag2_adapter.ConversableAgent")
@patch("massgen.adapters.ag2_adapter.setup_agent_from_config")
@patch("massgen.adapters.ag2_adapter.AutoPattern")
def test_adapter_setup_user_agent_custom(mock_pattern, mock_setup, mock_conversable):
    """Test setting up custom user agent."""
    mock_user_agent = MagicMock()
    mock_user_agent.name = "User"
    mock_agent = MagicMock()
    mock_agent.name = "TestAgent"

    # First call for expert agent, second for user agent
    mock_setup.side_effect = [mock_agent, mock_user_agent]

    group_config = {
        "llm_config": {"api_type": "openai", "model": "gpt-4o"},
        "agents": [{"type": "assistant", "name": "TestAgent", "llm_config": {"api_type": "openai", "model": "gpt-4o"}}],
        "pattern": {
            "type": "auto",
            "initial_agent": "TestAgent",
            "group_manager_args": {"llm_config": {"api_type": "openai", "model": "gpt-4o"}},
        },
        "user_agent": {
            "name": "User",
            "system_message": "Custom user agent",
            "llm_config": {"api_type": "openai", "model": "gpt-4o"},
        },
    }

    adapter = AG2Adapter(group_config=group_config)

    # Verify custom user agent was set up
    assert adapter.user_agent.name == "User"
    # setup_agent_from_config should be called twice: once for expert agent, once for user agent
    assert mock_setup.call_count == 2


@patch("massgen.adapters.ag2_adapter.setup_agent_from_config")
@patch("massgen.adapters.ag2_adapter.AutoPattern")
def test_adapter_invalid_pattern_type(mock_pattern, mock_setup):
    """Test that invalid pattern type raises error."""
    mock_agent = MagicMock()
    mock_agent.name = "Agent1"
    mock_setup.return_value = mock_agent

    group_config = {
        "llm_config": {"api_type": "openai", "model": "gpt-4o"},
        "agents": [{"type": "assistant", "name": "Agent1", "llm_config": {"api_type": "openai", "model": "gpt-4o"}}],
        "pattern": {
            "type": "invalid_pattern",
            "initial_agent": "Agent1",
        },
    }

    with pytest.raises(NotImplementedError) as exc_info:
        AG2Adapter(group_config=group_config)

    assert "invalid_pattern" in str(exc_info.value)
