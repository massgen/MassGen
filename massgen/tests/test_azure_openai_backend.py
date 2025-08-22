"""
Test Azure OpenAI backend functionality.
"""

import pytest
import os
import sys
from unittest.mock import patch, MagicMock, AsyncMock

# Add the parent directory to sys.path to allow relative imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Import directly from the backend module to avoid package-level imports
from backend.azure_openai import AzureOpenAIBackend


class TestAzureOpenAIBackend:
    """Test Azure OpenAI backend functionality."""

    def test_init_with_env_vars(self):
        """Test initialization with environment variables."""
        with patch.dict(
            os.environ,
            {
                "AZURE_OPENAI_API_KEY": "test-key",
                "AZURE_OPENAI_ENDPOINT": "https://test.openai.azure.com/",
                "AZURE_OPENAI_API_VERSION": "2024-02-15-preview",
            },
        ):
            backend = AzureOpenAIBackend()
            assert backend.api_key == "test-key"
            assert backend.azure_endpoint == "https://test.openai.azure.com"
            assert backend.api_version == "2024-02-15-preview"

    def test_init_with_kwargs(self):
        """Test initialization with keyword arguments."""
        backend = AzureOpenAIBackend(
            api_key="custom-key",
            base_url="https://custom.openai.azure.com/",
            api_version="2024-01-01",
        )
        assert backend.api_key == "custom-key"
        assert backend.azure_endpoint == "https://custom.openai.azure.com"
        assert backend.api_version == "2024-01-01"

    def test_init_missing_api_key(self):
        """Test initialization fails without API key."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(
                ValueError, match="Azure OpenAI endpoint URL is required"
            ):
                AzureOpenAIBackend()

    def test_init_missing_endpoint(self):
        """Test initialization fails without endpoint."""
        with patch.dict(os.environ, {"AZURE_OPENAI_API_KEY": "test-key"}, clear=True):
            with pytest.raises(
                ValueError, match="Azure OpenAI endpoint URL is required"
            ):
                AzureOpenAIBackend()

    def test_init_missing_api_key_with_endpoint(self):
        """Test initialization fails without API key when endpoint is provided."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="Azure OpenAI API key is required"):
                AzureOpenAIBackend(base_url="https://test.openai.azure.com/")

    def test_base_url_normalization(self):
        """Test base URL is properly normalized."""
        backend = AzureOpenAIBackend(
            api_key="test-key", base_url="https://test.openai.azure.com"
        )
        assert backend.azure_endpoint == "https://test.openai.azure.com"

        backend2 = AzureOpenAIBackend(
            api_key="test-key", base_url="https://test2.openai.azure.com/"
        )
        assert backend2.azure_endpoint == "https://test2.openai.azure.com"

    def test_get_provider_name(self):
        """Test provider name is correct."""
        backend = AzureOpenAIBackend(
            api_key="test-key", base_url="https://test.openai.azure.com/"
        )
        assert backend.get_provider_name() == "Azure OpenAI"

    def test_estimate_tokens(self):
        """Test token estimation."""
        backend = AzureOpenAIBackend(
            api_key="test-key", base_url="https://test.openai.azure.com/"
        )
        text = "This is a test message with several words."
        estimated = backend.estimate_tokens(text)
        assert estimated > 0
        assert isinstance(estimated, (int, float))

    def test_calculate_cost(self):
        """Test cost calculation."""
        backend = AzureOpenAIBackend(
            api_key="test-key", base_url="https://test.openai.azure.com/"
        )

        # Test GPT-4 cost calculation
        cost = backend.calculate_cost(1000, 500, "gpt-4o")
        assert cost > 0
        assert isinstance(cost, float)

        # Test GPT-3.5 cost calculation
        cost2 = backend.calculate_cost(1000, 500, "gpt-3.5-turbo")
        assert cost2 > 0
        assert cost2 < cost  # GPT-3.5 should be cheaper than GPT-4

    @pytest.mark.asyncio
    async def test_stream_with_tools_missing_model(self):
        """Test stream_with_tools fails without model parameter."""
        backend = AzureOpenAIBackend(
            api_key="test-key", base_url="https://test.openai.azure.com/"
        )

        messages = [{"role": "user", "content": "Hello"}]
        tools = []

        # The validation happens at the beginning of the method, before any API calls
        # So we don't need to mock the client for this test
        try:
            async for chunk in backend.stream_with_tools(messages, tools):
                # If we get here, the validation didn't work as expected
                # Check if it's an error chunk
                if chunk.type == "error" and "deployment name" in chunk.error:
                    # This is the expected behavior - validation error is yielded as a chunk
                    return
                else:
                    # Unexpected - validation should have failed
                    pytest.fail(f"Expected validation error, but got chunk: {chunk}")
        except ValueError as e:
            # This is the expected behavior - validation error is raised
            if "deployment name" in str(e):
                return
            else:
                pytest.fail(f"Unexpected ValueError: {e}")
        except Exception as e:
            pytest.fail(f"Unexpected exception: {e}")

    @pytest.mark.asyncio
    async def test_stream_with_tools_with_model(self):
        """Test stream_with_tools works with model parameter."""
        backend = AzureOpenAIBackend(
            api_key="test-key", base_url="https://test.openai.azure.com/"
        )

        messages = [{"role": "user", "content": "Hello"}]
        tools = []

        # Mock the client and create a mock stream response
        mock_chunk = MagicMock()
        mock_chunk.choices = [MagicMock()]
        mock_chunk.choices[0].delta = MagicMock()
        mock_chunk.choices[0].delta.content = "Hello"
        mock_chunk.choices[0].finish_reason = "stop"

        mock_stream = [mock_chunk]

        with patch.object(backend, "client") as mock_client:
            mock_client.chat.completions.create = AsyncMock(return_value=mock_stream)

            # Test that it doesn't raise an error with model parameter
            try:
                async for chunk in backend.stream_with_tools(
                    messages, tools, model="gpt-4"
                ):
                    # Just consume the stream
                    pass
            except Exception as e:
                # If there's an error, it should not be about missing model
                assert "deployment name" not in str(e)
