"""
Response API backend implementation.
Standalone implementation optimized for the standard Response API format (originated by OpenAI).
"""
from __future__ import annotations
import os
import logging
import json
import asyncio
import random
import re
from typing import Dict, List, Any, AsyncGenerator, Optional, Callable, Literal
from .base import LLMBackend, StreamChunk, FilesystemSupport
from ..logger_config import log_backend_activity, log_backend_agent_message, log_stream_chunk

logger = logging.getLogger(__name__)

# MCP integration imports
try:
    from ..mcp_tools import (
        MultiMCPClient, MCPError, MCPConnectionError, MCPCircuitBreaker,
        MCPConfigurationError, MCPValidationError, MCPTimeoutError, MCPServerError,
        MCPConfigValidator, validate_url
    )
except ImportError as e:  # MCP not installed or import failed within mcp_tools
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
    validate_url = None


# Import common utilities
from ..mcp_tools import Function, MCPErrorHandler


class ResponseBackend(LLMBackend):
    """Backend using the standard Response API format."""

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(api_key, **kwargs)
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")

        #MCP integration (filesystem MCP server may have been injected by base class)
        self.mcp_servers = self.config.get("mcp_servers", [])
        self.allowed_tools = kwargs.pop("allowed_tools", None)
        self.exclude_tools = kwargs.pop("exclude_tools", None)
        self._mcp_client: Optional[MultiMCPClient] = None
        self._mcp_initialized = False

        # MCP tool execution monitoring
        self._mcp_tool_calls_count = 0
        self._mcp_tool_failures = 0

        # Circuit breakers for different transport types with explicit configuration
        self._mcp_tools_circuit_breaker = None  # For stdio + streamable-http
        self._http_circuit_breaker = None       # For OpenAI native http
        self._circuit_breakers_enabled = MCPCircuitBreaker is not None
        
        # Initialize circuit breakers if available
        if self._circuit_breakers_enabled:
            from ..mcp_tools import MCPConfigHelper

            # Use shared utility to build circuit breaker configurations
            mcp_tools_config = MCPConfigHelper.build_circuit_breaker_config("mcp_tools")
            http_config = MCPConfigHelper.build_circuit_breaker_config("http")

            if mcp_tools_config:
                self._mcp_tools_circuit_breaker = MCPCircuitBreaker(mcp_tools_config)
            else:
                logger.warning("MCP tools circuit breaker config not available")
                self._mcp_tools_circuit_breaker = None

            if http_config:
                self._http_circuit_breaker = MCPCircuitBreaker(http_config)
            else:
                logger.warning("HTTP circuit breaker config not available")
                self._http_circuit_breaker = None

            if not (mcp_tools_config or http_config):
                logger.warning("No circuit breaker configs available, disabling circuit breaker functionality")
                self._circuit_breakers_enabled = False
            else:
                logger.info("Circuit breakers initialized for MCP transport types")
        else:
            logger.warning("Circuit breakers not available - proceeding without circuit breaker protection")

        # Transport Types:
        # - "stdio" & "streamable-http": Use our mcp_tools folder (MultiMCPClient)
        # - "http": Use OpenAI's native MCP client
        self._mcp_tools_servers: List[Dict[str, Any]] = []    # stdio + streamable-http servers (use our MultiMCPClient)
        self._http_servers: List[Dict[str, Any]] = []         # Native OpenAI HTTP MCP servers

        # Function registry for mcp_tools-based servers (stdio + streamable-http)
        self.functions: Dict[str, Function] = {}

        # Thread safety for counters
        self._stats_lock = asyncio.Lock()

        # Limit for message history growth within MCP execution loop
        self._max_mcp_message_history = kwargs.pop("max_mcp_message_history", 200)

        # Initialize backend name and agent ID for MCP operations
        self.backend_name = self.get_provider_name()
        self.agent_id = kwargs.get('agent_id', None)

        # Separate MCP servers by transport type if any are configured
        if self.mcp_servers:
            self._separate_mcp_servers_by_transport_type()

    def _normalize_mcp_servers(self) -> List[Dict[str, Any]]:
        """Validate and normalize mcp_servers into a list of dicts."""
        from ..mcp_tools import MCPSetupManager
        return MCPSetupManager.normalize_mcp_servers(self.mcp_servers)

    def _separate_mcp_servers_by_transport_type(self) -> None:
        """
        Separate MCP servers into local execution and HTTP transport types.
        
        Transport Types:
        - "stdio" & "streamable-http": Local execution MCP servers (both use MultiMCPClient)
        - "http": Native OpenAI HTTP MCP servers (direct OpenAI ↔ External server)
        """
        validated_servers = self._normalize_mcp_servers()

        for server in validated_servers:
            transport_type = server.get("type")
            server_name = server.get("name", "unnamed")

            if not transport_type:
                logger.warning(
                    f"MCP server '{server_name}' missing required 'type' field. "
                    f"Supported types: 'stdio', 'http', 'streamable-http'. Skipping server."
                )
                continue

            if transport_type in ["stdio", "streamable-http"]:
                
                self._mcp_tools_servers.append(server)
            elif transport_type == "http":  # Native OpenAI HTTP MCP
                self._http_servers.append(server)
            else:
                logger.warning(
                    f"Unknown MCP transport type '{transport_type}' for server '{server_name}'. "
                    f"Supported types: 'stdio', 'http', 'streamable-http'. Skipping server."
                )

    @staticmethod
    def _get_mcp_error_info(error: Exception) -> tuple[str, str, str]:
        """Get standardized MCP error information."""
        return MCPErrorHandler.get_error_details(error)

    def _log_mcp_error(self, error: Exception, context: str) -> None:
        """Log MCP errors with specific error type messaging."""
        MCPErrorHandler.log_error(error, context)

    async def _handle_mcp_retry_error(
        self, error: Exception, retry_count: int, max_retries: int
    ) -> tuple[bool, AsyncGenerator[StreamChunk, None]]:
        """Handle MCP retry errors with specific messaging and fallback logic."""
        from ..mcp_tools import MCPRetryHandler
        return await MCPRetryHandler.handle_retry_error(error, retry_count, max_retries, StreamChunk)

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

        log_type, user_message, _ = self._get_mcp_error_info(error)

     
        logger.warning(
            f"MCP tool call #{call_index_snapshot} failed - {log_type}: {error}"
        )

        # Yield user-friendly error message
        yield StreamChunk(
            type="content",
            content=f"\n⚠️  {user_message} ({error}); continuing without MCP tools\n",
        )

        # Build non-MCP configuration and stream fallback
        fallback_params = dict(api_params)

        # Remove any HTTP MCP tools from the tools list
        if "tools" in fallback_params:
            non_mcp_tools = [
                tool
                for tool in fallback_params["tools"]
                if tool.get("type") != "mcp"
            ]
            fallback_params["tools"] = non_mcp_tools

        # Add back provider tools if they were present
        if provider_tools:
            if "tools" not in fallback_params:
                fallback_params["tools"] = []
            fallback_params["tools"].extend(provider_tools)

        async for chunk in stream_func(fallback_params):
            yield chunk


    async def _execute_mcp_function_with_retry(
        self, function_name: str, arguments_json: str, max_retries: int = 3
    ) -> str:
        """Execute MCP function with exponential backoff retry logic."""
        import json
        from ..mcp_tools import MCPExecutionManager

        # Convert JSON string to dict for shared utility
        try:
            args = json.loads(arguments_json)
        except (json.JSONDecodeError, ValueError) as e:
            return f"Error: Invalid JSON arguments: {e}"

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
            if event == "failure":
                from ..mcp_tools import MCPCircuitBreakerManager
                await MCPCircuitBreakerManager.record_event(self._mcp_tools_servers, self._mcp_tools_circuit_breaker, "failure", error_msg, backend_name=self.backend_name, agent_id=self.agent_id)
            else:
                from ..mcp_tools import MCPCircuitBreakerManager
                await MCPCircuitBreakerManager.record_event(self._mcp_tools_servers, self._mcp_tools_circuit_breaker, "success", backend_name=self.backend_name, agent_id=self.agent_id)

        result = await MCPExecutionManager.execute_function_with_retry(
            function_name=function_name,
            args=args,
            functions=self.functions,
            max_retries=max_retries,
            stats_callback=stats_callback,
            circuit_breaker_callback=circuit_breaker_callback,
            logger_instance=logger
        )

        # Convert result to string for response.py compatibility
        if isinstance(result, dict) and "error" in result:
            return f"Error: {result['error']}"
        return str(result)

    async def _setup_mcp_tools(self) -> None:
        """Initialize MCP client for mcp_tools-based servers (stdio + streamable-http)."""
        if not self._mcp_tools_servers or self._mcp_initialized:
            return

        from ..mcp_tools import MCPResourceManager

        try:
            # Setup MCP client using consolidated utilities
            self._mcp_client = await MCPResourceManager.setup_mcp_client(
                servers=self._mcp_tools_servers,
                allowed_tools=self.allowed_tools,
                exclude_tools=self.exclude_tools,
                circuit_breaker=self._mcp_tools_circuit_breaker,
                timeout_seconds=30,
                backend_name=self.backend_name,
                agent_id=self.agent_id
            )

            # Guard after client setup
            if not self._mcp_client:
                self._mcp_initialized = False
                logger.warning("MCP client setup failed, falling back to HTTP/no-MCP streaming paths")
                return  # fall back to HTTP/no-MCP streaming paths

            # Convert tools to functions using consolidated utility
            self.functions.update(
                MCPResourceManager.convert_tools_to_functions(
                    self._mcp_client,
                    backend_name=self.backend_name,
                    agent_id=self.agent_id
                )
            )
            self._mcp_initialized = True
            logger.info(
                f"Successfully initialized MCP mcp_tools sessions with {len(self.functions)} tools converted to functions"
            )

        except Exception as e:
            logger.warning(f"Failed to setup MCP sessions: {e}")
            self._mcp_client = None
            self._mcp_initialized = False
            self.functions = {}


    def _convert_mcp_tools_to_openai_format(self) -> List[Dict[str, Any]]:
        """Convert MCP tools (stdio + streamable-http) to OpenAI function declarations."""
        if not self.functions:
            return []

        converted_tools = []
        for function in self.functions.values():
            converted_tools.append(function.to_openai_format())

        logger.debug(
            f"Converted {len(converted_tools)} MCP tools (stdio + streamable-http) to OpenAI format"
        )
        return converted_tools

    async def _convert_http_servers_to_openai_format(self) -> List[Dict[str, Any]]:
        """Convert HTTP MCP servers to OpenAI native MCP format."""
        converted_servers = []

        for server in self._http_servers:
            server_name = server.get("name", "unnamed")

            # Apply circuit breaker filtering for HTTP server
            if not self._should_include_http_server(server_name):
                continue

            server_url = server.get("url")
            if not server_url:
                logger.warning(
                    f"HTTP MCP server {server_name} missing URL, skipping"
                )
                continue

            # Validate URL if validate_url is available
            if validate_url is not None:
                try:
                    # Allow localhost/private IPs to support dev/test environments
                    validate_url(
                        server_url,
                        allow_localhost=True,
                        allow_private_ips=True
                    )
                except ValueError as e:
                    logger.warning(f"Invalid URL for HTTP MCP server {server_name}: {e}")
                    
                    # Record failure for invalid URL using consolidated utility
                    from ..mcp_tools import MCPCircuitBreakerManager
                    server_dict = {"name": server_name}
                    await MCPCircuitBreakerManager.record_event([server_dict], self._http_circuit_breaker, "failure", f"Invalid URL: {e}", backend_name=self.backend_name, agent_id=self.agent_id)
                    continue

            # Convert to OpenAI native MCP format
            openai_server = {
                "type": "mcp",
                "server_label": server_name,
                "server_url": server_url,
                "require_approval": server.get("require_approval", "never"),
            }

            # Add allowed_tools if present
            if "allowed_tools" in server:
                openai_server["allowed_tools"] = server["allowed_tools"]

            # Add authorization if present with environment variable substitution
            if "authorization" in server:
                authorization_value = server["authorization"]
                logger.debug(f"Processing authorization for HTTP MCP server {server_name}")
                
                # Apply environment variable substitution using existing pattern
                if isinstance(authorization_value, str) and '${' in authorization_value:
                    
                    def replace_env_var(match):
                        var_name = match.group(1)
                        env_value = os.environ.get(var_name)
                        if env_value is None or env_value.strip() == "":
                            raise ValueError(f"Required environment variable '{var_name}' is not set for HTTP MCP server {server_name} authorization")
                        return env_value
                    
                    original_value = authorization_value
                    authorization_value = re.sub(r'\$\{([A-Z_][A-Z0-9_]*)\}', replace_env_var, authorization_value)
                    logger.debug(f"Environment variable substitution for {server_name}: {original_value} -> {authorization_value}")
                
                openai_server["authorization"] = authorization_value
                logger.info(f"Added authorization to HTTP MCP server {server_name}")

            converted_servers.append(openai_server)

        logger.debug(
            f"Converted {len(converted_servers)} HTTP MCP servers to OpenAI format"
        )
        return converted_servers

    async def _build_response_api_params(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], all_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build OpenAI Response API parameters with MCP integration."""
        # Convert messages to Response API format
        converted_messages = self.convert_messages_to_response_api_format(messages)

        # Response API parameters (uses 'input', not 'messages')
        api_params = {"input": converted_messages, "stream": True}

        # Direct passthrough of all parameters except those handled separately
        excluded_params = {
            "enable_web_search",
            "enable_code_interpreter",
            "agent_id",
            "session_id",
            "type",  # Used for MCP server configuration
            "mcp_servers",  # MCP-specific parameter
            "allowed_tools",  # Tool filtering parameter
            "exclude_tools",  # Tool filtering parameter
            "cwd",  # Current working directory
            "agent_temporary_workspace",  # Agent temporary workspace
        }
        for key, value in all_params.items():
            if key not in excluded_params and value is not None:
                # Handle OpenAI Response API parameter name differences
                if key == "max_tokens":
                    api_params["max_output_tokens"] = value
                else:
                    api_params[key] = value

        # Add framework tools (convert to Response API format)
        if tools:
            converted_tools = self.convert_tools_to_response_api_format(tools)
            api_params["tools"] = converted_tools

        # Add MCP tools (stdio + streamable-http) as functions
        if self.functions:
            mcp_tools = self._convert_mcp_tools_to_openai_format()
            if mcp_tools:
                if "tools" not in api_params:
                    api_params["tools"] = []
                api_params["tools"].extend(mcp_tools)
                logger.info(f"Added {len(mcp_tools)} MCP tools (stdio + streamable-http) to OpenAI Response API")

        # Add HTTP MCP servers as native MCP tools
        if self._http_servers:
            http_mcp_tools = await self._convert_http_servers_to_openai_format()
            if http_mcp_tools:
                if "tools" not in api_params:
                    api_params["tools"] = []
                api_params["tools"].extend(http_mcp_tools)
                logger.info(f"Added {len(http_mcp_tools)} HTTP MCP servers to OpenAI tools")

        # Add provider tools (web search, code interpreter) if enabled
        provider_tools = []
        enable_web_search = all_params.get("enable_web_search", False)
        enable_code_interpreter = all_params.get("enable_code_interpreter", False)

        if enable_web_search:
            provider_tools.append({"type": "web_search"})
        if enable_code_interpreter:
            provider_tools.append(
                {"type": "code_interpreter", "container": {"type": "auto"}}
            )

        if provider_tools:
            if "tools" not in api_params:
                api_params["tools"] = []
            api_params["tools"].extend(provider_tools)

        return api_params

    def convert_tools_to_response_api_format(
        self, tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Convert tools from Chat Completions format to Response API format if needed.

        Chat Completions format: {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
        Response API format: {"type": "function", "name": ..., "description": ..., "parameters": ...}
        """
        if not tools:
            return tools

        converted_tools = []
        for tool in tools:
            if tool.get("type") == "function" and "function" in tool:
                # Chat Completions format - convert to Response API format
                func = tool["function"]
                converted_tools.append(
                    {
                        "type": "function",
                        "name": func["name"],
                        "description": func["description"],
                        "parameters": func.get("parameters", {}),
                    }
                )
            else:
                # Already in Response API format or non-function tool
                converted_tools.append(tool)

        return converted_tools

    def convert_messages_to_response_api_format(
        self, messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Convert messages from Chat Completions format to Response API format.

        Chat Completions tool message: {"role": "tool", "tool_call_id": "...", "content": "..."}
        Response API tool message: {"type": "function_call_output", "call_id": "...", "output": "..."}

        Note: Assistant messages with tool_calls should not be in input - they're generated by the backend.
        """
        
        cleaned_messages = []
        for message in messages:
            if "status" in message and "role" not in message:
                # Create a copy without 'status'
                cleaned_message = {k: v for k, v in message.items() if k != "status"}
                cleaned_messages.append(cleaned_message)
            else:
                cleaned_messages.append(message)

        converted_messages = []

        for message in cleaned_messages:
            if message.get("role") == "tool":
                # Convert Chat Completions tool message to Response API format
                converted_message = {
                    "type": "function_call_output",
                    "call_id": message.get("tool_call_id"),
                    "output": message.get("content", ""),
                }
                converted_messages.append(converted_message)
            elif message.get("type") == "function_call_output":
                # Already in Response API format
                converted_messages.append(message)
            elif message.get("role") == "assistant" and "tool_calls" in message:
                # Assistant message with tool_calls - remove tool_calls when sending as input
               
                cleaned_message = {
                    k: v for k, v in message.items() if k != "tool_calls"
                }
                converted_messages.append(cleaned_message)
            else:
                # For other message types, pass through as-is
                converted_messages.append(message.copy())

        return converted_messages

    def _trim_message_history(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Trim message history to prevent unbounded growth in MCP execution loop."""
        from ..mcp_tools import MCPMessageManager
        max_items = getattr(self, '_max_mcp_message_history', 200)
        return MCPMessageManager.trim_message_history(messages, max_items)

    async def stream_with_mcp(
        self, client, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:

        """Stream response with stdio MCP function call execution loop."""
        max_iterations = 10  # Prevent infinite loops
        current_messages = self._trim_message_history(messages.copy())

        # Yield MCP session initiation status
        if self.functions:
            yield StreamChunk(
                type="mcp_status",
                status="mcp_tools_initiated",
                content=f"🔧 [MCP] {len(self.functions)} tools available",
                source="mcp_session"
            )

        for iteration in range(max_iterations):
            logger.info(f"MCP function call iteration {iteration + 1}/{max_iterations}")

            # Build API params for this iteration
            all_params = {**self.config, **kwargs}
            api_params = await self._build_response_api_params(current_messages, tools, all_params)

            # Start streaming
            stream = await client.responses.create(**api_params)

            # Track function calls in this iteration
            captured_function_calls = []
            current_function_call = None
            content = ""
            response_completed = False

            async for chunk in stream:
                if hasattr(chunk, "type"):
                    # Detect function call start
                    if (chunk.type == "response.output_item.added" and
                        hasattr(chunk, "item") and chunk.item and
                        getattr(chunk.item, "type", None) == "function_call"):

                        current_function_call = {
                            "call_id": getattr(chunk.item, "call_id", ""),
                            "name": getattr(chunk.item, "name", ""),
                            "arguments": ""
                        }
                        logger.info(f"Function call detected: {current_function_call['name']}")

                    # Accumulate function arguments
                    elif (chunk.type == "response.function_call_arguments.delta" and
                          current_function_call is not None):
                        delta = getattr(chunk, "delta", "")
                        current_function_call["arguments"] += delta

                    # Function call completed
                    elif (chunk.type == "response.output_item.done" and
                          current_function_call is not None):
                        captured_function_calls.append(current_function_call)
                        current_function_call = None

                    # Handle regular content and other events
                    elif chunk.type == "response.output_text.delta":
                        delta = getattr(chunk, "delta", "")
                        content += delta
                        yield StreamChunk(type="content", content=delta)

                    # Handle other streaming events (reasoning, provider tools, etc.)
                    else:
                        # Pass through other chunk types
                        yield self._process_stream_chunk(chunk)

                    # Response completed
                    if chunk.type == "response.completed":
                        response_completed = True
                        if captured_function_calls:
                            # Execute captured function calls
                            break  # Exit chunk loop to execute functions
                        else:
                            # No function calls, we're done
                            yield StreamChunk(type="done")
                            return

            # Execute any captured function calls
            if captured_function_calls:
                # Check if any of the function calls are NOT MCP functions
                non_mcp_functions = [call for call in captured_function_calls if call["name"] not in self.functions]

                if non_mcp_functions:
                    logger.info(f"Non-MCP function calls detected: {[call['name'] for call in non_mcp_functions]}. Exiting MCP execution loop.")
                    yield StreamChunk(type="done")
                    return

                # Execute only MCP function calls
                mcp_functions_executed = False
                for call in captured_function_calls:
                    function_name = call["name"]
                    if function_name in self.functions:
                        # Yield MCP tool call status
                        yield StreamChunk(
                            type="mcp_status", 
                            status="mcp_tool_called",
                            content=f"🔧 [MCP Tool] Calling {function_name}...",
                            source=f"mcp_{function_name}"
                        )
                        
                        # Execute MCP function with retry and exponential backoff
                        result = await self._execute_mcp_function_with_retry(
                            function_name, call["arguments"]
                        )

                        # Add both the function call and the function call output to messages
                      
                        current_messages.append({
                            "type": "function_call",
                            "call_id": call["call_id"],
                            "name": function_name,
                            "arguments": call["arguments"]
                        })
                        current_messages.append({
                            "type": "function_call_output",
                            "call_id": call["call_id"],
                            "output": str(result)
                        })

                        logger.info(f"Executed MCP function {function_name} (stdio/streamable-http)")
                        
                        # Yield MCP tool response status
                        yield StreamChunk(
                            type="mcp_status",
                            status="mcp_tool_response", 
                            content=f"✅ [MCP Tool] {function_name} completed",
                            source=f"mcp_{function_name}"
                        )
                        
                        mcp_functions_executed = True

                        # Trim history after each execution to bound memory usage
                        current_messages = self._trim_message_history(current_messages)

                # After executing MCP functions, continue to next iteration to get the final response
                if mcp_functions_executed:
                    continue
                else:
                    # No MCP functions were executed, exit the loop
                    yield StreamChunk(type="done")
                    return
            elif response_completed:
                # Response completed with no function calls - we're truly done
                yield StreamChunk(
                    type="mcp_status", 
                    status="mcp_session_complete",
                    content="✅ [MCP] Session completed",
                    source="mcp_session"
                )
                yield StreamChunk(type="done")
                return
            else:
                # No function calls and response not completed - continue
                continue

        # Max iterations reached
        logger.warning(f"Max MCP function call iterations ({max_iterations}) reached")
        yield StreamChunk(
            type="mcp_status", 
            status="mcp_session_complete",
            content="✅ [MCP] Session completed (max iterations reached)",
            source="mcp_session"
        )
        yield StreamChunk(type="done")

    async def stream_without_mcp(
        self, client, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream response without stdio MCP function execution (HTTP-only or no MCP)."""
        all_params = {**self.config, **kwargs}
        api_params = await self._build_response_api_params(messages, tools, all_params)

        stream = await client.responses.create(**api_params)

        async for chunk in stream:
            yield self._process_stream_chunk(chunk)

    def _process_stream_chunk(self, chunk) -> StreamChunk:
        """Process individual stream chunks and convert to StreamChunk format."""
        if not hasattr(chunk, "type"):
            return StreamChunk(type="content", content="")

        chunk_type = chunk.type

        # Handle different chunk types
        if chunk_type == "response.output_text.delta" and hasattr(chunk, "delta"):
            return StreamChunk(type="content", content=chunk.delta)

        elif chunk_type == "response.reasoning_text.delta" and hasattr(chunk, "delta"):
            return StreamChunk(
                type="reasoning",
                content=f"🧠 [Reasoning] {chunk.delta}",
                reasoning_delta=chunk.delta,
                item_id=getattr(chunk, "item_id", None),
                content_index=getattr(chunk, "content_index", None),
            )

        elif chunk_type == "response.reasoning_text.done":
            reasoning_text = getattr(chunk, "text", "")
            return StreamChunk(
                type="reasoning_done",
                content=f"\n🧠 [Reasoning Complete]\n",
                reasoning_text=reasoning_text,
                item_id=getattr(chunk, "item_id", None),
                content_index=getattr(chunk, "content_index", None),
            )

        elif chunk_type == "response.reasoning_summary_text.delta" and hasattr(chunk, "delta"):
            return StreamChunk(
                type="reasoning_summary",
                content=chunk.delta,
                reasoning_summary_delta=chunk.delta,
                item_id=getattr(chunk, "item_id", None),
                summary_index=getattr(chunk, "summary_index", None),
            )

        elif chunk_type == "response.reasoning_summary_text.done":
            summary_text = getattr(chunk, "text", "")
            return StreamChunk(
                type="reasoning_summary_done",
                content=f"\n📋 [Reasoning Summary Complete]\n",
                reasoning_summary_text=summary_text,
                item_id=getattr(chunk, "item_id", None),
                summary_index=getattr(chunk, "summary_index", None),
            )

        # Provider tool events
        elif chunk_type == "response.web_search_call.in_progress":
            return StreamChunk(type="content", content=f"\n🔍 [Provider Tool: Web Search] Starting search...")
        elif chunk_type == "response.web_search_call.searching":
            return StreamChunk(type="content", content=f"\n🔍 [Provider Tool: Web Search] Searching...")
        elif chunk_type == "response.web_search_call.completed":
            return StreamChunk(type="content", content=f"\n✅ [Provider Tool: Web Search] Search completed")

        elif chunk_type == "response.code_interpreter_call.in_progress":
            return StreamChunk(type="content", content=f"\n💻 [Provider Tool: Code Interpreter] Starting execution...")
        elif chunk_type == "response.code_interpreter_call.executing":
            return StreamChunk(type="content", content=f"\n💻 [Provider Tool: Code Interpreter] Executing...")
        elif chunk_type == "response.code_interpreter_call.completed":
            return StreamChunk(type="content", content=f"\n✅ [Provider Tool: Code Interpreter] Execution completed")

        # MCP events
        elif chunk_type == "response.mcp_list_tools.started":
            return StreamChunk(type="content", content="\n🔧 [MCP] Listing available tools...")
        elif chunk_type == "response.mcp_list_tools.completed":
            return StreamChunk(type="content", content="\n✅ [MCP] Tool listing completed")
        elif chunk_type == "response.mcp_list_tools.failed":
            return StreamChunk(type="content", content="\n❌ [MCP] Tool listing failed")

        elif chunk_type == "response.mcp_call.started":
            tool_name = getattr(chunk, "tool_name", "unknown")
            return StreamChunk(type="content", content=f"\n🔧 [MCP] Calling tool '{tool_name}'...")
        elif chunk_type == "response.mcp_call.in_progress":
            return StreamChunk(type="content", content="\n⏳ [MCP] Tool execution in progress...")
        elif chunk_type == "response.mcp_call.completed":
            tool_name = getattr(chunk, "tool_name", "unknown")
            return StreamChunk(type="content", content=f"\n✅ [MCP] Tool '{tool_name}' completed")
        elif chunk_type == "response.mcp_call.failed":
            tool_name = getattr(chunk, "tool_name", "unknown")
            error_msg = getattr(chunk, "error", "unknown error")
            return StreamChunk(type="content", content=f"\n❌ [MCP] Tool '{tool_name}' failed: {error_msg}")

        elif chunk_type == "response.completed":
            if hasattr(chunk, "response"):
                response_dict = self._convert_to_dict(chunk.response)
                return StreamChunk(type="complete_response", response=response_dict)
            else:
                return StreamChunk(type="done")

        # Default chunk - this should not happen for valid responses
        return StreamChunk(type="content", content="")

    async def stream_with_tools(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream response using OpenAI Response API with MCP integration."""
        
        agent_id = kwargs.get('agent_id', None)
        
        log_backend_activity(
            self.get_provider_name(),
            "Starting stream_with_tools",
            {"num_messages": len(messages), "num_tools": len(tools) if tools else 0},
            agent_id=agent_id
        )
        
        # Use async context manager for proper MCP resource management
        async with self:
            try:
                import openai

                client = openai.AsyncOpenAI(api_key=self.api_key)

                # Yield MCP connection status if MCP tools are available
                if self.functions and self._mcp_tools_servers:
                    yield StreamChunk(
                        type="mcp_status",
                        status="mcp_connected", 
                        content=f"✅ [MCP] Connected to {len(self._mcp_tools_servers)} servers",
                        source="mcp_setup"
                    )

                # Choose streaming mode based on MCP availability
                if self.functions:
                    
                    logger.info("Using stdio MCP execution mode")
                    async for chunk in self.stream_with_mcp(client, messages, tools, **kwargs):
                        yield chunk
                else:
                
                    logger.info("Using HTTP-only MCP mode")
                    async for chunk in self.stream_without_mcp(client, messages, tools, **kwargs):
                        yield chunk

            except Exception as e:
                # Enhanced error handling for MCP-related errors
                if isinstance(e, (MCPConnectionError, MCPTimeoutError, MCPServerError, MCPError)):
                    self._log_mcp_error(e, "streaming")
                    yield StreamChunk(
                        type="mcp_status",
                        status="mcp_error", 
                        content=f"⚠️ [MCP Error] {str(e)}",
                        source="mcp_error"
                    )
                    yield StreamChunk(
                        type="content",
                        content=f"\n⚠️ MCP error: {str(e)}; continuing without MCP tools\n"
                    )
                else:
                    logger.error(f"Streaming error: {e}")
                    yield StreamChunk(type="error", error=str(e))
              
            finally:
                # Ensure the underlying HTTP client is properly closed to avoid event loop issues
                try:
                    if hasattr(client, 'aclose'):
                        await client.aclose()
                except Exception:
                    # Suppress cleanup errors so we don't mask primary exceptions
                    pass

    def get_provider_name(self) -> str:
        """Get the provider name."""
        return "OpenAI"
    
    def get_filesystem_support(self) -> FilesystemSupport:
        """OpenAI supports filesystem through MCP servers."""
        return FilesystemSupport.MCP

    def get_supported_builtin_tools(self) -> List[str]:
        """Get list of builtin tools supported by OpenAI."""
        return ["web_search", "code_interpreter"]

    def extract_tool_name(self, tool_call: Dict[str, Any]) -> str:
        """Extract tool name from OpenAI format (handles both Chat Completions and Responses API)."""
        # Check if it's Chat Completions format
        if "function" in tool_call:
            return tool_call.get("function", {}).get("name", "unknown")
        # Otherwise assume Responses API format
        return tool_call.get("name", "unknown")

    def extract_tool_arguments(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """Extract tool arguments from OpenAI format (handles both Chat Completions and Responses API)."""
        # Check if it's Chat Completions format
        if "function" in tool_call:
            return tool_call.get("function", {}).get("arguments", {})
        # Otherwise assume Responses API format
        arguments = tool_call.get("arguments", {})
        if isinstance(arguments, str):
            try:
                import json

                return json.loads(arguments)
            except:
                return {}
        return arguments

    def extract_tool_call_id(self, tool_call: Dict[str, Any]) -> str:
        """Extract tool call ID from OpenAI format (handles both Chat Completions and Responses API)."""
        return tool_call.get("call_id") or tool_call.get("id") or ""

    def create_tool_result_message(
        self, tool_call: Dict[str, Any], result_content: str
    ) -> Dict[str, Any]:
        """Create tool result message for OpenAI Responses API format."""
        tool_call_id = self.extract_tool_call_id(tool_call)
        # Use Responses API format directly - no conversion needed
        return {
            "type": "function_call_output",
            "call_id": tool_call_id,
            "output": result_content,
        }

    def extract_tool_result_content(self, tool_result_message: Dict[str, Any]) -> str:
        """Extract content from OpenAI Responses API tool result message."""
        return tool_result_message.get("output", "")

    def _convert_to_dict(self, obj) -> Dict[str, Any]:
        """Convert any object to dictionary with multiple fallback methods."""
        try:
            if hasattr(obj, "model_dump"):
                return obj.model_dump()
            elif hasattr(obj, "dict"):
                return obj.dict()
            else:
                return dict(obj)
        except:
            # Final fallback: extract key attributes manually
            return {
                key: getattr(obj, key, None)
                for key in dir(obj)
                if not key.startswith("_") and not callable(getattr(obj, key, None))
            }

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text (rough approximation)."""
        return len(text) // 4

    def calculate_cost(
        self, input_tokens: int, output_tokens: int, model: str
    ) -> float:
        """Calculate cost for OpenAI token usage (2024-2025 pricing)."""
        model_lower = model.lower()

        if "gpt-4" in model_lower:
            if "4o-mini" in model_lower:
                input_cost = input_tokens * 0.00015 / 1000
                output_cost = output_tokens * 0.0006 / 1000
            elif "4o" in model_lower:
                input_cost = input_tokens * 0.005 / 1000
                output_cost = output_tokens * 0.020 / 1000
            else:
                input_cost = input_tokens * 0.03 / 1000
                output_cost = output_tokens * 0.06 / 1000
        elif "gpt-3.5" in model_lower:
            input_cost = input_tokens * 0.0005 / 1000
            output_cost = output_tokens * 0.0015 / 1000
        else:
            input_cost = input_tokens * 0.0005 / 1000
            output_cost = output_tokens * 0.0015 / 1000

        return input_cost + output_cost

    async def cleanup_mcp(self) -> None:
        """Cleanup MCP connections."""
        from ..mcp_tools import MCPResourceManager
        
        if self._mcp_client:
            await MCPResourceManager.cleanup_mcp_client(
                self._mcp_client,
                backend_name=self.backend_name,
                agent_id=self.agent_id
            )
            self._mcp_client = None
            self._mcp_initialized = False
            self.functions.clear()
    
    def _apply_mcp_tools_circuit_breaker_filtering(
        self, servers: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Apply circuit breaker filtering to mcp_tools servers."""
        from ..mcp_tools import MCPCircuitBreakerManager

        if not self._circuit_breakers_enabled or not self._mcp_tools_circuit_breaker:
            logger.info("Circuit breaker not enabled for mcp_tools servers")
            return servers

        return MCPCircuitBreakerManager.apply_circuit_breaker_filtering(servers, self._mcp_tools_circuit_breaker)
    
    def _should_include_http_server(self, server_name: str) -> bool:
        """Check if HTTP server should be included based on circuit breaker state.
        
        Returns:
            True if server should be included, False if it should be skipped
        """
        if not self._circuit_breakers_enabled or not self._http_circuit_breaker:
            logger.info(f"Circuit breaker not enabled for HTTP server {server_name}")
            return True
        
        try:
            should_skip = self._http_circuit_breaker.should_skip_server(server_name)
            
            if should_skip:
                logger.info(f"Circuit breaker: Skipping HTTP MCP server {server_name}")
                return False
            else:
                logger.info(f"Circuit breaker: Allowing HTTP MCP server {server_name}")
                return True
        except Exception as cb_error:
            logger.warning(f"Circuit breaker should_skip_server failed for HTTP server {server_name}: {cb_error}")
            # Default to allowing the server if circuit breaker fails
            return True
    
    async def get_circuit_breaker_status(self) -> Dict[str, Dict[str, Any]]:
        """Get current status of all circuit breakers.
        
        Returns:
            Dict with circuit breaker status for each transport type:
            {
                "mcp_tools": {
                    "enabled": bool,
                    "servers": {
                        "server_name": {
                            "would_skip": bool
                        }
                    }
                },
                "http": {...}
            }
        """
        status = {
            "mcp_tools": {
                "enabled": self._circuit_breakers_enabled and self._mcp_tools_circuit_breaker is not None,
                "servers": {}
            },
            "http": {
                "enabled": self._circuit_breakers_enabled and self._http_circuit_breaker is not None,
                "servers": {}
            }
        }
        
        # Get mcp_tools circuit breaker status
        if self._mcp_tools_circuit_breaker:
            for server in self._mcp_tools_servers:
                server_name = server.get("name", "unnamed")
                # Check if the server would be skipped by circuit breaker
                try:
                    would_skip = self._mcp_tools_circuit_breaker.should_skip_server(server_name)
                    status["mcp_tools"]["servers"][server_name] = {
                        "would_skip": would_skip
                    }
                except Exception as cb_error:
                    logger.warning(f"Circuit breaker should_skip_server failed for mcp_tools server {server_name}: {cb_error}")
                    # Default to not skipping if circuit breaker fails
                    status["mcp_tools"]["servers"][server_name] = {
                        "would_skip": False
                    }
        
        # Get HTTP circuit breaker status
        if self._http_circuit_breaker:
            for server in self._http_servers:
                server_name = server.get("name", "unnamed")
                try:
                    would_skip = self._http_circuit_breaker.should_skip_server(server_name)
                    status["http"]["servers"][server_name] = {
                        "would_skip": would_skip
                    }
                except Exception as cb_error:
                    logger.warning(f"Circuit breaker should_skip_server failed for HTTP server {server_name}: {cb_error}")
                    # Default to not skipping if circuit breaker fails
                    status["http"]["servers"][server_name] = {
                        "would_skip": False
                    }
        
        return status

    async def __aenter__(self) -> "ResponseBackend":
        """Async context manager entry."""
        from ..mcp_tools import MCPResourceManager
        
        # Initialize MCP tools if configured
        await MCPResourceManager.setup_mcp_context_manager(
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
        from ..mcp_tools import MCPResourceManager
        
        await MCPResourceManager.cleanup_mcp_context_manager(
            self, logger_instance=logger,
            backend_name=self.backend_name, agent_id=self.agent_id
        )
        # Don't suppress the original exception if one occurred
        return False
