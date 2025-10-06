# Multi-Source Agent Integration Design for MassGen

## Overview

This document outlines the design for extending MassGen to support agents from multiple sources and frameworks, inspired by Claude's subagent system. The goal is to enable MassGen to orchestrate not only native agents but also agents built on various frameworks (LangChain, AutoGen, AG2, LangGraph, OpenAI Assistants, SmolAgent) and agents running locally or in the cloud.

## Design Principles

### 1. Framework Agnostic Integration
- Support agents from any framework through a unified adapter interface
- Preserve framework-specific capabilities while maintaining MassGen coordination
- Enable parallel execution across heterogeneous agent types

### 2. Minimal Overhead
- Lightweight adapters that don't duplicate framework functionality
- Direct communication with framework agents when possible
- Preserve streaming and async capabilities

### 3. Orchestrator Compatibility
- Framework agents participate in MassGen's voting and new_answer workflow
- Leverage existing ConfigurableAgent for orchestrator integration
- Maintain binary decision framework for coordination

### 4. Multi-Agent Group Integration
- **Existing framework multi-agent groups (e.g., AG2 GroupChat) act as single agents in MassGen**
- Non-parallel multi-agent conversations from frameworks are treated as one voting unit
- MassGen orchestrates at the framework level, not individual agents within frameworks

## Architecture

### Integration Layers

```
┌─────────────────────────────────────────────┐
│          MassGen Orchestrator               │
├─────────────────────────────────────────────┤
│         ConfigurableAgent Layer             │
├─────────────────────────────────────────────┤
│      ExternalAgentBackend (New)            │ (extends LLMBackend)
├─────────────────────────────────────────────┤
│        Agent Adapters (New)             │
├─────────┬───────────┬───────────┬───────────┤
│   AG2   │ LangChain │ Black Box │  Remote   │
└─────────┴───────────┴───────────┴───────────┘
```

### Core Backend Implementation

```python
class ExternalAgentBackend(LLMBackend):
    """
    Universal backend for external agents.
    Extends LLMBackend to integrate with MassGen's existing infrastructure.
    """

    def __init__(self, framework: str, **kwargs):
        super().__init__(**kwargs)
        self.framework = framework.lower()
        self.adapter = self._create_adapter(kwargs)

    def _create_adapter(self, config: Dict[str, Any]) -> AgentAdapter:
        """Factory method to create agent-specific adapters."""
        from ..adapters import adapter_registry

        adapter_class = adapter_registry.get(self.framework)
        if not adapter_class:
            raise ValueError(f"Unsupported framework: {self.framework}")

        return adapter_class(config)

    async def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Stream responses from framework agents.
        """
        # Convert messages to framework format
        framework_messages = self.adapter.convert_messages_to_framework(messages)
        framework_tools = self.adapter.convert_tools_to_framework(tools)

        # Execute through adapter
        async for chunk in self.adapter.execute_streaming(
            framework_messages,
            framework_tools,
            **kwargs
        ):
            yield chunk

    def get_provider_name(self) -> str:
        return f"Framework:{self.framework}"
```

### Framework Adapter Base Class

```python
from abc import ABC, abstractmethod

class AgentAdapter(ABC):
    """
    Base adapter for integrating external agents.
    Each agent type implements this interface.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._setup_adapter()

    @abstractmethod
    def _setup_adapter(self) -> None:
        """Initialize framework-specific components."""
        pass

    @abstractmethod
    def convert_messages_to_framework(self, messages: List[Dict[str, Any]]) -> Any:
        """Convert MassGen messages to framework format."""
        pass

    @abstractmethod
    def convert_tools_to_framework(self, tools: List[Dict[str, Any]]) -> Any:
        """Convert MassGen tools to framework format."""
        pass

    @abstractmethod
    async def execute_streaming(
        self,
        messages: Any,
        tools: Any,
        **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Execute agent and yield streaming chunks.
        """
        pass
```

### Agent-Specific Adapters

#### LangChain Adapter
```python
class LangChainAdapter(AgentAdapter):
    """Adapter for LangChain agents and chains."""

    def _setup_adapter(self) -> None:
        """Initialize LangChain components."""
        from langchain.agents import initialize_agent
        # Setup based on config
        self.chain_type = self.config.get("chain_type", "agent")
        self._initialize_agent()
```

#### AutoGen/AG2 Adapter
```python
class AG2Adapter(AgentAdapter):
    """Adapter for AG2/AutoGen agents including pattern-based group chat support."""

    def _setup_adapter(self) -> None:
        """Initialize AG2 agent or pattern-based group chat."""
        import autogen

        self.agent_type = self.config.get("agent_type", "AssistantAgent")
        self.agent_config = self.config.get("agent_config", {})
        self.group_config = self.config.get("group_config", None)

        if self.group_config:
            # Use patterns instead of naive GroupChat
            # Supports: AutoPattern, RoundRobinPattern, RandomPattern, DefaultPattern
            self._setup_group_chat()
        else:
            self._setup_single_agent()
```

#### OpenAI Assistants Adapter
```python
class OpenAIAssistantAdapter(AgentAdapter):
    """Adapter for OpenAI Assistants API."""

    def _setup_adapter(self) -> None:
        self.assistant_id = self.config.get("assistant_id")
        self.client = self._get_openai_client()
        self.thread = self.client.beta.threads.create()
```

#### SmolAgent Adapter
```python
class SmolAgentAdapter(AgentAdapter):
    """Adapter for SmolAgent framework."""

    def _setup_adapter(self) -> None:
        from smolagents import Agent
        self.model_id = self.config.get("model_id")
        self.tools = self._setup_tools()

### Remote Agent Integration

For agents running remotely (cloud services, microservices):

```python
class RemoteAgentAdapter(AgentAdapter):
    """Adapter for remote agents via HTTP/WebSocket/gRPC."""

    def _setup_adapter(self) -> None:
        self.connection_type = self.config.get("connection", {}).get("type", "http")
        self.url = self.config.get("connection", {}).get("url")

        if self.connection_type == "http":
            self._setup_http_client()
        elif self.connection_type == "websocket":
            self._setup_websocket_client()
```

### Black Box Agent Support

MassGen supports integrating any pre-existing agent as a "black box" without requiring knowledge of its internal implementation:

```python
class BlackBoxAdapter(AgentAdapter):
    """
    Universal adapter for black box agents.
    Supports multiple communication methods.
    """

    def _setup_adapter(self) -> None:
        self.communication_method = self.config.get("communication_method")

        if self.communication_method == "http":
            self.communicator = HTTPCommunicator(self.config)
        elif self.communication_method == "process":
            self.communicator = ProcessCommunicator(self.config)
        elif self.communication_method == "file":
            self.communicator = FileCommunicator(self.config)
```

## Orchestrator Integration

### Making Framework Agents MassGen-Compatible

Framework agents are integrated through the ExternalAgentBackend and wrapped with ConfigurableAgent:

```python
# Example: Integrating an AG2 agent into MassGen orchestration
from massgen.backend.framework import ExternalAgentBackend
from massgen.chat_agent import ConfigurableAgent
from massgen.agent_config import AgentConfig

# Create framework backend
ag2_backend = ExternalAgentBackend(
    framework="ag2",
    agent_type="AssistantAgent",
    agent_config={
        "name": "research_expert",
        "llm_config": {"model": "gpt-4"},
        "system_message": "You are a research specialist."
    }
)

# Wrap with ConfigurableAgent for orchestration
ag2_agent = ConfigurableAgent(
    backend=ag2_backend,
    config=AgentConfig()  # Provides vote/new_answer tools
)
```

This allows framework agents to:
1. Receive evaluation contexts with other agents' answers
2. Vote on best approaches (Case 2)
3. Provide new answers when needed (Case 1)
4. Participate in the binary decision framework

### Parallel Execution

The orchestrator handles framework agents identically to native agents:

```python
from massgen.orchestrator import Orchestrator

