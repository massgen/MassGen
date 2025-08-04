"""
CLI Backend Base Class - Abstract interface for CLI-based LLM backends.

This module provides the base class for backends that interact with LLM providers
through command-line interfaces (like Claude Code CLI, Gemini CLI, etc.).
"""

import asyncio
import json
import subprocess
import tempfile
from abc import abstractmethod
from typing import Dict, List, Any, AsyncGenerator, Optional
from pathlib import Path

from .base import LLMBackend, StreamChunk, TokenUsage


class CLIBackend(LLMBackend):
    """Abstract base class for CLI-based LLM backends."""
    
    def __init__(self, cli_command: str, api_key: Optional[str] = None, **kwargs):
        super().__init__(api_key, **kwargs)
        self.cli_command = cli_command
        self.working_dir = kwargs.get("working_dir", Path.cwd())
        self.timeout = kwargs.get("timeout", 300)  # 5 minutes default
        
    @abstractmethod
    def _build_command(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], **kwargs) -> List[str]:
        """Build the CLI command to execute.
        
        Args:
            messages: Conversation messages
            tools: Available tools
            **kwargs: Additional parameters
            
        Returns:
            List of command arguments for subprocess
        """
        pass
    
    @abstractmethod
    def _parse_output(self, output: str) -> Dict[str, Any]:
        """Parse CLI output into structured format.
        
        Args:
            output: Raw CLI output
            
        Returns:
            Parsed response data
        """
        pass
    
    async def _execute_cli_command(self, command: List[str]) -> str:
        """Execute CLI command asynchronously.
        
        Args:
            command: Command arguments
            
        Returns:
            Command output
            
        Raises:
            subprocess.CalledProcessError: If command fails
            asyncio.TimeoutError: If command times out
        """
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.working_dir
        )
        
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=self.timeout
            )
            
            if process.returncode != 0:
                error_msg = stderr.decode('utf-8') if stderr else "Unknown error"
                raise subprocess.CalledProcessError(process.returncode, command, error_msg)
                
            return stdout.decode('utf-8')
            
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise asyncio.TimeoutError(f"CLI command timed out after {self.timeout} seconds")
    
    def _create_temp_file(self, content: str, suffix: str = ".txt") -> Path:
        """Create a temporary file with content.
        
        Args:
            content: File content
            suffix: File suffix
            
        Returns:
            Path to temporary file
        """
        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False)
        temp_file.write(content)
        temp_file.close()
        return Path(temp_file.name)
    
    def _format_messages_for_cli(self, messages: List[Dict[str, Any]]) -> str:
        """Format messages for CLI input.
        
        Args:
            messages: Conversation messages
            
        Returns:
            Formatted string for CLI
        """
        formatted_parts = []
        
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            if role == "system":
                formatted_parts.append(f"System: {content}")
            elif role == "user":
                formatted_parts.append(f"User: {content}")
            elif role == "assistant":
                formatted_parts.append(f"Assistant: {content}")
                
        return "\n\n".join(formatted_parts)
    
    async def stream_with_tools(
        self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """Stream response with tools support."""
        try:
            # Build CLI command
            command = self._build_command(messages, tools, **kwargs)
            
            # Execute command
            output = await self._execute_cli_command(command)
            
            # Parse output
            parsed_response = self._parse_output(output)
            
            # Convert to stream chunks
            async for chunk in self._convert_to_stream_chunks(parsed_response):
                yield chunk
                
        except Exception as e:
            yield StreamChunk(
                type="error",
                error=f"CLI backend error: {str(e)}",
                source=self.__class__.__name__
            )
    
    async def _convert_to_stream_chunks(self, response: Dict[str, Any]) -> AsyncGenerator[StreamChunk, None]:
        """Convert parsed response to stream chunks.
        
        Args:
            response: Parsed response data
            
        Yields:
            StreamChunk objects
        """
        # Yield content
        if "content" in response and response["content"]:
            yield StreamChunk(
                type="content",
                content=response["content"],
                source=self.__class__.__name__
            )
        
        # Yield tool calls if present
        if "tool_calls" in response and response["tool_calls"]:
            yield StreamChunk(
                type="tool_calls",
                tool_calls=response["tool_calls"],
                source=self.__class__.__name__
            )
        
        # Yield complete message
        yield StreamChunk(
            type="complete_message",
            complete_message=response,
            source=self.__class__.__name__
        )
        
        # Yield done
        yield StreamChunk(
            type="done",
            source=self.__class__.__name__
        )
    
    def get_token_usage(self) -> TokenUsage:
        """Get token usage statistics."""
        # CLI backends typically don't provide detailed token usage
        # This could be estimated or left as zero
        return self.token_usage
    
    def get_cost_per_token(self) -> Dict[str, float]:
        """Get cost per token for this provider."""
        # Override in specific implementations
        return {"input": 0.0, "output": 0.0}
    
    def get_model_name(self) -> str:
        """Get the model name being used."""
        return self.config.get("model", "unknown")
    
    def get_provider_info(self) -> Dict[str, Any]:
        """Get provider information."""
        return {
            "provider": self.__class__.__name__,
            "cli_command": self.cli_command,
            "model": self.get_model_name(),
            "supports_tools": True,
            "supports_streaming": True,
        }
    
    def get_provider_name(self) -> str:
        """Get the name of this provider."""
        return self.__class__.__name__
    
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text (rough approximation)."""
        # Rough estimation: ~4 characters per token for most models
        return len(text) // 4
    
    def calculate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """Calculate cost for token usage."""
        costs = self.get_cost_per_token()
        return (input_tokens * costs.get("input", 0.0)) + (output_tokens * costs.get("output", 0.0))