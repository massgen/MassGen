"""
Response API backend implementation.
Standalone implementation optimized for the standard Response API format (originated by OpenAI).
"""
from __future__ import annotations
import os
import json
from typing import Dict, List, Any, AsyncGenerator, Optional
from .mcp_backend import MCPBackend
from .base import StreamChunk, FilesystemSupport
from ..logger_config import (
    log_backend_agent_message,
    log_stream_chunk,
    logger,
)


class ResponseBackend(MCPBackend):
    """Backend using the standard Response API format."""

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        # Call MCPBackend constructor which handles MCP initialization
        super().__init__(api_key, **kwargs)
        # Only set Response API-specific attributes
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")

    def _get_provider_tools(self, kwargs: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get provider tools (web search, code interpreter) if enabled."""
        provider_tools = []
        enable_web_search = kwargs.get("enable_web_search", False)
        enable_code_interpreter = kwargs.get("enable_code_interpreter", False)

        if enable_web_search:
            provider_tools.append({"type": "web_search"})
        if enable_code_interpreter:
            provider_tools.append(
                {"type": "code_interpreter", "container": {"type": "auto"}}
            )
        return provider_tools

    async def _build_api_params(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        kwargs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build OpenAI Response API parameters with MCP integration."""
        # Merge config with kwargs
        all_params = {**self.config, **kwargs}

        # Convert messages to Response API format
        converted_messages = self.message_formatter.to_response_api_format(messages)

        # Response API parameters (uses 'input', not 'messages')
        api_params = {"input": converted_messages, "stream": True}

        # Direct passthrough of all parameters except those handled separately
        excluded_params = self.get_base_excluded_config_params() | {
            # Response API specific exclusions
            "input",
            "enable_web_search",
            "enable_code_interpreter",
            "allowed_tools",  # Tool filtering parameter
            "exclude_tools",  # Tool filtering parameter
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
        if self._mcp_functions:
            mcp_tools = self.mcp_tool_formatter.to_response_api_format(
                self._mcp_functions
            )
            if mcp_tools:
                if "tools" not in api_params:
                    api_params["tools"] = []
                api_params["tools"].extend(mcp_tools)
                logger.info(
                    f"Added {len(mcp_tools)} MCP tools (stdio + streamable-http) to OpenAI Response API"
                )
        # Add provider tools (web search, code interpreter) if enabled
        provider_tools = self._get_provider_tools(all_params)

        if provider_tools:
            if "tools" not in api_params:
                api_params["tools"] = []
            api_params["tools"].extend(provider_tools)

        return api_params

    async def _create_stream(self, api_params: Dict[str, Any]) -> Any:
        """Create backend-specific streaming iterator."""
        import openai
        client = openai.AsyncOpenAI(api_key=self.api_key)
        return await client.responses.create(**api_params)

    def _detect_function_calls(self, chunk, current_call, captured_calls):
        """Detect function calls from Response API chunks."""
        consumed = False
        if hasattr(chunk, "type"):
            if (
                chunk.type == "response.output_item.added"
                and hasattr(chunk, "item")
                and chunk.item
                and getattr(chunk.item, "type", None) == "function_call"
            ):
                current_call = {
                    "call_id": getattr(chunk.item, "call_id", ""),
                    "name": getattr(chunk.item, "name", ""),
                    "arguments": "",
                }
                logger.info(f"Function call detected: {current_call['name']}")
                consumed = True
            elif (
                chunk.type == "response.function_call_arguments.delta"
                and current_call is not None
            ):
                delta = getattr(chunk, "delta", "")
                current_call["arguments"] += delta
                consumed = True
            elif (
                chunk.type == "response.output_item.done"
                and current_call is not None
            ):
                captured_calls.append(current_call)
                current_call = None
                consumed = True
        return current_call, captured_calls, consumed

    def _process_chunk(self, chunk) -> StreamChunk:
        """Process individual stream chunks and convert to StreamChunk format."""
        if not hasattr(chunk, "type"):
            return StreamChunk(type="content", content="")

        chunk_type = chunk.type

        # Handle different chunk types
        if chunk_type == "response.output_text.delta" and hasattr(chunk, "delta"):
            log_backend_agent_message(
                self.agent_id or "default",
                "RECV",
                {"content": chunk.delta},
                backend_name=self.get_provider_name(),
            )
            log_stream_chunk("backend.response", "content", chunk.delta, self.agent_id)
            return StreamChunk(type="content", content=chunk.delta)

        elif chunk_type == "response.reasoning_text.delta" and hasattr(chunk, "delta"):
            log_stream_chunk("backend.response", "reasoning", chunk.delta, self.agent_id)
            return StreamChunk(
                type="reasoning",
                content=f"🧠 [Reasoning] {chunk.delta}",
                reasoning_delta=chunk.delta,
                item_id=getattr(chunk, "item_id", None),
                content_index=getattr(chunk, "content_index", None),
            )

        elif chunk_type == "response.reasoning_text.done":
            reasoning_text = getattr(chunk, "text", "")
            log_stream_chunk(
                "backend.response", "reasoning_done", reasoning_text, self.agent_id
            )
            return StreamChunk(
                type="reasoning_done",
                content=f"\n🧠 [Reasoning Complete]\n",
                reasoning_text=reasoning_text,
                item_id=getattr(chunk, "item_id", None),
                content_index=getattr(chunk, "content_index", None),
            )

        elif chunk_type == "response.reasoning_summary_text.delta" and hasattr(
            chunk, "delta"
        ):
            log_stream_chunk(
                "backend.response", "reasoning_summary", chunk.delta, self.agent_id
            )
            return StreamChunk(
                type="reasoning_summary",
                content=chunk.delta,
                reasoning_summary_delta=chunk.delta,
                item_id=getattr(chunk, "item_id", None),
                summary_index=getattr(chunk, "summary_index", None),
            )

        elif chunk_type == "response.reasoning_summary_text.done":
            summary_text = getattr(chunk, "text", "")
            log_stream_chunk(
                "backend.response", "reasoning_summary_done", summary_text, self.agent_id
            )
            return StreamChunk(
                type="reasoning_summary_done",
                content=f"\n📋 [Reasoning Summary Complete]\n",
                reasoning_summary_text=summary_text,
                item_id=getattr(chunk, "item_id", None),
                summary_index=getattr(chunk, "summary_index", None),
            )

        # Provider tool events
        elif chunk_type == "response.web_search_call.in_progress":
            log_stream_chunk(
                "backend.response", "web_search", "Starting search", self.agent_id
            )
            return StreamChunk(
                type="content",
                content=f"\n🔍 [Provider Tool: Web Search] Starting search...",
            )
        elif chunk_type == "response.web_search_call.searching":
            log_stream_chunk("backend.response", "web_search", "Searching", self.agent_id)
            return StreamChunk(
                type="content", content=f"\n🔍 [Provider Tool: Web Search] Searching..."
            )
        elif chunk_type == "response.web_search_call.completed":
            log_stream_chunk(
                "backend.response", "web_search", "Search completed", self.agent_id
            )
            return StreamChunk(
                type="content",
                content=f"\n✅ [Provider Tool: Web Search] Search completed",
            )

        elif chunk_type == "response.code_interpreter_call.in_progress":
            log_stream_chunk(
                "backend.response", "code_interpreter", "Starting execution", self.agent_id
            )
            return StreamChunk(
                type="content",
                content=f"\n💻 [Provider Tool: Code Interpreter] Starting execution...",
            )
        elif chunk_type == "response.code_interpreter_call.executing":
            log_stream_chunk(
                "backend.response", "code_interpreter", "Executing", self.agent_id
            )
            return StreamChunk(
                type="content",
                content=f"\n💻 [Provider Tool: Code Interpreter] Executing...",
            )
        elif chunk_type == "response.code_interpreter_call.completed":
            log_stream_chunk(
                "backend.response", "code_interpreter", "Execution completed", self.agent_id
            )
            return StreamChunk(
                type="content",
                content=f"\n✅ [Provider Tool: Code Interpreter] Execution completed",
            )
        elif chunk.type == "response.output_item.done":
            # Get search query or executed code details - show them right after completion
            if hasattr(chunk, "item") and chunk.item:
                if hasattr(chunk.item, "type") and chunk.item.type == "web_search_call":
                    if hasattr(chunk.item, "action") and ("query" in chunk.item.action):
                        search_query = chunk.item.action["query"]
                        if search_query:
                            log_stream_chunk(
                                "backend.response",
                                "search_query",
                                search_query,
                                self.agent_id,
                            )
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
                        log_stream_chunk(
                            "backend.response",
                            "code_executed",
                            chunk.item.code,
                            self.agent_id,
                        )
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
                                log_stream_chunk(
                                    "backend.response",
                                    "code_result",
                                    output_text.strip(),
                                    self.agent_id,
                                )
                                return StreamChunk(
                                    type="content",
                                    content=f"📊 [Result] {output_text.strip()}\n",
                                )
        # MCP events
        elif chunk_type == "response.mcp_list_tools.started":
            return StreamChunk(
                type="content", content="\n🔧 [MCP] Listing available tools..."
            )
        elif chunk_type == "response.mcp_list_tools.completed":
            return StreamChunk(
                type="content", content="\n✅ [MCP] Tool listing completed"
            )
        elif chunk_type == "response.mcp_list_tools.failed":
            return StreamChunk(type="content", content="\n❌ [MCP] Tool listing failed")

        elif chunk_type == "response.mcp_call.started":
            tool_name = getattr(chunk, "tool_name", "unknown")
            return StreamChunk(
                type="content", content=f"\n🔧 [MCP] Calling tool '{tool_name}'..."
            )
        elif chunk_type == "response.mcp_call.in_progress":
            return StreamChunk(
                type="content", content="\n⏳ [MCP] Tool execution in progress..."
            )
        elif chunk_type == "response.mcp_call.completed":
            tool_name = getattr(chunk, "tool_name", "unknown")
            return StreamChunk(
                type="content", content=f"\n✅ [MCP] Tool '{tool_name}' completed"
            )
        elif chunk_type == "response.mcp_call.failed":
            tool_name = getattr(chunk, "tool_name", "unknown")
            error_msg = getattr(chunk, "error", "unknown error")
            return StreamChunk(
                type="content",
                content=f"\n❌ [MCP] Tool '{tool_name}' failed: {error_msg}",
            )

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

                            log_stream_chunk(
                                "backend.response",
                                "code_interpreter_result",
                                content,
                                self.agent_id,
                            )
                            return StreamChunk(type="content", content=content)
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
                                log_stream_chunk(
                                    "backend.response",
                                    "web_search_result",
                                    content,
                                    self.agent_id,
                                )
                                return StreamChunk(type="tool", content=content)

                # Yield the complete response for internal use
                log_stream_chunk(
                    "backend.response",
                    "complete_response",
                    "Response completed",
                    self.agent_id,
                )
                return StreamChunk(type="complete_response", response=response_dict)

        # Default chunk - this should not happen for valid responses
        return StreamChunk(type="content", content="")

    def _format_tool_result(self, tool_call, result_content):
        """Format tool result message for Response API."""
        return {
            "type": "function_call_output",
            "call_id": tool_call.get("call_id", ""),
            "output": result_content,
        }

    async def _stream_without_mcp(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream without MCP functionality (fallback mode)."""
        all_params = {**self.config, **kwargs}
        api_params = await self._build_api_params(messages, tools, all_params)

        stream = await self._create_stream(api_params)
        async for chunk in stream:
            processed = self._process_chunk(chunk)
            if processed.type == "complete_response":
                # Yield the complete response first
                yield processed
                # Then signal completion with done chunk
                log_stream_chunk("backend.response", "done", None, self.agent_id)
                yield StreamChunk(type="done")
            else:
                yield processed

    async def stream_with_tools(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """Main streaming entry point with MCP support."""
        async for chunk in self.stream_with_mcp_support(messages, tools, **kwargs):
            yield chunk

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