orchestrator = Orchestrator(
    agents={
        "native_agent": native_massgen_agent,
        "ag2_agent": ag2_agent,  # Using ExternalAgentBackend
        "langchain_agent": langchain_agent,
        "blackbox_agent": blackbox_agent
    }
)
```

All agents execute in parallel during coordination rounds, regardless of their implementation framework.

## Key Integration Concepts

### Framework Multi-Agent Groups as Single MassGen Agents

When frameworks like AG2 have their own multi-agent groups (e.g., GroupChat), these entire groups participate as **single agents** in MassGen's orchestration:

```python
# AG2 GroupChat with 3 agents internally
ag2_research_team = ExternalAgentBackend(
    framework="ag2",
    group_config={
        "agents": [
            {"type": "AssistantAgent", "config": {"name": "researcher"}},
            {"type": "AssistantAgent", "config": {"name": "analyst"}},
            {"type": "AssistantAgent", "config": {"name": "writer"}}
        ]
    }
)

# In MassGen orchestration, the entire GroupChat votes as one unit
orchestrator = Orchestrator(agents={
    "research_team": ag2_research_team,  # One voting entity
    "native_coder": massgen_native_agent,
    "reviewer": another_agent
})
```

## Configuration System

### YAML Configuration Schema

```yaml
agents:
  - id: "agent_id"
    backend:
      type: "ag2"  # Direct backend type (ag2, langchain, remote, blackbox, etc.)

      # Framework-specific configuration
      agent_type: "AssistantAgent"
      agent_config:
        name: "expert"
        llm_config:
          model: "gpt-4"

      # Optional: GroupChat configuration for AG2
      group_config:
        agents: [...]
        chat_config: {...}
```

## Configuration Examples

### Single AG2 Agent

```yaml
# ag2_single.yaml
agents:
  - id: "python_expert"
    backend:
      type: "ag2"
      agent_type: "AssistantAgent"
      agent_config:
        name: "python_expert"
        system_message: |
          You are a Python programming expert.
          Help users write clean, efficient Python code.
        llm_config:
          model: "gpt-4"
          temperature: 0.7
          max_tokens: 2000
        code_execution_config:
          work_dir: "./code_workspace"
          use_docker: false
```

### AG2 GroupChat Configuration

```yaml
# ag2_groupchat.yaml
agents:
  - id: "ag2_research_team"
    backend:
      type: "ag2"

      # GroupChat configuration - entire group acts as one MassGen agent
      group_config:
        # Define agents in the group
        agents:
          - type: "AssistantAgent"
            config:
              name: "researcher"
              system_message: |
                You are a research specialist.
                Find and analyze information from various sources.
              llm_config:
                model: "gpt-4"
                temperature: 0.7

          - type: "AssistantAgent"
            config:
              name: "analyst"
              system_message: |
                You are a data analyst.
                Analyze research findings and identify patterns.
              llm_config:
                model: "gpt-4"
                temperature: 0.5

          - type: "AssistantAgent"
            config:
              name: "writer"
              system_message: |
                You are a technical writer.
                Synthesize findings into clear, concise reports.
              llm_config:
                model: "gpt-4"
                temperature: 0.8

        # GroupChat settings
        chat_config:
          max_round: 10
          speaker_selection_method: "auto"
          allow_repeat_speaker: false

        # GroupChatManager settings
        manager_config:
          name: "research_team_manager"
          system_message: "Coordinate the research team effectively."
          llm_config:
            model: "gpt-4"
            temperature: 0.5
```

### Mixed Framework Team

```yaml
# mixed_team.yaml
agents:
  # AG2 GroupChat for research (one voting unit)
  - id: "research_group"
    backend:
      type: "ag2"
      group_config:
        agents:
          - type: "AssistantAgent"
            config:
              name: "web_researcher"
              system_message: "Search and gather information."
          - type: "AssistantAgent"
            config:
              name: "fact_checker"
              system_message: "Verify facts and sources."
        chat_config:
          max_round: 5

  # Native MassGen agent
  - id: "coder"
    backend:
      type: "openai"
      model: "gpt-4"
    system_message: "Write code based on research findings."

  # LangChain agent
  - id: "documenter"
    backend:
      type: "langchain"
      chain_type: "agent"
      agent_config:
        agent_type: "openai-functions"
        model_name: "gpt-4"
      tools: ["serpapi", "wikipedia"]

orchestrator:
  timeout_seconds: 1800
```

### Remote/Cloud Agent

```yaml
# remote_agent.yaml
agents:
  - id: "cloud_expert"
    backend:
      type: "remote"
      endpoint_url: "https://api.example.com/agent"
      auth_config:
        api_key: "${REMOTE_API_KEY}"
      protocol: "http"
      timeout: 300
```

### Black Box Subprocess Agent

```yaml
# subprocess_agent.yaml
agents:
  - id: "local_python_agent"
    backend:
      type: "blackbox"
      communication_method: "pipe"
      command: ["python", "my_agent.py"]
      working_dir: "./agents"
      env:
        AGENT_MODE: "production"
```

### CLI Backend Factory Updates

The CLI's `create_backend` function will be updated to use the adapter registry for framework detection:

```python
# In massgen/cli.py - modification to existing create_backend function
def create_backend(backend_type: str, **kwargs) -> Any:
    """Create backend instance from type and parameters."""
    backend_type = backend_type.lower()

    # Check if this is a framework/adapter type
    from massgen.adapters import adapter_registry

    if backend_type in adapter_registry:
        # Use ExternalAgentBackend for all registered adapter types
        from massgen.backend.framework import ExternalAgentBackend
        return ExternalAgentBackend(framework=backend_type, **kwargs)

    # Existing backend types (openai, claude, gemini, etc.)
    elif backend_type == "openai":
        # ... existing code ...
    # ... other existing backends ...
```

This approach provides several benefits:

1. **Single Source of Truth**: The adapter registry defines all supported framework types
2. **Cleaner Configuration**: Users specify `type: "ag2"` directly without nested framework config
3. **Easy Extension**: New frameworks are added to the registry, automatically available in CLI
4. **Type Safety**: Registry ensures only valid framework types are used

## Detailed Implementation

### Core Backend Implementation

```python
# massgen/backend/framework.py
from typing import Dict, List, Any, AsyncGenerator, Optional
from .base import LLMBackend, StreamChunk, FilesystemSupport

