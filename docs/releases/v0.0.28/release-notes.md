# MassGen v0.0.28 Release Notes

**Release Date:** October 6, 2025

---

## Overview

Version 0.0.28 introduces **AG2 Framework Integration**, enabling MassGen to orchestrate agents from external agent frameworks alongside native MassGen agents. This groundbreaking adapter architecture allows AG2 agents with code execution capabilities to collaborate with MassGen's multi-agent coordination system, opening the door for future integrations with other agent frameworks.

This release demonstrates MassGen's extensibility philosophy: any agent framework can be integrated through the adapter pattern, enabling unprecedented multi-framework agent collaboration.

---

## 🚀 What's New

### AG2 Framework Integration

The headline feature of v0.0.28 is complete **AG2 Framework Integration** through a flexible adapter system.

**Key Capabilities:**
- **External Framework Support:** Integrate agents from AG2 framework into MassGen workflows
- **Code Execution:** AG2 agents can execute Python code with multiple executor types
- **Multi-Framework Collaboration:** AG2 agents work alongside native MassGen agents (OpenAI, Claude, Gemini, etc.)
- **Extensible Architecture:** Adapter pattern designed for future framework integrations

**Implementation Details:**
- New `massgen/adapters/` module with base adapter architecture
- `base.py`: Abstract adapter interface for any agent framework
- `ag2_adapter.py`: AG2-specific implementation
- `ag2_utils.py`: AG2 agent setup and API key management utilities
- Support for AG2 ConversableAgent and AssistantAgent types

**AG2 Agent Types Supported:**
- **ConversableAgent:** General-purpose conversational agents
- **AssistantAgent:** Coding and task-oriented agents with tool/function calling

**Code Execution Capabilities:**
AG2 agents in MassGen support multiple code executor types:
- **LocalCommandLineCodeExecutor:** Execute code locally on the host machine
- **DockerCommandLineCodeExecutor:** Execute code in Docker containers for isolation
- **JupyterCodeExecutor:** Execute code in Jupyter notebooks
- **YepCodeCodeExecutor:** Cloud-based code execution

**Async Execution:**
- AG2 agents use `a_generate_reply` for autonomous async operation
- Seamless integration with MassGen's orchestration loop
- Proper handling of streaming responses and tool calls

**Configuration Example:**
```yaml
agents:
  - id: "ag2_coder"
    backend:
      type: ag2
      agent_config:
        type: assistant
        name: "AG2_Coder"
        system_message: |
          You are a helpful coding assistant.
          Write Python code in markdown blocks for automatic execution.
        llm_config:
          api_type: "openai"
          model: "gpt-4o"
        code_execution_config:
          executor:
            type: "LocalCommandLineCodeExecutor"
            timeout: 60
            work_dir: "./code_execution_workspace"

  - id: "gemini_agent"
    backend:
      type: "gemini"
      model: "gemini-2.5-pro"
```

**Try It Out:**
```bash
# Single AG2 agent with code execution
massgen --config @examples/ag2_ag2_coder \
  "Write a Python script to analyze CSV data and create visualizations"

# AG2 + Gemini hybrid collaboration
massgen --config @examples/ag2_ag2_coder_case_study \
  "Compare AG2 and MassGen frameworks, use code to fetch documentation"
```

---

### External Agent Backend

New **ExternalAgentBackend** class provides the foundation for integrating any external agent framework.

**Architecture:**
- **Adapter Registry Pattern:** Register framework-specific adapters
- **Unified Interface:** External agents work like native MassGen agents
- **Framework Detection:** Automatically selects appropriate adapter based on configuration
- **Configuration Validation:** Framework-specific config extraction and validation

**How It Works:**
```python
# MassGen automatically detects AG2 backend type
backend:
  type: ag2  # Triggers ExternalAgentBackend with AG2Adapter
  agent_config:
    # AG2-specific configuration
```

**Extensibility:**
Future framework integrations (LangChain, CrewAI, etc.) can follow the same pattern:
1. Implement adapter inheriting from base adapter
2. Register adapter in ExternalAgentBackend
3. Provide framework-specific configuration schema

**Benefits:**
- **Unified Orchestration:** MassGen orchestrates all agents regardless of source framework
- **Framework Strengths:** Leverage unique capabilities of each framework
- **Gradual Migration:** Mix agents from different frameworks in same workflow
- **Future-Proof:** Easy to add new framework integrations

---

### AG2 Test Suite

