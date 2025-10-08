# -*- coding: utf-8 -*-
"""
Utility functions for AG2 (AutoGen) adapter.
"""
import os
from typing import Any, Dict

from autogen import AssistantAgent, ConversableAgent, LLMConfig


def setup_api_keys() -> None:
    """Set up API keys for AG2 compatibility."""
    # Copy GEMINI_API_KEY to GOOGLE_GEMINI_API_KEY if it exists
    if "GEMINI_API_KEY" in os.environ and "GOOGLE_GEMINI_API_KEY" not in os.environ:
        os.environ["GOOGLE_GEMINI_API_KEY"] = os.environ["GEMINI_API_KEY"]


def validate_agent_config(cfg: Dict[str, Any], require_llm_config: bool = True) -> None:
    """
    Validate required fields in agent configuration.

    Args:
        cfg: Agent configuration dict
        require_llm_config: If True, llm_config is required. If False, it's optional.
    """
    if require_llm_config and "llm_config" not in cfg:
        raise ValueError("Each AG2 agent configuration must include 'llm_config'.")

    if "name" not in cfg:
        raise ValueError("Each AG2 agent configuration must include 'name'.")


def create_llm_config(llm_config_data: Any) -> LLMConfig:
    """
    Create LLMConfig from dict or list format.

    Supports new AG2 syntax:
    - Single dict: LLMConfig({'model': 'gpt-4', 'api_key': '...'})
    - List of dicts: LLMConfig({'model': 'gpt-4', ...}, {'model': 'gpt-3.5', ...})
    """
    if isinstance(llm_config_data, list):
        # YAML format: llm_config: [{...}, {...}]
        return LLMConfig(*llm_config_data)
    elif isinstance(llm_config_data, dict):
        # YAML format: llm_config: {model: 'gpt-4o', ...}
        return LLMConfig(llm_config_data)
    else:
        raise ValueError(f"llm_config must be a dict or list, got {type(llm_config_data)}")


def create_code_executor(executor_config: Dict[str, Any]) -> Any:
    """Create code executor from configuration."""
    executor_type = executor_config.get("type")

    if not executor_type:
        raise ValueError("code_execution_config.executor must include 'type' field")

    # Remove 'type' from config before passing to executor
    executor_params = {k: v for k, v in executor_config.items() if k != "type"}

    # Create appropriate executor based on type
    if executor_type == "LocalCommandLineCodeExecutor":
        from autogen.coding import LocalCommandLineCodeExecutor

        return LocalCommandLineCodeExecutor(**executor_params)

    elif executor_type == "DockerCommandLineCodeExecutor":
        from autogen.coding import DockerCommandLineCodeExecutor

        return DockerCommandLineCodeExecutor(**executor_params)

    elif executor_type == "YepCodeCodeExecutor":
        from autogen.coding import YepCodeCodeExecutor

        return YepCodeCodeExecutor(**executor_params)

    elif executor_type == "JupyterCodeExecutor":
        from autogen.coding.jupyter import JupyterCodeExecutor

        return JupyterCodeExecutor(**executor_params)

    else:
        raise ValueError(
            f"Unsupported code executor type: {executor_type}. " f"Supported types: LocalCommandLineCodeExecutor, DockerCommandLineCodeExecutor, " f"YepCodeCodeExecutor, JupyterCodeExecutor",
        )


def build_agent_kwargs(cfg: Dict[str, Any], llm_config: LLMConfig, code_executor: Any = None) -> Dict[str, Any]:
    """Build kwargs for agent initialization."""
    agent_kwargs = {
        "name": cfg["name"],
        "system_message": cfg.get("system_message", "You are a helpful AI assistant."),
        "human_input_mode": "NEVER",
        "llm_config": llm_config,
    }

    if code_executor is not None:
        agent_kwargs["code_execution_config"] = {"executor": code_executor}

    return agent_kwargs


def setup_agent_from_config(config: Dict[str, Any], default_llm_config: Any = None) -> ConversableAgent:
    """
    Set up a ConversableAgent from configuration.

    Args:
        config: Agent configuration dict
        default_llm_config: Default llm_config to use if agent doesn't provide one

    Returns:
        ConversableAgent or AssistantAgent instance
    """
    cfg = config.copy()

    # Check if llm_config is provided in agent config
    has_llm_config = "llm_config" in cfg

    # Validate configuration (llm_config optional if default provided)
    validate_agent_config(cfg, require_llm_config=not default_llm_config)

    # Extract agent type
    agent_type = cfg.pop("type", "conversable")

    # Create LLM config
    if has_llm_config:
        llm_config = create_llm_config(cfg.pop("llm_config"))
    elif default_llm_config:
        llm_config = create_llm_config(default_llm_config)
    else:
        raise ValueError("No llm_config provided for agent and no default_llm_config available")

    # Create code executor if configured
    code_executor = None
    if "code_execution_config" in cfg:
        code_exec_config = cfg.pop("code_execution_config")
        if "executor" in code_exec_config:
            code_executor = create_code_executor(code_exec_config["executor"])

    # Build agent kwargs
    agent_kwargs = build_agent_kwargs(cfg, llm_config, code_executor)

    # Create appropriate agent
    if agent_type == "assistant":
        return AssistantAgent(**agent_kwargs)
    elif agent_type == "conversable":
        return ConversableAgent(**agent_kwargs)
    else:
        raise ValueError(
            f"Unsupported AG2 agent type: {agent_type}. Use 'assistant' or 'conversable' for ag2 agents.",
        )
