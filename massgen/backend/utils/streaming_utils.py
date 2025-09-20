"""
Streaming utilities for backend implementations.
Provides common patterns for handling streaming responses.
"""

from __future__ import annotations

import asyncio
import json
from typing import Dict, List, Any, Optional, AsyncGenerator, Callable
from dataclasses import dataclass, field
from ..base import StreamChunk


class StreamAccumulator:
    """
    Helper class for accumulating streaming chunks.
    Used by all streaming backends to collect partial data.
    """
    
    def __init__(self):
        self.content: str = ""
        self.tool_calls: Dict[int, Dict[str, Any]] = {}
        self.metadata: Dict[str, Any] = {}
        self.finish_reason: Optional[str] = None
        self.usage: Optional[Dict[str, int]] = None
        
    def add_content(self, delta: str):
        """Add content delta to accumulated content."""
        if delta:
            self.content += delta
    
    def add_tool_call(self, index: int, call_data: Dict[str, Any]):
        """
        Add or update a tool call at the given index.
        
        Args:
            index: Tool call index
            call_data: Partial tool call data to merge
        """
        if index not in self.tool_calls:
            self.tool_calls[index] = {
                "id": "",
                "type": "function",
                "function": {"name": "", "arguments": ""}
            }
        
        # Merge the call data
        if "id" in call_data and call_data["id"]:
            self.tool_calls[index]["id"] = call_data["id"]
        
        if "function" in call_data:
            func_data = call_data["function"]
            if "name" in func_data:
                self.tool_calls[index]["function"]["name"] += func_data["name"]
            if "arguments" in func_data:
                self.tool_calls[index]["function"]["arguments"] += func_data["arguments"]
    
    def add_metadata(self, key: str, value: Any):
        """Add metadata to accumulator."""
        self.metadata[key] = value
    
    def set_finish_reason(self, reason: str):
        """Set the finish reason for the stream."""
        self.finish_reason = reason
    
    def set_usage(self, usage: Dict[str, int]):
        """Set token usage information."""
        self.usage = usage
    
    def to_message(self) -> Dict[str, Any]:
        """
        Convert accumulated data to a complete message.
        
        Returns:
            Complete message dictionary
        """
        message = {"role": "assistant"}
        
        if self.content:
            message["content"] = self.content
        
        if self.tool_calls:
            message["tool_calls"] = list(self.tool_calls.values())
        
        if self.metadata:
            message["metadata"] = self.metadata
        
        return message
    
    def get_tool_calls(self) -> List[Dict[str, Any]]:
        """Get accumulated tool calls as a list."""
        return list(self.tool_calls.values())
    
    def reset(self):
        """Reset accumulator to initial state."""
        self.content = ""
        self.tool_calls.clear()
        self.metadata.clear()
        self.finish_reason = None
        self.usage = None


class StreamProcessor:
    """
    Process streaming responses with common patterns like retry logic,
    error handling, and rate limiting.
    """
    
    @staticmethod
    async def process_with_retry(
        stream_func: Callable[[], AsyncGenerator[Any, None]],
        max_retries: int = 3,
        backoff_base: float = 2.0
    ) -> AsyncGenerator[Any, None]:
        """
        Add retry logic to any streaming function.
        
        Args:
            stream_func: Async generator function to retry
            max_retries: Maximum number of retry attempts
            backoff_base: Base for exponential backoff
            
        Yields:
            Stream chunks from the function
        """
        last_error = None
        
        for attempt in range(max_retries):
            try:
                async for chunk in stream_func():
                    yield chunk
                return  # Success, exit
                
            except asyncio.CancelledError:
                # Don't retry on cancellation
                raise
                
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    # Calculate backoff time
                    wait_time = backoff_base ** attempt
                    await asyncio.sleep(wait_time)
                else:
                    # Last attempt failed, raise the error
                    raise
    
    @staticmethod
    async def process_with_timeout(
        stream_func: Callable[[], AsyncGenerator[Any, None]],
        timeout_seconds: float = 300.0
    ) -> AsyncGenerator[Any, None]:
        """
        Add timeout to streaming function.
        
        Args:
            stream_func: Async generator function
            timeout_seconds: Timeout in seconds
            
        Yields:
            Stream chunks from the function
        """
        try:
            async with asyncio.timeout(timeout_seconds):
                async for chunk in stream_func():
                    yield chunk
        except asyncio.TimeoutError:
            yield StreamChunk(
                type="error",
                error=f"Stream timeout after {timeout_seconds} seconds"
            )
    
    @staticmethod
    async def buffer_chunks(
        stream: AsyncGenerator[Any, None],
        buffer_size: int = 10,
        flush_interval: float = 0.1
    ) -> AsyncGenerator[List[Any], None]:
        """
        Buffer streaming chunks for batch processing.
        
        Args:
            stream: Input stream
            buffer_size: Maximum buffer size before flush
            flush_interval: Maximum time before flush (seconds)
            
        Yields:
            Batches of chunks
        """
        buffer = []
        last_flush = asyncio.get_event_loop().time()
        
        async for chunk in stream:
            buffer.append(chunk)
            current_time = asyncio.get_event_loop().time()
            
            if len(buffer) >= buffer_size or (current_time - last_flush) >= flush_interval:
                if buffer:
                    yield buffer
                    buffer = []
                    last_flush = current_time
        
        # Flush remaining buffer
        if buffer:
            yield buffer


