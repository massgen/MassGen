"""
Message formatter for different LLM APIs.
Handles conversion between OpenAI, Claude, and Response API formats.
"""

from __future__ import annotations

from typing import Dict, List, Any


class ToolFormatter:
    """
    Convert messages between different API formats.
    Supports bidirectional conversion between all major formats.
    """
    
    @staticmethod
    def to_chat_completions_format(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
                    converted_tools.append(
                        {
                            "type": "function",
                            "function": {
                                "name": tool["name"],
                                "description": tool["description"],
                                "parameters": tool.get("parameters", {}),
                            },
                        }
                    )
                else:
                    # Unknown format - keep as-is
                    converted_tools.append(tool)
            else:
                # Non-function tool - keep as-is
                converted_tools.append(tool)

        return converted_tools
    
    @staticmethod
    def to_claude_format(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert tools to Claude's expected format.

        Input formats supported:
        - Response API format: {"type": "function", "name": ..., "description": ..., "parameters": ...}
        - Chat Completions format: {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}

        Claude format: {"type": "function", "name": ..., "description": ..., "input_schema": ...}
        """
        if not tools:
            return tools

        converted_tools = []
        for tool in tools:
            if tool.get("type") == "function":
                if "function" in tool:
                    # Chat Completions format -> Claude custom tool
                    func = tool["function"]
                    converted_tools.append(
                        {
                            "type": "custom",
                            "name": func["name"],
                            "description": func["description"],
                            "input_schema": func.get("parameters", {}),
                        }
                    )
                elif "name" in tool and "description" in tool:
                    # Response API format -> Claude custom tool
                    converted_tools.append(
                        {
                            "type": "custom",
                            "name": tool["name"],
                            "description": tool["description"],
                            "input_schema": tool.get("parameters", {}),
                        }
                    )
                else:
                    # Unknown format - keep as-is
                    converted_tools.append(tool)
            else:
                # Non-function tool (builtin tools) - keep as-is
                converted_tools.append(tool)

        return converted_tools
    
    @staticmethod
    def to_response_api_format(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert tools from Chat Completions format to Response API format if needed.

        Chat Completions format: {"type": "function", "function": {"name": ..., "description": ..., "parameters": ...}}
        Response API format: {"type": "function", "name": ..., "description": ..., "parameters": ...}
        """
        if not tools:
            return tools

        converted_tools = []
        for tool in tools:
            if tool.get("type") == "function" and "function" in tool:
                # Chat Completions format - convert to Response API format
                func = tool["function"]
                converted_tools.append(
                    {
                        "type": "function",
                        "name": func["name"],
                        "description": func["description"],
                        "parameters": func.get("parameters", {}),
                    }
                )
            else:
                # Already in Response API format or non-function tool
                converted_tools.append(tool)

        return converted_tools

    @staticmethod
    def convert_between_formats(
        tools: List[Dict[str, Any]],
        source_format: str,
        target_format: str
    ) -> List[Dict[str, Any]]:
        """
        Convert tools from one format to another.
        
        Args:
            tools: Tools in source format
            source_format: One of "chat_completions", "claude", "response_api"
            target_format: One of "chat_completions", "claude", "response_api"
            
        Returns:
            Tools in target format
        """
        if source_format == target_format:
            return tools
        
        # Convert based on source and target formats
        if source_format == "chat_completions":
            if target_format == "claude":
                return ToolFormatter.to_claude_format(tools)
            elif target_format == "response_api":
                return ToolFormatter.to_response_api_format(tools)
        elif source_format == "response_api":
            if target_format == "chat_completions":
                return ToolFormatter.to_chat_completions_format(tools)
            elif target_format == "claude":
                # First convert to chat_completions, then to claude
                chat_completions_tools = ToolFormatter.to_chat_completions_format(tools)
                return ToolFormatter.to_claude_format(chat_completions_tools)
        elif source_format == "claude":
            # Claude format conversion back to other formats
            # This would need custom logic to handle Claude's custom tool format
            if target_format == "chat_completions":
                # Convert Claude custom tools back to Chat Completions format
                converted_tools = []
                for tool in tools:
                    if tool.get("type") == "custom":
                        converted_tools.append({
                            "type": "function",
                            "function": {
                                "name": tool.get("name", ""),
                                "description": tool.get("description", ""),
                                "parameters": tool.get("input_schema", {})
                            }
                        })
                    else:
                        converted_tools.append(tool)
                return converted_tools
            elif target_format == "response_api":
                # Convert Claude custom tools back to Response API format
                converted_tools = []
                for tool in tools:
                    if tool.get("type") == "custom":
                        converted_tools.append({
                            "type": "function",
                            "name": tool.get("name", ""),
                            "description": tool.get("description", ""),
                            "parameters": tool.get("input_schema", {})
                        })
                    else:
                        converted_tools.append(tool)
                return converted_tools
        
        raise ValueError(f"Unsupported conversion: {source_format} to {target_format}")
        