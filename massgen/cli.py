#!/usr/bin/env python3
"""
MassGen Command Line Interface

A clean CLI for MassGen with file-based configuration support.
Supports both interactive mode and single-question mode.

Usage examples:
    # Use YAML/JSON configuration file
    python -m massgen.cli --config config.yaml "What is the capital of France?"

    # Quick setup with backend and model
    python -m massgen.cli --backend openai --model gpt-4o-mini "What is 2+2?"

    # Interactive mode
    python -m massgen.cli --config config.yaml

    # Multiple agents from config
    python -m massgen.cli --config multi_agent.yaml "Compare different approaches to renewable energy"
"""

import argparse
import asyncio
import json
import os
import sys
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List

from .utils import MODEL_MAPPINGS, get_backend_type_from_model


# Load environment variables from .env file
def load_env_file():
    """Load environment variables from .env file if it exists."""
    env_file = Path(".env")
    if env_file.exists():
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    # Remove quotes if present
                    value = value.strip("\"'")
                    os.environ[key] = value


# Load .env file at module import
load_env_file()

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from massgen.backend.response import ResponseBackend
from massgen.backend.grok import GrokBackend
from massgen.backend.claude import ClaudeBackend
from massgen.backend.gemini import GeminiBackend
from massgen.backend.chat_completions import ChatCompletionsBackend
from massgen.chat_agent import SingleAgent, ConfigurableAgent
from massgen.agent_config import AgentConfig
from massgen.orchestrator import Orchestrator
from massgen.frontend.coordination_ui import CoordinationUI

# Color constants for terminal output
BRIGHT_CYAN = "\033[96m"
BRIGHT_BLUE = "\033[94m"
BRIGHT_GREEN = "\033[92m"
BRIGHT_YELLOW = "\033[93m"
BRIGHT_MAGENTA = "\033[95m"
BRIGHT_RED = "\033[91m"
BRIGHT_WHITE = "\033[97m"
RESET = "\033[0m"
BOLD = "\033[1m"


class ConfigurationError(Exception):
    """Configuration error for CLI."""

    pass


def load_config_file(config_path: str) -> Dict[str, Any]:
    """Load configuration from YAML or JSON file."""
    path = Path(config_path)

    # If file doesn't exist in current path, try massgen/configs/ directory
    if not path.exists():
        # Try in massgen/configs/ directory
        configs_path = Path(__file__).parent / "configs" / path.name
        if configs_path.exists():
            path = configs_path
        else:
            raise ConfigurationError(
                f"Configuration file not found: {config_path} (also checked {configs_path})"
            )

    try:
        with open(path, "r", encoding="utf-8") as f:
            if path.suffix.lower() in [".yaml", ".yml"]:
                return yaml.safe_load(f)
            elif path.suffix.lower() == ".json":
                return json.load(f)
            else:
                raise ConfigurationError(
                    f"Unsupported config file format: {path.suffix}"
                )
    except Exception as e:
        raise ConfigurationError(f"Error reading config file: {e}")


def create_backend(backend_type: str, **kwargs) -> Any:
    """Create backend instance from type and parameters."""
    backend_type = backend_type.lower()

    if backend_type == "openai":
        api_key = kwargs.get("api_key") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ConfigurationError(
                "OpenAI API key not found. Set OPENAI_API_KEY or provide in config."
            )
        return ResponseBackend(api_key=api_key)

    elif backend_type == "grok":
        api_key = kwargs.get("api_key") or os.getenv("XAI_API_KEY")
        if not api_key:
            raise ConfigurationError(
                "Grok API key not found. Set XAI_API_KEY or provide in config."
            )
        return GrokBackend(api_key=api_key)

    elif backend_type == "claude":
        api_key = kwargs.get("api_key") or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ConfigurationError(
                "Claude API key not found. Set ANTHROPIC_API_KEY or provide in config."
            )
        return ClaudeBackend(api_key=api_key)

    elif backend_type == "gemini":
        api_key = (
            kwargs.get("api_key")
            or os.getenv("GOOGLE_API_KEY")
            or os.getenv("GEMINI_API_KEY")
        )
        if not api_key:
            raise ConfigurationError(
                "Gemini API key not found. Set GOOGLE_API_KEY or provide in config."
            )
        return GeminiBackend(api_key=api_key)

    elif backend_type == "chatcompletion":
        api_key = kwargs.get("api_key")
        base_url = kwargs.get("base_url")
        
        # Determine API key based on base URL if not explicitly provided
        if not api_key:
            if base_url and "cerebras.ai" in base_url:
                api_key = os.getenv("CEREBRAS_API_KEY")
                if not api_key:
                    raise ConfigurationError(
                        "Cerebras AI API key not found. Set CEREBRAS_API_KEY or provide in config."
                    )
        
        return ChatCompletionsBackend(api_key=api_key)

    else:
        raise ConfigurationError(f"Unsupported backend type: {backend_type}")