def parse_sse_chunk(line: str) -> Optional[Dict[str, Any]]:
    """
    Parse Server-Sent Events (SSE) format chunks.
    
    Args:
        line: SSE line to parse
        
    Returns:
        Parsed data dictionary or None
    """
    if not line or not line.startswith("data: "):
        return None
    
    data_str = line[6:].strip()  # Remove "data: " prefix
    
    if data_str == "[DONE]":
        return {"type": "done"}
    
    try:
        return json.loads(data_str)
    except json.JSONDecodeError:
        return None


def validate_message_format(message: Dict[str, Any], format_type: str) -> bool:
    """
    Validate message structure for different API formats.
    
    Args:
        message: Message to validate
        format_type: One of "openai", "claude", "gemini", "response_api"
        
    Returns:
        True if message is valid for the format
    """
    if not isinstance(message, dict):
        return False
    
    # Common validation
    if "role" not in message:
        return False
    
    valid_roles = {"system", "user", "assistant", "tool", "function"}
    if message["role"] not in valid_roles:
        return False
    
    # Format-specific validation
    if format_type == "openai":
        # OpenAI Chat Completions format
        if message["role"] == "tool":
            return "tool_call_id" in message and "content" in message
        else:
            return "content" in message or "tool_calls" in message
            
    elif format_type == "claude":
        # Claude Response API format
        if message["role"] in ["user", "assistant"]:
            content = message.get("content")
            if isinstance(content, str):
                return True
            elif isinstance(content, list):
                # Check for valid content blocks
                return all(
                    isinstance(block, dict) and "type" in block
                    for block in content
                )
        return True
        
    elif format_type == "gemini":
        # Gemini format
        return "parts" in message or "content" in message
        
    elif format_type == "response_api":
        # OpenAI Response API format
        return "content" in message or "function_call" in message
        
    return False


class ChunkMerger:
    """
    Utility for merging streaming chunks of different formats.
    """
    
    @staticmethod
    def merge_openai_chunks(base: Dict[str, Any], delta: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge OpenAI Chat Completions format chunks.
        
        Args:
            base: Existing chunk data
            delta: New delta to merge
            
        Returns:
            Merged chunk data
        """
        if not base:
            return delta
        
        # Merge content
        if "content" in delta:
            base["content"] = base.get("content", "") + delta["content"]
        
        # Merge tool calls
        if "tool_calls" in delta:
            if "tool_calls" not in base:
                base["tool_calls"] = []
            
            for tool_call in delta["tool_calls"]:
                index = tool_call.get("index", len(base["tool_calls"]))
                
                # Ensure list is large enough
                while len(base["tool_calls"]) <= index:
                    base["tool_calls"].append({})
                
                # Merge this tool call
                if "id" in tool_call:
                    base["tool_calls"][index]["id"] = tool_call["id"]
                
                if "function" in tool_call:
                    if "function" not in base["tool_calls"][index]:
                        base["tool_calls"][index]["function"] = {"name": "", "arguments": ""}
                    
                    func = tool_call["function"]
                    if "name" in func:
                        base["tool_calls"][index]["function"]["name"] += func["name"]
                    if "arguments" in func:
                        base["tool_calls"][index]["function"]["arguments"] += func["arguments"]
        
        return base
    
    @staticmethod
    def merge_claude_chunks(base: Dict[str, Any], delta: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge Claude Response API format chunks.
        
        Args:
            base: Existing chunk data
            delta: New delta to merge
            
        Returns:
            Merged chunk data
        """
        if not base:
            return delta
        
        # Handle content blocks
        if "type" in delta:
            if delta["type"] == "content_block_delta":
                if "delta" in delta and "text" in delta["delta"]:
                    base["content"] = base.get("content", "") + delta["delta"]["text"]
            
            elif delta["type"] == "content_block_start":
                # Initialize new content block
                if "content_block" in delta:
                    base["current_block"] = delta["content_block"]
        
        return base