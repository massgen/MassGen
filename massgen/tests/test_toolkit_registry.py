#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script to demonstrate the new toolkit registration system.
"""

import asyncio
import os
import sys
from typing import Any, Dict, List

from massgen.backend.chat_completions import ChatCompletionsBackend
from massgen.backend.claude import ClaudeBackend
from massgen.toolkits import (
    BaseToolkit,
    ToolType,
    register_builtin_toolkits,
    toolkit_registry,
)

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# Custom toolkit example
class CustomRAGToolkit(BaseToolkit):
    """Example custom RAG toolkit."""

    @property
    def toolkit_id(self) -> str:
        return "custom_rag"

    @property
    def toolkit_type(self) -> ToolType:
        return ToolType.BUILTIN

    def is_enabled(self, config: Dict[str, Any]) -> bool:
        return config.get("enable_rag", False)

    def get_tools(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        api_format = config.get("api_format", "chat_completions")

        if api_format == "chat_completions":
            return [
                {
                    "type": "function",
                    "function": {
                        "name": "search_documents",
                        "description": "Search through RAG documents",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {
                                    "type": "string",
                                    "description": "Search query",
                                },
                                "limit": {
                                    "type": "integer",
                                    "description": "Number of results",
                                    "default": 5,
                                },
                            },
                            "required": ["query"],
                        },
                    },
                },
            ]
        return []


def test_toolkit_registration():
    """Test the toolkit registration system."""
    print("=" * 80)
    print("Testing Toolkit Registration System")
    print("=" * 80)

    # 1. Register builtin toolkits
    print("\n1. Registering builtin toolkits...")
    register_builtin_toolkits()

    # List all registered toolkits
    all_toolkits = toolkit_registry.list_all_toolkits()
    print(f"   Registered toolkits: {list(all_toolkits.keys())}")

    # 2. Create backend and check auto-registration
    print("\n2. Creating ChatCompletions backend...")
    backend = ChatCompletionsBackend(
        api_key="test_key",
        enable_web_search=True,
        enable_code_interpreter=False,
    )

    # Check what toolkits are available for this backend
    available = backend.get_available_toolkits()
    print(f"   Available toolkits for {backend.get_provider_name()}: {available}")

    # 3. Test getting provider tools
    print("\n3. Testing provider tools retrieval...")
    config = {
        "enable_web_search": True,
        "enable_code_interpreter": False,
        "api_format": "chat_completions",
    }
    tools = toolkit_registry.get_provider_tools(backend.get_provider_name(), config)
    print(f"   Number of tools retrieved: {len(tools)}")
    if tools:
        print(f"   First tool: {tools[0].get('function', {}).get('name', tools[0].get('name', 'Unknown'))}")

    # 4. Register custom toolkit
    print("\n4. Registering custom RAG toolkit...")
    custom_toolkit = CustomRAGToolkit()
    backend.register_toolkit(custom_toolkit)

    # Check updated toolkits
    available = backend.get_available_toolkits()
    print(f"   Updated toolkits: {available}")

    # Test with custom toolkit enabled
    config["enable_rag"] = True
    tools = toolkit_registry.get_provider_tools(backend.get_provider_name(), config)
    print(f"   Tools with RAG enabled: {len(tools)} tools")
    for tool in tools:
        name = tool.get("function", {}).get("name", tool.get("name", "Unknown"))
        print(f"     - {name}")

    # 5. Test Claude backend
    print("\n5. Testing Claude backend...")
    claude_backend = ClaudeBackend(api_key="test_key")
    print(f"   Provider name: {claude_backend.get_provider_name()}")
    print(f"   Supported builtin tools: {claude_backend.get_supported_builtin_tools()}")

    # Test Claude-specific tool format
    claude_config = {
        "enable_web_search": True,
        "enable_code_execution": True,
        "api_format": "claude",
    }
    claude_tools = toolkit_registry.get_provider_tools(claude_backend.get_provider_name(), claude_config)
    print(f"   Claude tools: {len(claude_tools)} tools")
    for tool in claude_tools:
        print(f"     - {tool}")

    # 6. Test dynamic toolkit management
    print("\n6. Testing dynamic toolkit management...")
    # List all providers for web_search toolkit
    providers = toolkit_registry.get_toolkit_providers("web_search")
    print(f"   Providers supporting web_search: {providers}")

    # Unregister toolkit from a provider
    backend.unregister_toolkit("custom_rag")
    available = backend.get_available_toolkits()
    print(f"   Toolkits after unregistering custom_rag: {available}")

    print("\n" + "=" * 80)
    print("Test completed successfully!")
    print("=" * 80)


async def test_api_params_handler():
    """Test API params handler integration."""
    print("\n" + "=" * 80)
    print("Testing API Params Handler Integration")
    print("=" * 80)

    # Register builtin toolkits first
    register_builtin_toolkits()

    # Create backend
    backend = ChatCompletionsBackend(
        api_key="test_key",
        enable_web_search=True,
        enable_code_interpreter=True,
    )

    # Test building API params
    messages = [{"role": "user", "content": "Hello"}]
    tools = []  # No user-defined tools
    all_params = {
        "model": "gpt-4",
        "enable_web_search": True,
        "enable_code_interpreter": True,
        "temperature": 0.7,
    }

    # Build API params
    api_params = await backend.api_params_handler.build_api_params(messages, tools, all_params)

    print("\nAPI Parameters built:")
    print(f"  - Model: {api_params.get('model')}")
    print(f"  - Temperature: {api_params.get('temperature')}")
    print(f"  - Number of tools: {len(api_params.get('tools', []))}")

    if "tools" in api_params:
        print("\nTools included:")
        for tool in api_params["tools"]:
            if "function" in tool:
                print(f"    - Function: {tool['function']['name']}")
            else:
                print(f"    - Type: {tool.get('type', 'unknown')}")

    print("\n" + "=" * 80)
    print("API Params Handler test completed!")
    print("=" * 80)


if __name__ == "__main__":
    # Run synchronous tests
    test_toolkit_registration()

    # Run async tests
    asyncio.run(test_api_params_handler())
