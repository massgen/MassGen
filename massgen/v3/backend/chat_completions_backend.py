from __future__ import annotations

"""
Base class for backends using OpenAI Chat Completions API format.
Handles common message processing, tool conversion, and streaming patterns.
"""

import os
from typing import Dict, List, Any, AsyncGenerator, Optional
from .base import LLMBackend, StreamChunk


class ChatCompletionsBackend(LLMBackend):
    """Base class for backends using Chat Completions API with shared streaming logic."""
    
    def __init__(self, api_key: Optional[str] = None, **kwargs):
        super().__init__(api_key, **kwargs)
    
    def convert_tools_to_chat_completions_format(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert tools from Response API format to Chat Completions format if needed.
        
        Response API format: {"type": "function", "name": ..., "description": ..., "parameters": ...}
        Chat Completions format: {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
        """
        if not tools:
            return tools
            
        converted_tools = []
        for tool in tools:
            if tool.get("type") == "function":
                if "function" in tool:
                    # Already in Chat Completions format
                    converted_tools.append(tool)
                elif "name" in tool and "description" in tool:
                    # Response API format - convert to Chat Completions format
                    converted_tools.append({
                        "type": "function",
                        "function": {
                            "name": tool["name"],
                            "description": tool["description"],
                            "parameters": tool.get("parameters", {})
                        }
                    })
                else:
                    # Unknown format - keep as-is
                    converted_tools.append(tool)
            else:
                # Non-function tool - keep as-is
                converted_tools.append(tool)
        
        return converted_tools
    
    async def handle_chat_completions_stream(self, stream, enable_web_search: bool = False) -> AsyncGenerator[StreamChunk, None]:
        """Handle standard Chat Completions API streaming format."""
        content = ""
        current_tool_calls = {}
        search_sources_used = 0
        citations = []
        
        async for chunk in stream:
            try:
                if hasattr(chunk, 'choices') and chunk.choices:
                    choice = chunk.choices[0]
                    
                    # Handle content delta
                    if hasattr(choice, 'delta') and choice.delta:
                        if hasattr(choice.delta, 'content') and choice.delta.content:
                            content_chunk = choice.delta.content
                            content += content_chunk
                            yield StreamChunk(type="content", content=content_chunk)
                        
                        # Handle tool calls streaming
                        if hasattr(choice.delta, 'tool_calls') and choice.delta.tool_calls:
                            for tool_call_delta in choice.delta.tool_calls:
                                index = getattr(tool_call_delta, 'index', 0)
                                
                                if index not in current_tool_calls:
                                    current_tool_calls[index] = {
                                        "id": "",
                                        "name": "",
                                        "arguments": ""
                                    }
                                
                                if hasattr(tool_call_delta, 'id') and tool_call_delta.id:
                                    current_tool_calls[index]["id"] = tool_call_delta.id
                                
                                if hasattr(tool_call_delta, 'function') and tool_call_delta.function:
                                    if hasattr(tool_call_delta.function, 'name') and tool_call_delta.function.name:
                                        current_tool_calls[index]["name"] = tool_call_delta.function.name
                                    
                                    if hasattr(tool_call_delta.function, 'arguments') and tool_call_delta.function.arguments:
                                        current_tool_calls[index]["arguments"] += tool_call_delta.function.arguments
                    
                    # Handle finish reason
                    if hasattr(choice, 'finish_reason') and choice.finish_reason:
                        if choice.finish_reason == "tool_calls" and current_tool_calls:
                            # Convert accumulated tool calls to final format
                            final_tool_calls = []
                            for index in sorted(current_tool_calls.keys()):
                                tool_call = current_tool_calls[index]
                                
                                # Parse arguments as JSON
                                arguments = tool_call["arguments"]
                                if isinstance(arguments, str):
                                    try:
                                        import json
                                        arguments = json.loads(arguments) if arguments.strip() else {}
                                    except json.JSONDecodeError:
                                        arguments = {}
                                
                                final_tool_calls.append({
                                    "id": tool_call["id"] or f"call_{index}",
                                    "type": "function",
                                    "function": {
                                        "name": tool_call["name"],
                                        "arguments": arguments
                                    }
                                })
                            
                            yield StreamChunk(type="tool_calls", content=final_tool_calls)
                            
                            # Build and yield complete message
                            complete_message = {"role": "assistant", "content": content.strip()}
                            if final_tool_calls:
                                complete_message["tool_calls"] = final_tool_calls
                            yield StreamChunk(type="complete_message", complete_message=complete_message)
                        elif choice.finish_reason in ["stop", "length"]:
                            if search_sources_used > 0:
                                yield StreamChunk(type="content", content=f"\n✅ [Live Search Complete] Used {search_sources_used} sources\n")
                            
                            # Build and yield complete message (no tool calls)
                            complete_message = {"role": "assistant", "content": content.strip()}
                            yield StreamChunk(type="complete_message", complete_message=complete_message)
                            
                            yield StreamChunk(type="done")
                        return
                
                # Check for usage information (search sources) and citations
                if hasattr(chunk, 'usage') and chunk.usage:
                    if hasattr(chunk.usage, 'num_sources_used') and chunk.usage.num_sources_used:
                        search_sources_used = chunk.usage.num_sources_used
                        if enable_web_search and search_sources_used > 0:
                            yield StreamChunk(type="content", content=f"\n📊 [Live Search] Using {search_sources_used} sources for real-time data\n")
                
                # Check for citations (typically in final chunk)
                if hasattr(chunk, 'citations') and chunk.citations:
                    citations = chunk.citations
                    if enable_web_search and citations:
                        citation_text = "\n📚 **Citations:**\n"
                        for i, citation in enumerate(citations, 1):
                            citation_text += f"{i}. {citation}\n"
                        yield StreamChunk(type="content", content=citation_text)
            
            except Exception as chunk_error:
                yield StreamChunk(type="error", error=f"Chunk processing error: {chunk_error}")
                continue
        
        yield StreamChunk(type="done")
    
    def extract_tool_name(self, tool_call: Dict[str, Any]) -> str:
        """Extract tool name from Chat Completions format."""
        return tool_call.get("function", {}).get("name", "unknown")
    
    def extract_tool_arguments(self, tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """Extract tool arguments from Chat Completions format."""
        return tool_call.get("function", {}).get("arguments", {})