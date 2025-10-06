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
