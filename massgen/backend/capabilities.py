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
    MULTIMODAL = "multimodal"  # Legacy - being phased out
    VISION = "vision"  # Legacy - use image_understanding
    MCP = "mcp"
    FILESYSTEM_NATIVE = "filesystem_native"
    FILESYSTEM_MCP = "filesystem_mcp"
    REASONING = "reasoning"
    IMAGE_GENERATION = "image_generation"
    IMAGE_UNDERSTANDING = "image_understanding"
    AUDIO_GENERATION = "audio_generation"
    AUDIO_UNDERSTANDING = "audio_understanding"
    VIDEO_GENERATION = "video_generation"
    VIDEO_UNDERSTANDING = "video_understanding"


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
            "reasoning",
            "image_generation",
            "image_understanding",
            "audio_generation",
            "audio_understanding",
            "video_generation",
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
        notes="Reasoning support in GPT-5 and o-series models. Audio/video generation (v0.0.30+). Video generation via Sora-2 API (v0.0.31).",
    ),
    "claude": BackendCapabilities(
        backend_type="claude",
        provider_name="Claude",
        supported_capabilities={
            "web_search",
            "code_execution",
            "mcp",
            "audio_understanding",
            "video_understanding",
        },
        builtin_tools=["web_search", "code_execution"],
        filesystem_support="mcp",
        models=[
            "claude-haiku-4-5-20251001",
            "claude-sonnet-4-5-20250929",
            "claude-opus-4-1-20250805",
            "claude-sonnet-4-20250514",
            "claude-3-5-sonnet-latest",
            "claude-3-5-haiku-latest",
        ],
        default_model="claude-sonnet-4-5-20250929",
        env_var="ANTHROPIC_API_KEY",
        notes="Web search and code execution are built-in tools. Audio/video understanding support (v0.0.30+).",
    ),
    "claude_code": BackendCapabilities(
        backend_type="claude_code",
        provider_name="Claude Code",
        supported_capabilities={
            "bash",
            "mcp",
            "filesystem_native",
            "image_understanding",
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
        models=[
            "claude-sonnet-4-5-20250929",
            "claude-opus-4-1-20250805",
            "claude-sonnet-4-20250514",
        ],
        default_model="claude-sonnet-4-5-20250929",
        env_var="ANTHROPIC_API_KEY",
        notes=(
            "⚠️ Works with local Claude Code CLI login (`claude login`) or ANTHROPIC_API_KEY. "
            "Native filesystem access via SDK. Extensive built-in tooling for code operations. "
            "Image understanding support."
        ),
    ),
    "gemini": BackendCapabilities(
        backend_type="gemini",
        provider_name="Gemini",
        supported_capabilities={
            "web_search",
            "code_execution",
            "mcp",
            "image_understanding",
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
        env_var="GEMINI_API_KEY",
        notes="Google Search Retrieval provides web search. Image understanding capabilities.",
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
            "grok-4",
            "grok-4-fast",
            "grok-3",
            "grok-3-mini",
        ],
        default_model="grok-4",
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
            "image_generation",
            "image_understanding",
        },
        builtin_tools=["web_search", "code_execution"],
        filesystem_support="mcp",
        models=["gpt-4", "gpt-4o", "gpt-35-turbo"],
        default_model="gpt-4o",
        env_var="AZURE_OPENAI_API_KEY",
        notes="Capabilities depend on Azure deployment configuration. Image understanding and generation via gpt-4o.",
    ),
    "chatcompletion": BackendCapabilities(
        backend_type="chatcompletion",
        provider_name="Chat Completions (Generic)",
        supported_capabilities={
            "mcp",
            "audio_understanding",
            "video_understanding",
        },
        builtin_tools=[],
        filesystem_support="mcp",
        models=["custom"],
        default_model="custom",
        env_var=None,
        notes="Generic OpenAI-compatible API. Audio/video understanding via providers like OpenRouter, Qwen (v0.0.30+). Capabilities vary by provider.",
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
    "zai": BackendCapabilities(
        backend_type="zai",
        provider_name="ZAI (Z.AI)",
        supported_capabilities={
            "mcp",
        },
        builtin_tools=[],
        filesystem_support="mcp",
        models=["glm-4.5", "custom"],
        default_model="glm-4.5",
        env_var="ZAI_API_KEY",
        notes="OpenAI-compatible API from Z.AI. Supports GLM models.",
    ),
    "vllm": BackendCapabilities(
        backend_type="vllm",
        provider_name="vLLM",
        supported_capabilities={
            "mcp",
        },
        builtin_tools=[],
        filesystem_support="mcp",
        models=["custom"],
        default_model="custom",
        env_var=None,
        notes="vLLM inference server. Local model hosting with high throughput.",
    ),
    "sglang": BackendCapabilities(
        backend_type="sglang",
        provider_name="SGLang",
        supported_capabilities={
            "mcp",
        },
        builtin_tools=[],
        filesystem_support="mcp",
        models=["custom"],
        default_model="custom",
        env_var=None,
        notes="SGLang inference server. Fast local model serving.",
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
    # Individual ChatCompletion Provider Backends
    "cerebras": BackendCapabilities(
        backend_type="cerebras",
        provider_name="Cerebras AI",
        supported_capabilities={
            "mcp",
        },
        builtin_tools=[],
        filesystem_support="mcp",
        models=["llama-3.3-70b", "llama-3.1-70b", "llama-3.1-8b"],
        default_model="llama-3.3-70b",
        env_var="CEREBRAS_API_KEY",
        notes="OpenAI-compatible API. Base URL: https://api.cerebras.ai/v1. Ultra-fast inference with Cerebras WSE hardware.",
    ),
    "together": BackendCapabilities(
        backend_type="together",
        provider_name="Together AI",
        supported_capabilities={
            "mcp",
        },
        builtin_tools=[],
        filesystem_support="mcp",
        models=[
            "meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo",
            "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
            "mistralai/Mixtral-8x7B-Instruct-v0.1",
        ],
        default_model="meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo",
        env_var="TOGETHER_API_KEY",
        notes="OpenAI-compatible API. Base URL: https://api.together.xyz/v1. Access to open-source models at scale.",
    ),
    "fireworks": BackendCapabilities(
        backend_type="fireworks",
        provider_name="Fireworks AI",
        supported_capabilities={
            "mcp",
        },
        builtin_tools=[],
        filesystem_support="mcp",
        models=[
            "accounts/fireworks/models/llama-v3p3-70b-instruct",
            "accounts/fireworks/models/llama-v3p1-405b-instruct",
            "accounts/fireworks/models/qwen2p5-72b-instruct",
        ],
        default_model="accounts/fireworks/models/llama-v3p3-70b-instruct",
        env_var="FIREWORKS_API_KEY",
        notes="OpenAI-compatible API. Base URL: https://api.fireworks.ai/inference/v1. Fast inference for production workloads.",
    ),
    "groq": BackendCapabilities(
        backend_type="groq",
        provider_name="Groq",
        supported_capabilities={
            "mcp",
        },
        builtin_tools=[],
        filesystem_support="mcp",
        models=[
            "llama-3.3-70b-versatile",
            "llama-3.1-70b-versatile",
            "mixtral-8x7b-32768",
        ],
        default_model="llama-3.3-70b-versatile",
        env_var="GROQ_API_KEY",
        notes="OpenAI-compatible API. Base URL: https://api.groq.com/openai/v1. Ultra-fast inference with LPU hardware.",
    ),
    "openrouter": BackendCapabilities(
        backend_type="openrouter",
        provider_name="OpenRouter",
        supported_capabilities={
            "mcp",
            "audio_understanding",
            "video_understanding",
        },
        builtin_tools=[],
        filesystem_support="mcp",
        models=["custom"],  # OpenRouter supports 200+ models
        default_model="custom",
        env_var="OPENROUTER_API_KEY",
        notes="OpenAI-compatible API. Base URL: https://openrouter.ai/api/v1. Unified access to 200+ AI models. Audio/video understanding available on compatible models (v0.0.30+).",
    ),
    "moonshot": BackendCapabilities(
        backend_type="moonshot",
        provider_name="Kimi (Moonshot AI)",
        supported_capabilities={
            "mcp",
        },
        builtin_tools=[],
        filesystem_support="mcp",
        models=["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
        default_model="moonshot-v1-128k",
        env_var="MOONSHOT_API_KEY",
        notes="OpenAI-compatible API. Base URL: https://api.moonshot.cn/v1. Chinese language optimized models with long context windows.",
    ),
    "nebius": BackendCapabilities(
        backend_type="nebius",
        provider_name="Nebius AI Studio",
        supported_capabilities={
            "mcp",
        },
        builtin_tools=[],
        filesystem_support="mcp",
        models=["Qwen/Qwen3-4B-fast", "custom"],
        default_model="Qwen/Qwen3-4B-fast",
        env_var="NEBIUS_API_KEY",
        notes="OpenAI-compatible API. Base URL: https://api.studio.nebius.ai/v1. Nebius AI Studio cloud platform.",
    ),
    "poe": BackendCapabilities(
        backend_type="poe",
        provider_name="POE",
        supported_capabilities={
            "mcp",
        },
        builtin_tools=[],
        filesystem_support="mcp",
        models=["custom"],
        default_model="custom",
        env_var="POE_API_KEY",
        notes="OpenAI-compatible API via POE platform. Access to various AI models through POE's ecosystem.",
    ),
    "qwen": BackendCapabilities(
        backend_type="qwen",
        provider_name="Qwen (Alibaba Cloud)",
        supported_capabilities={
            "mcp",
            "audio_understanding",
            "video_understanding",
        },
        builtin_tools=[],
        filesystem_support="mcp",
        models=["qwen-max", "qwen-plus", "qwen-turbo", "qwen3-vl-30b-a3b-thinking"],
        default_model="qwen-max",
        env_var="QWEN_API_KEY",
        notes="OpenAI-compatible API. Base URL: https://dashscope-intl.aliyuncs.com/compatible-mode/v1. Qwen models from Alibaba Cloud. Audio/video understanding support (v0.0.30+).",
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

    # Check for deprecated system prompt parameters (standardized across all backends)
    if "append_system_prompt" in config:
        errors.append(
            "'append_system_prompt' in backend config is not supported. Use 'system_message' at the agent level (outside backend block) instead.",
        )

    if "system_prompt" in config:
        errors.append(
            "'system_prompt' in backend config is not supported. Use 'system_message' at the agent level (outside backend block) instead.",
        )

    return errors
