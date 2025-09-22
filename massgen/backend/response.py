"""
Response API backend implementation.
Standalone implementation optimized for the standard Response API format (originated by OpenAI).
"""
from __future__ import annotations
import os
import json
import asyncio
from typing import Dict, List, Any, AsyncGenerator, Optional, Callable, Literal
from .base import LLMBackend, StreamChunk, FilesystemSupport
from ..logger_config import log_backend_activity, log_backend_agent_message, log_stream_chunk,logger

# MCP integration imports
from ..mcp_tools import (
    MultiMCPClient, MCPError, MCPConnectionError, MCPTimeoutError, MCPServerError,
    Function, MCPMessageManager
)
from ..mcp_tools.mcp_handler import MCPHandler


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

        # Initialize circuit breaker using MCP handler
        self._mcp_tools_circuit_breaker = None  # For stdio + streamable-http
        self._circuit_breakers_enabled = False
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

        # Initialize MCP handler for consolidated MCP logic
        self.mcp_handler = MCPHandler(self)
        self.mcp_handler.setup_circuit_breaker()

    # _setup_mcp_tools method removed - handled directly by MCPHandler.setup_context_manager()

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

    def _get_provider_tools(self, all_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get provider tools (web search, code interpreter) if enabled."""
        provider_tools = []
        enable_web_search = all_params.get("enable_web_search", False)
        enable_code_interpreter = all_params.get("enable_code_interpreter", False)

        if enable_web_search:
            provider_tools.append({"type": "web_search"})
        if enable_code_interpreter:
            provider_tools.append(
                {"type": "code_interpreter", "container": {"type": "auto"}}
            )
        return provider_tools

    async def _build_response_api_params(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], all_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build OpenAI Response API parameters with MCP integration."""
        # Convert messages to Response API format
        converted_messages = self.message_formatter.to_response_api_format(messages)

        # Response API parameters (uses 'input', not 'messages')
        api_params = {"input": converted_messages, "stream": True}

        # Direct passthrough of all parameters except those handled separately
        excluded_params = {
            "input",
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
            converted_tools = self.tool_formatter.to_response_api_format(tools)
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
        provider_tools = self._get_provider_tools(all_params)

        if provider_tools:
            if "tools" not in api_params:
                api_params["tools"] = []
            api_params["tools"].extend(provider_tools)

        return api_params


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
        """Recursively stream MCP responses using callbacks wired to the handler."""

        # Callback: build api params for this iteration
        async def build_api_params_callback(updated_messages: List[Dict[str, Any]], _tools: List[Dict[str, Any]], params_from_handler: Dict[str, Any]) -> Dict[str, Any]:
            all_params = {**self.config, **(params_from_handler or {})}
            return await self._build_response_api_params(updated_messages, _tools, all_params)

        # Callback: create a new stream
        async def create_stream_callback(api_params: Dict[str, Any]):
            return await client.responses.create(**api_params)

        # Callback: detect function calls; return (current_function_call, captured_calls, consumed)
        def detect_function_calls_callback(chunk, current_function_call, captured_calls):
            consumed = False
            if hasattr(chunk, "type"):
                if (
                    chunk.type == "response.output_item.added"
                    and hasattr(chunk, "item")
                    and chunk.item
                    and getattr(chunk.item, "type", None) == "function_call"
                ):
                    current_function_call = {
                        "call_id": getattr(chunk.item, "call_id", ""),
                        "name": getattr(chunk.item, "name", ""),
                        "arguments": "",
                    }
                    logger.info(f"Function call detected: {current_function_call['name']}")
                    consumed = True
                elif (
                    chunk.type == "response.function_call_arguments.delta"
                    and current_function_call is not None
                ):
                    delta = getattr(chunk, "delta", "")
                    current_function_call["arguments"] += delta
                    consumed = True
                elif chunk.type == "response.output_item.done" and current_function_call is not None:
                    captured_calls.append(current_function_call)
                    current_function_call = None
                    consumed = True
            return current_function_call, captured_calls, consumed

        # Callback: process non-function chunks into StreamChunk
        def process_chunk_callback(chunk):
            return self._process_stream_chunk(chunk, self.agent_id)

        # Callback: format tool result back into provider-specific message format
        def format_tool_result_callback(tool_call: Dict[str, Any], result_content: str) -> Dict[str, Any]:
            return self.create_tool_result_message(tool_call, result_content)

        async def fallback_stream_callback(fallback_messages, fallback_tools):
            all_params = {**self.config, **kwargs}
            api_params = await self._build_response_api_params(fallback_messages, fallback_tools, all_params)
            # Remove MCP functions from tools for clean fallback
            if "tools" in api_params:
                mcp_function_names = set(self.functions.keys())
                api_params["tools"] = [
                    t for t in api_params["tools"]
                    if not (t.get("type") == "function" and t.get("name") in mcp_function_names)
                ]
            async for chunk in self._stream_non_mcp(api_params, client, self.agent_id):
                yield chunk

        # Delegate to handler which will iterate streaming and MCP execution until completion
        async for chunk in self.mcp_handler.execute_mcp_functions_and_recurse(
            current_messages,
            tools,
            client,
            build_api_params_callback=build_api_params_callback,
            create_stream_callback=create_stream_callback,
            detect_function_calls_callback=detect_function_calls_callback,
            process_chunk_callback=process_chunk_callback,
            format_tool_result_callback=format_tool_result_callback,
            fallback_stream_callback=fallback_stream_callback,
            **kwargs,
        ):
            yield chunk

    async def _stream_non_mcp(self, api_params: Dict[str, Any], client, agent_id: str) -> AsyncGenerator[StreamChunk, None]:
        """Helper method for non-MCP streaming fallback."""
        stream = await client.responses.create(**api_params)
        async for chunk in stream:

            processed = self._process_stream_chunk(chunk, agent_id)
            if processed.type == "complete_response":
                # Yield the complete response first
                yield processed
                # Then signal completion with done chunk
                log_stream_chunk("backend.response", "done", None, self.agent_id)
                yield StreamChunk(type="done")
                #return  # Ensure execution stops here after non-MCP streaming completes
            else:
                yield processed

    async def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream response using OpenAI Response API with unified MCP/non-MCP processing."""

        # Use self.agent_id consistently instead of extracting from kwargs
        log_backend_activity(
            self.get_provider_name(),
            "Starting stream_with_tools",
            {"num_messages": len(messages), "num_tools": len(tools) if tools else 0},
            agent_id=self.agent_id
        )
        
        # Catch setup errors by wrapping the context manager itself
        try:
            # Use async context manager for proper MCP resource management
            async with self:
                import openai

                client = openai.AsyncOpenAI(api_key=self.api_key)

                try:
                    # Yield MCP connection status if it was generated during setup
                    if hasattr(self, "_mcp_connection_status_chunk"):
                        yield self._mcp_connection_status_chunk
                        del self._mcp_connection_status_chunk

                    # Determine if we should show "no MCP mode" message
                    should_show_no_mcp_message = self.mcp_handler.should_show_no_mcp_message()

                    if should_show_no_mcp_message:
                        # Show "no MCP mode" message and mark as notified to prevent repeated messages
                        yield StreamChunk(
                            type="mcp_status",
                            status="mcp_unavailable",
                            content="⚠️ [MCP] Setup failed or no tools available; continuing without MCP",
                            source="mcp_setup"
                        )

                    # UNIFIED MCP-AWARE STREAMING: Always use MCP-aware mode when servers are configured
                    # Let MCP handler manage circuit breaker coordination and fallbacks internally
                    if self.mcp_servers:
                        logger.info("Using unified MCP-aware streaming mode")
                        
                        current_messages = MCPMessageManager.trim_message_history(messages.copy(), self._max_mcp_message_history)

                        # Show available tools status if MCP functions are available
                        if self.functions:
                            yield StreamChunk(
                                type="mcp_status",
                                status="mcp_tools_initiated",
                                content=f"🔧 [MCP] {len(self.functions)} tools available",
                                source="mcp_session"
                            )

                        # Start unified MCP-aware streaming (handles fallbacks internally)
                        async for chunk in self._stream_mcp_recursive(current_messages, tools, client, **kwargs):
                            yield chunk

                    else:
                        # NO MCP SERVERS: Simple passthrough streaming
                        logger.info("Using standard streaming (no MCP servers configured)")
                        
                        all_params = {**self.config, **kwargs}
                        api_params = await self._build_response_api_params(messages, tools, all_params)

                        async for chunk in self._stream_non_mcp(api_params, client, self.agent_id):
                            yield chunk

                except Exception as e:
                    # Enhanced error handling for streaming errors
                    if isinstance(e, (MCPConnectionError, MCPTimeoutError, MCPServerError, MCPError)):
                        all_params = {**self.config, **kwargs}
                        api_params = await self._build_response_api_params(messages, tools, all_params)

                        # Get provider tools for fallback
                        provider_tools = self._get_provider_tools(all_params)

                        # Use MCPHandler for error handling (clean fallback without additional retries)
                        async for chunk in self.mcp_handler.handle_mcp_error_and_fallback(
                            e, api_params, provider_tools,
                            lambda params: self._stream_non_mcp(params, client, self.agent_id),
                            is_multi_agent_context=kwargs.get('is_multi_agent_context', False),
                            is_final_agent=kwargs.get('is_final_agent', False),
                            original_tools=tools,
                            existing_answers_available=kwargs.get('existing_answers_available', False)
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
            # Circuit breaker already handled retries during setup, proceed with clean fallback
            try:
                import openai
                client = openai.AsyncOpenAI(api_key=self.api_key)

                all_params = {**self.config, **kwargs}
                api_params = await self._build_response_api_params(messages, tools, all_params)

                # Get provider tools for fallback
                provider_tools = self._get_provider_tools(all_params)

                if isinstance(e, (MCPConnectionError, MCPTimeoutError, MCPServerError, MCPError)):
                    # Use MCPHandler for clean fallback (circuit breaker already handled retries)
                    async for chunk in self.mcp_handler.handle_mcp_error_and_fallback(
                        e, api_params, provider_tools,
                        lambda params: self._stream_non_mcp(params, client, self.agent_id),
                        is_multi_agent_context=kwargs.get('is_multi_agent_context', False),
                        is_final_agent=kwargs.get('is_final_agent', False),
                        original_tools=tools,
                        existing_answers_available=kwargs.get('existing_answers_available', False)
                    ):
                        yield chunk
                else:
                    # Generic setup error: notify if MCP was configured
                    if self.mcp_servers:
                        yield StreamChunk(
                            type="mcp_status",
                            status="mcp_unavailable",
                            content=f"⚠️ [MCP] Setup failed; continuing without MCP ({e})",
                            source="mcp_setup"
                        )
                    
                    # Remove MCP functions for clean fallback
                    if "tools" in api_params:
                        mcp_function_names = set(self.functions.keys())
                        api_params["tools"] = [
                            t for t in api_params["tools"]
                            if not (t.get("type") == "function" and t.get("name") in mcp_function_names)
                        ]
                    
                    # Proceed with standard streaming
                    async for chunk in self._stream_non_mcp(api_params, client, self.agent_id):
                        yield chunk
            except Exception as inner_e:
                logger.error(f"Streaming error during fallback: {inner_e}")
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

    def create_tool_result_message(
        self,
        tool_call: Dict[str, Any],
        result_content: str,
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


    async def cleanup_mcp(self) -> None:
        """Cleanup MCP connections."""
        await self.mcp_handler.cleanup_mcp()
    

    async def __aenter__(self) -> "ResponseBackend":
        """Async context manager entry."""
        # Initialize MCP tools if configured
        await self.mcp_handler.setup_context_manager()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[object],
    ) -> None:
        """Async context manager exit with automatic resource cleanup."""
        await self.mcp_handler.cleanup_context_manager(logger_instance=logger)
        # Don't suppress the original exception if one occurred
        return None