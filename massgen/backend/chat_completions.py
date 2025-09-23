# -*- coding: utf-8 -*-
"""
Base class for backends using OpenAI Chat Completions API format.
Handles common message processing, tool conversion, and streaming patterns.

Supported Providers and Environment Variables:
- OpenAI: OPENAI_API_KEY
- Cerebras AI: CEREBRAS_API_KEY
- Together AI: TOGETHER_API_KEY
- Fireworks AI: FIREWORKS_API_KEY
- Groq: GROQ_API_KEY
- Kimi/Moonshot: MOONSHOT_API_KEY or KIMI_API_KEY
- Nebius AI Studio: NEBIUS_API_KEY
- OpenRouter: OPENROUTER_API_KEY
- ZAI: ZAI_API_KEY
"""

from __future__ import annotations

# Standard library imports
import asyncio
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Tuple

# Third-party imports
from openai import AsyncOpenAI

from ..logger_config import (
    log_backend_activity,
    log_backend_agent_message,
    log_stream_chunk,
    logger,
)

# Local imports
from .base import FilesystemSupport, LLMBackend, StreamChunk

# MCP integration imports
try:
    from ..mcp_tools import (
        Function,
        MCPCircuitBreaker,
        MCPCircuitBreakerManager,
        MCPConfigHelper,
        MCPConnectionError,
        MCPError,
        MCPErrorHandler,
        MCPExecutionManager,
        MCPMessageManager,
        MCPResourceManager,
        MCPServerError,
        MCPSetupManager,
        MCPTimeoutError,
        MultiMCPClient,
    )

except ImportError as e:  # MCP not installed or import failed
    logger.warning(f"MCP import failed: {e}")
    # Create fallback assignments for all MCP imports
    _mcp_fallbacks = {
        "MultiMCPClient": None,
        "MCPCircuitBreaker": None,
        "Function": None,
        "MCPConfigValidator": None,
        "MCPErrorHandler": None,
        "MCPSetupManager": None,
        "MCPResourceManager": None,
        "MCPExecutionManager": None,
        "MCPRetryHandler": None,
        "MCPMessageManager": None,
        "MCPConfigHelper": None,
        "MCPCircuitBreakerManager": None,
        "MCPError": ImportError,
        "MCPConnectionError": ImportError,
        "MCPConfigurationError": ImportError,
        "MCPValidationError": ImportError,
        "MCPTimeoutError": ImportError,
        "MCPServerError": ImportError,
    }
    globals().update(_mcp_fallbacks)


