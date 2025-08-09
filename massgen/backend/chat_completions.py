from __future__ import annotations

"""
Base class for backends using OpenAI Chat Completions API format.
Handles common message processing, tool conversion, and streaming patterns.

Supported Providers and Environment Variables:
- OpenAI: OPENAI_API_KEY
- Cerebras AI: CEREBRAS_API_KEY
- Together AI: TOGETHER_API_KEY
- Fireworks AI: FIREWORKS_API_KEY
- Groq: GROQ_API_KEY
- Nebius AI Studio: NEBIUS_API_KEY
- OpenRouter: OPENROUTER_API_KEY
"""


# Standard library imports
import asyncio
import os
from dataclasses import dataclass
from typing import Dict, List, Any, AsyncGenerator, Optional, Tuple
from urllib.parse import urlparse

# Third-party imports
import openai
from openai import AsyncOpenAI
import logging

# Local imports

from .base import LLMBackend, StreamChunk

# Set up logger
logger = logging.getLogger(__name__)


@dataclass
class ProviderConfig:
    """Configuration for a provider including domain, name, and environment variable."""
    domain: str
    display_name: str
    env_var: str


class ProviderRegistry:
    """Registry for managing provider configurations."""
    
    # Single source of truth for provider configurations
    PROVIDERS = [
        ProviderConfig("cerebras.ai", "Cerebras AI", "CEREBRAS_API_KEY"),
        ProviderConfig("together.xyz", "Together AI", "TOGETHER_API_KEY"),
        ProviderConfig("deepinfra.com", "DeepInfra",  "DEEPINFRA_API_KEY"),
        ProviderConfig("fireworks.ai", "Fireworks AI", "FIREWORKS_API_KEY"),
        ProviderConfig("api.groq.com", "Groq", "GROQ_API_KEY"),
        ProviderConfig("api.studio.nebius.ai", "Nebius AI Studio", "NEBIUS_API_KEY"),
        ProviderConfig("openrouter.ai", "OpenRouter", "OPENROUTER_API_KEY"),
        ProviderConfig("api.openai.com", "OpenAI", "OPENAI_API_KEY"),
    ]    
    # Build lookup dictionaries for O(1) access
    _domain_to_config: Dict[str, ProviderConfig] = {
        provider.domain: provider for provider in PROVIDERS
    }
    _name_to_config: Dict[str, ProviderConfig] = {
        provider.display_name.lower(): provider for provider in PROVIDERS
    }
    
    # Base URL mapping for provider names
    PROVIDER_BASE_URLS = {
        "openai": "https://api.openai.com/v1",
        "cerebras ai": "https://api.cerebras.ai/v1",
        "together ai": "https://api.together.xyz/v1",
        "deepinfra": "https://api.deepinfra.com/v1/openai",
        "fireworks ai": "https://api.fireworks.ai/inference/v1",
        "groq": "https://api.groq.com/openai/v1",
        "nebius ai studio": "https://api.studio.nebius.ai/v1",
        "openrouter": "https://openrouter.ai/api/v1",
    }
    
    @classmethod
    def detect_provider(cls, base_url: str) -> Tuple[str, str, str]:
        """
        Detect provider from URL using proper URL parsing.
        
        Returns:
            Tuple of (domain, display_name, env_var)
        """
        try:
            parsed = urlparse(base_url.lower())
            hostname = parsed.hostname or parsed.path
            
            # Check for exact domain match first
            for domain, config in cls._domain_to_config.items():
                if hostname and hostname.endswith(domain):
                    return config.domain, config.display_name, config.env_var
            
            # Default to OpenAI
            default = cls._domain_to_config.get("api.openai.com")
            return default.domain, default.display_name, default.env_var
            
        except Exception:
            # Fallback to OpenAI on any parsing error
            default = cls._domain_to_config.get("api.openai.com")
            return default.domain, default.display_name, default.env_var
    
    @classmethod
    def get_api_key(cls, base_url: str) -> Optional[str]:
        """
        Get API key for the detected provider.
        
        Returns:
            API key if found and valid, None otherwise
        """
        _, _, env_var = cls.detect_provider(base_url)
        api_key = os.getenv(env_var)
        # Validate that key exists and is not empty/whitespace
        return api_key.strip() if api_key and api_key.strip() else None
    
    @classmethod
    def get_base_url_from_provider(cls, provider_name: str) -> str:
        """
        Get base URL from provider name.
        
        Args:
            provider_name: Name of the provider (case-insensitive)
            
        Returns:
            Base URL for the provider, defaults to OpenAI if not found
        """
        provider_key = provider_name.lower().strip()
        return cls.PROVIDER_BASE_URLS.get(provider_key, cls.PROVIDER_BASE_URLS["openai"])
    
    @classmethod
    def get_api_key_from_provider(cls, provider_name: str) -> Optional[str]:
        """
        Get API key for the specified provider name.
        
        Args:
            provider_name: Name of the provider (case-insensitive)
            
        Returns:
            API key if found and valid, None otherwise
        """
        provider_key = provider_name.lower().strip()
        config = cls._name_to_config.get(provider_key)
        if config:
            api_key = os.getenv(config.env_var)
            return api_key.strip() if api_key and api_key.strip() else None
        return None


