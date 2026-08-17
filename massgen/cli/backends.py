#!/usr/bin/env python3
"""Backend and agent construction from configuration.

Part of the massgen.cli package (extracted from the legacy monolithic cli.py).
"""

import copy
import os
import re
from collections.abc import Callable
from typing import (
    TYPE_CHECKING,
    Any,
)

if TYPE_CHECKING:
    pass


from ..agent_config import AgentConfig
from ..backend.azure_openai import AzureOpenAIBackend
from ..backend.chat_completions import ChatCompletionsBackend
from ..backend.claude import ClaudeBackend
from ..backend.claude_code import ClaudeCodeBackend
from ..backend.codex import CodexBackend
from ..backend.copilot import CopilotBackend
from ..backend.gemini import GeminiBackend
from ..backend.gemini_cli import GeminiCLIBackend
from ..backend.grok import GrokBackend
from ..backend.inference import InferenceBackend
from ..backend.lmstudio import LMStudioBackend
from ..backend.response import ResponseBackend
from ..chat_agent import ConfigurableAgent
from ..dspy_paraphraser import (
    QuestionParaphraser,
    create_dspy_lm_from_backend_config,
    is_dspy_available,
)
from ..logger_config import logger
from ..utils import get_backend_type_from_model
from ..utils.provider_urls import is_atlascloud_url

# --- cross-module references within the cli package ---
from .config_loading import (
    ConfigurationError,
    _route_workspace_path,
    _scope_agent_temporary_workspace,
    _substitute_variables,
)


def _api_key_error_message(
    provider_name: str,
    env_var: str,
    config_path: str | None = None,
) -> str:
    """Generate standard API key error message."""
    msg = (
        f"{provider_name} API key not found. Set {env_var} environment variable.\n"
        "You can add it to a .env file in:\n"
        "  - Current directory: .env\n"
        "  - User config: ~/.config/massgen/.env\n"
        "  - Global: ~/.massgen/.env\n"
        "\nOr run: massgen --setup"
    )
    if config_path:
        msg += f"\n\n📄 Using config: {config_path}"
    return msg


