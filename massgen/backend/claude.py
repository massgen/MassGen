"""
Claude backend implementation using Anthropic's Messages API.
Production-ready implementation with full multi-tool support.

✅ FEATURES IMPLEMENTED:
- ✅ Messages API integration with streaming support
- ✅ Multi-tool support (server-side + user-defined tools combined)
- ✅ Web search tool integration with pricing tracking
- ✅ Code execution tool integration with session management
- ✅ Tool message format conversion for MassGen compatibility
- ✅ Advanced streaming with tool parameter streaming
- ✅ Error handling and token usage tracking
- ✅ Production-ready pricing calculations (2025 rates)

Multi-Tool Capabilities:
- Can combine web search + code execution + user functions in single request
- No API limitations unlike other providers
- Parallel and sequential tool execution supported
- Perfect integration with MassGen StreamChunk pattern
"""
from __future__ import annotations

import os
import json
import asyncio
from typing import Dict, List, Any, AsyncGenerator, Optional, Callable
from .base import LLMBackend, StreamChunk, FilesystemSupport
from ..logger_config import (
    log_backend_activity,
    log_backend_agent_message,
    log_stream_chunk,
    logger,
)

# MCP integration imports
try:
    from ..mcp_tools import (
        MultiMCPClient,
        MCPError,
        MCPConnectionError,
        MCPCircuitBreaker,
        MCPConfigurationError,
        MCPValidationError,
        MCPTimeoutError,
        MCPServerError,
        MCPConfigValidator,
        Function,
        MCPErrorHandler,
        MCPSetupManager,
        MCPResourceManager,
        MCPExecutionManager,
        MCPRetryHandler,
        MCPMessageManager,
        MCPConfigHelper,
        MCPCircuitBreakerManager,
    )
except ImportError as e:  # MCP not installed or import failed
    logger.warning(f"MCP import failed: {e}")
    MultiMCPClient = None  # type: ignore[assignment]
    MCPError = ImportError  # type: ignore[assignment]
    MCPConnectionError = ImportError  # type: ignore[assignment]
    MCPConfigValidator = None  # type: ignore[assignment]
    MCPCircuitBreaker = None  # type: ignore[assignment]
    MCPConfigurationError = ImportError  # type: ignore[assignment]
    MCPValidationError = ImportError  # type: ignore[assignment]
    MCPTimeoutError = ImportError  # type: ignore[assignment]
    MCPServerError = ImportError  # type: ignore[assignment]
    Function = None  # type: ignore[assignment]
    MCPErrorHandler = None  # type: ignore[assignment]
    MCPSetupManager = None  # type: ignore[assignment]
    MCPResourceManager = None  # type: ignore[assignment]
    MCPExecutionManager = None  # type: ignore[assignment]
    MCPRetryHandler = None  # type: ignore[assignment]
    MCPMessageManager = None  # type: ignore[assignment]
    MCPConfigHelper = None  # type: ignore[assignment]
    MCPCircuitBreakerManager = None  # type: ignore[assignment]


