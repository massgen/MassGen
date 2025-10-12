# AG2 Integration

**Introduced in:** v0.0.28 (October 2025)

MassGen integrates with AG2 framework, enabling AG2 agents with code execution capabilities to collaborate with native MassGen agents. This integration demonstrates MassGen's extensibility philosophy: any agent framework can be integrated through the adapter pattern.

## What is AG2 Integration?

AG2 Integration allows you to:
- **Use AG2 Agents:** Deploy AG2 ConversableAgent and AssistantAgent types within MassGen
- **Execute Code:** AG2 agents can write and execute Python code with multiple executor types
- **Mix Frameworks:** Combine AG2 agents with native MassGen agents (OpenAI, Claude, Gemini, etc.)
- **Leverage Strengths:** Use AG2's code execution with MassGen's multi-agent coordination

**Key Benefits:**
- Access to AG2's mature code execution capabilities
- Seamless integration with MassGen orchestration
- Multi-framework agent collaboration
- Gradual migration path from AG2 to MassGen or vice versa

## Key Capabilities

### 1. Code Execution

AG2 agents can execute Python code through multiple executor types:

**LocalCommandLineCodeExecutor** (Most Common)
- Executes code locally on host machine
- Fast and simple setup
- No dependencies required
```yaml
code_execution_config:
  executor:
    type: "LocalCommandLineCodeExecutor"
    timeout: 60
    work_dir: "./code_execution_workspace"
```

**DockerCommandLineCodeExecutor**
- Executes code in Docker containers
- Isolated execution environment
- Enhanced security
```yaml
code_execution_config:
  executor:
    type: "DockerCommandLineCodeExecutor"
    timeout: 120
    image: "python:3.11-slim"
```

**JupyterCodeExecutor**
- Executes code in Jupyter notebooks
- Interactive code sessions
- Persistent kernel state
```yaml
code_execution_config:
  executor:
    type: "JupyterCodeExecutor"
    timeout: 90
```

**YepCodeCodeExecutor**
- Cloud-based code execution
- Serverless execution model
- No local setup required

### 2. Agent Types

**ConversableAgent**
- General-purpose conversational agent
- Supports tool/function calling
- No code execution by default
```yaml
agent_config:
  type: "conversable"
  name: "MyConversableAgent"
  system_message: "You are a helpful assistant."
```

**AssistantAgent**
- Task-oriented coding agent
- Built-in code execution support
- Designed for programming tasks
```yaml
agent_config:
  type: "assistant"
  name: "MyAssistantAgent"
  system_message: "You are a coding assistant."
```

### 3. Multi-Framework Collaboration

AG2 agents work seamlessly with native MassGen agents:

```yaml
agents:
  - id: "ag2_coder"
    backend:
      type: ag2
      agent_config:
        type: assistant
        # AG2-specific config

  - id: "gemini_analyst"
    backend:
      type: "gemini"
      model: "gemini-2.5-pro"
      enable_web_search: true

  - id: "claude_reviewer"
    backend:
      type: "claude"
      model: "claude-sonnet-4-20250514"
```

**Collaboration Patterns:**
- AG2 agent writes and executes code
- Gemini agent performs web research
- Claude agent reviews and synthesizes

## Configuration Guide

### Basic AG2 Agent Configuration

Minimal AG2 agent setup:

```yaml
agents:
  - id: "ag2_assistant"
    backend:
      type: ag2
      agent_config:
        type: assistant
        name: "AG2_Assistant"
        system_message: "You are a helpful AI assistant powered by AG2."
        llm_config:
          api_type: "openai"
          model: "gpt-4o"
          temperature: 0.7
          cache_seed: 42
```

**Configuration Example:** [`ag2_single_agent.yaml`](../../massgen/configs/ag2/ag2_single_agent.yaml)

### AG2 Agent with Code Execution

Full configuration with code execution:

```yaml
agents:
  - id: "ag2_coder"
    backend:
      type: ag2
      agent_config:
        type: assistant
        name: "AG2_Coder"
        system_message: |
          You are a helpful coding assistant. When asked to create and run code:
          1. Write Python code in a markdown code block (```python ... ```)
          2. The code will be automatically executed
          3. Always print the results so they are visible
        llm_config:
          api_type: "openai"
          model: "gpt-5"
        code_execution_config:
          executor:
            type: "LocalCommandLineCodeExecutor"
            timeout: 60
            work_dir: "./code_execution_workspace"
```

