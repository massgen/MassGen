# -*- coding: utf-8 -*-
"""
Single source of truth for backend capabilities.
All documentation and UI should pull from this registry.

This module defines what each backend supports in terms of:
- Built-in tools (web search, code execution, etc.)
- Filesystem support (none, native, or via MCP)
- Model Context Protocol (MCP) support
- Multimodal capabilities (vision, image generation)
- Available models

Usage:
    from massgen.backend.capabilities import BACKEND_CAPABILITIES, get_capabilities

    # Get capabilities for a backend
    caps = get_capabilities("openai")
    if "web_search" in caps.builtin_tools:
        print("Backend supports web search")

IMPORTANT - Maintaining This Registry:
===========================================

When adding a NEW BACKEND:
1. Add a new entry to BACKEND_CAPABILITIES with all fields filled
2. Ensure the backend_type matches the backend's type string
3. Run tests: `uv run pytest massgen/tests/test_backend_capabilities.py`
4. Regenerate docs: `uv run python docs/scripts/generate_backend_tables.py`
5. Commit both the capabilities.py and generated docs

When adding a NEW FEATURE to an existing backend:
1. Update the backend's entry in BACKEND_CAPABILITIES
2. Add to supported_capabilities or builtin_tools as appropriate
3. Run tests: `uv run pytest massgen/tests/test_backend_capabilities.py`
4. Regenerate docs: `uv run python docs/scripts/generate_backend_tables.py`
5. Update the backend implementation to actually support the feature
6. Verify capability validation works: `validate_backend_config(backend_type, config)`

Why This Matters:
- Config wizard reads from here to show available features
- Documentation is auto-generated from here
- Backend validation uses this to prevent invalid configurations
- If this is out of sync with actual backends, users will experience errors

Testing:
Run the capabilities test suite to verify consistency:
    uv run pytest massgen/tests/test_backend_capabilities.py -v

This will verify:
- All backends in BACKEND_CAPABILITIES have valid configurations
- Required fields are present
- Model lists are not empty
- Default models exist in model lists
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Set


class Capability(Enum):
    """Enumeration of all possible backend capabilities."""

    WEB_SEARCH = "web_search"
    CODE_EXECUTION = "code_execution"
    BASH = "bash"
    MULTIMODAL = "multimodal"
    VISION = "vision"
    MCP = "mcp"
    FILESYSTEM_NATIVE = "filesystem_native"
    FILESYSTEM_MCP = "filesystem_mcp"
    REASONING = "reasoning"
    IMAGE_GENERATION = "image_generation"


@dataclass
class BackendCapabilities:
    """Capabilities for a specific backend."""

    backend_type: str
    provider_name: str
    supported_capabilities: Set[str]  # Set of capability strings (e.g., "web_search")
    builtin_tools: List[str]  # Tools native to the backend
    filesystem_support: str  # "none", "native", or "mcp"
    models: List[str]  # Available models
    default_model: str  # Default model for this backend
    env_var: Optional[str] = None  # Required environment variable (e.g., "OPENAI_API_KEY")
    notes: str = ""  # Additional notes about the backend


# THE REGISTRY - Single source of truth for all backend capabilities
BACKEND_CAPABILITIES: Dict[str, BackendCapabilities] = {
    "openai": BackendCapabilities(
        backend_type="openai",
        provider_name="OpenAI",
        supported_capabilities={
            "web_search",
            "code_execution",
            "mcp",
            "multimodal",
            "reasoning",
            "image_generation",
        },
        builtin_tools=["web_search", "code_interpreter"],
        filesystem_support="mcp",
        models=[
            "gpt-5",
            "gpt-5-mini",
            "gpt-5-nano",
            "gpt-4o",
            "gpt-4o-mini",
            "o4",
            "o4-mini",
        ],
        default_model="gpt-4o",
        env_var="OPENAI_API_KEY",
        notes="Reasoning support in GPT-5 and o-series models. Code interpreter includes Python execution sandbox.",
    ),
    "claude": BackendCapabilities(
        backend_type="claude",
        provider_name="Claude",
        supported_capabilities={
            "web_search",
            "code_execution",
            "mcp",
        },
        builtin_tools=["web_search", "code_execution"],
        filesystem_support="mcp",
        models=[
            "claude-sonnet-4-20250514",
            "claude-opus-4-20250514",
            "claude-3-5-sonnet-latest",
            "claude-3-5-haiku-latest",
        ],
        default_model="claude-sonnet-4-20250514",
        env_var="ANTHROPIC_API_KEY",
        notes="Web search and code execution are built-in tools via Claude's API.",
    ),
    "claude_code": BackendCapabilities(
        backend_type="claude_code",
        provider_name="Claude Code",
        supported_capabilities={
            "bash",
            "mcp",
            "filesystem_native",
        },
        builtin_tools=[
            "Read",
            "Write",
            "Edit",
            "MultiEdit",
            "Bash",
            "Grep",
            "Glob",
            "LS",
            "WebSearch",
            "WebFetch",
            "Task",
            "TodoWrite",
            "NotebookEdit",
            "NotebookRead",
        ],
        filesystem_support="native",
        models=["claude-sonnet-4-5-20250929", "claude-opus-4-20250514"],
        default_model="claude-sonnet-4-5-20250929",
        env_var="ANTHROPIC_API_KEY",
        notes="Native filesystem access via SDK. Extensive built-in tooling for code operations.",
    ),
    "gemini": BackendCapabilities(
        backend_type="gemini",
        provider_name="Gemini",
        supported_capabilities={
            "web_search",
            "code_execution",
            "mcp",
            "multimodal",
        },
        builtin_tools=["google_search_retrieval", "code_execution"],
        filesystem_support="mcp",
        models=[
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-2.0-flash-exp",
            "gemini-exp-1206",
        ],
        default_model="gemini-2.5-flash",
        env_var="GOOGLE_API_KEY",
        notes="Google Search Retrieval provides web search. Multimodal includes vision capabilities.",
    ),
    "grok": BackendCapabilities(
        backend_type="grok",
        provider_name="Grok",
        supported_capabilities={
            "web_search",
            "mcp",
        },
        builtin_tools=["web_search"],
        filesystem_support="mcp",
        models=[
            "grok-beta",
            "grok-vision-beta",
        ],
        default_model="grok-beta",
        env_var="XAI_API_KEY",
        notes="Web search includes real-time data access.",
    ),
    "azure_openai": BackendCapabilities(
        backend_type="azure_openai",
        provider_name="Azure OpenAI",
        supported_capabilities={
            "web_search",
            "code_execution",
            "mcp",
            "multimodal",
        },
        builtin_tools=["web_search", "code_execution"],
        filesystem_support="mcp",
        models=["gpt-4", "gpt-4o", "gpt-35-turbo"],
        default_model="gpt-4o",
        env_var="AZURE_OPENAI_API_KEY",
        notes="Capabilities depend on Azure deployment configuration. MCP support via ChatCompletions base.",
    ),
    "chatcompletion": BackendCapabilities(
        backend_type="chatcompletion",
        provider_name="Chat Completions (Generic)",
        supported_capabilities={
            "mcp",
        },
        builtin_tools=[],
        filesystem_support="mcp",
        models=["custom"],
        default_model="custom",
        env_var=None,
        notes="Generic OpenAI-compatible API. Capabilities vary by provider. Use for LiteLLM, custom endpoints, etc.",
    ),
    "lmstudio": BackendCapabilities(
        backend_type="lmstudio",
        provider_name="LM Studio",
        supported_capabilities={
            "mcp",
        },
        builtin_tools=[],
        filesystem_support="mcp",
        models=["custom"],
        default_model="custom",
        env_var=None,
        notes="Local model hosting. Capabilities depend on loaded model.",
    ),
    "inference": BackendCapabilities(
        backend_type="inference",
        provider_name="Inference (vLLM/SGLang)",
        supported_capabilities={
            "mcp",
        },
        builtin_tools=[],
        filesystem_support="mcp",
        models=["custom"],
        default_model="custom",
        env_var=None,
        notes="Unified backend for vLLM, SGLang, and custom inference servers.",
    ),
    "ag2": BackendCapabilities(
        backend_type="ag2",
        provider_name="AG2 (AutoGen)",
        supported_capabilities={
            "code_execution",
        },
        builtin_tools=[],
        filesystem_support="none",  # MCP support planned for future
        models=["custom"],  # AG2 uses any OpenAI-compatible backend
        default_model="custom",
        env_var=None,  # Depends on underlying LLM backend
        notes="AutoGen framework integration. Supports code execution with multiple executor types (Local, Docker, Jupyter). Uses any OpenAI-compatible LLM backend. MCP support planned.",
    ),
}


def get_capabilities(backend_type: str) -> Optional[BackendCapabilities]:
    """Get capabilities for a backend type.

    Args:
        backend_type: The backend type (e.g., "openai", "claude")

    Returns:
        BackendCapabilities object if found, None otherwise
    """
    return BACKEND_CAPABILITIES.get(backend_type)


def has_capability(backend_type: str, capability: str) -> bool:
    """Check if backend supports a capability.

    Args:
        backend_type: The backend type (e.g., "openai", "claude")
        capability: The capability to check (e.g., "web_search")

    Returns:
        True if backend supports the capability, False otherwise
    """
    caps = get_capabilities(backend_type)
    return capability in caps.supported_capabilities if caps else False


def get_all_backend_types() -> List[str]:
    """Get list of all registered backend types.

    Returns:
        List of backend type strings
    """
    return list(BACKEND_CAPABILITIES.keys())


def get_backends_with_capability(capability: str) -> List[str]:
    """Get all backends that support a given capability.

    Args:
        capability: The capability to search for (e.g., "web_search")

    Returns:
        List of backend types that support the capability
    """
    return [backend_type for backend_type, caps in BACKEND_CAPABILITIES.items() if capability in caps.supported_capabilities]


def validate_backend_config(backend_type: str, config: Dict) -> List[str]:
    """Validate a backend configuration against its capabilities.

    Args:
        backend_type: The backend type
        config: The backend configuration dict

    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    caps = get_capabilities(backend_type)

    if not caps:
        errors.append(f"Unknown backend type: {backend_type}")
        return errors

    # Check if requested tools are supported
    if "enable_web_search" in config and config["enable_web_search"]:
        if "web_search" not in caps.supported_capabilities:
            errors.append(f"{backend_type} does not support web_search")

    if "enable_code_execution" in config and config["enable_code_execution"]:
        if "code_execution" not in caps.supported_capabilities:
            errors.append(f"{backend_type} does not support code_execution")

    if "enable_code_interpreter" in config and config["enable_code_interpreter"]:
        if "code_execution" not in caps.supported_capabilities:
            errors.append(f"{backend_type} does not support code_execution/interpreter")

    # Check MCP configuration
    if "mcp_servers" in config and config["mcp_servers"]:
        if "mcp" not in caps.supported_capabilities:
            errors.append(f"{backend_type} does not support MCP")

    return errors
