#!/usr/bin/env python3
"""
MassGen v3 Command Line Interface

A clean CLI for MassGen v3 with file-based configuration support.
Supports both interactive mode and single-question mode.

Usage examples:
    # Use YAML/JSON configuration file
    python -m massgen.v3.cli --config config.yaml "What is the capital of France?"
    
    # Quick setup with backend and model
    python -m massgen.v3.cli --backend openai --model gpt-4o-mini "What is 2+2?"
    
    # Interactive mode
    python -m massgen.v3.cli --config config.yaml
    
    # Multiple agents from config
    python -m massgen.v3.cli --config multi_agent.yaml "Compare different approaches to renewable energy"
"""

import argparse
import asyncio
import json
import os
import sys
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List

# Add project root to path for imports
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from massgen.v3.backend.openai_backend import OpenAIBackend
from massgen.v3.backend.grok_backend import GrokBackend
from massgen.v3.chat_agent import SingleAgent
from massgen.v3.orchestrator import MassOrchestrator
from massgen.v3.frontend.coordination_ui import CoordinationUI

# Color constants for terminal output
BRIGHT_CYAN = '\033[96m'
BRIGHT_BLUE = '\033[94m'
BRIGHT_GREEN = '\033[92m'
BRIGHT_YELLOW = '\033[93m'
BRIGHT_MAGENTA = '\033[95m'
BRIGHT_RED = '\033[91m'
BRIGHT_WHITE = '\033[97m'
RESET = '\033[0m'
BOLD = '\033[1m'


class ConfigurationError(Exception):
    """Configuration error for CLI."""
    pass


def load_config_file(config_path: str) -> Dict[str, Any]:
    """Load configuration from YAML or JSON file."""
    path = Path(config_path)
    
    if not path.exists():
        raise ConfigurationError(f"Configuration file not found: {config_path}")
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            if path.suffix.lower() in ['.yaml', '.yml']:
                return yaml.safe_load(f)
            elif path.suffix.lower() == '.json':
                return json.load(f)
            else:
                raise ConfigurationError(f"Unsupported config file format: {path.suffix}")
    except Exception as e:
        raise ConfigurationError(f"Error reading config file: {e}")


def create_backend(backend_type: str, **kwargs) -> Any:
    """Create backend instance from type and parameters."""
    backend_type = backend_type.lower()
    
    if backend_type == 'openai':
        api_key = kwargs.get('api_key') or os.getenv('OPENAI_API_KEY')
        if not api_key:
            raise ConfigurationError("OpenAI API key not found. Set OPENAI_API_KEY or provide in config.")
        return OpenAIBackend(api_key=api_key)
    
    elif backend_type == 'grok':
        api_key = kwargs.get('api_key') or os.getenv('XAI_API_KEY')
        if not api_key:
            raise ConfigurationError("Grok API key not found. Set XAI_API_KEY or provide in config.")
        return GrokBackend(api_key=api_key)
    
    else:
        raise ConfigurationError(f"Unsupported backend type: {backend_type}")


def create_agents_from_config(config: Dict[str, Any]) -> Dict[str, SingleAgent]:
    """Create agents from configuration."""
    agents = {}
    
    # Handle single agent configuration
    if 'agent' in config:
        agent_config = config['agent']
        backend_config = agent_config.get('backend', {})
        backend = create_backend(backend_config['type'], **backend_config)
        
        agent = SingleAgent(
            backend=backend,
            agent_id=agent_config.get('id', 'agent1'),
            system_message=agent_config.get('system_message')
        )
        agents[agent.agent_id] = agent
    
    # Handle multiple agents configuration
    elif 'agents' in config:
        for agent_config in config['agents']:
            backend_config = agent_config.get('backend', {})
            backend = create_backend(backend_config['type'], **backend_config)
            
            agent = SingleAgent(
                backend=backend,
                agent_id=agent_config.get('id', f'agent{len(agents)+1}'),
                system_message=agent_config.get('system_message')
            )
            agents[agent.agent_id] = agent
    
    else:
        raise ConfigurationError("Configuration must contain either 'agent' or 'agents' section")
    
    return agents


def create_simple_config(backend_type: str, model: str, system_message: Optional[str] = None) -> Dict[str, Any]:
    """Create a simple single-agent configuration."""
    return {
        'agent': {
            'id': 'agent1',
            'backend': {
                'type': backend_type,
                'model': model
            },
            'system_message': system_message or "You are a helpful AI assistant."
        },
        'ui': {
            'display_type': 'terminal',
            'logging_enabled': True
        }
    }


