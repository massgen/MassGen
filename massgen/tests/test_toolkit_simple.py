#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple test script for the toolkit registration system.
"""

import os
import sys
from typing import Any, Dict, List

from massgen.toolkits import (
    BaseToolkit,
    ToolkitManager,
    ToolType,
    register_builtin_toolkits,
    toolkit_registry,
)

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class CustomToolkit(BaseToolkit):
    """Example custom toolkit."""

    @property
    def toolkit_id(self) -> str:
        return "custom_toolkit"

    @property
    def toolkit_type(self) -> ToolType:
        return ToolType.BUILTIN

    def is_enabled(self, config: Dict[str, Any]) -> bool:
        return config.get("enable_custom", False)

    def get_tools(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        api_format = config.get("api_format", "chat_completions")

        if api_format == "chat_completions":
            return [
                {
                    "type": "function",
                    "function": {
                        "name": "custom_function",
                        "description": "A custom function",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "input": {
                                    "type": "string",
                                    "description": "Input parameter",
                                },
                            },
                            "required": ["input"],
                        },
                    },
                },
            ]
        return []


def main():
    """Run the test."""
    print("=" * 60)
    print("Testing Toolkit Registration System")
    print("=" * 60)

    # 1. Register builtin toolkits
    print("\n1. Registering builtin toolkits...")
    register_builtin_toolkits()

    # List all registered toolkits
    all_toolkits = toolkit_registry.list_all_toolkits()
    print("   Registered toolkits:")
    for toolkit_id, info in all_toolkits.items():
        print(f"     - {toolkit_id}: type={info['type']}, providers={info['providers']}")

    # 2. Test getting tools for a provider
    print("\n2. Testing provider tools retrieval for 'openai'...")
    config = {
        "enable_web_search": True,
        "enable_code_interpreter": False,
        "api_format": "chat_completions",
    }
    tools = toolkit_registry.get_provider_tools("openai", config)
    print(f"   Tools retrieved: {len(tools)}")
    for tool in tools:
        if "function" in tool:
            print(f"     - Function: {tool['function']['name']}")
        else:
            print(f"     - Type: {tool.get('type', 'unknown')}")

    # 3. Register custom toolkit
    print("\n3. Registering custom toolkit...")
    custom_toolkit = CustomToolkit()
    toolkit_registry.register(custom_toolkit, providers=["openai", "custom_provider"])

    # Check it was registered
    all_toolkits = toolkit_registry.list_all_toolkits()
    if "custom_toolkit" in all_toolkits:
        info = all_toolkits["custom_toolkit"]
        print(f"   Custom toolkit registered: {info}")

    # 4. Test with custom toolkit enabled
    print("\n4. Testing with custom toolkit enabled...")
    config["enable_custom"] = True
    tools = toolkit_registry.get_provider_tools("openai", config)
    print(f"   Total tools with custom enabled: {len(tools)}")
    for tool in tools:
        if "function" in tool:
            print(f"     - {tool['function']['name']}")

    # 5. Test Claude format transformation
    print("\n5. Testing Claude format...")
    claude_config = {
        "enable_web_search": True,
        "enable_code_interpreter": True,
        "api_format": "claude",
    }

    # Register Claude provider
    toolkit_registry.add_provider_support("web_search", "claude")

    claude_tools = toolkit_registry.get_provider_tools("claude", claude_config)
    print(f"   Claude tools: {len(claude_tools)}")
    for tool in claude_tools:
        print(f"     - {tool}")

    # 6. Test Response API format
    print("\n6. Testing Response API format...")
    response_config = {
        "enable_web_search": True,
        "enable_code_interpreter": True,
        "api_format": "response",
    }
    response_tools = toolkit_registry.get_provider_tools("openai", response_config)
    print(f"   Response API tools: {len(response_tools)}")
    for tool in response_tools:
        print(f"     - {tool}")

    # 7. Test provider management
    print("\n7. Testing provider management...")
    providers = toolkit_registry.get_toolkit_providers("web_search")
    print(f"   Providers supporting web_search: {providers}")

    # Remove provider support
    toolkit_registry.remove_provider_support("custom_toolkit", "custom_provider")
    providers = toolkit_registry.get_toolkit_providers("custom_toolkit")
    print(f"   Providers after removal: {providers}")

    # 8. Test ToolkitManager
    print("\n8. Testing ToolkitManager...")
    toolkits = ToolkitManager.list_toolkits()
    print(f"   All toolkits via manager: {toolkits}")

    toolkits_for_openai = ToolkitManager.list_toolkits("openai")
    print(f"   OpenAI toolkits via manager: {toolkits_for_openai}")

    print("\n" + "=" * 60)
    print("Test completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