def create_backend(backend_type: str, **kwargs) -> Any:
    """Create backend instance from type and parameters.

    Supported backend types:
    - openai: OpenAI API (requires OPENAI_API_KEY)
    - grok: xAI Grok (requires XAI_API_KEY)
    - sglang: SGLang inference server (local)
    - claude: Anthropic Claude (requires ANTHROPIC_API_KEY)
    - gemini: Google Gemini (requires GOOGLE_API_KEY or GEMINI_API_KEY)
    - chatcompletion: OpenAI-compatible providers (auto-detects API key based on base_url)
    - nvidia_nim: Nvidia NIM (requires NGC_API_KEY)

    Supported backend with external dependencies:
    - ag2/autogen: AG2 (AutoGen) framework agents

    For chatcompletion backend, the following providers are auto-detected:
    - Cerebras AI (cerebras.ai) -> CEREBRAS_API_KEY
    - Together AI (together.ai/together.xyz) -> TOGETHER_API_KEY
    - Fireworks AI (fireworks.ai) -> FIREWORKS_API_KEY
    - Groq (groq.com) -> GROQ_API_KEY
    - Nebius AI Studio (studio.nebius.ai) -> NEBIUS_API_KEY
    - OpenRouter (openrouter.ai) -> OPENROUTER_API_KEY
    - Nvidia NIM (nvidia.com) -> NGC_API_KEY
    - POE (poe.com) -> POE_API_KEY
    - Qwen (dashscope.aliyuncs.com) -> QWEN_API_KEY
    - Atlas Cloud (atlascloud.ai) -> ATLASCLOUD_API_KEY

    External agent frameworks are supported via the adapter registry.
    """
    backend_type = backend_type.lower()

    # Extract config path for error messages (and remove it from kwargs so it doesn't interfere)
    config_path = kwargs.pop("_config_path", None)

    # Check if this is a framework/adapter type
    from massgen.adapters import adapter_registry

    if backend_type in adapter_registry:
        # Use ExternalAgentBackend for all registered adapter types
        from massgen.backend.external import ExternalAgentBackend

        return ExternalAgentBackend(adapter_type=backend_type, **kwargs)

    if backend_type == "openai":
        api_key = kwargs.get("api_key") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ConfigurationError(
                _api_key_error_message("OpenAI", "OPENAI_API_KEY", config_path),
            )
        return ResponseBackend(api_key=api_key, **kwargs)

    elif backend_type == "grok":
        api_key = kwargs.get("api_key") or os.getenv("XAI_API_KEY")
        if not api_key:
            raise ConfigurationError(
                _api_key_error_message("Grok", "XAI_API_KEY", config_path),
            )
        return GrokBackend(api_key=api_key, **kwargs)

    elif backend_type == "claude":
        api_key = kwargs.get("api_key") or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ConfigurationError(
                _api_key_error_message("Claude", "ANTHROPIC_API_KEY", config_path),
            )
        return ClaudeBackend(api_key=api_key, **kwargs)

    elif backend_type == "gemini":
        api_key = kwargs.get("api_key") or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ConfigurationError(
                _api_key_error_message("Gemini", "GOOGLE_API_KEY", config_path),
            )
        return GeminiBackend(api_key=api_key, **kwargs)

    elif backend_type == "copilot":
        # Copilot uses local auth via SDK, no API key required here
        return CopilotBackend(api_key="copilot-local", **kwargs)

    elif backend_type == "chatcompletion":
        api_key = kwargs.get("api_key")
        base_url = kwargs.get("base_url")

        # Determine API key based on base URL if not explicitly provided
        if not api_key:
            if base_url and "cerebras.ai" in base_url:
                api_key = os.getenv("CEREBRAS_API_KEY")
                if not api_key:
                    raise ConfigurationError(
                        "Cerebras AI API key not found. Set CEREBRAS_API_KEY environment variable.\n"
                        "You can add it to a .env file in:\n"
                        "  - Current directory: .env\n"
                        "  - Global config: ~/.massgen/.env",
                    )
            elif base_url and "together.xyz" in base_url:
                api_key = os.getenv("TOGETHER_API_KEY")
                if not api_key:
                    raise ConfigurationError(
                        "Together AI API key not found. Set TOGETHER_API_KEY environment variable.\n"
                        "You can add it to a .env file in:\n"
                        "  - Current directory: .env\n"
                        "  - Global config: ~/.massgen/.env",
                    )
            elif base_url and "fireworks.ai" in base_url:
                api_key = os.getenv("FIREWORKS_API_KEY")
                if not api_key:
                    raise ConfigurationError(
                        "Fireworks AI API key not found. Set FIREWORKS_API_KEY environment variable.\n"
                        "You can add it to a .env file in:\n"
                        "  - Current directory: .env\n"
                        "  - Global config: ~/.massgen/.env",
                    )
            elif base_url and "groq.com" in base_url:
                api_key = os.getenv("GROQ_API_KEY")
                if not api_key:
                    raise ConfigurationError(
                        "Groq API key not found. Set GROQ_API_KEY environment variable.\n" "You can add it to a .env file in:\n" "  - Current directory: .env\n" "  - Global config: ~/.massgen/.env",
                    )
            elif base_url and "nebius.com" in base_url:
                api_key = os.getenv("NEBIUS_API_KEY")
                if not api_key:
                    raise ConfigurationError(
                        "Nebius AI Studio API key not found. Set NEBIUS_API_KEY environment variable.\n"
                        "You can add it to a .env file in:\n"
                        "  - Current directory: .env\n"
                        "  - Global config: ~/.massgen/.env",
                    )
            elif base_url and "openrouter.ai" in base_url:
                api_key = os.getenv("OPENROUTER_API_KEY")
                if not api_key:
                    raise ConfigurationError(
                        "OpenRouter API key not found. Set OPENROUTER_API_KEY environment variable.\n"
                        "You can add it to a .env file in:\n"
                        "  - Current directory: .env\n"
                        "  - Global config: ~/.massgen/.env",
                    )
            elif base_url and ("z.ai" in base_url or "bigmodel.cn" in base_url):
                api_key = os.getenv("ZAI_API_KEY")
                if not api_key:
                    raise ConfigurationError(
                        "ZAI API key not found. Set ZAI_API_KEY environment variable.\n" "You can add it to a .env file in:\n" "  - Current directory: .env\n" "  - Global config: ~/.massgen/.env",
                    )
            elif base_url and ("moonshot.ai" in base_url or "moonshot.cn" in base_url):
                api_key = os.getenv("MOONSHOT_API_KEY") or os.getenv("KIMI_API_KEY")
                if not api_key:
                    raise ConfigurationError(
                        "Kimi/Moonshot API key not found. Set MOONSHOT_API_KEY or KIMI_API_KEY environment variable.\n"
                        "You can add it to a .env file in:\n"
                        "  - Current directory: .env\n"
                        "  - Global config: ~/.massgen/.env",
                    )
            elif base_url and "nvidia.com" in base_url:
                api_key = os.getenv("NGC_API_KEY")
                if not api_key:
                    raise ConfigurationError(
                        "Nvidia NIM API key not found. Set NGC_API_KEY environment variable.\n"
                        "You can add it to a .env file in:\n"
                        "  - Current directory: .env\n"
                        "  - Global config: ~/.massgen/.env",
                    )
            elif base_url and "poe.com" in base_url:
                api_key = os.getenv("POE_API_KEY")
                if not api_key:
                    raise ConfigurationError(
                        "POE API key not found. Set POE_API_KEY environment variable.\n" "You can add it to a .env file in:\n" "  - Current directory: .env\n" "  - Global config: ~/.massgen/.env",
                    )
            elif base_url and "aliyuncs.com" in base_url:
                api_key = os.getenv("QWEN_API_KEY")
                if not api_key:
                    raise ConfigurationError(
                        "Qwen API key not found. Set QWEN_API_KEY environment variable.\n" "You can add it to a .env file in:\n" "  - Current directory: .env\n" "  - Global config: ~/.massgen/.env",
                    )
            elif is_atlascloud_url(base_url):
                api_key = os.getenv("ATLASCLOUD_API_KEY")
                if not api_key:
                    raise ConfigurationError(
                        "Atlas Cloud API key not found. Set ATLASCLOUD_API_KEY environment variable.\n"
                        "You can add it to a .env file in:\n"
                        "  - Current directory: .env\n"
                        "  - Global config: ~/.massgen/.env",
                    )

        return ChatCompletionsBackend(api_key=api_key, **kwargs)

    elif backend_type == "zai":
        # ZAI (Zhipu.ai) uses OpenAI-compatible Chat Completions at a custom base_url
        # Supports both global (z.ai) and China (bigmodel.cn) endpoints
        api_key = kwargs.get("api_key") or os.getenv("ZAI_API_KEY")
        if not api_key:
            raise ConfigurationError(
                "ZAI API key not found. Set ZAI_API_KEY environment variable.\n" "You can add it to a .env file in:\n" "  - Current directory: .env\n" "  - Global config: ~/.massgen/.env",
            )
        return ChatCompletionsBackend(api_key=api_key, **kwargs)

    elif backend_type == "cerebras":
        # Cerebras AI uses OpenAI-compatible Chat Completions API
        api_key = kwargs.get("api_key") or os.getenv("CEREBRAS_API_KEY")
        if not api_key:
            raise ConfigurationError(
                _api_key_error_message("Cerebras AI", "CEREBRAS_API_KEY", config_path),
            )
        if "base_url" not in kwargs:
            kwargs["base_url"] = "https://api.cerebras.ai/v1"
        return ChatCompletionsBackend(api_key=api_key, **kwargs)

    elif backend_type == "together":
        # Together AI uses OpenAI-compatible Chat Completions API
        api_key = kwargs.get("api_key") or os.getenv("TOGETHER_API_KEY")
        if not api_key:
            raise ConfigurationError(
                _api_key_error_message("Together AI", "TOGETHER_API_KEY", config_path),
            )
        if "base_url" not in kwargs:
            kwargs["base_url"] = "https://api.together.xyz/v1"
        return ChatCompletionsBackend(api_key=api_key, **kwargs)

    elif backend_type == "fireworks":
        # Fireworks AI uses OpenAI-compatible Chat Completions API
        api_key = kwargs.get("api_key") or os.getenv("FIREWORKS_API_KEY")
        if not api_key:
            raise ConfigurationError(
                _api_key_error_message(
                    "Fireworks AI",
                    "FIREWORKS_API_KEY",
                    config_path,
                ),
            )
        if "base_url" not in kwargs:
            kwargs["base_url"] = "https://api.fireworks.ai/inference/v1"
        return ChatCompletionsBackend(api_key=api_key, **kwargs)

    elif backend_type == "groq":
        # Groq uses OpenAI-compatible Chat Completions API
        api_key = kwargs.get("api_key") or os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ConfigurationError(
                _api_key_error_message("Groq", "GROQ_API_KEY", config_path),
            )
        if "base_url" not in kwargs:
            kwargs["base_url"] = "https://api.groq.com/openai/v1"
        return ChatCompletionsBackend(api_key=api_key, **kwargs)

    elif backend_type == "openrouter":
        # OpenRouter uses OpenAI-compatible Chat Completions API
        api_key = kwargs.get("api_key") or os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ConfigurationError(
                _api_key_error_message("OpenRouter", "OPENROUTER_API_KEY", config_path),
            )
        if "base_url" not in kwargs:
            kwargs["base_url"] = "https://openrouter.ai/api/v1"
        return ChatCompletionsBackend(api_key=api_key, **kwargs)

    elif backend_type == "moonshot":
        # Kimi/Moonshot AI uses OpenAI-compatible Chat Completions API
        api_key = kwargs.get("api_key") or os.getenv("MOONSHOT_API_KEY") or os.getenv("KIMI_API_KEY")
        if not api_key:
            raise ConfigurationError(
                _api_key_error_message("Moonshot AI", "MOONSHOT_API_KEY", config_path),
            )
        if "base_url" not in kwargs:
            kwargs["base_url"] = "https://api.moonshot.cn/v1"
        return ChatCompletionsBackend(api_key=api_key, **kwargs)

    elif backend_type == "nvidia_nim":
        # Nvidia NIM uses OpenAI-compatible Chat Completions API
        api_key = kwargs.get("api_key") or os.getenv("NGC_API_KEY")
        if not api_key:
            raise ConfigurationError(
                _api_key_error_message("Nvidia NIM", "NGC_API_KEY", config_path),
            )
        if "base_url" not in kwargs:
            kwargs["base_url"] = "https://integrate.api.nvidia.com/v1"
        return ChatCompletionsBackend(api_key=api_key, **kwargs)

    elif backend_type == "nebius":
        # Nebius AI Studio uses OpenAI-compatible Chat Completions API
        api_key = kwargs.get("api_key") or os.getenv("NEBIUS_API_KEY")
        if not api_key:
            raise ConfigurationError(
                _api_key_error_message(
                    "Nebius AI Studio",
                    "NEBIUS_API_KEY",
                    config_path,
                ),
            )
        if "base_url" not in kwargs:
            kwargs["base_url"] = "https://api.studio.nebius.ai/v1"
        return ChatCompletionsBackend(api_key=api_key, **kwargs)

    elif backend_type == "poe":
        # POE uses OpenAI-compatible Chat Completions API
        api_key = kwargs.get("api_key") or os.getenv("POE_API_KEY")
        if not api_key:
            raise ConfigurationError(
                _api_key_error_message("POE", "POE_API_KEY", config_path),
            )
        # base_url must be provided in config as it's platform-specific
        return ChatCompletionsBackend(api_key=api_key, **kwargs)

    elif backend_type == "qwen":
        # Qwen uses OpenAI-compatible Chat Completions API
        api_key = kwargs.get("api_key") or os.getenv("QWEN_API_KEY")
        if not api_key:
            raise ConfigurationError(
                _api_key_error_message("Qwen", "QWEN_API_KEY", config_path),
            )
        if "base_url" not in kwargs:
            kwargs["base_url"] = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
        return ChatCompletionsBackend(api_key=api_key, **kwargs)

    elif backend_type == "lmstudio":
        # LM Studio local server (OpenAI-compatible). Defaults handled by backend.
        return LMStudioBackend(**kwargs)

    elif backend_type == "vllm":
        # vLLM local server (OpenAI-compatible). Defaults handled by backend.
        return InferenceBackend(backend_type="vllm", **kwargs)

    elif backend_type == "sglang":
        # SGLang local server (OpenAI-compatible). Defaults handled by backend.
        return InferenceBackend(backend_type="sglang", **kwargs)

    elif backend_type == "claude_code":
        # ClaudeCodeBackend using claude-code-sdk-python
        # Authentication handled by backend (API key or subscription)

        # Validate claude-code-sdk availability
        try:
            pass
        except ImportError:
            raise ConfigurationError(
                "claude-code-sdk not found. Install with: pip install claude-code-sdk",
            )

        return ClaudeCodeBackend(**kwargs)

    elif backend_type == "codex":
        # CodexBackend using OpenAI Codex CLI subprocess wrapper
        # Authentication: API key (OPENAI_API_KEY) or ChatGPT OAuth
        # Requires: npm install -g @openai/codex

        return CodexBackend(**kwargs)

    elif backend_type == "gemini_cli":
        # GeminiCLIBackend using Google Gemini CLI subprocess wrapper
        # Authentication: CLI login (gemini) or GOOGLE_API_KEY/GEMINI_API_KEY
        # Requires: npm install -g @google/gemini-cli

        return GeminiCLIBackend(**kwargs)

    elif backend_type == "antigravity_cli":
        # AntigravityCLIBackend wrapping Google's `agy` Go binary
        # (successor to Gemini CLI for consumer tiers as of 2026-06-18).
        # Authentication: existing Google OAuth at ~/.gemini/google_accounts.json,
        # or GEMINI_API_KEY / GOOGLE_API_KEY env vars (passthrough).
        # Requires: curl -fsSL https://antigravity.google/cli/install.sh | bash

        from massgen.backend import AntigravityCLIBackend

        return AntigravityCLIBackend(**kwargs)

    elif backend_type == "azure_openai":
        api_key = kwargs.get("api_key") or os.getenv("AZURE_OPENAI_API_KEY")
        endpoint = kwargs.get("base_url") or os.getenv("AZURE_OPENAI_ENDPOINT")
        if not api_key:
            raise ConfigurationError(
                _api_key_error_message(
                    "Azure OpenAI",
                    "AZURE_OPENAI_API_KEY",
                    config_path,
                ),
            )
        if not endpoint:
            raise ConfigurationError(
                "Azure OpenAI endpoint not found. Set AZURE_OPENAI_ENDPOINT or provide base_url in config.",
            )
        return AzureOpenAIBackend(**kwargs)

    else:
        raise ConfigurationError(f"Unsupported backend type: {backend_type}")