class ClaudeBackend(LLMBackend):
    """Claude backend using Anthropic's Messages API with full multi-tool support."""

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(api_key, **kwargs)
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.search_count = 0  # Track web search usage for pricing
        self.code_session_hours = 0.0  # Track code execution usage

        # MCP integration (filesystem MCP server may have been injected by base class)
        self.mcp_servers = self.config.get("mcp_servers", [])
        self.allowed_tools = kwargs.pop("allowed_tools", None)
        self.exclude_tools = kwargs.pop("exclude_tools", None)
        self._mcp_client: Optional[MultiMCPClient] = None
        self._mcp_initialized = False

        # MCP tool execution monitoring
        self._mcp_tool_calls_count = 0
        self._mcp_tool_failures = 0

        # Circuit breaker for MCP tools (stdio + streamable-http)
        self._mcp_tools_circuit_breaker = None
        self._circuit_breakers_enabled = MCPCircuitBreaker is not None

        if self._circuit_breakers_enabled:
            mcp_tools_config = (
                MCPConfigHelper.build_circuit_breaker_config("mcp_tools")
                if MCPConfigHelper
                else None
            )
            if mcp_tools_config:
                self._mcp_tools_circuit_breaker = MCPCircuitBreaker(mcp_tools_config)  # type: ignore[misc]
                logger.info("Circuit breaker initialized for MCP tools")
            else:
                logger.warning(
                    "MCP tools circuit breaker config not available, disabling circuit breaker functionality"
                )
                self._circuit_breakers_enabled = False
        else:
            logger.warning(
                "Circuit breakers not available - proceeding without circuit breaker protection"
            )

        # Function registry for mcp_tools-based servers (stdio + streamable-http)
        self.functions: Dict[str, Function] = {}

        # Thread safety for counters
        self._stats_lock = asyncio.Lock()

        # Limit for message history growth within MCP execution loop
        self._max_mcp_message_history = kwargs.pop("max_mcp_message_history", 200)

        # Initialize backend name and agent ID for MCP operations
        self.backend_name = self.get_provider_name()
        self.agent_id = kwargs.get("agent_id", None)

    def convert_tools_to_claude_format(
        self, tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Convert tools to Claude's expected format.

        Input formats supported:
        - Response API format: {"type": "function", "name": ..., "description": ..., "parameters": ...}
        - Chat Completions format: {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}

        Claude format: {"type": "function", "name": ..., "description": ..., "input_schema": ...}
        """
        if not tools:
            return tools

        converted_tools = []
        for tool in tools:
            if tool.get("type") == "function":
                if "function" in tool:
                    # Chat Completions format -> Claude custom tool
                    func = tool["function"]
                    converted_tools.append(
                        {
                            "type": "custom",
                            "name": func["name"],
                            "description": func["description"],
                            "input_schema": func.get("parameters", {}),
                        }
                    )
                elif "name" in tool and "description" in tool:
                    # Response API format -> Claude custom tool
                    converted_tools.append(
                        {
                            "type": "custom",
                            "name": tool["name"],
                            "description": tool["description"],
                            "input_schema": tool.get("parameters", {}),
                        }
                    )
                else:
                    # Unknown format - keep as-is
                    converted_tools.append(tool)
            else:
                # Non-function tool (builtin tools) - keep as-is
                converted_tools.append(tool)

        return converted_tools

    def convert_messages_to_claude_format(
        self, messages: List[Dict[str, Any]]
    ) -> tuple:
        """Convert messages to Claude's expected format.

        Handle different tool message formats and extract system message:
        - Chat Completions tool message: {"role": "tool", "tool_call_id": "...", "content": "..."}
        - Response API tool message: {"type": "function_call_output", "call_id": "...", "output": "..."}
        - System messages: Extract and return separately for top-level system parameter

        Returns:
            tuple: (converted_messages, system_message)
        """
        converted_messages = []
        system_message = ""

        for message in messages:
            if message.get("role") == "system":
                # Extract system message for top-level parameter
                system_message = message.get("content", "")
            elif message.get("role") == "tool":
                # Chat Completions tool message -> Claude tool result
                converted_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": message.get("tool_call_id"),
                                "content": message.get("content", ""),
                            }
                        ],
                    }
                )
            elif message.get("type") == "function_call_output":
                # Response API tool message -> Claude tool result
                converted_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": message.get("call_id"),
                                "content": message.get("output", ""),
                            }
                        ],
                    }
                )
            elif message.get("role") == "assistant" and "tool_calls" in message:
                # Assistant message with tool calls - convert to Claude format
                content = []

                # Add text content if present
                if message.get("content"):
                    content.append({"type": "text", "text": message["content"]})

                # Convert tool calls to Claude tool use format
                for tool_call in message["tool_calls"]:
                    tool_name = self.extract_tool_name(tool_call)
                    tool_args = self.extract_tool_arguments(tool_call)
                    tool_id = self.extract_tool_call_id(tool_call)

                    content.append(
                        {
                            "type": "tool_use",
                            "id": tool_id,
                            "name": tool_name,
                            "input": tool_args,
                        }
                    )

                converted_messages.append({"role": "assistant", "content": content})
            elif message.get("role") in ["user", "assistant"]:
                # Keep user and assistant messages, skip system
                converted_message = dict(message)
                if isinstance(converted_message.get("content"), str):
                    # Claude expects content to be text for simple messages
                    pass
                converted_messages.append(converted_message)

        return converted_messages, system_message

    async def _handle_mcp_error_and_fallback(
        self,
        error: Exception,
        api_params: Dict[str, Any],
        provider_tools: List[Dict[str, Any]],
        stream_func: Callable[[Dict[str, Any]], AsyncGenerator[StreamChunk, None]],
    ) -> AsyncGenerator[StreamChunk, None]:
        """Handle MCP errors with user-friendly messaging and fallback to non-MCP tools."""

        async with self._stats_lock:
            self._mcp_tool_failures += 1
            call_index_snapshot = self._mcp_tool_calls_count

        if MCPErrorHandler:
            log_type, user_message, _ = MCPErrorHandler.get_error_details(error)  # type: ignore[assignment]
        else:
            log_type, user_message = "mcp_error", "[MCP] Error occurred"

        logger.warning(
            f"MCP tool call #{call_index_snapshot} failed - {log_type}: {error}"
        )

        yield StreamChunk(
            type="content",
            content=f"\n⚠️  {user_message} ({error}); continuing without MCP tools\n",
        )

        # Build non-MCP configuration and stream fallback
        fallback_params = dict(api_params)

        # Remove any MCP tools from the tools list
        if "tools" in fallback_params and self.functions:
            mcp_names = set(self.functions.keys())
            non_mcp_tools = []
            for tool in fallback_params["tools"]:
                name = tool.get("name")
                if name in mcp_names:
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
    ) -> List[str | Any]:
        """Execute MCP function with exponential backoff retry logic."""
        # Convert JSON string to dict for shared utility
        try:
            args = (
                json.loads(arguments_json)
                if isinstance(arguments_json, str)
                else arguments_json
            )
        except (json.JSONDecodeError, ValueError) as e:
            return [f"Error: Invalid JSON arguments: {e}"]

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
            if not (
                self._circuit_breakers_enabled
                and MCPCircuitBreakerManager
                and self._mcp_tools_circuit_breaker
            ):
                return

            # Get relevant servers for circuit breaker
            relevant_servers = []
            if self._mcp_client and hasattr(self._mcp_client, "get_server_names"):
                try:
                    connected_names = self._mcp_client.get_server_names()
                    if connected_names and hasattr(
                        self, "_cached_servers_for_circuit_breaker"
                    ):
                        relevant_servers = [
                            server
                            for server in self._cached_servers_for_circuit_breaker
                            if server.get("name") in connected_names
                        ]
                except Exception as e:
                    logger.warning(f"Failed to get connected server names: {e}")

            # Fallback to cached servers if no connected servers found
            if not relevant_servers and hasattr(
                self, "_cached_servers_for_circuit_breaker"
            ):
                relevant_servers = self._cached_servers_for_circuit_breaker

            # Record event only if we have servers
            if relevant_servers:
                if event == "failure":
                    await MCPCircuitBreakerManager.record_event(relevant_servers, self._mcp_tools_circuit_breaker, "failure", error_msg, backend_name=self.backend_name, agent_id=self.agent_id)  # type: ignore[arg-type]
                else:
                    await MCPCircuitBreakerManager.record_event(relevant_servers, self._mcp_tools_circuit_breaker, "success", backend_name=self.backend_name, agent_id=self.agent_id)  # type: ignore[arg-type]
            else:
                logger.debug(
                    f"Skipping circuit breaker event recording - no servers available for {event}"
                )

        if not MCPExecutionManager:
            return ["Error: MCPExecutionManager unavailable"]

        result = await MCPExecutionManager.execute_function_with_retry(  # type: ignore[union-attr]
            function_name=function_name,
            args=args,
            functions=self.functions,
            max_retries=max_retries,
            stats_callback=stats_callback,
            circuit_breaker_callback=circuit_breaker_callback,
            logger_instance=logger,
        )

        # Convert result to simple types for streaming
        if isinstance(result, dict) and "error" in result:
            return [f"Error: {result['error']}"]
        return [str(result), result]

    async def _setup_mcp_tools(self) -> None:
        """Initialize MCP client for mcp_tools-based servers (stdio + streamable-http)."""
        if not self.mcp_servers or self._mcp_initialized or not MCPSetupManager:
            return

        try:
            # Normalize and separate MCP servers by transport type
            normalized_servers = MCPSetupManager.normalize_mcp_servers(  # type: ignore[union-attr]
                self.mcp_servers, backend_name=self.backend_name, agent_id=self.agent_id
            )
            mcp_tools_servers = MCPSetupManager.separate_stdio_streamable_servers(  # type: ignore[union-attr]
                normalized_servers,
                backend_name=self.backend_name,
                agent_id=self.agent_id,
            )

            if not mcp_tools_servers:
                logger.info("No stdio/streamable-http servers configured")
                return

            # Apply circuit breaker filtering before connection attempts
            if (
                self._circuit_breakers_enabled
                and self._mcp_tools_circuit_breaker
                and MCPCircuitBreakerManager
            ):
                filtered_servers = MCPCircuitBreakerManager.apply_circuit_breaker_filtering(  # type: ignore[union-attr]
                    mcp_tools_servers,
                    self._mcp_tools_circuit_breaker,
                    backend_name=self.backend_name,
                    agent_id=self.agent_id,
                )
                if not filtered_servers:
                    logger.warning(
                        "All MCP servers blocked by circuit breaker during setup"
                    )
                    return
                if len(filtered_servers) < len(mcp_tools_servers):
                    logger.info(
                        f"Circuit breaker filtered {len(mcp_tools_servers) - len(filtered_servers)} servers during setup"
                    )
                servers_to_use = filtered_servers
            else:
                servers_to_use = mcp_tools_servers

            if not MCPResourceManager:
                logger.warning("MCPResourceManager not available")
                return

            # Setup MCP client
            self._mcp_client = await MCPResourceManager.setup_mcp_client(  # type: ignore[union-attr]
                servers=servers_to_use,
                allowed_tools=self.allowed_tools,
                exclude_tools=self.exclude_tools,
                circuit_breaker=self._mcp_tools_circuit_breaker,
                timeout_seconds=30,
                backend_name=self.backend_name,
                agent_id=self.agent_id,
            )

            # Cache servers for circuit breaker callback
            self._cached_servers_for_circuit_breaker = servers_to_use

            if not self._mcp_client:
                self._mcp_initialized = False
                logger.warning(
                    "MCP client setup failed, falling back to no-MCP streaming"
                )
                return

            # Convert tools to functions
            self.functions.update(
                MCPResourceManager.convert_tools_to_functions(  # type: ignore[union-attr]
                    self._mcp_client,
                    backend_name=self.backend_name,
                    agent_id=self.agent_id,
                )
            )
            self._mcp_initialized = True
            logger.info(
                f"Successfully initialized MCP sessions with {len(self.functions)} tools converted to functions"
            )

            # Record success for circuit breaker
            if (
                self._circuit_breakers_enabled
                and self._mcp_tools_circuit_breaker
                and self._mcp_client
                and MCPCircuitBreakerManager
            ):
                try:
                    connected_server_names = (
                        self._mcp_client.get_server_names()
                        if hasattr(self._mcp_client, "get_server_names")
                        else []
                    )
                    if connected_server_names:
                        connected_server_configs = [
                            server
                            for server in servers_to_use
                            if server.get("name") in connected_server_names
                        ]
                        if connected_server_configs:
                            await MCPCircuitBreakerManager.record_success(  # type: ignore[union-attr]
                                connected_server_configs,
                                self._mcp_tools_circuit_breaker,
                                backend_name=self.backend_name,
                                agent_id=self.agent_id,
                            )
                except Exception as cb_error:
                    logger.warning(
                        f"Failed to record circuit breaker success: {cb_error}"
                    )

        except Exception as e:
            # Record failure for circuit breaker
            if (
                self._circuit_breakers_enabled
                and self._mcp_tools_circuit_breaker
                and MCPCircuitBreakerManager
            ):
                try:
                    await MCPCircuitBreakerManager.record_failure(  # type: ignore[union-attr]
                        servers_to_use
                        if "servers_to_use" in locals()
                        else mcp_tools_servers
                        if "mcp_tools_servers" in locals()
                        else [],
                        self._mcp_tools_circuit_breaker,
                        str(e),
                        backend_name=self.backend_name,
                        agent_id=self.agent_id,
                    )
                except Exception as cb_error:
                    logger.warning(
                        f"Failed to record circuit breaker failure: {cb_error}"
                    )

            logger.warning(f"Failed to setup MCP sessions: {e}")
            self._mcp_client = None
            self._mcp_initialized = False
            self.functions = {}

    def _convert_mcp_tools_to_claude_format(self) -> List[Dict[str, Any]]:
        """Convert MCP tools to Claude's custom tool format."""
        if not self.functions:
            return []
        converted: List[Dict[str, Any]] = []
        for function in self.functions.values():
            try:

                converted.append(function.to_claude_format())
            except Exception as e:
                logger.warning(f"Failed to convert MCP function to Claude format: {e}")
                continue
        logger.debug(f"Converted {len(converted)} MCP tools to Claude format")
        return converted

    async def _build_claude_api_params(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        all_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build Anthropic Messages API parameters with MCP integration."""
        # Convert messages to Claude format and extract system message
        converted_messages, system_message = self.convert_messages_to_claude_format(
            messages
        )

        # Combine tools
        combined_tools: List[Dict[str, Any]] = []

        # Server-side tools
        enable_web_search = all_params.get("enable_web_search", False)
        enable_code_execution = all_params.get("enable_code_execution", False)
        if enable_web_search:
            combined_tools.append({"type": "web_search_20250305", "name": "web_search"})
        if enable_code_execution:
            combined_tools.append(
                {"type": "code_execution_20250522", "name": "code_execution"}
            )

        # User-defined tools
        if tools:
            converted_tools = self.convert_tools_to_claude_format(tools)
            combined_tools.extend(converted_tools)

        # MCP tools
        if self.functions:
            mcp_tools = self._convert_mcp_tools_to_claude_format()
            combined_tools.extend(mcp_tools)

        # Build API parameters
        api_params: Dict[str, Any] = {"messages": converted_messages, "stream": True}

        if system_message:
            api_params["system"] = system_message
        if combined_tools:
            api_params["tools"] = combined_tools

        # Direct passthrough of all parameters except those handled separately
        excluded_params = {
            "enable_web_search",
            "enable_code_execution",
            "agent_id",
            "session_id",
            "cwd",
            "agent_temporary_workspace",
            "type",
            "mcp_servers",
            "allowed_tools",
            "exclude_tools",
        }
        for key, value in all_params.items():
            if key not in excluded_params and value is not None:
                api_params[key] = value

        # Claude API requires max_tokens - add default if not provided
        if "max_tokens" not in api_params:
            api_params["max_tokens"] = 4096

        if all_params.get("enable_code_execution"):
            api_params["betas"] = ["code-execution-2025-05-22"]

        return api_params

    async def _stream_mcp_recursive(
        self,
        current_messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        client,
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Recursively stream responses, executing MCP function calls when detected."""

        # Build API params for this iteration
        all_params = {**self.config, **kwargs}
        api_params = await self._build_claude_api_params(
            current_messages, tools, all_params
        )

        agent_id = kwargs.get("agent_id", None)

        # Create stream (handle code execution beta)
        if "betas" in api_params:
            stream = await client.beta.messages.create(**api_params)
        else:
            stream = await client.messages.create(**api_params)

        content = ""
        current_tool_uses: Dict[str, Dict[str, Any]] = {}
        mcp_tool_calls: List[Dict[str, Any]] = []
        response_completed = False

        async for event in stream:
            try:
                if event.type == "message_start":
                    continue
                elif event.type == "content_block_start":
                    if hasattr(event, "content_block"):
                        if event.content_block.type == "tool_use":
                            tool_id = event.content_block.id
                            tool_name = event.content_block.name
                            current_tool_uses[tool_id] = {
                                "id": tool_id,
                                "name": tool_name,
                                "input": "",
                                "index": getattr(event, "index", None),
                            }
                        elif event.content_block.type == "server_tool_use":
                            tool_id = event.content_block.id
                            tool_name = event.content_block.name
                            current_tool_uses[tool_id] = {
                                "id": tool_id,
                                "name": tool_name,
                                "input": "",
                                "index": getattr(event, "index", None),
                                "server_side": True,
                            }
                            if tool_name == "code_execution":
                                yield StreamChunk(
                                    type="content",
                                    content=f"\n💻 [Code Execution] Starting...\n",
                                )
                            elif tool_name == "web_search":
                                yield StreamChunk(
                                    type="content",
                                    content=f"\n🔍 [Web Search] Starting search...\n",
                                )
                        elif event.content_block.type == "code_execution_tool_result":
                            result_block = event.content_block
                            result_parts = []
                            if hasattr(result_block, "stdout") and result_block.stdout:
                                result_parts.append(
                                    f"Output: {result_block.stdout.strip()}"
                                )
                            if hasattr(result_block, "stderr") and result_block.stderr:
                                result_parts.append(
                                    f"Error: {result_block.stderr.strip()}"
                                )
                            if (
                                hasattr(result_block, "return_code")
                                and result_block.return_code != 0
                            ):
                                result_parts.append(
                                    f"Exit code: {result_block.return_code}"
                                )
                            if result_parts:
                                result_text = f"\n💻 [Code Execution Result]\n{chr(10).join(result_parts)}\n"
                                yield StreamChunk(type="content", content=result_text)
                elif event.type == "content_block_delta":
                    if hasattr(event, "delta"):
                        if event.delta.type == "text_delta":
                            text_chunk = event.delta.text
                            content += text_chunk
                            log_backend_agent_message(
                                agent_id or "default",
                                "RECV",
                                {"content": text_chunk},
                                backend_name="claude",
                            )
                            log_stream_chunk(
                                "backend.claude", "content", text_chunk, agent_id
                            )
                            yield StreamChunk(type="content", content=text_chunk)
                        elif event.delta.type == "input_json_delta":
                            if hasattr(event, "index"):
                                for tool_id, tool_data in current_tool_uses.items():
                                    if tool_data.get("index") == event.index:
                                        partial_json = getattr(
                                            event.delta, "partial_json", ""
                                        )
                                        tool_data["input"] += partial_json
                                        break
                elif event.type == "content_block_stop":
                    if hasattr(event, "index"):
                        for tool_id, tool_data in current_tool_uses.items():
                            if tool_data.get("index") == event.index and tool_data.get(
                                "server_side"
                            ):
                                tool_name = tool_data.get("name", "")
                                tool_input = tool_data.get("input", "")
                                try:
                                    parsed_input = (
                                        json.loads(tool_input) if tool_input else {}
                                    )
                                except json.JSONDecodeError:
                                    parsed_input = {"raw_input": tool_input}
                                if tool_name == "code_execution":
                                    code = parsed_input.get("code", "")
                                    if code:
                                        yield StreamChunk(
                                            type="content", content=f"💻 [Code] {code}\n"
                                        )
                                    yield StreamChunk(
                                        type="content",
                                        content=f"✅ [Code Execution] Completed\n",
                                    )
                                elif tool_name == "web_search":
                                    query = parsed_input.get("query", "")
                                    if query:
                                        yield StreamChunk(
                                            type="content",
                                            content=f"🔍 [Query] '{query}'\n",
                                        )
                                    yield StreamChunk(
                                        type="content",
                                        content=f"✅ [Web Search] Completed\n",
                                    )
                                tool_data["processed"] = True
                                break
                elif event.type == "message_delta":
                    pass
                elif event.type == "message_stop":
                    # Identify MCP and non-MCP tool calls among current_tool_uses
                    non_mcp_tool_calls = []
                    if current_tool_uses:
                        for tool_use in current_tool_uses.values():
                            tool_name = tool_use.get("name", "")
                            is_server_side = tool_use.get("server_side", False)
                            if is_server_side:
                                continue
                            # Parse accumulated JSON input for tool
                            tool_input = tool_use.get("input", "")
                            try:
                                parsed_input = (
                                    json.loads(tool_input) if tool_input else {}
                                )
                            except json.JSONDecodeError:
                                parsed_input = {"raw_input": tool_input}

                            if tool_name in self.functions:
                                mcp_tool_calls.append(
                                    {
                                        "id": tool_use["id"],
                                        "type": "function",
                                        "function": {
                                            "name": tool_name,
                                            "arguments": parsed_input,
                                        },
                                    }
                                )
                            else:
                                non_mcp_tool_calls.append(
                                    {
                                        "id": tool_use["id"],
                                        "type": "function",
                                        "function": {
                                            "name": tool_name,
                                            "arguments": parsed_input,
                                        },
                                    }
                                )
                    # Emit non-MCP tool calls for the caller to execute
                    if non_mcp_tool_calls:
                        log_stream_chunk(
                            "backend.claude", "tool_calls", non_mcp_tool_calls, agent_id
                        )
                        yield StreamChunk(
                            type="tool_calls", tool_calls=non_mcp_tool_calls
                        )
                    response_completed = True
                    break
            except Exception as event_error:
                error_msg = f"Event processing error: {event_error}"
                log_stream_chunk("backend.claude", "error", error_msg, agent_id)
                yield StreamChunk(type="error", error=error_msg)
                continue

        # If we captured MCP tool calls, execute them and recurse
        if response_completed and mcp_tool_calls:
            # Circuit breaker pre-execution check
            if (
                self._circuit_breakers_enabled
                and self._mcp_tools_circuit_breaker
                and MCPSetupManager
                and MCPCircuitBreakerManager
            ):
                try:
                    normalized_servers = MCPSetupManager.normalize_mcp_servers(self.mcp_servers)  # type: ignore[union-attr]
                    mcp_tools_servers = MCPSetupManager.separate_stdio_streamable_servers(normalized_servers)  # type: ignore[union-attr]
                    filtered_servers = MCPCircuitBreakerManager.apply_circuit_breaker_filtering(  # type: ignore[union-attr]
                        mcp_tools_servers, self._mcp_tools_circuit_breaker
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
                except Exception as cb_check_error:
                    logger.warning(
                        f"Circuit breaker pre-execution check failed: {cb_check_error}"
                    )

            updated_messages = current_messages.copy()

            # Build assistant message with tool_use blocks for all MCP tool calls
            assistant_content = []
            if content:  # Add text content if any
                assistant_content.append({"type": "text", "text": content})

            for tool_call in mcp_tool_calls:
                tool_name = tool_call["function"]["name"]
                tool_args = tool_call["function"]["arguments"]
                tool_id = tool_call["id"]

                assistant_content.append(
                    {
                        "type": "tool_use",
                        "id": tool_id,
                        "name": tool_name,
                        "input": tool_args,
                    }
                )

            # Append the assistant message with tool uses
            updated_messages.append({"role": "assistant", "content": assistant_content})

            # Now execute the MCP tool calls and append results
            for tool_call in mcp_tool_calls:
                function_name = tool_call["function"]["name"]

                # Yield MCP tool call status
                yield StreamChunk(
                    type="mcp_status",
                    status="mcp_tool_called",
                    content=f"🔧 [MCP Tool] Calling {function_name}...",
                    source=f"mcp_{function_name}",
                )

                try:
                    # Execute MCP function
                    args_json = (
                        json.dumps(tool_call["function"]["arguments"])
                        if isinstance(
                            tool_call["function"].get("arguments"), (dict, list)
                        )
                        else tool_call["function"].get("arguments", "{}")
                    )
                    result_list = await self._execute_mcp_function_with_retry(
                        function_name, args_json
                    )
                    if not result_list or (
                        isinstance(result_list[0], str)
                        and result_list[0].startswith("Error:")
                    ):
                        logger.warning(
                            f"MCP function {function_name} failed after retries: {result_list[0] if result_list else 'unknown error'}"
                        )
                        continue
                    result_str = result_list[0]
                    result_obj = result_list[1] if len(result_list) > 1 else None
                except Exception as e:
                    logger.error(f"Unexpected error in MCP function execution: {e}")
                    continue

                # Build tool result message: { "role":"user", "content":[{ "type":"tool_result", "tool_use_id": tool_call["id"], "content": result_str }] }
                tool_result_msg = {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_call["id"],
                            "content": result_str,
                        }
                    ],
                }

                # Append to updated_messages
                updated_messages.append(tool_result_msg)

                yield StreamChunk(
                    type="mcp_status",
                    status="function_call",
                    content=f"Arguments for Calling {function_name}: {json.dumps(tool_call['function'].get('arguments', {}))}",
                    source=f"mcp_{function_name}",
                )

                # If result_obj might be structured, try to display summary
                result_display = None
                try:
                    if hasattr(result_obj, "content") and result_obj.content:
                        part = result_obj.content[0]
                        if hasattr(part, "text"):
                            result_display = str(part.text)
                except Exception:
                    result_display = None
                if result_display:
                    yield StreamChunk(
                        type="mcp_status",
                        status="function_call_output",
                        content=f"Results for Calling {function_name}: {result_display}",
                        source=f"mcp_{function_name}",
                    )
                else:
                    yield StreamChunk(
                        type="mcp_status",
                        status="function_call_output",
                        content=f"Results for Calling {function_name}: {result_str}",
                        source=f"mcp_{function_name}",
                    )

                logger.info(
                    f"Executed MCP function {function_name} (stdio/streamable-http)"
                )
                yield StreamChunk(
                    type="mcp_status",
                    status="mcp_tool_response",
                    content=f"✅ [MCP Tool] {function_name} completed",
                    source=f"mcp_{function_name}",
                )

            # Trim updated_messages via MCPMessageManager.trim_message_history()
            if MCPMessageManager:
                updated_messages = MCPMessageManager.trim_message_history(updated_messages, self._max_mcp_message_history)  # type: ignore[union-attr]

            # After processing all MCP calls, recurse: async for chunk in self._stream_mcp_recursive(updated_messages, tools, client, **kwargs): yield chunk
            async for chunk in self._stream_mcp_recursive(
                updated_messages, tools, client, **kwargs
            ):
                yield chunk
            return
        else:
            # No MCP function calls; finalize this turn
            # Ensure termination with a done chunk when no further tool calls
            complete_message = {
                "role": "assistant",
                "content": content.strip(),
            }
            log_stream_chunk(
                "backend.claude", "complete_message", complete_message, agent_id
            )
            yield StreamChunk(
                type="complete_message", complete_message=complete_message
            )
            yield StreamChunk(
                type="mcp_status",
                status="mcp_session_complete",
                content="✅ [MCP] Session completed",
                source="mcp_session",
            )
            yield StreamChunk(type="done")
            return

    async def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream response using Claude's Messages API with MCP integration and fallback."""
        agent_id = kwargs.get("agent_id", None)

        log_backend_activity(
            "claude",
            "Starting stream_with_tools",
            {"num_messages": len(messages), "num_tools": len(tools) if tools else 0},
            agent_id=agent_id,
        )

        # Use async context manager for proper MCP resource management
        try:
            async with self:
                import anthropic

                client = anthropic.AsyncAnthropic(api_key=self.api_key)

                try:
                    # Determine if MCP processing is needed
                    use_mcp = bool(self.functions)

                    # If MCP is configured but unavailable, inform the user and fall back
                    if self.mcp_servers and not use_mcp:
                        yield StreamChunk(
                            type="mcp_status",
                            status="mcp_unavailable",
                            content="⚠️ [MCP] Setup failed or no tools available; continuing without MCP",
                            source="mcp_setup",
                        )

                    # Yield MCP connection status if MCP tools are available
                    if use_mcp and self.mcp_servers and MCPSetupManager:
                        normalized_servers = MCPSetupManager.normalize_mcp_servers(self.mcp_servers)  # type: ignore[union-attr]
                        mcp_tools_servers = MCPSetupManager.separate_stdio_streamable_servers(normalized_servers)  # type: ignore[union-attr]
                        if mcp_tools_servers:
                            yield StreamChunk(
                                type="mcp_status",
                                status="mcp_connected",
                                content=f"✅ [MCP] Connected to {len(mcp_tools_servers)} servers",
                                source="mcp_setup",
                            )

                    if use_mcp:
                        # MCP MODE
                        logger.info("Using recursive MCP execution mode (Claude)")
                        current_messages = MCPMessageManager.trim_message_history(messages.copy(), self._max_mcp_message_history) if MCPMessageManager else messages.copy()  # type: ignore[union-attr]
                        yield StreamChunk(
                            type="mcp_status",
                            status="mcp_tools_initiated",
                            content=f"🔧 [MCP] {len(self.functions)} tools available",
                            source="mcp_session",
                        )
                        async for chunk in self._stream_mcp_recursive(
                            current_messages, tools, client, **kwargs
                        ):
                            yield chunk
                    else:
                        # NON-MCP MODE
                        all_params = {**self.config, **kwargs}
                        api_params = await self._build_claude_api_params(
                            messages, tools, all_params
                        )

                        # Helper to run a stream with given params (used also for fallback)
                        async def run_stream(params: Dict[str, Any]):
                            # Log messages being sent (limited to non-MCP for now)
                            converted_messages = params.get("messages", [])
                            combined_tools = params.get("tools", [])
                            log_backend_agent_message(
                                agent_id or "default",
                                "SEND",
                                {
                                    "messages": converted_messages,
                                    "tools": len(combined_tools)
                                    if combined_tools
                                    else 0,
                                },
                                backend_name="claude",
                            )
                            if "betas" in params:
                                st = await client.beta.messages.create(**params)
                            else:
                                st = await client.messages.create(**params)

                            content_local = ""
                            current_tool_uses_local: Dict[str, Dict[str, Any]] = {}

                            async for event in st:
                                try:
                                    if event.type == "message_start":
                                        continue
                                    elif event.type == "content_block_start":
                                        if hasattr(event, "content_block"):
                                            if event.content_block.type == "tool_use":
                                                tool_id = event.content_block.id
                                                tool_name = event.content_block.name
                                                current_tool_uses_local[tool_id] = {
                                                    "id": tool_id,
                                                    "name": tool_name,
                                                    "input": "",
                                                    "index": getattr(
                                                        event, "index", None
                                                    ),
                                                }
                                            elif (
                                                event.content_block.type
                                                == "server_tool_use"
                                            ):
                                                tool_id = event.content_block.id
                                                tool_name = event.content_block.name
                                                current_tool_uses_local[tool_id] = {
                                                    "id": tool_id,
                                                    "name": tool_name,
                                                    "input": "",
                                                    "index": getattr(
                                                        event, "index", None
                                                    ),
                                                    "server_side": True,
                                                }
                                                if tool_name == "code_execution":
                                                    yield StreamChunk(
                                                        type="content",
                                                        content=f"\n💻 [Code Execution] Starting...\n",
                                                    )
                                                elif tool_name == "web_search":
                                                    yield StreamChunk(
                                                        type="content",
                                                        content=f"\n🔍 [Web Search] Starting search...\n",
                                                    )
                                            elif (
                                                event.content_block.type
                                                == "code_execution_tool_result"
                                            ):
                                                result_block = event.content_block
                                                result_parts = []
                                                if (
                                                    hasattr(result_block, "stdout")
                                                    and result_block.stdout
                                                ):
                                                    result_parts.append(
                                                        f"Output: {result_block.stdout.strip()}"
                                                    )
                                                if (
                                                    hasattr(result_block, "stderr")
                                                    and result_block.stderr
                                                ):
                                                    result_parts.append(
                                                        f"Error: {result_block.stderr.strip()}"
                                                    )
                                                if (
                                                    hasattr(result_block, "return_code")
                                                    and result_block.return_code != 0
                                                ):
                                                    result_parts.append(
                                                        f"Exit code: {result_block.return_code}"
                                                    )
                                                if result_parts:
                                                    result_text = f"\n💻 [Code Execution Result]\n{chr(10).join(result_parts)}\n"
                                                    yield StreamChunk(
                                                        type="content",
                                                        content=result_text,
                                                    )
                                    elif event.type == "content_block_delta":
                                        if hasattr(event, "delta"):
                                            if event.delta.type == "text_delta":
                                                text_chunk = event.delta.text
                                                content_local += text_chunk
                                                log_backend_agent_message(
                                                    agent_id or "default",
                                                    "RECV",
                                                    {"content": text_chunk},
                                                    backend_name="claude",
                                                )
                                                log_stream_chunk(
                                                    "backend.claude",
                                                    "content",
                                                    text_chunk,
                                                    agent_id,
                                                )
                                                yield StreamChunk(
                                                    type="content", content=text_chunk
                                                )
                                            elif event.delta.type == "input_json_delta":
                                                if hasattr(event, "index"):
                                                    for (
                                                        tool_id,
                                                        tool_data,
                                                    ) in (
                                                        current_tool_uses_local.items()
                                                    ):
                                                        if (
                                                            tool_data.get("index")
                                                            == event.index
                                                        ):
                                                            partial_json = getattr(
                                                                event.delta,
                                                                "partial_json",
                                                                "",
                                                            )
                                                            tool_data[
                                                                "input"
                                                            ] += partial_json
                                                            break
                                    elif event.type == "content_block_stop":
                                        if hasattr(event, "index"):
                                            for (
                                                tool_id,
                                                tool_data,
                                            ) in current_tool_uses_local.items():
                                                if tool_data.get(
                                                    "index"
                                                ) == event.index and tool_data.get(
                                                    "server_side"
                                                ):
                                                    tool_name = tool_data.get(
                                                        "name", ""
                                                    )
                                                    tool_input = tool_data.get(
                                                        "input", ""
                                                    )
                                                    try:
                                                        parsed_input = (
                                                            json.loads(tool_input)
                                                            if tool_input
                                                            else {}
                                                        )
                                                    except json.JSONDecodeError:
                                                        parsed_input = {
                                                            "raw_input": tool_input
                                                        }
                                                    if tool_name == "code_execution":
                                                        code = parsed_input.get(
                                                            "code", ""
                                                        )
                                                        if code:
                                                            yield StreamChunk(
                                                                type="content",
                                                                content=f"💻 [Code] {code}\n",
                                                            )
                                                        yield StreamChunk(
                                                            type="content",
                                                            content=f"✅ [Code Execution] Completed\n",
                                                        )
                                                    elif tool_name == "web_search":
                                                        query = parsed_input.get(
                                                            "query", ""
                                                        )
                                                        if query:
                                                            yield StreamChunk(
                                                                type="content",
                                                                content=f"🔍 [Query] '{query}'\n",
                                                            )
                                                        yield StreamChunk(
                                                            type="content",
                                                            content=f"✅ [Web Search] Completed\n",
                                                        )
                                                    tool_data["processed"] = True
                                                    break
                                    elif event.type == "message_delta":
                                        pass
                                    elif event.type == "message_stop":
                                        # Build final response and yield tool_calls for user-defined non-MCP tools
                                        user_tool_calls = []
                                        for (
                                            tool_use
                                        ) in current_tool_uses_local.values():
                                            tool_name = tool_use.get("name", "")
                                            is_server_side = tool_use.get(
                                                "server_side", False
                                            )
                                            if (
                                                not is_server_side
                                                and tool_name
                                                not in ["web_search", "code_execution"]
                                            ):
                                                tool_input = tool_use.get("input", "")
                                                try:
                                                    parsed_input = (
                                                        json.loads(tool_input)
                                                        if tool_input
                                                        else {}
                                                    )
                                                except json.JSONDecodeError:
                                                    parsed_input = {
                                                        "raw_input": tool_input
                                                    }
                                                user_tool_calls.append(
                                                    {
                                                        "id": tool_use["id"],
                                                        "type": "function",
                                                        "function": {
                                                            "name": tool_name,
                                                            "arguments": parsed_input,
                                                        },
                                                    }
                                                )

                                        if user_tool_calls:
                                            log_stream_chunk(
                                                "backend.claude",
                                                "tool_calls",
                                                user_tool_calls,
                                                agent_id,
                                            )
                                            yield StreamChunk(
                                                type="tool_calls",
                                                tool_calls=user_tool_calls,
                                            )

                                        complete_message = {
                                            "role": "assistant",
                                            "content": content_local.strip(),
                                        }
                                        if user_tool_calls:
                                            complete_message[
                                                "tool_calls"
                                            ] = user_tool_calls
                                        log_stream_chunk(
                                            "backend.claude",
                                            "complete_message",
                                            complete_message,
                                            agent_id,
                                        )
                                        yield StreamChunk(
                                            type="complete_message",
                                            complete_message=complete_message,
                                        )

                                        # Track usage for pricing
                                        if all_params.get("enable_web_search", False):
                                            self.search_count += 1
                                        if all_params.get(
                                            "enable_code_execution", False
                                        ):
                                            self.code_session_hours += 0.083

                                        log_stream_chunk(
                                            "backend.claude", "done", None, agent_id
                                        )
                                        yield StreamChunk(type="done")
                                        return
                                except Exception as event_error:
                                    error_msg = f"Event processing error: {event_error}"
                                    log_stream_chunk(
                                        "backend.claude", "error", error_msg, agent_id
                                    )
                                    yield StreamChunk(type="error", error=error_msg)
                                    continue

                        # Run normal stream
                        async for chunk in run_stream(api_params):
                            yield chunk

                except Exception as e:
                    # Enhanced error handling for MCP-related errors during streaming
                    if isinstance(
                        e,
                        (MCPConnectionError, MCPTimeoutError, MCPServerError, MCPError),
                    ):
                        # Record failure for circuit breaker
                        if (
                            self._circuit_breakers_enabled
                            and self._mcp_tools_circuit_breaker
                            and MCPSetupManager
                            and MCPCircuitBreakerManager
                        ):
                            try:
                                normalized_servers = MCPSetupManager.normalize_mcp_servers(self.mcp_servers)  # type: ignore[union-attr]
                                mcp_tools_servers = MCPSetupManager.separate_stdio_streamable_servers(normalized_servers)  # type: ignore[union-attr]
                                await MCPCircuitBreakerManager.record_failure(mcp_tools_servers, self._mcp_tools_circuit_breaker, str(e), backend_name=self.backend_name, agent_id=agent_id)  # type: ignore[union-attr]
                            except Exception as cb_error:
                                logger.warning(
                                    f"Failed to record circuit breaker failure: {cb_error}"
                                )

                        # Build params and provider tools for fallback
                        all_params = {**self.config, **kwargs}
                        api_params = await self._build_claude_api_params(
                            messages, tools, all_params
                        )
                        provider_tools = []
                        if all_params.get("enable_web_search", False):
                            provider_tools.append(
                                {"type": "web_search_20250305", "name": "web_search"}
                            )
                        if all_params.get("enable_code_execution", False):
                            provider_tools.append(
                                {
                                    "type": "code_execution_20250522",
                                    "name": "code_execution",
                                }
                            )

                        async def fallback_stream(params: Dict[str, Any]):
                            # Reuse the non-MCP run_stream helper
                            async for chunk in run_stream(params):
                                yield chunk

                        async for chunk in self._handle_mcp_error_and_fallback(
                            e, api_params, provider_tools, fallback_stream
                        ):
                            yield chunk
                    else:
                        logger.error(f"Streaming error: {e}")
                        yield StreamChunk(type="error", error=str(e))
                finally:
                    try:
                        if hasattr(client, "aclose"):
                            await client.aclose()
                    except Exception:
                        pass
        except Exception as e:
            # Handle exceptions that occur during MCP setup (__aenter__) or teardown
            try:
                import anthropic

                client = anthropic.AsyncAnthropic(api_key=self.api_key)

                all_params = {**self.config, **kwargs}
                api_params = await self._build_claude_api_params(
                    messages, tools, all_params
                )

                provider_tools = []
                if all_params.get("enable_web_search", False):
                    provider_tools.append(
                        {"type": "web_search_20250305", "name": "web_search"}
                    )
                if all_params.get("enable_code_execution", False):
                    provider_tools.append(
                        {"type": "code_execution_20250522", "name": "code_execution"}
                    )

                async def fallback_stream(params: Dict[str, Any]):
                    # Minimal non-MCP streaming for fallback
                    if "betas" in params:
                        st = await client.beta.messages.create(**params)
                    else:
                        st = await client.messages.create(**params)
                    content_local = ""
                    async for event in st:
                        if (
                            event.type == "content_block_delta"
                            and hasattr(event, "delta")
                            and event.delta.type == "text_delta"
                        ):
                            text_chunk = event.delta.text
                            content_local += text_chunk
                            yield StreamChunk(type="content", content=text_chunk)
                        elif event.type == "message_stop":
                            yield StreamChunk(
                                type="complete_message",
                                complete_message={
                                    "role": "assistant",
                                    "content": content_local.strip(),
                                },
                            )
                            yield StreamChunk(type="done")
                            return

                if isinstance(
                    e, (MCPConnectionError, MCPTimeoutError, MCPServerError, MCPError)
                ):
                    async for chunk in self._handle_mcp_error_and_fallback(
                        e, api_params, provider_tools, fallback_stream
                    ):
                        yield chunk
                else:
                    if self.mcp_servers:
                        yield StreamChunk(
                            type="mcp_status",
                            status="mcp_unavailable",
                            content=f"⚠️ [MCP] Setup failed; continuing without MCP ({e})",
                            source="mcp_setup",
                        )
                    async for chunk in fallback_stream(api_params):
                        yield chunk
            except Exception as inner_e:
                logger.error(f"Streaming error during MCP setup fallback: {inner_e}")
                yield StreamChunk(type="error", error=str(inner_e))
            finally:
                try:
                    if "client" in locals() and hasattr(client, "aclose"):
                        await client.aclose()
                except Exception:
                    pass

    def get_provider_name(self) -> str:
        """Get the provider name."""
        return "Claude"

    async def cleanup_mcp(self) -> None:
        """Cleanup MCP connections."""
        if self._mcp_client and MCPResourceManager:
            await MCPResourceManager.cleanup_mcp_client(  # type: ignore[union-attr]
                self._mcp_client, backend_name=self.backend_name, agent_id=self.agent_id
            )
            self._mcp_client = None
            self._mcp_initialized = False
            self.functions.clear()

    async def __aenter__(self) -> "ClaudeBackend":
        """Async context manager entry."""
        if MCPResourceManager:
            await MCPResourceManager.setup_mcp_context_manager(  # type: ignore[union-attr]
                self, backend_name=self.backend_name, agent_id=self.agent_id
            )
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[object],
    ) -> None:
        """Async context manager exit with automatic resource cleanup."""
        if MCPResourceManager:
            await MCPResourceManager.cleanup_mcp_context_manager(  # type: ignore[union-attr]
                self,
                logger_instance=logger,
                backend_name=self.backend_name,
                agent_id=self.agent_id,
            )
        return False

    def get_supported_builtin_tools(self) -> List[str]:
        """Get list of builtin tools supported by Claude."""
        return ["web_search", "code_execution"]

    def extract_tool_name(self, tool_call: Dict[str, Any]) -> str:
        """Extract tool name from tool call (handles multiple formats)."""
        # Chat Completions format
        if "function" in tool_call:
            return tool_call.get("function", {}).get("name", "unknown")
        # Claude native format
        elif "name" in tool_call:
            return tool_call.get("name", "unknown")
        # Fallback
        return "unknown"

    def extract_tool_arguments(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """Extract tool arguments from tool call (handles multiple formats)."""
        # Chat Completions format
        if "function" in tool_call:
            args = tool_call.get("function", {}).get("arguments", {})
        # Claude native format
        elif "input" in tool_call:
            args = tool_call.get("input", {})
        else:
            args = {}

        # Ensure JSON parsing if needed
        if isinstance(args, str):
            try:
                return json.loads(args)
            except:
                return {}
        return args

    def extract_tool_call_id(self, tool_call: Dict[str, Any]) -> str:
        """Extract tool call ID from tool call."""
        return tool_call.get("id") or tool_call.get("call_id") or ""

    def create_tool_result_message(
        self, tool_call: Dict[str, Any], result_content: str
    ) -> Dict[str, Any]:
        """Create tool result message in Claude's expected format."""
        tool_call_id = self.extract_tool_call_id(tool_call)
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call_id,
                    "content": result_content,
                }
            ],
        }

    def get_filesystem_support(self) -> FilesystemSupport:
        """Claude supports filesystem through MCP servers."""
        return FilesystemSupport.MCP

    def extract_tool_result_content(self, tool_result_message: Dict[str, Any]) -> str:
        """Extract content from Claude tool result message."""
        content = tool_result_message.get("content", [])
        if isinstance(content, list) and content:
            for item in content:
                if isinstance(item, dict) and item.get("type") == "tool_result":
                    return item.get("content", "")
        return ""

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text (Claude uses ~4 chars per token)."""
        return len(text) // 4

    def calculate_cost(
        self, input_tokens: int, output_tokens: int, model: str
    ) -> float:
        """Calculate cost for Claude token usage (2025 pricing)."""
        model_lower = model.lower()

        if "claude-4" in model_lower:
            if "opus" in model_lower:
                # Claude 4 Opus
                input_cost = (input_tokens / 1_000_000) * 15.0
                output_cost = (output_tokens / 1_000_000) * 75.0
            else:
                # Claude 4 Sonnet
                input_cost = (input_tokens / 1_000_000) * 3.0
                output_cost = (output_tokens / 1_000_000) * 15.0
        elif "claude-3.7" in model_lower or "claude-3-7" in model_lower:
            # Claude 3.7 Sonnet
            input_cost = (input_tokens / 1_000_000) * 3.0
            output_cost = (output_tokens / 1_000_000) * 15.0
        elif "claude-3.5" in model_lower or "claude-3-5" in model_lower:
            if "haiku" in model_lower:
                # Claude 3.5 Haiku
                input_cost = (input_tokens / 1_000_000) * 1.0
                output_cost = (output_tokens / 1_000_000) * 5.0
            else:
                # Claude 3.5 Sonnet (legacy)
                input_cost = (input_tokens / 1_000_000) * 3.0
                output_cost = (output_tokens / 1_000_000) * 15.0
        else:
            # Default fallback (assume Claude 4 Sonnet pricing)
            input_cost = (input_tokens / 1_000_000) * 3.0
            output_cost = (output_tokens / 1_000_000) * 15.0

        # Add tool usage costs
        tool_costs = 0.0
        if self.search_count > 0:
            tool_costs += (self.search_count / 1000) * 10.0  # $10 per 1,000 searches

        if self.code_session_hours > 0:
            tool_costs += self.code_session_hours * 0.05  # $0.05 per session-hour

        return input_cost + output_cost + tool_costs

    def reset_tool_usage(self):
        """Reset tool usage tracking."""
        self.search_count = 0
        self.code_session_hours = 0.0
        super().reset_token_usage()
