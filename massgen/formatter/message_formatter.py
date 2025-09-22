"""
Message formatter for different LLM APIs.
Handles conversion between OpenAI, Claude, Gemini, and Response API formats.
"""

from __future__ import annotations

import json
from typing import Dict, List, Any


class MessageFormatter:
    """
    Convert messages between different API formats.
    Supports bidirectional conversion between all major formats.
    """
    
    @staticmethod
    def to_chat_completions_format(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert messages for Chat Completions API compatibility.

        Chat Completions API expects tool call arguments as JSON strings in conversation history,
        but they may be passed as objects from other parts of the system.
        """

        converted = []

        for message in messages:
            # Create a copy to avoid modifying the original
            converted_msg = dict(message)

            # Convert tool_calls arguments from objects to JSON strings
            if message.get("role") == "assistant" and "tool_calls" in message:
                converted_tool_calls = []
                for tool_call in message["tool_calls"]:
                    converted_call = dict(tool_call)
                    if "function" in converted_call:
                        converted_function = dict(converted_call["function"])
                        arguments = converted_function.get("arguments")

                        # Convert arguments to JSON string if it's an object
                        if isinstance(arguments, dict):
                            converted_function["arguments"] = json.dumps(arguments)
                        elif arguments is None:
                            converted_function["arguments"] = "{}"
                        elif not isinstance(arguments, str):
                            # Handle other non-string types
                            converted_function[
                                "arguments"
                            ] = MessageFormatter._serialize_tool_arguments(arguments)
                        # If it's already a string, keep it as-is

                        converted_call["function"] = converted_function
                    converted_tool_calls.append(converted_call)
                converted_msg["tool_calls"] = converted_tool_calls

            converted.append(converted_msg)

        return converted
    
    @staticmethod
    def to_claude_format(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert messages to Claude's expected format.

        Handle different tool message formats and extract system message:
        - Chat Completions tool message: {"role": "tool", "tool_call_id": "...", "content": "..."}
        - Response API tool message: {"type": "function_call_output", "call_id": "...", "output": "..."}
        - System messages: Extract and return separately for top-level system parameter

        Returns:
            tuple: (converted_messages, system_message)
        """
        converted_messages = []
        system_message = ""

        for message in messages:
            if message.get("role") == "system":
                # Extract system message for top-level parameter
                system_message = message.get("content", "")
            elif message.get("role") == "tool":
                # Chat Completions tool message -> Claude tool result
                converted_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": message.get("tool_call_id"),
                                "content": message.get("content", ""),
                            }
                        ],
                    }
                )
            elif message.get("type") == "function_call_output":
                # Response API tool message -> Claude tool result
                converted_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": message.get("call_id"),
                                "content": message.get("output", ""),
                            }
                        ],
                    }
                )
            elif message.get("role") == "assistant" and "tool_calls" in message:
                # Assistant message with tool calls - convert to Claude format
                content = []

                # Add text content if present
                if message.get("content"):
                    content.append({"type": "text", "text": message["content"]})

                # Convert tool calls to Claude tool use format
                for tool_call in message["tool_calls"]:
                    tool_name = MessageFormatter.extract_tool_name(tool_call)
                    tool_args = MessageFormatter.extract_tool_arguments(tool_call)
                    tool_id = MessageFormatter.extract_tool_call_id(tool_call)

                    content.append(
                        {
                            "type": "tool_use",
                            "id": tool_id,
                            "name": tool_name,
                            "input": tool_args,
                        }
                    )

                converted_messages.append({"role": "assistant", "content": content})
            elif message.get("role") in ["user", "assistant"]:
                # Keep user and assistant messages, skip system
                converted_message = dict(message)
                if isinstance(converted_message.get("content"), str):
                    # Claude expects content to be text for simple messages
                    pass
                converted_messages.append(converted_message)

        return converted_messages, system_message
    
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
                openai_messages = MessageFormatter.to_openai_format(messages)
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
                openai_messages = MessageFormatter.to_openai_format(messages)
        else:
            openai_messages = messages
        
        # Then convert from OpenAI to target format
        if target_format == "openai":
            return openai_messages
        elif target_format == "claude":
            return MessageFormatter.to_claude_format(openai_messages)
        elif target_format == "gemini":
            return MessageFormatter.to_gemini_format(openai_messages)
        elif target_format == "response_api":
            return MessageFormatter.to_response_api_format(openai_messages)
        else:
            raise ValueError(f"Unknown target format: {target_format}")
        
    @staticmethod
    def extract_tool_name(tool_call: Dict[str, Any]) -> str:
        """
        Extract tool name from a tool call (handles multiple formats).
        
        Supports:
        - Chat Completions format: {"function": {"name": "...", ...}}
        - Response API format: {"name": "..."}
        - Claude native format: {"name": "..."}

        Args:
            tool_call: Tool call data structure from any backend

        Returns:
            Tool name string
        """
        # Chat Completions format
        if "function" in tool_call:
            return tool_call.get("function", {}).get("name", "unknown")
        # Response API / Claude native format
        elif "name" in tool_call:
            return tool_call.get("name", "unknown")
        # Fallback
        return "unknown"

    @staticmethod
    def extract_tool_arguments(tool_call: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract tool arguments from a tool call (handles multiple formats).
        
        Supports:
        - Chat Completions format: {"function": {"arguments": ...}}
        - Response API format: {"arguments": ...}
        - Claude native format: {"input": ...}

        Args:
            tool_call: Tool call data structure from any backend

        Returns:
            Tool arguments dictionary (parsed from JSON string if needed)
        """
        import json
        
        # Chat Completions format
        if "function" in tool_call:
            args = tool_call.get("function", {}).get("arguments", {})
        # Claude native format
        elif "input" in tool_call:
            args = tool_call.get("input", {})
        # Response API format
        elif "arguments" in tool_call:
            args = tool_call.get("arguments", {})
        else:
            args = {}

        # Parse JSON string if needed
        if isinstance(args, str):
            try:
                return json.loads(args) if args.strip() else {}
            except (json.JSONDecodeError, ValueError):
                return {}
        return args if isinstance(args, dict) else {}

    @staticmethod
    def extract_tool_call_id(tool_call: Dict[str, Any]) -> str:
        """
        Extract tool call ID from a tool call (handles multiple formats).
        
        Supports:
        - Chat Completions format: {"id": "..."}
        - Response API format: {"call_id": "..."}
        - Claude native format: {"id": "..."}

        Args:
            tool_call: Tool call data structure from any backend

        Returns:
            Tool call ID string
        """
        # Try multiple possible ID fields
        return tool_call.get("id") or tool_call.get("call_id") or ""
    
    @staticmethod
    def _serialize_tool_arguments(arguments) -> str:
        """Safely serialize tool call arguments to JSON string.

        Args:
            arguments: Tool arguments (can be string, dict, or other types)

        Returns:
            JSON string representation of arguments
        """
        import json

        if isinstance(arguments, str):
            # If already a string, validate it's valid JSON
            try:
                json.loads(arguments)  # Validate JSON
                return arguments
            except (json.JSONDecodeError, ValueError):
                # If not valid JSON, treat as plain string and wrap in quotes
                return json.dumps(arguments)
        elif arguments is None:
            return "{}"
        else:
            # Convert to JSON string
            try:
                return json.dumps(arguments)
            except (TypeError, ValueError) as e:
                # Logger not imported at module level, use print for warning
                print(f"Warning: Failed to serialize tool arguments: {e}, arguments: {arguments}")
                return "{}"