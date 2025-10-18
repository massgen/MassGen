# -*- coding: utf-8 -*-
"""
Gemini backend implementation using structured output for voting and answer submission.

APPROACH: Uses structured output instead of function declarations to handle the limitation
where Gemini API cannot combine builtin tools with user-defined function declarations.

KEY FEATURES:
- ✅ Structured output for vote and new_answer mechanisms
- ✅ Builtin tools support (code_execution + grounding)
- ✅ Streaming with proper token usage tracking
- ✅ Error handling and response parsing
- ✅ Compatible with MassGen StreamChunk architecture

TECHNICAL SOLUTION:
- Uses Pydantic models to define structured output schemas
- Prompts model to use specific JSON format for voting/ansering
- Converts structured responses to standard tool call format
- Maintains compatibility with existing MassGen workflow
"""

import json
import os
import time
from typing import Any, AsyncGenerator, Dict, List, Optional

from ..api_params_handler._gemini_api_params_handler import GeminiAPIParamsHandler
from ..formatter._gemini_formatter import GeminiFormatter
from ..logger_config import (
    log_backend_activity,
    log_backend_agent_message,
    log_stream_chunk,
    log_tool_call,
    logger,
)
from .base import FilesystemSupport, StreamChunk
from .base_with_custom_tool_and_mcp import CustomToolAndMCPBackend
from .gemini_mcp_manager import GeminiMCPManager
from .gemini_trackers import MCPCallTracker, MCPResponseExtractor, MCPResponseTracker
from .gemini_utils import CoordinationResponse

try:
    from pydantic import BaseModel, Field
except ImportError:
    BaseModel = None
    Field = None

# MCP integration imports
try:
    from ..mcp_tools import (
        MCPClient,
        MCPConfigurationError,
        MCPConfigValidator,
        MCPConnectionError,
        MCPError,
        MCPServerError,
        MCPTimeoutError,
        MCPValidationError,
    )
except ImportError:  # MCP not installed or import failed within mcp_tools
    MCPClient = None  # type: ignore[assignment]
    MCPError = ImportError  # type: ignore[assignment]
    MCPConnectionError = ImportError  # type: ignore[assignment]
    MCPConfigValidator = None  # type: ignore[assignment]
    MCPConfigurationError = ImportError  # type: ignore[assignment]
    MCPValidationError = ImportError  # type: ignore[assignment]
    MCPTimeoutError = ImportError  # type: ignore[assignment]
    MCPServerError = ImportError  # type: ignore[assignment]

# Import MCP backend utilities
try:
    from ..mcp_tools.backend_utils import (
        MCPCircuitBreakerManager,
        MCPConfigHelper,
        MCPErrorHandler,
        MCPExecutionManager,
        MCPMessageManager,
        MCPSetupManager,
    )
except ImportError:
    MCPErrorHandler = None  # type: ignore[assignment]
    MCPSetupManager = None  # type: ignore[assignment]
    MCPMessageManager = None  # type: ignore[assignment]
    MCPCircuitBreakerManager = None  # type: ignore[assignment]
    MCPExecutionManager = None  # type: ignore[assignment]
    MCPConfigHelper = None  # type: ignore[assignment]


