"""
Message format converters for different LLM APIs.
Handles conversion between OpenAI, Claude, Gemini, and Response API formats.
"""

from __future__ import annotations

import json
from typing import Dict, List, Any, Optional, Tuple, Union


class MessageConverter:
    """
    Convert messages between different API formats.
    Supports bidirectional conversion between all major formats.
    """
    
    @staticmethod
    def to_openai_format(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert messages to OpenAI Chat Completions format.
        
        Args:
            messages: Messages in any supported format
            
        Returns:
            Messages in OpenAI format
        """
        converted = []
        
        for msg in messages:
            role = msg.get("role", "")
            
            # Handle different content types
            content = msg.get("content", "")
            
            # If content is a list (Claude format), convert to string
            if isinstance(content, list):
                text_parts = []
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif block.get("type") == "tool_result":
                            # Convert tool result to tool message
                            converted.append({
                                "role": "tool",
                                "tool_call_id": block.get("tool_use_id", ""),
                                "content": block.get("content", "")
                            })
                            continue
                    else:
                        text_parts.append(str(block))
                
                if text_parts:
                    content = "\n".join(text_parts)
                else:
                    continue  # Skip if no text content
            
            # Build the message
            openai_msg = {"role": role}
            
            if content:
                openai_msg["content"] = content
            
            # Handle tool calls
            if "tool_calls" in msg:
                openai_msg["tool_calls"] = msg["tool_calls"]
            
            # Handle function calls (legacy format)
            if "function_call" in msg:
                # Convert to tool_calls format
                openai_msg["tool_calls"] = [{
                    "id": msg.get("id", "call_1"),
                    "type": "function",
                    "function": msg["function_call"]
                }]
            
            converted.append(openai_msg)
        
        return converted
    
    @staticmethod
    def to_claude_format(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert messages to Claude's format.
        
        Args:
            messages: Messages in any supported format
            
        Returns:
            Messages in Claude format with content blocks
        """
        converted = []
        
        for msg in messages:
            role = msg.get("role", "")
            
            # Skip system messages (handled separately in Claude)
            if role == "system":
                continue
            
            # Map roles
            if role == "tool":
                role = "user"  # Tool results go as user messages in Claude
            
            claude_msg = {"role": role, "content": []}
            
            # Handle content
            content = msg.get("content", "")
            if content:
                if isinstance(content, str):
                    claude_msg["content"].append({
                        "type": "text",
                        "text": content
                    })
                elif isinstance(content, list):
                    # Already in Claude format
                    claude_msg["content"] = content
            
            # Handle tool calls
            if "tool_calls" in msg:
                for tool_call in msg["tool_calls"]:
                    func = tool_call.get("function", {})
                    claude_msg["content"].append({
                        "type": "tool_use",
                        "id": tool_call.get("id", ""),
                        "name": func.get("name", ""),
                        "input": json.loads(func.get("arguments", "{}"))
                        if isinstance(func.get("arguments"), str)
                        else func.get("arguments", {})
                    })
            
            # Handle tool results (from tool role messages)
            if role == "user" and msg.get("tool_call_id"):
                claude_msg["content"] = [{
                    "type": "tool_result",
                    "tool_use_id": msg["tool_call_id"],
                    "content": msg.get("content", "")
                }]
            
            if claude_msg["content"]:  # Only add if there's content
                converted.append(claude_msg)
        
        return converted
    
    @staticmethod
    def to_gemini_format(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert messages to Gemini's format.
        
        Args:
            messages: Messages in any supported format
            
        Returns:
            Messages in Gemini format with parts
        """
        converted = []
        
        for msg in messages:
            role = msg.get("role", "")
            
            # Map roles to Gemini format
            if role == "assistant":
                role = "model"
            elif role == "system":
                role = "user"  # Gemini handles system as user with special marker
            elif role == "tool":
                role = "function"
            
            gemini_msg = {"role": role, "parts": []}
            
            # Handle content
            content = msg.get("content", "")
            if content:
                if isinstance(content, str):
                    if role == "function":
                        # Function response format
                        gemini_msg["parts"].append({
                            "functionResponse": {
                                "name": msg.get("name", "unknown"),
                                "response": {"content": content}
                            }
                        })
                    else:
                        gemini_msg["parts"].append({"text": content})
                elif isinstance(content, list):
                    # Convert content blocks
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "text":
                                gemini_msg["parts"].append({"text": block.get("text", "")})
            
            # Handle tool calls
            if "tool_calls" in msg:
                for tool_call in msg["tool_calls"]:
                    func = tool_call.get("function", {})
                    gemini_msg["parts"].append({
                        "functionCall": {
                            "name": func.get("name", ""),
                            "args": json.loads(func.get("arguments", "{}"))
                            if isinstance(func.get("arguments"), str)
                            else func.get("arguments", {})
                        }
                    })
            
            if gemini_msg["parts"]:  # Only add if there are parts
                converted.append(gemini_msg)
        
        return converted
    
    @staticmethod
    def to_response_api_format(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert messages from Chat Completions format to Response API format.

        Chat Completions tool message: {"role": "tool", "tool_call_id": "...", "content": "..."}
        Response API tool message: {"type": "function_call_output", "call_id": "...", "output": "..."}

        Note: Assistant messages with tool_calls should not be in input - they're generated by the backend.
        """
        
        cleaned_messages = []
        for message in messages:
            if "status" in message and "role" not in message:
                # Create a copy without 'status'
                cleaned_message = {k: v for k, v in message.items() if k != "status"}
                cleaned_messages.append(cleaned_message)
            else:
                cleaned_messages.append(message)

        converted_messages = []

        for message in cleaned_messages:
            if message.get("role") == "tool":
                # Convert Chat Completions tool message to Response API format
                converted_message = {
                    "type": "function_call_output",
                    "call_id": message.get("tool_call_id"),
                    "output": message.get("content", ""),
                }
                converted_messages.append(converted_message)
            elif message.get("type") == "function_call_output":
                # Already in Response API format
                converted_messages.append(message)
            elif message.get("role") == "assistant" and "tool_calls" in message:
                # Assistant message with tool_calls - remove tool_calls when sending as input
                cleaned_message = {
                    k: v for k, v in message.items() if k != "tool_calls"
                }
                converted_messages.append(cleaned_message)
            else:
                # For other message types, pass through as-is
                converted_messages.append(message.copy())

        return converted_messages
    
    @staticmethod
    def merge_system_messages(messages: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Extract and merge system messages into a single system prompt.
        Many APIs handle system messages differently, so this extracts them.
        
        Args:
            messages: List of messages possibly containing system messages
            
        Returns:
            Tuple of (merged_system_content, remaining_messages)
        """
        system_content = []
        other_messages = []
        
        for msg in messages:
            if msg.get("role") == "system":
                content = msg.get("content", "")
                if content:
                    system_content.append(content)
            else:
                other_messages.append(msg)
        
        merged_system = "\n\n".join(system_content) if system_content else None
        return merged_system, other_messages
    
    @staticmethod
    def normalize_tool_calls(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Normalize tool calls across different formats.
        Ensures all tool calls follow the same structure.
        
        Args:
            messages: Messages with potentially different tool call formats
            
        Returns:
            Messages with normalized tool calls
        """
        normalized = []
        
        for msg in messages:
            new_msg = msg.copy()
            
            # Convert function_call to tool_calls
            if "function_call" in msg and "tool_calls" not in msg:
                new_msg["tool_calls"] = [{
                    "id": f"call_{hash(str(msg['function_call']))}",
                    "type": "function",
                    "function": msg["function_call"]
                }]
                del new_msg["function_call"]
            
            # Ensure tool_calls have proper structure
            if "tool_calls" in new_msg:
                normalized_calls = []
                for call in new_msg["tool_calls"]:
                    if not isinstance(call, dict):
                        continue
                    
                    normalized_call = {
                        "id": call.get("id", f"call_{len(normalized_calls)}"),
                        "type": call.get("type", "function")
                    }
                    
                    # Handle function data
                    if "function" in call:
                        normalized_call["function"] = call["function"]
                    elif "name" in call:
                        # Direct function format
                        normalized_call["function"] = {
                            "name": call["name"],
                            "arguments": call.get("arguments", "{}")
                        }
                    
                    normalized_calls.append(normalized_call)
                
                if normalized_calls:
                    new_msg["tool_calls"] = normalized_calls
                else:
                    del new_msg["tool_calls"]
            
            normalized.append(new_msg)
        
        return normalized
    
    @staticmethod
    def extract_text_content(message: Dict[str, Any]) -> str:
        """
        Extract plain text content from a message regardless of format.
        
        Args:
            message: Message in any format
            
        Returns:
            Plain text content
        """
        content = message.get("content", "")
        
        if isinstance(content, str):
            return content
        
        if isinstance(content, list):
            # Handle content blocks (Claude format)
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_result":
                        text_parts.append(f"[Tool Result: {block.get('content', '')}]")
                else:
                    text_parts.append(str(block))
            return "\n".join(text_parts)
        
        # Handle Gemini parts format
        if "parts" in message:
            text_parts = []
            for part in message["parts"]:
                if isinstance(part, dict) and "text" in part:
                    text_parts.append(part["text"])
            return "\n".join(text_parts)
        
        return str(content) if content else ""
    
    @staticmethod
    def convert_between_formats(
        messages: List[Dict[str, Any]],
        source_format: str,
        target_format: str
    ) -> List[Dict[str, Any]]:
        """
        Convert messages from one format to another.
        
        Args:
            messages: Messages in source format
            source_format: One of "openai", "claude", "gemini", "response_api"
            target_format: One of "openai", "claude", "gemini", "response_api"
            
        Returns:
            Messages in target format
        """
        if source_format == target_format:
            return messages
        
        # First normalize to OpenAI format (common intermediate)
        if source_format != "openai":
            if source_format == "claude":
                # Claude to OpenAI conversion needs special handling
                openai_messages = MessageConverter.to_openai_format(messages)
            elif source_format == "gemini":
                # Convert Gemini to OpenAI
                openai_messages = []
                for msg in messages:
                    role = msg.get("role", "")
                    if role == "model":
                        role = "assistant"
                    elif role == "function":
                        role = "tool"
                    
                    openai_msg = {"role": role}
                    
                    # Extract content from parts
                    if "parts" in msg:
                        text_parts = []
                        for part in msg["parts"]:
                            if isinstance(part, dict) and "text" in part:
                                text_parts.append(part["text"])
                        if text_parts:
                            openai_msg["content"] = "\n".join(text_parts)
                    
                    openai_messages.append(openai_msg)
            else:
                openai_messages = MessageConverter.to_openai_format(messages)
        else:
            openai_messages = messages
        
        # Then convert from OpenAI to target format
        if target_format == "openai":
            return openai_messages
        elif target_format == "claude":
            return MessageConverter.to_claude_format(openai_messages)
        elif target_format == "gemini":
            return MessageConverter.to_gemini_format(openai_messages)
        elif target_format == "response_api":
            return MessageConverter.to_response_api_format(openai_messages)
        else:
            raise ValueError(f"Unknown target format: {target_format}")