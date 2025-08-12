"""
Gemini CLI Backend - Interface for Google's Gemini CLI.

This backend provides integration with Google's Gemini CLI tool,
allowing MassGen to use Gemini CLI's capabilities through its command-line interface.

Key Features:
- Native Gemini CLI integration
- One-shot command execution (stateless backend)
- Built-in tool execution capabilities
- MassGen workflow tool integration (new_answer, vote via system prompts)
- Streaming interface with async support
- Cost tracking and token usage estimation

Architecture:
- Uses Gemini CLI in one-shot mode (each request is independent)
- Maintains conversation history locally for context
- Supports streaming responses with proper chunk handling
- Injects MassGen workflow tools via system prompts
- Converts CLI output to MassGen StreamChunks

Requirements:
- Gemini CLI installed: npm install -g @google/gemini-cli or brew install gemini-cli
- Google account authentication or Gemini API key configured
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import uuid
from typing import Dict, List, Any, Optional, AsyncGenerator

from .base import LLMBackend, StreamChunk


class GeminiCLIBackend(LLMBackend):
    """Gemini CLI backend using command-line interface.

    Provides streaming interface to Gemini CLI with built-in tool execution
    capabilities and MassGen workflow tool integration. Uses one-shot commands
    for each request, maintaining conversation history locally for context.
    """
    
    def __init__(self, api_key: Optional[str] = None, **kwargs):
        """Initialize GeminiCLIBackend.

        Args:
            api_key: Gemini API key (falls back to GEMINI_API_KEY env var)
            **kwargs: Additional configuration options including:
                - model: Gemini model name
                - temperature: Temperature for response generation
                - system_prompt: Base system prompt
                - allowed_tools: List of allowed tools
                - cwd: Current working directory
        """
        # Check if Gemini CLI is installed
        if not shutil.which("gemini"):
            raise RuntimeError(
                "Gemini CLI not found. Please install it with: "
                "npm install -g @google/gemini-cli or brew install gemini-cli"
            )
        
        super().__init__(api_key, **kwargs)
        
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        
        # Gemini CLI specific configuration
        self.model = kwargs.get("model", "gemini-2.5-flash")
        self.temperature = kwargs.get("temperature", 0.7)
        self.timeout = kwargs.get("timeout", 300)  # 5 minutes default
        
        # Set API key in environment if provided
        if self.api_key:
            os.environ["GEMINI_API_KEY"] = self.api_key
        
        # Working directory for command execution
        self._working_dir = kwargs.get("cwd", os.getcwd())
        
        # Conversation history for context (since we're stateless)
        self._conversation_history: List[Dict[str, str]] = []
    
    def get_provider_name(self) -> str:
        """Get the name of this provider."""
        return "gemini_cli"

    def is_stateful(self) -> bool:
        """
        Gemini CLI backend is now stateless - uses one-shot commands.
        
        Returns:
            False - Each request is independent
        """
        return False

    async def clear_history(self) -> None:
        """
        Clear conversation history.
        
        Since we're using one-shot commands, this just clears
        the internal conversation history.
        """
        self._conversation_history = []

    async def reset_state(self) -> None:
        """
        Reset Gemini CLI backend state.
        
        Clears conversation history for stateless operation.
        """
        self._conversation_history = []
    
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text (approximation for Gemini)."""
        # Gemini tokenization approximation: ~3.5-4 characters per token
        return max(1, len(text.encode('utf-8')) // 4)

    def calculate_cost(
            self, input_tokens: int, output_tokens: int,
            model: str) -> float:
        """Calculate cost for token usage based on Gemini pricing."""
        model_lower = model.lower()
        
        # Gemini pricing (2025)
        if "2.5-pro" in model_lower:
            input_cost_per_token = 1.25 / 1_000_000   # $1.25 per million
            output_cost_per_token = 5.0 / 1_000_000   # $5.00 per million
        elif "2.5-flash" in model_lower:
            input_cost_per_token = 0.075 / 1_000_000  # $0.075 per million
            output_cost_per_token = 0.3 / 1_000_000   # $0.30 per million
        elif "1.5-pro" in model_lower:
            input_cost_per_token = 1.25 / 1_000_000   # $1.25 per million
            output_cost_per_token = 5.0 / 1_000_000   # $5.00 per million
        elif "1.5-flash" in model_lower:
            input_cost_per_token = 0.075 / 1_000_000  # $0.075 per million
            output_cost_per_token = 0.3 / 1_000_000   # $0.30 per million
        else:
            # Default to 2.5-flash pricing
            input_cost_per_token = 0.075 / 1_000_000
            output_cost_per_token = 0.3 / 1_000_000
            
        return ((input_tokens * input_cost_per_token) +
                (output_tokens * output_cost_per_token))

    def update_token_usage(
            self, messages: List[Dict[str, Any]], response_content: str,
            model: str):
        """Update token usage tracking."""
        # Estimate input tokens from messages
        input_text = "\n".join([msg.get("content", "") for msg in messages])
        input_tokens = self.estimate_tokens(input_text)
        
        # Estimate output tokens from response
        output_tokens = self.estimate_tokens(response_content)
        
        # Update totals
        self.token_usage.input_tokens += input_tokens
        self.token_usage.output_tokens += output_tokens
        
        # Calculate cost
        cost = self.calculate_cost(input_tokens, output_tokens, model)
        self.token_usage.estimated_cost += cost
    
    def get_supported_builtin_tools(self) -> List[str]:
        """Get list of builtin tools supported by Gemini CLI."""
        return [
            "code_execution", "search", "file_operations", "calculation"
        ]

    def _build_system_prompt_with_workflow_tools(
            self, tools: List[Dict[str, Any]],
            base_system: Optional[str] = None) -> str:
        """Build system prompt that includes workflow tools information."""
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
                    "IMPORTANT: You must respond with a structured JSON decision at the end of your response.")
                system_parts.append(
                    "You must use the coordination tools (new_answer, vote) "
                    "to participate in multi-agent workflows.")
                system_parts.append(
                    "The JSON MUST be formatted as a strict JSON code block:")
                system_parts.append(
                    "1. Start with ```json on one line")
                system_parts.append(
                    "2. Include your JSON content (properly formatted)")
                system_parts.append(
                    "3. End with ``` on one line")
                system_parts.append(
                    "Example format:\n```json\n{\"tool_name\": \"vote\", \"arguments\": {\"agent_id\": \"agent1\", \"reason\": \"explanation\"}}\n```")
                system_parts.append(
                    "The JSON block should be placed at the very end of your response, after your analysis.")
        
        return "\n".join(system_parts)
    
    def extract_structured_response(
            self, response_text: str) -> Optional[Dict[str, Any]]:
        """Extract structured JSON response from Gemini CLI output."""
        try:
            # Strategy 1: Look for JSON inside markdown code blocks first
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
            
            # Strategy 2: Look for complete JSON blocks
            json_pattern = r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}"
            json_matches = re.findall(json_pattern, response_text, re.DOTALL)
            
            for match in reversed(json_matches):
                try:
                    cleaned_match = match.strip()
                    parsed = json.loads(cleaned_match)
                    if isinstance(parsed, dict) and "tool_name" in parsed:
                        return parsed
                except json.JSONDecodeError:
                    continue
            
            return None
            
        except Exception:
            return None
    
    def _parse_workflow_tool_calls(
            self, text_content: str) -> List[Dict[str, Any]]:
        """Parse workflow tool calls from text content."""
        tool_calls = []
        
        # Try to extract structured JSON response
        structured_response = self.extract_structured_response(text_content)
        
        if structured_response and isinstance(structured_response, dict):
            tool_name = structured_response.get("tool_name")
            arguments = structured_response.get("arguments", {})
            
            if tool_name and isinstance(arguments, dict):
                tool_calls.append({
                    "id": f"call_{uuid.uuid4().hex[:8]}",
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": arguments
                    }
                })
        
        return tool_calls

    def _build_command(self, prompt: str) -> List[str]:
        """Build Gemini CLI command for one-shot execution."""
        command = ["gemini"]
        
        # Add model if specified
        if self.model:
            command.extend(["--model", self.model])
        
        # Add the prompt 
        command.extend(["--prompt", prompt])
        
        # Note: Gemini CLI doesn't support temperature parameter
        # Temperature control would need to be done via model selection
        
        return command
    
    def _format_conversation_context(self, messages: List[Dict[str, Any]]) -> str:
        """Format conversation history and messages into a single prompt."""
        prompt_parts = []
        
        # Add conversation history
        for hist in self._conversation_history:
            role = hist.get("role", "user")
            content = hist.get("content", "")
            if content:
                prompt_parts.append(f"{role.capitalize()}: {content}")
        
        # Add current messages
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if content and role != "system":  # System prompt handled separately
                prompt_parts.append(f"{role.capitalize()}: {content}")
        
        return "\n\n".join(prompt_parts)
    
    async def stream_with_tools(
            self, messages: List[Dict[str, Any]],
            tools: List[Dict[str, Any]], **_kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream a response with tool calling support using Gemini CLI."""
        try:
            # Extract system message and build system prompt
            system_msg = next(
                (msg for msg in messages if msg.get("role") == "system"), None)
            system_content = system_msg.get('content', '') if system_msg else ''
            
            # Build system prompt with tools information
            workflow_system_prompt = (
                self._build_system_prompt_with_workflow_tools(
                    tools or [], system_content))
            
            # Format the complete prompt
            conversation_context = self._format_conversation_context(messages)
            
            # Combine system prompt and conversation
            full_prompt_parts = []
            if workflow_system_prompt.strip():
                full_prompt_parts.append(f"System: {workflow_system_prompt}")
            if conversation_context.strip():
                full_prompt_parts.append(conversation_context)
            
            full_prompt = "\n\n".join(full_prompt_parts)
            
            if not full_prompt.strip():
                yield StreamChunk(
                    type="error",
                    error="No content to send to Gemini CLI",
                    source="gemini_cli"
                )
                return
            
            # Build and execute command
            command = self._build_command(full_prompt)
            
            # Execute as one-shot command
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._working_dir
            )
            
            # Read response with streaming
            accumulated_content = ""
            
            # Read stdout line by line for streaming effect
            while True:
                try:
                    line = await asyncio.wait_for(
                        process.stdout.readline(),
                        timeout=5.0  # Shorter timeout for line reading
                    )
                    
                    if not line:
                        break
                    
                    decoded_line = line.decode('utf-8').rstrip('\n')
                    
                    # Clean ANSI codes
                    cleaned_line = re.sub(r'\x1b\[[0-9;]*m', '', decoded_line)
                    
                    if cleaned_line.strip():
                        accumulated_content += cleaned_line + "\n"
                        
                        # Yield content chunk
                        yield StreamChunk(
                            type="content",
                            content=cleaned_line + "\n",
                            source="gemini_cli"
                        )
                        
                except asyncio.TimeoutError:
                    # Timeout on individual line read, continue to next
                    continue
            
            # Wait for process to complete
            try:
                await asyncio.wait_for(process.wait(), timeout=self.timeout)
            except asyncio.TimeoutError:
                process.terminate()
                await process.wait()
                yield StreamChunk(
                    type="error",
                    error="Gemini CLI command timed out",
                    source="gemini_cli"
                )
                return
            
            # Check for errors
            if process.returncode != 0:
                stderr = await process.stderr.read()
                error_msg = stderr.decode('utf-8') if stderr else "Unknown error"
                yield StreamChunk(
                    type="error",
                    error=f"Gemini CLI error (code {process.returncode}): {error_msg}",
                    source="gemini_cli"
                )
                return
            
            # Parse workflow tool calls
            workflow_tool_calls = self._parse_workflow_tool_calls(accumulated_content)
            if workflow_tool_calls:
                yield StreamChunk(
                    type="tool_calls",
                    tool_calls=workflow_tool_calls,
                    source="gemini_cli"
                )
            
            # Update conversation history for context
            # Add user message
            user_messages = [msg for msg in messages if msg.get("role") == "user"]
            if user_messages:
                last_user_msg = user_messages[-1]
                self._conversation_history.append({
                    "role": "user",
                    "content": last_user_msg.get("content", "")
                })
            
            # Add assistant response
            self._conversation_history.append({
                "role": "assistant",
                "content": accumulated_content
            })
            
            # Keep history size reasonable (last 10 exchanges)
            if len(self._conversation_history) > 20:
                self._conversation_history = self._conversation_history[-20:]
            
            # Update token usage
            self.update_token_usage(messages, accumulated_content, self.model)
            
            # Yield complete message
            yield StreamChunk(
                type="complete_message",
                complete_message={
                    "role": "assistant",
                    "content": accumulated_content
                },
                source="gemini_cli"
            )
            
            # Yield completion
            yield StreamChunk(
                type="complete_response",
                complete_message={
                    "cost_usd": self.token_usage.estimated_cost,
                    "usage": {
                        "input_tokens": self.token_usage.input_tokens,
                        "output_tokens": self.token_usage.output_tokens
                    }
                },
                source="gemini_cli"
            )
            
            # Final done signal
            yield StreamChunk(type="done", source="gemini_cli")
            
        except Exception as e:
            yield StreamChunk(
                type="error",
                error=f"Gemini CLI streaming error: {str(e)}",
                source="gemini_cli"
            )

    async def disconnect(self):
        """Disconnect and clean up resources."""
        # Clear conversation history
        await self.reset_state()