class ExternalAgentBackend(LLMBackend):
    """
    Universal backend for external agents.
    Delegates execution to agent-specific adapters.
    """

    EXCLUDED_API_PARAMS = LLMBackend.get_base_excluded_config_params().union({
        "framework",
        "agent_type",
        "agent_config",
        "group_config",
        "connection",
    })

    def __init__(self, framework: str, **kwargs):
        super().__init__(**kwargs)
        self.framework = framework.lower()
        self.adapter = self._create_adapter(kwargs)

    def _create_adapter(self, config: Dict[str, Any]) -> 'AgentAdapter':
        """Factory method to create agent-specific adapters."""
        from ..adapters import adapter_registry

        adapter_class = adapter_registry.get(self.framework)
        if not adapter_class:
            raise ValueError(f"Unsupported framework: {self.framework}")

        return adapter_class(config)

    async def stream_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Stream responses from framework agents.
        Handles message/tool conversion and streaming simulation.
        """
        # Convert messages to framework format
        framework_messages = self.adapter.convert_messages_to_framework(messages)
        framework_tools = self.adapter.convert_tools_to_framework(tools)

        # Execute through adapter
        async for chunk in self.adapter.execute_streaming(
            framework_messages,
            framework_tools,
            **kwargs
        ):
            yield chunk

    def get_provider_name(self) -> str:
        return f"Framework:{self.framework}"

    def get_filesystem_support(self) -> FilesystemSupport:
        """Framework agents may have their own filesystem access."""
        return self.adapter.get_filesystem_support()

    def estimate_tokens(self, text: str) -> int:
        """Estimate tokens using framework's method if available."""
        # Default implementation - can be overridden by adapter
        return len(text) // 4

    def calculate_cost(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """Calculate cost based on framework's pricing."""
        # Default free for local frameworks - adapters can override
        return 0.0
```

### Base Framework Adapter

```python
# massgen/adapters/base.py
from abc import ABC, abstractmethod
from typing import Any, Dict, List, AsyncGenerator, Optional
from ..backend.base import StreamChunk, FilesystemSupport

class AgentAdapter(ABC):
    """
    Base adapter for integrating external agents.
    Each agent type implements this interface.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self._setup_adapter()

    @abstractmethod
    def _setup_adapter(self) -> None:
        """Initialize framework-specific components."""
        pass

    @abstractmethod
    def convert_messages_to_framework(
        self,
        messages: List[Dict[str, Any]]
    ) -> Any:
        """Convert MassGen messages to framework format."""
        pass

    @abstractmethod
    def convert_tools_to_framework(
        self,
        tools: List[Dict[str, Any]]
    ) -> Any:
        """Convert MassGen tools to framework format."""
        pass

    @abstractmethod
    async def execute_streaming(
        self,
        messages: Any,
        tools: Any,
        **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Execute agent and yield streaming chunks.
        Must simulate streaming for non-streaming frameworks.
        """
        pass

    def get_filesystem_support(self) -> FilesystemSupport:
        """Default: no filesystem support."""
        return FilesystemSupport.NONE

    # Utility methods for streaming simulation
    async def simulate_streaming(
        self,
        content: str,
        chunk_size: int = 50
    ) -> AsyncGenerator[StreamChunk, None]:
        """Helper to simulate streaming for non-streaming responses."""
        import asyncio
        for i in range(0, len(content), chunk_size):
            chunk = content[i:i + chunk_size]
            yield StreamChunk(
                type="content",
                content=chunk
            )
            await asyncio.sleep(0.01)  # Small delay for realistic streaming

        # Send final complete message
        yield StreamChunk(
            type="complete_message",
            complete_message={
                "role": "assistant",
                "content": content
            }
        )
```

### AG2 (AutoGen) Adapter Implementation

```python
# massgen/adapters/ag2_adapter.py
from typing import List, Dict, Any, Optional, AsyncGenerator
import asyncio
from ..backend.base import StreamChunk
from .base import AgentAdapter

class AG2Adapter(AgentAdapter):
    """
    Adapter for AG2/AutoGen agents including GroupChat support.
    """

    def _setup_adapter(self) -> None:
        """Initialize AG2 agent or group chat."""
        self.agent_type = self.config.get("agent_type", "AssistantAgent")
        self.agent_config = self.config.get("agent_config", {})
        self.group_config = self.config.get("group_config", None)

        if self.group_config:
            # Create GroupChat with multiple agents
            self._setup_group_chat()
        else:
            # Create single AG2 agent
            self._setup_single_agent()

    def _setup_single_agent(self):
        """Create a single AG2 agent."""
        if self.agent_type == "AssistantAgent":
            from autogen import AssistantAgent
            self.agent = AssistantAgent(**self.agent_config)
        elif self.agent_type == "UserProxyAgent":
            from autogen import UserProxyAgent
            self.agent = UserProxyAgent(**self.agent_config)
        else:
            raise ValueError(f"Unsupported AG2 agent type: {self.agent_type}")

    def _setup_group_chat(self):
        """Create AG2 GroupChat with multiple agents."""
        from autogen import GroupChat, GroupChatManager

        # Create agents for the group
        agents = []
        for agent_def in self.group_config.get("agents", []):
            agent_type = agent_def.get("type", "AssistantAgent")
            agent_config = agent_def.get("config", {})

            if agent_type == "AssistantAgent":
                from autogen import AssistantAgent
                agent = AssistantAgent(**agent_config)
            elif agent_type == "UserProxyAgent":
                from autogen import UserProxyAgent
                agent = UserProxyAgent(**agent_config)
            else:
                continue

            agents.append(agent)

        # Create GroupChat
        group_chat_config = self.group_config.get("chat_config", {})
        self.group_chat = GroupChat(
            agents=agents,
            messages=[],
            **group_chat_config
        )

        # Create GroupChatManager
        manager_config = self.group_config.get("manager_config", {})
        self.agent = GroupChatManager(
            groupchat=self.group_chat,
            **manager_config
        )

    def convert_messages_to_framework(
        self,
        messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Convert MassGen messages to AG2 format."""
        ag2_messages = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if role == "system":
                # AG2 uses system_message in agent config, not in messages
                continue
            elif role == "user":
                ag2_messages.append({"role": "user", "content": content})
            elif role == "assistant":
                ag2_messages.append({"role": "assistant", "content": content})
            elif role == "tool":
                # Convert tool result to AG2 format
                ag2_messages.append({
                    "role": "function",
                    "name": msg.get("name", "tool"),
                    "content": content
                })

        return ag2_messages

    def convert_tools_to_framework(
        self,
        tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Convert MassGen tools to AG2 function format."""
        ag2_functions = []
        for tool in tools:
            if "function" in tool:
                func = tool["function"]
                ag2_functions.append({
                    "name": func["name"],
                    "description": func.get("description", ""),
                    "parameters": func.get("parameters", {})
                })
        return ag2_functions

    async def execute_streaming(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Execute AG2 agent and stream response.
        AG2 doesn't support native streaming, so we simulate it.
        """
        # For GroupChat, we need to handle the conversation differently
        if hasattr(self, 'group_chat'):
            response = await self._execute_group_chat(messages, tools)
        else:
            response = await self._execute_single_agent(messages, tools)

        # Simulate streaming of the response
        async for chunk in self.simulate_streaming(response):
            yield chunk

    async def _execute_single_agent(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]]
    ) -> str:
        """Execute single AG2 agent."""
        # Extract last user message
        user_message = ""
        for msg in reversed(messages):
            if msg["role"] == "user":
                user_message = msg["content"]
                break

        # Register tools if provided
        if tools:
            self._register_tools(tools)

        # Create a UserProxyAgent for interaction
        from autogen import UserProxyAgent
        user_proxy = UserProxyAgent(
            name="user_proxy",
            human_input_mode="NEVER",
            max_consecutive_auto_reply=0,
            code_execution_config={"use_docker": False}
        )

        # Run conversation
        response = await asyncio.to_thread(
            user_proxy.initiate_chat,
            self.agent,
            message=user_message,
            clear_history=False
        )

        # Extract response
        last_message = self.agent.last_message()
        return last_message.get("content", "")

    async def _execute_group_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]]
    ) -> str:
        """Execute AG2 GroupChat."""
        # Extract last user message
        user_message = ""
        for msg in reversed(messages):
            if msg["role"] == "user":
                user_message = msg["content"]
                break

        # Add message to group chat
        self.group_chat.messages.append({"role": "user", "content": user_message})

        # Run group chat manager
        response = await asyncio.to_thread(
            self.agent.run_chat,
            self.group_chat.messages[-1],
            self.group_chat
        )

        return response

    def _register_tools(self, tools: List[Dict[str, Any]]):
        """Register tools as AG2 functions."""
        for tool in tools:
            if "function" in tool:
                func = tool["function"]

                # Create a wrapper function for the tool
                def tool_wrapper(**kwargs):
                    # This would call the actual tool implementation
                    return f"Tool {func['name']} called with {kwargs}"

                # Register with the agent
                self.agent.register_function(
                    function_map={func["name"]: tool_wrapper}
                )
```

### LangChain Adapter Implementation

```python
# massgen/adapters/langchain_adapter.py
from typing import List, Dict, Any, Optional, AsyncGenerator
import asyncio
from ..backend.base import StreamChunk
from .base import AgentAdapter

class LangChainAdapter(AgentAdapter):
    """
    Adapter for LangChain agents and chains.
    """

    def _setup_adapter(self) -> None:
        """Initialize LangChain agent or chain."""
        from langchain.agents import initialize_agent, AgentType
        from langchain.chains import ConversationChain
        from langchain.memory import ConversationBufferMemory

        chain_type = self.config.get("chain_type", "agent")

        if chain_type == "agent":
            self._setup_agent()
        elif chain_type == "conversation":
            self._setup_conversation_chain()
        else:
            raise ValueError(f"Unsupported chain type: {chain_type}")

    def _setup_agent(self):
        """Setup LangChain agent."""
        from langchain.agents import initialize_agent, AgentType
        from langchain.llms import OpenAI
        from langchain.memory import ConversationBufferMemory

        # Get LLM configuration
        llm_config = self.config.get("llm_config", {})
        llm = OpenAI(**llm_config)

        # Setup memory
        memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True
        )

        # Get tools
        tools = self._get_langchain_tools()

        # Initialize agent
        agent_config = self.config.get("agent_config", {})
        self.agent = initialize_agent(
            tools=tools,
            llm=llm,
            agent=AgentType.CONVERSATIONAL_REACT_DESCRIPTION,
            memory=memory,
            **agent_config
        )

    def convert_messages_to_framework(
        self,
        messages: List[Dict[str, Any]]
    ) -> List[Any]:
        """Convert MassGen messages to LangChain format."""
        from langchain.schema import HumanMessage, AIMessage, SystemMessage

        langchain_messages = []
        for msg in messages:
            role = msg["role"]
            content = msg["content"]

            if role == "system":
                langchain_messages.append(SystemMessage(content=content))
            elif role == "user":
                langchain_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                langchain_messages.append(AIMessage(content=content))

        return langchain_messages

    def convert_tools_to_framework(
        self,
        tools: List[Dict[str, Any]]
    ) -> List[Any]:
        """Convert MassGen tools to LangChain format."""
        from langchain.tools import Tool

        langchain_tools = []
        for tool in tools:
            if "function" in tool:
                func = tool["function"]

                # Create wrapper function
                def tool_func(query: str) -> str:
                    return f"Called {func['name']} with: {query}"

                langchain_tools.append(
                    Tool(
                        name=func["name"],
                        description=func.get("description", ""),
                        func=tool_func
                    )
                )

        return langchain_tools

    async def execute_streaming(
        self,
        messages: List[Any],
        tools: List[Any],
        **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """Execute LangChain agent with streaming."""
        # Extract the last user message
        user_input = ""
        for msg in reversed(messages):
            if hasattr(msg, "content") and msg.__class__.__name__ == "HumanMessage":
                user_input = msg.content
                break

        # Run agent
        response = await asyncio.to_thread(
            self.agent.run,
            user_input
        )

        # Simulate streaming
        async for chunk in self.simulate_streaming(response):
            yield chunk

    def _get_langchain_tools(self) -> List[Any]:
        """Get configured LangChain tools."""
        from langchain.tools import Tool

        tools = []
        tool_configs = self.config.get("tools", [])

        for tool_config in tool_configs:
            if tool_config["type"] == "serpapi":
                from langchain.tools import DuckDuckGoSearchRun
                tools.append(DuckDuckGoSearchRun())
            elif tool_config["type"] == "wikipedia":
                from langchain.tools import WikipediaQueryRun
                from langchain.utilities import WikipediaAPIWrapper
                tools.append(WikipediaQueryRun(api_wrapper=WikipediaAPIWrapper()))

        return tools
```

### SmolAgent Adapter

```python
# massgen/adapters/smolagent_adapter.py
from typing import List, Dict, Any, AsyncGenerator
from ..backend.base import StreamChunk
from .base import AgentAdapter

class SmolAgentAdapter(AgentAdapter):
    """
    Adapter for HuggingFace SmolAgent framework agents.
    """

    def _setup_adapter(self):
        from smolagents import Agent, Tool

        self.agent_type = self.config.get("agent_type", "Agent")
        self.agent_config = self.config.get("agent_config", {})

        # Create SmolAgent
        if self.agent_type == "Agent":
            self.agent = Agent(**self.agent_config)
        else:
            raise ValueError(f"Unsupported SmolAgent type: {self.agent_type}")

    def convert_messages_to_framework(self, messages: List[Dict]) -> str:
        """Convert messages to SmolAgent format (single prompt)."""
        # SmolAgent typically works with a single prompt
        # Extract the last user message or concatenate conversation
        for message in reversed(messages):
            if message["role"] == "user":
                return message["content"]
        return ""

    def convert_tools_to_framework(self, tools: List[Dict]) -> List:
        """Convert MassGen tools to SmolAgent tools."""
        smol_tools = []
        for tool in tools:
            # Create SmolAgent tool wrapper
            # Note: This is a simplified example
            # Real implementation would need proper tool conversion
            pass
        return smol_tools

    async def execute_streaming(
        self,
        messages: str,  # SmolAgent uses string prompt
        tools: List,
        **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """Execute SmolAgent and stream response."""
        # SmolAgent doesn't support streaming natively
        response = await self._run_agent(messages, tools)

        # Simulate streaming
        async for chunk in self.simulate_streaming(response):
            yield chunk

    async def _run_agent(self, prompt: str, tools: List) -> str:
        """Run the SmolAgent."""
        import asyncio

        # Run synchronous agent in thread pool
        result = await asyncio.to_thread(
            self.agent.run,
            prompt,
            tools=tools
        )

        return result
```

### Black Box Agent Support

MassGen supports integrating any pre-existing agent as a "black box" without requiring knowledge of its internal implementation. This allows you to:
- Use agents written in any language (Python, JavaScript, Go, etc.)
- Integrate proprietary or closed-source agents
- Connect to agents running as microservices
- Use agents with complex dependencies without installing them locally

#### Black Box Agent Interface

```python
# massgen/adapters/blackbox.py
from typing import Protocol, Dict, List, Any, Optional, AsyncGenerator
import subprocess
import asyncio
import json
from abc import ABC, abstractmethod

class BlackBoxAgentProtocol(Protocol):
    """Minimal interface that any black box agent must implement."""

    async def chat(self, messages: List[Dict], **kwargs) -> AsyncGenerator[Dict, None]:
        """Send messages and receive streaming response."""
        ...

    async def health_check(self) -> bool:
        """Check if agent is responsive."""
        ...

class BlackBoxAdapter(AgentAdapter):
    """
    Universal adapter for black box agents.
    Requires only a communication protocol, not framework knowledge.
    """

    def _setup_adapter(self) -> None:
        """Initialize black box agent communication."""
        self.communication_method = self.config.get("communication_method", "http")
        self.protocol_version = self.config.get("protocol_version", "1.0")

        # Initialize appropriate communicator
        self.communicator = self._create_communicator()

    def _create_communicator(self):
        """Create appropriate communicator based on method."""
        if self.communication_method == "http":
            return HTTPCommunicator(self.config)
        elif self.communication_method == "pipe":
            return PipeCommunicator(self.config)
        elif self.communication_method == "file":
            return FileCommunicator(self.config)
        elif self.communication_method == "grpc":
            return GRPCCommunicator(self.config)
        else:
            raise ValueError(f"Unknown communication method: {self.communication_method}")

    def convert_messages_to_framework(
        self,
        messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Black box agents use standard message format."""
        return messages

    def convert_tools_to_framework(
        self,
        tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Black box agents use standard tool format."""
        return tools

    async def execute_streaming(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """Execute black box agent through standardized protocol."""

        # Prepare standardized request
        request = {
            "version": self.protocol_version,
            "messages": messages,
            "tools": tools,
            "options": kwargs
        }

        # Send request and stream response
        async for response in self.communicator.exchange(request):
            # Convert response to StreamChunk
            yield StreamChunk(
                type=response.get("type", "content"),
                content=response.get("content", ""),
                tool_calls=response.get("tool_calls"),
                complete_message=response.get("complete_message"),
                error=response.get("error")
            )
```

#### Communication Methods

##### 1. HTTP/REST Black Box Agent

```python
# massgen/adapters/blackbox/http_communicator.py
class HTTPCommunicator:
    """Communicate with black box agents via HTTP."""

    def __init__(self, config: Dict[str, Any]):
        self.endpoint = config["endpoint"]
        self.headers = config.get("headers", {})
        self.timeout = config.get("timeout", 300)

    async def exchange(self, request: Dict) -> AsyncGenerator[Dict, None]:
        """Send request via HTTP and stream response."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.endpoint,
                json=request,
                headers=self.headers,
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as response:
                # Handle streaming or non-streaming response
                if "stream" in response.headers.get("content-type", ""):
                    async for line in response.content:
                        if line:
                            yield json.loads(line.decode())
                else:
                    result = await response.json()
                    yield result
```

##### 2. Local Process Black Box Agent

```python
# massgen/adapters/blackbox/pipe_communicator.py
class PipeCommunicator:
    """Communicate with black box agents via stdin/stdout pipes."""

    def __init__(self, config: Dict[str, Any]):
        self.command = config["command"]  # e.g., ["python", "my_agent.py"]
        self.working_dir = config.get("working_dir", ".")
        self.env = config.get("env", {})
        self.process = None

    async def exchange(self, request: Dict) -> AsyncGenerator[Dict, None]:
        """Send request via pipe and stream response."""
        if not self.process:
            await self._start_process()

        # Send request as JSON line
        request_line = json.dumps(request) + "\n"
        self.process.stdin.write(request_line.encode())
        await self.process.stdin.drain()

        # Read streaming response
        while True:
            line = await self.process.stdout.readline()
            if not line:
                break

            response = json.loads(line.decode())
            if response.get("type") == "end":
                break

            yield response

    async def _start_process(self):
        """Start the black box agent process."""
        self.process = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.working_dir,
            env={**os.environ, **self.env}
        )
```

##### 3. File-Based Black Box Agent

```python
# massgen/adapters/blackbox/file_communicator.py
class FileCommunicator:
    """Communicate with black box agents via file system."""

    def __init__(self, config: Dict[str, Any]):
        self.input_file = config["input_file"]
        self.output_file = config["output_file"]
        self.trigger_command = config.get("trigger_command")  # Optional command to trigger processing
        self.polling_interval = config.get("polling_interval", 0.1)

    async def exchange(self, request: Dict) -> AsyncGenerator[Dict, None]:
        """Send request via file and read response."""
        # Write request to input file
        with open(self.input_file, 'w') as f:
            json.dump(request, f)

        # Trigger processing if command provided
        if self.trigger_command:
            await asyncio.create_subprocess_shell(self.trigger_command)

        # Poll output file for response
        output_path = Path(self.output_file)
        while not output_path.exists():
            await asyncio.sleep(self.polling_interval)

        # Read streaming response from file
        with open(self.output_file, 'r') as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)

        # Clean up
        output_path.unlink()
```

#### Black Box Agent Wrapper Scripts

For non-Python agents, provide wrapper scripts that implement the protocol:

##### Node.js Wrapper Example

```javascript
// blackbox_wrapper.js
const readline = require('readline');
const { MyCustomAgent } = require('./my_agent');

const agent = new MyCustomAgent();
const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout
});

