"""
MassGen v0.0.2 New Architecture

__version__ = "0.0.2"

Modern async ChatAgent-based architecture with streaming support,
semantic agent IDs, and unified backend system.

Core Components:
- ChatAgent: Abstract base class for all agent interactions
- StreamChunk: Standardized streaming response format  
- AgentBackend: Unified backend architecture with token tracking
- SimpleAgent: Full-featured agent implementation
- Factory functions for easy agent creation

Usage Examples:

Basic Agent Creation:
    from massgen.v2 import create_simple_agent
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

Team Creation:
    from massgen.v2 import create_agent_team
    
    team_configs = [
        {"agent_id": "researcher", "model": "gpt-4o", "system_message": "Research specialist"},
        {"agent_id": "writer", "model": "gpt-4o-mini", "system_message": "Technical writer"}
    ]
    team = create_agent_team(team_configs)

Direct Imports:
    from massgen.v2 import ChatAgent, StreamChunk, AgentBackend, SimpleAgent
    # Use the classes directly for advanced customization
"""

# Core interfaces
from .chat_agent import ChatAgent, StreamChunk

# Backend architecture  
from .backend import (
    AgentBackend, 
    TokenUsage, 
    OpenAIResponseBackend,
    OpenAIChatCompletionsBackend,
    create_backend,
    get_provider_from_model
)

# Agent implementations
from .simple_agent import (
    SimpleAgent,
    create_simple_agent, 
    create_agent_team
)

# Orchestrator implementation
from .orchestrator import (
    Orchestrator,
    AgentState,
    VoteRecord,
    create_orchestrator
)

# Configuration management
from .agent_config import (
    AgentConfig,
    OrchestratorConfig,
    ConfigManager,
    validate_agent_id,
    validate_config_file
)

# Team factories
from .team_factories import (
    create_research_team,
    create_development_team,
    create_analysis_team,
    create_creative_team,
    create_custom_team,
    get_available_teams,
    create_team,
    TEAM_FACTORIES
)

# Message templates
from .message_templates import MessageTemplates

# Frontend
from .frontend import (
    StreamingFrontend,
    SimpleStreamingDisplay,
    ColoredStreamingDisplay,
    stream_coordination
)

__version__ = "0.0.2"

__all__ = [
    # Core interfaces
    "ChatAgent",
    "StreamChunk",
    
    # Backend architecture
    "AgentBackend",
    "TokenUsage", 
    "OpenAIResponseBackend",
    "OpenAIChatCompletionsBackend", 
    "create_backend",
    "get_provider_from_model",
    
    # Agent implementations
    "SimpleAgent",
    "create_simple_agent",
    "create_agent_team",
    
    # Orchestrator implementation
    "Orchestrator",
    "AgentState",
    "VoteRecord", 
    "create_orchestrator",
    
    # Configuration management
    "AgentConfig",
    "OrchestratorConfig",
    "ConfigManager",
    "validate_agent_id",
    "validate_config_file",
    
    # Team factories
    "create_research_team",
    "create_development_team", 
    "create_analysis_team",
    "create_creative_team",
    "create_custom_team",
    "get_available_teams",
    "create_team",
    "TEAM_FACTORIES",
    
    # Message templates
    "MessageTemplates",
    
    # Frontend
    "StreamingFrontend",
    "SimpleStreamingDisplay",
    "ColoredStreamingDisplay", 
    "stream_coordination",
]