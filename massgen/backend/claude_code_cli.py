"""
Claude Code CLI Backend - Interface for Claude Code CLI.

This backend provides integration with Anthropic's Claude Code CLI tool,
allowing MassGen to use Claude Code's capabilities through its command-line interface.

Requirements:
- Claude Code CLI installed: npm install -g @anthropic-ai/claude-code
- Anthropic API key configured in environment or passed explicitly
"""

import json
import os
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional

from .cli_base import CLIBackend


class ClaudeCodeCLIBackend(CLIBackend):
    """Backend for Claude Code CLI integration."""
    
    def __init__(self, api_key: Optional[str] = None, **kwargs):
        # Check if Claude Code CLI is installed
        if not shutil.which("claude"):
            raise RuntimeError(
                "Claude Code CLI not found. Please install it with: "
                "npm install -g @anthropic-ai/claude-code"
            )
        
        super().__init__("claude", api_key, **kwargs)
        
        # Claude Code CLI specific configuration
        self.model = kwargs.get("model", "sonnet")  # Default to sonnet
        self.max_turns = kwargs.get("max_turns", 5)
        self.verbose = kwargs.get("verbose", False)
        
        # Set API key in environment if provided
        if api_key:
            os.environ["ANTHROPIC_API_KEY"] = api_key
    
    def _build_command(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], **kwargs) -> List[str]:
        """Build Claude Code CLI command."""
        # Format the conversation into a single prompt
        prompt = self._format_messages_for_claude_code(messages, tools)
        
        # Build base command
        command = [
            "claude",
            "-p",  # Print mode (non-interactive)
            prompt,
            "--output-format", "json",  # Get structured output
            "--model", self.model,
            "--max-turns", str(self.max_turns)
        ]
        
        # Add verbose flag if requested
        if self.verbose:
            command.append("--verbose")
        
        return command
    
    def _format_messages_for_claude_code(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> str:
        """Format messages specifically for Claude Code CLI."""
        formatted_parts = []
        
        # Add system message if present
        system_msg = next((msg for msg in messages if msg.get("role") == "system"), None)
        if system_msg:
            formatted_parts.append(f"System instructions: {system_msg.get('content', '')}")
        
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
            formatted_parts.append("Conversation:\\n" + "\\n".join(conversation_parts))
        
        # Add available tools information
        if tools:
            tools_info = self._format_tools_for_claude_code(tools)
            formatted_parts.append(f"Available tools: {tools_info}")
        
        return "\\n\\n".join(formatted_parts)
    
    def _format_tools_for_claude_code(self, tools: List[Dict[str, Any]]) -> str:
        """Format tools information for Claude Code."""
        if not tools:
            return "None"
        
        tool_descriptions = []
        for tool in tools:
            name = tool.get("function", {}).get("name", "unknown")
            description = tool.get("function", {}).get("description", "No description")
            tool_descriptions.append(f"- {name}: {description}")
        
        return "\\n".join(tool_descriptions)
    
    def _parse_output(self, output: str) -> Dict[str, Any]:
        """Parse Claude Code CLI JSON output."""
        try:
            # Claude Code CLI with --output-format json returns structured data
            parsed = json.loads(output.strip())
            
            # Extract the main response content
            content = ""
            tool_calls = []
            
            if isinstance(parsed, dict):
                # Handle different possible JSON structures
                if "response" in parsed:
                    content = parsed["response"]
                elif "content" in parsed:
                    content = parsed["content"]
                elif "text" in parsed:
                    content = parsed["text"]
                else:
                    # Fallback: use the entire parsed object as string
                    content = str(parsed)
                
                # Check for tool calls (if Claude Code CLI supports them in JSON output)
                if "tool_calls" in parsed:
                    tool_calls = parsed["tool_calls"]
                elif "tools" in parsed:
                    tool_calls = parsed["tools"]
            
            elif isinstance(parsed, str):
                content = parsed
            else:
                content = str(parsed)
            
            return {
                "content": content,
                "tool_calls": tool_calls,
                "raw_response": parsed
            }
            
        except json.JSONDecodeError:
            # Fallback: treat as plain text
            return {
                "content": output.strip(),
                "tool_calls": [],
                "raw_response": output
            }
    
    def get_cost_per_token(self) -> Dict[str, float]:
        """Get Claude Code cost per token estimates."""
        # These are approximate costs for Claude models
        model_costs = {
            "sonnet": {"input": 3.0e-6, "output": 15.0e-6},  # Claude Sonnet
            "opus": {"input": 15.0e-6, "output": 75.0e-6},   # Claude Opus
            "haiku": {"input": 0.25e-6, "output": 1.25e-6},  # Claude Haiku
        }
        
        return model_costs.get(self.model, {"input": 3.0e-6, "output": 15.0e-6})
    
    def get_model_name(self) -> str:
        """Get the Claude model name."""
        return f"claude-{self.model}"
    
    def get_provider_info(self) -> Dict[str, Any]:
        """Get Claude Code CLI provider information."""
        info = super().get_provider_info()
        info.update({
            "provider": "claude-code-cli",
            "model": self.get_model_name(),
            "max_turns": self.max_turns,
            "supports_builtin_tools": True,  # Claude Code has built-in tools
            "supports_file_operations": True,  # Claude Code can read/write files
            "supports_code_execution": True,  # Claude Code can run commands
        })
        return info