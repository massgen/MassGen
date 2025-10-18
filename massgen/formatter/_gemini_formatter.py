# -*- coding: utf-8 -*-
"""
Gemini formatter for message formatting, coordination prompts, and structured output parsing.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from ._formatter_base import FormatterBase

logger = logging.getLogger(__name__)


class GeminiFormatter(FormatterBase):
    def format_messages(self, messages: List[Dict[str, Any]]) -> str:
        """
        Build conversation content string from message history.

        Behavior mirrors the formatting used previously in the Gemini backend:
        - System messages buffered separately then prepended.
        - User => "User: {content}"
        - Assistant => "Assistant: {content}"
        - Tool => "Tool Result: {content}"
        """
        conversation_content = ""
        system_message = ""

        for msg in messages:
            role = msg.get("role")
            if role == "system":
                system_message = msg.get("content", "")
            elif role == "user":
                conversation_content += f"User: {msg.get('content', '')}\n"
            elif role == "assistant":
                conversation_content += f"Assistant: {msg.get('content', '')}\n"
            elif role == "tool":
                tool_output = msg.get("content", "")
                conversation_content += f"Tool Result: {tool_output}\n"

        # Combine system message and conversation
        full_content = ""
        if system_message:
            full_content += f"{system_message}\n\n"
        full_content += conversation_content
        return full_content

    def format_tools(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Gemini uses SDK-native tool format, not reformatting.
        """
        return tools or []

    def format_mcp_tools(self, mcp_functions: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        MCP tools are passed via SDK sessions in stream_with_tools; not function declarations.
        """
        return []

    # Coordination helpers

    def has_coordination_tools(self, tools: List[Dict[str, Any]]) -> bool:
        """Detect if tools contain vote/new_answer coordination tools."""
        if not tools:
            return False

        tool_names = set()
        for tool in tools:
            if tool.get("type") == "function":
                if "function" in tool:
                    tool_names.add(tool["function"].get("name", ""))
                elif "name" in tool:
                    tool_names.add(tool.get("name", ""))

        return "vote" in tool_names and "new_answer" in tool_names

    def build_structured_output_prompt(self, base_content: str, valid_agent_ids: Optional[List[str]] = None) -> str:
        """Build prompt that encourages structured output for coordination."""
        agent_list = ""
        if valid_agent_ids:
            agent_list = f"Valid agents: {', '.join(valid_agent_ids)}"

        return f"""{base_content}

IMPORTANT: You must respond with a structured JSON decision at the end of your response.

If you want to VOTE for an existing agent's answer:
{{
  "action_type": "vote",
  "vote_data": {{
    "action": "vote",
    "agent_id": "agent1",  // Choose from: {agent_list or "agent1, agent2, agent3, etc."}
    "reason": "Brief reason for your vote"
  }}
}}

If you want to provide a NEW ANSWER:
{{
  "action_type": "new_answer",
  "answer_data": {{
    "action": "new_answer",
    "content": "Your complete improved answer here"
  }}
}}

Make your decision and include the JSON at the very end of your response."""

    def extract_structured_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """Extract structured JSON response from model output."""
        try:
            # Strategy 0: Look for JSON inside markdown code blocks first
            markdown_json_pattern = r"```json\s*(\{.*?\})\s*```"
            markdown_matches = re.findall(markdown_json_pattern, response_text, re.DOTALL)

            for match in reversed(markdown_matches):
                try:
                    parsed = json.loads(match.strip())
                    if isinstance(parsed, dict) and "action_type" in parsed:
                        return parsed
                except json.JSONDecodeError:
                    continue

            # Strategy 1: Look for complete JSON blocks with proper braces
            json_pattern = r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}"
            json_matches = re.findall(json_pattern, response_text, re.DOTALL)

            # Try parsing each match (in reverse order - last one first)
            for match in reversed(json_matches):
                try:
                    cleaned_match = match.strip()
                    parsed = json.loads(cleaned_match)
                    if isinstance(parsed, dict) and "action_type" in parsed:
                        return parsed
                except json.JSONDecodeError:
                    continue

            # Strategy 2: Look for JSON blocks with nested braces (more complex)
            brace_count = 0
            json_start = -1

            for i, char in enumerate(response_text):
                if char == "{":
                    if brace_count == 0:
                        json_start = i
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0 and json_start >= 0:
                        # Found a complete JSON block
                        json_block = response_text[json_start : i + 1]
                        try:
                            parsed = json.loads(json_block)
                            if isinstance(parsed, dict) and "action_type" in parsed:
                                return parsed
                        except json.JSONDecodeError:
                            pass
                        json_start = -1

            # Strategy 3: Line-by-line approach (fallback)
            lines = response_text.strip().split("\n")
            json_candidates = []

            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith("{") and stripped.endswith("}"):
                    json_candidates.append(stripped)
                elif stripped.startswith("{"):
                    # Multi-line JSON - collect until closing brace
                    json_text = stripped
                    for j in range(i + 1, len(lines)):
                        json_text += "\n" + lines[j].strip()
                        if lines[j].strip().endswith("}"):
                            json_candidates.append(json_text)
                            break

            # Try to parse each candidate
            for candidate in reversed(json_candidates):
                try:
                    parsed = json.loads(candidate)
                    if isinstance(parsed, dict) and "action_type" in parsed:
                        return parsed
                except json.JSONDecodeError:
                    continue

            return None

        except Exception:
            return None

    def convert_structured_to_tool_calls(self, structured_response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Convert structured response to tool call format."""
        action_type = structured_response.get("action_type")

        if action_type == "vote":
            vote_data = structured_response.get("vote_data", {})
            return [
                {
                    "id": f"vote_{abs(hash(str(vote_data))) % 10000 + 1}",
                    "type": "function",
                    "function": {
                        "name": "vote",
                        "arguments": {
                            "agent_id": vote_data.get("agent_id", ""),
                            "reason": vote_data.get("reason", ""),
                        },
                    },
                },
            ]

        elif action_type == "new_answer":
            answer_data = structured_response.get("answer_data", {})
            return [
                {
                    "id": f"new_answer_{abs(hash(str(answer_data))) % 10000 + 1}",
                    "type": "function",
                    "function": {
                        "name": "new_answer",
                        "arguments": {"content": answer_data.get("content", "")},
                    },
                },
            ]

        return []

    # Custom tools formatting for Gemini

    def format_custom_tools(
        self,
        custom_tools: List[Dict[str, Any]],
        return_sdk_objects: bool = True
    ) -> List[Any]:
        """
        Convert custom tools from OpenAI Chat Completions format to Gemini format.

        Can return either SDK FunctionDeclaration objects (default) or Gemini-format dictionaries.

        OpenAI format:
            [{"type": "function", "function": {"name": ..., "description": ..., "parameters": {...}}}]

        Gemini dictionary format:
            [{"name": ..., "description": ..., "parameters": {...}}]

        Gemini SDK format:
            [FunctionDeclaration(name=..., description=..., parameters=Schema(...))]

        Args:
            custom_tools: List of tools in OpenAI Chat Completions format
            return_sdk_objects: If True, return FunctionDeclaration objects;
                               if False, return Gemini-format dictionaries

        Returns:
            List of tools in Gemini SDK format (default) or dictionary format
        """
        if not custom_tools:
            return []

        # Step 1: Convert to Gemini dictionary format
        gemini_dicts = self._convert_to_gemini_dict_format(custom_tools)

        if not return_sdk_objects:
            return gemini_dicts

        # Step 2: Convert dictionaries to SDK FunctionDeclaration objects
        return self._convert_to_function_declarations(gemini_dicts)

    def _convert_to_gemini_dict_format(self, custom_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert OpenAI format to Gemini dictionary format (intermediate step).

        Args:
            custom_tools: List of tools in OpenAI Chat Completions format

        Returns:
            List of tools in Gemini-compatible dictionary format
        """
        if not custom_tools:
            return []

        converted_tools = []

        for tool in custom_tools:
            # Handle OpenAI Chat Completions format with type="function" wrapper
            if isinstance(tool, dict) and tool.get("type") == "function" and "function" in tool:
                func_def = tool["function"]
                converted_tool = {
                    "name": func_def.get("name", ""),
                    "description": func_def.get("description", ""),
                    "parameters": func_def.get("parameters", {})
                }
                converted_tools.append(converted_tool)
            # Handle already-converted Gemini format (idempotent)
            elif isinstance(tool, dict) and "name" in tool and "parameters" in tool:
                # Already in Gemini format, pass through
                converted_tools.append(tool)
            else:
                # Skip unrecognized formats
                logger.warning(f"[GeminiFormatter] Skipping unrecognized tool format: {tool}")

        return converted_tools

    def _convert_to_function_declarations(self, tools_dicts: List[Dict[str, Any]]) -> List[Any]:
        """
        Convert Gemini-format tool dictionaries to FunctionDeclaration objects.

        Args:
            tools_dicts: List of tool dictionaries in Gemini format
                [{"name": ..., "description": ..., "parameters": {...}}]

        Returns:
            List of google.genai.types.FunctionDeclaration objects
        """
        if not tools_dicts:
            return []

        try:
            from google.genai import types
        except ImportError:
            logger.error("[GeminiFormatter] Cannot import google.genai.types for FunctionDeclaration")
            logger.error("[GeminiFormatter] Falling back to dictionary format")
            return tools_dicts  # Fallback to dict format

        function_declarations = []

        for tool_dict in tools_dicts:
            try:
                # Create Schema object for parameters
                params = tool_dict.get("parameters", {})

                # Convert parameters to Schema object (recursive)
                schema = self._build_schema_recursive(params)

                # Create FunctionDeclaration object
                func_decl = types.FunctionDeclaration(
                    name=tool_dict.get("name", ""),
                    description=tool_dict.get("description", ""),
                    parameters=schema
                )

                function_declarations.append(func_decl)

                logger.debug(
                    f"[GeminiFormatter] Converted tool '{tool_dict.get('name')}' "
                    f"to FunctionDeclaration"
                )

            except Exception as e:
                logger.error(
                    f"[GeminiFormatter] Failed to convert tool to FunctionDeclaration: {e}"
                )
                logger.error(f"[GeminiFormatter] Tool dict: {tool_dict}")
                # Continue processing other tools instead of failing completely
                continue

        return function_declarations

    def _build_schema_recursive(self, param_schema: Dict[str, Any]) -> Any:
        """
        Recursively build a Gemini Schema object from JSON Schema format.

        Handles nested objects, arrays, and all standard JSON Schema types.

        Args:
            param_schema: JSON Schema dictionary (may be nested)

        Returns:
            google.genai.types.Schema object
        """
        try:
            from google.genai import types
        except ImportError:
            logger.error("[GeminiFormatter] Cannot import google.genai.types")
            return None

        # Get the type (default to "object" for top-level parameters)
        param_type = param_schema.get("type", "object")
        gemini_type = self._convert_json_type_to_gemini_type(param_type)

        # Build base schema kwargs
        schema_kwargs = {
            "type": gemini_type,
        }

        # Add description if present
        if "description" in param_schema:
            schema_kwargs["description"] = param_schema["description"]

        # Handle object type with nested properties
        if param_type == "object" and "properties" in param_schema:
            schema_kwargs["properties"] = {
                prop_name: self._build_schema_recursive(prop_schema)
                for prop_name, prop_schema in param_schema["properties"].items()
            }

            # Add required fields if present
            if "required" in param_schema:
                schema_kwargs["required"] = param_schema["required"]

        # Handle array type with items
        elif param_type == "array" and "items" in param_schema:
            schema_kwargs["items"] = self._build_schema_recursive(param_schema["items"])

        # Handle enum if present (for string/number types)
        if "enum" in param_schema:
            schema_kwargs["enum"] = param_schema["enum"]

        # Handle format if present (e.g., "date-time", "email", etc.)
        if "format" in param_schema:
            schema_kwargs["format"] = param_schema["format"]

        # Handle nullable if present
        if "nullable" in param_schema:
            schema_kwargs["nullable"] = param_schema["nullable"]

        return types.Schema(**schema_kwargs)

    def _convert_json_type_to_gemini_type(self, json_type: str) -> Any:
        """
        Convert JSON Schema type string to Gemini Type enum.

        Args:
            json_type: JSON Schema type like "string", "number", "integer", etc.

        Returns:
            Corresponding google.genai.types.Type enum value
        """
        try:
            from google.genai import types
        except ImportError:
            # If we can't import, return string as fallback
            # This shouldn't happen in practice since _build_schema_recursive checks first
            return "STRING"

        # Map JSON Schema types to Gemini Type enum
        type_mapping = {
            "string": types.Type.STRING,
            "number": types.Type.NUMBER,
            "integer": types.Type.INTEGER,
            "boolean": types.Type.BOOLEAN,
            "array": types.Type.ARRAY,
            "object": types.Type.OBJECT,
        }

        # Return mapped type or default to STRING
        gemini_type = type_mapping.get(json_type.lower(), types.Type.STRING)

        if json_type.lower() not in type_mapping:
            logger.warning(
                f"[GeminiFormatter] Unknown JSON type '{json_type}', defaulting to STRING"
            )

        return gemini_type