def create_agents_from_config(config: Dict[str, Any]) -> Dict[str, ConfigurableAgent]:
    """Create agents from configuration."""
    agents = {}

    agent_entries = (
        [config["agent"]] if "agent" in config else
        config.get("agents", None)
    )

    if not agent_entries:
        raise ConfigurationError("Configuration must contain either 'agent' or 'agents' section")

    for i, agent_data in enumerate(agent_entries, start=1):
        backend_config = agent_data.get("backend", {})

        # Infer backend type from model if not explicitly provided
        backend_type = backend_config.get("type") or (
            get_backend_type_from_model(backend_config["model"])
            if "model" in backend_config else None
        )
        if not backend_type:
            raise ConfigurationError("Backend type must be specified or inferrable from model")

        backend = create_backend(backend_type, **backend_config)
        backend_params = {k: v for k, v in backend_config.items() if k != "type"}

        backend_type_lower = backend_type.lower()
        if backend_type_lower == "openai":
            agent_config = AgentConfig.create_openai_config(**backend_params)
        elif backend_type_lower == "claude":
            agent_config = AgentConfig.create_claude_config(**backend_params)
        elif backend_type_lower == "grok":
            agent_config = AgentConfig.create_grok_config(**backend_params)
        elif backend_type_lower == "gemini":
            agent_config = AgentConfig.create_gemini_config(**backend_params)
        elif backend_type_lower == "chatcompletion":
            agent_config = AgentConfig.create_chatcompletion_config(**backend_params)
        else:
            agent_config = AgentConfig(backend_params=backend_config)

        agent_config.agent_id = agent_data.get("id", f"agent{i}")
        agent_config.custom_system_instruction = agent_data.get("system_message")

        agent = ConfigurableAgent(config=agent_config, backend=backend)
        agents[agent.config.agent_id] = agent

    return agents


def create_simple_config(
    backend_type: str, model: str, system_message: Optional[str] = None, base_url: Optional[str] = None
) -> Dict[str, Any]:
    """Create a simple single-agent configuration."""
    backend_config = {"type": backend_type, "model": model}
    if base_url:
        backend_config["base_url"] = base_url
    
    return {
        "agent": {
            "id": "agent1",
            "backend": backend_config,
            "system_message": system_message or "You are a helpful AI assistant.",
        },
        "ui": {"display_type": "rich_terminal", "logging_enabled": True},
    }


