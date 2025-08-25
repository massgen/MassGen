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

# Import main classes for convenience
from .backend.response import ResponseBackend
from .backend.claude import ClaudeBackend
from .backend.gemini import GeminiBackend
from .backend.grok import GrokBackend
from .backend.lmstudio import LMStudioBackend
from .chat_agent import (
    ChatAgent,
    SingleAgent,
    ConfigurableAgent,
    create_simple_agent,
    create_expert_agent,
    create_research_agent,
    create_computational_agent,
)
from .orchestrator import Orchestrator, create_orchestrator
from .message_templates import MessageTemplates, get_templates
from .agent_config import AgentConfig

__version__ = "0.0.11"
__author__ = "MassGen Contributors"

__all__ = [
    # Backends
    "ResponseBackend",
    "ClaudeBackend",
    "GeminiBackend",
    "GrokBackend",
    "LMStudioBackend",
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
