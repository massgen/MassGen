"""
Factory Functions Demo - Issue #21 Implementation

This example demonstrates the comprehensive factory functions and configuration
system for easy creation of agents and orchestrators.
"""

import asyncio
import json
from pathlib import Path

# Import the new factory functions and configuration
from massgen.v2 import (
    # Configuration management
    AgentConfig, ConfigManager, validate_agent_id,
    
    # Factory functions
    create_simple_agent, create_research_team, create_development_team,
    create_custom_team, get_available_teams,
    
    # Basic components
    StreamChunk
)


async def demo_simple_agent():
    """Demonstrate simple agent creation with configuration."""
    print("=== Simple Agent Demo ===")
    
    # Create agent with factory function
    agent = create_simple_agent(
        agent_id="demo.assistant",
        model="gpt-4o-mini",  # Using mini for demo
        system_message="You are a helpful demo assistant. Keep responses brief.",
        temperature=0.7,
        max_tokens=100
    )
    
    print(f"Created agent: {agent.agent_id}")
    print(f"Backend: {agent.backend.get_provider_name()}")
    
    # Test basic chat (mock response since we don't have real API key)
    messages = [{"role": "user", "content": "Hello! Tell me about yourself briefly."}]
    
    try:
        response_text = ""
        async for chunk in agent.chat(messages):
            if chunk.type == "content":
                response_text += chunk.content
            elif chunk.type == "done":
                break
            elif chunk.type == "error":
                print(f"Error: {chunk.error}")
                break
        
        if response_text:
            print(f"Response: {response_text}")
    except Exception as e:
        print(f"Chat simulation failed (expected without real API key): {type(e).__name__}")
    
    # Show agent status
    status = agent.get_status()
    print(f"Agent status: {status['status']}")
    print(f"Total tokens used: {status['total_tokens']}")
    print()


def demo_agent_config():
    """Demonstrate AgentConfig features."""
    print("=== Agent Configuration Demo ===")
    
    # Create configuration with validation
    config = AgentConfig(
        agent_id="org.team.specialist",
        model="gpt-4o",
        system_message="You are a specialist in your field.",
        tags=["specialist", "expert"],
        temperature=0.8,
        max_tokens=1500
    )
    
    print(f"Agent ID: {config.agent_id}")
    print(f"Hierarchy level: {config.get_hierarchy_level()}")
    print(f"Parent ID: {config.get_parent_id()}")
    print(f"Root ID: {config.get_root_id()}")
    print(f"Is child of 'org.team': {config.is_child_of('org.team')}")
    
    # Demonstrate validation
    valid_ids = ["agent1", "team.researcher", "org.department.team.role"]
    invalid_ids = ["", "123agent", "agent..double", "a" * 51]
    
    print("\nID Validation Examples:")
    for agent_id in valid_ids:
        print(f"  '{agent_id}': {'✓' if validate_agent_id(agent_id) else '✗'}")
    
    for agent_id in invalid_ids:
        print(f"  '{agent_id}': {'✓' if validate_agent_id(agent_id) else '✗'}")
    
    # Save and load configuration
    config_dict = config.to_dict()
    loaded_config = AgentConfig.from_dict(config_dict)
    print(f"\nRound-trip conversion successful: {loaded_config.agent_id == config.agent_id}")
    print()


def demo_team_factories():
    """Demonstrate pre-configured team factories."""
    print("=== Team Factory Demo ===")
    
    # Show available team types
    teams = get_available_teams()
    print(f"Available team types: {teams}")
    
    # Create a research team
    research_team = create_research_team(
        team_id="demo_research",
        model="gpt-4o-mini",
        session_id="demo_session"
    )
    
    print(f"\nCreated research team: {research_team.orchestrator_id}")
    print(f"Team members ({len(research_team.agents)}):")
    for agent_id in research_team.agents:
        print(f"  - {agent_id}")
    
    # Create a development team
    dev_team = create_development_team(
        team_id="demo_dev",
        model="gpt-4o-mini"
    )
    
    print(f"\nCreated development team: {dev_team.orchestrator_id}")
    print(f"Team members ({len(dev_team.agents)}):")
    for agent_id in dev_team.agents:
        print(f"  - {agent_id}")
    print()