async def run_question_with_history(
    question: str,
    agents: Dict[str, SingleAgent],
    ui_config: Dict[str, Any],
    history: List[Dict[str, Any]],
) -> str:
    """Run MassGen with a question and conversation history."""
    # Build messages including history
    messages = history.copy()
    messages.append({"role": "user", "content": question})

    # Check if we should use orchestrator for single agents (default: False for backward compatibility)
    use_orchestrator_for_single = ui_config.get(
        "use_orchestrator_for_single_agent", True
    )

    if len(agents) == 1 and not use_orchestrator_for_single:
        # Single agent mode with history
        agent = next(iter(agents.values()))
        print(f"\n🤖 {BRIGHT_CYAN}Single Agent Mode{RESET}", flush=True)
        print(f"Agent: {agent.agent_id}", flush=True)
        if history:
            print(f"History: {len(history)//2} previous exchanges", flush=True)
        print(f"Question: {question}", flush=True)
        print("\n" + "=" * 60, flush=True)

        response_content = ""

        async for chunk in agent.chat(messages):
            if chunk.type == "content" and chunk.content:
                response_content += chunk.content
                print(chunk.content, end="", flush=True)
            elif chunk.type == "builtin_tool_results":
                # Skip builtin_tool_results to avoid duplication with real-time streaming
                # The backends already show tool status during execution
                continue
            elif chunk.type == "error":
                print(f"\n❌ Error: {chunk.error}", flush=True)
                return ""

        print("\n" + "=" * 60, flush=True)
        return response_content

    else:
        # Multi-agent mode with history
        orchestrator = Orchestrator(agents=agents)
        # Create a fresh UI instance for each question to ensure clean state
        ui = CoordinationUI(
            display_type=ui_config.get("display_type", "rich_terminal"),
            logging_enabled=ui_config.get("logging_enabled", True),
        )

        print(f"\n🤖 {BRIGHT_CYAN}Multi-Agent Mode{RESET}", flush=True)
        print(f"Agents: {', '.join(agents.keys())}", flush=True)
        if history:
            print(f"History: {len(history)//2} previous exchanges", flush=True)
        print(f"Question: {question}", flush=True)
        print("\n" + "=" * 60, flush=True)

        # For multi-agent with history, we need to use a different approach
        # that maintains coordination UI display while supporting conversation context

        if history and len(history) > 0:
            # Use coordination UI with conversation context
            # Extract current question from messages
            current_question = (
                messages[-1].get("content", question) if messages else question
            )

            # Pass the full message context to the UI coordination
            response_content = await ui.coordinate_with_context(
                orchestrator, current_question, messages
            )
        else:
            # Standard coordination for new conversations
            response_content = await ui.coordinate(orchestrator, question)

        return response_content


async def run_single_question(
    question: str, agents: Dict[str, SingleAgent], ui_config: Dict[str, Any]
) -> str:
    """Run MassGen with a single question."""
    # Check if we should use orchestrator for single agents (default: False for backward compatibility)
    use_orchestrator_for_single = ui_config.get(
        "use_orchestrator_for_single_agent", True
    )

    if len(agents) == 1 and not use_orchestrator_for_single:
        # Single agent mode with existing SimpleDisplay frontend
        agent = next(iter(agents.values()))

        print(f"\n🤖 {BRIGHT_CYAN}Single Agent Mode{RESET}", flush=True)
        print(f"Agent: {agent.agent_id}", flush=True)
        print(f"Question: {question}", flush=True)
        print("\n" + "=" * 60, flush=True)

        messages = [{"role": "user", "content": question}]
        response_content = ""

        async for chunk in agent.chat(messages):
            if chunk.type == "content" and chunk.content:
                response_content += chunk.content
                print(chunk.content, end="", flush=True)
            elif chunk.type == "builtin_tool_results":
                # Skip builtin_tool_results to avoid duplication with real-time streaming
                continue
            elif chunk.type == "error":
                print(f"\n❌ Error: {chunk.error}", flush=True)
                return ""

        print("\n" + "=" * 60, flush=True)
        return response_content

    else:
        # Multi-agent mode
        orchestrator = Orchestrator(agents=agents)
        # Create a fresh UI instance for each question to ensure clean state
        ui = CoordinationUI(
            display_type=ui_config.get("display_type", "rich_terminal"),
            logging_enabled=ui_config.get("logging_enabled", True),
        )

        print(f"\n🤖 {BRIGHT_CYAN}Multi-Agent Mode{RESET}", flush=True)
        print(f"Agents: {', '.join(agents.keys())}", flush=True)
        print(f"Question: {question}", flush=True)
        print("\n" + "=" * 60, flush=True)

        final_response = await ui.coordinate(orchestrator, question)
        return final_response


def print_help_messages():
    print(
        "\n💬 Type your questions below. Use slash commands or press Ctrl+C to stop.",
        flush=True,
    )
    print("💡 Commands: /quit, /exit, /reset, /help", flush=True)
    print("=" * 60, flush=True)


