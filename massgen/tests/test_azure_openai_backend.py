"""
Test Azure OpenAI backend functionality.
"""

import pytest
import os
import sys
from unittest.mock import patch, MagicMock

# Add the parent directory to sys.path to allow relative imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Import directly from the backend module to avoid package-level imports
from backend.azure_openai import AzureOpenAIBackend


class TestAzureOpenAIBackend:
    """Test Azure OpenAI backend functionality."""

    def test_init_with_env_vars(self):
        """Test initialization with environment variables."""
        with patch.dict(os.environ, {
            'AZURE_OPENAI_API_KEY': 'test-key',
            'AZURE_OPENAI_ENDPOINT': 'https://test.openai.azure.com/',
            'AZURE_OPENAI_API_VERSION': '2024-02-15-preview'
        }):
            backend = AzureOpenAIBackend()
            assert backend.api_key == 'test-key'
            assert backend.azure_endpoint == 'https://test.openai.azure.com'
            assert backend.api_version == '2024-02-15-preview'

    def test_init_with_kwargs(self):
        """Test initialization with keyword arguments."""
        backend = AzureOpenAIBackend(
            api_key='custom-key',
            base_url='https://custom.openai.azure.com/',
            api_version='2024-01-01'
        )
        assert backend.api_key == 'custom-key'
        assert backend.azure_endpoint == 'https://custom.openai.azure.com'
        assert backend.api_version == '2024-01-01'

    def test_init_missing_api_key(self):
        """Test initialization fails without API key."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="Azure OpenAI API key is required"):
                AzureOpenAIBackend()

    def test_init_missing_endpoint(self):
        """Test initialization fails without endpoint."""
        with patch.dict(os.environ, {'AZURE_OPENAI_API_KEY': 'test-key'}, clear=True):
            with pytest.raises(ValueError, match="Azure OpenAI endpoint URL is required"):
                AzureOpenAIBackend()

    def test_base_url_normalization(self):
        """Test base URL is properly normalized."""
        backend = AzureOpenAIBackend(
            api_key='test-key',
            base_url='https://test.openai.azure.com'
        )
        assert backend.azure_endpoint == 'https://test.openai.azure.com'

        backend2 = AzureOpenAIBackend(
            api_key='test-key',
            base_url='https://test2.openai.azure.com/'
        )
        assert backend2.azure_endpoint == 'https://test2.openai.azure.com'

    def test_get_provider_name(self):
        """Test provider name is correct."""
        backend = AzureOpenAIBackend(
            api_key='test-key',
            base_url='https://test.openai.azure.com/'
        )
        assert backend.get_provider_name() == 'Azure OpenAI'

    def test_estimate_tokens(self):
        """Test token estimation."""
        backend = AzureOpenAIBackend(
            api_key='test-key',
            base_url='https://test.openai.azure.com/'
        )
        text = "This is a test message with several words."
        estimated = backend.estimate_tokens(text)
        assert estimated > 0
        assert isinstance(estimated, (int, float))

    def test_calculate_cost(self):
        """Test cost calculation."""
        backend = AzureOpenAIBackend(
            api_key='test-key',
            base_url='https://test.openai.azure.com/'
        )
        
        # Test GPT-4 cost calculation
        cost = backend.calculate_cost(1000, 500, 'gpt-4o')
        assert cost > 0
        assert isinstance(cost, float)
        
        # Test GPT-3.5 cost calculation
        cost2 = backend.calculate_cost(1000, 500, 'gpt-3.5-turbo')
        assert cost2 > 0
        assert cost2 < cost  # GPT-3.5 should be cheaper than GPT-4

    @pytest.mark.asyncio
    async def test_stream_with_tools_missing_model(self):
        """Test stream_with_tools fails without model parameter."""
        backend = AzureOpenAIBackend(
            api_key='test-key',
            base_url='https://test.openai.azure.com/'
        )
        
        messages = [{"role": "user", "content": "Hello"}]
        tools = []
        
        with pytest.raises(ValueError, match="Azure OpenAI requires a deployment name"):
            async for _ in backend.stream_with_tools(messages, tools):
                pass

    @pytest.mark.asyncio
    async def test_stream_with_tools_with_model(self):
        """Test stream_with_tools works with model parameter."""
        backend = AzureOpenAIBackend(
            api_key='test-key',
            base_url='https://test.openai.azure.com/'
        )
        
        messages = [{"role": "user", "content": "Hello"}]
        tools = []
        
        # Mock the parent class method
        with patch.object(backend, 'stream_with_tools') as mock_stream:
            mock_stream.return_value = iter([])
            
            async for _ in backend.stream_with_tools(messages, tools, model='gpt-4'):
                pass
            
            # Verify the model parameter was passed correctly
            mock_stream.assert_called_once_with(messages, tools, model='gpt-4')
