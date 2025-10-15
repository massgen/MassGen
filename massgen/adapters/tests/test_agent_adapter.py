# -*- coding: utf-8 -*-
"""
Unit tests for base AgentAdapter class.
"""
import pytest

from massgen.adapters.base import AgentAdapter


class MockAdapter(AgentAdapter):
    """Mock adapter for testing."""

    async def execute_streaming(self, messages, tools, **kwargs):
        """Mock implementation."""
        content = "Mock response"
        async for chunk in self.simulate_streaming(content):
            yield chunk


@pytest.mark.asyncio
async def test_simulate_streaming():
    """Test streaming simulation."""
    adapter = MockAdapter()

    content = "Hello world"
    chunks = []

    async for chunk in adapter.simulate_streaming(content):
        chunks.append(chunk)

    # Should have content chunks + complete_message + done
    assert len(chunks) > 0
    assert any(c.type == "content" for c in chunks)
    assert any(c.type == "complete_message" for c in chunks)
    assert any(c.type == "done" for c in chunks)

    # Complete message should have content
    complete_chunks = [c for c in chunks if c.type == "complete_message"]
    assert len(complete_chunks) == 1
    assert complete_chunks[0].complete_message["content"] == content


@pytest.mark.asyncio
async def test_simulate_streaming_with_tool_calls():
    """Test streaming simulation with tool calls."""
    adapter = MockAdapter()

    content = "Using tools"
    tool_calls = [
        {
            "id": "call_1",
            "function": {"name": "search", "arguments": '{"query": "test"}'},
        },
    ]

    chunks = []
    async for chunk in adapter.simulate_streaming(content, tool_calls):
        chunks.append(chunk)

    # Should have tool_calls chunk
    tool_chunks = [c for c in chunks if c.type == "tool_calls"]
    assert len(tool_chunks) == 1
    assert tool_chunks[0].tool_calls == tool_calls

    # Complete message should include tool calls
    complete_chunks = [c for c in chunks if c.type == "complete_message"]
    assert complete_chunks[0].complete_message["tool_calls"] == tool_calls


def test_convert_messages_default():
    """Test default message conversion (passthrough)."""
    adapter = MockAdapter()

    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi"},
    ]

    result = adapter.convert_messages_from_massgen(messages)
    assert result == messages


def test_convert_tools_default():
    """Test default tool conversion (passthrough)."""
    adapter = MockAdapter()

    tools = [
        {
            "type": "function",
            "function": {"name": "search", "description": "Search tool"},
        },
    ]

    result = adapter.convert_tools_from_massgen(tools)
    assert result == tools


def test_is_stateful_default():
    """Test default stateful behavior."""
    adapter = MockAdapter()
    assert adapter.is_stateful() is False


def test_clear_history():
    """Test clearing conversation history."""
    adapter = MockAdapter()

    # Add some history
    adapter._conversation_history = [{"role": "user", "content": "test"}]

    # Clear it
    adapter.clear_history()

    assert len(adapter._conversation_history) == 0


def test_reset_state():
    """Test resetting adapter state."""
    adapter = MockAdapter()

    # Add some history
    adapter._conversation_history = [{"role": "user", "content": "test"}]

    # Reset
    adapter.reset_state()

    # Should clear history
    assert len(adapter._conversation_history) == 0