async def run_interactive_mode(
    agents: Dict[str, SingleAgent], ui_config: Dict[str, Any]
):
    """Run MassGen in interactive mode with conversation history."""
    print(f"\n{BRIGHT_CYAN}🤖 MassGen Interactive Mode{RESET}", flush=True)
    print("=" * 60, flush=True)

    # Display configuration
    print(f"📋 {BRIGHT_YELLOW}Configuration:{RESET}", flush=True)
    print(f"   Agents: {len(agents)}", flush=True)
    for agent_id, agent in agents.items():
        backend_name = agent.backend.__class__.__name__.replace("Backend", "")
        print(f"   • {agent_id}: {backend_name}", flush=True)

    use_orchestrator_for_single = ui_config.get(
        "use_orchestrator_for_single_agent", True
    )
    if len(agents) == 1:
        mode = (
            "Single Agent (Orchestrator)"
            if use_orchestrator_for_single
            else "Single Agent (Direct)"
        )
    else:
        mode = "Multi-Agent Coordination"
    print(f"   Mode: {mode}", flush=True)
    print(f"   UI: {ui_config.get('display_type', 'rich_terminal')}", flush=True)

    print_help_messages()

    # Maintain conversation history
    conversation_history = []

    try:
        while True:
            try:
                question = input(f"\n{BRIGHT_BLUE}👤 User:{RESET} ").strip()

                # Handle slash commands
                if question.startswith("/"):
                    command = question.lower()

                    if command in ["/quit", "/exit", "/q"]:
                        print("👋 Goodbye!", flush=True)
                        break
                    elif command in ["/reset", "/clear"]:
                        conversation_history = []
                        # Reset all agents
                        for agent in agents.values():
                            agent.reset()
                        print(
                            f"{BRIGHT_YELLOW}🔄 Conversation history cleared!{RESET}",
                            flush=True,
                        )
                        continue
                    elif command in ["/help", "/h"]:
                        print(
                            f"\n{BRIGHT_CYAN}📚 Available Commands:{RESET}", flush=True
                        )
                        print("   /quit, /exit, /q     - Exit the program", flush=True)
                        print(
                            "   /reset, /clear       - Clear conversation history",
                            flush=True,
                        )
                        print(
                            "   /help, /h            - Show this help message",
                            flush=True,
                        )
                        print(
                            "   /status              - Show current status", flush=True
                        )
                        continue
                    elif command == "/status":
                        print(f"\n{BRIGHT_CYAN}📊 Current Status:{RESET}", flush=True)
                        print(
                            f"   Agents: {len(agents)} ({', '.join(agents.keys())})",
                            flush=True,
                        )
                        use_orch_single = ui_config.get(
                            "use_orchestrator_for_single_agent", True
                        )
                        if len(agents) == 1:
                            mode_display = (
                                "Single Agent (Orchestrator)"
                                if use_orch_single
                                else "Single Agent (Direct)"
                            )
                        else:
                            mode_display = "Multi-Agent"
                        print(f"   Mode: {mode_display}", flush=True)
                        print(
                            f"   History: {len(conversation_history)//2} exchanges",
                            flush=True,
                        )
                        continue
                    else:
                        print(f"❓ Unknown command: {command}", flush=True)
                        print("💡 Type /help for available commands", flush=True)
                        continue

                # Handle legacy plain text commands for backwards compatibility
                if question.lower() in ["quit", "exit", "q"]:
                    print("👋 Goodbye!")
                    break

                if question.lower() in ["reset", "clear"]:
                    conversation_history = []
                    for agent in agents.values():
                        agent.reset()
                    print(f"{BRIGHT_YELLOW}🔄 Conversation history cleared!{RESET}")
                    continue

                if not question:
                    print(
                        "Please enter a question or type /help for commands.",
                        flush=True,
                    )
                    continue

                print(f"\n🔄 {BRIGHT_YELLOW}Processing...{RESET}", flush=True)

                response = await run_question_with_history(
                    question, agents, ui_config, conversation_history
                )

                if response:
                    # Add to conversation history
                    conversation_history.append({"role": "user", "content": question})
                    conversation_history.append(
                        {"role": "assistant", "content": response}
                    )
                    print(f"\n{BRIGHT_GREEN}✅ Complete!{RESET}", flush=True)
                    print(
                        f"{BRIGHT_CYAN}💭 History: {len(conversation_history)//2} exchanges{RESET}",
                        flush=True,
                    )
                    print_help_messages()

                else:
                    print(f"\n{BRIGHT_RED}❌ No response generated{RESET}", flush=True)

            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {e}", flush=True)
                print("Please try again or type /quit to exit.", flush=True)

    except KeyboardInterrupt:
        print("\n👋 Goodbye!")

