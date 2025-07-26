"""
MassGen - Multi-Agent Scaling System

A powerful multi-agent collaboration framework that enables multiple AI agents
to work together on complex tasks, share insights, vote on solutions, and reach
consensus through structured collaboration and debate.

The system also supports single-agent mode for simpler tasks that don't require
multi-agent collaboration.

Key Features:
- Single-agent mode for simple, direct processing
- Multi-agent collaboration with dynamic restart logic
- Comprehensive YAML configuration system
- Real-time streaming display with multi-region layout
- Robust consensus mechanisms with debate phases
- Support for multiple LLM backends (OpenAI, Gemini, Grok)
- Comprehensive logging and monitoring

Command-Line Usage:
    # Use cli.py for all command-line operations
    
    # Single agent mode
    python cli.py "What is 2+2?" --models gpt-4o
    
    # Multi-agent mode
    python cli.py "What is 2+2?" --models gpt-4o gemini-2.5-flash
    python cli.py "Complex question" --config examples/production.yaml

Programmatic Usage (v0.0.1 Legacy):
    # Using YAML configuration
    from massgen import run_mass_with_config, load_config_from_yaml
    config = load_config_from_yaml("config.yaml")
    result = run_mass_with_config("Your question here", config)
    
    # Using simple model list (single agent)
    from massgen import run_mass_agents
    result = run_mass_agents("What is 2+2?", ["gpt-4o"])
    
    # Using simple model list (multi-agent)
    from massgen import run_mass_agents
    result = run_mass_agents("What is 2+2?", ["gpt-4o", "gemini-2.5-flash"])

New Architecture Usage (v0.0.2):
    # Create a simple agent
    from massgen import create_simple_agent
    import asyncio
    
    agent = create_simple_agent(
        agent_id="helpful_assistant",
        model="gpt-4o-mini",
        system_message="You are a helpful AI assistant."
    )
    
    # Chat with streaming responses
    async def chat_example():
        messages = [{"role": "user", "content": "Hello!"}]
        async for chunk in agent.chat(messages):
            if chunk.type == "content":
                print(chunk.content, end="")
    
    asyncio.run(chat_example())
    
    # Create a team of agents
    from massgen import create_agent_team
    
    team_configs = [
        {"agent_id": "researcher", "model": "gpt-4o", "system_message": "Research specialist"},
        {"agent_id": "writer", "model": "gpt-4o-mini", "system_message": "Technical writer"}
    ]
    team = create_agent_team(team_configs)
"""

# Core system components
from .main import (
    MassSystem, 
    run_mass_agents, 
    run_mass_with_config
)

# Configuration system
from .config import (
    load_config_from_yaml,
    create_config_from_models,
    ConfigurationError
)

# Configuration classes
from .types import (
    MassConfig,
    OrchestratorConfig, 
    AgentConfig,
    ModelConfig,
    StreamingDisplayConfig,
    LoggingConfig,
    TaskInput
)

# Advanced components (for custom usage)
from .orchestrator import MassOrchestrator
from .streaming_display import create_streaming_display
from .logging import MassLogManager

# v0.0.2 New Architecture Components
from .chat_agent import ChatAgent, StreamChunk
from .agent_backend import AgentBackend, TokenUsage, OpenAIResponseBackend, create_backend
from .simple_agent import SimpleAgent, create_simple_agent, create_agent_team

__version__ = "0.0.2"

__all__ = [
    # Main interfaces
    "MassSystem",
    "run_mass_agents", 
    "run_mass_with_config",
    
    # Configuration system
    "load_config_from_yaml",
    "create_config_from_models",
    "ConfigurationError",
    
    # Configuration classes
    "MassConfig",
    "OrchestratorConfig",
    "AgentConfig", 
    "ModelConfig",
    "StreamingDisplayConfig",
    "LoggingConfig",
    "TaskInput",
    
    # Advanced components
    "MassOrchestrator",
    "create_streaming_display",
    "MassLogManager",
    
    # v0.0.2 New Architecture
    "ChatAgent",
    "StreamChunk", 
    "AgentBackend",
    "TokenUsage",
    "OpenAIResponseBackend",
    "create_backend",
    "SimpleAgent",
    "create_simple_agent",
    "create_agent_team",
] 