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

# LiteLLM integration
#
# LiteLLM integration
#
# NOTE:
# Some environments (including restricted sandboxes / CI hardening) may forbid
# reading system CA bundle locations during module import. `litellm` currently
# initializes an HTTP client + SSL context at import-time, which can raise
# PermissionError and prevent *any* MassGen import (and therefore pytest
# collection). Treat LiteLLM as an optional integration and fail soft.
try:
    from .litellm_provider import MassGenLLM, register_with_litellm

    LITELLM_AVAILABLE = True
except Exception:  # pragma: no cover - environment-specific import side effects
    MassGenLLM = None  # type: ignore[assignment]
    register_with_litellm = None  # type: ignore[assignment]
    LITELLM_AVAILABLE = False
from .message_templates import MessageTemplates, get_templates
from .orchestrator import Orchestrator, create_orchestrator

__version__ = "0.1.92"
__author__ = "MassGen Contributors"


def build_config(
    num_agents: int = None,
    backend: str = None,
    model: str = None,
    models: list = None,
    backends: list = None,
    use_docker: bool = False,
    context_paths: list = None,
) -> dict:
    """Build a MassGen configuration dict programmatically.

    This creates a full-featured multi-agent config similar to --quickstart,
    with code-based tools, orchestration, and all the good defaults.

    Args:
        num_agents: Number of agents (1-10). Auto-detected from models/backends if not specified.
        backend: Backend provider for all agents - 'openai', 'anthropic', 'gemini', 'grok'
        model: Model name for all agents. Supports slash format: 'gpt-5' or 'openai/gpt-5'
        models: List of models, one per agent. Supports slash format:
            - ['gpt-5', 'claude-sonnet-4-5-20250929'] (auto-detect backends)
            - ['openai/gpt-5', 'groq/llama-3.3-70b'] (explicit backends)
        backends: List of backends, one per agent (e.g., ['openai', 'claude']) - optional if using slash format
        use_docker: Enable Docker execution mode (default: False for local mode)
        context_paths: List of context paths with permissions. Each entry can be:
            - str: Path with default "write" permission
            - dict: {"path": "/path", "permission": "read" or "write"}

    Returns:
        dict: Complete configuration dict ready to use with run()

    Examples:
        # Same model for all agents
        >>> config = massgen.build_config(num_agents=3, model="gpt-5")

        # Different models with auto-detected backends
        >>> config = massgen.build_config(
        ...     models=["gpt-5", "claude-sonnet-4-5-20250929", "gemini-2.5-flash"]
        ... )

        # Slash format for explicit backends (recommended for custom models)
        >>> config = massgen.build_config(
        ...     models=["openai/gpt-5", "groq/llama-3.3-70b", "cerebras/llama-3.3-70b"]
        ... )

        # Mixed: auto-detect + explicit
        >>> config = massgen.build_config(
        ...     models=["gpt-5", "groq/llama-3.3-70b-versatile"]
        ... )

        # With context paths (multiple paths with different permissions)
        >>> config = massgen.build_config(
        ...     models=["gpt-5", "claude-sonnet-4.5"],
        ...     context_paths=[
        ...         {"path": "/path/to/project", "permission": "write"},
        ...         {"path": "/path/to/reference", "permission": "read"},
        ...     ]
        ... )

        # Use with run()
        >>> config = massgen.build_config(models=["openai/gpt-5", "gemini/gemini-2.5-flash"])
        >>> result = await massgen.run(query="Your question", config_dict=config)
    """
    from .config_builder import ConfigBuilder
    from .utils import get_backend_type_from_model

    def parse_model_spec(spec: str) -> tuple:
        """Parse 'backend/model' or just 'model' string.

        Returns:
            tuple: (backend_type, model_name)
        """
        if "/" in spec:
            # Explicit backend: "openai/gpt-5" or "groq/llama-3.3-70b"
            parts = spec.split("/", 1)
            return parts[0], parts[1]
        else:
            # Auto-detect backend from model name
            return get_backend_type_from_model(spec), spec

    builder = ConfigBuilder()

    # Determine agents config from parameters
    agents_config = []

    if models:
        # Multiple models specified - one agent per model
        # Supports: "gpt-5", "openai/gpt-5", "groq/llama-3.3-70b"
        for i, model_spec in enumerate(models):
            # Parse backend/model (slash format) or auto-detect
            if backends and i < len(backends):
                # Explicit backends list provided - use that
                backend_type = backends[i]
                model_name = model_spec.split("/")[-1] if "/" in model_spec else model_spec
            else:
                # Parse from spec (supports "backend/model" or just "model")
                backend_type, model_name = parse_model_spec(model_spec)

            provider_info = builder.PROVIDERS.get(backend_type, {})
            agents_config.append(
                {
                    "id": f"agent_{chr(ord('a') + i)}",  # agent_a, agent_b, agent_c, ...
                    "type": provider_info.get("type", backend_type),
                    "model": model_name,
                },
            )
    elif model:
        # Single model for all agents
        # Supports: "gpt-5", "openai/gpt-5", "groq/llama-3.3-70b"
        n = num_agents or 2
        if backend:
            backend_type = backend
            model_name = model.split("/")[-1] if "/" in model else model
        else:
            backend_type, model_name = parse_model_spec(model)
        provider_info = builder.PROVIDERS.get(backend_type, {})

        for i in range(n):
            agents_config.append(
                {
                    "id": f"agent_{chr(ord('a') + i)}",  # agent_a, agent_b, agent_c, ...
                    "type": provider_info.get("type", backend_type),
                    "model": model_name,
                },
            )
    else:
        # Default: 2 agents with gpt-5.4
        default_model = "gpt-5.4"
        default_backend = "openai"
        n = num_agents or 2
        provider_info = builder.PROVIDERS.get(default_backend, {})

        for i in range(n):
            agents_config.append(
                {
                    "id": f"agent_{chr(ord('a') + i)}",  # agent_a, agent_b, agent_c, ...
                    "type": provider_info.get("type", default_backend),
                    "model": default_model,
                },
            )

    # Normalize context paths
    normalized_context_paths = None
    if context_paths:
        normalized_context_paths = []
        for entry in context_paths:
            if isinstance(entry, str):
                # Simple string path - default to write permission
                normalized_context_paths.append({"path": entry, "permission": "write"})
            elif isinstance(entry, dict):
                # Dict with path and optional permission
                normalized_context_paths.append(
                    {
                        "path": entry["path"],
                        "permission": entry.get("permission", "write"),
                    },
                )

    # Generate full config
    config = builder._generate_quickstart_config(
        agents_config,
        context_paths=normalized_context_paths,
        use_docker=use_docker,
    )

    return config


