# -*- coding: utf-8 -*-
"""
Gemini API parameters handler building SDK config with parameter mapping and exclusions.
"""

from typing import Any, Dict, List, Set

from ._api_params_handler_base import APIParamsHandlerBase


class GeminiAPIParamsHandler(APIParamsHandlerBase):
    def get_excluded_params(self) -> Set[str]:
        base = self.get_base_excluded_params()
        extra = {
            "enable_web_search",
            "enable_code_execution",
            "use_multi_mcp",
            "mcp_sdk_auto",
            "allowed_tools",
            "exclude_tools",
            "custom_tools",
            "enable_file_generation",  # Internal flag for file generation (used in system messages only)
            "enable_image_generation",  # Internal flag for image generation (used in system messages only)
            "enable_audio_generation",  # Internal flag for audio generation (used in system messages only)
            "enable_video_generation",  # Internal flag for video generation (used in system messages only)
        }
        return set(base) | extra

    def get_provider_tools(self, all_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        These are SDK Tool objects (from google.genai.types), not JSON tool declarations.
        """
        tools: List[Any] = []

        if all_params.get("enable_web_search", False):
            try:
                from google.genai.types import GoogleSearch, Tool

                tools.append(Tool(google_search=GoogleSearch()))
            except Exception:
                # Gracefully ignore if SDK not available
                pass

        if all_params.get("enable_code_execution", False):
            try:
                from google.genai.types import Tool, ToolCodeExecution

                tools.append(Tool(code_execution=ToolCodeExecution()))
            except Exception:
                # Gracefully ignore if SDK not available
                pass

        return tools

    async def build_api_params(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], all_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Build a config dict for google-genai Client.generate_content_stream.
        - Map max_tokens -> max_output_tokens
        - Do not include 'model' here; caller extracts it
        - Do not add builtin tools; stream logic handles them
        - Do not handle MCP tools or coordination schema here
        """
        excluded = self.get_excluded_params()
        config: Dict[str, Any] = {}

        for key, value in all_params.items():
            if key in excluded or value is None:
                continue
            if key == "max_tokens":
                config["max_output_tokens"] = value
            elif key == "model":
                # Caller will extract model separately
                continue
            else:
                config[key] = value

        return config
