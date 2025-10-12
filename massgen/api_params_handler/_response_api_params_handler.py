# -*- coding: utf-8 -*-
"""
Response API parameters handler.
Handles parameter building for OpenAI Response API format.
"""

from __future__ import annotations

from typing import Any, Dict, List, Set

from ._api_params_handler_base import APIParamsHandlerBase


class ResponseAPIParamsHandler(APIParamsHandlerBase):
    """Handler for Response API parameters."""

    def get_excluded_params(self) -> Set[str]:
        """Get parameters to exclude from Response API calls."""
        return self.get_base_excluded_params().union(
            {
                "enable_web_search",
                "enable_code_interpreter",
                "allowed_tools",
                "exclude_tools",
                "_has_file_search_files",  # Internal flag for file search tracking
                "_file_search_vector_store_ids",  # Internal vector store IDs from uploads
            },
        )

    def get_api_format(self) -> str:
        """Get the API format for Response API."""
        return "response"

    def _convert_mcp_tools_to_openai_format(self) -> List[Dict[str, Any]]:
        """Convert MCP tools to OpenAI function format for Response API."""
        if not hasattr(self.backend, "_mcp_functions") or not self.backend._mcp_functions:
            return []

        converted_tools = []
        for function in self.backend._mcp_functions.values():
            converted_tools.append(function.to_openai_format())

        return converted_tools

    async def build_api_params(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        all_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build Response API parameters."""
        # Convert messages to Response API format
        converted_messages = self.formatter.format_messages(messages)

        # Response API uses 'input' instead of 'messages'
        api_params = {
            "input": converted_messages,
            "stream": True,
        }

        # Add filtered parameters with parameter mapping
        excluded = self.get_excluded_params()
        for key, value in all_params.items():
            if key not in excluded and value is not None:
                # Handle Response API parameter name differences
                if key == "max_tokens":
                    api_params["max_output_tokens"] = value
                else:
                    api_params[key] = value

        # Combine all tools
        combined_tools = api_params.setdefault("tools", [])

        # Add provider tools first
        provider_tools = self.get_provider_tools(all_params)
        if provider_tools:
            combined_tools.extend(provider_tools)

        # Add framework tools
        if tools:
            converted_tools = self.formatter.format_tools(tools)
            combined_tools.extend(converted_tools)

        # Add MCP tools (use OpenAI format)
        mcp_tools = self._convert_mcp_tools_to_openai_format()
        if mcp_tools:
            combined_tools.extend(mcp_tools)

        if combined_tools:
            api_params["tools"] = combined_tools
        # File Search integration
        vector_store_ids = all_params.get("_file_search_vector_store_ids")
        if vector_store_ids:
            # Ensure vector_store_ids is a list
            if not isinstance(vector_store_ids, list):
                vector_store_ids = [vector_store_ids]

            # Check if file_search tool already exists
            file_search_tool_index = None
            for i, tool in enumerate(combined_tools):
                if tool.get("type") == "file_search":
                    file_search_tool_index = i
                    break

            # Add or update file_search tool with embedded vector_store_ids
            if file_search_tool_index is not None:
                # Update existing file_search tool
                combined_tools[file_search_tool_index]["vector_store_ids"] = vector_store_ids
            else:
                # Add new file_search tool with vector_store_ids
                combined_tools.append(
                    {
                        "type": "file_search",
                        "vector_store_ids": vector_store_ids,
                    },
                )

        return api_params