**Configuration Example:** [`ag2_coder.yaml`](../../massgen/configs/ag2/ag2_coder.yaml)

### AG2 + Native MassGen Agent

Multi-agent configuration mixing AG2 and MassGen agents:

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
          Write Python code for data fetching and processing.
        llm_config:
          api_type: "openai"
          model: "gpt-5"
        code_execution_config:
          executor:
            type: "LocalCommandLineCodeExecutor"
            timeout: 60
            work_dir: "./code_execution_workspace"

  - id: "gemini_analyst"
    backend:
      type: "gemini"
      model: "gemini-2.5-pro"
      enable_web_search: true

ui:
  type: "rich_terminal"
  logging_enabled: true
```

**Configuration Example:** [`ag2_coder_case_study.yaml`](../../massgen/configs/ag2/ag2_coder_case_study.yaml)

### AG2 with Claude Backend

AG2 agent using Claude models:

```yaml
agents:
  - id: "ag2_assistant"
    backend:
      type: ag2
      agent_config:
        type: assistant
        name: "AG2_Assistant"
        system_message: "You are a helpful AI assistant powered by AG2."
        llm_config:
          - api_type: "anthropic"
            model: "claude-sonnet-4-20250514"
            temperature: 0.7
            cache_seed: 42

  - id: "gemini2.5flash"
    backend:
      type: "gemini"
      model: "gemini-2.5-flash"
      enable_web_search: true
```

**Configuration Example:** [`ag2_gemini.yaml`](../../massgen/configs/ag2/ag2_gemini.yaml)

## Configuration Parameters

### Required Parameters

**`type: ag2`**
- Specifies AG2 backend
- Triggers ExternalAgentBackend with AG2Adapter
```yaml
backend:
  type: ag2
```

**`agent_config`**
- AG2-specific agent configuration
- Contains agent type, name, and settings
```yaml
agent_config:
  type: "assistant"  # or "conversable"
  name: "AgentName"
```

**`llm_config`**
- LLM backend configuration for AG2 agent
- Supports OpenAI, Anthropic, etc.
```yaml
llm_config:
  api_type: "openai"    # or "anthropic"
  model: "gpt-4o"
  temperature: 0.7
  cache_seed: 42
```

### Optional Parameters

**`system_message`**
- Custom instructions for the AG2 agent
- Guides agent behavior
```yaml
system_message: |
  You are a specialized coding assistant.
  Always include error handling in your code.
```

**`code_execution_config`**
- Code execution settings
- Only for agents that need to run code
```yaml
code_execution_config:
  executor:
    type: "LocalCommandLineCodeExecutor"
    timeout: 60
    work_dir: "./workspace"
```

**`temperature`**
- Controls response randomness (0.0 to 1.0)
- Lower = more deterministic
```yaml
llm_config:
  temperature: 0.7  # Balanced creativity
```

**`cache_seed`**
- Seed for response caching
- Set to integer for consistent caching
```yaml
llm_config:
  cache_seed: 42
```

## Supported LLM Backends

AG2 agents can use different LLM backends through `llm_config`:

### OpenAI

```yaml
llm_config:
  api_type: "openai"
  model: "gpt-5"         # or gpt-4o, gpt-5-nano, etc.
  temperature: 0.7
```

**Supported Models:**
- `gpt-5`
- `gpt-5-nano`
- `gpt-4o`
- `gpt-4o-mini`
- `o4`
- `o4-mini`

### Anthropic Claude

```yaml
llm_config:
  api_type: "anthropic"
  model: "claude-sonnet-4-20250514"
  temperature: 0.7