async def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="MassGen - Multi-Agent Coordination CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use configuration file
  python -m massgen.cli --config config.yaml "What is machine learning?"
  
  # Quick single agent setup
  python -m massgen.cli --backend openai --model gpt-4o-mini "Explain quantum computing"
  python -m massgen.cli --backend claude --model claude-sonnet-4-20250514 "Analyze this data"
  
  # Use ChatCompletion backend with custom base URL
  python -m massgen.cli --backend chatcompletion --model gpt-oss-120b --base-url https://api.cerebras.ai/v1/chat/completions "What is 2+2?"
  
  # Interactive mode
  python -m massgen.cli --config config.yaml
  
  # Create sample configurations
  python -m massgen.cli --create-samples

Environment Variables:
  OPENAI_API_KEY      - Required for OpenAI backend
  XAI_API_KEY         - Required for Grok backend  
  ANTHROPIC_API_KEY   - Required for Claude backend
  CEREBRAS_API_KEY    - Required for CEREBRAS CLOUD API (chatcompletion backend)
        """,
    )

    # Question (optional for interactive mode)
    parser.add_argument(
        "question",
        nargs="?",
        help="Question to ask (optional - if not provided, enters interactive mode)",
    )

    # Configuration options
    config_group = parser.add_mutually_exclusive_group()
    config_group.add_argument(
        "--config", type=str, help="Path to YAML/JSON configuration file"
    )
    config_group.add_argument(
        "--backend",
        type=str,
        choices=["chatcompletion", "claude", "gemini", "grok", "openai"],
        help="Backend type for quick setup",
    )

    # Quick setup options
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4o-mini",
        help="Model name for quick setup (default: gpt-4o-mini)",
    )
    parser.add_argument(
        "--system-message", type=str, help="System message for quick setup"
    )
    parser.add_argument(
        "--base-url", type=str, help="Base URL for API endpoint (e.g., https://api.cerebras.ai/v1/chat/completions)"
    )

    # UI options
    parser.add_argument(
        "--no-display", action="store_true", help="Disable visual coordination display"
    )
    parser.add_argument("--no-logs", action="store_true", help="Disable logging")

    args = parser.parse_args()

    # Validate arguments
    if not args.backend:
        if not args.model and not args.config:
            parser.error(
                "If there is not --backend, either --config or --model must be specified"
            )

    try:
        # Load or create configuration
        if args.config:
            config = load_config_file(args.config)
        else:
            model = args.model
            if args.backend:
                backend = args.backend
            else:
                backend = get_backend_type_from_model(model=model)
            if args.system_message:
                system_message = args.system_message
            else:
                system_message = None
            config = create_simple_config(
                backend_type=backend, model=model, system_message=system_message, base_url=args.base_url
            )

        # Apply command-line overrides
        ui_config = config.get("ui", {})
        if args.no_display:
            ui_config["display_type"] = "simple"
        if args.no_logs:
            ui_config["logging_enabled"] = False

        # Create agents
        agents = create_agents_from_config(config)

        if not agents:
            raise ConfigurationError("No agents configured")

        # Run mode based on whether question was provided
        if args.question:
            response = await run_single_question(args.question, agents, ui_config)
            # if response:
            #     print(f"\n{BRIGHT_GREEN}Final Response:{RESET}", flush=True)
            #     print(f"{response}", flush=True)
        else:
            await run_interactive_mode(agents, ui_config)

    except ConfigurationError as e:
        print(f"❌ Configuration error: {e}", flush=True)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n👋 Goodbye!", flush=True)
    except Exception as e:
        print(f"❌ Error: {e}", flush=True)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