Comprehensive test coverage ensures reliable AG2 integration.

**Test Files:**
- `test_ag2_adapter.py`: AG2 adapter functionality tests
- `test_agent_adapter.py`: Base adapter interface tests
- `test_external_agent_backend.py`: External backend integration tests

**Test Coverage:**
- AG2 agent initialization and configuration
- Message passing between MassGen and AG2 agents
- Code execution workflow
- Error handling and edge cases
- Adapter registry pattern
- Configuration validation

**Quality Assurance:**
- All tests passing in CI/CD pipeline
- Integration tests with real AG2 agents
- Mock tests for faster unit testing
- Coverage for both ConversableAgent and AssistantAgent types

---

### MCP Circuit Breaker Enhancements

**Improved MCP Server Initialization:**
- Enhanced circuit breaker state management in `base_with_mcp.py`
- Better error handling during MCP server startup
- More resilient initialization logic
- Graceful degradation when MCP servers fail to initialize

**Benefits:**
- Fewer MCP initialization failures
- Better error messages for debugging
- More robust multi-MCP setups
- Improved reliability in production environments

---

## 📦 New Configurations

### AG2 Configuration Examples (4)

Located in `massgen/configs/ag2/`:

1. **ag2_single_agent.yaml**
   - Basic single AG2 agent setup
   - ConversableAgent with simple configuration
   - Use Case: Learning AG2 integration basics
   - Example: "Explain how neural networks work"

2. **ag2_coder.yaml**
   - AG2 AssistantAgent with code execution
   - LocalCommandLineCodeExecutor for running Python code
   - Use Case: Coding tasks requiring execution
   - Example: "Create a data analysis script and run it"

3. **ag2_coder_case_study.yaml**
   - Multi-agent: AG2 coder + Gemini agent
   - Demonstrates AG2 + MassGen native agent collaboration
   - Use Case: Complex tasks requiring code execution + web search
   - Example: "Compare AG2 vs MassGen by fetching and analyzing their docs"

4. **ag2_gemini.yaml**
   - AG2-Gemini hybrid configuration
   - Shows framework integration patterns
   - Use Case: Combining AG2's code execution with Gemini's capabilities

**Quick Start:**
```bash
# Basic AG2 agent
massgen --config @examples/ag2_ag2_single_agent \
  "Your task"

# AG2 with code execution
massgen --config @examples/ag2_ag2_coder \
  "Write and execute a web scraping script"

# AG2 + Gemini collaboration
massgen --config @examples/ag2_ag2_gemini \
  "Complex task requiring multiple capabilities"
```

---

## 🔧 What Changed

### New Adapters Module

**Structure:**
```
massgen/
├── adapters/
│   ├── __init__.py
│   ├── base.py              # Abstract adapter interface
│   ├── ag2_adapter.py       # AG2-specific implementation
│   └── utils/
│       ├── __init__.py
│       └── ag2_utils.py     # AG2 utilities
```

**Base Adapter Interface:**
- `initialize()`: Set up framework-specific agent
- `generate_response()`: Get response from agent
- `validate_config()`: Validate framework configuration
- Extensible for future frameworks

**AG2 Adapter:**
- Handles AG2 ConversableAgent and AssistantAgent
- Manages code execution configuration
- Bridges AG2's async API with MassGen's orchestration
- Proper error handling and logging

---

## 📚 Documentation Updates

### Enhanced Documentation

- **MULTI_SOURCE_AGENT_INTEGRATION_DESIGN.md:** Updated with AG2 adapter architecture
- **AG2 Integration Guide:** Configuration examples and best practices
- **README.md:** AG2 integration mentioned in features

### Design Documentation

The design doc provides:
- Architecture overview of adapter pattern
- Sequence diagrams for agent interaction
- Configuration schema documentation
- Future framework integration guidelines

---

## 📊 Technical Details

### Statistics

- **Commits:** 12 commits
- **Files Modified:** 18 files
- **Insertions:** 1,423 lines
- **Deletions:** 71 lines
- **New Module:** `massgen/adapters/`
- **New Tests:** 3 test files

### Major Components Changed

1. **Adapters Module:** New adapter architecture
2. **Backend System:** ExternalAgentBackend class
3. **Test Suite:** Comprehensive AG2 integration tests
4. **Configuration:** 4 new AG2 example configs
5. **Documentation:** Design doc updates

### Code Quality