```

**Supported Models:**
- `claude-sonnet-4-20250514`
- `claude-3-5-sonnet-20241022`
- `claude-3-7-sonnet-20250219`
- `claude-3-5-haiku-20241022`
- `claude-opus-4-20250514`

## When to Use AG2 Agents

### Use AG2 Agents When:

✅ **Code Execution Required**
- Data analysis and visualization
- Web scraping and data processing
- Algorithm implementation and testing
- File manipulation and processing

✅ **Existing AG2 Configurations**
- Migrating from pure AG2 setup
- Leveraging existing AG2 agents
- Gradually adopting MassGen

✅ **Specific Executor Types Needed**
- Docker isolation required
- Jupyter notebook integration
- Cloud-based execution (YepCode)

✅ **Tool/Function Calling**
- AG2's mature function calling system
- Existing AG2 tool definitions
- Complex tool orchestration

### Use Native MassGen Agents When:

✅ **MCP Integration Required**
- Discord, Notion, Twitter integrations
- Custom MCP servers
- External tool access

✅ **Web Search Capabilities**
- Gemini native web search
- OpenAI web search (GPT models)
- Grok web search

✅ **Native Filesystem Operations**
- Claude Code filesystem tools
- Gemini filesystem MCP
- Workspace isolation features

✅ **Planning Mode Coordination**
- Multi-agent coordination with MCP
- Preventing duplicate actions
- Separation of planning and execution

### Use Hybrid (AG2 + MassGen) When:

✅ **Combining Capabilities**
- Code execution + web search
- Code execution + MCP tools
- Multiple specialized capabilities

✅ **Multi-Model Diversity**
- Leveraging different model strengths
- Balanced voting and consensus
- Specialized role assignment

## Working Examples

### Example 1: Simple Code Execution

**Configuration:** [`ag2_coder.yaml`](../../massgen/configs/ag2/ag2_coder.yaml)

**Task:**
```bash
uv run python -m massgen.cli \
  --config massgen/configs/ag2/ag2_coder.yaml \
  "Create a factorial function and calculate the factorial of 8. Show the result?"
```

**What Happens:**
1. AG2 agent writes Python factorial function
2. Code is automatically executed in workspace
3. Result is displayed and returned
4. Workspace files are preserved for inspection

**Use Case:**
- Learning AG2 integration basics
- Simple coding tasks with immediate execution
- Mathematical computations
- Algorithm testing

### Example 2: Data Analysis

**Configuration:** [`ag2_coder.yaml`](../../massgen/configs/ag2/ag2_coder.yaml)

**Task:**
```bash
uv run python -m massgen.cli \
  --config massgen/configs/ag2/ag2_coder.yaml \
  "Load iris.csv dataset, perform statistical analysis, and create visualizations"
```

**What Happens:**
1. AG2 agent writes data loading code
2. Performs statistical analysis (mean, std, correlations)
3. Creates matplotlib/seaborn visualizations
4. Saves plots to workspace
5. Returns analysis summary

**Use Case:**
- Data science workflows
- Statistical analysis
- Data visualization
- Exploratory data analysis

### Example 3: Multi-Framework Collaboration

**Configuration:** [`ag2_coder_case_study.yaml`](../../massgen/configs/ag2/ag2_coder_case_study.yaml)

**Task:**
```bash
uv run python -m massgen.cli \
  --config massgen/configs/ag2/ag2_coder_case_study.yaml \
  "Compare AG2 and MassGen frameworks: fetch documentation, analyze differences"
```

**What Happens:**
1. **AG2 agent:**
   - Writes web scraping code
   - Fetches AG2 and MassGen documentation
   - Extracts key information
   - Processes and structures data

2. **Gemini agent:**
   - Uses native web search
   - Gathers additional context
   - Cross-validates information
   - Provides analysis

3. **Coordination:**
   - Both agents share findings
   - MassGen orchestrates consensus
   - Combined insights produced

**Use Case:**
- Complex research tasks
- Multi-capability requirements
- Combining code execution with web search
- Framework comparisons

### Example 4: Claude-Powered AG2 Agent

**Configuration:** [`ag2_gemini.yaml`](../../massgen/configs/ag2/ag2_gemini.yaml)

**Task:**
```bash
uv run python -m massgen.cli \
  --config massgen/configs/ag2/ag2_gemini.yaml \
  "Explain quantum computing principles with code examples"