rl.on('line', async (line) => {
    const request = JSON.parse(line);

    // Call your agent
    const response = await agent.chat(request.messages);

    // Stream response
    for (const chunk of response) {
        console.log(JSON.stringify({
            type: 'content',
            content: chunk
        }));
    }

    // Signal completion
    console.log(JSON.stringify({ type: 'end' }));
});
```

##### Python Wrapper Example

```python
# blackbox_wrapper.py
import sys
import json
from my_custom_agent import MyAgent  # Your existing agent

agent = MyAgent()

while True:
    line = sys.stdin.readline()
    if not line:
        break

    request = json.loads(line)

    # Call your agent
    response = agent.process(request['messages'])

    # Stream response
    for chunk in response:
        print(json.dumps({
            'type': 'content',
            'content': chunk
        }))
        sys.stdout.flush()

    # Signal completion
    print(json.dumps({'type': 'end'}))
    sys.stdout.flush()
```

### Remote/Cloud Agent Adapter

```python
# massgen/adapters/remote_adapter.py
import aiohttp
import asyncio
from typing import List, Dict, Any, Optional, AsyncGenerator
import json
from urllib.parse import urljoin

class RemoteAgentAdapter(AgentAdapter):
    """Adapter for agents running as remote services."""

    def _setup_adapter(self) -> None:
        """Initialize remote agent connection."""
        self.endpoint_url = self.config.get("endpoint_url")
        self.auth_config = self.config.get("auth_config", {})
        self.protocol = self.config.get("protocol", "http")
        self.timeout = self.config.get("timeout", 300)
        self.session = None

        self.endpoint_url = endpoint_url
        self.auth_config = auth_config or {}
        self.protocol = protocol
        self.timeout = timeout
        self.session = None

    async def _ensure_session(self):
        """Ensure HTTP session exists."""
        if self.session is None:
            timeout_config = aiohttp.ClientTimeout(total=self.timeout)
            self.session = aiohttp.ClientSession(
                timeout=timeout_config,
                headers=self._get_auth_headers()
            )

    def _get_auth_headers(self) -> Dict[str, str]:
        """Build authentication headers."""
        headers = {"Content-Type": "application/json"}

        if self.auth_config.get("api_key"):
            headers["Authorization"] = f"Bearer {self.auth_config['api_key']}"
        elif self.auth_config.get("custom_headers"):
            headers.update(self.auth_config["custom_headers"])

        return headers

    async def _execute_framework_agent(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        **kwargs
    ) -> AsyncGenerator[Dict, None]:
        """Execute remote agent via HTTP or WebSocket."""

        if self.protocol == "websocket":
            async for chunk in self._execute_websocket(messages, tools, **kwargs):
                yield chunk
        else:
            async for chunk in self._execute_http(messages, tools, **kwargs):
                yield chunk

    async def _execute_http(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        **kwargs
    ) -> AsyncGenerator[Dict, None]:
        """Execute via HTTP with SSE streaming support."""
        await self._ensure_session()

        payload = {
            "messages": messages,
            "tools": tools,
            "stream": True,
            **kwargs
        }

        # Retry logic
        retries = 0
        max_retries = self.config.retry_config.get("max_retries", 3)

        while retries < max_retries:
            try:
                async with self.session.post(
                    urljoin(self.endpoint_url, "/chat"),
                    json=payload
                ) as response:
                    if response.status != 200:
                        raise Exception(f"Remote agent error: {response.status}")

                    # Handle Server-Sent Events (SSE) streaming
                    if response.headers.get("Content-Type", "").startswith("text/event-stream"):
                        async for line in response.content:
                            line = line.decode("utf-8").strip()
                            if line.startswith("data: "):
                                data = line[6:]  # Remove "data: " prefix
                                if data == "[DONE]":
                                    break
                                try:
                                    chunk = json.loads(data)
                                    yield chunk
                                except json.JSONDecodeError:
                                    continue
                    else:
                        # Non-streaming response
                        result = await response.json()
                        yield {
                            "content": result.get("response", ""),
                            "type": "final",
                            "metadata": result.get("metadata", {})
                        }
                    break

            except asyncio.TimeoutError:
                retries += 1
                if retries >= max_retries:
                    yield {
                        "content": "Remote agent timeout",
                        "type": "error"
                    }
                await asyncio.sleep(self.config.retry_config.get("backoff", 2) ** retries)
            except Exception as e:
                retries += 1
                if retries >= max_retries:
                    yield {
                        "content": f"Remote agent error: {str(e)}",
                        "type": "error"
                    }
                await asyncio.sleep(self.config.retry_config.get("backoff", 2) ** retries)

    async def _execute_websocket(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        **kwargs
    ) -> AsyncGenerator[Dict, None]:
        """Execute via WebSocket for real-time streaming."""
        import aiohttp

        ws_url = self.endpoint_url.replace("http://", "ws://").replace("https://", "wss://")

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(
                ws_url,
                headers=self._get_auth_headers()
            ) as ws:
                # Send request
                await ws.send_json({
                    "messages": messages,
                    "tools": tools,
                    **kwargs
                })

                # Receive streaming response
                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        if data.get("type") == "done":
                            break
                        yield data
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        yield {
                            "content": f"WebSocket error: {ws.exception()}",
                            "type": "error"
                        }
                        break

    async def cleanup(self):
        """Cleanup resources."""
        if self.session:
            await self.session.close()
