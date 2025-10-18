# -*- coding: utf-8 -*-
"""
Gemini formatter for message formatting, coordination prompts, and structured output parsing.
"""

import json
import re
from typing import Any, Dict, List, Optional

from ._formatter_base import FormatterBase


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