```

**What Happens:**
1. **AG2 agent (Claude backend):**
   - Provides detailed quantum computing explanation
   - Uses Claude's reasoning capabilities
   - Structured, comprehensive response

2. **Gemini agent:**
   - Performs web search for latest research
   - Validates explanations
   - Adds current context

**Use Case:**
- Leveraging Claude's reasoning in AG2
- Multi-model perspectives
- Complex explanations
- Educational content

## Code Execution Workflow

### How Code Execution Works

1. **Code Detection:**
   - AG2 agent writes code in markdown blocks
   - Format: ` ```python ... ``` `
   - Automatically detected by AG2

2. **Execution:**
   - Code extracted from markdown
   - Executed in configured executor
   - Timeout enforced (default: 60s)

3. **Output Capture:**
   - STDOUT captured
   - STDERR captured
   - Exit code recorded

4. **Result Integration:**
   - Output returned to agent
   - Agent can see execution results
   - Can iterate based on results

### Workspace Management

**Workspace Directory:**
- Configured in `code_execution_config.executor.work_dir`
- Persistent across executions within same session
- Files can be accessed by subsequent code

**Example:**
```yaml
code_execution_config:
  executor:
    type: "LocalCommandLineCodeExecutor"
    work_dir: "./code_execution_workspace"
```

**Benefits:**
- File persistence between executions
- Multi-step data pipelines
- Result inspection after execution
- Debugging capabilities

### Timeout Configuration

**Purpose:**
- Prevents infinite loops
- Limits resource usage
- Ensures responsiveness

**Configuration:**
```yaml
code_execution_config:
  executor:
    timeout: 60  # seconds
```

**Recommendations:**
- Quick scripts: 30-60 seconds
- Data processing: 120-300 seconds
- ML training: 600+ seconds
- Web scraping: 120-180 seconds

## Architecture

### Adapter Pattern

MassGen uses an adapter architecture for external frameworks:

```
MassGen Orchestrator
        ↓
ExternalAgentBackend
        ↓
    AG2Adapter
        ↓
  AG2 Framework
  (ConversableAgent/AssistantAgent)
```

**Components:**

**BaseAdapter** (`massgen/adapters/base.py`)
- Abstract interface for all framework adapters
- Defines common methods: `initialize()`, `generate_response()`
- Extensible for future frameworks (LangChain, CrewAI, etc.)

**AG2Adapter** (`massgen/adapters/ag2_adapter.py`)
- AG2-specific implementation
- Handles AG2 agent initialization
- Manages code execution configuration
- Bridges AG2's async API with MassGen

**ExternalAgentBackend** (`massgen/backends/external_agent_backend.py`)
- Detects framework type from configuration
- Selects appropriate adapter
- Validates framework-specific config
- Provides unified interface to orchestrator

### Message Flow

1. **User Query** → MassGen Orchestrator
2. **Orchestrator** → Distributes to agents (AG2 + native)
3. **ExternalAgentBackend** → Routes to AG2Adapter
4. **AG2Adapter** → Calls `agent.a_generate_reply(messages)`
5. **AG2 Agent** → Generates response (may include code execution)
6. **Response** → Back through chain to orchestrator
7. **Orchestrator** → Collects all agent responses
8. **Consensus** → Voting/aggregation across all agents

### Async Execution

AG2 agents use async execution:
```python
result = await self.agent.a_generate_reply(messages)
```

**Benefits:**
- Non-blocking execution
- Parallel agent processing
- Efficient resource usage
- Responsive orchestration

## Tool and Function Calling

### AG2 Tool Support

AG2 agents support OpenAI function calling format:

```yaml
# MassGen automatically passes tools to AG2 agents
# Tools are registered using update_tool_signature()
```

**How It Works:**
1. MassGen orchestrator provides tools
2. AG2Adapter registers tools with AG2 agent
3. AG2 agent can call tools during execution
4. Tool results returned to agent for further processing

**Current Status:**
- ✅ Single agent tool registration
- ✅ OpenAI function format compatibility
- ⏳ GroupChat tool registration (coming soon)
- ⏳ MCP tool integration (planned)

### Future: AG2 + MCP Tools

**Planned Integration:**
AG2 agents will be able to access MCP tools through MassGen:

```yaml
agents:
  - id: "ag2_coder"
    backend:
      type: ag2
      agent_config:
        # AG2 config
      mcp_servers:  # Future: MCP for AG2 agents
        - name: "discord"
          type: "stdio"
          # MCP config