class ChatCompletionsBackend(LLMBackend):
    """Complete OpenAI-compatible Chat Completions API backend.
    
    Can be used directly with any OpenAI-compatible provider by setting provider name.
    Supports Cerebras AI, Together AI, Fireworks AI, DeepInfra, and other compatible providers.
    
    Environment Variables:
        Provider-specific API keys are automatically detected based on provider name.
        See ProviderRegistry.PROVIDERS for the complete list.
    
    Optional kwargs:
        - provider: str – provider name (e.g., "openai", "cerebras ai", "together ai")
        - base_url: str – provider base URL (optional, auto-detected from provider name)
        - model: str – default model name
        - stream: bool – default streaming mode (defaults to True)
        - provider_name: str – display name override for errors and UI (deprecated, use 'provider')
        - default_headers: Dict[str, str] – custom headers passed to the HTTP client
            Examples (provider-specific):
              - OpenRouter expects: {"HTTP-Referer": "https://your.app", "X-Title": "Your App"}
            Notes:
              - If not provided or empty, no additional headers are sent
              - Call-time headers (via stream_with_tools) override same keys from instance headers
    """

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(api_key, **kwargs)
        
        # Initialize provider configuration
        # Support both provider name and base_url for backward compatibility
        provider_name = kwargs.get("provider", kwargs.get("provider_name"))
        if not provider_name and "base_url" in kwargs:
            _, detected_name, _ = ProviderRegistry.detect_provider(kwargs["base_url"])
            provider_name = detected_name
        provider_name = provider_name or "openai"
        self.base_url: str = kwargs.get("base_url") or ProviderRegistry.get_base_url_from_provider(provider_name)
        self.model_name: str = kwargs.get("model", "gpt-5-mini")
        self.stream: bool = kwargs.get("stream", True)
        
        # Optional provider-specific HTTP headers used by some OpenAI-compatible providers.
        # - Normalized to {} when None
        # - For OpenRouter, set "HTTP-Referer" and "X-Title" to identify your app
        self.default_headers: Dict[str, str] = kwargs.get("default_headers", {}) or {}
        
        # Resolve provider and API key
        self._provider_name: str = provider_name
        self.api_key: str = self._resolve_api_key(api_key, provider_name)
        
    def _resolve_api_key(self, provided_key: Optional[str], provider_name: str) -> str:
        """
        Resolve and validate API key.
        
        Args:
            provided_key: Explicitly provided API key
            provider_name: Name of the provider
            
        Returns:
            Valid API key
            
        Raises:
            ValueError: If no valid API key is found
        """
        # Use provided key if available and valid
        if provided_key and provided_key.strip():
            return provided_key.strip()
        
        # Try to get key from environment based on provider name first
        api_key = ProviderRegistry.get_api_key_from_provider(provider_name)
        if api_key:
            return api_key
        
        # Fallback to URL-based detection for backward compatibility
        api_key = ProviderRegistry.get_api_key(self.base_url)
        if api_key:
            return api_key
        
        # No valid key found - raise error with helpful message
        domain, display_name, env_var = ProviderRegistry.detect_provider(self.base_url)
        provider_display = display_name

        raise ValueError(
            f"API key required for {provider_display}. "
            f"Please set the {env_var} environment variable or provide api_key in configuration."
        )    
    def get_provider_name(self) -> str:
        """Get the name of this provider."""
        if self._provider_name:
            return self._provider_name
        
        # Auto-detect from URL if not explicitly set
        _, display_name, _ = ProviderRegistry.detect_provider(self.base_url)
        return display_name


    def convert_tools_to_chat_completions_format(
        self, tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Convert tools from Response API format to Chat Completions format if needed.

        Response API format: {"type": "function", "name": ..., "description": ..., "parameters": ...}
        Chat Completions format: {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
        """
        if not tools:
            return tools

        converted_tools = []
        for tool in tools:
            if tool.get("type") == "function":
                if "function" in tool:
                    # Already in Chat Completions format
                    converted_tools.append(tool)
                elif "name" in tool and "description" in tool:
                    # Response API format - convert to Chat Completions format
                    converted_tools.append(
                        {
                            "type": "function",
                            "function": {
                                "name": tool["name"],
                                "description": tool["description"],
                                "parameters": tool.get("parameters", {}),
                            },
                        }
                    )
                else:
                    # Unknown format - keep as-is
                    converted_tools.append(tool)
            else:
                # Non-function tool - keep as-is
                converted_tools.append(tool)

        return converted_tools

    async def handle_chat_completions_stream(
        self, stream, enable_web_search: bool = False
    ) -> AsyncGenerator[StreamChunk, None]:
        """Handle standard Chat Completions API streaming format."""
        import json

        content = ""
        current_tool_calls = {}
        search_sources_used = 0

        async for chunk in stream:
            try:
                if hasattr(chunk, "choices") and chunk.choices:
                    choice = chunk.choices[0]

                    # Handle content delta
                    if hasattr(choice, "delta") and choice.delta:
                        delta = choice.delta

                        # Plain text content
                        if getattr(delta, "content", None):
                            content_chunk = delta.content
                            content += content_chunk
                            yield StreamChunk(type="content", content=content_chunk)
                        
                        # Tool calls streaming (OpenAI-style)
                        if getattr(delta, "tool_calls", None):
                            for tool_call_delta in delta.tool_calls:
                                index = getattr(tool_call_delta, "index", 0)

                                if index not in current_tool_calls:
                                    current_tool_calls[index] = {
                                        "id": "",
                                        "function": {
                                            "name": "",
                                            "arguments": "",
                                        },
                                    }

                                # Accumulate id
                                if getattr(tool_call_delta, "id", None):
                                    current_tool_calls[index]["id"] = tool_call_delta.id

                                # Function name
                                if (
                                    hasattr(tool_call_delta, "function")
                                    and tool_call_delta.function
                                ):
                                    if getattr(tool_call_delta.function, "name", None):
                                        current_tool_calls[index]["function"][
                                            "name"
                                        ] = tool_call_delta.function.name

                                    # Accumulate arguments (as string chunks)
                                    if getattr(tool_call_delta.function, "arguments", None):
                                        current_tool_calls[index]["function"][
                                            "arguments"
                                        ] += tool_call_delta.function.arguments

                    # Handle finish reason
                    if getattr(choice, "finish_reason", None):
                        if choice.finish_reason == "tool_calls" and current_tool_calls:

                            final_tool_calls = []

                            for index in sorted(current_tool_calls.keys()):
                                call = current_tool_calls[index]
                                function_name = call["function"]["name"]
                                arguments_str = call["function"]["arguments"]

                                try:
                                    arguments_obj = (
                                        json.loads(arguments_str)
                                        if arguments_str.strip()
                                        else {}
                                    )
                                except json.JSONDecodeError:
                                    arguments_obj = {}

                                final_tool_calls.append(
                                    {
                                        "id": call["id"] or f"toolcall_{index}",
                                        "type": "function",
                                        "function": {
                                            "name": function_name,
                                            "arguments": arguments_obj,
                                        },
                                    }
                                )

                            yield StreamChunk(
                                type="tool_calls", tool_calls=final_tool_calls
                            )

                            complete_message = {
                                "role": "assistant",
                                "content": content.strip(),
                                "tool_calls": final_tool_calls,
                            }

                            yield StreamChunk(
                                type="complete_message",
                                complete_message=complete_message,
                            )
                            yield StreamChunk(type="done")
                            return

                        elif choice.finish_reason in ["stop", "length"]:
                            if search_sources_used > 0:
                                yield StreamChunk(
                                    type="content",
                                    content=f"\n✅ [Live Search Complete] Used {search_sources_used} sources\n",
                                )

                            # Handle citations if present
                            if hasattr(chunk, "citations") and chunk.citations:
                                if enable_web_search:
                                    citation_text = "\n📚 **Citations:**\n"
                                    for i, citation in enumerate(chunk.citations, 1):
                                        citation_text += f"{i}. {citation}\n"
                                    yield StreamChunk(
                                        type="content", content=citation_text
                                    )

                            # Return final message
                            complete_message = {
                                "role": "assistant",
                                "content": content.strip(),
                            }
                            yield StreamChunk(
                                type="complete_message",
                                complete_message=complete_message,
                            )
                            yield StreamChunk(type="done")
                            return

                # Optionally handle usage metadata
                if hasattr(chunk, "usage") and chunk.usage:
                    if getattr(chunk.usage, "num_sources_used", 0) > 0:
                        search_sources_used = chunk.usage.num_sources_used
                        if enable_web_search:
                            yield StreamChunk(
                                type="content",
                                content=f"\n📊 [Live Search] Using {search_sources_used} sources for real-time data\n",
                            )

            except Exception as chunk_error:
                yield StreamChunk(
                    type="error", error=f"Chunk processing error: {chunk_error}"
                )
                continue

        # Fallback in case stream ends without finish_reason
        yield StreamChunk(type="done")


    async def stream_with_tools(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream response using OpenAI-compatible Chat Completions API."""
        
        # 2. Parameter validation errors
        try:
            if not messages:
                raise ValueError("Messages parameter cannot be empty")
            if not isinstance(messages, list):
                raise TypeError("Messages must be a list")
            
            for i, msg in enumerate(messages):
                if not isinstance(msg, dict):
                    raise TypeError(f"Message at index {i} must be a dictionary")
                if 'role' not in msg:
                    raise ValueError(f"Message at index {i} missing required 'role' field")
                if 'content' not in msg:
                    raise ValueError(f"Message at index {i} missing required 'content' field")
                if not isinstance(msg['role'], str):
                    raise TypeError(f"Message at index {i} 'role' must be a string")
                if msg['role'] not in ['system', 'user', 'assistant', 'tool']:
                    raise ValueError(f"Message at index {i} has invalid role '{msg['role']}'. Must be one of: system, user, assistant, tool")
            
            if tools is not None and not isinstance(tools, list):
                raise TypeError("Tools parameter must be a list or None")
                
            if not hasattr(self, 'model_name') or not self.model_name:
                raise ValueError("Model name is not configured")
                
        except (ValueError, TypeError) as e:
            logger.error(f"Parameter validation error in stream_with_tools: {e}")
            yield StreamChunk(type="error", error=f"Parameter validation error: {e}")
            return
        except Exception as e:
            logger.error(f"Unexpected error during parameter validation in stream_with_tools: {e}")
            yield StreamChunk(type="error", error=f"Parameter validation failed: {e}")
            return

        # 1. Client creation and configuration errors
        try:
            # Merge headers from instance and call-time overrides.
            # Precedence: call-time > instance-level. When both are empty, pass None so the SDK
            # does not attach an empty headers object. This affects providers like OpenRouter
            # that require headers such as HTTP-Referer and X-Title.
            provided_default_headers: Optional[Dict[str, str]] = kwargs.get("default_headers")
            merged_default_headers: Optional[Dict[str, str]] = (
                {**self.default_headers, **provided_default_headers}
                if isinstance(provided_default_headers, dict)
                else (self.default_headers if self.default_headers else None)
            )

            # Forward merged headers to the OpenAI SDK. The SDK will send these headers with
            # every HTTP request made by this client instance.
            client = AsyncOpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                default_headers=merged_default_headers,
            )
            
        except AttributeError as e:
            logger.error(f"Client configuration error - missing required attributes: {e}")
            yield StreamChunk(type="error", error=f"Client configuration failed - missing attributes: {e}")
            return
        except ImportError as e:
            logger.error(f"Client creation error - missing required dependencies: {e}")
            yield StreamChunk(type="error", error=f"Failed to import required client dependencies: {e}")
            return
        except Exception as e:
            logger.error(f"Unexpected error during client creation: {e}")
            yield StreamChunk(type="error", error=f"Client creation failed: {e}")
            return

        # Extract parameters with validation
        try:
            model = kwargs.get("model", self.model_name)
            max_tokens = kwargs.get("max_tokens", None)
            temperature = kwargs.get("temperature", None)
            enable_web_search = kwargs.get("enable_web_search", False)
            
            # Validate parameter types and ranges
            if max_tokens is not None and (not isinstance(max_tokens, int) or max_tokens <= 0):
                raise ValueError(f"max_tokens must be a positive integer, got: {max_tokens}")
            if temperature is not None and (not isinstance(temperature, (int, float)) or temperature < 0 or temperature > 2):
                raise ValueError(f"temperature must be a number between 0 and 2, got: {temperature}")
                
        except (ValueError, TypeError) as e:
            logger.error(f"Parameter extraction/validation error: {e}")
            yield StreamChunk(type="error", error=f"Parameter validation error: {e}")
            return

        # 3. Tool conversion errors
        converted_tools = None
        if tools:
            try:
                converted_tools = self.convert_tools_to_chat_completions_format(tools)
                
                # Validate converted tools structure
                if not isinstance(converted_tools, list):
                    raise ValueError("Tool conversion returned non-list result")
                    
                for i, tool in enumerate(converted_tools):
                    if not isinstance(tool, dict):
                        raise ValueError(f"Converted tool at index {i} is not a dictionary")
                    if 'type' not in tool:
                        raise ValueError(f"Converted tool at index {i} missing 'type' field")
                        
            except AttributeError as e:
                logger.error(f"Tool conversion error - method not implemented: {e}")
                yield StreamChunk(type="error", error=f"Tool conversion not supported for this backend: {e}")
                return
            except (ValueError, TypeError) as e:
                logger.error(f"Tool format conversion error: {e}")
                yield StreamChunk(type="error", error=f"Invalid tool format: {e}")
                return
            except Exception as e:
                logger.error(f"Unexpected error during tool conversion: {e}")
                yield StreamChunk(type="error", error=f"Tool conversion failed: {e}")
                return

        # 4. API parameter construction errors
        try:
            api_params = {
                "model": model,
                "messages": messages,
                "stream": kwargs.get("stream", self.stream)
            }

            # Add tools if provided
            if converted_tools:
                api_params["tools"] = converted_tools

            # Add optional parameters only if they have values
            if max_tokens is not None:
                api_params["max_tokens"] = max_tokens
            if temperature is not None:
                api_params["temperature"] = temperature

            # Add provider tools (web search) if enabled
            provider_tools = []
            if enable_web_search:
                provider_tools.append({
                    "type": "function",
                    "function": {
                    "name": "web_search",
                    "description": "Search the web for current or factual information",
                    "parameters": {
                        "type": "object",
                        "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query to send to the web"
           
                        }
                        },
                        "required": ["query"]
                    }
                    }
                })

            if provider_tools:
                if "tools" not in api_params:
                    api_params["tools"] = []
                api_params["tools"].extend(provider_tools)
                
            # Validate final API parameters
            if not isinstance(api_params.get("model"), str):
                raise ValueError(f"Model parameter must be a string, got: {type(api_params.get('model'))}")
            if not isinstance(api_params.get("messages"), list):
                raise ValueError("Messages parameter must be a list")
            if not isinstance(api_params.get("stream"), bool):
                raise ValueError("Stream parameter must be a boolean")
                
        except (ValueError, TypeError, KeyError) as e:
            logger.error(f"API parameter construction error: {e}")
            yield StreamChunk(type="error", error=f"API parameter construction failed: {e}")
            return
        except Exception as e:
            logger.error(f"Unexpected error during API parameter construction: {e}")
            yield StreamChunk(type="error", error=f"API parameter construction failed: {e}")
            return

        # 5. Stream creation errors with specific error handling
        try:
            stream = await client.chat.completions.create(**api_params)
            
        except openai.AuthenticationError as e:
            # 8. Authentication errors
            logger.error(f"Authentication error: {e}")
            yield StreamChunk(type="error", error=f"Authentication failed - check API key: {e}")
            return
        except openai.RateLimitError as e:
            # 9. Rate limiting errors
            logger.error(f"Rate limit error: {e}")
            yield StreamChunk(type="error", error=f"Rate limit exceeded - please retry later: {e}")
            return
        except openai.APITimeoutError as e:
            # 10. Timeout errors
            logger.error(f"API timeout error: {e}")
            yield StreamChunk(type="error", error=f"Request timed out - please retry: {e}")
            return
        except (openai.APIConnectionError, openai.APIError) as e:
            # 7. Network/connection errors
            logger.error(f"Network/connection error: {e}")
            yield StreamChunk(type="error", error=f"Network connection failed: {e}")
            return
        except openai.BadRequestError as e:
            logger.error(f"Bad request error during stream creation: {e}")
            yield StreamChunk(type="error", error=f"Invalid request parameters: {e}")
            return
        except Exception as e:
            logger.error(f"Unexpected error during stream creation: {e}")
            yield StreamChunk(type="error", error=f"Stream creation failed: {e}")
            return

        # 6. Individual chunk processing errors (enhanced existing)
        try:
            async for chunk in self.handle_chat_completions_stream(
                stream, enable_web_search
            ):
                try:
                    yield chunk
                except Exception as chunk_error:
                    logger.error(f"Error processing individual chunk: {chunk_error}")
                    yield StreamChunk(type="error", error=f"Chunk processing error: {chunk_error}")
                    continue
                    
        except asyncio.TimeoutError as e:
            # 10. Timeout errors during streaming
            logger.error(f"Streaming timeout error: {e}")
            yield StreamChunk(type="error", error=f"Streaming timed out: {e}")
            return
        except (openai.APIConnectionError, ConnectionError) as e:
            # 7. Network/connection errors during streaming
            logger.error(f"Network error during streaming: {e}")
            yield StreamChunk(type="error", error=f"Network connection lost during streaming: {e}")
            return
        except openai.AuthenticationError as e:
            # 8. Authentication errors during streaming
            logger.error(f"Authentication error during streaming: {e}")
            yield StreamChunk(type="error", error=f"Authentication failed during streaming: {e}")
            return
        except openai.RateLimitError as e:
            # 9. Rate limiting errors during streaming
            logger.error(f"Rate limit error during streaming: {e}")
            yield StreamChunk(type="error", error=f"Rate limit exceeded during streaming: {e}")
            return
        except Exception as e:
            logger.error(f"Unexpected error during chunk processing: {e}")
            yield StreamChunk(type="error", error=f"Streaming failed: {e}")
            return


    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text (rough approximation)."""
        # Simple approximation: ~1.3 tokens per word
        return int(len(text.split()) * 1.3)

    def calculate_cost(
        self, input_tokens: int, output_tokens: int, model: str
    ) -> float:
        """Calculate cost for token usage based on OpenAI pricing (default fallback)."""
        model_lower = model.lower()
        
        # OpenAI GPT-4o pricing (most common)
        if "gpt-4o" in model_lower:
            if "mini" in model_lower:
                input_cost = (input_tokens / 1_000_000) * 0.15
                output_cost = (output_tokens / 1_000_000) * 0.60
            else:
                input_cost = (input_tokens / 1_000_000) * 2.50
                output_cost = (output_tokens / 1_000_000) * 10.00
        # GPT-4 pricing
        elif "gpt-4" in model_lower:
            if "turbo" in model_lower:
                input_cost = (input_tokens / 1_000_000) * 10.00
                output_cost = (output_tokens / 1_000_000) * 30.00
            else:
                input_cost = (input_tokens / 1_000_000) * 30.00
                output_cost = (output_tokens / 1_000_000) * 60.00
        # GPT-3.5 pricing
        elif "gpt-3.5" in model_lower:
            input_cost = (input_tokens / 1_000_000) * 0.50
            output_cost = (output_tokens / 1_000_000) * 1.50
        else:
            # Generic fallback pricing (moderate cost estimate)
            input_cost = (input_tokens / 1_000_000) * 1.00
            output_cost = (output_tokens / 1_000_000) * 3.00

        return input_cost + output_cost

    def extract_tool_name(self, tool_call: Dict[str, Any]) -> str:
        """Extract tool name from Chat Completions format."""
        return tool_call.get("function", {}).get("name", "unknown")

    def extract_tool_arguments(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """Extract tool arguments from Chat Completions format."""
        arguments = tool_call.get("function", {}).get("arguments", {})
        if isinstance(arguments, str):
            try:
                import json
                return json.loads(arguments) if arguments.strip() else {}
            except json.JSONDecodeError:
                return {}
        return arguments

    def extract_tool_call_id(self, tool_call: Dict[str, Any]) -> str:
        """Extract tool call ID from Chat Completions format."""
        return tool_call.get("id", "")

    def create_tool_result_message(
        self, tool_call: Dict[str, Any], result_content: str
    ) -> Dict[str, Any]:
        """Create tool result message for Chat Completions format."""
        tool_call_id = self.extract_tool_call_id(tool_call)
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": result_content,
        }

    def extract_tool_result_content(self, tool_result_message: Dict[str, Any]) -> str:
        """Extract content from Chat Completions tool result message."""
        return tool_result_message.get("content", "")

    def get_supported_builtin_tools(self) -> List[str]:
        """Get list of builtin tools supported by this provider."""
        # Chat Completions API doesn't typically support builtin tools like web_search
        # But some providers might - this can be overridden in subclasses
        return []