```

### Message and Tool Converters

**Note**: Message and tool conversion is handled directly within each adapter's `convert_messages_to_framework` and `convert_tools_to_framework` methods. This keeps the conversion logic close to where it's used and allows each framework adapter to handle its specific requirements.

### Adapter Registry

```python
# massgen/adapters/__init__.py
from typing import Dict, Type
from .base import AgentAdapter
from .ag2_adapter import AG2Adapter
from .langchain_adapter import LangChainAdapter
from .langgraph_adapter import LangGraphAdapter
from .smolagent_adapter import SmolAgentAdapter
from .blackbox_adapter import BlackBoxAdapter
from .remote_adapter import RemoteAgentAdapter
# Global adapter registry used by ExternalAgentBackend
adapter_registry: Dict[str, Type[AgentAdapter]] = {
    # Framework-specific adapters
    "ag2": AG2Adapter,
    "autogen": AG2Adapter,  # AG2 is the new name for AutoGen
    "langchain": LangChainAdapter,
    "langgraph": LangGraphAdapter,
    "smolagent": SmolAgentAdapter,

    # Black box adapter for any external agent (including subprocess)
    "blackbox": BlackBoxAdapter,
    "process": BlackBoxAdapter,  # Alias - uses pipe communication
    "local": BlackBoxAdapter,    # Alias - uses pipe communication

    # Remote agent adapter (HTTP/WebSocket APIs)
    "remote": RemoteAgentAdapter,
}