```

**Benefits:**
- AG2 code execution + MCP external tools
- Discord, Notion, Twitter access from AG2 agents
- Unified tool ecosystem across frameworks

## Troubleshooting

### AG2 Not Installed

**Error:**
```
ModuleNotFoundError: No module named 'autogen'
```

**Solution:**
Install AG2 framework:
```bash
uv pip install ag2
# or
pip install ag2
```

### Code Execution Fails

**Error:**
```
Code execution failed: timeout
```

**Solutions:**
1. Increase timeout:
```yaml
code_execution_config:
  executor:
    timeout: 120  # Increase from 60
```

2. Check code for infinite loops
3. Verify workspace permissions
4. Check available disk space

### Workspace Directory Not Found

**Error:**
```
FileNotFoundError: [Errno 2] No such file or directory: './code_execution_workspace'
```

**Solution:**
Create workspace directory or use absolute path:
```yaml
code_execution_config:
  executor:
    work_dir: "/absolute/path/to/workspace"
```

Or let AG2 create it:
```bash
mkdir -p ./code_execution_workspace
```

### API Key Issues

**Error:**
```
Authentication failed
```

**Solutions:**
Ensure correct API keys in `.env`:
```bash
# For OpenAI backend
OPENAI_API_KEY="your_key"

# For Anthropic backend
ANTHROPIC_API_KEY="your_key"
```

### Agent Not Responding

**Debugging Steps:**

1. **Enable logging:**
```yaml
ui:
  logging_enabled: true
```

2. **Check AG2 agent initialization:**
```bash
# Look for AG2Adapter logs
uv run python -m massgen.cli --config your_config.yaml --verbose
```

3. **Verify LLM config:**
```yaml
llm_config:
  api_type: "openai"  # Check spelling
  model: "gpt-4o"     # Verify model exists
```

4. **Test with simple query:**
```bash
uv run python -m massgen.cli \
  --config massgen/configs/ag2/ag2_single_agent.yaml \
  "Hello, are you working?"
```

## Performance Considerations

### Code Execution Overhead

**Execution Time:**
- LocalCommandLineCodeExecutor: Fast (< 1s overhead)
- DockerCommandLineCodeExecutor: Slower (1-3s overhead for container)
- JupyterCodeExecutor: Medium (kernel startup time)

**Recommendations:**
- Use LocalCommandLineCodeExecutor for quick iterations
- Use Docker for security-critical applications
- Use Jupyter for interactive, stateful sessions

### Memory Usage

**AG2 Agent Memory:**
- ConversableAgent: ~50-100 MB
- AssistantAgent with code execution: ~100-200 MB
- Docker executor adds container overhead: ~100-500 MB

**Optimization:**
- Limit workspace file sizes
- Clean up workspace between sessions
- Use timeout to prevent runaway processes

### Response Time

**Typical Latencies:**
- Simple response (no code): 2-5 seconds
- Code execution: 5-30 seconds (depends on code complexity)
- Multi-agent coordination: 10-60 seconds (parallel execution)

## Best Practices

### 1. Clear System Messages

Guide AG2 agents with explicit instructions:

```yaml
system_message: |
  You are a coding assistant specializing in data analysis.

  When writing code:
  1. Write Python code in markdown blocks (```python ... ```)
  2. Always print results so they are visible
  3. Include error handling (try/except)
  4. Add comments explaining key steps
  5. Use clear variable names

  For data analysis:
  - Load data with pandas
  - Perform statistical analysis
  - Create visualizations with matplotlib
  - Save plots to workspace
```

### 2. Appropriate Timeout

Set timeout based on expected task duration:

```yaml
# Quick scripts
timeout: 30

# Data processing
timeout: 120

