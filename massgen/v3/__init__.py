"""
MassGen v3 - Multi-Agent System Generator (Foundation Release)

Built on the proven MassGen framework with working tool message handling,
async generator patterns, and reliable multi-agent coordination.

Key Features:
- Working OpenAI Response API integration with proper tool message conversion
- Async streaming with proper chat agent interfaces
- Multi-agent orchestration with voting and consensus
- Real-time frontend displays with multi-region terminal UI

TODO - Missing Features (to be added in future releases):
- Grok backend testing and fixes
- Gemini backend support  
- Configuration options for voting info in user messages
- Enhanced frontend features from v0.0.1
- Advanced logging and monitoring capabilities
- Tool execution with custom functions
- Web search and code interpreter integration
- Performance optimizations

Usage:
    from massgen.v3 import OpenAIBackend, create_simple_agent, MassOrchestrator
    
    backend = OpenAIBackend()
    agent = create_simple_agent(backend, "You are a helpful assistant")
    orchestrator = MassOrchestrator(agents={"agent1": agent})
    
    async for chunk in orchestrator.chat_simple("Your question"):
        if chunk.type == "content":
            print(chunk.content, end="")
"""

# Import main classes for convenience
from .backend.openai_backend import OpenAIBackend
from .chat_agent import (
    ChatAgent, 
    SingleAgent, 
    ConfigurableAgent,
    create_simple_agent,
    create_expert_agent, 
    create_research_agent,
    create_computational_agent
)
from .orchestrator import MassOrchestrator, create_orchestrator
from .message_templates import MessageTemplates, get_templates
from .agent_config import AgentConfig

__version__ = "0.0.3"
__author__ = "MassGen Contributors"

__all__ = [
    # Backends
    "OpenAIBackend",
    
    # Agents
    "ChatAgent",
    "SingleAgent", 
    "ConfigurableAgent",
    "create_simple_agent",
    "create_expert_agent",
    "create_research_agent", 
    "create_computational_agent",
    
    # Orchestrator
    "MassOrchestrator",
    "create_orchestrator",
    
    # Configuration
    "AgentConfig",
    "MessageTemplates",
    "get_templates",
    
    # Metadata
    "__version__",
    "__author__"
]