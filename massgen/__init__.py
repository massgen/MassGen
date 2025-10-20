# -*- coding: utf-8 -*-
"""
MassGen - Multi-Agent System Generator (Foundation Release)

Built on the proven MassGen framework with working tool message handling,
async generator patterns, and reliable multi-agent coordination.

Key Features:
- Multi-backend support: Response API (standard format), Claude (Messages API), Grok (Chat API)
- Builtin tools: Code execution and web search with streaming results
- Async streaming with proper chat agent interfaces and tool result handling
- Multi-agent orchestration with voting and consensus mechanisms
- Real-time frontend displays with multi-region terminal UI
- CLI with file-based YAML configuration and interactive mode
- Proper StreamChunk architecture separating tool_calls from builtin_tool_results

TODO - Missing Features (to be added in future releases):
- ✅ Grok backend testing and fixes (COMPLETED)
- ✅ CLI interface for MassGen (COMPLETED - file-based config, interactive mode, slash commands)
- ✅ Missing test files recovery (COMPLETED - two agents, three agents)
- ✅ Multi-turn conversation support (COMPLETED - dynamic context reconstruction)
- ✅ Chat interface with orchestrator (COMPLETED - async streaming with context)
- ✅ Fix CLI multi-turn conversation display (COMPLETED - coordination UI integration)
- ✅ Case study configurations and test commands (COMPLETED - specialized YAML configs)
- ✅ Claude backend support (COMPLETED - production-ready multi-tool API with streaming)
- ✅ Claude streaming handler fixes (COMPLETED - proper tool argument capture)
- ✅ OpenAI builtin tools support (COMPLETED - code execution and web search streaming)
- ✅ CLI backend parameter passing (COMPLETED - proper ConfigurableAgent integration)
- ✅ StreamChunk builtin_tool_results support (COMPLETED - separate from regular tool_calls)
- ✅ Gemini backend support (COMPLETED - streaming with function calling and builtin tools)
- Orchestrator final_answer_agent configuration support (MEDIUM PRIORITY)
- Configuration options for voting info in user messages (MEDIUM PRIORITY)
- Enhanced frontend features from v0.0.1 (MEDIUM PRIORITY)
- Advanced logging and monitoring capabilities
- Tool execution with custom functions
- Performance optimizations

Usage:
    from massgen import ResponseBackend, create_simple_agent, Orchestrator

    backend = ResponseBackend()
    agent = create_simple_agent(backend, "You are a helpful assistant")
    orchestrator = Orchestrator(agents={"agent1": agent})

    async for chunk in orchestrator.chat_simple("Your question"):
        if chunk.type == "content":
            print(chunk.content, end="")
"""

from .agent_config import AgentConfig
from .backend.claude import ClaudeBackend
from .backend.gemini import GeminiBackend
from .backend.grok import GrokBackend
from .backend.inference import InferenceBackend
from .backend.lmstudio import LMStudioBackend

# Import main classes for convenience
from .backend.response import ResponseBackend
from .chat_agent import (
    ChatAgent,
    ConfigurableAgent,
    SingleAgent,
    create_computational_agent,
    create_expert_agent,
    create_research_agent,
    create_simple_agent,
)
from .message_templates import MessageTemplates, get_templates
from .orchestrator import Orchestrator, create_orchestrator

__version__ = "0.1.1"
__author__ = "MassGen Contributors"


# Python API for programmatic usage
async def run(
    query: str,
    config: str = None,
    model: str = None,
    **kwargs,
) -> dict:
    """Run MassGen query programmatically.

    This is an async wrapper around MassGen's CLI logic, providing a simple
    Python API for programmatic usage.

    Args:
        query: Question or task for the agent(s)
        config: Config file path or @examples/NAME (optional)
        model: Quick single-agent mode with model name (optional)
        **kwargs: Additional configuration options

    Returns:
        dict: Result with 'final_answer' and metadata:
            {
                'final_answer': str,  # The generated answer
                'winning_agent_id': str,  # ID of winning agent (multi-agent)
                'config_used': str,  # Path to config used
            }

    Examples:
        # Single agent with model
        >>> result = await massgen.run(
        ...     query="What is machine learning?",
        ...     model="gpt-5-mini"
        ... )
        >>> print(result['final_answer'])

        # Multi-agent with config
        >>> result = await massgen.run(
        ...     query="Compare renewable energy sources",
        ...     config="@examples/basic_multi"
        ... )

        # Use default config (from first-run setup)
        >>> result = await massgen.run("Your question")

    Note:
        MassGen is async by nature. Use `asyncio.run()` if calling from sync code:
        >>> import asyncio
        >>> result = asyncio.run(massgen.run("Question", model="gpt-5"))
    """
    from pathlib import Path

    from .cli import (
        create_agents_from_config,
        create_simple_config,
        load_config_file,
        resolve_config_path,
        run_single_question,
    )
    from .utils import get_backend_type_from_model

    # Determine config to use
    if config:
        resolved_path = resolve_config_path(config)
        if resolved_path is None:
            raise ValueError("Could not resolve config path. Use --init to create default config.")
        config_dict = load_config_file(str(resolved_path))
        config_path_used = str(resolved_path)
    elif model:
        # Quick single-agent mode
        backend_type = get_backend_type_from_model(model)
        # Create headless UI config for programmatic API usage
        headless_ui_config = {
            "display_type": "simple",
            "logging_enabled": False,
        }
        config_dict = create_simple_config(
            backend_type=backend_type,
            model=model,
            system_message=kwargs.get("system_message"),
            base_url=kwargs.get("base_url"),
            ui_config=headless_ui_config,
        )
        config_path_used = f"single-agent:{model}"
    else:
        # Try default config
        default_config = Path.home() / ".config/massgen/config.yaml"
        if default_config.exists():
            config_dict = load_config_file(str(default_config))
            config_path_used = str(default_config)
        else:
            raise ValueError(
                "No config specified and no default config found.\n" "Run `massgen --init` to create a default configuration.",
            )

    # Extract orchestrator config
    orchestrator_cfg = config_dict.get("orchestrator", {})

    # Create agents
    agents = create_agents_from_config(config_dict, orchestrator_cfg)
    if not agents:
        raise ValueError("No agents configured")

    # Force headless UI config for programmatic API usage
    # Override any UI settings from the config file to ensure non-interactive operation
    ui_config = {
        "display_type": "simple",  # Headless mode for API usage
        "logging_enabled": False,  # Quiet for API usage
    }

    # Run the query
    answer = await run_single_question(
        query,
        agents,
        ui_config,
        orchestrator=orchestrator_cfg,
    )

    # Build result dict
    result = {
        "final_answer": answer,
        "config_used": config_path_used,
    }

    return result


__all__ = [
    # Python API
    "run",
    # Backends
    "ResponseBackend",
    "ClaudeBackend",
    "GeminiBackend",
    "GrokBackend",
    "LMStudioBackend",
    "InferenceBackend",
    # Agents
    "ChatAgent",
    "SingleAgent",
    "ConfigurableAgent",
    "create_simple_agent",
    "create_expert_agent",
    "create_research_agent",
    "create_computational_agent",
    # Orchestrator
    "Orchestrator",
    "create_orchestrator",
    # Configuration
    "AgentConfig",
    "MessageTemplates",
    "get_templates",
    # Metadata
    "__version__",
    "__author__",
]
