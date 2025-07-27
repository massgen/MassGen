#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MassGen (Multi-Agent Scaling System) - Command Line Interface

This provides a clean command-line interface for the MassGen system.

Usage examples:
    # Use YAML configuration file
    python cli.py "What is 2+2?" --config examples/production.yaml
    
    # Use model names directly (single or multiple agents)
    python cli.py "What is 2+2?" --models gpt-4o gemini-2.5-flash
    python cli.py "What is 2+2?" --models gpt-4o  # Single agent mode
    
    # Interactive mode (no question provided)
    python cli.py --models gpt-4o grok-4
"""

import argparse
import sys
import os
from pathlib import Path

# Add massgen package to path
sys.path.insert(0, str(Path(__file__).parent))

from massgen import (
    run_mass_with_config, load_config_from_yaml, create_config_from_models, 
    ConfigurationError
)

# Color constants for beautiful terminal output
BRIGHT_CYAN = '\033[96m'
BRIGHT_BLUE = '\033[94m'
BRIGHT_GREEN = '\033[92m'
BRIGHT_YELLOW = '\033[93m'
BRIGHT_MAGENTA = '\033[95m'
BRIGHT_RED = '\033[91m'
BRIGHT_WHITE = '\033[97m'
RESET = '\033[0m'
BOLD = '\033[1m'
DIM = '\033[2m'

def display_vote_distribution(vote_distribution):
    """Display the vote distribution in a more readable format."""
    # sort the keys
    sorted_keys = sorted(vote_distribution.keys())
    for agent_id in sorted_keys:
        print(f"      {BRIGHT_CYAN}Agent {agent_id}{RESET}: {BRIGHT_GREEN}{vote_distribution[agent_id]}{RESET} votes")

def run_interactive_mode(config):
    """Run MassGen in interactive mode, asking for questions repeatedly."""
    
    print("\n🤖 MassGen Interactive Mode")
    print("="*60)
    
    # Display current configuration
    print("📋 Current Configuration:")
    print("-" * 30)
    
    # Show models/agents
    if hasattr(config, 'agents') and config.agents:
        print(f"🤖 Agents ({len(config.agents)}):")
        for i, agent in enumerate(config.agents, 1):
            model_name = getattr(agent.model_config, 'model', 'Unknown') if hasattr(agent, 'model_config') else 'Unknown'
            agent_type = getattr(agent, 'agent_type', 'Unknown')
            tools = getattr(agent.model_config, 'tools', []) if hasattr(agent, 'model_config') else []
            tools_str = ', '.join(tools) if tools else 'None'
            print(f"   {i}. {model_name} ({agent_type})")
            print(f"      Tools: {tools_str}")
    else:
        print("🤖 Single Agent Mode")
    
    # Show orchestrator settings
    if hasattr(config, 'orchestrator'):
        orch = config.orchestrator
        print(f"⚙️  Orchestrator:")
        print(f"   • Duration: {getattr(orch, 'max_duration', 'Default')}s")
        print(f"   • Consensus: {getattr(orch, 'consensus_threshold', 'Default')}")
        print(f"   • Max Debate Rounds: {getattr(orch, 'max_debate_rounds', 'Default')}")
    
    # Show model parameters (from first agent as representative)
    if hasattr(config, 'agents') and config.agents and hasattr(config.agents[0], 'model_config'):
        model_config = config.agents[0].model_config
        print(f"🔧 Model Config:")
        temp = getattr(model_config, 'temperature', 'Default')
        timeout = getattr(model_config, 'inference_timeout', 'Default')
        max_rounds = getattr(model_config, 'max_rounds', 'Default')
        print(f"   • Temperature: {temp}")
        print(f"   • Timeout: {timeout}s")
        print(f"   • Max Debate Rounds: {max_rounds}")
    
    # Show display settings
    if hasattr(config, 'streaming_display'):
        display = config.streaming_display
        display_status = "✅ Enabled" if getattr(display, 'display_enabled', True) else "❌ Disabled"
        logs_status = "✅ Enabled" if getattr(display, 'save_logs', True) else "❌ Disabled"
        print(f"📺 Display: {display_status}")
        print(f"📁 Logs: {logs_status}")
    
    print("-" * 30)
    print("💬 Type your questions below. Type 'quit', 'exit', or press Ctrl+C to stop.")
    print("="*60)
    
    chat_history = ""
    try:
        while True:
            try:
                question = input("\n👤 User: ").strip()
                chat_history += f"User: {question}\n"
                
                if question.lower() in ['quit', 'exit', 'q']:
                    print("👋 Goodbye!")
                    break
                
                if not question:
                    print("Please enter a question or type 'quit' to exit.")
                    continue
                
                print("\n🔄 Processing your question...")
                
                # Run MassGen
                result = run_mass_with_config(chat_history, config)
                
                response = result["answer"]
                chat_history += f"Assistant: {response}\n"
                
                # Display complete conversation exchange
                print(f"\n{BRIGHT_CYAN}{'='*80}{RESET}")
                print(f"{BOLD}{BRIGHT_WHITE}💬 CONVERSATION EXCHANGE{RESET}")
                print(f"{BRIGHT_CYAN}{'='*80}{RESET}")
                
                # User input section with simple indentation
                print(f"\n{BRIGHT_BLUE}👤 User:{RESET}")
                print(f"    {BRIGHT_WHITE}{question}{RESET}")
                
                # Assistant response section 
                print(f"\n{BRIGHT_GREEN}🤖 Assistant:{RESET}")
                
                agents = {f"Agent {agent.agent_id}": agent.model_config.model for agent in config.agents}

                # Show metadata with clean indentation
                if result.get("single_agent_mode", False):
                    print(f"    {BRIGHT_YELLOW}📋 Mode:{RESET} Single Agent")
                    print(f"    {BRIGHT_MAGENTA}🤖 Agents:{RESET} {agents}")
                    print(f"    {BRIGHT_CYAN}🎯 Representative:{RESET} {result['representative_agent_id']}")
                    print(f"    {BRIGHT_GREEN}🔧 Model:{RESET} {result.get('model_used', 'Unknown')}")
                    print(f"    {BRIGHT_BLUE}⏱️  Duration:{RESET} {result['session_duration']:.1f}s")
                    if result.get("citations"):
                        print(f"    {BRIGHT_WHITE}📚 Citations:{RESET} {len(result['citations'])}")
                    if result.get("code"):
                        print(f"    {BRIGHT_WHITE}💻 Code blocks:{RESET} {len(result['code'])}")
                else:
                    print(f"    {BRIGHT_YELLOW}📋 Mode:{RESET} Multi-Agent")
                    print(f"    {BRIGHT_MAGENTA}🤖 Agents:{RESET} {agents}")
                    print(f"    {BRIGHT_CYAN}🎯 Representative:{RESET} {result['representative_agent_id']}")
                    print(f"    {BRIGHT_GREEN}✅ Consensus:{RESET} {result['consensus_reached']}")
                    print(f"    {BRIGHT_BLUE}⏱️  Duration:{RESET} {result['session_duration']:.1f}s")
                    print(f"    {BRIGHT_YELLOW}📊 Vote Distribution:{RESET}")
                    display_vote_distribution(result['summary']['final_vote_distribution'])
                    
                # Print the response with simple indentation
                print(f"\n    {BRIGHT_RED}💡 Response:{RESET}")
                # Indent the response content
                for line in response.split('\n'):
                    print(f"        {line}")
                
                print(f"\n{BRIGHT_CYAN}{'='*80}{RESET}")
                
            except KeyboardInterrupt:
                print("\n👋 Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error processing question: {e}")
                print("Please try again or type 'quit' to exit.")
                
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")


def main():
    """Clean CLI interface for MassGen."""
    parser = argparse.ArgumentParser(
        description="MassGen (Multi-Agent Scaling System) - Clean CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Use YAML configuration
  python cli.py "What is the capital of France?" --config examples/production.yaml
  
  # Use model names directly (single or multiple agents)
  python cli.py "What is 2+2?" --models gpt-4o gemini-2.5-flash
  python cli.py "What is 2+2?" --models gpt-4o  # Single agent mode
  
  # Interactive mode (no question provided)
  python cli.py --models gpt-4o grok-4
  
  # Override parameters
  python cli.py "Question" --models gpt-4o gemini-2.5-flash --max-duration 1200 --consensus 0.8
        """
    )
    
    # Task input (now optional for interactive mode)
    parser.add_argument("question", nargs='?', help="Question to solve (optional - if not provided, enters interactive mode)")
    
    # Configuration options (mutually exclusive)
    config_group = parser.add_mutually_exclusive_group(required=True)
    config_group.add_argument("--config", type=str,
                             help="Path to YAML configuration file")
    config_group.add_argument("--models", nargs="+",
                             help="Model names (e.g., gpt-4o gemini-2.5-flash)")
    
    # Configuration overrides
    parser.add_argument("--max-duration", type=int, default=None,
                       help="Max duration in seconds")
    parser.add_argument("--consensus", type=float, default=None,
                       help="Consensus threshold (0.0-1.0)")
    parser.add_argument("--max-debates", type=int, default=None,
                       help="Maximum debate rounds")
    parser.add_argument("--no-display", action="store_true",
                       help="Disable streaming display")
    parser.add_argument("--no-logs", action="store_true",
                       help="Disable file logging")
    
    # File context options
    parser.add_argument("--files", nargs="+", default=None,
                       help="Files to load as context (supports .py, .txt, .csv, .pdf, .md, .json)")
    parser.add_argument("--chunk-size", type=int, default=2000,
                       help="Maximum characters per file chunk (default: 2000)")
    
    args = parser.parse_args()
            
    # Load configuration
    try:
        if args.config:
            config = load_config_from_yaml(args.config)
        else:  # args.models
            config = create_config_from_models(args.models)
        
        # Handle file context configuration from CLI
        files_to_load = []
        if args.files:
            files_to_load.extend(args.files)
        
        if files_to_load:
            # Import FileContextConfig here to avoid circular imports
            from massgen.types import FileContextConfig
            
            file_context_config = FileContextConfig(
                files=files_to_load,
                chunk_size=args.chunk_size,
                default_role="user"
            )
            file_context_config.validate()
            
            # Apply file context to all agents
            for agent in config.agents:
                agent.model_config.file_context = file_context_config
        
        # Apply command-line overrides
        if args.max_duration is not None:
            config.orchestrator.max_duration = args.max_duration
        if args.consensus is not None:
            config.orchestrator.consensus_threshold = args.consensus
        if args.max_debates is not None:
            config.orchestrator.max_debate_rounds = args.max_debates
        if args.no_display:
            config.streaming_display.display_enabled = False
        if args.no_logs:
            config.streaming_display.save_logs = False
        
        # Validate final configuration
        config.validate()
        
        # The used models
        agents = {f"Agent {agent.agent_id}": agent.model_config.model for agent in config.agents}

        # Check if question was provided
        if args.question:
            # Single question mode
            result = run_mass_with_config(args.question, config)
            

            # Display results
            print("\n" + "="*60)
            print(f"🎯 FINAL ANSWER (Agent {result['representative_agent_id']}):")
            print("="*60)
            print(result["answer"])
            print("\n" + "="*60)
            
            # Show different metadata based on single vs multi-agent mode
            if result.get("single_agent_mode", False):
                print("🤖 Single Agent Mode")
                print(f"🤖 Agents: {agents}")
                print(f"⏱️  Duration: {result['session_duration']:.1f}s")
                if result.get("citations"):
                    print(f"📚 Citations: {len(result['citations'])}")
                if result.get("code"):
                    print(f"💻 Code blocks: {len(result['code'])}")
            else:
                print(f"🤖 Agents: {agents}")
                print(f"🎯 Representative Agent: {result['representative_agent_id']}")
                print(f"✅ Consensus: {result['consensus_reached']}")
                print(f"⏱️  Duration: {result['session_duration']:.1f}s")
                print(f"📊 Votes:")
                display_vote_distribution(result['summary']['final_vote_distribution'])
        else:
            # Interactive mode
            run_interactive_mode(config)
        
    except ConfigurationError as e:
        print(f"❌ Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 