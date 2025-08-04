"""
Gemini CLI Backend - Interface for Google's Gemini CLI.

This backend provides integration with Google's Gemini CLI tool,
allowing MassGen to use Gemini CLI's capabilities through its command-line interface.

Requirements:
- Gemini CLI installed: npm install -g @google/gemini-cli or brew install gemini-cli
- Google account authentication or Gemini API key configured
"""

import asyncio
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional

from .cli_base import CLIBackend


class GeminiCLIBackend(CLIBackend):
    """Backend for Gemini CLI integration."""
    
    def __init__(self, api_key: Optional[str] = None, **kwargs):
        # Check if Gemini CLI is installed
        if not shutil.which("gemini"):
            raise RuntimeError(
                "Gemini CLI not found. Please install it with: "
                "npm install -g @google/gemini-cli or brew install gemini-cli"
            )
        
        super().__init__("gemini", api_key, **kwargs)
        
        # Gemini CLI specific configuration
        self.model = kwargs.get("model", "gemini-2.5-pro")
        self.temperature = kwargs.get("temperature", 0.7)
        
        # Set API key in environment if provided
        if api_key:
            os.environ["GEMINI_API_KEY"] = api_key
    
    def _build_command(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], **kwargs) -> List[str]:
        """Build Gemini CLI command.
        
        Note: Gemini CLI is primarily interactive, so we need to work around this
        by using input redirection or temporary files.
        """
        # Format the conversation into a single prompt
        prompt = self._format_messages_for_gemini_cli(messages, tools)
        
        # Create a temporary file with the prompt
        temp_file = self._create_temp_file(prompt, suffix=".txt")
        
        # Since Gemini CLI doesn't have a direct non-interactive mode,
        # we'll use input redirection with a timeout
        command = [
            "timeout", "60",  # 60 second timeout
            "gemini"
        ]
        
        # Store temp file path for cleanup
        self._temp_file = temp_file
        
        return command
    
    async def _execute_cli_command(self, command: List[str]) -> str:
        """Execute Gemini CLI command with input redirection."""
        # Read the prompt from temp file
        prompt_content = self._temp_file.read_text()
        
        # Execute command with input
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.working_dir
        )
        
        try:
            # Send the prompt and add exit command
            input_data = f"{prompt_content}\\n/exit\\n"
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(input_data.encode('utf-8')),
                timeout=self.timeout
            )
            
            # Clean up temp file
            self._temp_file.unlink(missing_ok=True)
            
            if process.returncode not in [0, 124]:  # 124 is timeout exit code
                error_msg = stderr.decode('utf-8') if stderr else "Unknown error"
                if "timeout" not in error_msg.lower():
                    raise subprocess.CalledProcessError(process.returncode, command, error_msg)
                
            return stdout.decode('utf-8')
            
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            self._temp_file.unlink(missing_ok=True)
            raise asyncio.TimeoutError(f"Gemini CLI command timed out after {self.timeout} seconds")
    
    def _format_messages_for_gemini_cli(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> str:
        """Format messages specifically for Gemini CLI."""
        formatted_parts = []
        
        # Add system message if present
        system_msg = next((msg for msg in messages if msg.get("role") == "system"), None)
        if system_msg:
            formatted_parts.append(f"Instructions: {system_msg.get('content', '')}")
        
        # Add conversation history
        conversation_parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if role == "user":
                conversation_parts.append(content)
            elif role == "assistant":
                conversation_parts.append(f"Previous response: {content}")
        
        # The last user message becomes the main prompt
        if conversation_parts:
            if len(conversation_parts) > 1:
                formatted_parts.extend(conversation_parts[:-1])
            formatted_parts.append(conversation_parts[-1])
        
        # Add available tools information
        if tools:
            tools_info = self._format_tools_for_gemini_cli(tools)
            formatted_parts.append(f"\\nAvailable tools: {tools_info}")
        
        return "\\n\\n".join(formatted_parts)
    
    def _format_tools_for_gemini_cli(self, tools: List[Dict[str, Any]]) -> str:
        """Format tools information for Gemini CLI."""
        if not tools:
            return "None"
        
        tool_descriptions = []
        for tool in tools:
            name = tool.get("function", {}).get("name", "unknown")
            description = tool.get("function", {}).get("description", "No description")
            tool_descriptions.append(f"- {name}: {description}")
        
        return "\\n".join(tool_descriptions)
    
    def _parse_output(self, output: str) -> Dict[str, Any]:
        """Parse Gemini CLI output.
        
        Since Gemini CLI doesn't have structured output mode,
        we need to parse the interactive session output.
        """
        # Clean up the output
        lines = output.strip().split('\\n')
        
        # Remove CLI prompt artifacts and control characters
        cleaned_lines = []
        for line in lines:
            # Skip empty lines and CLI prompts
            line = line.strip()
            if line and not line.startswith('>') and not line.startswith('gemini'):
                # Remove ANSI color codes
                line = re.sub(r'\\x1b\\[[0-9;]*m', '', line)
                cleaned_lines.append(line)
        
        # Join the cleaned content
        content = '\\n'.join(cleaned_lines)
        
        # Try to extract structured information
        tool_calls = []
        
        # Look for tool usage patterns (this would depend on Gemini CLI's output format)
        # This is a simplified approach - would need refinement based on actual Gemini CLI behavior
        tool_pattern = r'/tools\\s+(\\w+)'
        tool_matches = re.findall(tool_pattern, content)
        if tool_matches:
            for tool_name in tool_matches:
                tool_calls.append({
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": "{}"
                    }
                })
        
        return {
            "content": content,
            "tool_calls": tool_calls,
            "raw_response": output
        }
    
    def get_cost_per_token(self) -> Dict[str, float]:
        """Get Gemini cost per token estimates."""
        # These are approximate costs for Gemini models
        model_costs = {
            "gemini-2.5-pro": {"input": 1.25e-6, "output": 5.0e-6},
            "gemini-2.5-flash": {"input": 0.075e-6, "output": 0.3e-6},
            "gemini-1.5-pro": {"input": 1.25e-6, "output": 5.0e-6},
            "gemini-1.5-flash": {"input": 0.075e-6, "output": 0.3e-6},
        }
        
        return model_costs.get(self.model, {"input": 1.25e-6, "output": 5.0e-6})
    
    def get_model_name(self) -> str:
        """Get the Gemini model name."""
        return self.model
    
    def get_provider_info(self) -> Dict[str, Any]:
        """Get Gemini CLI provider information."""
        info = super().get_provider_info()
        info.update({
            "provider": "gemini-cli",
            "model": self.get_model_name(),
            "temperature": self.temperature,
            "supports_builtin_tools": True,  # Gemini CLI has built-in tools
            "supports_file_operations": True,  # Gemini CLI can work with files
            "supports_code_execution": True,  # Gemini CLI can execute code
            "interactive_only": True,  # Gemini CLI is primarily interactive
        })
        return info