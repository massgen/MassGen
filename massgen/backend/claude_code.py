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
import shutil
import uuid
from pathlib import Path
from typing import Dict, List, Any, AsyncGenerator, Optional
from claude_code_sdk import (  # type: ignore
    ClaudeSDKClient,
    ClaudeCodeOptions,
    ResultMessage,
    SystemMessage,
    AssistantMessage,
    UserMessage,
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
)
import sys
import warnings
import atexit


from .base import LLMBackend, StreamChunk
from ..logger_config import log_backend_activity, log_backend_agent_message, log_stream_chunk, logger


class ClaudeCodeBackend(LLMBackend):
    """Claude Code backend using claude-code-sdk-python.

    Provides streaming interface to Claude Code with built-in tool execution
    capabilities and MassGen workflow tool integration. Uses ClaudeSDKClient
    for direct communication with Claude Code server.
    
    TODO (v0.0.14 Context Sharing Enhancement - See docs/dev_notes/v0.0.14-context.md):
    - Implement permission enforcement during file/workspace operations
    - Add execute_with_permissions() method to check permissions before operations
    - Integrate with PermissionManager for access control validation
    - Add audit logging for all file system access attempts
    - Enforce workspace boundaries based on agent permissions
    - Prevent unauthorized access to other agents' workspaces
    - Support permission-aware tool execution (Read, Write, Bash, etc.)
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

        # Set git-bash path for Windows compatibility
        if sys.platform == "win32" and not os.environ.get("CLAUDE_CODE_GIT_BASH_PATH"):
            import shutil
            bash_path = shutil.which("bash")
            if bash_path:
                os.environ["CLAUDE_CODE_GIT_BASH_PATH"] = bash_path
                print(f"[ClaudeCodeBackend] Set CLAUDE_CODE_GIT_BASH_PATH={bash_path}")

        # Comprehensive Windows subprocess cleanup warning suppression
        if sys.platform == "win32":
            self._setup_windows_subprocess_cleanup_suppression()

        # Single ClaudeSDKClient for this backend instance
        self._client: Optional[Any] = None  # ClaudeSDKClient
        self._current_session_id: Optional[str] = None
        self._cwd: Optional[str] = None
        self._temporary_cwd: Optional[str] = None  # Temporary workspace for context sharing

        # Handle initial cwd if provided - create directory and clear existing files
        cwd_path = kwargs.get("cwd")
        if cwd_path:
            cwd_dir = Path(cwd_path)
            if not cwd_dir.is_absolute():
                # Convert relative path to absolute path
                cwd_dir = cwd_dir.resolve()

            # Clear existing files if directory exists
            if cwd_dir.exists() and cwd_dir.is_dir():
                for item in cwd_dir.iterdir():
                    if item.is_file():
                        item.unlink()
                    elif item.is_dir():
                        shutil.rmtree(item)

            # Create directory if it doesn't exist
            cwd_dir.mkdir(parents=True, exist_ok=True)

            # Store the validated absolute path
            self._cwd = str(cwd_dir)

        self._pending_system_prompt: Optional[str] = None  # Windows-only workaround

    def _setup_windows_subprocess_cleanup_suppression(self):
        """Comprehensive Windows subprocess cleanup warning suppression."""
        # All warning filters
        warnings.filterwarnings("ignore", message="unclosed transport")
        warnings.filterwarnings("ignore", message="I/O operation on closed pipe")
        warnings.filterwarnings("ignore", category=ResourceWarning, message="unclosed transport")
        warnings.filterwarnings("ignore", category=ResourceWarning, message="unclosed event loop")
        warnings.filterwarnings("ignore", category=ResourceWarning, message="unclosed <socket.socket")
        warnings.filterwarnings("ignore", category=RuntimeWarning, message="coroutine")
        warnings.filterwarnings("ignore", message="Exception ignored in")
        warnings.filterwarnings("ignore", message="sys:1: ResourceWarning")
        warnings.filterwarnings("ignore", category=ResourceWarning, message="unclosed.*transport.*")
        warnings.filterwarnings("ignore", message=".*BaseSubprocessTransport.*")
        warnings.filterwarnings("ignore", message=".*_ProactorBasePipeTransport.*")
        warnings.filterwarnings("ignore", message=".*Event loop is closed.*")

        # Patch asyncio transport destructors to be silent
        try:
            import asyncio.base_subprocess
            import asyncio.proactor_events

            # Store originals
            original_subprocess_del = getattr(asyncio.base_subprocess.BaseSubprocessTransport, '__del__', None)
            original_pipe_del = getattr(asyncio.proactor_events._ProactorBasePipeTransport, '__del__', None)

            def silent_subprocess_del(self):
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        if original_subprocess_del:
                            original_subprocess_del(self)
                except Exception:
                    pass

            def silent_pipe_del(self):
                try:
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        if original_pipe_del:
                            original_pipe_del(self)
                except Exception:
                    pass

            # Apply patches
            if original_subprocess_del:
                asyncio.base_subprocess.BaseSubprocessTransport.__del__ = silent_subprocess_del
            if original_pipe_del:
                asyncio.proactor_events._ProactorBasePipeTransport.__del__ = silent_pipe_del
        except Exception:
            pass  # If patching fails, fall back to warning filters only

        # Setup exit handler for stderr suppression
        original_stderr = sys.stderr

        def suppress_exit_warnings():
            try:
                sys.stderr = open(os.devnull, 'w')
                import time
                time.sleep(0.3)
            except Exception:
                pass
            finally:
                try:
                    if sys.stderr != original_stderr:
                        sys.stderr.close()
                    sys.stderr = original_stderr
                except Exception:
                    pass

        atexit.register(suppress_exit_warnings)


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
    
    def set_temporary_cwd(self, temporary_cwd: str) -> None:
        """Set the temporary working directory for context sharing.
        
        Args:
            temporary_cwd: Path to temporary workspace containing shared context from other agents
        """
        self._temporary_cwd = temporary_cwd

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
        return max(1, len(text.encode("utf-8")) // 4)

    def calculate_cost(
        self, input_tokens: int, output_tokens: int, model: str, result_message=None
    ) -> float:
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
            if (
                ResultMessage is not None
                and isinstance(result_message, ResultMessage)
                and result_message.total_cost_usd is not None
            ):
                return result_message.total_cost_usd
            # Fallback: check if it has the expected attribute (for SDK compatibility)
            elif (
                hasattr(result_message, "total_cost_usd")
                and result_message.total_cost_usd is not None
            ):
                return result_message.total_cost_usd

        # Fallback: calculate estimated cost based on Claude pricing (2025)
        model_lower = model.lower()

        # Claude 4 pricing
        if "opus-4" in model_lower or "claude-4" in model_lower:
            input_cost_per_token = 15.0 / 1_000_000  # $15 per million
            output_cost_per_token = 75.0 / 1_000_000  # $75 per million
        # Claude Sonnet 4 pricing
        elif "sonnet-4" in model_lower:
            input_cost_per_token = 15.0 / 1_000_000  # $15 per million
            output_cost_per_token = 75.0 / 1_000_000  # $75 per million
        # Claude 3.5 Sonnet pricing
        elif "sonnet" in model_lower and "3.5" in model_lower:
            input_cost_per_token = 3.0 / 1_000_000  # $3 per million
            output_cost_per_token = 15.0 / 1_000_000  # $15 per million
        # Claude 3.5 Haiku pricing
        elif "haiku" in model_lower:
            input_cost_per_token = 0.25 / 1_000_000  # $0.25 per million
            output_cost_per_token = 1.25 / 1_000_000  # $1.25 per million
        else:
            # Default to Claude 3.5 Sonnet pricing
            input_cost_per_token = 3.0 / 1_000_000
            output_cost_per_token = 15.0 / 1_000_000

        return (input_tokens * input_cost_per_token) + (
            output_tokens * output_cost_per_token
        )

    def update_token_usage_from_result_message(self, result_message) -> None:
        """Update token usage from Claude Code ResultMessage.

        Extracts actual token usage and cost data from Claude Code server
        response. This is more accurate than estimation-based methods.

        Args:
            result_message: ResultMessage from Claude Code with usage data
        """
        # Check if we have a valid ResultMessage
        if ResultMessage is not None and not isinstance(result_message, ResultMessage):
            return
        # Fallback: check if it has the expected attributes (for SDK compatibility)
        if not hasattr(result_message, "usage") or not hasattr(
            result_message, "total_cost_usd"
        ):
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
                if result_message.usage
                else 0
            )
            output_tokens = (
                result_message.usage.get("output_tokens", 0)
                if result_message.usage
                else 0
            )
            cost = self.calculate_cost(input_tokens, output_tokens, "", result_message)
            self.token_usage.estimated_cost += cost

    def update_token_usage(
        self, messages: List[Dict[str, Any]], response_content: str, model: str
    ):
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
            input_tokens, output_tokens, model, result_message=None
        )
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
            "Read",
            "Write",
            "Edit",
            "MultiEdit",
            "Bash",
            "Grep",
            "Glob",
            "LS",
            "WebSearch",
            "WebFetch",
            "Task",
            "TodoWrite",
            "NotebookEdit",
            "NotebookRead",
            "mcp__ide__getDiagnostics",
            "mcp__ide__executeCode",
            "ExitPlanMode",
        ]

    def get_current_session_id(self) -> Optional[str]:
        """Get current session ID from server-side session management.

        Returns:
            Current session ID if available, None otherwise
        """
        return self._current_session_id
    
    # TODO (v0.0.14 Context Sharing Enhancement - See docs/dev_notes/v0.0.14-context.md):
    # Add permission enforcement methods:
    # def execute_with_permissions(self, operation, path):
    #     """Execute operation only if permissions allow.
    #     
    #     Args:
    #         operation: The operation to execute (e.g., tool call)
    #         path: The file/directory path being accessed
    #     
    #     Raises:
    #         PermissionError: If agent lacks required access
    #     """
    #     if not self.check_permission(path, operation.type):
    #         raise PermissionError(f"Agent {self.agent_id} lacks {operation.type} access to {path}")
    #
    # def check_permission(self, path: str, access_type: str) -> bool:
    #     """Check if current agent has permission for path access."""
    #     # Will integrate with PermissionManager
    #     pass

    def _build_system_prompt_with_workflow_tools(
        self, tools: List[Dict[str, Any]], base_system: Optional[str] = None
    ) -> str:
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
                t
                for t in tools
                if t.get("function", {}).get("name") in ["new_answer", "vote"]
            ]
            if workflow_tools:
                system_parts.append("\n--- Coordination Actions ---")
                for tool in workflow_tools:
                    name = tool.get("function", {}).get("name", "unknown")
                    description = tool.get("function", {}).get(
                        "description", "No description"
                    )
                    system_parts.append(f"- {name}: {description}")

                    # Add usage examples for workflow tools
                    if name == "new_answer":
                        # Add reference to temporary workspace if available
                        if self._temporary_cwd:
                            absolute_temp_path = os.path.join(os.getcwd(), self._temporary_cwd)
                            system_parts.append(
                                f"    Context: You have access to a reference workspace at: {absolute_temp_path}"
                            )
                            system_parts.append(
                                "    This workspace contains work from yourself and other agents for REFERENCE ONLY."
                            )
                            system_parts.append(
                                "    CRITICAL: To understand your own or other agents' information, context, and work, ONLY check the temporary workspace."
                            )
                            system_parts.append(
                                f"    DO NOT look in your working directory ({self._cwd}) for agent information - it's exclusively for creating YOUR OWN new work."
                            )
                            system_parts.append(
                                "    You may READ documents or EXECUTE code from the temporary workspace to understand other agents' work."
                            )
                            system_parts.append(
                                "    When you READ or EXECUTE content from the temporary workspace, save any resulting outputs (analysis results, execution outputs, etc.) to the temporary workspace as well."
                            )
                            system_parts.append(
                                f"    IMPORTANT: ALL your own work (like writing files and creating outputs) MUST be done in your working directory: {self._cwd}"
                            )
                        system_parts.append(
                            '    Usage: {"tool_name": "new_answer", '
                            '"arguments": {"content": "your improved answer. If any builtin tools were used, mention how they are used here."}}'
                        )
                    elif name == "vote":
                        # Add reference to temporary workspace if available for voting context
                        if self._temporary_cwd:
                            absolute_temp_path = os.path.join(os.getcwd(), self._temporary_cwd)
                            system_parts.append(
                                f"    Context: You can review all agents' work (including your own) at: {absolute_temp_path}"
                            )
                            system_parts.append(
                                "    CRITICAL: To understand your own or other agents' information, context, and work, ONLY check the temporary workspace."
                            )
                            system_parts.append(
                                f"    DO NOT look in your working directory ({self._cwd}) for agent information - it's exclusively for creating YOUR OWN new work."
                            )
                            system_parts.append(
                                "    You may READ documents or EXECUTE code from the temporary workspace to understand other agents' work."
                            )
                            system_parts.append(
                                "    When you READ or EXECUTE content from the temporary workspace, save any resulting outputs (analysis results, execution outputs, etc.) to the temporary workspace as well."
                            )
                            system_parts.append(
                                f"    IMPORTANT: ALL your own work (like writing files and creating outputs) MUST be done in your working directory: {self._cwd}"
                            )
                            system_parts.append(
                                "    Use this context to make an informed voting decision."
                            )
                        
                        # Extract valid agent IDs from enum if available
                        agent_id_enum = None
                        for t in tools:
                            if t.get("function", {}).get("name") == "vote":
                                agent_id_param = (
                                    t.get("function", {})
                                    .get("parameters", {})
                                    .get("properties", {})
                                    .get("agent_id", {})
                                )
                                if "enum" in agent_id_param:
                                    agent_id_enum = agent_id_param["enum"]
                                break

                        if agent_id_enum:
                            agent_list = ", ".join(agent_id_enum)
                            system_parts.append(
                                f'    Usage: {{"tool_name": "vote", '
                                f'"arguments": {{"agent_id": "agent1", '
                                f'"reason": "explanation"}}}} // Choose agent_id from: {agent_list}'
                            )
                        else:
                            system_parts.append(
                                '    Usage: {"tool_name": "vote", '
                                '"arguments": {"agent_id": "agent1", '
                                '"reason": "explanation"}}'
                            )

                system_parts.append("\n--- MassGen Coordination Instructions ---")
                system_parts.append(
                    "IMPORTANT: You must respond with a structured JSON decision at the end of your response."
                )
                # system_parts.append(
                #     "You must use the coordination tools (new_answer, vote) "
                #     "to participate in multi-agent workflows."
                # )
                # system_parts.append(
                #     "Make sure to include the JSON in the exact format shown in the usage examples above.")
                system_parts.append(
                    "The JSON MUST be formatted as a strict JSON code block:"
                )
                system_parts.append("1. Start with ```json on one line")
                system_parts.append("2. Include your JSON content (properly formatted)")
                system_parts.append("3. End with ``` on one line")
                system_parts.append(
                    'Example format:\n```json\n{"tool_name": "vote", "arguments": {"agent_id": "agent1", "reason": "explanation"}}\n```'
                )
                system_parts.append(
                    "The JSON block should be placed at the very end of your response, after your analysis."
                )

        return "\n".join(system_parts)

    async def _log_backend_input(self, messages, system_prompt, tools, kwargs):
        """Log backend inputs using StreamChunk for visibility (enabled by default)."""
        # Enable by default, but allow disabling via environment variable
        if os.getenv('MASSGEN_LOG_BACKENDS', '1') == '0':
            return
            
        try:
            # Create debug info using the logging approach that works in MassGen
            reset_mode = "🔄 RESET" if kwargs.get('reset_chat') else "💬 CONTINUE"  
            tools_info = f"🔧 {len(tools)} tools" if tools else "🚫 No tools"
            
            debug_info = f"[BACKEND] {reset_mode} | {tools_info} | Session: {self._current_session_id}"
            
            if system_prompt and len(system_prompt) > 0:
                # Show full system prompt in debug logging
                debug_info += f"\n[SYSTEM_FULL] {system_prompt}"
                
                
            # Yield a debug chunk that will be captured by the logging system
            yield StreamChunk(
                type="debug",
                content=debug_info,
                source="claude_code_backend"
            )
                
        except Exception as e:
            # Log the error but don't break backend execution
            yield StreamChunk(
                type="debug",
                content=f"[BACKEND_LOG_ERROR] {str(e)}",
                source="claude_code_backend"
            )

    def extract_structured_response(
        self, response_text: str
    ) -> Optional[Dict[str, Any]]:
        """Extract structured JSON response for Claude Code format.

        Looks for JSON in the format:
        {"tool_name": "vote/new_answer", "arguments": {...}}

        Args:
            response_text: The full response text to search

        Returns:
            Extracted JSON dict if found, None otherwise
        """
        try:
            import re

            # Strategy 0: Look for JSON inside markdown code blocks first
            markdown_json_pattern = r"```json\s*(\{.*?\})\s*```"
            markdown_matches = re.findall(
                markdown_json_pattern, response_text, re.DOTALL
            )

            for match in reversed(markdown_matches):
                try:
                    parsed = json.loads(match.strip())
                    if isinstance(parsed, dict) and "tool_name" in parsed:
                        return parsed
                except json.JSONDecodeError:
                    continue

            # Strategy 1: Look for complete JSON blocks with proper braces
            json_pattern = r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}"
            json_matches = re.findall(json_pattern, response_text, re.DOTALL)

            # Try parsing each match (in reverse order - last one first)
            for match in reversed(json_matches):
                try:
                    cleaned_match = match.strip()
                    parsed = json.loads(cleaned_match)
                    if isinstance(parsed, dict) and "tool_name" in parsed:
                        return parsed
                except json.JSONDecodeError:
                    continue

            # Strategy 2: Look for JSON blocks with nested braces (more complex)
            brace_count = 0
            json_start = -1

            for i, char in enumerate(response_text):
                if char == "{":
                    if brace_count == 0:
                        json_start = i
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0 and json_start >= 0:
                        # Found a complete JSON block
                        json_block = response_text[json_start : i + 1]
                        try:
                            parsed = json.loads(json_block)
                            if isinstance(parsed, dict) and "tool_name" in parsed:
                                return parsed
                        except json.JSONDecodeError:
                            pass
                        json_start = -1

            # Strategy 3: Line-by-line approach (fallback)
            lines = response_text.strip().split("\n")
            json_candidates = []

            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith("{") and stripped.endswith("}"):
                    json_candidates.append(stripped)
                elif stripped.startswith("{"):
                    # Multi-line JSON - collect until closing brace
                    json_text = stripped
                    for j in range(i + 1, len(lines)):
                        json_text += "\n" + lines[j].strip()
                        if lines[j].strip().endswith("}"):
                            json_candidates.append(json_text)
                            break

            # Try to parse each candidate
            for candidate in reversed(json_candidates):
                try:
                    parsed = json.loads(candidate)
                    if isinstance(parsed, dict) and "tool_name" in parsed:
                        return parsed
                except json.JSONDecodeError:
                    continue

            return None

        except Exception:
            return None

    def _parse_workflow_tool_calls(self, text_content: str) -> List[Dict[str, Any]]:
        """Parse workflow tool calls from text content.

        Searches for JSON-formatted tool calls in the response text and
        converts them to the standard tool call format used by MassGen.
        Uses the extract_structured_response method for robust JSON extraction.

        Args:
            text_content: Response text to search for tool calls

        Returns:
            List of unique tool call dictionaries in standard format
        """
        tool_calls = []

        # First try to extract structured JSON response
        structured_response = self.extract_structured_response(text_content)

        if structured_response and isinstance(structured_response, dict):
            tool_name = structured_response.get("tool_name")
            arguments = structured_response.get("arguments", {})

            if tool_name and isinstance(arguments, dict):
                tool_calls.append(
                    {
                        "id": f"call_{uuid.uuid4().hex[:8]}",
                        "type": "function",
                        "function": {"name": tool_name, "arguments": arguments},
                    }
                )
                return tool_calls

        # Fallback: Look for multiple JSON tool calls using regex patterns
        seen_calls = set()  # Track unique tool calls to prevent duplicates

        # Look for JSON tool call patterns
        json_patterns = [
            r'\{"tool_name":\s*"([^"]+)",\s*"arguments":\s*' r"(\{[^}]*\})\}",
            r'\{\s*"tool_name"\s*:\s*"([^"]+)"\s*,\s*"arguments"'
            r"\s*:\s*(\{[^}]*\})\s*\}",
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
                        tool_calls.append(
                            {
                                "id": f"call_{uuid.uuid4().hex[:8]}",
                                "type": "function",
                                "function": {"name": tool_name, "arguments": arguments},
                            }
                        )
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
        cwd_path = options_kwargs.get("cwd", os.getcwd())
        permission_mode = options_kwargs.get("permission_mode", "acceptEdits")
        allowed_tools = options_kwargs.get(
            "allowed_tools", self.get_supported_builtin_tools()
        )

        # Filter out parameters handled separately or not for ClaudeCodeOptions
        excluded_params = {
            "cwd",
            "permission_mode",
            "type",
            "agent_id",
            "session_id",
            "api_key",
            "allowed_tools",
        }

        # Handle cwd - create directory if it doesn't exist and ensure absolute path
        cwd_option = None
        if cwd_path:
            cwd_dir = Path(cwd_path)
            if not cwd_dir.is_absolute():
                # Convert relative path to absolute path
                cwd_dir = cwd_dir.resolve()

            # Create directory if it doesn't exist (files already cleared in __init__ if needed)
            cwd_dir.mkdir(parents=True, exist_ok=True)

            # Ensure we return a valid absolute path
            cwd_option = cwd_dir
            # Update the stored cwd path
            self._cwd = str(cwd_option)

        return ClaudeCodeOptions(
            # No model set by default - let Claude Code decide
            # No allowed_tools restriction - allow ALL tools for maximum
            # power. Security is enforced through disallowed_tools only
            cwd=cwd_option,
            resume=self.get_current_session_id(),
            permission_mode=permission_mode,
            allowed_tools=allowed_tools,
            **{k: v for k, v in options_kwargs.items() if k not in excluded_params},
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
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], **kwargs
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
        # Extract agent_id from kwargs if provided
        agent_id = kwargs.get('agent_id', None)
        
        log_backend_activity(
            self.get_provider_name(),
            "Starting stream_with_tools",
            {"num_messages": len(messages), "num_tools": len(tools) if tools else 0},
            agent_id=agent_id
        )
        # Merge constructor config with stream kwargs (stream kwargs take priority)
        all_params = {**self.config, **kwargs}
        # Check if we already have a client
        if self._client is not None:
            client = self._client
        else:
            # Set default disallowed_tools if not provided
            if "disallowed_tools" not in all_params:
                all_params["disallowed_tools"] = [
                    "Bash(rm*)",
                    "Bash(sudo*)",
                    "Bash(su*)",
                    "Bash(chmod*)",
                    "Bash(chown*)",
                ]

            # Extract system message from messages for append mode (always do this)
            system_msg = next(
                (msg for msg in messages if msg.get("role") == "system"), None
            )
            if system_msg:
                system_content = system_msg.get("content", "")  # noqa: E128
            else:
                system_content = ""
            
            # Build system prompt with tools information
            workflow_system_prompt = self._build_system_prompt_with_workflow_tools(
                tools or [], system_content
            )

            # Windows-specific handling: detect complex prompts that cause subprocess hang
            if sys.platform == "win32" and len(workflow_system_prompt) > 200:
                # Windows with complex prompt: use post-connection delivery to avoid hang
                print(f"[ClaudeCodeBackend] Windows detected complex system prompt, using post-connection delivery")
                clean_params = {k: v for k, v in all_params.items() 
                                if k not in ["system_prompt", "append_system_prompt"]}
                client = self.create_client(**clean_params)
                self._pending_system_prompt = workflow_system_prompt

            else:
                    # Original approach for Mac/Linux and Windows with simple prompts
                try:
                    # Handle different system prompt mode
                    if all_params.get("system_prompt"):
                        # Create client with system_prompt
                        client = self.create_client(
                            **{**all_params, "system_prompt": workflow_system_prompt}
                        )
                    else:
                        # Create client with the enhanced system prompt
                        client = self.create_client(
                            **{**all_params, "append_system_prompt": workflow_system_prompt}
                        )
                    self._pending_system_prompt = None

                except Exception as create_error:
                    # Fallback for unexpected failures
                    if sys.platform == "win32":
                        clean_params = {k: v for k, v in all_params.items() 
                                        if k not in ["system_prompt", "append_system_prompt"]}
                        client = self.create_client(**clean_params)
                        self._pending_system_prompt = workflow_system_prompt
                    else:
                        # On Mac/Linux, re-raise the error since this shouldn't happen
                        raise create_error
                    

        # Connect client if not already connected
        if not client._transport:
            try:
                await client.connect()

                # If we have a pending system prompt, deliver it at system level using /system command
                if hasattr(self, '_pending_system_prompt') and self._pending_system_prompt:
                    try:
                        # Use Claude Code's native /system command for proper system-level delivery
                        system_command = f"/system {self._pending_system_prompt}"
                        await client.query(system_command)

                        # Consume the system response
                        async for response in client.receive_response():
                            if hasattr(response, 'subtype') and response.subtype == 'init':
                                # This is the system initialization response
                                break

                        yield StreamChunk(
                            type="content",
                            content=f"[SYSTEM] Applied system instructions at system level\n",
                            source="claude_code"
                        )

                        # Clear the pending prompt
                        self._pending_system_prompt = None

                    except Exception as sys_e:
                        yield StreamChunk(
                            type="content",
                            content=f"[SYSTEM] Warning: System-level delivery failed: {str(sys_e)}\n",
                            source="claude_code"
                        )

            except Exception as e:
                yield StreamChunk(
                    type="error",
                    error=f"Failed to connect to Claude Code: {str(e)}",
                    source="claude_code"
                )
                return  

        # Log backend inputs when we have workflow_system_prompt available
        if 'workflow_system_prompt' in locals():
            async for debug_chunk in self._log_backend_input(messages, workflow_system_prompt, tools, kwargs):
                yield debug_chunk

        # Format the messages for Claude Code
        if not messages:
            log_stream_chunk("backend.claude_code", "error", "No messages provided to stream_with_tools", agent_id)
            # No messages to process - yield error
            yield StreamChunk(
                type="error",
                error="No messages provided to stream_with_tools",
                source="claude_code",
            )
            return

        # Validate messages - should only contain user messages for Claude Code
        user_messages = [msg for msg in messages if msg.get("role") == "user"]
        assistant_messages = [msg for msg in messages if msg.get("role") == "assistant"]

        if assistant_messages:
            log_stream_chunk("backend.claude_code", "error", "Claude Code backend cannot accept assistant messages - it maintains its own conversation history", agent_id)
            yield StreamChunk(
                type="error",
                error="Claude Code backend cannot accept assistant messages - it maintains its own conversation history",
                source="claude_code",
            )
            return

        if not user_messages:
            log_stream_chunk("backend.claude_code", "error", "No user messages found to send to Claude Code", agent_id)
            yield StreamChunk(
                type="error",
                error="No user messages found to send to Claude Code",
                source="claude_code",
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
            log_backend_agent_message(
                agent_id or "default",
                "SEND",
                {"system": workflow_system_prompt, "user": combined_query},
                backend_name=self.get_provider_name()
            )
            await client.query(combined_query)
        else:
            log_stream_chunk("backend.claude_code", "error", "All user messages were empty", agent_id)
            yield StreamChunk(
                type="error", error="All user messages were empty", source="claude_code"
            )
            return
        
        # Stream response and convert to MassGen StreamChunks
        accumulated_content = ""
        try:
            async for message in client.receive_response():

                if isinstance(message, (AssistantMessage, UserMessage)):
                    # Process assistant message content
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            accumulated_content += block.text

                            # Yield content chunk
                            log_backend_agent_message(
                                agent_id or "default",
                                "RECV",
                                {"content": block.text},
                                backend_name=self.get_provider_name()
                            )
                            log_stream_chunk("backend.claude_code", "content", block.text, agent_id)
                            yield StreamChunk(
                                type="content", content=block.text, source="claude_code"
                            )

                        elif isinstance(block, ToolUseBlock):
                            # Claude Code's builtin tool usage
                            log_backend_activity(
                                self.get_provider_name(),
                                f"Builtin tool called: {block.name}",
                                {"tool_id": block.id},
                                agent_id=agent_id
                            )
                            log_stream_chunk("backend.claude_code", "tool_use", {"name": block.name, "input": block.input}, agent_id)
                            yield StreamChunk(
                                type="content",
                                content=f"🔧 {block.name}({block.input})",
                                source="claude_code",
                            )

                        elif isinstance(block, ToolResultBlock):
                            # Tool result from Claude Code - use simple content format
                            # Note: ToolResultBlock.tool_use_id references
                            # the original ToolUseBlock.id
                            status = "❌ Error" if block.is_error else "✅ Result"
                            log_stream_chunk("backend.claude_code", "tool_result", {"is_error": block.is_error, "content": block.content}, agent_id)
                            yield StreamChunk(
                                type="content",
                                content=f"🔧 Tool {status}: {block.content}",
                                source="claude_code",
                            )

                    # Parse workflow tool calls from accumulated content
                    workflow_tool_calls = self._parse_workflow_tool_calls(
                        accumulated_content
                    )
                    if workflow_tool_calls:
                        log_stream_chunk("backend.claude_code", "tool_calls", workflow_tool_calls, agent_id)
                        yield StreamChunk(
                            type="tool_calls",
                            tool_calls=workflow_tool_calls,
                            source="claude_code",
                        )

                    # Yield complete message
                    log_stream_chunk("backend.claude_code", "complete_message", accumulated_content[:200] if len(accumulated_content) > 200 else accumulated_content, agent_id)
                    yield StreamChunk(
                        type="complete_message",
                        complete_message={
                            "role": "assistant",
                            "content": accumulated_content,
                        },
                        source="claude_code",
                    )

                elif isinstance(message, SystemMessage):
                    # System status updates
                    self._track_session_info(message=message)
                    log_stream_chunk("backend.claude_code", "backend_status", {"subtype": message.subtype, "data": message.data}, agent_id)
                    yield StreamChunk(
                        type="backend_status",
                        status=message.subtype,
                        content=json.dumps(message.data),
                        source="claude_code",
                    )

                elif isinstance(message, ResultMessage):
                    # Track session ID from server response
                    self._track_session_info(message)

                    # Update token usage using ResultMessage data
                    self.update_token_usage_from_result_message(message)

                    # Yield completion
                    log_stream_chunk("backend.claude_code", "complete_response", {"session_id": message.session_id, "cost_usd": message.total_cost_usd}, agent_id)
                    yield StreamChunk(
                        type="complete_response",
                        complete_message={
                            "session_id": message.session_id,
                            "duration_ms": message.duration_ms,
                            "cost_usd": message.total_cost_usd,
                            "usage": message.usage,
                            "is_error": message.is_error,
                        },
                        source="claude_code",
                    )

                    # Final done signal
                    log_stream_chunk("backend.claude_code", "done", None, agent_id)
                    yield StreamChunk(type="done", source="claude_code")
                    break

        except Exception as e:
            error_msg = str(e)

            # Provide helpful Windows-specific guidance
            if "git-bash" in error_msg.lower() or "bash.exe" in error_msg.lower():
                error_msg += "\n\nWindows Setup Required:\n1. Install Git Bash: https://git-scm.com/downloads/win\n2. Ensure git-bash is in PATH, or set: CLAUDE_CODE_GIT_BASH_PATH=C:\\Program Files\\Git\\bin\\bash.exe"
            elif "exit code 1" in error_msg and "win32" in str(sys.platform):
                error_msg += "\n\nThis may indicate missing git-bash on Windows. Please install Git Bash from https://git-scm.com/downloads/win"

            log_stream_chunk("backend.claude_code", "error", error_msg, agent_id)
            yield StreamChunk(
                type="error",
                error=f"Claude Code streaming error: {str(error_msg)}",
                source="claude_code",
            )

    def _track_session_info(self, message) -> None:
        """Track session information from Claude Code server responses.

        Extracts and stores session ID, working directory, and other session
        metadata from ResultMessage and SystemMessage responses to enable
        session continuation and state management across multiple interactions.

        Args:
            message: Message from Claude Code (ResultMessage or SystemMessage)
                    potentially containing session information
        """
        if ResultMessage is not None and isinstance(message, ResultMessage):
            # ResultMessage contains definitive session information
            if hasattr(message, "session_id") and message.session_id:
                old_session_id = self._current_session_id
                self._current_session_id = message.session_id

        elif SystemMessage is not None and isinstance(message, SystemMessage):
            # SystemMessage may contain session state updates
            if hasattr(message, "data") and isinstance(message.data, dict):
                # Extract session ID from system message data
                if "session_id" in message.data and message.data["session_id"]:
                    old_session_id = self._current_session_id
                    self._current_session_id = message.data["session_id"]
                    if old_session_id != self._current_session_id:
                        print(
                            f"[ClaudeCodeBackend] Session ID from SystemMessage: {old_session_id} → {self._current_session_id}"
                        )

                # Extract working directory from system message data
                if "cwd" in message.data and message.data["cwd"]:
                    self._cwd = message.data["cwd"]

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