def register_adapter(name: str, adapter_class: Type[AgentAdapter]):
    """Register a new adapter in the global registry."""
    adapter_registry[name] = adapter_class
```

## File Structure and Organization

### Directory Layout

```
massgen/
├── adapters/                      # All framework adapter implementations
│   ├── __init__.py               # Export main adapter classes
│   ├── base.py                   # Base AgentAdapter class
│   ├── registry.py               # Adapter registry and registration functions
│   ├── __init__.py               # Contains adapter_registry for all adapters
│   │
│   ├── blackbox/                 # Black box agent support
│   │   ├── __init__.py
│   │   ├── blackbox_adapter.py  # BlackBoxAdapter main class
│   │   ├── communicators.py     # All communicator implementations
│   │   ├── http_communicator.py # HTTP/REST communication
│   │   ├── pipe_communicator.py # Stdin/stdout pipe communication
│   │   ├── file_communicator.py # File-based communication
│   │   └── grpc_communicator.py # gRPC communication (optional)
│   │
│   ├── frameworks/               # Framework-specific adapters
│   │   ├── __init__.py
│   │   ├── langchain_adapter.py # LangChainAgentAdapter
│   │   ├── autogen_adapter.py   # AutoGenAgentAdapter (also for AG2)
│   │   ├── langgraph_adapter.py # LangGraphAdapter
│   │   ├── openai_assistant_adapter.py # OpenAIAssistantAdapter
│   │   └── smolagent_adapter.py # SmolAgentAdapter
│   │
│   ├── remote/                   # Remote and cloud agent adapters
│   │   ├── __init__.py
│   │   └── remote_adapter.py    # RemoteAgentAdapter (HTTP/WebSocket)
│   │
│   └── utils/                    # Adapter utilities
│       ├── __init__.py
│       ├── streaming.py          # Streaming helpers and queue management
│       ├── retry.py              # Retry logic and exponential backoff
│       ├── auth.py               # Authentication helpers
│       └── protocol.py           # Protocol definitions and validators
│
├── backend/                      # Existing backend implementations
│   ├── base.py                  # LLMBackend base class (already exists)
│   └── ...                      # Other existing backends
│
├── configs/                      # Configuration files
│   ├── examples/                # Example configurations
│   │   ├── framework_agents/    # Framework-specific examples
│   │   │   ├── langchain_team.yaml
│   │   │   ├── autogen_team.yaml
│   │   │   ├── mixed_framework_team.yaml
│   │   │   └── cloud_agents.yaml
│   │   └── ...                  # Existing examples
│   └── ...                      # Existing configs
│
└── tests/                       # Test files
    ├── adapters/                # Adapter-specific tests
    │   ├── test_base_adapter.py
    │   ├── test_langchain_adapter.py
    │   ├── test_autogen_adapter.py
    │   ├── test_remote_adapter.py
    │   ├── test_converters.py
    │   └── test_factory.py
    └── ...                      # Existing tests
```

### File Contents Specification

#### 1. Core Base Classes

**`massgen/adapters/base.py`**
```python
# Contains:
- AgentAdapter abstract base class
- StreamChunk simulation utilities
- Common adapter base functionality
```

**`massgen/adapters/converters.py`**
**Note**: Message and tool conversion is now integrated directly into each adapter implementation.

**`massgen/adapters/factory.py`**
```python
# Contains:
- AgentAdapterRegistry class
- load_framework_agent() function
- Dynamic adapter registration
```

#### 2. Agent-Specific Adapters

**`massgen/adapters/frameworks/langchain_adapter.py`**
```python
# Contains:
- LangChainAgentAdapter class
- LangChain-specific message conversion
- Chain and AgentExecutor handling
```

**`massgen/adapters/frameworks/autogen_adapter.py`**
```python
# Contains:
- AutoGenAgentAdapter class
- AG2 compatibility layer
- Code execution integration
```

**`massgen/adapters/frameworks/langgraph_adapter.py`**
```python
# Contains:
- LangGraphAdapter class
- Graph-based agent workflow support
- State machine integration
```

**`massgen/adapters/frameworks/openai_assistant_adapter.py`**
```python
# Contains:
- OpenAIAssistantAdapter class
- Thread management
- Assistant API integration
```

**`massgen/adapters/frameworks/smolagent_adapter.py`**
```python
# Contains:
- SmolAgentAdapter class
- SmolAgent tool integration
- Lightweight agent support
```

#### 3. Remote Agent Adapters

**`massgen/adapters/remote/remote_adapter.py`**
```python
# Contains:
- RemoteAgentAdapter class
- HTTP/HTTPS client implementation
- WebSocket client implementation
- SSE (Server-Sent Events) handling
```

**Note**: Cloud agents (AWS Lambda, Google Cloud Functions, etc.) can be integrated using `RemoteAgentAdapter` with appropriate authentication configuration. No separate cloud adapter is needed.

**Note**: Local subprocess agents are handled by `BlackBoxAdapter` with `communication_method: "pipe"` using the `PipeCommunicator`. This avoids duplication since subprocess communication is just one method of black box agent integration.

#### 4. Utility Modules

**`massgen/adapters/utils/streaming.py`**
```python
# Contains:
- StreamQueue class for async streaming
- ChunkProcessor for format conversion
- StreamMerger for combining multiple streams
```

**`massgen/adapters/utils/retry.py`**
```python
# Contains:
- RetryPolicy class
- ExponentialBackoff implementation
- Circuit breaker pattern
```

**`massgen/adapters/utils/auth.py`**
```python
# Contains:
- AuthProvider interface
- OAuth2Provider class
- APIKeyProvider class
- Custom header management
```

### Integration Points

#### 1. Modify Existing Files

**`massgen/chat_agent.py`**
```python
# No changes needed - ConfigurableAgent already supports custom backends
```

**`massgen/orchestrator.py`**
```python
# Minor addition to support framework agent loading:
def _load_agents_from_config(self, config: Dict) -> Dict[str, ChatAgent]:
    """Load agents including framework agents."""
    agents = {}
    for agent_config in config.get("agents", []):
        if agent_config.get("type") == "framework":
            from .adapters.factory import load_framework_agent
            agents[agent_config["id"]] = load_framework_agent(agent_config)
        else:
            # Existing agent loading logic
            pass
    return agents
```

**`massgen/cli.py`**
```python
# Add framework agent support in configuration loading:
def load_configuration(config_path: str) -> Dict:
    """Enhanced to support framework agent configurations."""
    # Existing loading logic
    # Add validation for framework agent configs
    pass
```

**`massgen/__init__.py`**
```python
# Export new adapter classes:
from .adapters.factory import (
    AgentAdapterRegistry,
    load_framework_agent
)
from .adapters.base import AgentAdapter

