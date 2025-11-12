# MassGen Agent Hierarchy Implementation Proposal

This document outlines the design and implementation plan for a hierarchical agent structure in MassGen.

## I. Core Design Principles

Based on the "Agent as Tool" design pattern, the implementation aims to achieve the following goals:

1. **Agent as both executor and tool**: Any agent can be invoked by other agents as a tool
2. **Hierarchy transparency**: Upper-level agents don't need to know the internal implementation of lower-level agents
3. **Unified interface**: Leverage existing ChatAgent interface and tool system
4. **Flexible composition**: Support dynamic configuration of hierarchical structures

---

## II. Architecture Design

### 2.1 Overall Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                  Root Agent (L3)                        │
│  - High-level decision-making agent                     │
│  - Can invoke lower-level agents as tools               │
└───────────────────┬─────────────────────────────────────┘
                    │
        ┌───────────┴───────────┐
        │                       │
┌───────▼──────────┐    ┌──────▼─────────────┐
│  Agent A (L2)    │    │  Orchestrator (L2) │
│  - Specialized   │    │  - Multi-agent     │
│  - Can use tools │    │    coordination    │
└──────────────────┘    └────────┬───────────┘
                                 │
                    ┌────────────┼───────────┐
                    │            │           │
              ┌─────▼────┐ ┌────▼────┐ ┌───▼─────┐
              │ Agent 1  │ │ Agent 2 │ │ Agent 3 │
              │  (L1)    │ │  (L1)   │ │  (L1)   │
              └──────────┘ └─────────┘ └─────────┘
