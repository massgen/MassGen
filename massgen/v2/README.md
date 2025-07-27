# MassGen v0.0.2 New Architecture

This directory contains the next-generation MassGen architecture with modern async streaming, semantic agent IDs, and unified backend support.

## 🚀 Quick Start

```python
from massgen.v2 import create_simple_agent
import asyncio

async def main():
    # Create an agent with semantic ID
    agent = create_simple_agent(
        agent_id="helpful_assistant",
        model="gpt-4o-mini",
        system_message="You are a helpful AI assistant."
    )
    
    # Chat with streaming responses
    messages = [{"role": "user", "content": "Hello!"}]
    async for chunk in agent.chat(messages):
        if chunk.type == "content":
            print(chunk.content, end="")

asyncio.run(main())
```

## 🏗️ Architecture Components

### Core Interfaces
- **`ChatAgent`**: Abstract base class for all agents
- **`StreamChunk`**: Standardized streaming response format

### Backend System
- **`AgentBackend`**: Unified backend architecture
- **`TokenUsage`**: Token tracking and cost calculation
- **`OpenAIResponseBackend`**: OpenAI Response API implementation

### Agent Implementations
- **`SimpleAgent`**: Full-featured agent with LLM integration
- **Factory Functions**: `create_simple_agent()`, `create_agent_team()`

## 🆕 Key Features

### 1. Semantic String Agent IDs
```python
# ❌ Old: Numeric IDs
agent_1, agent_2 = create_agents(2)

# ✅ New: Semantic string IDs  
researcher = create_simple_agent(agent_id="research.specialist", ...)
writer = create_simple_agent(agent_id="content.writer", ...)
```

### 2. Unified Async Streaming
```python
async for chunk in agent.chat(messages):
    match chunk.type:
        case "content":
            print(chunk.content, end="")
        case "tool_calls":
            handle_tool_calls(chunk.content)
        case "done":
            print(f"✅ Complete from {chunk.source}")
```

### 3. Token Usage Tracking
```python
status = agent.get_status()
usage = status["token_usage"]
print(f"Tokens: {usage['total_tokens']}, Cost: ${usage['estimated_cost']:.4f}")
```

## 🔄 Migration from v0.0.1

v0.0.1 continues to work unchanged:
```python
from massgen import run_mass_agents  # Still works exactly the same
```

New v0.0.2 architecture:
```python
from massgen.v2 import create_simple_agent  # New architecture
```

## 📁 File Structure

```
massgen/v2/
├── __init__.py           # Public API exports
├── chat_agent.py         # ChatAgent interface + StreamChunk
├── agent_backend.py      # Backend architecture + implementations  
├── simple_agent.py       # SimpleAgent + factory functions
├── README.md            # This file
└── MIGRATION.md         # Migration strategy documentation
```

## 🎯 Development Status

- ✅ **Phase 1 Complete**: Core foundation (Issues #17-19)
- 🚧 **Phase 2 Next**: Orchestrator implementation (Issues #20-22)
- 📋 **Roadmap**: See GitHub issues #17-30 for full roadmap

## 🔧 Advanced Usage

### Custom Backend
```python
from massgen.v2 import AgentBackend, SimpleAgent

class CustomBackend(AgentBackend):
    # Implement your custom LLM backend
    pass

agent = SimpleAgent("custom_agent", CustomBackend())
```

### Team Collaboration
```python
from massgen.v2 import create_agent_team

team = create_agent_team([
    {"agent_id": "researcher", "model": "gpt-4o"},
    {"agent_id": "writer", "model": "gpt-4o-mini"},
    {"agent_id": "reviewer", "model": "gpt-4o"}
])

# Each agent can work independently with unified interface
for agent_id, agent in team.items():
    async for chunk in agent.chat(messages):
        print(f"[{agent_id}] {chunk.content}", end="")
```

This architecture provides the foundation for the next phases of MassGen development while maintaining complete compatibility with existing v0.0.1 code.