# ML training
timeout: 600
```

### 3. Workspace Organization

Use descriptive workspace names:

```yaml
work_dir: "./workspaces/data_analysis_session_1"
```

Clean up after sessions:
```bash
rm -rf ./code_execution_workspace/*
```

### 4. Model Selection

Choose appropriate models:

**For Code Generation:**
- `gpt-5` - Best code quality
- `gpt-4o` - Balanced performance
- `claude-sonnet-4-20250514` - Strong reasoning

**For Quick Tasks:**
- `gpt-5-nano` - Fast, cost-effective
- `gpt-4o-mini` - Good balance

### 5. Multi-Framework Mixing

Assign specialized roles:

```yaml
agents:
  # AG2: Code execution
  - id: "ag2_coder"
    backend:
      type: ag2
      # Focus on code generation and execution

  # Gemini: Web research
  - id: "gemini_researcher"
    backend:
      type: "gemini"
      enable_web_search: true

  # Claude: Analysis and synthesis
  - id: "claude_analyst"
    backend:
      type: "claude"
      # Focus on reasoning and synthesis
```

### 6. Error Handling

Include error handling in system messages:

```yaml
system_message: |
  Always include try/except blocks in your code:

  ```python
  try:
      # Your code here
      result = process_data()
      print(f"Success: {result}")
  except Exception as e:
      print(f"Error: {str(e)}")
  ```
```

## Available Configurations

All 4 AG2 configurations are located in [`massgen/configs/ag2/`](../../massgen/configs/ag2/):

| Configuration | Description | Use Case |
|--------------|-------------|----------|
| [`ag2_single_agent.yaml`](../../massgen/configs/ag2/ag2_single_agent.yaml) | Basic single AG2 agent | Learning AG2 integration |
| [`ag2_coder.yaml`](../../massgen/configs/ag2/ag2_coder.yaml) | AG2 with code execution | Coding tasks with execution |
| [`ag2_coder_case_study.yaml`](../../massgen/configs/ag2/ag2_coder_case_study.yaml) | AG2 + Gemini hybrid | Multi-capability tasks |
| [`ag2_gemini.yaml`](../../massgen/configs/ag2/ag2_gemini.yaml) | AG2 (Claude) + Gemini | Multi-model collaboration |

## Comparison: AG2 vs Native MassGen Agents

| Feature | AG2 Agents | Native MassGen Agents |
|---------|-----------|---------------------|
| **Code Execution** | ✅ Multiple executors | ❌ Use AG2 for code |
| **MCP Integration** | ⏳ Planned | ✅ Full support |
| **Web Search** | ❌ Use native agents | ✅ Gemini, OpenAI, Grok |
| **Filesystem Tools** | ❌ Use native agents | ✅ Claude Code, Gemini MCP |
| **Planning Mode** | ✅ Participates | ✅ Full support |
| **Tool Calling** | ✅ OpenAI format | ✅ OpenAI format |
| **Docker Execution** | ✅ Built-in | ❌ Use AG2 |
| **Jupyter Integration** | ✅ Built-in | ❌ Use AG2 |
| **Framework Lock-in** | Medium (AG2 specific) | None (MassGen native) |
| **Setup Complexity** | Medium (AG2 + MassGen) | Low (MassGen only) |

**When to Mix Both:**
- Code execution + Web search
- Code execution + MCP tools
- Multi-model diversity
- Specialized capabilities

## Future Enhancements

### Planned Features

**GroupChat Support** (Coming Soon)
- Multi-agent conversations within AG2
- AG2's pattern-based orchestration
- Integration with MassGen coordination

**MCP Tool Access for AG2 Agents** (Planned)
- AG2 agents access Discord, Notion, etc.
- Unified tool ecosystem
- Code execution + external tools

**Additional Framework Integrations** (Roadmap)
- LangChain adapter
- CrewAI adapter
- AutoGPT adapter
- Custom framework support

**Enhanced Code Execution** (Under Consideration)
- Streaming code execution output
- Live code cell updates
- Interactive debugging
- Breakpoint support

## Related Documentation

- **[Backend Support](./backend-support.md)** - All supported backends including AG2
- **[Configuration Guide](./configuration-guide.md)** - AG2 config patterns
- **[Multi-Agent Coordination](./multi-agent-coordination.md)** - How AG2 agents coordinate
- **[v0.0.28 Release Notes](../releases/v0.0.28/release-notes.md)** - AG2 integration details

## Resources

- **AG2 GitHub:** https://github.com/ag2ai/ag2
- **AG2 Documentation:** https://docs.ag2.ai/
- **MassGen Design Doc:** [MULTI_SOURCE_AGENT_INTEGRATION_DESIGN.md](../../MULTI_SOURCE_AGENT_INTEGRATION_DESIGN.md)
- **Case Study:** [v0.0.28 Case Study](../releases/v0.0.28/case-study.md)

---

**Last Updated:** October 2025 | **MassGen Version:** v0.0.28+