def create_agents_from_config(
    config: dict[str, Any],
    orchestrator_config: dict[str, Any] | None = None,
    enable_rate_limit: bool = False,
    config_path: str | None = None,
    memory_session_id: str | None = None,
    debug: bool = False,
    filesystem_session_id: str | None = None,
    session_storage_base: str | None = None,
    progress_callback: Callable[[str, str], None] | None = None,
) -> dict[str, ConfigurableAgent]:
    """Create agents from configuration.

    TIMING: This function is instrumented for performance analysis.

    Args:
        config: Configuration dictionary
        orchestrator_config: Optional orchestrator configuration
        enable_rate_limit: Whether to enable rate limiting (from CLI flag)
        config_path: Optional path to the config file for error messages
        memory_session_id: Optional session ID to use for memory isolation.
                          If provided, overrides session_name from YAML config.
        filesystem_session_id: Optional session ID for Docker session pre-mounting.
                   Enables faster multi-turn by avoiding container recreation.
        session_storage_base: Base directory for session storage (e.g., ".massgen/sessions").
                             Required with filesystem_session_id for session pre-mounting.
        progress_callback: Optional callback for progress updates (status, detail).
    """
    agents = {}

    agent_entries = [config["agent"]] if "agent" in config else config.get("agents", None)

    if not agent_entries:
        raise ConfigurationError(
            "Configuration must contain either 'agent' or 'agents' section",
        )

    # Create shared Qdrant client for all agents (avoids concurrent access errors)
    # ONE client can be used by multiple mem0 instances safely
    shared_qdrant_client = None
    global_memory_config = config.get("memory", {})
    if global_memory_config.get("enabled", False) and global_memory_config.get(
        "persistent_memory",
        {},
    ).get("enabled", False):
        try:
            from qdrant_client import QdrantClient

            pm_config = global_memory_config.get("persistent_memory", {})

            # Support both server mode and file-based mode
            qdrant_config = pm_config.get("qdrant", {})
            mode = qdrant_config.get("mode", "local")  # "local" or "server"

            if mode == "server":
                # Server mode (RECOMMENDED for multi-agent)
                host = qdrant_config.get("host", "localhost")
                port = qdrant_config.get("port", 6333)
                shared_qdrant_client = QdrantClient(host=host, port=port)
                logger.info(
                    f"🗄️  Shared Qdrant client created (server mode: {host}:{port})",
                )
            else:
                # Local file-based mode (single agent only)
                # WARNING: Does NOT support concurrent access by multiple agents
                qdrant_path = pm_config.get("path", ".massgen/qdrant")
                shared_qdrant_client = QdrantClient(path=qdrant_path)
                logger.info(
                    f"🗄️  Shared Qdrant client created (local mode: {qdrant_path})",
                )
                if len(agent_entries) > 1:
                    logger.warning(
                        "⚠️  Multi-agent setup detected with local Qdrant mode. "
                        "This may cause concurrent access errors. "
                        "Consider using server mode: set memory.persistent_memory.qdrant.mode='server'",
                    )
        except Exception as e:
            logger.warning(f"⚠️  Failed to create shared Qdrant client: {e}")
            logger.warning("   Persistent memory will be disabled for all agents")
            logger.warning(
                "   For multi-agent setup, start Qdrant server: docker-compose -f docker-compose.qdrant.yml up -d",
            )

    for i, agent_data in enumerate(agent_entries, start=1):
        backend_config = agent_data.get("backend", {})

        # Inject rate limiting flag from CLI
        backend_config["enable_rate_limit"] = enable_rate_limit

        # Inject two-tier workspace setting from coordination config
        orchestrator_section = orchestrator_config or {}
        coordination_settings_for_injection = orchestrator_section.get(
            "coordination",
            {},
        )
        if coordination_settings_for_injection.get("use_two_tier_workspace", False):
            backend_config["use_two_tier_workspace"] = True

        # Inject write_mode so FilesystemManager knows to suppress Docker context mounts
        write_mode_setting = coordination_settings_for_injection.get("write_mode")
        if write_mode_setting:
            backend_config["write_mode"] = write_mode_setting

        # Inject session mount parameters for multi-turn Docker support
        # This enables the session directory to be pre-mounted so all turn
        # workspaces are automatically visible without container recreation
        if filesystem_session_id and session_storage_base:
            backend_config["filesystem_session_id"] = filesystem_session_id
            backend_config["session_storage_base"] = session_storage_base

        # Substitute variables like ${cwd} in backend config, then apply unique suffix
        if "cwd" in backend_config:
            variables = {"cwd": backend_config["cwd"]}
            backend_config = _substitute_variables(backend_config, variables)

            # Route relative workspace paths under .massgen/workspaces/
            backend_config["cwd"] = _route_workspace_path(backend_config["cwd"])

            # Apply unique suffix to workspace paths to prevent filesystem conflicts
            # and identity leakage between agents. Each agent gets a unique suffix.
            # This runs for ALL entrypoints (CLI, SDK, Web UI).
            import uuid
            from pathlib import PurePath

            original_cwd = backend_config["cwd"]
            cwd_path = PurePath(original_cwd)
            leaf = cwd_path.name
            # Normalize only "workspaceN" pattern to prevent identity leakage
            if re.fullmatch(r"workspace\d+", leaf):
                leaf = re.sub(r"\d+$", "", leaf)
                base_name = str(cwd_path.with_name(leaf))
            else:
                base_name = str(cwd_path)
            # Generate unique suffix per agent
            agent_workspace_suffix = uuid.uuid4().hex[:8]
            backend_config["cwd"] = f"{base_name}_{agent_workspace_suffix}"
            logger.debug(
                f"Auto-generated unique workspace: {original_cwd} -> {backend_config['cwd']}",
            )

        # Infer backend type from model if not explicitly provided
        backend_type = backend_config.get("type") or (get_backend_type_from_model(backend_config["model"]) if "model" in backend_config else None)
        if not backend_type:
            raise ConfigurationError(
                "Backend type must be specified or inferrable from model",
            )

        # Add orchestrator context for filesystem setup if available
        if orchestrator_config:
            if "agent_temporary_workspace" in orchestrator_config:
                backend_config["agent_temporary_workspace"] = _scope_agent_temporary_workspace(
                    orchestrator_config["agent_temporary_workspace"],
                )
            # Add orchestrator-level context_paths to all agents
            if "context_paths" in orchestrator_config:
                # Merge orchestrator context_paths with agent-specific ones
                agent_context_paths = backend_config.get("context_paths", [])
                orchestrator_context_paths = orchestrator_config["context_paths"]

                # Deduplicate paths - orchestrator paths take precedence
                merged_paths = orchestrator_context_paths.copy()
                orchestrator_paths_set = {path.get("path") for path in orchestrator_context_paths}

                for agent_path in agent_context_paths:
                    if agent_path.get("path") not in orchestrator_paths_set:
                        merged_paths.append(agent_path)

                backend_config["context_paths"] = merged_paths

            # Inherit enable_multimodal_tools from orchestrator if not set per-agent
            if "enable_multimodal_tools" in orchestrator_config:
                if "enable_multimodal_tools" not in backend_config:
                    backend_config["enable_multimodal_tools"] = orchestrator_config["enable_multimodal_tools"]

            # Inherit generation config from orchestrator if not set per-agent
            # These set default backends/models for image/video/audio generation
            generation_config_keys = [
                "image_generation_backend",
                "image_generation_model",
                "video_generation_backend",
                "video_generation_model",
                "audio_generation_backend",
                "audio_generation_model",
            ]
            for key in generation_config_keys:
                if key in orchestrator_config and key not in backend_config:
                    backend_config[key] = orchestrator_config[key]

            # Also support nested multimodal_config from orchestrator
            if "multimodal_config" in orchestrator_config:
                if "multimodal_config" not in backend_config:
                    backend_config["multimodal_config"] = orchestrator_config["multimodal_config"]

        # Add config path for better error messages
        if config_path:
            backend_config["_config_path"] = config_path

        # Get agent_id for AgentConfig and backend (needed for MCP tool span correlation)
        agent_id = agent_data.get("id", f"agent{i}")

        # Emit progress for this agent
        total = len(agent_entries)
        if progress_callback:
            progress_callback(
                f"🤖 Initializing {agent_id} ({i}/{total})...",
                f"Backend: {backend_type}",
            )

        # Pass agent_id to backend for MCP tool span correlation
        backend = create_backend(backend_type, agent_id=agent_id, **backend_config)
        backend_params = {k: v for k, v in backend_config.items() if k not in ("type", "_config_path")}

        backend_type_lower = backend_type.lower()
        if backend_type_lower == "openai":
            agent_config = AgentConfig.create_openai_config(**backend_params)
        elif backend_type_lower == "claude":
            agent_config = AgentConfig.create_claude_config(**backend_params)
        elif backend_type_lower == "grok":
            agent_config = AgentConfig.create_grok_config(**backend_params)
        elif backend_type_lower == "gemini":
            agent_config = AgentConfig.create_gemini_config(**backend_params)
        elif backend_type_lower == "zai":
            agent_config = AgentConfig.create_zai_config(**backend_params)
        elif backend_type_lower == "chatcompletion":
            agent_config = AgentConfig.create_chatcompletion_config(**backend_params)
        elif backend_type_lower in [
            "cerebras",
            "together",
            "fireworks",
            "groq",
            "openrouter",
            "moonshot",
            "nvidia_nim",
            "nebius",
            "poe",
            "qwen",
        ]:
            agent_config = AgentConfig.create_chatcompletion_config(**backend_params)
        elif backend_type_lower == "lmstudio":
            agent_config = AgentConfig.create_lmstudio_config(**backend_params)
        elif backend_type_lower == "vllm":
            agent_config = AgentConfig.create_vllm_config(**backend_params)
        elif backend_type_lower == "sglang":
            agent_config = AgentConfig.create_sglang_config(**backend_params)
        elif backend_type_lower == "claude_code":
            agent_config = AgentConfig.create_claude_code_config(**backend_params)
        elif backend_type_lower == "gemini_cli":
            agent_config = AgentConfig(backend_params=backend_params)
        elif backend_type_lower == "copilot":
            # Copilot maps to standard Config with minimal params?
            # Or dedicated config if needed. For now standard.
            agent_config = AgentConfig(backend_params=backend_params)
        elif backend_type_lower == "azure_openai":
            agent_config = AgentConfig.create_azure_openai_config(**backend_params)
        else:
            agent_config = AgentConfig(backend_params=backend_params)

        agent_config.agent_id = agent_id
        agent_config.subagent_agents = copy.deepcopy(agent_data.get("subagent_agents", []))

        # System message handling: all backends use system_message at agent level
        system_msg = agent_data.get("system_message")
        if system_msg:
            # Set on AgentConfig (ConfigurableAgent will extract it)
            agent_config._custom_system_instruction = system_msg

        # Timeout configuration will be applied to orchestrator instead of individual agents

        # Merge global and per-agent memory configuration
        global_memory_config = config.get("memory", {})
        agent_memory_config = agent_data.get("memory", {})

        # Deep merge: agent config overrides global config
        def merge_configs(global_cfg, agent_cfg):
            """Recursively merge agent config into global config."""
            merged = global_cfg.copy()
            for key, value in agent_cfg.items():
                if isinstance(value, dict) and key in merged and isinstance(merged[key], dict):
                    merged[key] = merge_configs(merged[key], value)
                else:
                    merged[key] = value
            return merged

        memory_config = merge_configs(global_memory_config, agent_memory_config)

        # Create context monitor if memory config is enabled
        context_monitor = None
        if memory_config.get("enabled", False):
            from ..memory._context_monitor import ContextWindowMonitor

            compression_config = memory_config.get("compression", {})
            trigger_threshold = compression_config.get("trigger_threshold", 0.75)
            target_ratio = compression_config.get("target_ratio", 0.40)

            # Get model name from backend config
            model_name = backend_config.get("model", "unknown")

            # Normalize provider name for monitor
            provider_map = {
                "openai": "openai",
                "anthropic": "anthropic",
                "claude": "anthropic",
                "google": "google",
                "gemini": "google",
                "gemini_cli": "google",
            }
            provider = provider_map.get(backend_type_lower, backend_type_lower)

            context_monitor = ContextWindowMonitor(
                model_name=model_name,
                provider=provider,
                trigger_threshold=trigger_threshold,
                target_ratio=target_ratio,
                enabled=True,
            )
            logger.info(
                f"📊 Context monitor created for {agent_config.agent_id}: " f"{context_monitor.context_window:,} tokens, " f"trigger={trigger_threshold * 100:.0f}%, target={target_ratio * 100:.0f}%",
            )

        # Enable NLIP per-agent if configured in YAML
        agent_nlip_section = agent_data.get("nlip") or {}
        agent_enable_nlip = bool(agent_data.get("enable_nlip"))
        if isinstance(agent_nlip_section, dict):
            agent_enable_nlip = agent_enable_nlip or agent_nlip_section.get(
                "enabled",
                False,
            )

        if agent_enable_nlip:
            agent_config.enable_nlip = True
            if isinstance(agent_nlip_section, dict) and agent_nlip_section:
                agent_config.nlip_config = agent_nlip_section
            logger.info(
                f"[CLI] NLIP enabled for agent {agent_config.agent_id} via config file",
            )

        # Create per-agent memory objects if memory is enabled
        conversation_memory = None
        persistent_memory = None

        if memory_config.get("enabled", False):
            from ..memory import ConversationMemory

            # Create conversation memory for this agent
            if memory_config.get("conversation_memory", {}).get("enabled", True):
                conversation_memory = ConversationMemory()
                logger.info(
                    f"💾 Conversation memory created for {agent_config.agent_id}",
                )

            # Create persistent memory for this agent (if enabled)
            if memory_config.get("persistent_memory", {}).get("enabled", False):
                from ..memory import PersistentMemory

                pm_config = memory_config.get("persistent_memory", {})

                # Get persistent memory configuration
                agent_name = pm_config.get("agent_name", agent_config.agent_id)

                # Use unified session: memory_session_id (from CLI) > YAML session_name > None
                session_name = memory_session_id or pm_config.get("session_name")

                on_disk = pm_config.get("on_disk", True)
                qdrant_path = pm_config.get(
                    "path",
                    ".massgen/qdrant",
                )  # Project dir, not /tmp

                try:
                    # Configure LLM for memory operations (fact extraction)
                    # RECOMMENDED: Use mem0's native LLMs (no adapter overhead, no async complexity)
                    llm_cfg = pm_config.get("llm", {})

                    if not llm_cfg:
                        # Default: gpt-4.1-nano-2025-04-14 (mem0's default, fast and cheap for memory ops)
                        llm_cfg = {
                            "provider": "openai",
                            "model": "gpt-4.1-nano-2025-04-14",
                        }

                    # Add API key if not specified
                    if "api_key" not in llm_cfg:
                        llm_provider = llm_cfg.get("provider", "openai")
                        if llm_provider == "openai":
                            llm_cfg["api_key"] = os.getenv("OPENAI_API_KEY")
                        elif llm_provider == "anthropic":
                            llm_cfg["api_key"] = os.getenv("ANTHROPIC_API_KEY")
                        elif llm_provider == "groq":
                            llm_cfg["api_key"] = os.getenv("GROQ_API_KEY")
                        # Add more providers as needed

                    # Configure embedding for persistent memory
                    # RECOMMENDED: Use mem0's native embedders (no adapter overhead)
                    embedding_cfg = pm_config.get("embedding", {})

                    if not embedding_cfg:
                        # Default: OpenAI text-embedding-3-small
                        embedding_cfg = {
                            "provider": "openai",
                            "model": "text-embedding-3-small",
                        }

                    # Add API key if not specified
                    if "api_key" not in embedding_cfg:
                        emb_provider = embedding_cfg.get("provider", "openai")
                        if emb_provider == "openai":
                            api_key = os.getenv("OPENAI_API_KEY")
                            if not api_key:
                                logger.warning(
                                    "⚠️  OPENAI_API_KEY not found in environment - embedding will fail!",
                                )
                            else:
                                logger.debug(
                                    "✅ Using OPENAI_API_KEY from environment",
                                )
                            embedding_cfg["api_key"] = api_key
                        elif emb_provider == "together":
                            embedding_cfg["api_key"] = os.getenv("TOGETHER_API_KEY")
                        elif emb_provider == "azure_openai":
                            embedding_cfg["api_key"] = os.getenv("AZURE_OPENAI_API_KEY")
                        # Add more providers as needed

                    # Use shared Qdrant client if available
                    if shared_qdrant_client:
                        persistent_memory = PersistentMemory(
                            agent_name=agent_name,
                            session_name=session_name,
                            llm_config=llm_cfg,  # Use native mem0 LLM
                            embedding_config=embedding_cfg,  # Use native mem0 embedder
                            qdrant_client=shared_qdrant_client,  # Share ONE client from server
                            debug=debug,  # Enable memory debug mode if --debug flag used
                            on_disk=on_disk,
                        )
                        logger.info(
                            f"💾 Persistent memory created for {agent_config.agent_id} "
                            f"(agent_name={agent_name}, session={session_name or 'cross-session'}, "
                            f"llm={llm_cfg.get('provider')}/{llm_cfg.get('model')}, "
                            f"embedder={embedding_cfg.get('provider')}/{embedding_cfg.get('model')}, shared_qdrant=True)",
                        )
                    else:
                        # Fallback: create individual vector store (for backward compatibility)
                        # WARNING: File-based Qdrant doesn't support concurrent access
                        from mem0.vector_stores.configs import VectorStoreConfig

                        vector_store_config = VectorStoreConfig(
                            config={
                                "on_disk": on_disk,
                                "path": qdrant_path,
                            },
                        )

                        persistent_memory = PersistentMemory(
                            agent_name=agent_name,
                            session_name=session_name,
                            llm_config=llm_cfg,  # Use native mem0 LLM
                            embedding_config=embedding_cfg,  # Use native mem0 embedder
                            vector_store_config=vector_store_config,
                            debug=debug,  # Enable memory debug mode if --debug flag used
                            on_disk=on_disk,
                        )
                        logger.info(
                            f"💾 Persistent memory created for {agent_config.agent_id} "
                            f"(agent_name={agent_name}, session={session_name or 'cross-session'}, "
                            f"llm={llm_cfg.get('provider')}/{llm_cfg.get('model')}, "
                            f"embedder={embedding_cfg.get('provider')}/{embedding_cfg.get('model')}, path={qdrant_path})",
                        )
                except Exception as e:
                    logger.warning(
                        f"⚠️  Failed to create persistent memory for {agent_config.agent_id}: {e}",
                    )
                    persistent_memory = None

        # Get memory recording settings
        recording_config = memory_config.get("recording", {})
        record_all_tool_calls = recording_config.get("record_all_tool_calls", False)
        record_reasoning = recording_config.get("record_reasoning", False)

        # Get per-agent voting sensitivity (if specified)
        agent_voting_sensitivity = agent_data.get("voting_sensitivity")

        # Create agent
        agent = ConfigurableAgent(
            config=agent_config,
            backend=backend,
            conversation_memory=conversation_memory,
            persistent_memory=persistent_memory,
            context_monitor=context_monitor,
            record_all_tool_calls=record_all_tool_calls,
            record_reasoning=record_reasoning,
            voting_sensitivity=agent_voting_sensitivity,
        )

        # Configure retrieval settings from YAML (if memory is enabled)
        if memory_config.get("enabled", False):
            retrieval_config = memory_config.get("retrieval", {})
            agent._retrieval_limit = retrieval_config.get("limit", 5)
            agent._retrieval_exclude_recent = retrieval_config.get(
                "exclude_recent",
                False,
            )

            if retrieval_config or recording_config:  # Log if custom config provided
                config_info = []
                if retrieval_config:
                    config_info.append(
                        f"retrieval(limit={agent._retrieval_limit}, exclude_recent={agent._retrieval_exclude_recent})",
                    )
                if recording_config:
                    config_info.append(
                        f"recording(all_tools={record_all_tool_calls}, reasoning={record_reasoning})",
                    )
                logger.info(
                    f"🔧 Memory configured for {agent_config.agent_id}: {', '.join(config_info)}",
                )

        agents[agent.config.agent_id] = agent

    return agents