__all__ = [
    # ... existing exports ...
    "AgentAdapterRegistry",
    "load_framework_agent",
    "AgentAdapter",
]
```

### Configuration Schema Updates

**`massgen/schemas/agent_config_schema.json`** (updates to existing file)
```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "definitions": {
    "frameworkAgent": {
      "type": "object",
      "required": ["id", "backend"],
      "properties": {
        "id": {"type": "string"},
        "backend": {
          "type": "object",
          "required": ["type"],
          "properties": {
            "type": {
              "enum": ["ag2", "langchain", "langgraph", "smolagent", "blackbox", "remote"]
            }
          },
          "additionalProperties": true
        },
        "system_message": {"type": "string"}
      }
    },
    "nativeAgent": {
      "type": "object",
      "required": ["id", "backend"],
      "properties": {
        "id": {"type": "string"},
        "backend": {"type": "object"},
        "system_message": {"type": "string"}
      }
    }
  }
}
```

### Testing Structure

**`massgen/tests/adapters/test_base_adapter.py`**
```python
# Tests for:
- AgentAdapter abstract methods
- Message conversion pipeline
- Tool merging logic
- Streaming functionality
```

**`massgen/tests/adapters/test_langchain_adapter.py`**
```python
# Tests for:
- LangChain agent execution
- Memory management
- Tool registration
- Streaming callbacks
```

**`massgen/tests/adapters/test_factory.py`**
```python
# Tests for:
- Registry registration/lookup
- Dynamic adapter creation
- Configuration loading
- ConfigurableAgent wrapping
```

### Import Structure

The main entry points for using framework agents:

```python
# For users of the library:
from massgen import load_framework_agent, AgentAdapterRegistry

# For extending with custom frameworks:
from massgen.adapters.base import AgentAdapter

# For direct adapter usage:
from massgen.adapters.frameworks import (
    LangChainAdapter,
    AG2Adapter
)
from massgen.adapters.remote import RemoteAgentAdapter
```

## Implementation Plan

### Phase 1: Core Infrastructure + AG2 (Week 1)
1. Create `ExternalAgentBackend` class extending `LLMBackend`
2. Implement base `AgentAdapter` with streaming simulation
3. Add framework detection to CLI backend factory
4. Implement AG2 adapter with single agent and GroupChat support
5. Create message and tool converters
6. Write comprehensive test suite for AG2 integration

### Phase 2: Additional Frameworks (As Needed)
- LangChain adapter when LangChain integration is required
- Remote agent adapter for HTTP/WebSocket agents
- Other framework adapters based on user requirements
- Each can be implemented independently as demand arises
- Create comprehensive documentation:
  - Integration guide for new frameworks
  - Performance tuning guide
  - Troubleshooting guide
  - API reference documentation

**Deliverables**:
- 2+ additional framework adapters
- Performance optimization utilities
- Reliability features
- Complete documentation suite
- Performance benchmarks

### Phase 6: Testing and Documentation (Week 6-7)
**Goal**: Ensure production readiness

**Tasks**:
- **Testing**:
  - End-to-end integration tests with mixed agent teams
  - Stress testing with 10+ concurrent agents
  - Failure scenario testing
  - Performance regression tests
  - Security audit of authentication mechanisms
- **Documentation**:
  - Update README with framework integration examples
  - Create migration guide from single-framework setups
  - Write best practices guide
  - Add troubleshooting section
  - Create video tutorials
- **Examples and Templates**:
  - 10+ example configurations for different use cases
  - Project templates for common scenarios
  - Jupyter notebooks with demonstrations
  - CLI tool for generating configurations
- **Community Preparation**:
  - Create contribution guidelines for new adapters
  - Set up GitHub issue templates
  - Prepare release notes
  - Create blog post announcing the feature

**Deliverables**:
- 95%+ test coverage
- Complete documentation
- 10+ working examples
- Release-ready codebase

## Example Configurations

### Black Box Agent Configuration Examples

#### Example 1: Using a Pre-existing Local Agent

```yaml
# blackbox_local_agent.yaml
agents:
  - id: "my_existing_agent"
    type: "blackbox"
    communication_method: "pipe"
    connection_config:
      command: ["python", "/path/to/my/agent.py"]
      working_dir: "/path/to/my/agent"
      env:
        MY_AGENT_CONFIG: "production"
    system_message: |
      You are integrated as a black box agent. Process requests and provide responses.

  - id: "nodejs_agent"
    type: "blackbox"
    communication_method: "pipe"
    connection_config:
      command: ["node", "/path/to/agent/wrapper.js"]
      working_dir: "/path/to/agent"

  - id: "native_agent"
    type: "native"
    backend:
      type: "openai"
      model: "gpt-4o-mini"

orchestrator:
  timeout_config:
    orchestrator_timeout_seconds: 600

ui:
  type: "rich_terminal"
```

Run commands with specific prompts:
```bash
uv run python -m massgen.cli --config blackbox_local_agent.yaml "Convert this request to SQL: Show me all customers who made purchases over $1000 in the last month"

```

#### Example 2: Using a Cloud-based Black Box Agent

```yaml
# blackbox_cloud_agent.yaml
agents:
  - id: "proprietary_cloud_agent"
    type: "blackbox"
    communication_method: "http"
    connection_config:
      endpoint: "https://api.mycompany.com/agent/chat"
      headers:
        Authorization: "Bearer ${MY_API_KEY}"
        X-Agent-Version: "2.0"
      timeout: 300

  - id: "microservice_agent"
    type: "blackbox"
    communication_method: "http"
    connection_config:
      endpoint: "http://agent-service.internal:8080/process"
      headers:
        Content-Type: "application/json"

  - id: "analysis_agent"
    type: "native"
    backend:
      type: "claude"
      model: "claude-3-sonnet"

orchestrator:
  snapshot_storage: "blackbox_snapshots"

ui:
  type: "rich_terminal"
```

Run commands with specific prompts:
```bash
# Natural language to SQL
uv run python -m massgen.cli --config blackbox_cloud_agent.yaml "Convert this request to SQL: Show me all customers who made purchases over $1000 in the last month"
```

#### Example 3: File-based Black Box Agent

```yaml
# blackbox_file_agent.yaml
agents:
  - id: "legacy_system_agent"
    type: "blackbox"
    communication_method: "file"
    connection_config:
      input_file: "/tmp/agent_input.json"
      output_file: "/tmp/agent_output.json"
      trigger_command: "/usr/local/bin/process_agent_request"
      polling_interval: 0.5

  - id: "batch_processor"
    type: "blackbox"
    communication_method: "file"
    connection_config:
      input_file: "/shared/input/request.json"
      output_file: "/shared/output/response.json"
      trigger_command: "docker run --rm -v /shared:/data my-agent:latest"
```

Run commands with specific prompts:
```bash
# Batch data transformation
uv run python -m massgen.cli --config blackbox_file_agent.yaml "Transform the daily transaction logs from fixed-width format to JSON and apply business rules validation"
```

### Framework Agent Configuration Examples
### Example 1: Research Team with Mixed Frameworks

```yaml
# research_mixed_team.yaml
agents:
  - id: "web_researcher"
    backend:
      type: "langchain"
      chain_type: "ReActChain"
      llm:
        provider: "openai"
        model: "gpt-4o-mini"
      tools:
        - "google_search"
        - "wikipedia"
        - "arxiv"
      memory:
        type: "conversation_buffer"
        max_tokens: 2000

  - id: "data_analyst"
    type: "native"
    backend:
      type: "openai"
      model: "gpt-5-nano"
      enable_code_interpreter: true
    system_message: |
      You are a data analysis expert. Analyze data, create visualizations,
      and provide statistical insights.

  - id: "report_writer"
    backend:
      type: "ag2"  # AG2 is the new name for AutoGen
      llm_config:
        model: "claude-3-sonnet"
        temperature: 0.7
      human_input_mode: "NEVER"
      code_execution_config:
        work_dir: "./autogen_workspace"
        use_docker: false
    system_message: |
      You are a technical report writer. Synthesize research findings
      into clear, structured reports with executive summaries.

orchestrator:
  snapshot_storage: "research_snapshots"
  agent_temporary_workspace: "research_workspace"

ui:
  type: "rich_terminal"
  logging_enabled: true
