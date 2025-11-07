# -*- coding: utf-8 -*-
"""
OpenAI Operator API parameters handler.
Extends Response API handler with computer use tool support.
"""

from __future__ import annotations

from typing import Any, Dict, List, Set

from ._response_api_params_handler import ResponseAPIParamsHandler


class OpenAIOperatorAPIParamsHandler(ResponseAPIParamsHandler):
    """Handler for OpenAI Operator API parameters with computer use support."""

    def get_excluded_params(self) -> Set[str]:
        """Get parameters to exclude from Operator API calls."""
        return (
            super()
            .get_excluded_params()
            .union(
                {
                    "enable_computer_use",
                    "display_width",
                    "display_height",
                    "computer_environment",
                },
            )
        )

    async def build_api_params(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        all_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build Operator API parameters with computer-use-preview specific requirements."""
        api_params = await super().build_api_params(messages, tools, all_params)

        model = all_params.get("model", "")
        if "computer-use-preview" in model:
            api_params["truncation"] = "auto"

        return api_params

    def get_provider_tools(self, all_params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get provider tools for Operator API format.

        Note: The hosted computer_use_preview tool is only added when explicitly
        enabled AND using the computer-use-preview model. For gpt-4.1 and other
        models, use the custom function-based computer_use tool instead.
        """
        provider_tools = super().get_provider_tools(all_params)

        # Only add hosted tool if explicitly enabled AND using computer-use-preview model
        model = all_params.get("model", "")
        if all_params.get("enable_computer_use", False) and "computer-use-preview" in model:
            display_width = all_params.get("display_width", 1920)
            display_height = all_params.get("display_height", 1080)
            environment = all_params.get("computer_environment", "linux")

            provider_tools.append(
                {
                    "type": "computer_use_preview",
                    "display_width": display_width,
                    "display_height": display_height,
                    "environment": environment,
                },
            )

        return provider_tools
