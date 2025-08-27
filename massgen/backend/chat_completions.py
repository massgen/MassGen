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
- ZAI: ZAI_API_KEY
"""


# Standard library imports
import asyncio
import random
import uuid
from typing import Dict, List, Any, AsyncGenerator, Optional, Union, Literal


# Third-party imports
import openai
from openai import AsyncOpenAI
import logging

# Set up logger
logger = logging.getLogger(__name__)

# Local imports
from .base import LLMBackend, StreamChunk

# MCP integration imports
try:
    from ..mcp_tools import MultiMCPClient, MCPError, MCPConnectionError
    from ..mcp_tools.config_validator import MCPConfigValidator
    from ..mcp_tools.circuit_breaker import MCPCircuitBreaker
    from ..mcp_tools.exceptions import (
        MCPConfigurationError,
        MCPValidationError,
        MCPTimeoutError,
        MCPServerError,
        MCPAuthenticationError,
        MCPResourceError,
    )
    from ..mcp_tools.security import validate_url
    from .common import Function
except ImportError as e:  # MCP not installed or import failed within mcp_tools
    logger.debug(f"MCP import failed: {e}")
    MultiMCPClient = None  # type: ignore[assignment]
    MCPError = ImportError  # type: ignore[assignment]
    MCPConnectionError = ImportError  # type: ignore[assignment]
    MCPConfigValidator = None  # type: ignore[assignment]
    MCPCircuitBreaker = None  # type: ignore[assignment]
    MCPConfigurationError = ImportError  # type: ignore[assignment]
    MCPValidationError = ImportError  # type: ignore[assignment]
    MCPTimeoutError = ImportError  # type: ignore[assignment]
    MCPServerError = ImportError  # type: ignore[assignment]
    MCPAuthenticationError = ImportError  # type: ignore[assignment]
    MCPResourceError = ImportError  # type: ignore[assignment]
    validate_url = None
    Function = None


class ChatCompletionsBackend(LLMBackend):
    """Complete OpenAI-compatible Chat Completions API backend.

    Can be used directly with any OpenAI-compatible provider by setting provider name.
    Supports Cerebras AI, Together AI, Fireworks AI, DeepInfra, and other compatible providers.

    Environment Variables:
        Provider-specific API keys are automatically detected based on provider name.
        See ProviderRegistry.PROVIDERS for the complete list.

    """

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(api_key, **kwargs)
        
        # MCP integration
        self.mcp_servers = kwargs.pop("mcp_servers", [])
        self.allowed_tools = kwargs.pop("allowed_tools", None)
        self.exclude_tools = kwargs.pop("exclude_tools", None)
        self._mcp_client: Optional[MultiMCPClient] = None
        self._mcp_initialized = False

        # MCP tool execution monitoring
        self._mcp_tool_calls_count = 0
        self._mcp_tool_failures = 0
        
        # Limit for message history growth within MCP execution loop
        self._max_mcp_message_history = kwargs.pop("max_mcp_message_history", 200)
        
        # Lock to prevent concurrent MCP initialization
        self._mcp_setup_lock = asyncio.Lock()

        # Circuit breakers for different transport types with explicit configuration
        self._mcp_tools_circuit_breaker = None
        self._circuit_breakers_enabled = MCPCircuitBreaker is not None
        
        # Initialize circuit breakers if available
        if self._circuit_breakers_enabled:
            from ..mcp_tools.circuit_breaker import CircuitBreakerConfig
            
            # Configure circuit breakers with explicit parameters for different transport types
            mcp_tools_config = CircuitBreakerConfig(
                max_failures=3,      
                reset_time_seconds=30,  
                backoff_multiplier=2,   
                max_backoff_multiplier=8  
            )
            self._mcp_tools_circuit_breaker = MCPCircuitBreaker(mcp_tools_config)
            
            logger.debug("Circuit breakers initialized for MCP transport types")
        else:
            logger.debug("Circuit breakers not available - proceeding without circuit breaker protection")

        # Separation containers for different transport types
        # Transport Types - "stdio" & "streamable-http"
        self._mcp_tools_servers: List[Dict[str, Any]] = [] 

        # Function registry for mcp_tools-based servers
        self.functions: Dict[str, Function] = {}

        # Thread safety for counters
        self._stats_lock = asyncio.Lock()

        # Separate MCP servers by transport type if any are configured
        if self.mcp_servers:
            self._separate_mcp_servers_by_transport_type()

    def _normalize_mcp_servers(self) -> List[Dict[str, Any]]:
        """Validate and normalize mcp_servers into a list of dicts."""
        servers = self.mcp_servers
        if not servers:
            return []
        if isinstance(servers, dict):
            return [servers]
        if not isinstance(servers, list):
            raise ValueError(
                f"mcp_servers must be a list or dict, got {type(servers).__name__}"
            )
        normalized: List[Dict[str, Any]] = []
        for idx, entry in enumerate(servers):
            if not isinstance(entry, dict):
                raise ValueError(
                    f"MCP server configuration at index {idx} must be a dictionary, got {type(entry).__name__}"
                )
            normalized.append(entry)
        return normalized

    def _separate_mcp_servers_by_transport_type(self) -> None:
        """
        Separate MCP servers into local execution transport types.
        
        Transport Types:
        - "stdio" & "streamable-http"
        """
        validated_servers = self._normalize_mcp_servers()

        for server in validated_servers:
            # Accept both 'type' and legacy 'transport_type' keys
            transport_type = server.get("type") or server.get("transport_type")
            server_name = server.get("name", "unnamed")

            if not transport_type:
                logger.warning(
                    f"MCP server '{server_name}' missing required 'type' field. "
                    f"Supported types: 'stdio', 'streamable-http'. Skipping server."
                )
                continue

            if transport_type in ["stdio", "streamable-http"]:
                # Both stdio and streamable-http use our mcp_tools folder (MultiMCPClient)
                self._mcp_tools_servers.append(server)
            else:
                logger.warning(
                    f"Unknown MCP transport type '{transport_type}' for server '{server_name}'. "
                    f"Supported types: 'stdio', 'streamable-http'. Skipping server."
                )

    def _apply_mcp_tools_circuit_breaker_filtering(self, servers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter MCP tools servers based on circuit breaker state."""
        if not self._circuit_breakers_enabled or not self._mcp_tools_circuit_breaker:
            return servers
        
        filtered_servers = []
        for server in servers:
            server_name = server.get("name", "unnamed")
            if not self._mcp_tools_circuit_breaker.should_skip_server(server_name):
                filtered_servers.append(server)
            else:
                logger.debug(f"Circuit breaker: Skipping MCP tools server {server_name} (circuit open)")
        
        return filtered_servers

    def get_circuit_breaker_status(self) -> Dict[str, Any]:
        """Get comprehensive circuit breaker status for all MCP servers.

        Returns:
            Dict with mcp_tools circuit breaker status information
        """
        status = {
            "mcp_tools": {
                "enabled": self._circuit_breakers_enabled and self._mcp_tools_circuit_breaker is not None,
                "servers": {}
            }
        }
        
        # Check mcp_tools servers
        if status["mcp_tools"]["enabled"]:
            for server in self._mcp_tools_servers:
                server_name = server.get("name", "unnamed")
                try:
                    would_skip = self._mcp_tools_circuit_breaker.should_skip_server(server_name)
                    status["mcp_tools"]["servers"][server_name] = {"would_skip": would_skip}
                except Exception as e:
                    logger.warning(f"Failed to check circuit breaker status for mcp_tools server {server_name}: {e}")
                    status["mcp_tools"]["servers"][server_name] = {"would_skip": False}
        else:
            logger.debug("Circuit breaker disabled for mcp_tools - status fallback to enabled for all servers")

        return status
        

    async def _record_mcp_tools_success(self, servers: List[Dict[str, Any]]) -> None:
        """Record successful MCP tools operation for circuit breaker."""
        if self._mcp_tools_circuit_breaker:
            for server in servers:
                server_name = server.get("name", "unknown")
                self._mcp_tools_circuit_breaker.record_success(server_name)
                logger.debug(f"Recorded MCP tools success for server: {server_name}")
        

    async def _record_mcp_tools_failure(self, servers: List[Dict[str, Any]], error_message: str) -> None:
        """Record connection failure for mcp_tools servers in circuit breaker."""
        await self._record_mcp_tools_event(servers, event="failure", error_message=error_message)

    async def _record_mcp_tools_event(
        self,
        servers: List[Dict[str, Any]],
        event: Literal["success", "failure"],
        error_message: Optional[str] = None,
    ) -> None:
        """Record success/failure for mcp_tools servers in circuit breaker."""
        if not self._circuit_breakers_enabled or not self._mcp_tools_circuit_breaker:
            return

        count = 0
        for server in servers:
            server_name = server.get("name", "unnamed")
            try:
                if event == "success":
                    self._mcp_tools_circuit_breaker.record_success(server_name)
                else:
                    self._mcp_tools_circuit_breaker.record_failure(server_name)
                count += 1
            except Exception as cb_error:
                logger.warning(
                    f"Circuit breaker record_{event} failed for mcp_tools server {server_name}: {cb_error}"
                )

        if count > 0:
            if event == "success":
                logger.debug(
                    f"Circuit breaker: Recorded success for {count} mcp_tools servers"
                )
            else:
                logger.warning(
                    f"Circuit breaker: Recorded failure for {count} mcp_tools servers. Error: {error_message}"
                )




    @staticmethod
    def _get_mcp_error_info(error: Exception) -> tuple[str, str, str]:
        """Get standardized MCP error information.

        Returns:
            tuple: (log_type, user_message, error_category)
        """
        error_mappings = {
            MCPConnectionError: ("connection error", "MCP connection failed", "connection"),
            MCPTimeoutError: ("timeout error", "MCP session timeout", "timeout"),
            MCPServerError: ("server error", "MCP server error", "server"),
            MCPError: ("MCP error", "MCP error", "general"),
        }

        return error_mappings.get(
            type(error), ("unexpected error", "MCP communication error", "unknown")
        )

    def _log_mcp_error(self, error: Exception, operation: str) -> None:
        """Log MCP errors with appropriate severity based on error type."""
        error_type = type(error).__name__
        if isinstance(error, (MCPConnectionError, MCPTimeoutError)):
            logger.warning(f"MCP {operation} failed (transient {error_type}): {error}")
        elif isinstance(error, (MCPAuthenticationError, MCPResourceError)):
            logger.error(f"MCP {operation} failed (auth/resource {error_type}): {error}")
        elif isinstance(error, MCPServerError):
            logger.error(f"MCP {operation} failed (server error {error_type}): {error}")
        elif isinstance(error, MCPError):
            logger.warning(f"MCP {operation} failed (general {error_type}): {error}")
        else:
            logger.error(f"MCP {operation} failed (unexpected {error_type}): {error}")

    @staticmethod
    def _is_transient_error(error: Exception) -> bool:
        """Determine if an error is transient and should be retried."""
        transient_errors = (
            MCPTimeoutError,
            MCPConnectionError,
            asyncio.TimeoutError,
            ConnectionResetError,
            ConnectionAbortedError,
        )
        return isinstance(error, transient_errors)

    async def _setup_mcp_tools(self) -> None:
        """Initialize MCP client for mcp_tools-based servers (stdio + streamable-http)."""
        async with self._mcp_setup_lock:
            if not self._mcp_tools_servers or self._mcp_initialized:
                return

            if MultiMCPClient is None:
                reason = "MCP import failed - MultiMCPClient not available"
                logger.warning(
                    "MCP support import failed (%s). mcp_tools servers were provided; falling back to workflow tools without MCP. Ensure the 'mcp' package is installed and compatible with this codebase.",
                    reason,
                )
                # Clear mcp_tools servers to prevent further attempts
                self._mcp_tools_servers = []
                return

            try:
                # Extract tool filtering parameters
                allowed_tools = self.allowed_tools
                exclude_tools = self.exclude_tools

                # Validate MCP configuration before initialization
                if MCPConfigValidator is not None:
                    try:
                        backend_config = {
                            "mcp_servers": self._mcp_tools_servers,
                            "allowed_tools": allowed_tools,
                            "exclude_tools": exclude_tools
                        }

                        # Use the comprehensive validator class for enhanced validation
                        validator = MCPConfigValidator()
                        validated_config = validator.validate_backend_mcp_config(backend_config)

                        self._mcp_tools_servers = validated_config.get("mcp_servers", self._mcp_tools_servers)

                        # Extract validated tool filtering parameters
                        allowed_tools = validated_config.get("allowed_tools", self.allowed_tools)
                        exclude_tools = validated_config.get("exclude_tools", self.exclude_tools)

                        logger.debug(
                            f"MCP configuration validation passed for {len(self._mcp_tools_servers)} mcp_tools servers"
                        )

                    except (MCPConfigurationError, MCPValidationError) as validation_error:
                        logger.error(f"MCP configuration validation failed: {validation_error}")
                        self._mcp_tools_servers = []  # Clear invalid configuration
                        return

                else:
                    logger.debug("MCP validation not available, proceeding without validation")

                logger.info(
                    f"Setting up MCP sessions with {len(self._mcp_tools_servers)} mcp_tools servers (stdio + streamable-http)"
                )

                # Log tool filtering if configured
                if allowed_tools:
                    logger.info(f"MCP tool filtering - allowed tools: {allowed_tools}")
                if exclude_tools:
                    logger.info(f"MCP tool filtering - excluding: {exclude_tools}")

                # Create MCP client connection with retry logic and circuit breaker
                max_mcp_retries = 3
                mcp_connected = False

                for retry_count in range(1, max_mcp_retries + 1):
                    try:
                        if retry_count > 1:
                            logger.info(f"MCP connection retry {retry_count}/{max_mcp_retries}")
                            await asyncio.sleep(0.5 * retry_count)  # Progressive backoff

                        # Apply circuit breaker filtering for mcp_tools servers
                        filtered_servers = self._apply_mcp_tools_circuit_breaker_filtering(
                            self._mcp_tools_servers
                        )

                        if not filtered_servers:
                            logger.warning("All MCP servers filtered out by circuit breaker")
                            continue

                        # Initialize and connect MultiMCPClient with validated servers (same as response.py)
                        logger.debug(f"Initializing MCP client with {len(filtered_servers)} servers")
                        self._mcp_client = await MultiMCPClient.create_and_connect(
                            filtered_servers,
                            timeout_seconds=30,
                            allowed_tools=allowed_tools,
                            exclude_tools=exclude_tools,
                        )
                        
                        # Convert MCP tools to Function objects for compatibility (same as response.py)
                        import json
                        for tool_name, tool in self._mcp_client.tools.items():
                            try:
                                # Fix closure bug by using default parameter to capture tool_name
                                def create_tool_entrypoint(captured_tool_name: str = tool_name):
                                    async def tool_entrypoint(input_str: str) -> Any:
                                        try:
                                            arguments = json.loads(input_str)
                                        except (json.JSONDecodeError, ValueError) as e:
                                            logger.error(f"Invalid JSON arguments for MCP tool {captured_tool_name}: {e}")
                                            raise MCPValidationError(
                                                f"Invalid JSON arguments for tool {captured_tool_name}: {e}",
                                                field="arguments",
                                                value=input_str
                                            )
                                        return await self._mcp_client.call_tool(
                                            captured_tool_name, arguments
                                        )
                                    return tool_entrypoint

                                # Create the entrypoint with captured tool name
                                entrypoint = create_tool_entrypoint()

                                # Create a Function for the tool
                                function = Function(
                                    name=tool_name,
                                    description=tool.description,
                                    parameters=tool.inputSchema,
                                    entrypoint=entrypoint,
                                )

                                # Register the Function
                                self.functions[function.name] = function
                                logger.debug(f"Function: {function.name} registered")
                            except Exception as e:
                                logger.error(f"Failed to register tool {tool_name}: {e}")
                        self._mcp_initialized = True
                        mcp_connected = True

                        # Record successful setup for circuit breaker
                        await self._record_mcp_tools_success(filtered_servers)

                        logger.info(
                            f"MCP tools initialized successfully with {len(self.functions)} functions "
                            f"from {len(filtered_servers)} servers"
                        )
                        break

                    except (MCPConnectionError, MCPTimeoutError, MCPServerError) as mcp_error:
                        logger.warning(f"MCP connection attempt {retry_count} failed: {mcp_error}")
                        await self._record_mcp_tools_failure(self._mcp_tools_servers, str(mcp_error))
                        
                        if retry_count == max_mcp_retries:
                            logger.error("All MCP connection retries exhausted")
                            break
                            
                    except Exception as unexpected_error:
                        logger.error(f"Unexpected error during MCP setup attempt {retry_count}: {unexpected_error}")
                        if retry_count == max_mcp_retries:
                            break

                if not mcp_connected:
                    logger.info("Falling back to workflow tools after MCP connection failures")
                    return

            except Exception as setup_error:
                logger.error(f"MCP setup failed: {setup_error}")
                self._mcp_tools_servers = []
                return

    def _convert_mcp_tools_to_chat_completions_format(self) -> List[Dict[str, Any]]:
        """Convert MCP tools (stdio + streamable-http) to Chat Completions format."""
        if not self.functions:
            return []

        converted_tools = []
        for function in self.functions.values(): 
            openai_format = function.to_openai_format()
            # Convert from Response API format to Chat Completions format
            chat_completions_format = {
                "type": "function",
                "function": {
                    "name": openai_format["name"],
                    "description": openai_format["description"],
                    "parameters": (openai_format.get("parameters") or {}),
                }
            }
            converted_tools.append(chat_completions_format)

        logger.debug(
            f"Converted {len(converted_tools)} MCP tools (stdio + streamable-http) to Chat Completions format"
        )
        return converted_tools

    async def cleanup_mcp(self) -> None:
        """Cleanup MCP resources and disconnect client."""
        if self._mcp_client:
            try:
                logger.debug("Starting MCP client cleanup")
                await self._mcp_client.disconnect()
                logger.info("MCP client disconnected successfully")
            except (MCPConnectionError, MCPTimeoutError, MCPServerError, MCPError, Exception) as e:
                self._log_mcp_error(e, "disconnect")
            finally:
                self._mcp_client = None
                self._mcp_initialized = False
                logger.debug("MCP client cleanup completed")


    def get_provider_name(self) -> str:
        """Get the name of this provider."""
        # Check if provider name was explicitly set in config
        if "provider" in self.config:
            return self.config["provider"]
        elif "provider_name" in self.config:
            return self.config["provider_name"]

        # Try to infer from base_url
        base_url = self.config.get("base_url", "")
        if "openai.com" in base_url:
            return "OpenAI"
        elif "cerebras.ai" in base_url:
            return "Cerebras AI"
        elif "together.ai" in base_url:
            return "Together AI"
        elif "fireworks.ai" in base_url:
            return "Fireworks AI"
        elif "groq.com" in base_url:
            return "Groq"
        elif "nebius.ai" in base_url:
            return "Nebius AI"
        elif "openrouter.ai" in base_url:
            return "OpenRouter"
        elif "z.ai" in base_url:
            return "ZAI"
        else:
            return "ChatCompletion"

    def convert_tools_to_chat_completions_format(
        self, tools: List[Union[Dict[str, Any], Any]]
    ) -> List[Dict[str, Any]]:
        """Convert tools from Response API format to Chat Completions format if needed.

        Response API format: {"type": "function", "name": ..., "description": ..., "parameters": ...}
        Chat Completions format: {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
        """
        if not tools:
            return tools

        converted_tools = []
        for tool in tools:
            # Handle MCP Function objects directly
            if Function is not None and isinstance(tool, Function):
                openai_format = tool.to_openai_format()
                name = openai_format.get("name")
                if not name:
                    logger.warning("MCP Function missing name; skipping tool conversion")
                    continue
                description = openai_format.get("description", "")
                parameters = openai_format.get("parameters") or {}
                converted_tools.append({
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": description,
                        "parameters": parameters,
                    }
                })
            elif isinstance(tool, dict) and tool.get("type") == "function":
                if "function" in tool:
                    # Already in Chat Completions format
                    converted_tools.append(tool)
                elif "name" in tool:
                    converted_tools.append({
                        "type": "function",
                        "function": {
                            "name": tool["name"],
                            "description": tool.get("description", ""),
                            "parameters": (tool.get("parameters") or {}),
                        }
                    })
                else:
                    
                    converted_tools.append(tool)
            else:
                
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
                            # handle reasoning first
                            reasoning_active_key = f"_reasoning_active"
                            if hasattr(self, reasoning_active_key):
                                if getattr(self, reasoning_active_key) == True:
                                    setattr(self, reasoning_active_key, False)
                                    yield StreamChunk(type="reasoning_done", content="")
                            content_chunk = delta.content
                            content += content_chunk
                            yield StreamChunk(type="content", content=content_chunk)

                        # Provider-specific reasoning/thinking streams (non-standard OpenAI fields)
                        if getattr(delta, "reasoning_content", None):
                            reasoning_active_key = f"_reasoning_active"
                            setattr(self, reasoning_active_key, True)
                            thinking_delta = getattr(delta, "reasoning_content")
                            if thinking_delta:
                                yield StreamChunk(
                                    type="reasoning",
                                    content=thinking_delta,
                                    reasoning_delta=thinking_delta,
                                )

                        # Tool calls streaming (OpenAI-style)
                        if getattr(delta, "tool_calls", None):
                            # handle reasoning first
                            reasoning_active_key = f"_reasoning_active"
                            if hasattr(self, reasoning_active_key):
                                if getattr(self, reasoning_active_key) == True:
                                    setattr(self, reasoning_active_key, False)
                                    yield StreamChunk(type="reasoning_done", content="")

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
                                    if getattr(
                                        tool_call_delta.function, "arguments", None
                                    ):
                                        current_tool_calls[index]["function"][
                                            "arguments"
                                        ] += tool_call_delta.function.arguments

                    # Handle finish reason
                    if getattr(choice, "finish_reason", None):
                        # handle reasoning first
                        reasoning_active_key = f"_reasoning_active"
                        if hasattr(self, reasoning_active_key):
                            if getattr(self, reasoning_active_key) == True:
                                setattr(self, reasoning_active_key, False)
                                yield StreamChunk(type="reasoning_done", content="")

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

    def _build_chat_completions_params(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], **kwargs
    ) -> Dict[str, Any]:
        """Build parameters for Chat Completions API call.

        Filters out non-OpenAI params from both base config and per-call kwargs.
        """
        # Parameters that must never be forwarded to the Chat Completions API
        excluded_params = {
            "enable_web_search",
            "enable_code_interpreter",
            "base_url",
            "agent_id",
            "session_id",
            "type",        
            "mcp_servers",   # MCP-specific parameter
            "allowed_tools", # Tool filtering parameter
            "exclude_tools", # Tool filtering parameter
            "tools",      
        }

        # Start with a filtered copy of base config
        api_params = {k: v for k, v in self.config.items() if k not in excluded_params and v is not None}

        # Add messages
        api_params["messages"] = messages

        # Add tools if provided
        if tools:
            api_params["tools"] = tools

        # Override with any additional kwargs (also filtered)
        for key, value in kwargs.items():
            if key not in excluded_params and value is not None:
                api_params[key] = value

        return api_params


    async def stream_with_tools(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream response using OpenAI-compatible Chat Completions API."""
        try:
            import openai

            # Setup MCP tools first
            await self._setup_mcp_tools()

            # Merge constructor config with stream kwargs (stream kwargs take priority)
            all_params = {**self.config, **kwargs}

            # Get base_url from config or use OpenAI default
            base_url = all_params.get("base_url", "https://api.openai.com/v1")

            client = openai.AsyncOpenAI(api_key=self.api_key, base_url=base_url)

            # Extract framework-specific parameters
            enable_web_search = all_params.get("enable_web_search", False)
            enable_code_interpreter = all_params.get("enable_code_interpreter", False)

            # Convert tools to Chat Completions format
            converted_tools = (
                self.convert_tools_to_chat_completions_format(tools) if tools else None
            )

            # Chat Completions API parameters
            api_params = {
                "messages": messages,
                "stream": True,
            }

            # Add framework tools if provided
            if converted_tools:
                api_params["tools"] = converted_tools

            # Add MCP tools (stdio + streamable-http) to the tools list
            if self.functions:
                mcp_tools = self._convert_mcp_tools_to_chat_completions_format()
                if mcp_tools:
                    if "tools" not in api_params:
                        api_params["tools"] = []
                    api_params["tools"].extend(mcp_tools)
                    logger.debug(f"Added {len(mcp_tools)} MCP tools (stdio + streamable-http) to Chat Completions API")

            # Only stdio and streamable-http transports are supported

            # Direct passthrough of all parameters except those handled separately
            excluded_params = {
                "enable_web_search",
                "enable_code_interpreter",
                "base_url",
                "agent_id",
                "session_id",
                "type",
                "mcp_servers",  # MCP-specific parameter
                "allowed_tools",  # Tool filtering parameter
                "exclude_tools",  # Tool filtering parameter
                "tools",
            }
            for key, value in all_params.items():
                if key not in excluded_params and value is not None:
                    api_params[key] = value

            # Add provider tools (web search, code interpreter) if enabled
            provider_tools = []
            if enable_web_search:
                provider_tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": "web_search",
                            "description": "Search the web for current or factual information",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "query": {
                                        "type": "string",
                                        "description": "The search query to send to the web",
                                    }
                                },
                                "required": ["query"],
                            },
                        },
                    }
                )

            if enable_code_interpreter:
                provider_tools.append(
                    {"type": "code_interpreter", "container": {"type": "auto"}}
                )

            if provider_tools:
                if "tools" not in api_params:
                    api_params["tools"] = []
                api_params["tools"].extend(provider_tools)

            # Determine execution mode based on available MCP functions
            if self.functions:
                # stdio/streamable-http MCP execution
                logger.debug("Using stdio/streamable-http MCP execution mode")
                try:
                    async for chunk in self.stream_with_mcp(
                        client, messages, api_params.get("tools", []), **all_params
                    ):
                        yield chunk
                except (MCPConnectionError, MCPTimeoutError, MCPServerError) as mcp_error:
                    # MCP streaming failed, record failure and fallback to non-MCP mode
                    logger.warning(f"MCP streaming failed, falling back to non-MCP mode: {mcp_error}")
                    await self._record_mcp_tools_failure(self._mcp_tools_servers, str(mcp_error))
                    
                    # Fallback to simple streaming
                    async for chunk in self.stream_without_mcp(
                        client, messages, api_params.get("tools", []), **all_params
                    ):
                        yield chunk
                except Exception as unexpected_error:
                    # Unexpected error during MCP streaming
                    logger.error(f"Unexpected error in MCP streaming: {unexpected_error}")
                    yield StreamChunk(type="error", error=f"MCP streaming error: {str(unexpected_error)}")
            else:
               
                logger.debug("Using no MCP mode - simple streaming")
                async for chunk in self.stream_without_mcp(
                    client, messages, api_params.get("tools", []), **all_params
                ):
                    yield chunk

        except Exception as e:
            yield StreamChunk(
                type="error", error=f"Chat Completions API error: {str(e)}"
            )
        finally:
            # Cleanup MCP resources if initialized but context manager isn't used
            if self._mcp_initialized and not hasattr(self, '_context_manager_active'):
                try:
                    await self.cleanup_mcp()
                except Exception as cleanup_error:
                    logger.error(f"MCP cleanup failed during stream termination: {cleanup_error}")
            
            # Ensure the underlying HTTP client is properly closed to avoid event loop issues
            try:
                if hasattr(client, 'aclose'):
                    await client.aclose()
            except Exception:
                
                pass

    def _trim_message_history(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Trim message history to prevent unbounded growth in MCP execution loop.
        Preserves the first system message if present; keeps only the most recent
        messages up to the configured limit.
        """
        try:
            max_items = int(getattr(self, '_max_mcp_message_history', 200))
        except Exception:
            max_items = 200

        if max_items <= 0 or len(messages) <= max_items:
            return messages

        preserved = []
        remaining = messages
        if messages and messages[0].get("role") == "system":
            preserved = [messages[0]]
            remaining = messages[1:]

        # Keep the most recent items within the limit
        allowed = max_items - len(preserved)
        trimmed_tail = remaining[-allowed:] if allowed > 0 else []
        return preserved + trimmed_tail

    async def _execute_mcp_function_with_retry(
        self, function_name: str, args: Dict[str, Any], max_retries: int = 3
    ) -> Any:
        """Execute MCP function with exponential backoff retry logic.
        
        Args:
            function_name: Name of the MCP function to call
            args: Function arguments as dictionary
            max_retries: Maximum number of retry attempts
            
        Returns:
            Function result or structured error payload if all retries fail
        """
        async with self._stats_lock:
            self._mcp_tool_calls_count += 1
            call_index_snapshot = self._mcp_tool_calls_count

        import json

        for attempt in range(max_retries + 1):
            try:
                # Convert args to JSON string for the function call
                arguments_json = json.dumps(args)
                
                # Execute the MCP function with enhanced error handling
                result = await self.functions[function_name].call(arguments_json)
                
                # Successful execution, return result
                if attempt > 0:
                    logger.info(f"MCP function {function_name} (#{call_index_snapshot}) succeeded on retry attempt {attempt}")
                
                return result
                
            except (MCPAuthenticationError, MCPResourceError) as auth_error:
                self._log_mcp_error(auth_error, f"function call {function_name}")
                await self._record_mcp_tools_failure(self._mcp_tools_servers, str(auth_error))
                async with self._stats_lock:
                    self._mcp_tool_failures += 1
                return {"error": str(auth_error), "type": "auth_resource_error", "function": function_name}
                
            except Exception as e:
                is_last_attempt = attempt == max_retries
                
                if self._is_transient_error(e) and not is_last_attempt:
                    # Calculate exponential backoff with jitter
                    base_delay = 0.5  
                    backoff_delay = base_delay * (2 ** attempt)
                    jitter = random.uniform(0.1, 0.3) * backoff_delay
                    total_delay = backoff_delay + jitter
                    
                    self._log_mcp_error(e, f"function call {function_name} (attempt {attempt + 1})")
                    logger.warning(f"Retrying in {total_delay:.2f}s...")
                    
                    await asyncio.sleep(total_delay)
                    continue
                else:
                    self._log_mcp_error(e, f"function call {function_name} (final)")
                    await self._record_mcp_tools_failure(self._mcp_tools_servers, str(e))
                    
                    # Record failure in stats
                    async with self._stats_lock:
                        self._mcp_tool_failures += 1

                    # Return structured error payload as fallback
                    return {"error": str(e), "type": "execution_error", "function": function_name, "attempts": attempt + 1}
        
        async with self._stats_lock:
            self._mcp_tool_failures += 1
        return {"error": f"Maximum retries ({max_retries}) exceeded", "type": "retry_exhausted", "function": function_name}

    async def stream_with_mcp(
        self, client, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream response with stdio/streamable-http MCP function call execution loop.Handles iterative execution for both stdio and streamable-http MCP servers
        using Chat Completions API format.
        """
        logger.debug("Starting stdio/streamable-http MCP execution mode")
        max_iterations = 10
        current_messages = self._trim_message_history(messages.copy())

        for iteration in range(max_iterations):
            logger.debug(f"MCP function call iteration {iteration + 1}/{max_iterations}")

            # Build API params for this iteration
            api_params = self._build_chat_completions_params(
                current_messages, tools, **kwargs
            )
            api_params["stream"] = True

            # Start streaming
            stream = await client.chat.completions.create(**api_params)

            # Track function calls in this iteration
            captured_tool_calls = []
            response_completed = False
            finish_reason = None
            tool_calls_emitted = set()

            async for chunk in stream:
                # Handle Chat Completions streaming format
                if hasattr(chunk, 'choices') and chunk.choices:
                    choice = chunk.choices[0]
                    delta = choice.delta

                    # Handle content streaming
                    if hasattr(delta, 'content') and delta.content:
                        content_delta = delta.content
                        yield StreamChunk(type="content", content=content_delta)

                    # Handle tool calls
                    if hasattr(delta, 'tool_calls') and delta.tool_calls:
                        for tool_call_delta in delta.tool_calls:
                            index = tool_call_delta.index

                            # Ensure the list has a slot for this index
                            if index >= len(captured_tool_calls):
                                captured_tool_calls.extend([None] * (index + 1 - len(captured_tool_calls)))

                            # Initialize call entry if missing
                            if captured_tool_calls[index] is None:
                                captured_tool_calls[index] = {
                                    "id": (tool_call_delta.id or ""),
                                    "type": "function",
                                    "function": {
                                        "name": (tool_call_delta.function.name if tool_call_delta.function else "") or "",
                                        "arguments": ""
                                    }
                                }
                            else:
                                if tool_call_delta.id and tool_call_delta.id != captured_tool_calls[index]["id"]:
                                    captured_tool_calls[index]["id"] = tool_call_delta.id
                                    logger.debug(f"Updated tool call ID for index {index} -> {tool_call_delta.id}")

                            # Accumulate function arguments
                            if tool_call_delta.function and getattr(tool_call_delta.function, "arguments", None):
                                captured_tool_calls[index]["function"]["arguments"] += tool_call_delta.function.arguments

                            logger.debug(f"Tool call detected: {captured_tool_calls[index]['function']['name']}")

                    # Check if response is finished and capture finish_reason
                    if choice.finish_reason:
                        finish_reason = choice.finish_reason
                        response_completed = True
                        break

            # Filter out None entries and validate tool call completeness
            valid_tool_calls = []
            for call in captured_tool_calls:
                if call and call.get("function", {}).get("name"):
                    # Validate tool call completeness
                    function_name = call["function"]["name"]
                    arguments = call["function"]["arguments"]
                    call_id = call.get("id")
                    is_complete = bool(function_name) and bool(call_id)
                    if arguments:
                        try:
                            import json
                            json.loads(arguments)
                        except (json.JSONDecodeError, TypeError):
                            logger.warning(f"Tool call {function_name} has invalid JSON arguments: {arguments}")
                            is_complete = False
                    
                    if is_complete:
                        valid_tool_calls.append(call)
                        
                        # Emit tool_call content message now that arguments are complete
                        if call_id not in tool_calls_emitted:
                            tool_name = self.extract_tool_name(call)
                            
                            yield StreamChunk(
                                type="content",
                                content=f"\n🔧 [MCP] Calling tool '{tool_name}'...\n"
                            )
                            tool_calls_emitted.add(call_id)
                else:
                    # Extract function name safely for logging incomplete tool calls
                    incomplete_function_name = call.get("function", {}).get("name", "unknown") if call else "unknown"
                    logger.warning(f"Incomplete tool call detected: {incomplete_function_name}, skipping execution")
            
            captured_tool_calls = valid_tool_calls

            # Enhanced finish_reason handling
            if finish_reason == "tool_calls":
                logger.debug("Finish reason: tool_calls - proceeding with tool execution")
            elif finish_reason == "stop" and captured_tool_calls:
                # Unexpected: stop with partial tool calls - treat as non-MCP content
                logger.warning("Finish reason: stop but tool calls detected - treating as non-MCP content")
                captured_tool_calls = []  # Clear to avoid execution

            # Execute any captured tool calls
            if captured_tool_calls:
                non_mcp_functions = [call for call in captured_tool_calls 
                                   if call["function"]["name"] not in (self.functions or {})]

                if non_mcp_functions:
                    # Detect workflow tools specifically
                    workflow_tool_names = [self.extract_tool_name(call) for call in non_mcp_functions]
                    is_workflow_tools = any(name in ["vote", "new_answer"] for name in workflow_tool_names)
                    
                    if is_workflow_tools:
                        logger.debug(
                            f"Workflow tools detected: {workflow_tool_names}. "
                            f"Exiting MCP execution loop to allow orchestrator handling."
                        )
                    else:
                        logger.debug(
                            f"Non-MCP function calls detected: {workflow_tool_names}. "
                            f"Exiting MCP execution loop."
                        )
                    # This forwards workflow tools (vote, new_answer) to the orchestrator
                    yield StreamChunk(
                        type="tool_calls",
                        tool_calls=captured_tool_calls  
                    )
                    
                    # Add assistant message with tool_calls to history before exiting
                    assistant_message = {
                        "role": "assistant",
                        "content": None, 
                        "tool_calls": captured_tool_calls
                    }
                    current_messages.append(assistant_message)
                    
                    # Exit MCP execution loop and let the normal workflow handle them
                    yield StreamChunk(type="done")
                    return

                # Add assistant message with tool calls to history
                assistant_message = {
                    "role": "assistant",
                    "content": None,  
                    "tool_calls": captured_tool_calls
                }
                current_messages.append(assistant_message)

                # Execute only MCP function calls
                mcp_functions_executed = False
                for call in captured_tool_calls:
                    function_name = call["function"]["name"]
                    if function_name in (self.functions or {}):
                        # Execute MCP function with retry and comprehensive error handling
                        import json
                        try:
                            args_dict = json.loads(call["function"]["arguments"]) if isinstance(call["function"]["arguments"], str) else call["function"]["arguments"]
                            result = await self._execute_mcp_function_with_retry(
                                function_name, args_dict
                            )
                        except Exception as exec_error:
                            logger.error(f"MCP function execution failed for {function_name}: {exec_error}")
                            result = f"Error: Function execution failed - {str(exec_error)}"

                        # Use provider-supplied ID for tool result
                        final_id = self.extract_tool_call_id(call)

                        # Emit tool completion content message after execution
                        yield StreamChunk(
                            type="content",
                            content=f"\n✅ [MCP] Tool '{function_name}' completed\n"
                        )

                        # Create tool result message with correct ID
                        call_with_final_id = call.copy()
                        call_with_final_id["id"] = final_id
                        tool_message = self.create_tool_result_message(call_with_final_id, str(result))
                        current_messages.append(tool_message)

                        logger.debug(f"Executed MCP function {function_name} (stdio/streamable-http)")
                        mcp_functions_executed = True

                        # Trim history after each execution to bound memory usage
                        current_messages = self._trim_message_history(current_messages)

                # After executing MCP functions, continue to next iteration to get the final response
                if mcp_functions_executed:
                    continue
                else:  
                    yield StreamChunk(type="done")
                    return
            elif response_completed:
                
                yield StreamChunk(type="done")
                return
            else:
                continue

        
        logger.warning(f"Max MCP function call iterations ({max_iterations}) reached")
        yield StreamChunk(type="done")

    async def stream_without_mcp(
        self, client, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream response without MCP functionality - simple streaming fallback."""
        logger.debug("Starting no MCP mode - simple streaming")
        
        try:
           
            api_params = self._build_chat_completions_params(messages, tools, **kwargs)
            api_params["stream"] = True

            stream = await client.chat.completions.create(**api_params)

            async for chunk in self.handle_chat_completions_stream(stream, kwargs.get('enable_web_search', False)):
                yield chunk

        except Exception as e:
            logger.error(f"Non-MCP streaming failed: {e}")
            yield StreamChunk(type="error", error=f"Chat Completions API error: {str(e)}")

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

    async def __aenter__(self) -> "ChatCompletionsBackend":
        """Async context manager entry."""
        logger.debug("Entering ChatCompletionsBackend async context")
        self._context_manager_active = True
        return self

    async def __aexit__(self, exc_type: Optional[type], exc_val: Optional[BaseException], exc_tb: Optional[object]) -> bool:
        """Async context manager exit."""
        logger.debug("Exiting ChatCompletionsBackend async context")
        try:
            await self.cleanup_mcp()
        except Exception as e:
            logger.error(f"Error during ChatCompletionsBackend cleanup: {e}")
        finally:
            self._context_manager_active = False
        logger.debug("ChatCompletionsBackend async context exit completed")
        return False

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