def create_dspy_paraphraser_from_config(
    config: dict[str, Any],
    *,
    config_path: str | None = None,
) -> QuestionParaphraser | None:
    """Instantiate DSPy paraphraser from orchestrator configuration.

    Returns:
        QuestionParaphraser instance when DSPy is enabled and properly configured; otherwise None.
    """

    orchestrator_cfg = config.get("orchestrator", {}) if isinstance(config, dict) else {}
    dspy_cfg = orchestrator_cfg.get("dspy") if isinstance(orchestrator_cfg, dict) else None

    if not isinstance(dspy_cfg, dict) or not dspy_cfg.get("enabled", False):
        return None

    if not is_dspy_available():
        location = f" ({config_path})" if config_path else ""
        logger.warning("DSPy is not installed")
        return None

    backend_cfg = dspy_cfg.get("backend", {})
    if not isinstance(backend_cfg, dict) or not backend_cfg:
        logger.warning(
            "DSPy paraphrasing enabled but no backend configuration provided. Skipping DSPy setup.",
        )
        return None

    lm = create_dspy_lm_from_backend_config(backend_cfg)
    if lm is None:
        logger.warning(
            "Failed to initialize DSPy language model from backend configuration. Skipping DSPy setup.",
        )
        return None

    paraphraser_kwargs: dict[str, Any] = {}

    # Simple pass-through configuration values
    for key in [
        "num_variants",
        "strategy",
        "cache_enabled",
        "semantic_threshold",
        "use_chain_of_thought",
        "validate_semantics",
    ]:
        if key in dspy_cfg:
            paraphraser_kwargs[key] = dspy_cfg[key]

    # Temperature range expects a tuple of two numeric values
    temperature_range = dspy_cfg.get("temperature_range")
    if isinstance(temperature_range, (list, tuple)) and len(temperature_range) == 2:
        try:
            paraphraser_kwargs["temperature_range"] = (
                float(temperature_range[0]),
                float(temperature_range[1]),
            )
        except (TypeError, ValueError):
            logger.warning(
                "Ignoring invalid DSPy temperature_range; expected two numeric values.",
            )
    elif temperature_range is not None:
        logger.warning(
            "Ignoring invalid DSPy temperature_range; expected a list/tuple with two values.",
        )

    try:
        paraphraser = QuestionParaphraser(lm=lm, **paraphraser_kwargs)
    except Exception as exc:
        location = f" ({config_path})" if config_path else ""
        logger.warning(f"Failed to initialize DSPy paraphraser{location}: {exc}")
        return None

    logger.info(
        "✅ DSPy question paraphrasing enabled (strategy=%s, variants=%s)",
        paraphraser_kwargs.get("strategy", "balanced"),
        paraphraser_kwargs.get("num_variants", 3),
    )
    return paraphraser