async def run_question_with_history(question: str, agents: Dict[str, SingleAgent], ui_config: Dict[str, Any], history: List[Dict[str, Any]]) -> str:
    """Run MassGen with a question and conversation history."""
    # Build messages including history
    messages = history.copy()
    messages.append({"role": "user", "content": question})
    
    if len(agents) == 1:
        # Single agent mode with history
        agent = next(iter(agents.values()))
        print(f"\n🤖 {BRIGHT_CYAN}Single Agent Mode{RESET}")
        print(f"Agent: {agent.agent_id}")
        if history:
            print(f"History: {len(history)//2} previous exchanges")
        print(f"Question: {BRIGHT_WHITE}{question}{RESET}")
        print("\n" + "="*60)
        
        response_content = ""
        
        async for chunk in agent.chat(messages):
            if chunk.type == "content" and chunk.content:
                response_content += chunk.content
                print(chunk.content, end="", flush=True)
            elif chunk.type == "error":
                print(f"\n❌ Error: {chunk.error}")
                return ""
        
        print("\n" + "="*60)
        return response_content
    
    else:
        # Multi-agent mode with history
        orchestrator = MassOrchestrator(agents=agents)
        ui = CoordinationUI(
            display_type=ui_config.get('display_type', 'terminal'),
            logging_enabled=ui_config.get('logging_enabled', True)
        )
        
        print(f"\n🤖 {BRIGHT_CYAN}Multi-Agent Mode{RESET}")
        print(f"Agents: {', '.join(agents.keys())}")
        if history:
            print(f"History: {len(history)//2} previous exchanges")
        print(f"Question: {BRIGHT_WHITE}{question}{RESET}")
        print("\n" + "="*60)
        
        # Use orchestrator chat method directly with full message history
        response_content = ""
        async for chunk in orchestrator.chat(messages):
            if chunk.type == "content" and chunk.content:
                response_content += chunk.content
            elif chunk.type == "done":
                break
        
        return response_content


async def run_single_question(question: str, agents: Dict[str, SingleAgent], ui_config: Dict[str, Any]) -> str:
    """Run MassGen with a single question."""
    if len(agents) == 1:
        # Single agent mode
        agent = next(iter(agents.values()))
        print(f"\n🤖 {BRIGHT_CYAN}Single Agent Mode{RESET}")
        print(f"Agent: {agent.agent_id}")
        print(f"Question: {BRIGHT_WHITE}{question}{RESET}")
        print("\n" + "="*60)
        
        messages = [{"role": "user", "content": question}]
        response_content = ""
        
        async for chunk in agent.chat(messages):
            if chunk.type == "content" and chunk.content:
                response_content += chunk.content
                print(chunk.content, end="", flush=True)
            elif chunk.type == "error":
                print(f"\n❌ Error: {chunk.error}")
                return ""
        
        print("\n" + "="*60)
        return response_content
    
    else:
        # Multi-agent mode
        orchestrator = MassOrchestrator(agents=agents)
        ui = CoordinationUI(
            display_type=ui_config.get('display_type', 'terminal'),
            logging_enabled=ui_config.get('logging_enabled', True)
        )
        
        print(f"\n🤖 {BRIGHT_CYAN}Multi-Agent Mode{RESET}")
        print(f"Agents: {', '.join(agents.keys())}")
        print(f"Question: {BRIGHT_WHITE}{question}{RESET}")
        print("\n" + "="*60)
        
        final_response = await ui.coordinate(orchestrator, question)
        return final_response


async def run_interactive_mode(agents: Dict[str, SingleAgent], ui_config: Dict[str, Any]):
    """Run MassGen in interactive mode with conversation history."""
    print(f"\n{BRIGHT_CYAN}🤖 MassGen v3 Interactive Mode{RESET}")
    print("="*60)
    
    # Display configuration
    print(f"📋 {BRIGHT_YELLOW}Configuration:{RESET}")
    print(f"   Agents: {len(agents)}")
    for agent_id, agent in agents.items():
        backend_name = agent.backend.__class__.__name__.replace('Backend', '')
        print(f"   • {agent_id}: {backend_name}")
    
    mode = "Single Agent" if len(agents) == 1 else "Multi-Agent Coordination"
    print(f"   Mode: {mode}")
    print(f"   UI: {ui_config.get('display_type', 'terminal')}")
    
    print("\n💬 Type your questions below. Type 'quit', 'exit', 'reset', or press Ctrl+C to stop.")
    print("💡 Use 'reset' to clear conversation history.")
    print("="*60)
    
    # Maintain conversation history
    conversation_history = []
    
    try:
        while True:
            try:
                question = input(f"\n{BRIGHT_BLUE}👤 User:{RESET} ").strip()
                
                if question.lower() in ['quit', 'exit', 'q']:
                    print("👋 Goodbye!")
                    break
                
                if question.lower() in ['reset', 'clear']:
                    conversation_history = []
                    # Reset all agents
                    for agent in agents.values():
                        agent.reset()
                    print(f"{BRIGHT_YELLOW}🔄 Conversation history cleared!{RESET}")
                    continue
                
                if not question:
                    print("Please enter a question or type 'quit' to exit.")
                    continue
                
                print(f"\n🔄 {BRIGHT_YELLOW}Processing...{RESET}")
                
                response = await run_question_with_history(question, agents, ui_config, conversation_history)
                
                if response:
                    # Add to conversation history
                    conversation_history.append({"role": "user", "content": question})
                    conversation_history.append({"role": "assistant", "content": response})
                    print(f"\n{BRIGHT_GREEN}✅ Complete!{RESET}")
                    print(f"{BRIGHT_CYAN}💭 History: {len(conversation_history)//2} exchanges{RESET}")
                else:
                    print(f"\n{BRIGHT_RED}❌ No response generated{RESET}")
                
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
                print("Please try again or type 'quit' to exit.")
                
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")


