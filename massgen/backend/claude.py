# -*- coding: utf-8 -*-
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

import json
import os
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

import anthropic

from ..logger_config import log_backend_agent_message, log_stream_chunk, logger
from ..mcp_tools.backend_utils import MCPErrorHandler
from .base import FilesystemSupport, StreamChunk
from .base_with_mcp import MCPBackend
from .utils.api_params_handler import ClaudeAPIParamsHandler
from .utils.formatter import ClaudeFormatter


class ClaudeBackend(MCPBackend):
    """Claude backend using Anthropic's Messages API with full multi-tool support."""

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(api_key, **kwargs)
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.search_count = 0  # Track web search usage for pricing
        self.code_session_hours = 0.0  # Track code execution usage
        self.formatter = ClaudeFormatter()
        self.api_params_handler = ClaudeAPIParamsHandler(self)

    async def _stream_with_mcp_tools(
        self,
        current_messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        client,
        **kwargs,
    ) -> AsyncGenerator[StreamChunk, None]:
        """Recursively stream responses, executing MCP function calls when detected."""

        # Build API params for this iteration
        all_params = {**self.config, **kwargs}
        api_params = await self.api_params_handler.build_api_params(current_messages, tools, all_params)

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
                                    content="\n💻 [Code Execution] Starting...\n",
                                )
                            elif tool_name == "web_search":
                                yield StreamChunk(
                                    type="content",
                                    content="\n🔍 [Web Search] Starting search...\n",
                                )
                        elif event.content_block.type == "code_execution_tool_result":
                            result_block = event.content_block
                            result_parts = []
                            if hasattr(result_block, "stdout") and result_block.stdout:
                                result_parts.append(f"Output: {result_block.stdout.strip()}")
                            if hasattr(result_block, "stderr") and result_block.stderr:
                                result_parts.append(f"Error: {result_block.stderr.strip()}")
                            if hasattr(result_block, "return_code") and result_block.return_code != 0:
                                result_parts.append(f"Exit code: {result_block.return_code}")
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
                            log_stream_chunk("backend.claude", "content", text_chunk, agent_id)
                            yield StreamChunk(type="content", content=text_chunk)
                        elif event.delta.type == "input_json_delta":
                            if hasattr(event, "index"):
                                for tool_id, tool_data in current_tool_uses.items():
                                    if tool_data.get("index") == event.index:
                                        partial_json = getattr(event.delta, "partial_json", "")
                                        tool_data["input"] += partial_json
                                        break
                elif event.type == "content_block_stop":
                    if hasattr(event, "index"):
                        for tool_id, tool_data in current_tool_uses.items():
                            if tool_data.get("index") == event.index and tool_data.get("server_side"):
                                tool_name = tool_data.get("name", "")
                                tool_input = tool_data.get("input", "")
                                try:
                                    parsed_input = json.loads(tool_input) if tool_input else {}
                                except json.JSONDecodeError:
                                    parsed_input = {"raw_input": tool_input}
                                if tool_name == "code_execution":
                                    code = parsed_input.get("code", "")
                                    if code:
                                        yield StreamChunk(type="content", content=f"💻 [Code] {code}\n")
                                    yield StreamChunk(
                                        type="content",
                                        content="✅ [Code Execution] Completed\n",
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
                                        content="✅ [Web Search] Completed\n",
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
                                parsed_input = json.loads(tool_input) if tool_input else {}
                            except json.JSONDecodeError:
                                parsed_input = {"raw_input": tool_input}

                            if self.is_mcp_tool_call(tool_name):
                                mcp_tool_calls.append(
                                    {
                                        "id": tool_use["id"],
                                        "type": "function",
                                        "function": {
                                            "name": tool_name,
                                            "arguments": parsed_input,
                                        },
                                    },
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
                                    },
                                )
                    # Emit non-MCP tool calls for the caller to execute
                    if non_mcp_tool_calls:
                        log_stream_chunk("backend.claude", "tool_calls", non_mcp_tool_calls, agent_id)
                        yield StreamChunk(type="tool_calls", tool_calls=non_mcp_tool_calls)
                    response_completed = True
                    break
            except Exception as event_error:
                error_msg = f"Event processing error: {event_error}"
                log_stream_chunk("backend.claude", "error", error_msg, agent_id)
                yield StreamChunk(type="error", error=error_msg)
                continue

        # If we captured MCP tool calls, execute them and recurse
        if response_completed and mcp_tool_calls:
            # Circuit breaker pre-execution check using base class method
            if not await self._check_circuit_breaker_before_execution():
                yield StreamChunk(
                    type="mcp_status",
                    status="mcp_blocked",
                    content="⚠️ [MCP] All servers blocked by circuit breaker",
                    source="circuit_breaker",
                )
                yield StreamChunk(type="done")
                return

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
                    },
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
                    args_json = json.dumps(tool_call["function"]["arguments"]) if isinstance(tool_call["function"].get("arguments"), (dict, list)) else tool_call["function"].get("arguments", "{}")
                    result_list = await self._execute_mcp_function_with_retry(function_name, args_json)
                    if not result_list or (isinstance(result_list[0], str) and result_list[0].startswith("Error:")):
                        logger.warning(f"MCP function {function_name} failed after retries: {result_list[0] if result_list else 'unknown error'}")
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
                        },
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

                logger.info(f"Executed MCP function {function_name} (stdio/streamable-http)")
                yield StreamChunk(
                    type="mcp_status",
                    status="mcp_tool_response",
                    content=f"✅ [MCP Tool] {function_name} completed",
                    source=f"mcp_{function_name}",
                )

            # Trim updated_messages using base class method
            updated_messages = self._trim_message_history(updated_messages)

            # After processing all MCP calls, recurse: async for chunk in self._stream_mcp_recursive(updated_messages, tools, client, **kwargs): yield chunk
            async for chunk in self._stream_with_mcp_tools(updated_messages, tools, client, **kwargs):
                yield chunk
            return
        else:
            # No MCP function calls; finalize this turn
            # Ensure termination with a done chunk when no further tool calls
            complete_message = {
                "role": "assistant",
                "content": content.strip(),
            }
            log_stream_chunk("backend.claude", "complete_message", complete_message, agent_id)
            yield StreamChunk(type="complete_message", complete_message=complete_message)
            yield StreamChunk(
                type="mcp_status",
                status="mcp_session_complete",
                content="✅ [MCP] Session completed",
                source="mcp_session",
            )
            yield StreamChunk(type="done")
            return

    async def _process_stream(
        self,
        stream,
        all_params: Dict[str, Any],
        agent_id: Optional[str],
    ) -> AsyncGenerator[StreamChunk, None]:
        """Process stream events and yield StreamChunks."""
        content_local = ""
        current_tool_uses_local: Dict[str, Dict[str, Any]] = {}

        async for chunk in stream:
            try:
                if chunk.type == "message_start":
                    continue
                elif chunk.type == "content_block_start":
                    if hasattr(chunk, "content_block"):
                        if chunk.content_block.type == "tool_use":
                            tool_id = chunk.content_block.id
                            tool_name = chunk.content_block.name
                            current_tool_uses_local[tool_id] = {
                                "id": tool_id,
                                "name": tool_name,
                                "input": "",
                                "index": getattr(chunk, "index", None),
                            }
                        elif chunk.content_block.type == "server_tool_use":
                            tool_id = chunk.content_block.id
                            tool_name = chunk.content_block.name
                            current_tool_uses_local[tool_id] = {
                                "id": tool_id,
                                "name": tool_name,
                                "input": "",
                                "index": getattr(chunk, "index", None),
                                "server_side": True,
                            }
                            if tool_name == "code_execution":
                                yield StreamChunk(
                                    type="content",
                                    content="\n💻 [Code Execution] Starting...\n",
                                )
                            elif tool_name == "web_search":
                                yield StreamChunk(
                                    type="content",
                                    content="\n🔍 [Web Search] Starting search...\n",
                                )
                        elif chunk.content_block.type == "code_execution_tool_result":
                            result_block = chunk.content_block
                            result_parts = []
                            if hasattr(result_block, "stdout") and result_block.stdout:
                                result_parts.append(f"Output: {result_block.stdout.strip()}")
                            if hasattr(result_block, "stderr") and result_block.stderr:
                                result_parts.append(f"Error: {result_block.stderr.strip()}")
                            if hasattr(result_block, "return_code") and result_block.return_code != 0:
                                result_parts.append(f"Exit code: {result_block.return_code}")
                            if result_parts:
                                result_text = f"\n💻 [Code Execution Result]\n{chr(10).join(result_parts)}\n"
                                yield StreamChunk(
                                    type="content",
                                    content=result_text,
                                )
                elif chunk.type == "content_block_delta":
                    if hasattr(chunk, "delta"):
                        if chunk.delta.type == "text_delta":
                            text_chunk = chunk.delta.text
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
                            yield StreamChunk(type="content", content=text_chunk)
                        elif chunk.delta.type == "input_json_delta":
                            if hasattr(chunk, "index"):
                                for (
                                    tool_id,
                                    tool_data,
                                ) in current_tool_uses_local.items():
                                    if tool_data.get("index") == chunk.index:
                                        partial_json = getattr(
                                            chunk.delta,
                                            "partial_json",
                                            "",
                                        )
                                        tool_data["input"] += partial_json
                                        break
                elif chunk.type == "content_block_stop":
                    if hasattr(chunk, "index"):
                        for (
                            tool_id,
                            tool_data,
                        ) in current_tool_uses_local.items():
                            if tool_data.get("index") == chunk.index and tool_data.get("server_side"):
                                tool_name = tool_data.get("name", "")
                                tool_input = tool_data.get("input", "")
                                try:
                                    parsed_input = json.loads(tool_input) if tool_input else {}
                                except json.JSONDecodeError:
                                    parsed_input = {"raw_input": tool_input}
                                if tool_name == "code_execution":
                                    code = parsed_input.get("code", "")
                                    if code:
                                        yield StreamChunk(
                                            type="content",
                                            content=f"💻 [Code] {code}\n",
                                        )
                                    yield StreamChunk(
                                        type="content",
                                        content="✅ [Code Execution] Completed\n",
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
                                        content="✅ [Web Search] Completed\n",
                                    )
                                tool_data["processed"] = True
                                break
                elif chunk.type == "message_delta":
                    pass
                elif chunk.type == "message_stop":
                    # Build final response and yield tool_calls for user-defined non-MCP tools
                    user_tool_calls = []
                    for tool_use in current_tool_uses_local.values():
                        tool_name = tool_use.get("name", "")
                        is_server_side = tool_use.get("server_side", False)
                        if not is_server_side and tool_name not in ["web_search", "code_execution"]:
                            tool_input = tool_use.get("input", "")
                            try:
                                parsed_input = json.loads(tool_input) if tool_input else {}
                            except json.JSONDecodeError:
                                parsed_input = {"raw_input": tool_input}
                            user_tool_calls.append(
                                {
                                    "id": tool_use["id"],
                                    "type": "function",
                                    "function": {
                                        "name": tool_name,
                                        "arguments": parsed_input,
                                    },
                                },
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
                        complete_message["tool_calls"] = user_tool_calls
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
                    if all_params.get("enable_code_execution", False):
                        self.code_session_hours += 0.083

                    log_stream_chunk("backend.claude", "done", None, agent_id)
                    yield StreamChunk(type="done")
                    return
            except Exception as event_error:
                error_msg = f"Event processing error: {event_error}"
                log_stream_chunk("backend.claude", "error", error_msg, agent_id)
                yield StreamChunk(type="error", error=error_msg)
                continue

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

        logger.warning(f"MCP tool call #{call_index_snapshot} failed - {log_type}: {error}")

        yield StreamChunk(
            type="content",
            content=f"\n⚠️  {user_message} ({error}); continuing without MCP tools\n",
        )

        # Build non-MCP configuration and stream fallback
        fallback_params = dict(api_params)

        # Remove any MCP tools from the tools list
        if "tools" in fallback_params and self._mcp_functions:
            mcp_names = set(self._mcp_functions.keys())
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
        """Execute MCP function with Claude-specific formatting."""
        # Use parent class method which returns tuple
        result_str, result_obj = await super()._execute_mcp_function_with_retry(
            function_name,
            arguments_json,
            max_retries,
        )

        # Convert to list format expected by Claude streaming
        if result_str.startswith("Error:"):
            return [result_str]
        return [result_str, result_obj]

    def create_tool_result_message(self, tool_call: Dict[str, Any], result_content: str) -> Dict[str, Any]:
        """Create tool result message in Claude's expected format."""
        tool_call_id = self.extract_tool_call_id(tool_call)
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call_id,
                    "content": result_content,
                },
            ],
        }

    def extract_tool_result_content(self, tool_result_message: Dict[str, Any]) -> str:
        """Extract content from Claude tool result message."""
        content = tool_result_message.get("content", [])
        if isinstance(content, list) and content:
            for item in content:
                if isinstance(item, dict) and item.get("type") == "tool_result":
                    return item.get("content", "")
        return ""

    def reset_tool_usage(self):
        """Reset tool usage tracking."""
        self.search_count = 0
        self.code_session_hours = 0.0
        super().reset_token_usage()

    def _create_client(self, **kwargs):
        return anthropic.AsyncAnthropic(api_key=self.api_key)

    def get_provider_name(self) -> str:
        """Get the provider name."""
        return "Claude"

    def get_supported_builtin_tools(self) -> List[str]:
        """Get list of builtin tools supported by Claude."""
        return ["web_search", "code_execution"]

    def get_filesystem_support(self) -> FilesystemSupport:
        """Claude supports filesystem through MCP servers."""
        return FilesystemSupport.MCP