```

Run commands with specific prompts:
```bash
# Research quantum computing
uv run python -m massgen.cli --config ag2_groupchat.yaml "Research the latest developments in quantum computing and analyze their potential impact on cryptography"
```

### Example 2: Mixed Team Configuration

```yaml
# Mixed team: AG2 GroupChat + Native MassGen agents
agents:
  # AG2 GroupChat for research
  - id: "ag2_research_group"
    backend:
      type: "ag2"

      group_config:
        agents:
          - type: "AssistantAgent"
            config:
              name: "web_researcher"
              system_message: "Search and gather information from the web."
              llm_config:
                model: "gpt-4"

          - type: "AssistantAgent"
            config:
              name: "fact_checker"
              system_message: "Verify facts and check sources."
              llm_config:
                model: "gpt-4"

        chat_config:
          max_round: 5
          speaker_selection_method: "round_robin"

  # Native MassGen agent for code
  - id: "native_coder"
    backend:
      type: "openai"
      model: "gpt-4"
      enable_code_interpreter: true
    system_message: "You write and debug code based on research findings."

  # LangChain agent for documentation
  - id: "langchain_documenter"
    backend:
      type: "langchain"

      chain_type: "agent"
      agent_config:
        agent_type: "openai-functions"
        model_name: "gpt-4"
        temperature: 0.7
        tools: ["serpapi", "wikipedia"]

      memory_config:
        type: "ConversationSummaryMemory"
        llm_model_name: "gpt-3.5-turbo"

# Orchestrator configuration
orchestrator:
  timeout_seconds: 1800

  # Enable workspace sharing between agents
  context_sharing:
    enabled: true
    snapshot_storage: "./agent_snapshots"

  # Orchestration strategy
  strategy:
    type: "voting"
    min_votes: 2
```

### Example 3: Parallel Data Science Agents

```yaml
# data_science_team.yaml
agents:
  - id: "claude_code"
    type: "native"
    backend:
      type: "claude_code"
      cwd: "claude_workspace"
      model: "claude-opus-4-1"
      allowed_tools:
        - "Read"
        - "Write"
        - "Edit"
        - "Bash"
        - "WebSearch"
        - "TodoWrite"
        - "NotebookEdit"
        - "mcp__ide__executeCode"
    system_message: |
      You are Claude Code, an expert data science assistant with comprehensive
      development tools. Focus on exploratory data analysis, feature engineering,
      and model prototyping.

  - id: "ag2_specialist"
    backend:
      type: "ag2"
      agent_type: "AssistantAgent"
      name: "DataScienceSpecialist"
      llm_config:
        config_list:
          - model: "gpt-5-mini"
            api_key: "${OPENAI_API_KEY}"
        temperature: 0.5
      code_execution_config:
        last_n_messages: 2
        work_dir: "./ag2_workspace"
        use_docker: false
      max_consecutive_auto_reply: 10
      human_input_mode: "NEVER"
      system_message: |
        You are an AG2-based data science specialist. Excel at statistical analysis,
        machine learning model development, and automated experimentation.
        Use your code execution capabilities for complex computations.

  - id: "smolagent_analyst"
    type: "framework"
    framework: "smolagent"
    framework_config:
      model_id: "Qwen/Qwen2.5-72B-Instruct"
      tools:
        - name: "PythonInterpreter"
        - name: "Calculator"
        - name: "DataVisualizer"
        - name: "FileManager"
      max_steps: 20
      memory:
        type: "working_memory"
        max_messages: 10
    system_message: |
      You are a SmolAgent-powered data analyst specializing in automated
      data processing pipelines and visualization. Focus on efficiency
      and creating reusable analysis workflows.

orchestrator:
  snapshot_storage: "data_science_snapshots"
  agent_temporary_workspace: "data_science_workspaces"
  timeout_config:
    orchestrator_timeout_seconds: 3600  # 1 hour for complex analyses

ui:
  type: "rich_terminal"
  logging_enabled: true
```

Run commands with specific prompts:
```bash
# Process data through black box agents
uv run python -m massgen.cli --config blackbox_agents.yaml "Process the customer data through our proprietary system and generate insights"
```

## Black Box Agent Advantages

### Why Use Black Box Agents?

1. **Language Independence**: Your agent can be written in any language (Python, JavaScript, Go, Rust, Java, etc.)
2. **No Framework Lock-in**: Use any existing agent regardless of its underlying framework
3. **Proprietary Code Protection**: Keep your agent's implementation private
4. **Complex Dependencies**: Avoid dependency conflicts by isolating agents
5. **Legacy System Integration**: Integrate older systems without modification
6. **Microservice Architecture**: Use agents deployed as independent services

### Common Use Cases

#### 1. Enterprise Integration
```yaml
# Integrate proprietary company agents
agents:
  - id: "company_knowledge_base"
    type: "blackbox"
    communication_method: "http"
    connection_config:
      endpoint: "https://internal.co gmpany.com/ai-agent/v2"
      headers:
        Authorization: "Bearer ${COMPANY_TOKEN}"
```

#### 2. Multi-Language Teams
```yaml
# Team members can contribute agents in their preferred language
agents:
  - id: "rust_performance_analyzer"
    type: "blackbox"
    communication_method: "pipe"
    connection_config:
      command: ["./rust_agent"]

  - id: "golang_data_processor"
    type: "blackbox"
    communication_method: "pipe"
    connection_config:
      command: ["./go_agent"]
```

#### 3. Docker Container Agents
```yaml
# Run agents in isolated Docker containers
agents:
  - id: "containerized_agent"
    type: "blackbox"
    communication_method: "pipe"
    connection_config:
      command: ["docker", "run", "--rm", "-i", "my-agent:latest"]
```

#### 4. Serverless Functions
```yaml
# Use AWS Lambda or similar as agents
agents:
  - id: "lambda_agent"
    type: "blackbox"
    communication_method: "http"
    connection_config:
      endpoint: "https://api.gateway.url/prod/agent"
      headers:
        X-API-Key: "${AWS_API_KEY}"
```

### Protocol Specification

The black box protocol is intentionally simple to make integration easy:

#### Request Format
```json
{
  "version": "1.0",
  "messages": [
    {"role": "user", "content": "Hello"}
  ],
  "tools": [],  // Optional
  "options": {   // Optional
    "temperature": 0.7,
    "max_tokens": 1000
  }
}
```

#### Response Format (Streaming)
```json
{"type": "content", "content": "Hello! "}
{"type": "content", "content": "How can I help?"}
{"type": "tool_call", "tool": "search", "args": {...}}
{"type": "end"}
```

#### Response Format (Non-streaming)
```json
{
  "type": "final",
  "content": "Hello! How can I help you today?",
  "metadata": {
    "tokens_used": 15,
    "model": "custom-model-v1"
  }
}
```

## Benefits

### 1. Framework Diversity
- Leverage best-in-class capabilities from each framework
- Use specialized agents for specific domains
- Avoid framework lock-in

### 2. Scalability
- Distribute agents across local and cloud resources
- Scale individual agents independently
- Optimize resource usage per agent type

### 3. Compatibility
- Preserve existing MassGen coordination logic
- Framework agents participate as first-class citizens
- Unified configuration and management

### 4. Extensibility
- Easy to add new framework adapters
- Support for custom agent implementations
- Plugin architecture for specialized agents

## Future Considerations

### Dynamic Agent Selection
- Orchestrator could dynamically choose which framework agents to activate based on task requirements
- Cost-aware agent selection (prefer local/cheaper agents when suitable)

### Cross-Framework Communication
- Direct agent-to-agent communication bypassing orchestrator for efficiency
- Shared memory/context between framework agents

### Framework-Specific Optimizations
- Batch processing for certain frameworks
- Connection pooling for remote agents
- Caching of framework agent responses

## Conclusion

This design enables MassGen to become a universal orchestrator for agents regardless of their implementation framework. By wrapping framework agents with ConfigurableAgent and providing appropriate adapters, we maintain full compatibility with MassGen's proven binary decision coordination while leveraging the unique strengths of each framework. The parallel execution model ensures efficient multi-agent collaboration, and the flexible configuration system makes it easy to compose teams of heterogeneous agents for any task.