def create_sample_configs():
    """Create sample configuration files."""
    configs_dir = Path("configs")
    configs_dir.mkdir(exist_ok=True)
    
    # Single agent config
    single_agent_config = {
        "agent": {
            "id": "assistant",
            "backend": {
                "type": "openai",
                "model": "gpt-4o-mini"
            },
            "system_message": "You are a helpful AI assistant."
        },
        "ui": {
            "display_type": "terminal",
            "logging_enabled": True
        }
    }
    
    # Multi-agent config
    multi_agent_config = {
        "agents": [
            {
                "id": "researcher",
                "backend": {
                    "type": "openai",
                    "model": "gpt-4o-mini"
                },
                "system_message": "You are a thorough researcher focused on gathering accurate information."
            },
            {
                "id": "analyst",
                "backend": {
                    "type": "grok",
                    "model": "grok-3-mini"
                },
                "system_message": "You are a critical analyst focused on evaluation and insights."
            }
        ],
        "ui": {
            "display_type": "terminal",
            "logging_enabled": True
        }
    }
    
    # Write sample configs
    with open(configs_dir / "single_agent.yaml", 'w') as f:
        yaml.dump(single_agent_config, f, default_flow_style=False)
    
    with open(configs_dir / "multi_agent.yaml", 'w') as f:
        yaml.dump(multi_agent_config, f, default_flow_style=False)
    
    print(f"✅ Sample configurations created in {configs_dir}/")
    print("   • single_agent.yaml - Single agent setup")
    print("   • multi_agent.yaml - Multi-agent coordination")


async def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="MassGen v3 - Multi-Agent Coordination CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use configuration file
  python -m massgen.v3.cli --config config.yaml "What is machine learning?"
  
  # Quick single agent setup
  python -m massgen.v3.cli --backend openai --model gpt-4o-mini "Explain quantum computing"
  
  # Interactive mode
  python -m massgen.v3.cli --config config.yaml
  
  # Create sample configurations
  python -m massgen.v3.cli --create-samples
        """
    )
    
    # Question (optional for interactive mode)
    parser.add_argument("question", nargs='?', 
                       help="Question to ask (optional - if not provided, enters interactive mode)")
    
    # Configuration options
    config_group = parser.add_mutually_exclusive_group()
    config_group.add_argument("--config", type=str,
                             help="Path to YAML/JSON configuration file")
    config_group.add_argument("--backend", type=str, choices=['openai', 'grok'],
                             help="Backend type for quick setup")
    
    # Quick setup options
    parser.add_argument("--model", type=str, default="gpt-4o-mini",
                       help="Model name for quick setup (default: gpt-4o-mini)")
    parser.add_argument("--system-message", type=str,
                       help="System message for quick setup")
    
    # Utility options
    parser.add_argument("--create-samples", action="store_true",
                       help="Create sample configuration files")
    
    # UI options
    parser.add_argument("--no-display", action="store_true",
                       help="Disable visual coordination display")
    parser.add_argument("--no-logs", action="store_true",
                       help="Disable logging")
    
    args = parser.parse_args()
    
    # Handle utility commands
    if args.create_samples:
        create_sample_configs()
        return
    
    # Validate arguments
    if not args.config and not args.backend:
        parser.error("Either --config or --backend must be specified")
    
    try:
        # Load or create configuration
        if args.config:
            config = load_config_file(args.config)
        else:
            config = create_simple_config(args.backend, args.model, args.system_message)
        
        # Apply command-line overrides
        ui_config = config.get('ui', {})
        if args.no_display:
            ui_config['display_type'] = 'simple'
        if args.no_logs:
            ui_config['logging_enabled'] = False
        
        # Create agents
        agents = create_agents_from_config(config)
        
        if not agents:
            raise ConfigurationError("No agents configured")
        
        # Run mode based on whether question was provided
        if args.question:
            response = await run_single_question(args.question, agents, ui_config)
            if response:
                print(f"\n{BRIGHT_GREEN}Final Response:{RESET}")
                print(f"{response}")
        else:
            await run_interactive_mode(agents, ui_config)
        
    except ConfigurationError as e:
        print(f"❌ Configuration error: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())