# Python API for programmatic usage
async def run(
    query: str,
    config: str = None,
    config_dict: dict = None,
    model: str = None,
    models: list = None,
    num_agents: int = None,
    use_docker: bool = False,
    enable_filesystem: bool = True,
    enable_logging: bool = False,
    output_file: str = None,
    verbose: bool = False,
    conversation_history: list = None,
    parse_at_references: bool = False,
    **kwargs,
) -> dict:
    """Run MassGen query programmatically.

    This is an async wrapper around MassGen's CLI logic, providing a simple
    Python API for programmatic usage.

    Args:
        query: Question or task for the agent(s)
        config: Config file path or @examples/NAME (optional)
        config_dict: Pre-built config dict from build_config() (optional)
        model: Quick single-agent mode with model name, or all agents use this model
        models: List of models for multi-agent mode (e.g., ['gpt-4o', 'claude-sonnet-4-20250514'])
        num_agents: Number of agents when using single model (default: 2)
        use_docker: Enable Docker execution when building config (default: False)
        enable_filesystem: Enable filesystem/MCP tools (default: True).
            Set to False for lightweight agents without file operations.
        enable_logging: If True, enable logging and return log_directory (default: False)
        output_file: If provided, write final answer to this file path
        verbose: If True, show progress output to stdout (default: False for quiet mode)
        conversation_history: List of prior messages for multi-turn context (optional)
            Format: [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}, ...]
        parse_at_references: If True, parse @path and @path:w references from query
            and add them as context_paths (default: False for explicit control).
            Example: "Review @src/main.py" extracts src/main.py as read-only context.
        **kwargs: Additional configuration options:
            - system_message: Custom system prompt for agents
            - base_url: Custom API endpoint
            - context_paths: List of paths with permissions. Each entry can be:
                - str: Path with default "write" permission
                - dict: {"path": "/path", "permission": "read" or "write"}

    Returns:
        dict: Result with 'final_answer' and coordination metadata:
            {
                'final_answer': str,  # The generated answer
                'config_used': str,  # Path to config or description
                'session_id': str,  # Session ID for continuation
                'log_directory': str,  # Root log directory path
                'final_answer_path': str,  # Path to final/ directory
                'selected_agent': str,  # ID of winning agent (multi-agent only)
                'vote_results': dict,  # Voting details: vote_counts, voter_details, winner, is_tie
                'answers': list,  # List of answers with label, agent_id, answer_path, content
            }

    Examples:
        # Single agent with model
        >>> result = await massgen.run(
        ...     query="What is machine learning?",
        ...     model="gpt-5"
        ... )

        # Multi-agent with same model
        >>> result = await massgen.run(
        ...     query="Compare approaches",
        ...     model="gpt-5",
        ...     num_agents=3
        ... )

        # Multi-agent with different models (auto-builds config)
        >>> result = await massgen.run(
        ...     query="Compare renewable energy sources",
        ...     models=["gpt-5", "claude-sonnet-4-5-20250929", "gemini-2.5-pro"]
        ... )

        # With pre-built config dict
        >>> config = massgen.build_config(models=["gpt-5", "gemini-2.5-pro"])
        >>> result = await massgen.run(query="Your question", config_dict=config)

        # With config file
        >>> result = await massgen.run(
        ...     query="Your question",
        ...     config="@examples/basic_multi"
        ... )

    Note:
        MassGen is async by nature. Use `asyncio.run()` if calling from sync code:
        >>> import asyncio
        >>> result = asyncio.run(massgen.run("Question", model="gpt-4o"))
    """
    from datetime import datetime
    from pathlib import Path

    from .cli import (
        create_agents_from_config,
        create_simple_config,
        load_config_file,
        resolve_config_path,
        run_question_with_history,
        run_single_question,
    )
    from .logger_config import (
        LoggingSession,
        _current_session,
        save_execution_metadata,
        set_current_session,
        setup_logging,
    )

    # Create an isolated logging session for this run so concurrent massgen.run()
    # calls don't share globals (see MAS-274).
    _run_session = LoggingSession.create()
    _session_token = set_current_session(_run_session)

    def _cleanup_session():
        """Ensure session handlers are closed and ContextVar is restored."""
        _run_session.close()
        _current_session.reset(_session_token)

    from .utils import get_backend_type_from_model

    # Initialize logging for programmatic API
    # This ensures massgen.log is created and captures INFO+ messages
    setup_logging(debug=False, session=_run_session)

    # Generate session ID
    session_id = f"api_session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    try:
        # Determine config to use (priority order)
        final_config_dict = None
        raw_config_for_metadata = None  # Raw config (unexpanded env vars) for safe logging
        config_path_used = None

        if config_dict:
            # 1. Pre-built config dict provided directly
            final_config_dict = config_dict
            raw_config_for_metadata = config_dict  # No env expansion for dict input
            config_path_used = "config_dict"

        elif models:
            # 2. Multiple models specified - build multi-agent config
            final_config_dict = build_config(
                models=models,
                use_docker=use_docker,
                context_paths=kwargs.get("context_paths"),
            )
            raw_config_for_metadata = final_config_dict  # No env expansion for built config
            config_path_used = f"multi-agent:{','.join(models)}"

        elif model and enable_filesystem:
            # 3. Model with filesystem support (default) - use full config
            final_config_dict = build_config(
                num_agents=num_agents or 1,
                model=model,
                use_docker=use_docker,
                context_paths=kwargs.get("context_paths"),
            )
            raw_config_for_metadata = final_config_dict  # No env expansion for built config
            config_path_used = f"agent:{model}x{num_agents or 1}"

        elif config:
            # 4. Config file path
            resolved_path = resolve_config_path(config)
            if resolved_path is None:
                raise ValueError("Could not resolve config path. Use --init to create default config.")
            final_config_dict, raw_config_for_metadata = load_config_file(str(resolved_path))
            config_path_used = str(resolved_path)

        elif model:
            # 5. Lightweight mode (enable_filesystem=False) - no MCP/filesystem
            backend_type = get_backend_type_from_model(model)
            headless_ui_config = {
                "display_type": "simple",
                "logging_enabled": enable_logging,
            }
            final_config_dict = create_simple_config(
                backend_type=backend_type,
                model=model,
                system_message=kwargs.get("system_message"),
                base_url=kwargs.get("base_url"),
                ui_config=headless_ui_config,
            )
            raw_config_for_metadata = final_config_dict  # No env expansion for simple config
            config_path_used = f"single-agent-light:{model}"

        else:
            # 6. Try default config
            default_config = Path.home() / ".config/massgen/config.yaml"
            if default_config.exists():
                final_config_dict, raw_config_for_metadata = load_config_file(str(default_config))
                config_path_used = str(default_config)
            else:
                raise ValueError(
                    "No config specified and no default config found.\n" "Options: specify model=, models=, config=, or config_dict=\n" "Or run `massgen --init` to create a default configuration.",
                )

        # Use the determined config
        config_dict = final_config_dict

        # Parse @references from query if opt-in
        if parse_at_references:
            from .path_handling.prompt_parser import (
                PromptParserError,
                parse_prompt_for_context,
            )

            try:
                parsed = parse_prompt_for_context(query)
                if parsed.context_paths:
                    # Inject into config
                    if "orchestrator" not in config_dict:
                        config_dict["orchestrator"] = {}
                    if "context_paths" not in config_dict["orchestrator"]:
                        config_dict["orchestrator"]["context_paths"] = []

                    # Add extracted paths (avoiding duplicates)
                    existing_paths = {p.get("path") for p in config_dict["orchestrator"]["context_paths"]}
                    for ctx in parsed.context_paths:
                        if ctx["path"] not in existing_paths:
                            config_dict["orchestrator"]["context_paths"].append(ctx)
                            existing_paths.add(ctx["path"])

                    # Use cleaned query
                    query = parsed.cleaned_prompt

                    # Show extracted paths if verbose
                    if verbose:
                        print("\n📂 Context paths from query:")
                        for ctx in parsed.context_paths:
                            perm_icon = "📝" if ctx["permission"] == "write" else "📖"
                            print(f"   {perm_icon} {ctx['path']} ({ctx['permission']})")
                        for suggestion in parsed.suggestions:
                            print(f"   💡 {suggestion}")
                        print()
            except PromptParserError as e:
                raise ValueError(str(e)) from e

        # Extract orchestrator config
        orchestrator_cfg = config_dict.get("orchestrator", {})

        # Create agents
        agents = create_agents_from_config(config_dict, orchestrator_cfg)
        if not agents:
            raise ValueError("No agents configured")

        # Save execution metadata for debugging and reconstruction (matches CLI behavior)
        # Use raw_config_for_metadata to avoid logging expanded secrets
        save_execution_metadata(
            query=query,
            config_path=config_path_used if config_path_used and not config_path_used.startswith(("config_dict", "multi-agent:", "agent:", "single-agent-light:")) else None,
            config_content=raw_config_for_metadata,
            cli_args={
                "mode": "programmatic_api",
                "session_id": session_id,
                "enable_logging": enable_logging,
                "verbose": verbose,
                "config_source": config_path_used,
            },
        )

        # Force headless UI config for programmatic API usage
        # Override any UI settings from the config file to ensure non-interactive operation
        ui_config = {
            "display_type": "simple" if verbose else "none",  # Quiet by default, simple if verbose
            "logging_enabled": enable_logging,
        }

        # Build kwargs for run_single_question
        run_kwargs = {
            "orchestrator": orchestrator_cfg,
        }
        if output_file:
            run_kwargs["output_file"] = output_file

        # Extract timeout config from config dict (matches CLI path in cli.py)
        timeout_settings = config_dict.get("timeout_settings", {}) if config_dict else {}
        if timeout_settings:
            from .agent_config import TimeoutConfig

            run_kwargs["timeout_config"] = TimeoutConfig(**timeout_settings)

        # Run the query - use history-aware version if conversation history provided
        if conversation_history:
            # Use run_question_with_history for multi-turn context
            session_info = {
                "session_id": session_id,
                "current_turn": len([m for m in conversation_history if m.get("role") == "user"]),
                "previous_turns": [],
                "winning_agents_history": [],
            }
            response_text, _, _ = await run_question_with_history(
                query,
                agents,
                ui_config,
                history=conversation_history,
                session_info=session_info,
                **run_kwargs,
            )
            response = {"answer": response_text, "coordination_result": None}
        else:
            # Standard single-turn query with metadata
            response = await run_single_question(
                query,
                agents,
                ui_config,
                session_id=session_id,
                return_metadata=True,
                **run_kwargs,
            )

        # Extract answer and coordination result
        answer = response.get("answer", "") if isinstance(response, dict) else response
        coordination_result = response.get("coordination_result") if isinstance(response, dict) else None

        # Build result dict
        result = {
            "final_answer": answer,
            "config_used": config_path_used,
            "session_id": session_id,
        }

        # Add coordination metadata if available
        if coordination_result:
            result["selected_agent"] = coordination_result.get("selected_agent")
            result["vote_results"] = coordination_result.get("vote_results")
            result["answers"] = coordination_result.get("answers")  # List with label, agent_id, answer_path, content
            result["log_directory"] = coordination_result.get("log_directory")
            result["final_answer_path"] = coordination_result.get("final_answer_path")
            result["usage"] = coordination_result.get("usage")  # Token usage stats
            # Note: agent_mapping is inside vote_results (vote_results.agent_mapping)
        elif enable_logging:
            # Fallback: add log directory even without full coordination result
            try:
                from .logger_config import get_log_session_root

                log_dir = get_log_session_root()
                result["log_directory"] = str(log_dir)
            except Exception:
                pass  # Log directory not available

    finally:
        _cleanup_session()

    return result


__all__ = [
    # Python API
    "run",
    "build_config",
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
    # LiteLLM integration
    "MassGenLLM",
    "register_with_litellm",
    "LITELLM_AVAILABLE",
    # Metadata
    "__version__",
    "__author__",
]
