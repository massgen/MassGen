"""
Claude Code Stream Backend - Streaming interface using claude-code-sdk-python.

This backend provides integration with Claude Code through the
claude-code-sdk-python, leveraging Claude Code's server-side session
persistence and tool execution capabilities.

Key Features:
- ✅ Native Claude Code streaming integration
- ✅ Server-side session persistence (no client-side session
  management needed)
- ✅ Built-in tool execution (Read, Write, Bash, WebSearch, etc.)
- ✅ MassGen workflow tool integration (new_answer, vote via system prompts)
- ✅ Single persistent client with automatic session ID tracking
- ✅ Cost tracking from server-side usage data

Architecture:
- Uses ClaudeSDKClient with minimal functionality overlay
- Claude Code server maintains conversation history
- Extracts session IDs from ResultMessage responses
- Injects MassGen workflow tools via system prompts
- Converts claude-code-sdk Messages to MassGen StreamChunks

Requirements:
- claude-code-sdk-python installed: uv add claude-code-sdk
- Claude Code CLI available in PATH
- ANTHROPIC_API_KEY configured OR Claude subscription authentication
"""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Dict, List, Any, AsyncGenerator, Optional
from claude_code_sdk import ClaudeSDKClient, ClaudeCodeOptions


from .base import LLMBackend, StreamChunk


