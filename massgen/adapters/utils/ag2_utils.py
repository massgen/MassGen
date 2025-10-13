# -*- coding: utf-8 -*-
"""
Utility functions for AG2 (AutoGen) adapter.
"""
import os
import time

# Suppress autogen deprecation warnings
import warnings
from typing import Any, Dict, List

warnings.filterwarnings("ignore", category=DeprecationWarning, module="autogen")
warnings.filterwarnings("ignore", message=".*jsonschema.*")
warnings.filterwarnings("ignore", message=".*Pydantic.*")

from autogen import AssistantAgent, ConversableAgent, LLMConfig  # noqa: E402


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


def get_group_initial_message() -> Dict[str, Any] | None:
    """
    Create the initial system message for group chat.

    Returns:
        Dict with role and content for initial system message
    """
    initial_message = f"""
    CURRENT ANSWER from multiple agents for final response to a message is given.
    Different agents may have different builtin tools and capabilities.
    Does the best CURRENT ANSWER address the ORIGINAL MESSAGE well?

    If CURRENT ANSWER is given, digest existing answers, combine their strengths, and do additional work to address their weaknesses.
    if you think CURRENT ANSWER is good enough, you can also use it as your answer.

    *Note*: The CURRENT TIME is **{time.strftime("%Y-%m-%d %H:%M:%S")}**.
    """

    # Not real system message. Can't send system message to group chat.
    # When a non function/tool message is sent to an agent in group chat, it will be treated as user message.
    return {"role": "system", "content": initial_message}


def get_user_agent_initial_system_message() -> str:
    system_message = """"
    You are the User agent overseeing a team of expert agents. They worked together to create an improved answer to the ORIGINAL MESSAGE based on CURRENT ANSWER (if given).

    Does CURRENT ANSWER address the ORIGINAL MESSAGE well? If YES, use the `vote` tool to record your vote and skip the `new_answer` tool.
    Otherwise, find the final improved answer generated by team and use the `new_answer` tool to provide it as your final answer to the ORIGINAL MESSAGE.

    You MUST ONLY use one of the two tools (`vote` or `new_answer`) ONCE to respond.
    """

    return system_message


def postprocess_group_chat_results(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for message in messages:
        if message["content"]:
            message["content"] = f"<SENDER>: {message['name']} </SENDER> \n" + message["content"]
        message["role"] = "assistant"

    return messages


def unregister_tools_for_agent(tools: List[Dict[str, Any]], agent: ConversableAgent) -> None:
    """Unregister all tools from single agent."""
    for tool in tools:
        agent.update_tool_signature(tool_sig=tool, is_remove=True, silent_override=True)


def register_tools_for_agent(tools: List[Dict[str, Any]], agent: ConversableAgent) -> None:
    """Register all tools to single agent."""
    for tool in tools:
        agent.update_tool_signature(tool_sig=tool, is_remove=False, silent_override=True)