class GeminiBackend(CustomToolAndMCPBackend):
    """Google Gemini backend using structured output for coordination and MCP tool integration."""

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        # Store Gemini-specific API key before calling parent init
        gemini_api_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

        # Call parent class __init__ - this initializes custom_tool_manager and MCP-related attributes
        super().__init__(gemini_api_key, **kwargs)

        # Override API key with Gemini-specific value
        self.api_key = gemini_api_key

        # Gemini-specific counters for builtin tools
        self.search_count = 0
        self.code_execution_count = 0

        # New components for separation of concerns
        self.formatter = GeminiFormatter()
        self.api_params_handler = GeminiAPIParamsHandler(self)

        # Gemini-specific MCP monitoring (additional to parent class)
        self._mcp_tool_successes = 0
        self._mcp_connection_retries = 0

        # MCP Response Extractor for capturing tool interactions (Gemini-specific)
        self.mcp_extractor = MCPResponseExtractor()

        # Initialize Gemini MCP manager after all attributes are ready
        self.mcp_manager = GeminiMCPManager(self)

    def _setup_permission_hooks(self):
        """Override base class - Gemini uses session-based permissions, not function hooks."""
        logger.debug("[Gemini] Using session-based permissions, skipping function hook setup")

    async def _process_stream(self, stream, all_params, agent_id: Optional[str] = None) -> AsyncGenerator[StreamChunk, None]:
        """
        Required by CustomToolAndMCPBackend abstract method.
        Not used by Gemini - Gemini SDK handles streaming directly in stream_with_tools().
        """
        if False:
            yield  # Make this an async generator
        raise NotImplementedError("Gemini uses custom streaming logic in stream_with_tools()")

    async def _setup_mcp_tools(self) -> None:
        """
        Override parent class - Gemini uses GeminiMCPManager for MCP setup.
        This method is called by the parent class's __aenter__() context manager.
        """
        await self.mcp_manager.setup_mcp_tools(agent_id=self.agent_id)

    def supports_upload_files(self) -> bool:
        """
        Override parent class - Gemini does not support upload_files preprocessing.
        Returns False to skip upload_files processing in parent class methods.
        """
        return False

    async def stream_with_tools(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], **kwargs) -> AsyncGenerator[StreamChunk, None]:
        """Stream response using Gemini API with structured output for coordination and MCP tool support."""
        # Use instance agent_id (from __init__) or get from kwargs if not set
        agent_id = self.agent_id or kwargs.get("agent_id", None)
        client = None
        stream = None

        log_backend_activity(
            "gemini",
            "Starting stream_with_tools",
            {"num_messages": len(messages), "num_tools": len(tools) if tools else 0},
            agent_id=agent_id,
        )

        # Only trim when MCP tools will be used
        if self.mcp_servers and MCPMessageManager is not None and hasattr(self, "_max_mcp_message_history") and self._max_mcp_message_history > 0:
            original_count = len(messages)
            messages = MCPMessageManager.trim_message_history(messages, self._max_mcp_message_history)
            if len(messages) < original_count:
                log_backend_activity(
                    "gemini",
                    "Trimmed MCP message history",
                    {
                        "original": original_count,
                        "trimmed": len(messages),
                        "limit": self._max_mcp_message_history,
                    },
                    agent_id=agent_id,
                )

        try:
            from google import genai

            # Setup MCP with status streaming via manager if not already initialized
            if not self._mcp_initialized and self.mcp_servers:
                async for chunk in self.mcp_manager.setup_mcp_with_status_stream(agent_id):
                    yield chunk
            elif not self._mcp_initialized:
                # Setup MCP without streaming for backward compatibility
                await self.mcp_manager.setup_mcp_tools(agent_id)

            # Merge constructor config with stream kwargs (stream kwargs take priority)
            all_params = {**self.config, **kwargs}

            # Extract framework-specific parameters
            all_params.get("enable_web_search", False)
            enable_code_execution = all_params.get("enable_code_execution", False)

            # Always use SDK MCP sessions when mcp_servers are configured
            using_sdk_mcp = bool(self.mcp_servers)

            # Custom tool handling - add custom tools if any
            using_custom_tools = bool(self.custom_tool_manager and len(self._custom_tool_names) > 0)

            # Analyze tool types
            is_coordination = self.formatter.has_coordination_tools(tools)

            valid_agent_ids = None

            if is_coordination:
                # Extract valid agent IDs from vote tool enum if available
                for tool in tools:
                    if tool.get("type") == "function":
                        func_def = tool.get("function", {})
                        if func_def.get("name") == "vote":
                            agent_id_param = func_def.get("parameters", {}).get("properties", {}).get("agent_id", {})
                            if "enum" in agent_id_param:
                                valid_agent_ids = agent_id_param["enum"]
                            break

            # Build content string from messages using formatter
            full_content = self.formatter.format_messages(messages)
            # For coordination requests, modify the prompt to use structured output
            if is_coordination:
                full_content = self.formatter.build_structured_output_prompt(full_content, valid_agent_ids)


            # Use google-genai package
            client = genai.Client(api_key=self.api_key)

            # Setup builtin tools via API params handler (SDK Tool objects)
            builtin_tools = self.api_params_handler.get_provider_tools(all_params)
            # Build config via API params handler (maps params, excludes backend-managed ones)
            config = await self.api_params_handler.build_api_params(messages, tools, all_params)
            # Extract model name (not included in config)
            model_name = all_params.get("model")

            # Setup tools configuration (builtins only when not using sessions)
            all_tools = []

            # Branch 1: SDK auto-calling via MCP sessions (reuse existing MCPClient sessions)
            if using_sdk_mcp and self.mcp_servers:
                if not self._mcp_client or not getattr(self._mcp_client, "is_connected", lambda: False)():
                    mcp_connected, status_chunks = await self.mcp_manager.setup_mcp_sessions_with_retry(agent_id, max_retries=5)
                    async for chunk in status_chunks:
                        yield chunk
                    if not mcp_connected:
                        using_sdk_mcp = False
                        self._mcp_client = None

            if not using_sdk_mcp and not using_custom_tools:
                all_tools.extend(builtin_tools)
                if all_tools:
                    config["tools"] = all_tools

            # For coordination requests, use JSON response format (may conflict with tools/sessions)
            if is_coordination:
                # Only request JSON schema when no tools are present
                if (not using_sdk_mcp) and (not using_custom_tools) and (not all_tools):
                    config["response_mime_type"] = "application/json"
                    config["response_schema"] = CoordinationResponse.model_json_schema()
                else:
                    # Tools or sessions are present; fallback to text parsing
                    pass
            # Log messages being sent after builtin_tools is defined
            log_backend_agent_message(
                agent_id or "default",
                "SEND",
                {
                    "content": full_content,
                    "builtin_tools": len(builtin_tools) if builtin_tools else 0,
                },
                backend_name="gemini",
            )

            # Use streaming for real-time response
            full_content_text = ""
            final_response = None
            # Buffer the last response chunk that contains candidate metadata so we can
            # inspect builtin tool usage (grounding/code execution) after streaming
            last_response_with_candidates = None
            if (using_sdk_mcp and self.mcp_servers) or using_custom_tools:
                # Process MCP and/or custom tools
                try:
                    # ====================================================================
                    # Preparation phase: Initialize MCP and custom tools
                    # ====================================================================
                    mcp_sessions = []
                    mcp_error = None
                    custom_tools_functions = []
                    custom_tools_error = None

                    # Try to initialize MCP sessions
                    if using_sdk_mcp and self.mcp_servers:
                        try:
                            if not self._mcp_client:
                                raise RuntimeError("MCP client not initialized")
                            mcp_sessions = self.mcp_manager.get_active_mcp_sessions(
                                convert_to_permission_sessions=bool(self.filesystem_manager)
                            )
                            if not mcp_sessions:
                                # If no MCP sessions, record error but don't interrupt (may still have custom tools)
                                mcp_error = RuntimeError("No active MCP sessions available")
                                logger.warning(f"[Gemini] MCP sessions unavailable: {mcp_error}")
                        except Exception as e:
                            mcp_error = e
                            logger.warning(f"[Gemini] Failed to initialize MCP sessions: {e}")

                    # Try to initialize custom tools
                    if using_custom_tools:
                        try:
                            # Get custom tools schemas (in OpenAI format)
                            custom_tools_schemas = self._get_custom_tools_schemas()
                            if custom_tools_schemas:
                                # Convert to Gemini SDK format using formatter
                                # formatter handles: OpenAI format -> Gemini dict -> FunctionDeclaration objects
                                custom_tools_functions = self.formatter.format_custom_tools(
                                    custom_tools_schemas,
                                    return_sdk_objects=True
                                )

                                if custom_tools_functions:
                                    logger.debug(
                                        f"[Gemini] Loaded {len(custom_tools_functions)} custom tools "
                                        f"as FunctionDeclarations"
                                    )
                                else:
                                    custom_tools_error = RuntimeError("Custom tools conversion failed")
                                    logger.warning(f"[Gemini] Custom tools unavailable: {custom_tools_error}")
                            else:
                                custom_tools_error = RuntimeError("No custom tools available")
                                logger.warning(f"[Gemini] Custom tools unavailable: {custom_tools_error}")
                        except Exception as e:
                            custom_tools_error = e
                            logger.warning(f"[Gemini] Failed to initialize custom tools: {e}")

                    # Check if at least one tool system is available
                    has_mcp = bool(mcp_sessions and not mcp_error)
                    has_custom_tools = bool(custom_tools_functions and not custom_tools_error)

                    if not has_mcp and not has_custom_tools:
                        # Both failed, raise error to enter fallback
                        raise RuntimeError(
                            f"Both MCP and custom tools unavailable. "
                            f"MCP error: {mcp_error}. Custom tools error: {custom_tools_error}"
                        )

                    # ====================================================================
                    # Configuration phase: Build session_config
                    # ====================================================================
                    session_config = dict(config)

                    # Collect all available tool information
                    available_mcp_tools = []
                    if has_mcp and self._mcp_client:
                        available_mcp_tools = list(self._mcp_client.tools.keys())

                    available_custom_tool_names = list(self._custom_tool_names) if has_custom_tools else []

                    # Apply tools to config
                    tools_to_apply = []
                    sessions_applied = False
                    custom_tools_applied = False

                    # Add MCP sessions (if available and not blocked by planning mode)
                    if has_mcp:
                        if not self.mcp_manager.should_block_mcp_tools_in_planning_mode(
                            self.is_planning_mode_enabled(), available_mcp_tools
                        ):
                            logger.debug(
                                f"[Gemini] Passing {len(mcp_sessions)} MCP sessions to SDK: "
                                f"{[type(s).__name__ for s in mcp_sessions]}"
                            )
                            tools_to_apply.extend(mcp_sessions)
                            sessions_applied = True

                    # Add custom tools (if available)
                    if has_custom_tools:
                        # Note: This assumes custom_tools_functions is already in Gemini-compatible format
                        # If not, format conversion is needed here
                        logger.debug(f"[Gemini] Passing {len(custom_tools_functions)} custom tools to SDK")
                        tools_to_apply.extend(custom_tools_functions)
                        custom_tools_applied = True

                    # Apply tool configuration
                    if tools_to_apply:
                        session_config["tools"] = tools_to_apply

                    # ====================================================================
                    # Logging and status output
                    # ====================================================================
                    if sessions_applied:
                        # Track MCP tool usage attempt
                        self._mcp_tool_calls_count += 1

                        log_backend_activity(
                            "gemini",
                            "MCP tool call initiated",
                            {
                                "call_number": self._mcp_tool_calls_count,
                                "session_count": len(mcp_sessions),
                                "available_tools": available_mcp_tools[:],
                                "total_tools": len(available_mcp_tools),
                            },
                            agent_id=agent_id,
                        )

                        log_tool_call(
                            agent_id,
                            "mcp_session_tools",
                            {
                                "session_count": len(mcp_sessions),
                                "call_number": self._mcp_tool_calls_count,
                                "available_tools": available_mcp_tools,
                            },
                            backend_name="gemini",
                        )

                        tools_info = f" ({len(available_mcp_tools)} tools available)" if available_mcp_tools else ""
                        yield StreamChunk(
                            type="mcp_status",
                            status="mcp_tools_initiated",
                            content=f"MCP tool call initiated (call #{self._mcp_tool_calls_count}){tools_info}: {', '.join(available_mcp_tools[:5])}{'...' if len(available_mcp_tools) > 5 else ''}",
                            source="mcp_tools",
                        )

                    if custom_tools_applied:
                        # Track custom tool usage attempt
                        log_backend_activity(
                            "gemini",
                            "Custom tools initiated",
                            {
                                "tool_count": len(custom_tools_functions),
                                "available_tools": available_custom_tool_names,
                            },
                            agent_id=agent_id,
                        )

                        yield StreamChunk(
                            type="custom_tool_status",
                            status="custom_tools_initiated",
                            content=f"Custom tools initiated ({len(custom_tools_functions)} tools available): {', '.join(available_custom_tool_names[:5])}{'...' if len(available_custom_tool_names) > 5 else ''}",
                            source="custom_tools",
                        )

                    # ====================================================================
                    # Streaming phase
                    # ====================================================================
                    # Use async streaming call with sessions/tools
                    stream = await client.aio.models.generate_content_stream(
                        model=model_name, contents=full_content, config=session_config
                    )

                    # Initialize trackers for both MCP and custom tools
                    mcp_tracker = MCPCallTracker()
                    mcp_response_tracker = MCPResponseTracker()
                    custom_tracker = MCPCallTracker()  # Reuse MCPCallTracker for custom tools
                    custom_response_tracker = MCPResponseTracker()  # Reuse for custom tools

                    mcp_tools_used = []  # Keep for backward compatibility
                    custom_tools_used = []  # Track custom tool usage

                    # Iterate over the asynchronous stream to get chunks as they arrive
                    async for chunk in stream:
                        print(chunk)
                        # ============================================
                        # 1. Process function calls/responses
                        # ============================================
                        if hasattr(chunk, "automatic_function_calling_history") and chunk.automatic_function_calling_history:
                            for history_item in chunk.automatic_function_calling_history:
                                if hasattr(history_item, "parts") and history_item.parts is not None:
                                    for part in history_item.parts:
                                        # Check for function_call part
                                        if hasattr(part, "function_call") and part.function_call:
                                            # Use MCPResponseExtractor to extract call data
                                            call_data = self.mcp_extractor.extract_function_call(part.function_call)

                                            if call_data:
                                                tool_name = call_data["name"]
                                                tool_args = call_data["arguments"]

                                                # Determine if it's MCP tool or custom tool
                                                is_mcp_tool = has_mcp and tool_name in available_mcp_tools
                                                is_custom_tool = has_custom_tools and tool_name in self._custom_tool_names

                                                if is_mcp_tool:
                                                    # Process MCP tool call
                                                    if mcp_tracker.is_new_call(tool_name, tool_args):
                                                        call_record = mcp_tracker.add_call(tool_name, tool_args)

                                                        mcp_tools_used.append(
                                                            {
                                                                "name": tool_name,
                                                                "arguments": tool_args,
                                                                "timestamp": call_record["timestamp"],
                                                            },
                                                        )

                                                        timestamp_str = time.strftime(
                                                            "%H:%M:%S",
                                                            time.localtime(call_record["timestamp"]),
                                                        )

                                                        yield StreamChunk(
                                                            type="mcp_status",
                                                            status="mcp_tool_called",
                                                            content=f"🔧 MCP Tool Called: {tool_name} at {timestamp_str} with args: {json.dumps(tool_args, indent=2)}",
                                                            source="mcp_tools",
                                                        )

                                                        log_tool_call(
                                                            agent_id,
                                                            tool_name,
                                                            tool_args,
                                                            backend_name="gemini",
                                                        )

                                                elif is_custom_tool:
                                                    # Process custom tool call
                                                    if custom_tracker.is_new_call(tool_name, tool_args):
                                                        call_record = custom_tracker.add_call(tool_name, tool_args)

                                                        custom_tools_used.append(
                                                            {
                                                                "name": tool_name,
                                                                "arguments": tool_args,
                                                                "timestamp": call_record["timestamp"],
                                                            },
                                                        )

                                                        timestamp_str = time.strftime(
                                                            "%H:%M:%S",
                                                            time.localtime(call_record["timestamp"]),
                                                        )

                                                        yield StreamChunk(
                                                            type="custom_tool_status",
                                                            status="custom_tool_called",
                                                            content=f"🔧 Custom Tool Called: {tool_name} at {timestamp_str} with args: {json.dumps(tool_args, indent=2)}",
                                                            source="custom_tools",
                                                        )

                                                        log_tool_call(
                                                            agent_id,
                                                            tool_name,
                                                            tool_args,
                                                            backend_name="gemini",
                                                        )

                                        # Check for function_response part
                                        elif hasattr(part, "function_response") and part.function_response:
                                            response_data = self.mcp_extractor.extract_function_response(part.function_response)

                                            if response_data:
                                                tool_name = response_data["name"]
                                                tool_response = response_data["response"]

                                                # Determine if it's MCP tool or custom tool
                                                is_mcp_tool = has_mcp and tool_name in available_mcp_tools
                                                is_custom_tool = has_custom_tools and tool_name in self._custom_tool_names

                                                if is_mcp_tool:
                                                    # Process MCP tool response
                                                    if mcp_response_tracker.is_new_response(tool_name, tool_response):
                                                        response_record = mcp_response_tracker.add_response(tool_name, tool_response)

                                                        # Extract text content from CallToolResult
                                                        response_text = None
                                                        if isinstance(tool_response, dict) and "result" in tool_response:
                                                            result = tool_response["result"]
                                                            if hasattr(result, "content") and result.content:
                                                                first_content = result.content[0]
                                                                if hasattr(first_content, "text"):
                                                                    response_text = first_content.text

                                                        if response_text is None:
                                                            response_text = str(tool_response)

                                                        timestamp_str = time.strftime(
                                                            "%H:%M:%S",
                                                            time.localtime(response_record["timestamp"]),
                                                        )

                                                        yield StreamChunk(
                                                            type="mcp_status",
                                                            status="mcp_tool_response",
                                                            content=f"✅ MCP Tool Response from {tool_name} at {timestamp_str}: {response_text}",
                                                            source="mcp_tools",
                                                        )

                                                        log_backend_activity(
                                                            "gemini",
                                                            "MCP tool response received",
                                                            {
                                                                "tool_name": tool_name,
                                                                "response_preview": str(tool_response)[:],
                                                            },
                                                            agent_id=agent_id,
                                                        )

                                                elif is_custom_tool:
                                                    # Process custom tool response
                                                    if custom_response_tracker.is_new_response(tool_name, tool_response):
                                                        response_record = custom_response_tracker.add_response(tool_name, tool_response)

                                                        # Extract text from response
                                                        response_text = str(tool_response)

                                                        timestamp_str = time.strftime(
                                                            "%H:%M:%S",
                                                            time.localtime(response_record["timestamp"]),
                                                        )

                                                        yield StreamChunk(
                                                            type="custom_tool_status",
                                                            status="custom_tool_response",
                                                            content=f"✅ Custom Tool Response from {tool_name} at {timestamp_str}: {response_text}",
                                                            source="custom_tools",
                                                        )

                                                        log_backend_activity(
                                                            "gemini",
                                                            "Custom tool response received",
                                                            {
                                                                "tool_name": tool_name,
                                                                "response_preview": str(tool_response)[:200],
                                                            },
                                                            agent_id=agent_id,
                                                        )

                        # ============================================
                        # 2. Process text content
                        # ============================================
                        if hasattr(chunk, "text") and chunk.text:
                            chunk_text = chunk.text
                            full_content_text += chunk_text
                            log_backend_agent_message(
                                agent_id,
                                "RECV",
                                {"content": chunk_text},
                                backend_name="gemini",
                            )
                            log_stream_chunk("backend.gemini", "content", chunk_text, agent_id)
                            yield StreamChunk(type="content", content=chunk_text)

                        # ============================================
                        # 3. Buffer last chunk with candidates
                        # ============================================
                        if hasattr(chunk, "candidates") and chunk.candidates:
                            last_response_with_candidates = chunk

                    # Reset stream tracking
                    if hasattr(self, "_mcp_stream_started"):
                        delattr(self, "_mcp_stream_started")

                    # ====================================================================
                    # Completion phase: Output summary
                    # ====================================================================

                    # Add MCP usage indicator with detailed summary
                    if has_mcp:
                        mcp_summary = mcp_tracker.get_summary()
                        if not mcp_summary or mcp_summary == "No MCP tools called":
                            mcp_summary = "MCP session completed (no tools explicitly called)"
                        else:
                            mcp_summary = f"MCP session complete - {mcp_summary}"

                        log_stream_chunk("backend.gemini", "mcp_indicator", mcp_summary, agent_id)
                        yield StreamChunk(
                            type="mcp_status",
                            status="mcp_session_complete",
                            content=mcp_summary,
                            source="mcp_tools",
                        )

                    # Add custom tool usage indicator with detailed summary
                    if has_custom_tools:
                        custom_summary = custom_tracker.get_summary()
                        if not custom_summary or custom_summary == "No MCP tools called":
                            custom_summary = "Custom tools session completed (no tools explicitly called)"
                        else:
                            # Replace "MCP tool" with "Custom tool"
                            custom_summary = custom_summary.replace("MCP tool", "Custom tool")
                            custom_summary = f"Custom tools session complete - {custom_summary}"

                        log_stream_chunk("backend.gemini", "custom_tools_indicator", custom_summary, agent_id)
                        yield StreamChunk(
                            type="custom_tool_status",
                            status="custom_tools_session_complete",
                            content=custom_summary,
                            source="custom_tools",
                        )

                except (
                    MCPConnectionError,
                    MCPTimeoutError,
                    MCPServerError,
                    MCPError,
                    Exception,
                ) as e:
                    log_stream_chunk("backend.gemini", "tools_error", str(e), agent_id)

                    # ====================================================================
                    # Error handling: Distinguish MCP and custom tools errors
                    # ====================================================================

                    # Determine error type
                    is_mcp_error = isinstance(e, (MCPConnectionError, MCPTimeoutError, MCPServerError, MCPError))
                    is_custom_tool_error = not is_mcp_error and using_custom_tools

                    # Emit user-friendly error message
                    if is_mcp_error:
                        async for chunk in self.mcp_manager.handle_mcp_error_and_fallback(e):
                            yield chunk
                    elif is_custom_tool_error:
                        yield StreamChunk(
                            type="custom_tool_status",
                            status="custom_tools_error",
                            content=f"⚠️ [Custom Tools] Error: {str(e)}; falling back to non-custom-tool mode",
                            source="custom_tools",
                        )
                    else:
                        yield StreamChunk(
                            type="mcp_status",
                            status="tools_error",
                            content=f"⚠️ [Tools] Error: {str(e)}; falling back",
                            source="tools",
                        )

                    # Fallback configuration
                    manual_config = dict(config)

                    # Decide fallback configuration based on error type
                    if is_mcp_error and using_custom_tools:
                        # MCP error but custom tools available: exclude MCP, keep custom tools
                        try:
                            custom_tools_schemas = self._get_custom_tools_schemas()
                            if custom_tools_schemas:
                                # Convert to Gemini format using formatter
                                custom_tools_functions = self.formatter.format_custom_tools(
                                    custom_tools_schemas,
                                    return_sdk_objects=True
                                )
                                manual_config["tools"] = custom_tools_functions
                                logger.info("[Gemini] Fallback: using custom tools only (MCP failed)")
                            else:
                                # Custom tools also unavailable, use builtin tools
                                if all_tools:
                                    manual_config["tools"] = all_tools
                                logger.info("[Gemini] Fallback: using builtin tools only (both MCP and custom tools failed)")
                        except Exception:
                            if all_tools:
                                manual_config["tools"] = all_tools
                            logger.info("[Gemini] Fallback: using builtin tools only (custom tools also failed)")

                    elif is_custom_tool_error and using_sdk_mcp:
                        # Custom tools error but MCP available: exclude custom tools, keep MCP
                        try:
                            if self._mcp_client:
                                mcp_sessions = self.mcp_manager.get_active_mcp_sessions(
                                    convert_to_permission_sessions=bool(self.filesystem_manager)
                                )
                                if mcp_sessions:
                                    manual_config["tools"] = mcp_sessions
                                    logger.info("[Gemini] Fallback: using MCP only (custom tools failed)")
                                else:
                                    if all_tools:
                                        manual_config["tools"] = all_tools
                                    logger.info("[Gemini] Fallback: using builtin tools only (both custom tools and MCP failed)")
                        except Exception:
                            if all_tools:
                                manual_config["tools"] = all_tools
                            logger.info("[Gemini] Fallback: using builtin tools only (MCP also failed)")

                    else:
                        # Both failed or cannot determine: use builtin tools
                        if all_tools:
                            manual_config["tools"] = all_tools
                        logger.info("[Gemini] Fallback: using builtin tools only (all advanced tools failed)")

                    # Create new stream for fallback
                    stream = await client.aio.models.generate_content_stream(
                        model=model_name, contents=full_content, config=manual_config
                    )

                    async for chunk in stream:
                        # Process text content
                        if hasattr(chunk, "text") and chunk.text:
                            chunk_text = chunk.text
                            full_content_text += chunk_text
                            log_stream_chunk(
                                "backend.gemini",
                                "fallback_content",
                                chunk_text,
                                agent_id,
                            )
                            yield StreamChunk(type="content", content=chunk_text)
                        # Buffer last chunk with candidates for fallback path
                        if hasattr(chunk, "candidates") and chunk.candidates:
                            last_response_with_candidates = chunk
            else:
                # Non-MCP streaming path: execute when MCP is disabled
                try:
                    # Use the standard config (with builtin tools if configured)
                    stream = await client.aio.models.generate_content_stream(
                        model=model_name,
                        contents=full_content,
                        config=config,
                    )

                    # Process streaming chunks
                    async for chunk in stream:
                        # Process text content
                        if hasattr(chunk, "text") and chunk.text:
                            chunk_text = chunk.text
                            full_content_text += chunk_text
                            log_backend_agent_message(
                                agent_id,
                                "RECV",
                                {"content": chunk_text},
                                backend_name="gemini",
                            )
                            log_stream_chunk("backend.gemini", "content", chunk_text, agent_id)
                            yield StreamChunk(type="content", content=chunk_text)
                        # Buffer last chunk with candidates for non-MCP path
                        if hasattr(chunk, "candidates") and chunk.candidates:
                            last_response_with_candidates = chunk

                except Exception as e:
                    error_msg = f"Non-MCP streaming error: {e}"
                    log_stream_chunk(
                        "backend.gemini",
                        "non_mcp_stream_error",
                        {"error_type": type(e).__name__, "error_message": str(e)},
                        agent_id,
                    )
                    yield StreamChunk(type="error", error=error_msg)

            content = full_content_text

            # Process tool calls - only coordination tool calls (MCP manual mode removed)
            tool_calls_detected: List[Dict[str, Any]] = []

            # Then, process coordination tools if present
            if is_coordination and content.strip() and not tool_calls_detected:
                # For structured output mode, the entire content is JSON
                structured_response = None
                # Try multiple parsing strategies
                try:
                    # Strategy 1: Parse entire content as JSON (works for both modes)
                    structured_response = json.loads(content.strip())
                except json.JSONDecodeError:
                    # Strategy 2: Extract JSON from mixed text content (handles markdown-wrapped JSON)
                    structured_response = self.formatter.extract_structured_response(content)

                if structured_response and isinstance(structured_response, dict) and "action_type" in structured_response:
                    # Convert to tool calls
                    tool_calls = self.formatter.convert_structured_to_tool_calls(structured_response)
                    if tool_calls:
                        tool_calls_detected = tool_calls
                        # Log conversion to tool calls (summary)
                        log_stream_chunk("backend.gemini", "tool_calls", tool_calls, agent_id)

                        # Log each coordination tool call for analytics/debugging
                        try:
                            for tool_call in tool_calls:
                                log_tool_call(
                                    agent_id,
                                    tool_call.get("function", {}).get("name", "unknown_coordination_tool"),
                                    tool_call.get("function", {}).get("arguments", {}),
                                    result="coordination_tool_called",
                                    backend_name="gemini",
                                )
                        except Exception:
                            # Ensure logging does not interrupt flow
                            pass

            # Assign buffered final response (if available) so builtin tool indicators can be emitted
            if last_response_with_candidates is not None:
                final_response = last_response_with_candidates

            # Process builtin tool results if any tools were used
            if builtin_tools and final_response and hasattr(final_response, "candidates") and final_response.candidates:
                # Check for grounding or code execution results
                candidate = final_response.candidates[0]

                # Check for web search results - only show if actually used
                if hasattr(candidate, "grounding_metadata") and candidate.grounding_metadata:
                    # Check if web search was actually used by looking for queries or chunks
                    search_actually_used = False
                    search_queries = []

                    # Look for web search queries
                    if hasattr(candidate.grounding_metadata, "web_search_queries") and candidate.grounding_metadata.web_search_queries:
                        try:
                            for query in candidate.grounding_metadata.web_search_queries:
                                if query and query.strip():
                                    search_queries.append(query.strip())
                                    search_actually_used = True
                        except (TypeError, AttributeError):
                            pass

                    # Look for grounding chunks (indicates actual search results)
                    if hasattr(candidate.grounding_metadata, "grounding_chunks") and candidate.grounding_metadata.grounding_chunks:
                        try:
                            if len(candidate.grounding_metadata.grounding_chunks) > 0:
                                search_actually_used = True
                        except (TypeError, AttributeError):
                            pass

                    # Only show indicators if search was actually used
                    if search_actually_used:
                        # Enhanced web search logging
                        log_stream_chunk(
                            "backend.gemini",
                            "web_search_result",
                            {"queries": search_queries, "results_integrated": True},
                            agent_id,
                        )
                        log_tool_call(
                            agent_id,
                            "google_search_retrieval",
                            {
                                "queries": search_queries,
                                "chunks_found": len(candidate.grounding_metadata.grounding_chunks) if hasattr(candidate.grounding_metadata, "grounding_chunks") else 0,
                            },
                            result="search_completed",
                            backend_name="gemini",
                        )
                        yield StreamChunk(
                            type="content",
                            content="🔍 [Builtin Tool: Web Search] Results integrated\n",
                        )

                        # Show search queries
                        for query in search_queries:
                            log_stream_chunk(
                                "backend.gemini",
                                "web_search_result",
                                {"queries": search_queries, "results_integrated": True},
                                agent_id,
                            )
                            yield StreamChunk(type="content", content=f"🔍 [Search Query] '{query}'\n")

                        self.search_count += 1

                # Check for code execution in the response parts
                if enable_code_execution and hasattr(candidate, "content") and hasattr(candidate.content, "parts"):
                    # Look for executable_code and code_execution_result parts
                    code_parts = []
                    for part in candidate.content.parts:
                        if hasattr(part, "executable_code") and part.executable_code:
                            code_content = getattr(part.executable_code, "code", str(part.executable_code))
                            code_parts.append(f"Code: {code_content}")
                        elif hasattr(part, "code_execution_result") and part.code_execution_result:
                            result_content = getattr(
                                part.code_execution_result,
                                "output",
                                str(part.code_execution_result),
                            )
                            code_parts.append(f"Result: {result_content}")

                    if code_parts:
                        # Code execution was actually used
                        log_stream_chunk(
                            "backend.gemini",
                            "code_execution",
                            "Code executed",
                            agent_id,
                        )

                        # Log code execution as a tool call event
                        try:
                            log_tool_call(
                                agent_id,
                                "code_execution",
                                {"code_parts_count": len(code_parts)},
                                result="code_executed",
                                backend_name="gemini",
                            )
                        except Exception:
                            pass

                        yield StreamChunk(
                            type="content",
                            content="💻 [Builtin Tool: Code Execution] Code executed\n",
                        )
                        # Also show the actual code and result
                        for part in code_parts:
                            if part.startswith("Code: "):
                                code_content = part[6:]  # Remove "Code: " prefix
                                log_stream_chunk(
                                    "backend.gemini",
                                    "code_execution_result",
                                    {
                                        "code_parts": len(code_parts),
                                        "execution_successful": True,
                                        "snippet": code_content,
                                    },
                                    agent_id,
                                )
                                yield StreamChunk(
                                    type="content",
                                    content=f"💻 [Code Executed]\n```python\n{code_content}\n```\n",
                                )
                            elif part.startswith("Result: "):
                                result_content = part[8:]  # Remove "Result: " prefix
                                log_stream_chunk(
                                    "backend.gemini",
                                    "code_execution_result",
                                    {
                                        "code_parts": len(code_parts),
                                        "execution_successful": True,
                                        "result": result_content,
                                    },
                                    agent_id,
                                )
                                yield StreamChunk(
                                    type="content",
                                    content=f"📊 [Result] {result_content}\n",
                                )

                        self.code_execution_count += 1

            # Yield coordination tool calls if detected
            if tool_calls_detected:
                # Enhanced tool calls summary logging
                log_stream_chunk(
                    "backend.gemini",
                    "tool_calls_yielded",
                    {
                        "tool_count": len(tool_calls_detected),
                        "tool_names": [tc.get("function", {}).get("name") for tc in tool_calls_detected],
                    },
                    agent_id,
                )
                yield StreamChunk(type="tool_calls", tool_calls=tool_calls_detected)

            # Build complete message
            complete_message = {"role": "assistant", "content": content.strip()}
            if tool_calls_detected:
                complete_message["tool_calls"] = tool_calls_detected

            # Enhanced complete message logging with metadata
            log_stream_chunk(
                "backend.gemini",
                "complete_message",
                {
                    "content_length": len(content.strip()),
                    "has_tool_calls": bool(tool_calls_detected),
                },
                agent_id,
            )
            yield StreamChunk(type="complete_message", complete_message=complete_message)
            log_stream_chunk("backend.gemini", "done", None, agent_id)
            yield StreamChunk(type="done")

        except Exception as e:
            error_msg = f"Gemini API error: {e}"
            # Enhanced error logging with structured details
            log_stream_chunk(
                "backend.gemini",
                "stream_error",
                {"error_type": type(e).__name__, "error_message": str(e)},
                agent_id,
            )
            yield StreamChunk(type="error", error=error_msg)
        finally:
            # Cleanup resources
            await self.mcp_manager.cleanup_genai_resources(stream, client)
            # Ensure context manager exit for MCP cleanup
            try:
                await self.__aexit__(None, None, None)
            except Exception as e:
                log_backend_activity(
                    "gemini",
                    "MCP cleanup failed",
                    {"error": str(e)},
                    agent_id=self.agent_id,
                )

    def get_provider_name(self) -> str:
        """Get the provider name."""
        return "Gemini"

    def get_filesystem_support(self) -> FilesystemSupport:
        """Gemini supports filesystem through MCP servers."""
        return FilesystemSupport.MCP

    def get_supported_builtin_tools(self) -> List[str]:
        """Get list of builtin tools supported by Gemini."""
        return ["google_search_retrieval", "code_execution"]

    def get_mcp_results(self) -> Dict[str, Any]:
        """
        Get all captured MCP tool calls and responses.

        Returns:
            Dict containing:
            - calls: List of all MCP tool calls
            - responses: List of all MCP tool responses
            - pairs: List of matched call-response pairs
            - summary: Statistical summary of interactions
        """
        return {
            "calls": self.mcp_extractor.mcp_calls,
            "responses": self.mcp_extractor.mcp_responses,
            "pairs": self.mcp_extractor.call_response_pairs,
            "summary": self.mcp_extractor.get_summary(),
        }

    def get_mcp_paired_results(self) -> List[Dict[str, Any]]:
        """
        Get only the paired MCP tool calls and responses.

        Returns:
            List of dictionaries containing matched call-response pairs
        """
        return self.mcp_extractor.call_response_pairs

    def get_mcp_summary(self) -> Dict[str, Any]:
        """
        Get a summary of MCP tool interactions.

        Returns:
            Dictionary with statistics about MCP tool usage
        """
        return self.mcp_extractor.get_summary()

    def clear_mcp_results(self):
        """Clear all stored MCP interaction data."""
        self.mcp_extractor.clear()

    def reset_tool_usage(self):
        """Reset tool usage tracking."""
        self.search_count = 0
        self.code_execution_count = 0
        # Reset MCP monitoring metrics
        self._mcp_tool_calls_count = 0
        self._mcp_tool_failures = 0
        self._mcp_tool_successes = 0
        self._mcp_connection_retries = 0
        # Clear MCP extractor data
        self.mcp_extractor.clear()
        super().reset_token_usage()

    async def cleanup_mcp(self):
        """Cleanup MCP connections - override parent class to use Gemini-specific cleanup."""
        if self._mcp_client:
            try:
                await self._mcp_client.disconnect()
                log_backend_activity("gemini", "MCP client disconnected", {}, agent_id=self.agent_id)
            except (
                MCPConnectionError,
                MCPTimeoutError,
                MCPServerError,
                MCPError,
                Exception,
            ) as e:
                MCPErrorHandler.get_error_details(e, "disconnect", log=True)
            finally:
                self._mcp_client = None
                self._mcp_initialized = False
                # Also clear parent class attributes if they exist (for compatibility)
                if hasattr(self, "_mcp_functions"):
                    self._mcp_functions.clear()
                if hasattr(self, "_mcp_function_names"):
                    self._mcp_function_names.clear()

    async def __aenter__(self) -> "GeminiBackend":
        """Async context manager entry."""
        try:
            await self.mcp_manager.setup_mcp_tools(agent_id=self.agent_id)
        except Exception as e:
            log_backend_activity(
                "gemini",
                "MCP setup failed during context entry",
                {"error": str(e)},
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
        # Parameters are required by context manager protocol but not used
        _ = (exc_type, exc_val, exc_tb)
        try:
            await self.cleanup_mcp()
        except Exception as e:
            log_backend_activity(
                "gemini",
                "Backend cleanup error",
                {"error": str(e)},
                agent_id=self.agent_id,
            )