class ClaudeCodeBackend(LLMBackend):
    """Claude Code backend using claude-code-sdk-python.

    Provides streaming interface to Claude Code with built-in tool execution
    capabilities and MassGen workflow tool integration. Uses ClaudeSDKClient
    for direct communication with Claude Code server.
    """

    def __init__(self, api_key: Optional[str] = None, **kwargs):
        """Initialize ClaudeCodeBackend.

        Args:
            api_key: Anthropic API key (falls back to ANTHROPIC_API_KEY env
                    var). If None, will attempt to use Claude subscription
                    authentication
            **kwargs: Additional configuration options including:
                - model: Claude model name (default: claude-sonnet-4-20250514)
                - system_prompt: Base system prompt
                - allowed_tools: List of allowed tools
                - max_thinking_tokens: Maximum thinking tokens (default: 8000)
                - cwd: Current working directory

        Note:
            Authentication is validated on first use. If neither API key nor
            subscription authentication is available, errors will surface when
            attempting to use the backend.
        """
        super().__init__(api_key, **kwargs)

        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.use_subscription_auth = not bool(self.api_key)

        # Set API key in environment for SDK if provided
        if self.api_key:
            os.environ["ANTHROPIC_API_KEY"] = self.api_key

        # Configuration
        self.model = kwargs.get("model", "claude-sonnet-4-20250514")
        self.system_prompt = kwargs.get("system_prompt")
        self.append_system_prompt = kwargs.get("append_system_prompt")
        # Keep for backward compatibility
        self.allowed_tools = kwargs.get("allowed_tools", [])
        self.disallowed_tools = kwargs.get("disallowed_tools", [
            "Bash(rm*)", "Bash(sudo*)", "Bash(su*)", "Bash(chmod*)",
            "Bash(chown*)"])
        self.max_thinking_tokens = kwargs.get("max_thinking_tokens", 8000)
        self.cwd = kwargs.get("cwd")

        # Single ClaudeSDKClient for this backend instance
        self._client: Optional[Any] = None  # ClaudeSDKClient
        self._current_session_id: Optional[str] = None

    def get_provider_name(self) -> str:
        """Get the name of this provider."""
        return "claude_code"

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text (approximation for Claude)."""
        # Claude tokenization approximation: ~3.5-4 characters per token
        # More accurate than 4:1 ratio, especially for code/structured text
        return max(1, len(text.encode('utf-8')) // 4)

    def calculate_cost(
            self, input_tokens: int, output_tokens: int,
            model: str, result_message=None) -> float:
        """Calculate cost for token usage.

        Prefers ResultMessage actual cost over estimation.

        Args:
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            model: Model name for pricing lookup
            result_message: Optional ResultMessage with actual cost data

        Returns:
            Cost in USD, using actual cost from ResultMessage if available,
            otherwise calculated using model pricing
        """
        # If we have a ResultMessage with actual cost, use that
        if result_message is not None:
            try:
                from claude_code_sdk import ResultMessage
                if (isinstance(result_message, ResultMessage) and
                        result_message.total_cost_usd is not None):
                    return result_message.total_cost_usd
            except ImportError:
                # Fallback: check if it has the expected attribute
                if (hasattr(result_message, 'total_cost_usd') and
                        result_message.total_cost_usd is not None):
                    return result_message.total_cost_usd

        # Fallback: calculate estimated cost based on Claude pricing (2025)
        model_lower = model.lower()

        # Claude 4 pricing
        if "opus-4" in model_lower or "claude-4" in model_lower:
            input_cost_per_token = 15.0 / 1_000_000   # $15 per million
            output_cost_per_token = 75.0 / 1_000_000  # $75 per million
        # Claude Sonnet 4 pricing
        elif "sonnet-4" in model_lower:
            input_cost_per_token = 15.0 / 1_000_000   # $15 per million
            output_cost_per_token = 75.0 / 1_000_000  # $75 per million
        # Claude 3.5 Sonnet pricing
        elif "sonnet" in model_lower and "3.5" in model_lower:
            input_cost_per_token = 3.0 / 1_000_000    # $3 per million
            output_cost_per_token = 15.0 / 1_000_000  # $15 per million
        # Claude 3.5 Haiku pricing
        elif "haiku" in model_lower:
            input_cost_per_token = 0.25 / 1_000_000   # $0.25 per million
            output_cost_per_token = 1.25 / 1_000_000  # $1.25 per million
        else:
            # Default to Claude 3.5 Sonnet pricing
            input_cost_per_token = 3.0 / 1_000_000
            output_cost_per_token = 15.0 / 1_000_000

        return ((input_tokens * input_cost_per_token) +
                (output_tokens * output_cost_per_token))

    def update_token_usage_from_result_message(
            self, result_message) -> None:
        """Update token usage from Claude Code ResultMessage.

        Extracts actual token usage and cost data from Claude Code server
        response. This is more accurate than estimation-based methods.

        Args:
            result_message: ResultMessage from Claude Code with usage data
        """
        # Import locally to avoid import issues
        try:
            from claude_code_sdk import ResultMessage
            if not isinstance(result_message, ResultMessage):
                return
        except ImportError:
            # Fallback: check if it has the expected attributes
            if (not hasattr(result_message, 'usage') or
                    not hasattr(result_message, 'total_cost_usd')):
                return

        # Extract usage information from ResultMessage
        if result_message.usage:
            usage_data = result_message.usage

            # Claude Code provides actual token counts
            input_tokens = usage_data.get("input_tokens", 0)
            output_tokens = usage_data.get("output_tokens", 0)

            # Update cumulative tracking
            self.token_usage.input_tokens += input_tokens
            self.token_usage.output_tokens += output_tokens

        # Use actual cost from Claude Code (preferred over calculation)
        if result_message.total_cost_usd is not None:
            self.token_usage.estimated_cost += result_message.total_cost_usd
        else:
            # Fallback: calculate cost if not provided
            input_tokens = (
                result_message.usage.get("input_tokens", 0)
                if result_message.usage else 0)
            output_tokens = (
                result_message.usage.get("output_tokens", 0)
                if result_message.usage else 0)
            cost = self.calculate_cost(
                input_tokens, output_tokens, self.model, result_message)
            self.token_usage.estimated_cost += cost

    def update_token_usage(
            self, messages: List[Dict[str, Any]], response_content: str,
            model: str):
        """Update token usage tracking (fallback method).

        Only used when no ResultMessage available. Provides estimated token
        tracking for compatibility with base class interface. Should only be
        called when ResultMessage data is not available.

        Args:
            messages: List of conversation messages
            response_content: Generated response content
            model: Model name for cost calculation
        """
        # This method should only be called when we don't have a
        # ResultMessage. It provides estimated tracking for compatibility
        # with base class interface

        # Estimate input tokens from messages
        input_text = "\n".join([msg.get("content", "") for msg in messages])
        input_tokens = self.estimate_tokens(input_text)

        # Estimate output tokens from response
        output_tokens = self.estimate_tokens(response_content)

        # Update totals
        self.token_usage.input_tokens += input_tokens
        self.token_usage.output_tokens += output_tokens

        # Calculate estimated cost (no ResultMessage available)
        cost = self.calculate_cost(
            input_tokens, output_tokens, model, result_message=None)
        self.token_usage.estimated_cost += cost

    def get_supported_builtin_tools(self) -> List[str]:
        """Get list of builtin tools supported by Claude Code.

        Returns maximum tool set available, with security enforced through
        disallowed_tools. Dangerous operations are blocked at the tool
        level, not by restricting tool access.

        Returns:
            List of all tool names that Claude Code provides natively
        """
        return [
            "Read", "Write", "Edit", "MultiEdit", "Bash", "Grep", "Glob",
            "LS", "WebSearch", "WebFetch", "Task", "TodoWrite",
            "NotebookEdit", "NotebookRead", "mcp__ide__getDiagnostics",
            "mcp__ide__executeCode", "ExitPlanMode"
        ]

    def get_current_session_id(self) -> Optional[str]:
        """Get current session ID from server-side session management.

        Returns:
            Current session ID if available, None otherwise
        """
        return self._current_session_id

    def _format_messages_for_claude_code(
            self, messages: List[Dict[str, Any]],
            tools: List[Dict[str, Any]]) -> str:
        """Format messages specifically for Claude Code.

        Adapted from previous Claude Code CLI backend. Converts MassGen
        message format to Claude Code's expected format, including
        conversation history and tool information.

        Args:
            messages: List of conversation messages
            tools: List of available tools

        Returns:
            Formatted string suitable for Claude Code query
        """
        formatted_parts = []

        # Add system message if present
        system_msg = next(
            (msg for msg in messages if msg.get("role") == "system"), None)
        if system_msg:
            formatted_parts.append(
                f"System instructions: {system_msg.get('content', '')}")

        # Add conversation history
        conversation_parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "user":
                conversation_parts.append(f"User: {content}")
            elif role == "assistant":
                conversation_parts.append(f"Assistant: {content}")

        if conversation_parts:
            formatted_parts.append("Conversation:\n" +
                                   "\n".join(conversation_parts))

        # Add available tools information (including workflow tools)
        if tools:
            tools_info = self._format_tools_for_claude_code(tools)
            formatted_parts.append(f"Available tools: {tools_info}")

        return "\n\n".join(formatted_parts)

    def _format_tools_for_claude_code(
            self, tools: List[Dict[str, Any]]) -> str:
        """Format tools information for Claude Code.

        Adapted from previous Claude Code CLI backend. Converts tool
        definitions to human-readable format with special handling for
        MassGen workflow tools (new_answer, vote).

        Args:
            tools: List of tool definitions

        Returns:
            Formatted tool descriptions string
        """
        if not tools:
            return "None"

        tool_descriptions = []
        for tool in tools:
            name = tool.get("function", {}).get("name", "unknown")
            description = tool.get("function", {}).get("description",
                                                        "No description")

            # Special handling for MassGen workflow tools
            if name in ["new_answer", "vote"]:
                params = tool.get("function", {}).get(
                    "parameters", {}).get("properties", {})
                param_details = []
                for param_name, param_def in params.items():
                    param_desc = param_def.get("description", "")
                    param_details.append(
                    f"    {param_name}: {param_desc}")

                tool_descriptions.append(f"- {name}: {description}")
                if param_details:
                    tool_descriptions.append("\n".join(param_details))

                # Add usage example for workflow tools
                if name == "new_answer":
                    tool_descriptions.append(
                        '    Usage: {"tool_name": "new_answer", '
                        '"arguments": {"content": "your answer"}}')
                elif name == "vote":
                    tool_descriptions.append(
                        '    Usage: {"tool_name": "vote", '
                        '"arguments": {"agent_id": "agent1", '
                        '"reason": "explanation"}}')
            else:
                tool_descriptions.append(f"- {name}: {description}")

        return "\n".join(tool_descriptions)

    def _build_system_prompt_with_workflow_tools(
            self, tools: List[Dict[str, Any]],
            base_system: Optional[str] = None) -> str:
        """Build system prompt that includes workflow tools information.

        Creates comprehensive system prompt that instructs Claude on tool
        usage, particularly for MassGen workflow coordination tools.

        Args:
            tools: List of available tools
            base_system: Base system prompt to extend (optional)

        Returns:
            Complete system prompt with tool instructions
        """
        system_parts = []

        # Start with base system prompt
        if base_system:
            system_parts.append(base_system)

        # Add tools information if present
        if tools:
            system_parts.append("\n--- Available Tools ---")
            tools_info = self._format_tools_for_claude_code(tools)
            system_parts.append(tools_info)

            # Check for workflow tools and add special instructions
            workflow_tools = [
                t for t in tools
                if t.get("function", {}).get("name") in ["new_answer", "vote"]]
            if workflow_tools:
                system_parts.append("\n--- MassGen Workflow Instructions ---")
                system_parts.append(
                    "You must use the coordination tools (new_answer, vote) "
                    "to participate in multi-agent workflows.")
                system_parts.append(
                    "Respond with the JSON format shown in the tool usage "
                    "examples above.")

        return "\n".join(system_parts)

    def _parse_workflow_tool_calls(
            self, text_content: str) -> List[Dict[str, Any]]:
        """Parse workflow tool calls from text content.

        Searches for JSON-formatted tool calls in the response text and
        converts them to the standard tool call format used by MassGen.
        Generates unique tool call IDs using uuid4.

        Args:
            text_content: Response text to search for tool calls

        Returns:
            List of tool call dictionaries in standard format
        """
        tool_calls = []

        # Look for JSON tool call patterns
        json_patterns = [
            r'\{"tool_name":\s*"([^"]+)",\s*"arguments":\s*'
            r'(\{[^}]*\})\}',
            r'\{\s*"tool_name"\s*:\s*"([^"]+)"\s*,\s*"arguments"'
            r'\s*:\s*(\{[^}]*\})\s*\}'
        ]

        for pattern in json_patterns:
            matches = re.finditer(pattern, text_content, re.IGNORECASE)
            for match in matches:
                tool_name = match.group(1)
                try:
                    arguments = json.loads(match.group(2))
                    tool_calls.append({
                        "id": f"call_{uuid.uuid4().hex[:8]}",
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": arguments
                        }
                    })
                except json.JSONDecodeError:
                    continue

        return tool_calls

    def _get_default_claude_options(self) -> ClaudeCodeOptions:
        """Get default ClaudeCodeOptions with maximum tool access.

        Except dangerous operations. Creates a secure configuration that
        allows ALL Claude Code tools while explicitly disallowing dangerous
        operations. This gives Claude Code maximum power while maintaining
        security.

        Returns:
            ClaudeCodeOptions configured for maximum capability with
            security restrictions
        """
        return ClaudeCodeOptions(
            model=self.model,
            # No allowed_tools restriction - allow ALL tools for maximum
            # power. Security is enforced through disallowed_tools only
            disallowed_tools=[
                "Bash(rm*)", "Bash(sudo*)", "Bash(su*)",
                "Bash(chmod*)", "Bash(chown*)"],
            max_thinking_tokens=self.max_thinking_tokens,
            cwd=Path(self.cwd) if self.cwd else None,
            resume=self.get_current_session_id(),
            permission_mode="acceptEdits",  # Accept file edits by default
        )

    def get_or_create_client(
            self, system_prompt: Optional[str] = None,
            allowed_tools: Optional[List[str]] = None,
            disallowed_tools: Optional[List[str]] = None,
            **options_kwargs) -> ClaudeSDKClient:
        """Get or create ClaudeSDKClient with configurable parameters.

        Args:
            system_prompt: Override system prompt
            allowed_tools: Override allowed tools list (for backward
                          compatibility)
            disallowed_tools: Override disallowed tools list (preferred
                             approach)
            **options_kwargs: Additional ClaudeCodeOptions parameters

        Returns:
            ClaudeSDKClient instance
        """
        if self._client is not None:
            return self._client

        # Start with default options
        options = self._get_default_claude_options()

        # Override with provided parameters
        if system_prompt:
            options.system_prompt = system_prompt
        elif self.system_prompt:
            options.system_prompt = self.system_prompt

        # Handle allowed_tools for backward compatibility
        if allowed_tools:
            options.allowed_tools = allowed_tools
        elif self.allowed_tools:
            # Only set allowed_tools if explicitly provided (legacy
            # support)
            options.allowed_tools = self.allowed_tools

        # Handle disallowed_tools (preferred security approach)
        if disallowed_tools:
            options.disallowed_tools = disallowed_tools
        else:
            # Use instance disallowed_tools (includes secure defaults)
            options.disallowed_tools = self.disallowed_tools

        # Apply any additional options
        for key, value in options_kwargs.items():
            if hasattr(options, key):
                setattr(options, key, value)

        # Create ClaudeSDKClient with configured options
        self._client = ClaudeSDKClient(options)
        return self._client

    async def stream_with_tools(
            self, messages: List[Dict[str, Any]],
            tools: List[Dict[str, Any]], **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Stream a response with tool calling support using claude-code-sdk.

        Uses previous Claude Code CLI backend's formatting approach to
        properly handle messages and tools context for Claude Code.

        Args:
            messages: List of conversation messages
            tools: List of available tools (includes workflow tools)
            **kwargs: Additional options (unused but maintained for
                     interface compatibility)

        Yields:
            StreamChunk objects with response content and metadata
        """
        # Note: kwargs unused but maintained for base class interface
        # compatibility
        try:
            # Extract system message from messages for append mode
            system_msg = next(
                (msg for msg in messages if msg.get("role") == "system"), None)
            system_content = (system_msg.get('content', '')
                             if system_msg else '')
            workflow_system_prompt = (
                self._build_system_prompt_with_workflow_tools(
                    tools or [], system_content))
            # Handle different system prompt modes
            if self.append_system_prompt:
                # Get or create client with append_system_prompt
                client = self.get_or_create_client(
                    append_system_prompt=workflow_system_prompt)
            else:
                # Build system prompt with tools information
                # (following ClaudeCodeCLI approach)
                # Get or create client with the enhanced system prompt
                client = self.get_or_create_client(
                    system_prompt=workflow_system_prompt)

            # Connect client if not already connected
            if not client._transport:
                await client.connect()

            # Format the entire conversation context (not just latest
            # message). This ensures Claude Code has full context including
            # tools.
            if messages:
                # For streaming, we can send the formatted context as a
                # single query
                formatted_context = self._format_messages_for_claude_code(
                    messages, tools or [])
                await client.query(formatted_context)
            else:
                # Fallback: just send a basic query
                await client.query("Hello")

            # Stream response and convert to MassGen StreamChunks
            accumulated_content = ""

            async for message in client.receive_response():
                # Import message types
                from claude_code_sdk import (
                    AssistantMessage, SystemMessage, ResultMessage,
                    TextBlock, ToolUseBlock, ToolResultBlock
                )

                if isinstance(message, AssistantMessage):
                    # Process assistant message content
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            accumulated_content += block.text

                            # Yield content chunk
                            yield StreamChunk(
                                type="content",
                                content=block.text,
                                source="claude_code"
                            )

                        elif isinstance(block, ToolUseBlock):
                            # Claude Code's builtin tool usage
                            yield StreamChunk(
                                type="builtin_tool_results",
                                builtin_tool_results=[{
                                    "tool_name": block.name,
                                    "tool_input": block.input,
                                    "tool_call_id": block.id
                                }],
                                source="claude_code"
                            )

                        elif isinstance(block, ToolResultBlock):
                            # Tool result from Claude Code
                            # Note: ToolResultBlock.tool_use_id references
                            # the original ToolUseBlock.id
                            yield StreamChunk(
                                type="builtin_tool_results",
                                builtin_tool_results=[{
                                    "tool_call_id": block.tool_use_id,
                                    "tool_result": block.content,
                                    "is_error": block.is_error or False
                                }],
                                source="claude_code"
                            )

                    # Parse workflow tool calls from accumulated content
                    workflow_tool_calls = (
                        self._parse_workflow_tool_calls(accumulated_content))
                    if workflow_tool_calls:
                        yield StreamChunk(
                            type="tool_calls",
                            tool_calls=workflow_tool_calls,
                            source="claude_code"
                        )

                    # Yield complete message
                    yield StreamChunk(
                        type="complete_message",
                        complete_message={
                            "role": "assistant",
                            "content": accumulated_content
                        },
                        source="claude_code"
                    )

                elif isinstance(message, SystemMessage):
                    # System status updates
                    yield StreamChunk(
                        type="agent_status",
                        status=message.subtype,
                        content=str(message.data),
                        source="claude_code"
                    )

                elif isinstance(message, ResultMessage):
                    # Track session ID from server response
                    self._track_session_id(message)

                    # Update token usage using ResultMessage data
                    self.update_token_usage_from_result_message(message)

                    # Yield completion
                    yield StreamChunk(
                        type="complete_response",
                        response={
                            "session_id": message.session_id,
                            "duration_ms": message.duration_ms,
                            "cost_usd": message.total_cost_usd,
                            "usage": message.usage,
                            "is_error": message.is_error
                        },
                        source="claude_code"
                    )

                    # Final done signal
                    yield StreamChunk(type="done", source="claude_code")
                    break

        except Exception as e:
            yield StreamChunk(
                type="error",
                error=f"Claude Code streaming error: {str(e)}",
                source="claude_code"
            )

    def extract_tool_name(self, tool_call: Dict[str, Any]) -> str:
        """Extract tool name from tool call."""
        return tool_call.get("function", {}).get("name", "unknown")

    def extract_tool_arguments(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """Extract tool arguments from tool call."""
        return tool_call.get("function", {}).get("arguments", {})

    def extract_tool_call_id(self, tool_call: Dict[str, Any]) -> str:
        """Extract tool call ID from tool call."""
        return tool_call.get("id", "")

    def create_tool_result_message(
            self, tool_call: Dict[str, Any], result_content: str
    ) -> Dict[str, Any]:
        """Create tool result message."""
        return {
            "role": "tool",
            "tool_call_id": self.extract_tool_call_id(tool_call),
            "content": result_content
        }

    def _track_session_id(self, message) -> None:
        """Track session ID from server responses for session persistence.

        Extracts and stores session ID from ResultMessage to enable session
        continuation across multiple interactions.

        Args:
            message: Message from Claude Code, potentially containing session ID
        """
        # Import message types locally to avoid import issues
        try:
            from claude_code_sdk import ResultMessage
            if (isinstance(message, ResultMessage) and
                hasattr(message, 'session_id') and message.session_id):
                self._current_session_id = message.session_id
        except ImportError:
            # Fallback - check if message has session_id attribute
            if hasattr(message, 'session_id') and message.session_id:
                self._current_session_id = message.session_id

    async def disconnect(self):
        """Disconnect the ClaudeSDKClient and clean up resources.

        Properly closes the connection and resets internal state.
        Should be called when the backend is no longer needed.
        """
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:
                pass  # Ignore cleanup errors
            finally:
                self._client = None
                self._current_session_id = None

    def __del__(self):
        """Cleanup on destruction.

        Note: This won't work for async cleanup in practice.
        Use explicit disconnect() calls for proper resource cleanup.
        """
        # Note: This won't work for async cleanup, but serves as documentation
        # Real cleanup should be done via explicit disconnect() calls
        pass