- Full type hints in adapter module
- Comprehensive error handling
- Async/await patterns properly implemented
- Test coverage for all major paths

---

## 🎯 Use Cases

### When to Use AG2 Agents

**✅ Use AG2 Agents When:**
- You need code execution capabilities
- Working with existing AG2 agent configurations
- Leveraging AG2's tool/function calling
- Requiring specific AG2 executor types (Docker, Jupyter)
- Gradually migrating from AG2 to MassGen

**✅ Use AG2 + MassGen Native Agents When:**
- Combining code execution with other capabilities (web search, MCP tools)
- Need multi-model diversity (AG2 coder + Gemini analyst + Claude reviewer)
- Leveraging strengths of both frameworks
- Complex workflows requiring different agent types

### Example Workflows

**Data Analysis:**
```bash
# AG2 agent fetches data, writes analysis code, executes it
# Gemini agent interprets results and writes report
massgen --config @examples/ag2_ag2_coder_case_study \
  "Analyze NYC taxi data: fetch, process, visualize trends"
```

**Web Research + Automation:**
```bash
# AG2 agent scrapes web, processes data with code
# MassGen agents analyze and synthesize findings
massgen --config @examples/ag2_ag2_gemini \
  "Research AI safety papers from last 6 months, summarize key findings"
```

**Code Generation + Review:**
```yaml
agents:
  - id: "ag2_coder"     # Writes and tests code
    backend:
      type: ag2
      # ... code execution config

  - id: "claude_reviewer"  # Reviews code quality
    backend:
      type: "claude"

  - id: "gemini_docs"   # Writes documentation
    backend:
      type: "gemini"
```

---

## 🚀 Migration Guide

### Upgrading from v0.0.27

**No Breaking Changes**

v0.0.28 is fully backward compatible with v0.0.27. All existing configurations will continue to work.

**Optional: Add AG2 Agents**

To use AG2 agents in your workflow:

1. **Install AG2 (optional dependency):**
```bash
pip install ag2  # or uv pip install ag2
```

2. **Add AG2 agent to your configuration:**
```yaml
agents:
  - id: "my_ag2_agent"
    backend:
      type: ag2
      agent_config:
        type: assistant
        name: "MyAgent"
        llm_config:
          api_type: "openai"
          model: "gpt-4o"
        code_execution_config:
          executor:
            type: "LocalCommandLineCodeExecutor"
            work_dir: "./workspace"
```

3. **Mix with existing agents:**
```yaml
agents:
  - id: "ag2_coder"
    backend:
      type: ag2
      # AG2 config...

  - id: "existing_gemini"
    backend:
      type: "gemini"
      model: "gemini-2.5-pro"
```

---

## 🤝 Contributors

Special thanks to all contributors who made v0.0.28 possible:

- @Eric-Shang
- @praneeth999
- @qidanrui
- @sonichi
- @Henry-811
- And the entire MassGen team

---

## 🔗 Resources

- **CHANGELOG:** [CHANGELOG.md](../../../CHANGELOG.md#0028---2025-10-06)
- **Case Study:** [case-study.md](case-study.md)
- **Features Overview:** [features-overview.md](features-overview.md)
- **Design Doc:** [MULTI_SOURCE_AGENT_INTEGRATION_DESIGN.md](../../../MULTI_SOURCE_AGENT_INTEGRATION_DESIGN.md)
- **AG2 GitHub:** https://github.com/ag2ai/ag2
- **AG2 Documentation:** https://docs.ag2.ai/

---

## 🔮 What's Next

See the [v0.0.29 Release](../v0.0.29/release-notes.md) for what came after, including:
- **MCP Planning Mode** - Coordinate without executing irreversible actions
- **FileOperationTracker** - Read-before-delete enforcement
- **Enhanced MCP Tool Filtering** - Multi-level tool control

---

## 💡 Future Framework Integrations

The adapter architecture introduced in v0.0.28 paves the way for:

**Potential Future Integrations:**
- **LangChain:** Agent and chain integrations
- **CrewAI:** Role-based agent collaboration
- **AutoGPT:** Autonomous agent capabilities
- **BabyAGI:** Task decomposition agents
- **Custom Frameworks:** Your own agent framework

**Integration Pattern:**
1. Implement adapter inheriting from `BaseAdapter`
2. Add framework-specific configuration schema
3. Register in `ExternalAgentBackend`
4. Provide example configurations
5. Add test suite

---

*Released with ❤️ by the MassGen team*
