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

Test Results:
✅ TESTED 2025-08-10: Single agent coordination working correctly
- Command: uv run python -m massgen.cli --config claude_code_single.yaml "2+2=?"
- Auto-created working directory: claude_code_workspace/
- Session: 42593707-bca6-40ad-b154-7dc1c222d319
- Model: claude-sonnet-4-20250514 (Claude Code default)
- Tools available: Task, Bash, Glob, Grep, LS, Read, Write, WebSearch, etc.
- Answer provided: "2 + 2 = 4" 
- Coordination: Agent voted for itself, selected as final answer
- Performance: 70 seconds total (includes coordination overhead)

TODO:
- Consider including cwd/session_id in new_answer results for context preservation
- Investigate whether next iterations need working directory context
"""

from __future__ import annotations

import json
import os
import re
import uuid
from pathlib import Path
from typing import Dict, List, Any, AsyncGenerator, Optional
from claude_code_sdk import ClaudeSDKClient, ClaudeCodeOptions  # type: ignore


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
                - model: Claude model name
                - system_prompt: Base system prompt
                - allowed_tools: List of allowed tools
                - max_thinking_tokens: Maximum thinking tokens
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

        # Single ClaudeSDKClient for this backend instance
        self._client: Optional[Any] = None  # ClaudeSDKClient
        self._current_session_id: Optional[str] = None

    def get_provider_name(self) -> str:
        """Get the name of this provider."""
        return "claude_code"

    def is_stateful(self) -> bool:
        """
        Claude Code backend is stateful - maintains conversation context.
        
        Returns:
            True - Claude Code maintains server-side session state
        """
        return True

    async def clear_history(self) -> None:
        """
        Clear Claude Code conversation history while preserving session.
        
        Uses the /clear slash command to clear conversation history without
        destroying the session, working directory, or other session state.
        """
        if self._client is None:
            # No active session to clear
            return
            
        try:
            # Send /clear command to clear history while preserving session
            await self._client.query("/clear")
            
            # The /clear command should preserve:
            # - Session ID
            # - Working directory
            # - Tool availability
            # - Permission settings
            # While clearing only the conversation history
            
        except Exception as e:
            # Fallback to full reset if /clear command fails
            print(f"Warning: /clear command failed ({e}), falling back to full reset")
            await self.reset_state()

    async def reset_state(self) -> None:
        """
        Reset Claude Code backend state.
        
        Properly disconnects and clears the current session and client connection to start fresh.
        """
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:
                pass  # Ignore cleanup errors
        self._client = None
        self._current_session_id = None

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
                from claude_code_sdk import ResultMessage  # type: ignore
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
            from claude_code_sdk import ResultMessage  # type: ignore
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

        # Add workflow tools information if present
        if tools:
            workflow_tools = [
                t for t in tools
                if t.get("function", {}).get("name") in ["new_answer", "vote"]]
            if workflow_tools:
                system_parts.append("\n--- Available Tools ---")
                for tool in workflow_tools:
                    name = tool.get("function", {}).get("name", "unknown")
                    description = tool.get("function", {}).get("description", "No description")
                    system_parts.append(f"- {name}: {description}")
                    
                    # Add usage examples for workflow tools
                    if name == "new_answer":
                        system_parts.append(
                            '    Usage: {"tool_name": "new_answer", '
                            '"arguments": {"content": "your answer"}}')
                    elif name == "vote":
                        system_parts.append(
                            '    Usage: {"tool_name": "vote", '
                            '"arguments": {"agent_id": "agent1", '
                            '"reason": "explanation"}}')
                        
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
            List of unique tool call dictionaries in standard format
        """
        tool_calls = []
        seen_calls = set()  # Track unique tool calls to prevent duplicates

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
                    
                    # Create a unique identifier for this tool call
                    # Based on tool name and arguments content
                    call_signature = (tool_name, json.dumps(arguments, sort_keys=True))
                    
                    # Only add if we haven't seen this exact call before
                    if call_signature not in seen_calls:
                        seen_calls.add(call_signature)
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

    def _build_claude_options(self, **options_kwargs) -> ClaudeCodeOptions:
        """Build ClaudeCodeOptions with provided parameters.

        Creates a secure configuration that allows ALL Claude Code tools while
        explicitly disallowing dangerous operations. This gives Claude Code
        maximum power while maintaining security.

        Returns:
            ClaudeCodeOptions configured with provided parameters and
            security restrictions
        """
        cwd_path = options_kwargs.get("cwd")
        permission_mode = options_kwargs.get("permission_mode", "acceptEdits")
        
        # Filter out parameters handled separately or not for ClaudeCodeOptions
        excluded_params = {
            "cwd", "permission_mode", "type", "agent_id", "session_id", "api_key"
        }
        
        # Handle cwd - create directory if it doesn't exist or use current dir
        cwd_option = None
        if cwd_path:
            cwd_dir = Path(cwd_path)
            if cwd_dir.is_absolute():
                # Absolute path - create if needed
                cwd_dir.mkdir(parents=True, exist_ok=True)
                cwd_option = cwd_dir
            else:
                # Relative path - create relative to current working directory
                cwd_dir.mkdir(parents=True, exist_ok=True)
                cwd_option = cwd_dir
        
        return ClaudeCodeOptions(
            # No model set by default - let Claude Code decide
            # No allowed_tools restriction - allow ALL tools for maximum
            # power. Security is enforced through disallowed_tools only
            cwd=cwd_option,
            resume=self.get_current_session_id(),
            permission_mode=permission_mode,
            **{k: v for k, v in options_kwargs.items() if k not in excluded_params}
        )

    def create_client(self, **options_kwargs) -> ClaudeSDKClient:
        """Create ClaudeSDKClient with configurable parameters.

        Args:
            **options_kwargs: ClaudeCodeOptions parameters

        Returns:
            ClaudeSDKClient instance
        """
        # Build options with all parameters
        options = self._build_claude_options(**options_kwargs)

        # Create ClaudeSDKClient with configured options
        self._client = ClaudeSDKClient(options)
        return self._client

    async def stream_with_tools(
            self, messages: List[Dict[str, Any]],
            tools: List[Dict[str, Any]], **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Stream a response with tool calling support using claude-code-sdk.

        Properly handle messages and tools context for Claude Code.

        Args:
            messages: List of conversation messages
            tools: List of available tools (includes workflow tools)
            **kwargs: Additional options for client configuration

        Yields:
            StreamChunk objects with response content and metadata
        """
        # Merge constructor config with stream kwargs (stream kwargs take priority)
        all_params = {**self.config, **kwargs}
        # Check if we already have a client
        if self._client is not None:
            client = self._client
        else:
            # Set default disallowed_tools if not provided
            if "disallowed_tools" not in all_params:
                all_params["disallowed_tools"] = [
                    "Bash(rm*)", "Bash(sudo*)", "Bash(su*)", "Bash(chmod*)",
                    "Bash(chown*)"
                ]
                # Extract system message from messages for append mode
                system_msg = next(
                    (msg for msg in messages if msg.get("role") == "system"), None)
                if system_msg:
                    system_content = system_msg.get('content', '')  # noqa: E128
                else:
                    system_content = ''
                workflow_system_prompt = (
                    self._build_system_prompt_with_workflow_tools(
                        tools or [], system_content))
                # Handle different system prompt modes
                if all_params.get("append_system_prompt"):
                    # Create client with append_system_prompt
                    client = self.create_client(
                        append_system_prompt=workflow_system_prompt,
                        **all_params)
                else:
                    # Build system prompt with tools information
                    # (following ClaudeCodeCLI approach)
                    # Create client with the enhanced system prompt
                    client = self.create_client(
                        system_prompt=workflow_system_prompt,
                        **all_params)

        # Connect client if not already connected
        if not client._transport:
            await client.connect()

        # Format the messages for Claude Code
        if not messages:
            # No messages to process - yield error
            yield StreamChunk(
                type="error",
                error="No messages provided to stream_with_tools",
                source="claude_code"
            )
            return
            
        # Validate messages - should only contain user messages for Claude Code
        user_messages = [msg for msg in messages if msg.get("role") == "user"]
        assistant_messages = [msg for msg in messages if msg.get("role") == "assistant"]
        
        if assistant_messages:
            yield StreamChunk(
                type="error",
                error="Claude Code backend cannot accept assistant messages - it maintains its own conversation history",
                source="claude_code"
            )
            return
            
        if not user_messages:
            yield StreamChunk(
                type="error",
                error="No user messages found to send to Claude Code",
                source="claude_code"
            )
            return
        
        # Combine all user messages into a single query
        user_contents = []
        for user_msg in user_messages:
            content = user_msg.get("content", "").strip()
            if content:
                user_contents.append(content)
        if user_contents:
            # Join multiple user messages with newlines
            combined_query = "\n\n".join(user_contents)
            await client.query(combined_query)
        else:
            yield StreamChunk(
                type="error",
                error="All user messages were empty",
                    source="claude_code"
                )
            return
        # Stream response and convert to MassGen StreamChunks
        accumulated_content = ""
        try:
            async for message in client.receive_response():
                # Import message types
                from claude_code_sdk import (  # type: ignore
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

    def _track_session_id(self, message) -> None:
        """Track session ID from server responses for session persistence.

        Extracts and stores session ID from ResultMessage to enable
        session continuation across multiple interactions.  # noqa: E501

        Args:
            message: Message from Claude Code, potentially containing
                session ID  # noqa: E129
        """
        # Import message types locally to avoid import issues
        try:
            from claude_code_sdk import ResultMessage  # type: ignore
            if (isinstance(message, ResultMessage) and
                    hasattr(message, 'session_id') and
                    message.session_id):
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
