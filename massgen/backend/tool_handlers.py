"""
Tool Handling Mixins
Provides unified tool conversion, filtering, and validation functionality.
"""

from __future__ import annotations

import json
from typing import Dict, List, Any, Optional, Union
from ..logger_config import logger


class ToolFormat:
    """Enum-like class for tool format types."""
    RESPONSE_API = "response_api"  # Claude Response API format
    CHAT_COMPLETIONS = "chat_completions"  # OpenAI Chat Completions format
    GEMINI = "gemini"  # Google Gemini format
    VERTEX = "vertex"  # Google Vertex AI format


class ToolHandlerMixin:
    """Mixin class providing tool handling functionality."""
    
    def convert_tools_format(
        self,
        tools: List[Dict[str, Any]],
        target_format: str
    ) -> List[Dict[str, Any]]:
        """
        Convert tools between different API formats.
        
        Args:
            tools: List of tool definitions
            target_format: Target format (response_api, chat_completions, gemini, vertex)
            
        Returns:
            Converted tool definitions
        """
        if not tools:
            return []
        
        converted = []
        for tool in tools:
            converted_tool = self._convert_single_tool(tool, target_format)
            if converted_tool:
                converted.append(converted_tool)
        
        return converted
    
    def _convert_single_tool(
        self,
        tool: Dict[str, Any],
        target_format: str
    ) -> Optional[Dict[str, Any]]:
        """Convert a single tool to target format."""
        
        # Detect source format
        source_format = self._detect_tool_format(tool)
        
        if source_format == target_format:
            return tool
        
        # Extract tool information in a normalized way
        name, description, parameters = self._extract_tool_info(tool, source_format)
        
        if not name:
            logger.warning(f"Could not extract tool name from: {tool}")
            return None
        
        # Build tool in target format
        if target_format == ToolFormat.CHAT_COMPLETIONS:
            return {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description or "",
                    "parameters": parameters or {}
                }
            }
        
        elif target_format == ToolFormat.RESPONSE_API:
            return {
                "type": "function",
                "name": name,
                "description": description or "",
                "parameters": parameters or {}
            }
        
        elif target_format == ToolFormat.GEMINI:
            # Gemini format with functionDeclarations
            return {
                "functionDeclarations": [{
                    "name": name,
                    "description": description or "",
                    "parameters": self._convert_parameters_to_gemini(parameters)
                }]
            }
        
        elif target_format == ToolFormat.VERTEX:
            # Vertex AI format
            return {
                "function_declarations": [{
                    "name": name,
                    "description": description or "",
                    "parameters": parameters or {}
                }]
            }
        
        else:
            logger.warning(f"Unknown target format: {target_format}")
            return None
    
    def _detect_tool_format(self, tool: Dict[str, Any]) -> str:
        """Detect the format of a tool definition."""
        
        # Check for Chat Completions format
        if "function" in tool and isinstance(tool["function"], dict):
            return ToolFormat.CHAT_COMPLETIONS
        
        # Check for Gemini format
        if "functionDeclarations" in tool:
            return ToolFormat.GEMINI
        
        # Check for Vertex format
        if "function_declarations" in tool:
            return ToolFormat.VERTEX
        
        # Check for Response API format
        if "name" in tool and "parameters" in tool:
            return ToolFormat.RESPONSE_API
        
        # Default to Response API format
        return ToolFormat.RESPONSE_API
    
    def _extract_tool_info(
        self,
        tool: Dict[str, Any],
        source_format: str
    ) -> tuple[Optional[str], Optional[str], Optional[Dict[str, Any]]]:
        """
        Extract name, description, and parameters from tool definition.
        
        Returns:
            Tuple of (name, description, parameters)
        """
        name = None
        description = None
        parameters = None
        
        if source_format == ToolFormat.CHAT_COMPLETIONS:
            func = tool.get("function", {})
            name = func.get("name")
            description = func.get("description")
            parameters = func.get("parameters")
        
        elif source_format == ToolFormat.RESPONSE_API:
            name = tool.get("name")
            description = tool.get("description")
            parameters = tool.get("parameters")
        
        elif source_format == ToolFormat.GEMINI:
            func_decls = tool.get("functionDeclarations", [])
            if func_decls and len(func_decls) > 0:
                func = func_decls[0]
                name = func.get("name")
                description = func.get("description")
                parameters = self._convert_gemini_parameters_to_standard(
                    func.get("parameters", {})
                )
        
        elif source_format == ToolFormat.VERTEX:
            func_decls = tool.get("function_declarations", [])
            if func_decls and len(func_decls) > 0:
                func = func_decls[0]
                name = func.get("name")
                description = func.get("description")
                parameters = func.get("parameters")
        
        return name, description, parameters
    
    def _convert_parameters_to_gemini(
        self,
        parameters: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Convert standard JSON Schema parameters to Gemini format."""
        if not parameters:
            return {"type": "object", "properties": {}}
        
        # Gemini expects specific format for parameters
        gemini_params = {
            "type": parameters.get("type", "object"),
            "properties": parameters.get("properties", {}),
        }
        
        if "required" in parameters:
            gemini_params["required"] = parameters["required"]
        
        return gemini_params
    
    def _convert_gemini_parameters_to_standard(
        self,
        gemini_params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Convert Gemini parameters to standard JSON Schema format."""
        return {
            "type": gemini_params.get("type", "object"),
            "properties": gemini_params.get("properties", {}),
            "required": gemini_params.get("required", [])
        }
    
    def filter_tools(
        self,
        tools: List[Dict[str, Any]],
        allowed: Optional[List[str]] = None,
        excluded: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Filter tools based on allowed and excluded lists.
        
        Args:
            tools: List of tool definitions
            allowed: Optional list of allowed tool names
            excluded: Optional list of excluded tool names
            
        Returns:
            Filtered list of tools
        """
        if not tools:
            return []
        
        filtered = []
        
        for tool in tools:
            # Extract tool name
            tool_name = self._extract_tool_name(tool)
            
            if not tool_name:
                logger.warning(f"Could not extract name from tool: {tool}")
                continue
            
            # Apply filters
            if allowed and tool_name not in allowed:
                logger.debug(f"Tool '{tool_name}' not in allowed list, skipping")
                continue
            
            if excluded and tool_name in excluded:
                logger.debug(f"Tool '{tool_name}' in excluded list, skipping")
                continue
            
            filtered.append(tool)
        
        logger.debug(f"Filtered {len(tools)} tools to {len(filtered)} tools")
        return filtered
    
    def _extract_tool_name(self, tool: Dict[str, Any]) -> Optional[str]:
        """Extract tool name from various formats."""
        # Try Chat Completions format
        if "function" in tool and isinstance(tool["function"], dict):
            return tool["function"].get("name")
        
        # Try Response API format
        if "name" in tool:
            return tool["name"]
        
        # Try Gemini format
        if "functionDeclarations" in tool:
            func_decls = tool["functionDeclarations"]
            if func_decls and len(func_decls) > 0:
                return func_decls[0].get("name")
        
        # Try Vertex format
        if "function_declarations" in tool:
            func_decls = tool["function_declarations"]
            if func_decls and len(func_decls) > 0:
                return func_decls[0].get("name")
        
        return None
    
    def validate_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]],
        available_tools: Optional[List[str]] = None
    ) -> tuple[List[Dict[str, Any]], List[str]]:
        """
        Validate tool calls and return valid calls and errors.
        
        Args:
            tool_calls: List of tool calls to validate
            available_tools: Optional list of available tool names
            
        Returns:
            Tuple of (valid_tool_calls, error_messages)
        """
        valid_calls = []
        errors = []
        
        for i, call in enumerate(tool_calls):
            # Validate structure
            if not isinstance(call, dict):
                errors.append(f"Tool call {i} is not a dictionary")
                continue
            
            # Extract tool information
            tool_name = None
            tool_args = None
            
            # Try different formats
            if "function" in call:
                func = call.get("function", {})
                tool_name = func.get("name")
                tool_args = func.get("arguments")
            elif "name" in call:
                tool_name = call.get("name")
                tool_args = call.get("arguments") or call.get("parameters")
            
            # Validate name
            if not tool_name:
                errors.append(f"Tool call {i} missing tool name")
                continue
            
            # Check availability
            if available_tools and tool_name not in available_tools:
                errors.append(f"Tool '{tool_name}' not available")
                continue
            
            # Validate arguments
            if tool_args:
                if isinstance(tool_args, str):
                    # Try to parse JSON string
                    try:
                        json.loads(tool_args)
                    except json.JSONDecodeError as e:
                        errors.append(f"Tool '{tool_name}' has invalid JSON arguments: {e}")
                        continue
                elif not isinstance(tool_args, dict):
                    errors.append(f"Tool '{tool_name}' arguments must be dict or JSON string")
                    continue
            
            valid_calls.append(call)
        
        return valid_calls, errors
    
    def create_tool_result_message(
        self,
        tool_call: Dict[str, Any],
        result: Union[str, Dict[str, Any]],
        format_type: str = ToolFormat.CHAT_COMPLETIONS
    ) -> Dict[str, Any]:
        """
        Create a tool result message in the specified format.
        
        Args:
            tool_call: Original tool call
            result: Tool execution result
            format_type: Target message format
            
        Returns:
            Tool result message
        """
        # Convert result to string if needed
        result_str = result if isinstance(result, str) else json.dumps(result)
        
        if format_type == ToolFormat.CHAT_COMPLETIONS:
            # OpenAI Chat Completions format
            tool_call_id = tool_call.get("id", "")
            return {
                "role": "tool",
                "tool_call_id": tool_call_id,
                "content": result_str
            }
        
        elif format_type == ToolFormat.RESPONSE_API:
            # Claude Response API format
            tool_use_id = tool_call.get("id", "")
            return {
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": result_str
                }]
            }
        
        elif format_type == ToolFormat.GEMINI:
            # Gemini format
            function_name = self._extract_tool_name(tool_call)
            return {
                "role": "function",
                "parts": [{
                    "functionResponse": {
                        "name": function_name,
                        "response": {
                            "content": result_str
                        }
                    }
                }]
            }
        
        else:
            # Default format
            return {
                "role": "tool",
                "content": result_str
            }
    
    def merge_tool_definitions(
        self,
        *tool_lists: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Merge multiple tool lists, removing duplicates.
        
        Args:
            *tool_lists: Variable number of tool definition lists
            
        Returns:
            Merged list with unique tools
        """
        seen_tools = set()
        merged = []
        
        for tools in tool_lists:
            if not tools:
                continue
            
            for tool in tools:
                tool_name = self._extract_tool_name(tool)
                if tool_name and tool_name not in seen_tools:
                    seen_tools.add(tool_name)
                    merged.append(tool)
        
        return merged