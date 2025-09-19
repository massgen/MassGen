"""
Response API backend implementation.
Standalone implementation optimized for the standard Response API format (originated by OpenAI).
"""
from __future__ import annotations
import os
import logging
import json
import asyncio
from typing import Dict, List, Any, AsyncGenerator, Optional, Callable, Literal
from .base import LLMBackend, StreamChunk, FilesystemSupport
from ..logger_config import log_backend_activity, log_backend_agent_message, log_stream_chunk,logger

# MCP integration imports
try:
    from ..mcp_tools import (
        MultiMCPClient, MCPError, MCPConnectionError, MCPCircuitBreaker,
        MCPConfigurationError, MCPValidationError, MCPTimeoutError, MCPServerError,
        MCPConfigValidator, Function, MCPErrorHandler, MCPSetupManager, MCPResourceManager, 
        MCPExecutionManager, MCPRetryHandler, MCPMessageManager, 
        MCPConfigHelper, MCPCircuitBreakerManager
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
                logger.warning("MCP tools circuit breaker config not available, disabling circuit breaker functionality")
                self._circuit_breakers_enabled = False
        else:
            logger.warning("Circuit breakers not available - proceeding without circuit breaker protection")

        # Transport Types:
        # - "stdio" & "streamable-http": Use our mcp_tools folder (MultiMCPClient)

        # Function registry for mcp_tools-based servers (stdio + streamable-http)
        self.functions: Dict[str, Function] = {}

        # Thread safety for counters
        self._stats_lock = asyncio.Lock()

        # Limit for message history growth within MCP execution loop
        self._max_mcp_message_history = kwargs.pop("max_mcp_message_history", 200)

        # Initialize backend name and agent ID for MCP operations
        self.backend_name = self.get_provider_name()
        self.agent_id = kwargs.get('agent_id', None)


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
            f"MCP tool call #{call_index_snapshot} failed - {log_type}: {error}"
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
    ) -> List[str, Any]:
        """Execute MCP function with exponential backoff retry logic."""
        import json

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
            # For individual function calls, we don't have server configurations readily available
            # The circuit breaker manager should handle this gracefully with empty server list
            if event == "failure":
                await MCPCircuitBreakerManager.record_event([], self._mcp_tools_circuit_breaker, "failure", error_msg, backend_name=self.backend_name, agent_id=self.agent_id)
            else:
                await MCPCircuitBreakerManager.record_event([], self._mcp_tools_circuit_breaker, "success", backend_name=self.backend_name, agent_id=self.agent_id)

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
            error_msg = f"Error: {result['error']}"
            return error_msg, result
        return str(result), result

    async def _setup_mcp_tools(self) -> None:
        """Initialize MCP client for mcp_tools-based servers (stdio + streamable-http)."""
        if not self.mcp_servers or self._mcp_initialized:
            return

        try:
            # Normalize and separate MCP servers by transport type using mcp_tools utilities
            normalized_servers = MCPSetupManager.normalize_mcp_servers(
                self.mcp_servers, backend_name=self.backend_name, agent_id=self.agent_id
            )
            mcp_tools_servers = MCPSetupManager.separate_stdio_streamable_servers(
                normalized_servers, backend_name=self.backend_name, agent_id=self.agent_id
            )
            
            if not mcp_tools_servers:
                logger.info("No stdio/streamable-http servers configured")
                return

            # Apply circuit breaker filtering before connection attempts  
            if self._circuit_breakers_enabled and self._mcp_tools_circuit_breaker:
                filtered_servers = MCPCircuitBreakerManager.apply_circuit_breaker_filtering(
                    mcp_tools_servers, self._mcp_tools_circuit_breaker,
                    backend_name=self.backend_name, agent_id=self.agent_id
                )
                if not filtered_servers:
                    logger.warning("All MCP servers blocked by circuit breaker during setup")
                    return
                if len(filtered_servers) < len(mcp_tools_servers):
                    logger.info(f"Circuit breaker filtered {len(mcp_tools_servers) - len(filtered_servers)} servers during setup")
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
                agent_id=self.agent_id
            )

            # Guard after client setup
            if not self._mcp_client:
                self._mcp_initialized = False
                logger.warning("MCP client setup failed, falling back to no-MCP streaming")
                return  # fall back to HTTP/no-MCP streaming paths

            # Convert tools to functions using consolidated utility
            self.functions.update(
                MCPResourceManager.convert_tools_to_functions(
                    self._mcp_client,
                    backend_name=self.backend_name,
                    agent_id=self.agent_id,
                    hook_manager=getattr(self, 'function_hook_manager', None),
                )
            )
            self._mcp_initialized = True
            logger.info(
                f"Successfully initialized MCP mcp_tools sessions with {len(self.functions)} tools converted to functions"
            )

            # Record success for circuit breaker
            if self._circuit_breakers_enabled and self._mcp_tools_circuit_breaker and self._mcp_client:
                try:
                    connected_server_names = self._mcp_client.get_server_names() if hasattr(self._mcp_client, 'get_server_names') else []
                    if connected_server_names:
                        connected_server_configs = [
                            server for server in servers_to_use
                            if server.get("name") in connected_server_names
                        ]
                        if connected_server_configs:
                            await MCPCircuitBreakerManager.record_success(
                                connected_server_configs, self._mcp_tools_circuit_breaker,
                                backend_name=self.backend_name, agent_id=self.agent_id
                            )
                except Exception as cb_error:
                    logger.warning(f"Failed to record circuit breaker success: {cb_error}")

        except Exception as e:
            # Record failure for circuit breaker
            if self._circuit_breakers_enabled and self._mcp_tools_circuit_breaker:
                try:
                    await MCPCircuitBreakerManager.record_failure(
                        servers_to_use if 'servers_to_use' in locals() else mcp_tools_servers if 'mcp_tools_servers' in locals() else [],
                        self._mcp_tools_circuit_breaker, str(e),
                        backend_name=self.backend_name, agent_id=self.agent_id
                    )
                except Exception as cb_error:
                    logger.warning(f"Failed to record circuit breaker failure: {cb_error}")

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


    async def _build_response_api_params(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], all_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build OpenAI Response API parameters with MCP integration."""
        # Convert messages to Response API format
        converted_messages = self.convert_messages_to_response_api_format(messages)

        # Response API parameters (uses 'input', not 'messages')
        api_params = {"input": converted_messages, "stream": True}

        # Direct passthrough of all parameters except those handled separately
        excluded_params = self.get_base_excluded_config_params() | {
            # Response backend specific exclusions
            "enable_web_search",
            "enable_code_interpreter",
            "allowed_tools",
            "exclude_tools",
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

    def _process_stream_chunk(self, chunk, agent_id) -> StreamChunk:
        """Process individual stream chunks and convert to StreamChunk format."""
        if not hasattr(chunk, "type"):
            return StreamChunk(type="content", content="")

        chunk_type = chunk.type

        # Handle different chunk types
        if chunk_type == "response.output_text.delta" and hasattr(chunk, "delta"):
            log_backend_agent_message(
                agent_id or "default",
                "RECV",
                {"content": chunk.delta},
                backend_name=self.get_provider_name()
            )
            log_stream_chunk("backend.response", "content", chunk.delta, agent_id)
            return StreamChunk(type="content", content=chunk.delta)

        elif chunk_type == "response.reasoning_text.delta" and hasattr(chunk, "delta"):
            log_stream_chunk("backend.response", "reasoning", chunk.delta, agent_id)
            return StreamChunk(
                type="reasoning",
                content=f"🧠 [Reasoning] {chunk.delta}",
                reasoning_delta=chunk.delta,
                item_id=getattr(chunk, "item_id", None),
                content_index=getattr(chunk, "content_index", None),
            )

        elif chunk_type == "response.reasoning_text.done":
            reasoning_text = getattr(chunk, "text", "")
            log_stream_chunk("backend.response", "reasoning_done", reasoning_text, agent_id)
            return StreamChunk(
                type="reasoning_done",
                content=f"\n🧠 [Reasoning Complete]\n",
                reasoning_text=reasoning_text,
                item_id=getattr(chunk, "item_id", None),
                content_index=getattr(chunk, "content_index", None),
            )

        elif chunk_type == "response.reasoning_summary_text.delta" and hasattr(chunk, "delta"):
            log_stream_chunk("backend.response", "reasoning_summary", chunk.delta, agent_id)
            return StreamChunk(
                type="reasoning_summary",
                content=chunk.delta,
                reasoning_summary_delta=chunk.delta,
                item_id=getattr(chunk, "item_id", None),
                summary_index=getattr(chunk, "summary_index", None),
            )

        elif chunk_type == "response.reasoning_summary_text.done":
            summary_text = getattr(chunk, "text", "")
            log_stream_chunk("backend.response", "reasoning_summary_done", summary_text, agent_id)
            return StreamChunk(
                type="reasoning_summary_done",
                content=f"\n📋 [Reasoning Summary Complete]\n",
                reasoning_summary_text=summary_text,
                item_id=getattr(chunk, "item_id", None),
                summary_index=getattr(chunk, "summary_index", None),
            )

        # Provider tool events
        elif chunk_type == "response.web_search_call.in_progress":
            log_stream_chunk("backend.response", "web_search", "Starting search", agent_id)
            return StreamChunk(type="content", content=f"\n🔍 [Provider Tool: Web Search] Starting search...")
        elif chunk_type == "response.web_search_call.searching":
            log_stream_chunk("backend.response", "web_search", "Searching", agent_id)
            return StreamChunk(type="content", content=f"\n🔍 [Provider Tool: Web Search] Searching...")
        elif chunk_type == "response.web_search_call.completed":
            log_stream_chunk("backend.response", "web_search", "Search completed", agent_id)
            return StreamChunk(type="content", content=f"\n✅ [Provider Tool: Web Search] Search completed")

        elif chunk_type == "response.code_interpreter_call.in_progress":
            log_stream_chunk("backend.response", "code_interpreter", "Starting execution", agent_id)
            return StreamChunk(type="content", content=f"\n💻 [Provider Tool: Code Interpreter] Starting execution...")
        elif chunk_type == "response.code_interpreter_call.executing":
            log_stream_chunk("backend.response", "code_interpreter", "Executing", agent_id)
            return StreamChunk(type="content", content=f"\n💻 [Provider Tool: Code Interpreter] Executing...")
        elif chunk_type == "response.code_interpreter_call.completed":
            log_stream_chunk("backend.response", "code_interpreter", "Execution completed", agent_id)
            return StreamChunk(type="content", content=f"\n✅ [Provider Tool: Code Interpreter] Execution completed")
        elif chunk.type == "response.output_item.done":
            # Get search query or executed code details - show them right after completion
            if hasattr(chunk, "item") and chunk.item:
                if (
                    hasattr(chunk.item, "type")
                    and chunk.item.type == "web_search_call"
                ):
                    if hasattr(chunk.item, "action") and (
                        "query" in chunk.item.action
                    ):
                        search_query = chunk.item.action["query"]
                        if search_query:
                            log_stream_chunk("backend.response", "search_query", search_query, agent_id)
                            return StreamChunk(
                                type="content",
                                content=f"\n🔍 [Search Query] '{search_query}'\n",
                            )
                elif (
                    hasattr(chunk.item, "type")
                    and chunk.item.type == "code_interpreter_call"
                ):
                    if hasattr(chunk.item, "code") and chunk.item.code:
                        # Format code as a proper code block - don't assume language
                        log_stream_chunk("backend.response", "code_executed", chunk.item.code, agent_id)
                        return StreamChunk(
                            type="content",
                            content=f"💻 [Code Executed]\n```\n{chunk.item.code}\n```\n",
                        )

                    # Also show the execution output if available
                    if (
                        hasattr(chunk.item, "outputs")
                        and chunk.item.outputs
                    ):
                        for output in chunk.item.outputs:
                            output_text = None
                            if hasattr(output, "text") and output.text:
                                output_text = output.text
                            elif (
                                hasattr(output, "content")
                                and output.content
                            ):
                                output_text = output.content
                            elif hasattr(output, "data") and output.data:
                                output_text = str(output.data)
                            elif isinstance(output, str):
                                output_text = output
                            elif isinstance(output, dict):
                                # Handle dict format outputs
                                if "text" in output:
                                    output_text = output["text"]
                                elif "content" in output:
                                    output_text = output["content"]
                                elif "data" in output:
                                    output_text = str(output["data"])

                            if output_text and output_text.strip():
                                log_stream_chunk("backend.response", "code_result", output_text.strip(), agent_id)
                                return StreamChunk(
                                    type="content",
                                    content=f"📊 [Result] {output_text.strip()}\n",
                                )
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

        elif chunk.type == "response.completed":
            # Extract and yield tool calls from the complete response
            if hasattr(chunk, "response"):
                response_dict = self._convert_to_dict(chunk.response)

                # Handle builtin tool results from output array with simple content format
                if (
                    isinstance(response_dict, dict)
                    and "output" in response_dict
                ):
                    for item in response_dict["output"]:
                        if item.get("type") == "code_interpreter_call":
                            # Code execution result
                            status = item.get("status", "unknown")
                            code = item.get("code", "")
                            outputs = item.get("outputs")
                            content = (
                                f"\n🔧 Code Interpreter [{status.title()}]"
                            )
                            if code:
                                content += f": {code}"
                            if outputs:
                                content += f" → {outputs}"

                            log_stream_chunk("backend.response", "code_interpreter_result", content, agent_id)
                            return StreamChunk(
                                type="content", content=content
                            )
                        elif item.get("type") == "web_search_call":
                            # Web search result
                            status = item.get("status", "unknown")
                            # Query is in action.query, not directly in item
                            query = item.get("action", {}).get("query", "")
                            results = item.get("results")

                            # Only show web search completion if query is present
                            if query:
                                content = f"\n🔧 Web Search [{status.title()}]: {query}"
                                if results:
                                    content += (
                                        f" → Found {len(results)} results"
                                    )
                                log_stream_chunk("backend.response", "web_search_result", content, agent_id)
                                return StreamChunk(
                                    type="tool", content=content
                                )

                # Yield the complete response for internal use
                log_stream_chunk("backend.response", "complete_response", "Response completed", agent_id)
                return StreamChunk(
                    type="complete_response", response=response_dict
                )

        # Default chunk - this should not happen for valid responses
        return StreamChunk(type="content", content="")

    async def _stream_mcp_recursive(
        self,
        current_messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]], 
        client,
        **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """Recursively stream MCP responses, executing function calls as needed."""
        
        # Build API params for this iteration
        all_params = {**self.config, **kwargs}
        api_params = await self._build_response_api_params(current_messages, tools, all_params)

        agent_id = kwargs['agent_id']
        # Start streaming
        stream = await client.responses.create(**api_params)

        # Track function calls in this iteration
        captured_function_calls = []
        current_function_call = None
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
                    yield StreamChunk(type="content", content=delta)

                # Handle other streaming events (reasoning, provider tools, etc.)
                else:
                    result = self._process_stream_chunk(chunk, agent_id)
                    yield result

                # Response completed
                if chunk.type == "response.completed":
                    response_completed = True
                    if captured_function_calls:
                        # Execute captured function calls and recurse
                        break  # Exit chunk loop to execute functions
                    else:
                        # No function calls, we're done (base case)
                        yield StreamChunk(type="done")
                        return

        # Execute any captured function calls
        if captured_function_calls and response_completed:
            # Check if any of the function calls are NOT MCP functions
            non_mcp_functions = [call for call in captured_function_calls if call["name"] not in self.functions]

            if non_mcp_functions:
                logger.info(f"Non-MCP function calls detected: {[call['name'] for call in non_mcp_functions]}. Ending MCP processing.")
                yield StreamChunk(type="done")
                return

            # Check circuit breaker status before executing MCP functions
            if self._circuit_breakers_enabled and self._mcp_tools_circuit_breaker:
                # Get current mcp_tools servers using utility functions
                normalized_servers = MCPSetupManager.normalize_mcp_servers(self.mcp_servers)
                mcp_tools_servers = MCPSetupManager.separate_stdio_streamable_servers(normalized_servers)
                
                filtered_servers = MCPCircuitBreakerManager.apply_circuit_breaker_filtering(
                    mcp_tools_servers, self._mcp_tools_circuit_breaker
                )
                if not filtered_servers:
                    logger.warning("All MCP servers blocked by circuit breaker")
                    yield StreamChunk(
                        type="mcp_status",
                        status="mcp_blocked",
                        content="⚠️ [MCP] All servers blocked by circuit breaker",
                        source="circuit_breaker"
                    )
                    yield StreamChunk(type="done")
                    return

            # Execute only MCP function calls
            mcp_functions_executed = False
            updated_messages = current_messages.copy()
            
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
                    
                    try:
                        # Execute MCP function with retry and exponential backoff
                        result, result_obj = await self._execute_mcp_function_with_retry(
                            function_name, call["arguments"]
                        )
                        
                        # Check if function failed after all retries
                        if isinstance(result, str) and result.startswith("Error:"):
                            # Log failure and skip to next function
                            logger.warning(f"MCP function {function_name} failed after retries: {result}")
                            continue
                            
                    except Exception as e:
                        # Only catch unexpected non-MCP system errors
                        logger.error(f"Unexpected error in MCP function execution: {e}")
                        continue

                    # Add function call to messages and yield as StreamChunk
                    function_call_msg = {
                        "type": "function_call",
                        "call_id": call["call_id"],
                        "name": function_name,
                        "arguments": call["arguments"]
                    }
                    updated_messages.append(function_call_msg)
                    yield StreamChunk(
                        type="mcp_status",
                        status="function_call",
                        content=f"Arguments for Calling {function_name}: {call["arguments"]}",
                        source=f"mcp_{function_name}"
                    )
                    
                    # Add function output to messages and yield as StreamChunk
                    function_output_msg = {
                        "type": "function_call_output",
                        "call_id": call["call_id"],
                        "output": str(result)
                    }
                    updated_messages.append(function_output_msg)
                    yield StreamChunk(
                        type="mcp_status",
                        status="function_call_output",
                        content=f"Results for Calling {function_name}: {str(result_obj.content[0].text)}",
                        source=f"mcp_{function_name}"
                    )

                    logger.info(f"Executed MCP function {function_name} (stdio/streamable-http)")
                    
                    # Yield MCP tool response status
                    yield StreamChunk(
                        type="mcp_status",
                        status="mcp_tool_response", 
                        content=f"✅ [MCP Tool] {function_name} completed",
                        source=f"mcp_{function_name}"
                    )
                    
                    mcp_functions_executed = True

            # Trim history after function executions to bound memory usage
            if mcp_functions_executed:
                updated_messages = MCPMessageManager.trim_message_history(updated_messages, self._max_mcp_message_history)
                
                # Recursive call with updated messages
                async for chunk in self._stream_mcp_recursive(updated_messages, tools, client, **kwargs):
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
                source="mcp_session"
            )
            yield StreamChunk(type="done")
            return

    async def stream_with_tools(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream response using OpenAI Response API with unified MCP/non-MCP processing."""
        
        agent_id = kwargs.get('agent_id', None)
        
        log_backend_activity(
            self.get_provider_name(),
            "Starting stream_with_tools",
            {"num_messages": len(messages), "num_tools": len(tools) if tools else 0},
            agent_id=agent_id
        )
        
        # Catch setup errors by wrapping the context manager itself
        try:
            # Use async context manager for proper MCP resource management
            async with self:
                import openai

                client = openai.AsyncOpenAI(api_key=self.api_key)

                try:
                    # Determine if MCP processing is needed
                    use_mcp = bool(self.functions)

                    # If MCP is configured but unavailable, inform the user and fall back
                    if self.mcp_servers and not use_mcp:
                        yield StreamChunk(
                            type="mcp_status",
                            status="mcp_unavailable",
                            content="⚠️ [MCP] Setup failed or no tools available; continuing without MCP",
                            source="mcp_setup"
                        )

                    # Yield MCP connection status if MCP tools are available
                    if use_mcp and self.mcp_servers:
                        # Count only stdio/streamable-http servers for display
                        normalized_servers = MCPSetupManager.normalize_mcp_servers(self.mcp_servers)
                        mcp_tools_servers = MCPSetupManager.separate_stdio_streamable_servers(normalized_servers)
                        if mcp_tools_servers:
                            yield StreamChunk(
                                type="mcp_status",
                                status="mcp_connected", 
                                content=f"✅ [MCP] Connected to {len(mcp_tools_servers)} servers",
                                source="mcp_setup"
                            )

                    if use_mcp:
                        # MCP MODE: Recursive function call detection and execution
                        logger.info("Using recursive MCP execution mode")
                        
                        current_messages = MCPMessageManager.trim_message_history(messages.copy(), 200)

                        # Yield MCP session initiation status
                        yield StreamChunk(
                            type="mcp_status",
                            status="mcp_tools_initiated",
                            content=f"🔧 [MCP] {len(self.functions)} tools available",
                            source="mcp_session"
                        )

                        # Start recursive MCP streaming
                        async for chunk in self._stream_mcp_recursive(current_messages, tools, client, **kwargs):
                            yield chunk

                    else:
                        # NON-MCP MODE: Simple passthrough streaming
                        logger.info("Using no-MCP mode")
                        
                        all_params = {**self.config, **kwargs}
                        api_params = await self._build_response_api_params(messages, tools, all_params)

                        stream = await client.responses.create(**api_params)

                        async for chunk in stream:
                            processed = self._process_stream_chunk(chunk, agent_id)
                            if processed.type == "complete_response":
                                # Yield the complete response first
                                yield processed
                                # Then signal completion with done chunk
                                log_stream_chunk("backend.response", "done", None, agent_id)
                                yield StreamChunk(type="done")
                            else:
                                yield processed

                except Exception as e:
                    # Enhanced error handling for MCP-related errors during streaming
                    if isinstance(e, (MCPConnectionError, MCPTimeoutError, MCPServerError, MCPError)):
                        # Record failure for circuit breaker
                        if self._circuit_breakers_enabled and self._mcp_tools_circuit_breaker:
                            try:
                                # Get current mcp_tools servers for circuit breaker failure recording
                                normalized_servers = MCPSetupManager.normalize_mcp_servers(self.mcp_servers)
                                mcp_tools_servers = MCPSetupManager.separate_stdio_streamable_servers(normalized_servers)
                                
                                await MCPCircuitBreakerManager.record_failure(
                                    mcp_tools_servers, self._mcp_tools_circuit_breaker, str(e),
                                    backend_name=self.backend_name, agent_id=agent_id
                                )
                            except Exception as cb_error:
                                logger.warning(f"Failed to record circuit breaker failure: {cb_error}")

                        # Use local error handling function
                        all_params = {**self.config, **kwargs}
                        api_params = await self._build_response_api_params(messages, tools, all_params)
                        
                        # Get provider tools for fallback
                        provider_tools = []
                        enable_web_search = all_params.get("enable_web_search", False)
                        enable_code_interpreter = all_params.get("enable_code_interpreter", False)
                        if enable_web_search:
                            provider_tools.append({"type": "web_search"})
                        if enable_code_interpreter:
                            provider_tools.append({"type": "code_interpreter", "container": {"type": "auto"}})
                        
                        # Use inline fallback logic instead of deleted stream_without_mcp method
                        async def fallback_stream(params):
                            stream = await client.responses.create(**params)
                            async for chunk in stream:
                                yield self._process_stream_chunk(chunk, agent_id)
                        
                        async for chunk in self._handle_mcp_error_and_fallback(
                            e, api_params, provider_tools, fallback_stream
                        ):
                            yield chunk
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
        except Exception as e:
            # Handle exceptions that occur during MCP setup (__aenter__) or teardown
            # Provide a clear user-facing message and fall back to non-MCP streaming
            try:
                import openai
                client = openai.AsyncOpenAI(api_key=self.api_key)

                all_params = {**self.config, **kwargs}
                api_params = await self._build_response_api_params(messages, tools, all_params)

                # Get provider tools for fallback
                provider_tools = []
                enable_web_search = all_params.get("enable_web_search", False)
                enable_code_interpreter = all_params.get("enable_code_interpreter", False)
                if enable_web_search:
                    provider_tools.append({"type": "web_search"})
                if enable_code_interpreter:
                    provider_tools.append({"type": "code_interpreter", "container": {"type": "auto"}})

                # Fallback stream that bypasses MCP entirely
                async def fallback_stream(params):
                    stream = await client.responses.create(**params)
                    async for chunk in stream:
                        yield self._process_stream_chunk(chunk, agent_id)

                if isinstance(e, (MCPConnectionError, MCPTimeoutError, MCPServerError, MCPError)):
                    async for chunk in self._handle_mcp_error_and_fallback(
                        e, api_params, provider_tools, fallback_stream
                    ):
                        yield chunk
                else:
                    # Generic setup error: still notify if MCP was configured
                    if self.mcp_servers:
                        yield StreamChunk(
                            type="mcp_status",
                            status="mcp_unavailable",
                            content=f"⚠️ [MCP] Setup failed; continuing without MCP ({e})",
                            source="mcp_setup"
                        )

                    # Proceed with non-MCP streaming
                    stream = await client.responses.create(**api_params)
                    async for chunk in stream:
                        yield self._process_stream_chunk(chunk, agent_id)
            except Exception as inner_e:
                logger.error(f"Streaming error during MCP setup fallback: {inner_e}")
                yield StreamChunk(type="error", error=str(inner_e))
            finally:
                try:
                    if 'client' in locals() and hasattr(client, 'aclose'):
                        await client.aclose()
                except Exception:
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
        if self._mcp_client:
            await MCPResourceManager.cleanup_mcp_client(
                self._mcp_client,
                backend_name=self.backend_name,
                agent_id=self.agent_id
            )
            self._mcp_client = None
            self._mcp_initialized = False
            self.functions.clear()
    

    async def __aenter__(self) -> "ResponseBackend":
        """Async context manager entry."""
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
        await MCPResourceManager.cleanup_mcp_context_manager(
            self, logger_instance=logger,
            backend_name=self.backend_name, agent_id=self.agent_id
        )
        # Don't suppress the original exception if one occurred
        return False