class ChatCompletionsBackend(LLMBackend):
    """Complete OpenAI-compatible Chat Completions API backend.

    Can be used directly with any OpenAI-compatible provider by setting provider name.
    Supports Cerebras AI, Together AI, Fireworks AI, DeepInfra, and other compatible providers.

    Environment Variables:
        Provider-specific API keys are automatically detected based on provider name.
        See ProviderRegistry.PROVIDERS for the complete list.

    """

    # Parameters to exclude when building API requests
    # Merge base class exclusions with backend-specific ones
    EXCLUDED_API_PARAMS = LLMBackend.get_base_excluded_config_params().union(
        {
            "base_url",  # Used for client initialization, not API calls
            "enable_web_search",
            "enable_code_interpreter",
            "allowed_tools",  # Tool filtering parameter
            "exclude_tools",  # Tool filtering parameter
        },
    )

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(api_key, **kwargs)

        # MCP integration (filesystem MCP server may have been injected by base class)
        self.mcp_servers = self.config.get("mcp_servers", [])
        self.allowed_tools = kwargs.pop("allowed_tools", None)
        self.exclude_tools = kwargs.pop("exclude_tools", None)
        self._mcp_client: Optional[MultiMCPClient] = None
        self._mcp_initialized = False

        # MCP tool execution monitoring
        self._mcp_tool_calls_count = 0
        self._mcp_tool_failures = 0
        self._mcp_function_names: set[str] = set()

        # Circuit breaker for MCP tools (stdio + streamable-http) with explicit configuration
        self._mcp_tools_circuit_breaker = None  # For stdio + streamable-http
        self._circuit_breakers_enabled = MCPCircuitBreaker is not None

        # Initialize circuit breaker if available
        if self._circuit_breakers_enabled:
            # Use shared utility to build circuit breaker configuration
            mcp_tools_config = MCPConfigHelper.build_circuit_breaker_config("mcp_tools")

            if mcp_tools_config:
                self._mcp_tools_circuit_breaker = MCPCircuitBreaker(mcp_tools_config)
                logger.info("Circuit breaker initialized for MCP tools")
            else:
                logger.warning(
                    "MCP tools circuit breaker config not available, disabling circuit breaker functionality",
                )
                self._circuit_breakers_enabled = False
        else:
            logger.warning(
                "Circuit breakers not available - proceeding without circuit breaker protection",
            )

        # Transport Types:
        # - "stdio" & "streamable-http": Use our mcp_tools folder (MultiMCPClient)

        # Function registry for mcp_tools-based servers (stdio + streamable-http)
        self._mcp_functions: Dict[str, Function] = {}

        # Thread safety for counters
        self._stats_lock = asyncio.Lock()

        # Limit for message history growth within MCP execution loop
        self._max_mcp_message_history = kwargs.pop("max_mcp_message_history", 200)

        # Initialize backend name and agent ID for MCP operations
        self.backend_name = self.get_provider_name()
        self.agent_id = kwargs.get("agent_id", None)

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
        elif "together.xyz" in base_url:
            return "Together AI"
        elif "fireworks.ai" in base_url:
            return "Fireworks AI"
        elif "groq.com" in base_url:
            return "Groq"
        elif "openrouter.ai" in base_url:
            return "OpenRouter"
        elif "z.ai" in base_url or "bigmodel.cn" in base_url:
            return "ZAI"
        elif "nebius.com" in base_url:
            return "Nebius AI Studio"
        elif "moonshot.ai" in base_url or "moonshot.cn" in base_url:
            return "Kimi"
        else:
            return "ChatCompletion"

    async def _setup_mcp_tools(self) -> None:
        """Initialize MCP client for mcp_tools-based servers (stdio + streamable-http)."""
        if not self.mcp_servers or self._mcp_initialized:
            return

        try:
            # Normalize and separate MCP servers by transport type using mcp_tools utilities
            normalized_servers = MCPSetupManager.normalize_mcp_servers(
                self.mcp_servers,
                backend_name=self.backend_name,
                agent_id=self.agent_id,
            )
            mcp_tools_servers = MCPSetupManager.separate_stdio_streamable_servers(
                normalized_servers,
                backend_name=self.backend_name,
                agent_id=self.agent_id,
            )

            if not mcp_tools_servers:
                logger.info("No stdio/streamable-http servers configured")
                return

            # Apply circuit breaker filtering before connection attempts
            if self._circuit_breakers_enabled and self._mcp_tools_circuit_breaker:
                filtered_servers = MCPCircuitBreakerManager.apply_circuit_breaker_filtering(
                    mcp_tools_servers,
                    self._mcp_tools_circuit_breaker,
                    backend_name=self.backend_name,
                    agent_id=self.agent_id,
                )
                if not filtered_servers:
                    logger.warning(
                        "All MCP servers blocked by circuit breaker during setup",
                    )
                    return
                if len(filtered_servers) < len(mcp_tools_servers):
                    logger.info(
                        f"Circuit breaker filtered {len(mcp_tools_servers) - len(filtered_servers)} servers during setup",
                    )
                servers_to_use = filtered_servers
            else:
                servers_to_use = mcp_tools_servers

            # Setup MCP client using consolidated utilities
            self._mcp_client = await MCPResourceManager.setup_mcp_client(
                servers=servers_to_use,
                allowed_tools=self.allowed_tools,
                exclude_tools=self.exclude_tools,
                circuit_breaker=self._mcp_tools_circuit_breaker,
                timeout_seconds=30,
                backend_name=self.backend_name,
                agent_id=self.agent_id,
            )

            # Guard after client setup
            if not self._mcp_client:
                self._mcp_initialized = False
                logger.warning(
                    "MCP client setup failed, falling back to no-MCP streaming",
                )
                return

            # Convert tools to functions using consolidated utility
            self._mcp_functions.update(
                MCPResourceManager.convert_tools_to_functions(
                    self._mcp_client,
                    backend_name=self.backend_name,
                    agent_id=self.agent_id,
                    hook_manager=getattr(self, "function_hook_manager", None),
                ),
            )
            self._mcp_initialized = True
            logger.info(
                f"Successfully initialized MCP mcp_tools sessions with {len(self._mcp_functions)} tools converted to functions",
            )

            # Record success for circuit breaker
            if self._circuit_breakers_enabled and self._mcp_tools_circuit_breaker and self._mcp_client:
                try:
                    connected_server_names = self._mcp_client.get_server_names() if hasattr(self._mcp_client, "get_server_names") else []
                    if connected_server_names:
                        connected_server_configs = [server for server in servers_to_use if server.get("name") in connected_server_names]
                        if connected_server_configs:
                            await MCPCircuitBreakerManager.record_success(
                                connected_server_configs,
                                self._mcp_tools_circuit_breaker,
                                backend_name=self.backend_name,
                                agent_id=self.agent_id,
                            )
                except Exception as cb_error:
                    logger.warning(
                        f"Failed to record circuit breaker success: {cb_error}",
                    )

        except Exception as e:
            # Record failure for circuit breaker
            if self._circuit_breakers_enabled and self._mcp_tools_circuit_breaker:
                try:
                    await MCPCircuitBreakerManager.record_failure(
                        servers_to_use if "servers_to_use" in locals() else mcp_tools_servers if "mcp_tools_servers" in locals() else [],
                        self._mcp_tools_circuit_breaker,
                        str(e),
                        backend_name=self.backend_name,
                        agent_id=self.agent_id,
                    )
                except Exception as cb_error:
                    logger.warning(
                        f"Failed to record circuit breaker failure: {cb_error}",
                    )

            logger.warning(f"Failed to setup MCP sessions: {e}")
            self._mcp_client = None
            self._mcp_initialized = False
            self._mcp_functions = {}

    def _track_mcp_function_names(self, tools: List[Dict[str, Any]]) -> None:
        """Track MCP function names for fallback filtering."""
        for tool in tools:
            if tool.get("type") == "function":
                name = tool.get("function", {}).get("name")
                if name:
                    self._mcp_function_names.add(name)

    async def _handle_mcp_error_and_fallback(
        self,
        error: Exception,
        api_params: Dict[str, Any],
        provider_tools: List[Dict[str, Any]],
        stream_func: Callable[[Dict[str, Any]], AsyncGenerator[StreamChunk, None]],
    ) -> AsyncGenerator[StreamChunk, None]:
        """Handle MCP errors with specific messaging and fallback to non-MCP tools."""

        async with self._stats_lock:
            self._mcp_tool_failures += 1
            call_index_snapshot = self._mcp_tool_calls_count

        log_type, user_message, _ = MCPErrorHandler.get_error_details(error)

        logger.warning(
            f"MCP tool call #{call_index_snapshot} failed - {log_type}: {error}",
        )

        # Yield detailed MCP error status as StreamChunk (similar to gemini.py)
        yield StreamChunk(
            type="mcp_status",
            status="mcp_tools_failed",
            content=f"MCP tool call failed (call #{call_index_snapshot}): {user_message}",
            source="mcp_error",
        )

        # Yield user-friendly error message
        yield StreamChunk(
            type="content",
            content=f"\n⚠️  {user_message} ({error}); continuing without MCP tools\n",
        )

        # Build non-MCP configuration and stream fallback
        fallback_params = dict(api_params)

        # Remove any MCP tools from the tools list
        if "tools" in fallback_params:
            non_mcp_tools = []
            for tool in fallback_params.get("tools", []):
                if tool.get("type") == "function":
                    name = tool.get("function", {}).get("name")
                    if name and name in self._mcp_function_names:
                        continue
                non_mcp_tools.append(tool)
            fallback_params["tools"] = non_mcp_tools

        # Add back provider tools if they were present
        if provider_tools:
            if "tools" not in fallback_params:
                fallback_params["tools"] = []
            fallback_params["tools"].extend(provider_tools)

        async for chunk in stream_func(fallback_params):
            yield chunk

    async def _execute_mcp_function_with_retry(
        self,
        function_name: str,
        arguments_json: str,
        max_retries: int = 3,
    ) -> Tuple[str, Any]:
        """Execute MCP function with exponential backoff retry logic."""
        import json

        # Convert JSON string to dict for shared utility
        try:
            args = json.loads(arguments_json)
        except (json.JSONDecodeError, ValueError) as e:
            error_str = f"Error: Invalid JSON arguments: {e}"
            return error_str, {"error": error_str}

        # Stats callback for tracking
        async def stats_callback(action: str) -> int:
            async with self._stats_lock:
                if action == "increment_calls":
                    self._mcp_tool_calls_count += 1
                    return self._mcp_tool_calls_count
                elif action == "increment_failures":
                    self._mcp_tool_failures += 1
                    return self._mcp_tool_failures
            return 0

        # Circuit breaker callback
        async def circuit_breaker_callback(event: str, error_msg: str) -> None:
            # For individual function calls, we don't have server configurations readily available
            # The circuit breaker manager should handle this gracefully with empty server list
            if event == "failure":
                await MCPCircuitBreakerManager.record_event(
                    [],
                    self._mcp_tools_circuit_breaker,
                    "failure",
                    error_msg,
                    backend_name=self.backend_name,
                    agent_id=self.agent_id,
                )
            else:
                await MCPCircuitBreakerManager.record_event(
                    [],
                    self._mcp_tools_circuit_breaker,
                    "success",
                    backend_name=self.backend_name,
                    agent_id=self.agent_id,
                )

        result = await MCPExecutionManager.execute_function_with_retry(
            function_name=function_name,
            args=args,
            functions=self._mcp_functions,
            max_retries=max_retries,
            stats_callback=stats_callback,
            circuit_breaker_callback=circuit_breaker_callback,
            logger_instance=logger,
        )

        # Convert result to string for Chat Completions compatibility and return tuple
        if isinstance(result, dict) and "error" in result:
            return f"Error: {result['error']}", result
        return str(result), result

    async def _build_chat_completions_api_params(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        all_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build Chat Completions API parameters with MCP integration."""
        # Build base API parameters
        api_params = self._build_base_api_params(messages, all_params)

        # Prepare and add tools
        api_tools = self._prepare_tools_for_api(tools, all_params)
        if api_tools:
            api_params["tools"] = api_tools

        # Add MCP tools (stdio + streamable-http) as functions
        if self._mcp_functions:
            mcp_tools = self.mcp_tool_formatter.to_chat_completions_format(
                self._mcp_functions,
            )
            if mcp_tools:
                # Track MCP function names for fallback filtering
                self._track_mcp_function_names(mcp_tools)
                if "tools" not in api_params:
                    api_params["tools"] = []
                api_params["tools"].extend(mcp_tools)
                logger.info(
                    f"Added {len(mcp_tools)} MCP tools (stdio + streamable-http) to Chat Completions API",
                )

        return api_params

    def _get_provider_tools(self, all_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Return provider tools (web_search, code_interpreter) in Chat Completions format.

        Ensures consistent definitions across all code paths.
        """
        provider_tools: List[Dict[str, Any]] = []
        enable_web_search = all_params.get("enable_web_search", False)
        enable_code_interpreter = all_params.get("enable_code_interpreter", False)

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
                                },
                            },
                            "required": ["query"],
                        },
                    },
                },
            )

        if enable_code_interpreter:
            provider_tools.append(
                {"type": "code_interpreter", "container": {"type": "auto"}},
            )

        return provider_tools

    def _convert_messages_for_mcp_chat_completions(
        self,
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Convert messages for MCP Chat Completions format if needed."""
        # For Chat Completions, messages are already in the correct format
        # Just ensure tool result messages use the correct format
        converted_messages = []

        for message in messages:
            if message.get("type") == "function_call_output":
                # Convert Response API format to Chat Completions format
                converted_message = {
                    "role": "tool",
                    "tool_call_id": message.get("call_id"),
                    "content": message.get("output", ""),
                }
                converted_messages.append(converted_message)
            else:
                # Pass through other messages as-is
                converted_messages.append(message.copy())

        return converted_messages

    async def _stream_mcp_recursive(
        self,
        current_messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        client,
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Recursively stream MCP responses, executing function calls as needed."""

        # Build API params for this iteration
        all_params = {**self.config, **kwargs}
        api_params = await self._build_chat_completions_api_params(
            current_messages,
            tools,
            all_params,
        )

        # Add provider tools (web search, code interpreter) if enabled
        provider_tools = self._get_provider_tools(all_params)

        if provider_tools:
            if "tools" not in api_params:
                api_params["tools"] = []
            api_params["tools"].extend(provider_tools)

        # Start streaming
        stream = await client.chat.completions.create(**api_params)

        # Track function calls in this iteration
        captured_function_calls = []
        current_tool_calls = {}
        response_completed = False
        content = ""

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
                                if hasattr(tool_call_delta, "function") and tool_call_delta.function:
                                    if getattr(tool_call_delta.function, "name", None):
                                        current_tool_calls[index]["function"]["name"] = tool_call_delta.function.name

                                    # Accumulate arguments (as string chunks)
                                    if getattr(
                                        tool_call_delta.function,
                                        "arguments",
                                        None,
                                    ):
                                        current_tool_calls[index]["function"]["arguments"] += tool_call_delta.function.arguments

                    # Handle finish reason
                    if getattr(choice, "finish_reason", None):
                        if choice.finish_reason == "tool_calls" and current_tool_calls:
                            final_tool_calls = []

                            for index in sorted(current_tool_calls.keys()):
                                call = current_tool_calls[index]
                                function_name = call["function"]["name"]
                                arguments_str = call["function"]["arguments"]

                                # Providers expect arguments to be a JSON string
                                arguments_str_sanitized = arguments_str if arguments_str.strip() else "{}"

                                final_tool_calls.append(
                                    {
                                        "id": call["id"],
                                        "type": "function",
                                        "function": {
                                            "name": function_name,
                                            "arguments": arguments_str_sanitized,
                                        },
                                    },
                                )

                            # Convert to captured format for processing (ensure arguments is a JSON string)
                            for tool_call in final_tool_calls:
                                args_value = tool_call["function"]["arguments"]
                                if not isinstance(args_value, str):
                                    args_value = self.message_formatter._serialize_tool_arguments(
                                        args_value,
                                    )
                                captured_function_calls.append(
                                    {
                                        "call_id": tool_call["id"],
                                        "name": tool_call["function"]["name"],
                                        "arguments": args_value,
                                    },
                                )

                            yield StreamChunk(
                                type="tool_calls",
                                tool_calls=final_tool_calls,
                            )

                            response_completed = True
                            break  # Exit chunk loop to execute functions

                        elif choice.finish_reason in ["stop", "length"]:
                            response_completed = True
                            # No function calls, we're done (base case)
                            yield StreamChunk(type="done")
                            return

            except Exception as chunk_error:
                yield StreamChunk(
                    type="error",
                    error=f"Chunk processing error: {chunk_error}",
                )
                continue

        # Execute any captured function calls
        if captured_function_calls and response_completed:
            # Check if any of the function calls are NOT MCP functions
            non_mcp_functions = [call for call in captured_function_calls if call["name"] not in self._mcp_functions]

            if non_mcp_functions:
                logger.info(
                    f"Non-MCP function calls detected (will be ignored in MCP execution): {[call['name'] for call in non_mcp_functions]}",
                )

            # Check circuit breaker status before executing MCP functions
            if self._circuit_breakers_enabled and self._mcp_tools_circuit_breaker:
                # Get current mcp_tools servers using utility functions
                normalized_servers = MCPSetupManager.normalize_mcp_servers(
                    self.mcp_servers,
                )
                mcp_tools_servers = MCPSetupManager.separate_stdio_streamable_servers(
                    normalized_servers,
                )

                filtered_servers = MCPCircuitBreakerManager.apply_circuit_breaker_filtering(
                    mcp_tools_servers,
                    self._mcp_tools_circuit_breaker,
                )
                if not filtered_servers:
                    logger.warning("All MCP servers blocked by circuit breaker")
                    yield StreamChunk(
                        type="mcp_status",
                        status="mcp_blocked",
                        content="⚠️ [MCP] All servers blocked by circuit breaker",
                        source="circuit_breaker",
                    )
                    yield StreamChunk(type="done")
                    return

            # Execute only MCP function calls
            mcp_functions_executed = False
            updated_messages = current_messages.copy()

            # Create single assistant message with all tool calls
            if captured_function_calls:
                # First add the assistant message with ALL tool_calls
                all_tool_calls = []
                for call in captured_function_calls:
                    if call["name"] in self._mcp_functions:
                        all_tool_calls.append(
                            {
                                "id": call["call_id"],
                                "type": "function",
                                "function": {
                                    "name": call["name"],
                                    "arguments": self.message_formatter._serialize_tool_arguments(
                                        call["arguments"],
                                    ),
                                },
                            },
                        )

                # Only add assistant message if we have tool calls to execute
                if all_tool_calls:
                    assistant_message = {
                        "role": "assistant",
                        "content": content.strip() if content.strip() else None,
                        "tool_calls": all_tool_calls,
                    }
                    updated_messages.append(assistant_message)

            # Execute functions and collect results
            tool_results = []
            # Ensure every captured function call gets a result to prevent OpenAI hanging
            processed_call_ids = set()

            for call in captured_function_calls:
                function_name = call["name"]
                if function_name in self._mcp_functions:
                    yield StreamChunk(
                        type="mcp_status",
                        status="mcp_tool_called",
                        content=f"🔧 [MCP Tool] Calling {function_name}...",
                        source=f"mcp_{function_name}",
                    )

                    # Yield detailed MCP status as StreamChunk (similar to gemini.py)
                    tools_info = f" ({len(self._mcp_functions)} tools available)" if self._mcp_functions else ""
                    yield StreamChunk(
                        type="mcp_status",
                        status="mcp_tools_initiated",
                        content=f"MCP tool call initiated (call #{self._mcp_tool_calls_count}){tools_info}: {function_name}",
                        source=f"mcp_{function_name}",
                    )

                    try:
                        # Execute MCP function with retry and exponential backoff
                        (
                            result_str,
                            result_obj,
                        ) = await self._execute_mcp_function_with_retry(
                            function_name,
                            call["arguments"],
                        )

                        # Check if function failed after all retries
                        if isinstance(result_str, str) and result_str.startswith(
                            "Error:",
                        ):
                            # Log failure but still create tool response
                            logger.warning(
                                f"MCP function {function_name} failed after retries: {result_str}",
                            )
                            tool_results.append(
                                {
                                    "tool_call_id": call["call_id"],
                                    "content": result_str,
                                    "success": False,
                                },
                            )
                            processed_call_ids.add(call["call_id"])
                        else:
                            # Yield MCP success status as StreamChunk (similar to gemini.py)
                            yield StreamChunk(
                                type="mcp_status",
                                status="mcp_tools_success",
                                content=f"MCP tool call succeeded (call #{self._mcp_tool_calls_count})",
                                source=f"mcp_{function_name}",
                            )

                            tool_results.append(
                                {
                                    "tool_call_id": call["call_id"],
                                    "content": result_str,
                                    "success": True,
                                    "result_obj": result_obj,
                                },
                            )

                        processed_call_ids.add(call["call_id"])

                    except Exception as e:
                        # Only catch unexpected non-MCP system errors
                        logger.error(f"Unexpected error in MCP function execution: {e}")
                        error_msg = f"Error executing {function_name}: {str(e)}"
                        tool_results.append(
                            {
                                "tool_call_id": call["call_id"],
                                "content": error_msg,
                                "success": False,
                            },
                        )
                        processed_call_ids.add(call["call_id"])
                        continue

                    # Yield function_call status
                    yield StreamChunk(
                        type="mcp_status",
                        status="function_call",
                        content=f"Arguments for Calling {function_name}: {call['arguments']}",
                        source=f"mcp_{function_name}",
                    )

                    logger.info(
                        f"Executed MCP function {function_name} (stdio/streamable-http)",
                    )
                    mcp_functions_executed = True

            # Ensure all captured function calls have results to prevent OpenAI hanging
            for call in captured_function_calls:
                if call["call_id"] not in processed_call_ids:
                    logger.warning(f"Tool call {call['call_id']} for function {call['name']} was not processed - adding error result")
                    tool_results.append(
                        {
                            "tool_call_id": call["call_id"],
                            "content": f"Error: Tool call {call['call_id']} for function {call['name']} was not processed. This may indicate a validation or execution error.",
                            "success": False,
                        },
                    )

            # Add all tool response messages after the assistant message
            for result in tool_results:
                # Yield function_call_output status with preview
                result_text = str(result["content"])
                if result.get("success") and hasattr(result.get("result_obj"), "content") and result["result_obj"].content:
                    obj = result["result_obj"]
                    if isinstance(obj.content, list) and len(obj.content) > 0:
                        first_item = obj.content[0]
                        if hasattr(first_item, "text"):
                            result_text = first_item.text

                yield StreamChunk(
                    type="mcp_status",
                    status="function_call_output",
                    content=f"Results for Calling {function_name}: {result_text}",
                    source=f"mcp_{function_name}",
                )

                function_output_msg = {
                    "role": "tool",
                    "tool_call_id": result["tool_call_id"],
                    "content": result["content"],
                }
                updated_messages.append(function_output_msg)

                yield StreamChunk(
                    type="mcp_status",
                    status="mcp_tool_response",
                    content=f"✅ [MCP Tool] {function_name} completed",
                    source=f"mcp_{function_name}",
                )

            # Trim history after function executions to bound memory usage
            if mcp_functions_executed:
                updated_messages = MCPMessageManager.trim_message_history(
                    updated_messages,
                    self._max_mcp_message_history,
                )

                # Recursive call with updated messages
                async for chunk in self._stream_mcp_recursive(
                    updated_messages,
                    tools,
                    client,
                    **kwargs,
                ):
                    yield chunk
            else:
                # No MCP functions were executed, we're done
                yield StreamChunk(type="done")
                return

        elif response_completed:
            # Response completed with no function calls - we're done (base case)
            yield StreamChunk(
                type="mcp_status",
                status="mcp_session_complete",
                content="✅ [MCP] Session completed",
                source="mcp_session",
            )
            return

    async def handle_chat_completions_stream_with_logging(
        self,
        stream,
        enable_web_search: bool = False,
        agent_id: Optional[str] = None,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Handle standard Chat Completions API streaming format with logging."""

        content = ""
        current_tool_calls = {}
        search_sources_used = 0
        provider_name = self.get_provider_name()
        log_prefix = f"backend.{provider_name.lower().replace(' ', '_')}"

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
                            reasoning_active_key = "_reasoning_active"
                            if hasattr(self, reasoning_active_key):
                                if getattr(self, reasoning_active_key) is True:
                                    setattr(self, reasoning_active_key, False)
                                    log_stream_chunk(
                                        log_prefix,
                                        "reasoning_done",
                                        "",
                                        agent_id,
                                    )
                                    yield StreamChunk(type="reasoning_done", content="")
                            content_chunk = delta.content
                            content += content_chunk
                            log_backend_agent_message(
                                agent_id or "default",
                                "RECV",
                                {"content": content_chunk},
                                backend_name=provider_name,
                            )
                            log_stream_chunk(
                                log_prefix,
                                "content",
                                content_chunk,
                                agent_id,
                            )
                            yield StreamChunk(type="content", content=content_chunk)

                        # Provider-specific reasoning/thinking streams (non-standard OpenAI fields)
                        if getattr(delta, "reasoning_content", None):
                            reasoning_active_key = "_reasoning_active"
                            setattr(self, reasoning_active_key, True)
                            thinking_delta = getattr(delta, "reasoning_content")
                            if thinking_delta:
                                log_stream_chunk(
                                    log_prefix,
                                    "reasoning",
                                    thinking_delta,
                                    agent_id,
                                )
                                yield StreamChunk(
                                    type="reasoning",
                                    content=thinking_delta,
                                    reasoning_delta=thinking_delta,
                                )

                        # Tool calls streaming (OpenAI-style)
                        if getattr(delta, "tool_calls", None):
                            # handle reasoning first
                            reasoning_chunk = self._handle_reasoning_transition(
                                log_prefix,
                                agent_id,
                            )
                            if reasoning_chunk:
                                yield reasoning_chunk

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
                                if hasattr(tool_call_delta, "function") and tool_call_delta.function:
                                    if getattr(tool_call_delta.function, "name", None):
                                        current_tool_calls[index]["function"]["name"] = tool_call_delta.function.name

                                    # Accumulate arguments (as string chunks)
                                    if getattr(
                                        tool_call_delta.function,
                                        "arguments",
                                        None,
                                    ):
                                        current_tool_calls[index]["function"]["arguments"] += tool_call_delta.function.arguments

                    # Handle finish reason
                    if getattr(choice, "finish_reason", None):
                        # handle reasoning first
                        reasoning_chunk = self._handle_reasoning_transition(
                            log_prefix,
                            agent_id,
                        )
                        if reasoning_chunk:
                            yield reasoning_chunk

                        if choice.finish_reason == "tool_calls" and current_tool_calls:
                            final_tool_calls = []

                            for index in sorted(current_tool_calls.keys()):
                                call = current_tool_calls[index]
                                function_name = call["function"]["name"]
                                arguments_str = call["function"]["arguments"]

                                # Providers expect arguments to be a JSON string
                                arguments_str_sanitized = arguments_str if arguments_str.strip() else "{}"

                                final_tool_calls.append(
                                    {
                                        "id": call["id"],
                                        "type": "function",
                                        "function": {
                                            "name": function_name,
                                            "arguments": arguments_str_sanitized,
                                        },
                                    },
                                )

                            log_stream_chunk(
                                log_prefix,
                                "tool_calls",
                                final_tool_calls,
                                agent_id,
                            )
                            yield StreamChunk(
                                type="tool_calls",
                                tool_calls=final_tool_calls,
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
                            log_stream_chunk(log_prefix, "done", None, agent_id)
                            yield StreamChunk(type="done")
                            return

                        elif choice.finish_reason in ["stop", "length"]:
                            if search_sources_used > 0:
                                search_complete_msg = f"\n✅ [Live Search Complete] Used {search_sources_used} sources\n"
                                log_stream_chunk(
                                    log_prefix,
                                    "content",
                                    search_complete_msg,
                                    agent_id,
                                )
                                yield StreamChunk(
                                    type="content",
                                    content=search_complete_msg,
                                )

                            # Handle citations if present
                            if hasattr(chunk, "citations") and chunk.citations:
                                if enable_web_search:
                                    citation_text = "\n📚 **Citations:**\n"
                                    for i, citation in enumerate(chunk.citations, 1):
                                        citation_text += f"{i}. {citation}\n"
                                    log_stream_chunk(
                                        log_prefix,
                                        "content",
                                        citation_text,
                                        agent_id,
                                    )
                                    yield StreamChunk(
                                        type="content",
                                        content=citation_text,
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
                            log_stream_chunk(log_prefix, "done", None, agent_id)
                            yield StreamChunk(type="done")
                            return

                # Optionally handle usage metadata
                if hasattr(chunk, "usage") and chunk.usage:
                    if getattr(chunk.usage, "num_sources_used", 0) > 0:
                        search_sources_used = chunk.usage.num_sources_used
                        if enable_web_search:
                            search_msg = f"\n📊 [Live Search] Using {search_sources_used} sources for real-time data\n"
                            log_stream_chunk(
                                log_prefix,
                                "content",
                                search_msg,
                                agent_id,
                            )
                            yield StreamChunk(
                                type="content",
                                content=search_msg,
                            )

            except Exception as chunk_error:
                error_msg = f"Chunk processing error: {chunk_error}"
                log_stream_chunk(log_prefix, "error", error_msg, agent_id)
                yield StreamChunk(type="error", error=error_msg)
                continue

        # Fallback in case stream ends without finish_reason
        log_stream_chunk(log_prefix, "done", None, agent_id)
        yield StreamChunk(type="done")

    async def _stream_without_mcp(
        self,
        client,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        all_params: Dict[str, Any],
        agent_id: Optional[str],
    ) -> AsyncGenerator[StreamChunk, None]:
        """Centralized non-MCP streaming using Chat Completions format."""
        api_params = await self._build_chat_completions_api_params(
            messages,
            tools,
            all_params,
        )
        log_backend_agent_message(
            agent_id or "default",
            "SEND",
            {
                "messages": api_params["messages"],
                "tools": len(api_params.get("tools", [])) if api_params.get("tools") else 0,
            },
            backend_name=self.get_provider_name(),
        )
        enable_web_search = all_params.get("enable_web_search", False)
        try:
            stream = await client.chat.completions.create(**api_params)
            async for chunk in self.handle_chat_completions_stream_with_logging(
                stream,
                enable_web_search,
                agent_id,
            ):
                yield chunk
        except Exception as e:
            logger.error(f"Streaming error (non-MCP): {e}")
            yield StreamChunk(type="error", error=str(e))

    async def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream response using OpenAI-compatible Chat Completions API."""
        # Extract agent_id for logging
        agent_id = kwargs.get("agent_id", None)

        log_backend_activity(
            self.get_provider_name(),
            "Starting stream_with_tools",
            {"num_messages": len(messages), "num_tools": len(tools) if tools else 0},
            agent_id=agent_id,
        )

        # Check if MCP is configured
        if self.mcp_servers:
            # Use MCP mode with async context manager
            client = None
            try:
                async with self:
                    # Merge constructor config with stream kwargs (stream kwargs take priority)
                    all_params = {**self.config, **kwargs}

                    client = self._create_openai_client(**kwargs)

                    # Determine if MCP processing is needed AFTER setup
                    use_mcp = bool(self._mcp_functions)

                    # If MCP is configured but unavailable, inform the user and fall back
                    if self.mcp_servers and not use_mcp:
                        yield StreamChunk(
                            type="mcp_status",
                            status="mcp_unavailable",
                            content="⚠️ [MCP] Setup failed or no tools available; continuing without MCP",
                            source="mcp_setup",
                        )

                    # Yield MCP connection status if MCP tools are available
                    if use_mcp and self.mcp_servers:
                        # Count only stdio/streamable-http servers for display
                        normalized_servers = MCPSetupManager.normalize_mcp_servers(
                            self.mcp_servers,
                        )
                        mcp_tools_servers = MCPSetupManager.separate_stdio_streamable_servers(
                            normalized_servers,
                        )
                        if mcp_tools_servers:
                            yield StreamChunk(
                                type="mcp_status",
                                status="mcp_connected",
                                content=f"✅ [MCP] Connected to {len(mcp_tools_servers)} servers",
                                source="mcp_setup",
                            )

                    if use_mcp:
                        # MCP MODE: Recursive function call detection and execution
                        logger.info("Using recursive MCP execution mode")

                        current_messages = MCPMessageManager.trim_message_history(
                            messages.copy(),
                            200,
                        )

                        # Yield MCP session initiation status
                        yield StreamChunk(
                            type="mcp_status",
                            status="mcp_tools_initiated",
                            content=f"🔧 [MCP] {len(self._mcp_functions)} tools available",
                            source="mcp_session",
                        )

                        # Start recursive MCP streaming
                        async for chunk in self._stream_mcp_recursive(
                            current_messages,
                            tools,
                            client,
                            **kwargs,
                        ):
                            yield chunk

                    else:
                        # NON-MCP MODE: Use unified helper
                        logger.info("Using no-MCP mode")
                        async for chunk in self._stream_without_mcp(
                            client,
                            messages,
                            tools,
                            all_params,
                            agent_id,
                        ):
                            yield chunk
                        return
            except Exception as e:
                # Handle exceptions that occur during MCP setup (__aenter__) or teardown
                # Provide a clear user-facing message and fall back to non-MCP streaming
                client = None
                try:
                    # Merge constructor config with stream kwargs (stream kwargs take priority)
                    all_params = {**self.config, **kwargs}

                    client = self._create_openai_client(**kwargs)

                    if isinstance(
                        e,
                        (MCPConnectionError, MCPTimeoutError, MCPServerError, MCPError),
                    ):
                        api_params = await self._build_chat_completions_api_params(
                            messages,
                            tools,
                            all_params,
                        )
                        provider_tools = self._get_provider_tools(all_params)

                        async def fallback_stream(params):
                            stream = await client.chat.completions.create(**params)
                            async for chunk in self.handle_chat_completions_stream_with_logging(
                                stream,
                                all_params.get("enable_web_search", False),
                                agent_id,
                            ):
                                yield chunk

                        async for chunk in self._handle_mcp_error_and_fallback(
                            e,
                            api_params,
                            provider_tools,
                            fallback_stream,
                        ):
                            yield chunk
                    else:
                        # Generic setup error: still notify if MCP was configured
                        if self.mcp_servers:
                            yield StreamChunk(
                                type="content",
                                content=f"⚠️ [MCP] Setup failed; continuing without MCP ({e})",
                            )

                        # Use existing non-MCP logic (fallback)
                        api_params = self._build_base_api_params(messages, all_params)

                        # Note: base_url is excluded here as it's handled during client creation
                        if "base_url" in api_params:
                            del api_params["base_url"]

                        # Prepare and add tools
                        api_tools = self._prepare_tools_for_api(tools, all_params)
                        if api_tools:
                            api_params["tools"] = api_tools

                        # Proceed with non-MCP streaming
                        stream = await client.chat.completions.create(**api_params)
                        async for chunk in self.handle_chat_completions_stream_with_logging(
                            stream,
                            all_params.get("enable_web_search", False),
                            agent_id,
                        ):
                            yield chunk
                except Exception as inner_e:
                    logger.error(
                        f"Streaming error during MCP setup fallback: {inner_e}",
                    )
                    yield StreamChunk(type="error", error=str(inner_e))
                finally:
                    # Ensure the underlying HTTP client is properly closed to avoid event loop issues
                    await self._cleanup_client(client)
        else:
            client = None
            try:
                all_params = {**self.config, **kwargs}
                client = self._create_openai_client(**kwargs)

                async for chunk in self._stream_without_mcp(
                    client,
                    messages,
                    tools,
                    all_params,
                    agent_id,
                ):
                    yield chunk
            except Exception as e:
                logger.error(f"Chat Completions API error: {str(e)}")
                yield StreamChunk(type="error", error=str(e))
            finally:
                await self._cleanup_client(client)

    def create_tool_result_message(
        self,
        tool_call: Dict[str, Any],
        result_content: str,
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

    def get_filesystem_support(self) -> FilesystemSupport:
        """Chat Completions supports filesystem through MCP servers."""
        return FilesystemSupport.MCP

    def get_supported_builtin_tools(self) -> List[str]:
        """Get list of builtin tools supported by this provider."""
        # Chat Completions API doesn't typically support builtin tools like web_search
        # But some providers might - this can be overridden in subclasses
        return []

    def _create_openai_client(self, **kwargs) -> AsyncOpenAI:
        """Create OpenAI client with consistent configuration."""
        import openai

        all_params = {**self.config, **kwargs}
        base_url = all_params.get("base_url", "https://api.openai.com/v1")
        return openai.AsyncOpenAI(api_key=self.api_key, base_url=base_url)

    async def _cleanup_client(self, client: Optional[AsyncOpenAI]) -> None:
        """Clean up OpenAI client resources."""
        try:
            if client is not None and hasattr(client, "aclose"):
                await client.aclose()
        except Exception:
            pass

    def _handle_reasoning_transition(
        self,
        log_prefix: str,
        agent_id: Optional[str],
    ) -> Optional[StreamChunk]:
        """Handle reasoning state transition and return StreamChunk if transition occurred."""
        reasoning_active_key = "_reasoning_active"
        if hasattr(self, reasoning_active_key):
            if getattr(self, reasoning_active_key) is True:
                setattr(self, reasoning_active_key, False)
                log_stream_chunk(log_prefix, "reasoning_done", "", agent_id)
                return StreamChunk(type="reasoning_done", content="")
        return None

    def _sanitize_messages_for_api(
        self,
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Ensure assistant tool_calls are valid per OpenAI Chat Completions rules:
        - For any assistant message with tool_calls, each tool_call.id must have a following
          tool message with matching tool_call_id in the subsequent history.
        - Remove any tool_calls lacking matching tool results; drop the whole assistant message
          if no valid tool_calls remain and it has no useful content.
        This prevents 400 wrong_api_format errors.
        """
        try:
            sanitized: List[Dict[str, Any]] = []
            len(messages)
            for i, msg in enumerate(messages):
                if msg.get("role") == "assistant" and "tool_calls" in msg:
                    tool_calls = msg.get("tool_calls") or []
                    valid_tool_calls = []
                    for tc in tool_calls:
                        tc_id = tc.get("id")
                        if not tc_id:
                            continue
                        # Does a later tool message reference this id?
                        has_match = any((m.get("role") == "tool" and m.get("tool_call_id") == tc_id) for m in messages[i + 1 :])
                        if has_match:
                            # Normalize arguments to string
                            fn = dict(tc.get("function", {}))
                            fn["arguments"] = self.message_formatter._serialize_tool_arguments(
                                fn.get("arguments"),
                            )
                            valid_tc = dict(tc)
                            valid_tc["function"] = fn
                            valid_tool_calls.append(valid_tc)
                    if valid_tool_calls:
                        new_msg = dict(msg)
                        new_msg["tool_calls"] = valid_tool_calls
                        sanitized.append(new_msg)
                    else:
                        # Keep as plain assistant if it has content; otherwise drop
                        if msg.get("content"):
                            new_msg = {k: v for k, v in msg.items() if k != "tool_calls"}
                            sanitized.append(new_msg)
                        else:
                            logger.warning(
                                "Dropping assistant tool_calls message without matching tool results",
                            )
                            continue
                else:
                    sanitized.append(msg)
            return sanitized
        except Exception as e:
            logger.warning(
                f"sanitize_messages_for_api failed: {e}; using original messages",
            )
            return messages

    def _build_base_api_params(
        self,
        messages: List[Dict[str, Any]],
        all_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build base API parameters for Chat Completions requests."""
        # Sanitize: remove trailing assistant tool_calls without corresponding tool results
        sanitized_messages = self._sanitize_messages_for_api(messages)
        # Convert messages to ensure tool call arguments are properly serialized
        converted_messages = self.message_formatter.to_chat_completions_format(
            sanitized_messages,
        )

        api_params = {
            "messages": converted_messages,
            "stream": True,
        }

        # Direct passthrough of all parameters except those handled separately
        for key, value in all_params.items():
            if key not in self.EXCLUDED_API_PARAMS and value is not None:
                api_params[key] = value

        return api_params

    def _prepare_tools_for_api(
        self,
        tools: List[Dict[str, Any]],
        all_params: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Prepare and combine framework tools with provider tools for API request."""
        api_tools = []

        # Add framework tools (convert to Chat Completions format)
        if tools:
            converted_tools = self.tool_formatter.to_chat_completions_format(tools)
            api_tools.extend(converted_tools)

        # Add provider tools (web search, code interpreter) if enabled
        provider_tools = self._get_provider_tools(all_params)
        if provider_tools:
            api_tools.extend(provider_tools)

        return api_tools

    async def cleanup_mcp(self) -> None:
        """Cleanup MCP connections."""
        if self._mcp_client:
            await MCPResourceManager.cleanup_mcp_client(
                self._mcp_client,
                backend_name=self.backend_name,
                agent_id=self.agent_id,
            )
            self._mcp_client = None
            self._mcp_initialized = False
            self._mcp_functions.clear()
            self._mcp_function_names.clear()

    async def __aenter__(self) -> "ChatCompletionsBackend":
        """Async context manager entry."""
        # Initialize MCP tools if configured
        await MCPResourceManager.setup_mcp_context_manager(
            self,
            backend_name=self.backend_name,
            agent_id=self.agent_id,
        )
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[object],
    ) -> None:
        """Async context manager exit with automatic resource cleanup."""
        await MCPResourceManager.cleanup_mcp_context_manager(
            self,
            logger_instance=logger,
            backend_name=self.backend_name,
            agent_id=self.agent_id,
        )
        # Don't suppress the original exception if one occurred
        return False