def demo_custom_team():
    """Demonstrate custom team creation from configuration."""
    print("=== Custom Team Demo ===")
    
    # Define custom team configuration
    custom_config = {
        "team_id": "demo_consulting",
        "agents": [
            {
                "agent_id": "demo_consulting.strategy_consultant",
                "model": "gpt-4o-mini",
                "system_message": "You are a strategy consultant focused on business transformation.",
                "tags": ["strategy", "consulting", "business"]
            },
            {
                "agent_id": "demo_consulting.technical_consultant", 
                "model": "gpt-4o-mini",
                "system_message": "You are a technical consultant specializing in technology solutions.",
                "tags": ["technical", "consulting", "technology"]
            },
            {
                "agent_id": "demo_consulting.project_manager",
                "model": "gpt-4o-mini", 
                "system_message": "You are a project manager ensuring successful delivery.",
                "tags": ["pm", "delivery", "coordination"]
            }
        ],
        "orchestrator": {
            "max_duration": 900,
            "voting_config": {
                "include_vote_reasons": True,
                "voting_strategy": "simple_majority",
                "tie_breaking": "longest_answer"
            }
        }
    }
    
    # Create custom team
    consulting_team = create_custom_team(custom_config, session_id="consulting_demo")
    
    print(f"Created custom consulting team: {consulting_team.orchestrator_id}")
    print(f"Team members ({len(consulting_team.agents)}):")
    for agent_id in consulting_team.agents:
        print(f"  - {agent_id}")
    
    # Show orchestrator configuration
    print(f"Max duration: {consulting_team.max_duration}s")
    print(f"Voting config: {consulting_team.voting_config}")
    print()


def demo_config_templates():
    """Demonstrate configuration template usage."""
    print("=== Configuration Templates Demo ===")
    
    # Check if templates exist
    template_dir = Path(__file__).parent.parent / "massgen" / "v2" / "config_templates"
    
    if template_dir.exists():
        templates = list(template_dir.glob("*.yaml")) + list(template_dir.glob("*.json"))
        print(f"Available templates ({len(templates)}):")
        for template in templates:
            print(f"  - {template.name}")
        
        # Try to load a template
        research_template = template_dir / "research_team.yaml"
        if research_template.exists():
            try:
                team_config = ConfigManager.load_from_file(research_template)
                print(f"\nLoaded research team template:")
                print(f"  Team ID: {team_config.get('team_id', 'N/A')}")
                print(f"  Agents: {len(team_config.get('agents', []))}")
                print(f"  Max duration: {team_config.get('orchestrator', {}).get('max_duration', 'N/A')}s")
            except Exception as e:
                print(f"Template loading failed: {e}")
    else:
        print("Template directory not found")
    print()


def demo_configuration_files():
    """Demonstrate configuration file operations."""
    print("=== Configuration File Demo ===")
    
    # Create sample configuration
    config = AgentConfig(
        agent_id="file_demo.agent",
        model="gpt-4o-mini",
        system_message="Demo agent for file operations",
        tags=["demo", "file-ops"],
        temperature=0.5
    )
    
    # Save to JSON
    json_path = "demo_config.json"
    try:
        ConfigManager.save_agent_config(config, json_path)
        print(f"✓ Saved configuration to {json_path}")
        
        # Load from JSON
        loaded_config = ConfigManager.load_agent_config(json_path)
        print(f"✓ Loaded configuration: {loaded_config.agent_id}")
        
        # Cleanup
        Path(json_path).unlink()
        print(f"✓ Cleaned up {json_path}")
        
    except Exception as e:
        print(f"File operations failed: {e}")
    
    print()


async def main():
    """Run all demonstrations."""
    print("🚀 MassGen v0.0.2 Factory Functions Demo")
    print("=" * 50)
    
    await demo_simple_agent()
    demo_agent_config()
    demo_team_factories() 
    demo_custom_team()
    demo_config_templates()
    demo_configuration_files()
    
    print("✅ All demonstrations completed!")
    print("\nNext steps:")
    print("1. Set up API keys in environment variables")
    print("2. Try the configuration templates in config_templates/")
    print("3. Create your own custom team configurations")
    print("4. Run integration tests with: pytest test_factory_integration.py")


if __name__ == "__main__":
    asyncio.run(main())