```

---

## III. Core Component Design

### 3.1 New Component: AgentToolkit

**Location**: `massgen/tool/workflow_toolkits/agent_toolkit.py`

**Responsibilities**:
- Wrap any ChatAgent instance as a tool
- Handle input/output conversion for agent calls
- Manage child agent lifecycle

**Key Methods**:

```python
class AgentToolkit(BaseToolkit):
    """
    Wraps a ChatAgent as a callable tool
    """
    def __init__(self, agent: ChatAgent, agent_id: str, description: str):
        self._agent = agent
        self._agent_id = agent_id
        self._description = description

    @property
    def toolkit_id(self) -> str:
        return f"agent_{self._agent_id}"

    @property
    def toolkit_type(self) -> ToolType:
        return ToolType.AGENT  # New type

    def get_tools(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Returns tool definition describing how to invoke this agent
        """
        return [{
            "type": "function",
            "function": {
                "name": f"call_{self._agent_id}",
                "description": self._description,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Question or task to send to the agent"
                        },
                        "context": {
                            "type": "string",
                            "description": "Optional context information"
                        }
                    },
                    "required": ["query"]
                }
            }
        }]

    async def execute(self, query: str, context: str = "") -> str:
        """
        Execute agent invocation
        """
        messages = []
        if context:
            messages.append({"role": "user", "content": context})
        messages.append({"role": "user", "content": query})

        # Collect complete response
        response_content = ""
        async for chunk in self._agent.chat(messages):
            if chunk.type == "content":
                response_content += chunk.content or ""

        return response_content
```

---

### 3.2 Extension: HierarchicalAgent

**Location**: `massgen/hierarchical_agent.py`

**Responsibilities**:
- Inherit from SingleAgent or ConfigurableAgent
- Support registering child agents as tools
- Manage hierarchical relationships and dependencies

**Key Features**:

```python
class HierarchicalAgent(ConfigurableAgent):
    """
    Agent with hierarchical structure support, can invoke other agents as tools
    """
    def __init__(
        self,
        config: AgentConfig,
        child_agents: Optional[Dict[str, ChatAgent]] = None,
        agent_descriptions: Optional[Dict[str, str]] = None
    ):
        super().__init__(config)
        self._child_agents = child_agents or {}
        self._agent_descriptions = agent_descriptions or {}
        self._agent_toolkits = self._create_agent_toolkits()

    def _create_agent_toolkits(self) -> List[AgentToolkit]:
        """
        Create tool wrappers for each child agent
        """
        toolkits = []
        for agent_id, agent in self._child_agents.items():
            description = self._agent_descriptions.get(
                agent_id,
                f"Call {agent_id} agent for specialized tasks"
            )
            toolkit = AgentToolkit(agent, agent_id, description)
            toolkits.append(toolkit)
        return toolkits

    def add_child_agent(
        self,
        agent_id: str,
        agent: ChatAgent,
        description: str
    ) -> None:
        """
        Dynamically add child agent
        """
        self._child_agents[agent_id] = agent
        self._agent_descriptions[agent_id] = description
        self._agent_toolkits = self._create_agent_toolkits()

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        reset_chat: bool = False,
        clear_history: bool = False,
        **kwargs
    ) -> AsyncGenerator[StreamChunk, None]:
        """
        Override chat method to automatically inject agent tools
        """
        # Get agent tool definitions
        agent_tools = []
        for toolkit in self._agent_toolkits:
            tools = toolkit.get_tools({})
            agent_tools.extend(tools)

        # Merge user-provided tools with agent tools
        user_tools = kwargs.pop("tools", [])
        all_tools = user_tools + agent_tools

        # Call parent method with all tools
        async for chunk in super().chat(
            messages,
            reset_chat=reset_chat,
            clear_history=clear_history,
            tools=all_tools,
            **kwargs
        ):
            # Intercept tool calls, handle agent invocations
            if chunk.type == "tool_calls":
                await self._handle_agent_tool_calls(chunk.tool_calls)

            yield chunk

    async def _handle_agent_tool_calls(
        self,
        tool_calls: List[Dict[str, Any]]
    ) -> None:
        """
        Handle tool calls to child agents
        """
        for tool_call in tool_calls:
            function_name = tool_call.get("function", {}).get("name", "")

            # Check if this is an agent call
            if function_name.startswith("call_"):
                agent_id = function_name[5:]  # Remove "call_" prefix

                if agent_id in self._child_agents:
                    # Find corresponding toolkit and execute
                    for toolkit in self._agent_toolkits:
                        if toolkit._agent_id == agent_id:
                            arguments = json.loads(
                                tool_call.get("function", {}).get("arguments", "{}")
                            )
                            result = await toolkit.execute(**arguments)

                            # Further processing of results can happen here
                            # e.g., add result to message history
                            break
```

---

### 3.3 Extension: HierarchicalOrchestrator

**Location**: `massgen/hierarchical_orchestrator.py`

**Responsibilities**:
- Expose Orchestrator as a tool to higher-level agents
- Support nested multi-agent coordination

**Design Approach**:

```python
class HierarchicalOrchestrator(Orchestrator):
    """
    Orchestrator that can be invoked as a tool
    """
    def __init__(
        self,
        agents: List[ConfigurableAgent],
        orchestrator_id: str = "orchestrator",
        description: str = "Multi-agent coordination system",
        **kwargs
    ):
        super().__init__(agents, **kwargs)
        self.orchestrator_id = orchestrator_id
        self.description = description

    def as_toolkit(self) -> AgentToolkit:
        """
        Wrap itself as AgentToolkit
        """
        return AgentToolkit(
            agent=self,
            agent_id=self.orchestrator_id,
            description=self.description
        )

    async def execute_as_tool(self, query: str, context: str = "") -> str:
        """
        Execution logic when invoked as a tool
        """
        messages = []
        if context:
            messages.append({"role": "user", "content": context})
        messages.append({"role": "user", "content": query})

        response_content = ""
        async for chunk in self.chat(messages):
            if chunk.type == "content":
                response_content += chunk.content or ""

        return response_content
```

---

## IV. Configuration System Design

### 4.1 Hierarchical Configuration Structure

**Example File**: `configs/hierarchical_agent.yaml`

```yaml
# Root Agent Config
agents:
  id: "strategic_agent"
  backend:
    type: "openai"
    model: "gpt-4o"
  system_message: "You are a strategic decision-making agent. You can delegate tasks to specialized agents."

  # Child Agent Configs
  agents:
    - id: "research_agent"
      type: "single"  # Single agent
      description: "Expert in research and information gathering"
      backend:
        type: "gemini"
        model: "gemini-2.5-pro"
        enable_web_search: true

    - id: "analysis_orchestrator"
      type: "orchestrator"  # Orchestrator as child agent
      description: "Multi-agent analysis team for complex analytical tasks"
      agents:
        - id: "analyst_1"
          backend:
            type: "openai"
            model: "gpt-4o"

        - id: "analyst_2"
          backend:
            type: "claude"
            model: "claude-3-5-sonnet-20241022"

    - id: "coding_agent"
      type: "single"
      description: "Expert in code generation and debugging"
      backend:
        type: "openai"
        model: "gpt-4o"
        enable_code_execution: true
```

---

### 4.2 Configuration Loader

**Location**: `massgen/config_loader.py` (extend existing functionality)

```python
class HierarchicalConfigLoader:
    """
    Load hierarchical agent configuration
    """
    @staticmethod
    async def load_hierarchical_agent(
        config: Dict[str, Any]
    ) -> HierarchicalAgent:
        """
        Load hierarchical agent from configuration
        """
        root_config = config["root_agent"]

        # Create root agent configuration
        backend_params = root_config["backend"]
        agent_config = AgentConfig(
            backend_params=backend_params,
            agent_id=root_config["id"],
            custom_system_instruction=root_config.get("system_message")
        )

        # Recursively load child agents
        child_agents = {}
        agent_descriptions = {}

        for child_config in root_config.get("child_agents", []):
            child_id = child_config["id"]
            child_type = child_config["type"]

            if child_type == "single":
                # Load single agent
                child_agent = await load_single_agent(child_config)
            elif child_type == "orchestrator":
                # Load orchestrator
                child_agent = await load_orchestrator(child_config)
            elif child_type == "hierarchical":
                # Recursively load hierarchical agent
                child_agent = await HierarchicalConfigLoader.load_hierarchical_agent({
                    "root_agent": child_config
                })

            child_agents[child_id] = child_agent
            agent_descriptions[child_id] = child_config.get("description", "")

        # Create hierarchical agent
        return HierarchicalAgent(
            config=agent_config,
            child_agents=child_agents,
            agent_descriptions=agent_descriptions
        )
```

---

## V. Tool Invocation Flow

### 5.1 Agent Invocation Example

```
User → Root Agent (Strategic Agent)
  ↓
Root Agent thinks: needs research information
  ↓
Root Agent calls tool: call_research_agent
  {
    "query": "What are the latest developments in quantum computing?",
    "context": "We are planning a new product strategy"
  }
  ↓
AgentToolkit executes
  ↓
Research Agent (Gemini with Web Search) processes
  ↓
Research Agent returns results
  ↓
Root Agent receives results, continues processing
  ↓
Root Agent calls tool: call_analysis_orchestrator
  {
    "query": "Analyze the strategic implications of quantum computing",
    "context": "<research results>"
  }
  ↓
Orchestrator (multiple Analyst Agents) coordinates
  ↓
Orchestrator returns comprehensive analysis
  ↓
Root Agent integrates all information, generates final decision
```

---

### 5.2 Tool Call Handling Logic

```python
# In HierarchicalAgent._handle_agent_tool_calls

async def _handle_agent_tool_calls(self, tool_calls):
    """
    Handle agent tool calls
    """
    results = []

    for tool_call in tool_calls:
        function_name = tool_call["function"]["name"]

        if function_name.startswith("call_"):
            agent_id = function_name[5:]

            if agent_id in self._child_agents:
                # Parse arguments
                args = json.loads(tool_call["function"]["arguments"])

                # Find corresponding toolkit
                toolkit = next(
                    (tk for tk in self._agent_toolkits if tk._agent_id == agent_id),
                    None
                )

                if toolkit:
                    # Execute child agent
                    result = await toolkit.execute(**args)

                    # Construct tool result
                    tool_result = {
                        "tool_call_id": tool_call["id"],
                        "role": "tool",
                        "name": function_name,
                        "content": result
                    }

                    results.append(tool_result)

    return results
```

---

## VI. Implementation Advantages

### 6.1 Architectural Advantages

1. **Fully compatible with existing system**
   - Doesn't break existing ChatAgent interface
   - Leverages existing tool system (BaseToolkit)
   - Maintains Orchestrator coordination logic

2. **Flexible hierarchy depth**
   - Supports arbitrary levels of nesting
   - Can mix SingleAgent, Orchestrator, HierarchicalAgent

3. **Unified tool interface**
   - Agents as tools seamlessly integrate with other tools
   - Upper-level agents don't need special handling, just call tools

4. **Dynamic configuration**
   - Easily define hierarchical structure through YAML config
   - Support runtime addition/removal of child agents

### 6.2 Functional Advantages

1. **Task decomposition**
   - Root agent can decompose complex tasks to specialized agents
   - Each agent focuses on its area of expertise

2. **Specialization**
   - Different hierarchy levels can have different specialties
   - Examples: research, analysis, coding, decision-making

3. **Scalability**
   - Easy to add new child agents
   - Support mixed use of multiple backends

4. **Context passing**
   - Pass context through tool parameters
   - Maintain information flow between hierarchy levels

---

## VII. Usage Examples

### 7.1 Creating a Three-Level Agent System

```python
from massgen import HierarchicalAgent, HierarchicalOrchestrator, ConfigurableAgent
from massgen.agent_config import AgentConfig

# === Level 1: Base Agents ===
analyst1 = ConfigurableAgent(
    AgentConfig.create_openai_config(model="gpt-4o", agent_id="analyst1")
)

analyst2 = ConfigurableAgent(
    AgentConfig.create_claude_config(
        model="claude-3-5-sonnet-20241022",
        agent_id="analyst2"
    )
)

# === Level 2: Orchestrator (contains multiple Level 1 agents) ===
analysis_orchestrator = HierarchicalOrchestrator(
    agents=[analyst1, analyst2],
    orchestrator_id="analysis_team",
    description="Multi-agent analysis team for complex analytical tasks"
)

# === Level 2: Research Agent ===
research_agent = ConfigurableAgent(
    AgentConfig.create_gemini_config(
        model="gemini-2.5-pro",
        enable_web_search=True,
        agent_id="researcher"
    )
)

# === Level 3: Root Agent (calls Level 2 agents) ===
root_agent = HierarchicalAgent(
    config=AgentConfig.create_openai_config(
        model="gpt-4o",
        agent_id="strategic_agent"
    ),
    child_agents={
        "analysis_team": analysis_orchestrator,
        "researcher": research_agent
    },
    agent_descriptions={
        "analysis_team": "Expert team for deep analysis and decision-making",
        "researcher": "Expert in research and information gathering with web search"
    }
)

# === Usage ===
async def main():
    messages = [{
        "role": "user",
        "content": "Analyze the future of AI in healthcare and provide strategic recommendations"
    }]

    async for chunk in root_agent.chat(messages):
        if chunk.type == "content":
            print(chunk.content, end="", flush=True)

# Root Agent may:
# 1. Call researcher to get latest information
# 2. Call analysis_team for deep analysis
# 3. Integrate all information to generate strategic recommendations
```

---

### 7.2 Loading from Configuration File

```python
from massgen.config_loader import HierarchicalConfigLoader
import yaml

# Load configuration
with open("configs/hierarchical_agent.yaml") as f:
    config = yaml.safe_load(f)

# Create hierarchical agent
root_agent = await HierarchicalConfigLoader.load_hierarchical_agent(config)

# Use
async for chunk in root_agent.chat([{
    "role": "user",
    "content": "Your complex task here"
}]):
    if chunk.type == "content":
        print(chunk.content, end="")
```

---

## VIII. Implementation Roadmap

### Phase 1: Core Foundation (Required)

1. ✅ Design AgentToolkit base class
2. ✅ Implement HierarchicalAgent class
3. ✅ Extend ToolType enum, add AGENT type
4. ✅ Implement basic agent-to-agent call mechanism

### Phase 2: Orchestrator Integration (Important)

1. ✅ Implement HierarchicalOrchestrator
2. ✅ Support Orchestrator as child agent
3. ✅ Test nested multi-agent coordination

### Phase 3: Configuration System (Convenience)

1. ✅ Design YAML configuration format
2. ✅ Implement HierarchicalConfigLoader
3. ✅ Support recursive loading of hierarchical structures
4. ✅ Configuration validation and error handling

### Phase 4: Advanced Features (Optimization)

1. 🔄 Agent caching and reuse
2. 🔄 Timeout control for child agents
3. 🔄 Context management between hierarchy levels
4. 🔄 Permission control for agent tools

### Phase 5: Monitoring and Debugging (Observability)

1. 🔄 Hierarchical call chain tracing
2. 🔄 Performance monitoring and analysis
3. 🔄 Visualize hierarchical structure
4. 🔄 Debugging tools and logging

---

## IX. Key File Checklist

### Files to create/modify:

**New Files:**

1. `massgen/tool/workflow_toolkits/agent_toolkit.py` - Agent tool wrapper
2. `massgen/hierarchical_agent.py` - Hierarchical Agent implementation
3. `massgen/hierarchical_orchestrator.py` - Hierarchical Orchestrator
4. `massgen/config_loader.py` - Configuration loader (may exist, needs extension)
5. `tests/test_hierarchical_agent.py` - Unit tests
6. `examples/hierarchical_example.py` - Usage examples
7. `configs/hierarchical_agent.yaml` - Configuration examples

**Modified Files:**

1. `massgen/tool/_base.py` - Extend ToolType enum
2. `massgen/tool/_manager.py` - Support registering agent tools
3. `massgen/chat_agent.py` - May need interface adjustments
4. `massgen/__init__.py` - Export new classes

---

## X. Summary

The core ideas of this design proposal are:

1. **Minimize invasiveness**: Leverage existing ChatAgent interface and tool system
2. **Maximize flexibility**: Support arbitrary hierarchy levels and combinations
3. **Maintain consistency**: Agents as tools are no different from other tools
4. **Easy configuration**: Easily define hierarchical structure through YAML config files

Through this proposal, you can achieve:
- ✅ Multi-level agent collaboration
- ✅ Specialized task division
- ✅ Flexible dynamic composition
- ✅ Seamless integration with existing system

---

This is the complete implementation proposal! The design enables hierarchical agent structures where agents can invoke other agents as tools, supporting arbitrary nesting levels and flexible configurations.
