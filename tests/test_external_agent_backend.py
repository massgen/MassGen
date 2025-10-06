# -*- coding: utf-8 -*-
"""
Unit tests for ExternalAgentBackend.
"""
import pytest

from massgen.adapters import adapter_registry
from massgen.adapters.base import AgentAdapter
from massgen.backend.external import ExternalAgentBackend


class SimpleTestAdapter(AgentAdapter):
    """Simple test adapter."""

    async def execute_streaming(self, messages, tools, **kwargs):
        """Return simple response."""
        content = "Test response"
        async for chunk in self.simulate_streaming(content):
            yield chunk


@pytest.fixture(autouse=True)
def register_test_adapter():
    """Register test adapter before tests."""
    adapter_registry["test"] = SimpleTestAdapter
    yield
    # Cleanup
    if "test" in adapter_registry:
        del adapter_registry["test"]


def test_initialization_with_valid_adapter():
    """Test backend initialization with valid adapter type."""
    backend = ExternalAgentBackend(adapter_type="test")

    assert backend.adapter_type == "test"
    assert isinstance(backend.adapter, SimpleTestAdapter)
    assert backend.get_provider_name() == "test"


def test_initialization_with_invalid_adapter():
    """Test backend initialization with invalid adapter type."""
    with pytest.raises(ValueError) as exc_info:
        ExternalAgentBackend(adapter_type="nonexistent")

    assert "Unsupported framework" in str(exc_info.value)
    assert "nonexistent" in str(exc_info.value)


def test_adapter_type_case_insensitive():
    """Test that adapter type is case-insensitive."""
    backend1 = ExternalAgentBackend(adapter_type="TEST")
    backend2 = ExternalAgentBackend(adapter_type="Test")
    backend3 = ExternalAgentBackend(adapter_type="test")

    assert backend1.adapter_type == "test"
    assert backend2.adapter_type == "test"
    assert backend3.adapter_type == "test"


@pytest.mark.asyncio
async def test_stream_with_tools():
    """Test streaming with tools."""
    backend = ExternalAgentBackend(adapter_type="test")

    messages = [{"role": "user", "content": "Hello"}]
    tools = []

    chunks = []
    async for chunk in backend.stream_with_tools(messages, tools):
        chunks.append(chunk)

    # Should receive chunks from adapter
    assert len(chunks) > 0
    assert any(c.type == "content" for c in chunks)
    assert any(c.type == "done" for c in chunks)


def test_extract_adapter_config():
    """Test extraction of adapter-specific config."""
    backend = ExternalAgentBackend(
        adapter_type="test",
        # Base params (should be excluded)
        type="test",
        agent_id="test_agent",
        session_id="session_1",
        # Custom params (should be included)
        custom_param="value",
        temperature=0.7,
    )

    # Check that adapter received config
    assert "custom_param" in backend.adapter.config
    assert "temperature" in backend.adapter.config

    # Base params should not be in adapter config
    assert "type" not in backend.adapter.config
    assert "agent_id" not in backend.adapter.config
    assert "session_id" not in backend.adapter.config


def test_is_stateful_default():
    """Test stateful check with default adapter."""
    backend = ExternalAgentBackend(adapter_type="test")

    # Default is False
    assert backend.is_stateful() is False


def test_clear_history():
    """Test clearing history."""
    backend = ExternalAgentBackend(adapter_type="test")

    # Add some history
    backend.adapter._conversation_history = [{"role": "user", "content": "test"}]

    # Clear
    backend.clear_history()

    assert len(backend.adapter._conversation_history) == 0


def test_reset_state():
    """Test resetting state."""
    backend = ExternalAgentBackend(adapter_type="test")

    # Add some history
    backend.adapter._conversation_history = [{"role": "user", "content": "test"}]

    # Reset
    backend.reset_state()

    # Should clear history
    assert len(backend.adapter._conversation_history) == 0
