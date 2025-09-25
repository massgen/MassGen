# -*- coding: utf-8 -*-
"""
Response API backend implementation.
Standalone implementation optimized for the standard Response API format (originated by OpenAI).
"""
from __future__ import annotations

import os
from typing import Any, AsyncGenerator, Dict, List, Optional

from ..logger_config import (
    log_backend_activity,
    log_backend_agent_message,
    log_stream_chunk,
    logger,
)

# MCP integration imports - now inherited from MCPBackend
from ..mcp_tools import (
    MCPCircuitBreakerManager,
    MCPConnectionError,
    MCPError,
    MCPServerError,
    MCPSetupManager,
    MCPTimeoutError,
)
from .base import FilesystemSupport, StreamChunk
from .base_with_mcp import MCPBackend
from .utils.api_params_handler import ResponseAPIParamsHandler
from .utils.formatter import ResponseFormatter


class ResponseBackend(MCPBackend):
    """Backend using the standard Response API format."""

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(api_key, **kwargs)
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.formatter = ResponseFormatter()
        self.api_params_handler = ResponseAPIParamsHandler(self)

    async def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream response using OpenAI Response API with unified MCP/non-MCP processing."""

        agent_id = kwargs.get("agent_id", None)

        log_backend_activity(
            self.get_provider_name(),
            "Starting stream_with_tools",
            {"num_messages": len(messages), "num_tools": len(tools) if tools else 0},
            agent_id=agent_id,
        )

        # Catch setup errors by wrapping the context manager itself
        try:
            # Use async context manager for proper MCP resource management
            async with self:
                import openai

                client = openai.AsyncOpenAI(api_key=self.api_key)

                try:
                    # Determine if MCP processing is needed
                    use_mcp = bool(self._mcp_functions)

                    # Use parent class method to yield MCP status chunks
                    async for status_chunk in super().yield_mcp_status_chunks(use_mcp):
                        yield status_chunk

                    if use_mcp:
                        # MCP MODE: Recursive function call detection and execution
                        logger.info("Using recursive MCP execution mode")

                        current_messages = super()._trim_message_history(messages.copy())

                        # Start recursive MCP streaming
                        async for chunk in self._stream_with_mcp_tools(current_messages, tools, client, **kwargs):
                            yield chunk

                    else:
                        # NON-MCP MODE: Simple passthrough streaming
                        logger.info("Using no-MCP mode")

                        # Start non-MCP streaming
                        async for chunk in self._stream_without_mcp_tools(messages, tools, client, **kwargs):
                            yield chunk

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
                                    mcp_tools_servers,
                                    self._mcp_tools_circuit_breaker,
                                    str(e),
                                    backend_name=self.backend_name,
                                    agent_id=agent_id,
                                )
                            except Exception as cb_error:
                                logger.warning(f"Failed to record circuit breaker failure: {cb_error}")

                        # Handle MCP exceptions with fallback
                        async for chunk in self._stream_handle_mcp_exceptions(e, messages, tools, client, **kwargs):
                            yield chunk
                    else:
                        logger.error(f"Streaming error: {e}")
                        yield StreamChunk(type="error", error=str(e))

                finally:
                    await self._cleanup_client(client)
        except Exception as e:
            # Handle exceptions that occur during MCP setup (__aenter__) or teardown
            # Provide a clear user-facing message and fall back to non-MCP streaming
            try:
                import openai

                client = openai.AsyncOpenAI(api_key=self.api_key)

                if isinstance(e, (MCPConnectionError, MCPTimeoutError, MCPServerError, MCPError)):
                    # Handle MCP exceptions with fallback
                    async for chunk in self._stream_handle_mcp_exceptions(e, messages, tools, client, **kwargs):
                        yield chunk
                else:
                    # Generic setup error: still notify if MCP was configured
                    if self.mcp_servers:
                        yield StreamChunk(
                            type="mcp_status",
                            status="mcp_unavailable",
                            content=f"⚠️ [MCP] Setup failed; continuing without MCP ({e})",
                            source="mcp_setup",
                        )

                    # Proceed with non-MCP streaming
                    async for chunk in self._stream_without_mcp_tools(messages, tools, client, **kwargs):
                        yield chunk
            except Exception as inner_e:
                logger.error(f"Streaming error during MCP setup fallback: {inner_e}")
                yield StreamChunk(type="error", error=str(inner_e))
            finally:
                await self._cleanup_client(client)

    async def _stream_with_mcp_tools(
        self,
        current_messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        client,
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Recursively stream MCP responses, executing function calls as needed."""

        # Build API params for this iteration
        all_params = {**self.config, **kwargs}
        api_params = await self.api_params_handler.build_api_params(current_messages, tools, all_params)

        agent_id = kwargs["agent_id"]
        # Start streaming
        stream = await client.responses.create(**api_params)

        # Track function calls in this iteration
        captured_function_calls = []
        current_function_call = None
        response_completed = False

        async for chunk in stream:
            print(chunk)
            if hasattr(chunk, "type"):
                # Detect function call start
                if chunk.type == "response.output_item.added" and hasattr(chunk, "item") and chunk.item and getattr(chunk.item, "type", None) == "function_call":
                    current_function_call = {
                        "call_id": getattr(chunk.item, "call_id", ""),
                        "name": getattr(chunk.item, "name", ""),
                        "arguments": "",
                    }
                    logger.info(f"Function call detected: {current_function_call['name']}")

                # Accumulate function arguments
                elif chunk.type == "response.function_call_arguments.delta" and current_function_call is not None:
                    delta = getattr(chunk, "delta", "")
                    current_function_call["arguments"] += delta

                # Function call completed
                elif chunk.type == "response.output_item.done" and current_function_call is not None:
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
            non_mcp_functions = [call for call in captured_function_calls if call["name"] not in self._mcp_functions]

            if non_mcp_functions:
                logger.info(f"Non-MCP function calls detected: {[call['name'] for call in non_mcp_functions]}. Ending MCP processing.")
                yield StreamChunk(type="done")
                return

            # Check circuit breaker status before executing MCP functions
            if not await super()._check_circuit_breaker_before_execution():
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
            # Ensure every captured function call gets a result to prevent hanging
            processed_call_ids = set()

            for call in captured_function_calls:
                function_name = call["name"]
                if function_name in self._mcp_functions:
                    # Yield MCP tool call status
                    yield StreamChunk(
                        type="mcp_status",
                        status="mcp_tool_called",
                        content=f"🔧 [MCP Tool] Calling {function_name}...",
                        source=f"mcp_{function_name}",
                    )

                    try:
                        # Execute MCP function with retry and exponential backoff
                        result, result_obj = await super()._execute_mcp_function_with_retry(
                            function_name,
                            call["arguments"],
                        )

                        # Check if function failed after all retries
                        if isinstance(result, str) and result.startswith("Error:"):
                            # Log failure but still create tool response
                            logger.warning(f"MCP function {function_name} failed after retries: {result}")

                            # Add error result to messages
                            function_call_msg = {
                                "type": "function_call",
                                "call_id": call["call_id"],
                                "name": function_name,
                                "arguments": call["arguments"],
                            }
                            updated_messages.append(function_call_msg)

                            error_output_msg = {
                                "type": "function_call_output",
                                "call_id": call["call_id"],
                                "output": result,
                            }
                            updated_messages.append(error_output_msg)

                            processed_call_ids.add(call["call_id"])
                            mcp_functions_executed = True
                            continue

                    except Exception as e:
                        # Only catch unexpected non-MCP system errors
                        logger.error(f"Unexpected error in MCP function execution: {e}")
                        error_msg = f"Error executing {function_name}: {str(e)}"

                        # Add error result to messages
                        function_call_msg = {
                            "type": "function_call",
                            "call_id": call["call_id"],
                            "name": function_name,
                            "arguments": call["arguments"],
                        }
                        updated_messages.append(function_call_msg)

                        error_output_msg = {
                            "type": "function_call_output",
                            "call_id": call["call_id"],
                            "output": error_msg,
                        }
                        updated_messages.append(error_output_msg)

                        processed_call_ids.add(call["call_id"])
                        mcp_functions_executed = True
                        continue

                    # Add function call to messages and yield as StreamChunk
                    function_call_msg = {
                        "type": "function_call",
                        "call_id": call["call_id"],
                        "name": function_name,
                        "arguments": call["arguments"],
                    }
                    updated_messages.append(function_call_msg)
                    yield StreamChunk(
                        type="mcp_status",
                        status="function_call",
                        content=f"Arguments for Calling {function_name}: {call['arguments']}",
                        source=f"mcp_{function_name}",
                    )

                    # Add function output to messages and yield as StreamChunk
                    function_output_msg = {
                        "type": "function_call_output",
                        "call_id": call["call_id"],
                        "output": str(result),
                    }
                    updated_messages.append(function_output_msg)
                    yield StreamChunk(
                        type="mcp_status",
                        status="function_call_output",
                        content=f"Results for Calling {function_name}: {str(result_obj.content[0].text)}",
                        source=f"mcp_{function_name}",
                    )

                    logger.info(f"Executed MCP function {function_name} (stdio/streamable-http)")
                    processed_call_ids.add(call["call_id"])

                    # Yield MCP tool response status
                    yield StreamChunk(
                        type="mcp_status",
                        status="mcp_tool_response",
                        content=f"✅ [MCP Tool] {function_name} completed",
                        source=f"mcp_{function_name}",
                    )

                    mcp_functions_executed = True

            # Ensure all captured function calls have results to prevent hanging
            for call in captured_function_calls:
                if call["call_id"] not in processed_call_ids:
                    logger.warning(f"Tool call {call['call_id']} for function {call['name']} was not processed - adding error result")

                    # Add missing function call and error result to messages
                    function_call_msg = {
                        "type": "function_call",
                        "call_id": call["call_id"],
                        "name": call["name"],
                        "arguments": call["arguments"],
                    }
                    updated_messages.append(function_call_msg)

                    error_output_msg = {
                        "type": "function_call_output",
                        "call_id": call["call_id"],
                        "output": f"Error: Tool call {call['call_id']} for function {call['name']} was not processed. This may indicate a validation or execution error.",
                    }
                    updated_messages.append(error_output_msg)
                    mcp_functions_executed = True

            # Trim history after function executions to bound memory usage
            if mcp_functions_executed:
                updated_messages = super()._trim_message_history(updated_messages)

                # Recursive call with updated messages
                async for chunk in self._stream_with_mcp_tools(updated_messages, tools, client, **kwargs):
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
            yield StreamChunk(type="done")
            return

    def _convert_mcp_tools_to_openai_format(self) -> List[Dict[str, Any]]:
        """Convert MCP tools (stdio + streamable-http) to OpenAI function declarations."""
        if not self._mcp_functions:
            return []

        converted_tools = []
        for function in self._mcp_functions.values():
            converted_tools.append(function.to_openai_format())

        logger.debug(
            f"Converted {len(converted_tools)} MCP tools (stdio + streamable-http) to OpenAI format",
        )
        return converted_tools

    async def _process_stream(self, stream, all_params, agent_id=None):
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
                backend_name=self.get_provider_name(),
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
                content="\n🧠 [Reasoning Complete]\n",
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
                content="\n📋 [Reasoning Summary Complete]\n",
                reasoning_summary_text=summary_text,
                item_id=getattr(chunk, "item_id", None),
                summary_index=getattr(chunk, "summary_index", None),
            )

        # Provider tool events
        elif chunk_type == "response.web_search_call.in_progress":
            log_stream_chunk("backend.response", "web_search", "Starting search", agent_id)
            return StreamChunk(type="content", content="\n🔍 [Provider Tool: Web Search] Starting search...")
        elif chunk_type == "response.web_search_call.searching":
            log_stream_chunk("backend.response", "web_search", "Searching", agent_id)
            return StreamChunk(type="content", content="\n🔍 [Provider Tool: Web Search] Searching...")
        elif chunk_type == "response.web_search_call.completed":
            log_stream_chunk("backend.response", "web_search", "Search completed", agent_id)
            return StreamChunk(type="content", content="\n✅ [Provider Tool: Web Search] Search completed")

        elif chunk_type == "response.code_interpreter_call.in_progress":
            log_stream_chunk("backend.response", "code_interpreter", "Starting execution", agent_id)
            return StreamChunk(type="content", content="\n💻 [Provider Tool: Code Interpreter] Starting execution...")
        elif chunk_type == "response.code_interpreter_call.executing":
            log_stream_chunk("backend.response", "code_interpreter", "Executing", agent_id)
            return StreamChunk(type="content", content="\n💻 [Provider Tool: Code Interpreter] Executing...")
        elif chunk_type == "response.code_interpreter_call.completed":
            log_stream_chunk("backend.response", "code_interpreter", "Execution completed", agent_id)
            return StreamChunk(type="content", content="\n✅ [Provider Tool: Code Interpreter] Execution completed")
        elif chunk.type == "response.output_item.done":
            # Get search query or executed code details - show them right after completion
            if hasattr(chunk, "item") and chunk.item:
                if hasattr(chunk.item, "type") and chunk.item.type == "web_search_call":
                    if hasattr(chunk.item, "action") and ("query" in chunk.item.action):
                        search_query = chunk.item.action["query"]
                        if search_query:
                            log_stream_chunk("backend.response", "search_query", search_query, agent_id)
                            return StreamChunk(
                                type="content",
                                content=f"\n🔍 [Search Query] '{search_query}'\n",
                            )
                elif hasattr(chunk.item, "type") and chunk.item.type == "code_interpreter_call":
                    if hasattr(chunk.item, "code") and chunk.item.code:
                        # Format code as a proper code block - don't assume language
                        log_stream_chunk("backend.response", "code_executed", chunk.item.code, agent_id)
                        return StreamChunk(
                            type="content",
                            content=f"💻 [Code Executed]\n```\n{chunk.item.code}\n```\n",
                        )

                    # Also show the execution output if available
                    if hasattr(chunk.item, "outputs") and chunk.item.outputs:
                        for output in chunk.item.outputs:
                            output_text = None
                            if hasattr(output, "text") and output.text:
                                output_text = output.text
                            elif hasattr(output, "content") and output.content:
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
                if isinstance(response_dict, dict) and "output" in response_dict:
                    for item in response_dict["output"]:
                        if item.get("type") == "code_interpreter_call":
                            # Code execution result
                            status = item.get("status", "unknown")
                            code = item.get("code", "")
                            outputs = item.get("outputs")
                            content = f"\n🔧 Code Interpreter [{status.title()}]"
                            if code:
                                content += f": {code}"
                            if outputs:
                                content += f" → {outputs}"

                            log_stream_chunk("backend.response", "code_interpreter_result", content, agent_id)
                            return StreamChunk(
                                type="content",
                                content=content,
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
                                    content += f" → Found {len(results)} results"
                                log_stream_chunk("backend.response", "web_search_result", content, agent_id)
                                return StreamChunk(
                                    type="tool",
                                    content=content,
                                )

                # Yield the complete response for internal use
                log_stream_chunk("backend.response", "complete_response", "Response completed", agent_id)
                return StreamChunk(
                    type="complete_response",
                    response=response_dict,
                )

        # Default chunk - this should not happen for valid responses
        return StreamChunk(type="content", content="")

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
        except Exception:
            # Final fallback: extract key attributes manually
            return {key: getattr(obj, key, None) for key in dir(obj) if not key.startswith("_") and not callable(getattr(obj, key, None))}

    def get_provider_name(self) -> str:
        """Get the provider name."""
        return "OpenAI"

    def get_filesystem_support(self) -> FilesystemSupport:
        """OpenAI supports filesystem through MCP servers."""
        return FilesystemSupport.MCP

    def get_supported_builtin_tools(self) -> List[str]:
        """Get list of builtin tools supported by OpenAI."""
        return ["web_search", "code_interpreter"]
