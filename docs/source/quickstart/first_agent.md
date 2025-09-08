# Creating Your First Agent

This guide will walk you through creating and running your first MassGen agent, from simple single-agent setups to powerful multi-agent collaborations.

## Single Agent Quick Start

### Basic Command

The simplest way to start is with a single agent using the command line:

```bash
# Using Claude
uv run python -m massgen.cli --model claude-3-5-sonnet-latest "What is machine learning?"

# Using Gemini
uv run python -m massgen.cli --model gemini-2.5-flash "Explain quantum computing"

# Using GPT
uv run python -m massgen.cli --model gpt-5-nano "How does blockchain work?"
```

### Understanding the Output

When you run a single agent, you'll see:

1. **Initialization**: Agent loading and configuration
2. **Processing**: The agent thinking through your query
3. **Response**: The final answer with formatting

Example output:
```
🚀 Initializing MassGen...
📋 Loading agent: claude-3-5-sonnet-latest
💭 Processing query...

Machine learning is a subset of artificial intelligence that enables 
computers to learn and improve from experience without being explicitly 
programmed...
```

## Multi-Agent Collaboration

### Using Configuration Files

For multi-agent setups, use YAML configuration files:

```bash
# Three agents working together
uv run python -m massgen.cli --config three_agents_default.yaml "Design a sustainable city"
```

### Creating Your First Configuration

Create a file `my_first_team.yaml`:

```yaml
# Simple two-agent configuration
agents:
  - id: "Research Expert"
    backend:
      type: "gemini"
      model: "gemini-2.5-flash"
    system_message: "You are a research expert. Focus on finding accurate information."
    
  - id: "Creative Writer"  
    backend:
      type: "claude"
      model: "claude-3-5-sonnet-latest"
    system_message: "You are a creative writer. Focus on clear, engaging explanations."

ui:
  display_type: "rich_terminal"
  logging_enabled: true
```

Run your configuration:
```bash
uv run python -m massgen.cli --config my_first_team.yaml "Write about renewable energy"
```

## Interactive Mode

Start an interactive conversation with agents:

```bash
# Single agent interactive mode
uv run python -m massgen.cli --model gpt-5-mini

# Multi-agent interactive mode
uv run python -m massgen.cli --config three_agents_default.yaml
```

Commands in interactive mode:
- Type your questions naturally
- `/clear` - Clear conversation history
- `/quit` or `/exit` - Exit the session
- `Ctrl+C` - Force exit

## Adding Tools and Capabilities

### Web Search

Enable web search for informed responses:

```yaml
agents:
  - id: "Research Assistant"
    backend:
      type: "gemini"
      model: "gemini-2.5-flash"
      enable_web_search: true
    system_message: "Research current events and provide accurate information."
```

### Code Execution

Enable code execution for technical tasks:

```yaml
agents:
  - id: "Code Expert"
    backend:
      type: "claude"
      model: "claude-3-5-sonnet-latest"
      enable_code_execution: true
    system_message: "Write and test code solutions."
```

### File Operations (Claude Code)

Use Claude Code for file manipulation:

```bash
# Direct CLI usage
uv run python -m massgen.cli --backend claude_code "Create a Python web server"

# In configuration
agents:
  - id: "Developer"
    backend:
      type: "claude_code"
      cwd: "my_workspace"
```

## Understanding Agent Collaboration

### How Agents Work Together

1. **Parallel Processing**: All agents receive the task simultaneously
2. **Information Sharing**: Agents see each other's progress in real-time
3. **Iterative Refinement**: Agents can restart and improve based on others' insights
4. **Consensus Building**: The system identifies when agents converge on a solution

### Visualization

Watch agents collaborate in real-time:

```yaml
ui:
  display_type: "rich_terminal"  # Full visualization
  # or "terminal" for simpler display
  # or "simple" for basic text output
```

## Examples by Use Case

### Research Task

```bash
# Multiple agents research a topic
uv run python -m massgen.cli --config research_team.yaml \
  "What are the latest breakthroughs in quantum computing?"
```

### Creative Writing

```bash
# Collaborative story writing
uv run python -m massgen.cli --config creative_team.yaml \
  "Write a short story about AI discovering consciousness"
```

### Code Development

```bash
# Multi-agent code review and optimization
uv run python -m massgen.cli --config claude_code_flash2.5.yaml \
  "Create a REST API with authentication"
```

### Data Analysis

```bash
# Analyze and visualize data
uv run python -m massgen.cli --config technical_analysis.yaml \
  "Analyze this CSV data and create visualizations"
```

## Best Practices

### 1. Choose the Right Models

- **Fast responses**: Use `gemini-2.5-flash`, `gpt-5-nano`
- **Complex reasoning**: Use `claude-3-5-sonnet`, `gpt-5`
- **Creative tasks**: Use `claude-3-5-sonnet`, `gemini-2.5-pro`
- **Code tasks**: Use `claude_code` backend

### 2. Optimize System Messages

Good system message:
```yaml
system_message: "You are a data analyst. Focus on statistical accuracy, 
                 clear visualizations, and actionable insights."
```

Avoid vague messages:
```yaml
system_message: "You are helpful."  # Too generic
```

### 3. Use Appropriate Team Sizes

- **2-3 agents**: Optimal for most tasks
- **4-5 agents**: Complex problems requiring diverse perspectives
- **1 agent**: Simple queries or when testing

### 4. Monitor Performance

Enable logging to track agent behavior:
```yaml
ui:
  logging_enabled: true  # Saves detailed logs
```

## Troubleshooting

### Agent Not Responding

```bash
# Add timeout settings
timeout_settings:
  orchestrator_timeout_seconds: 60  # Increase timeout
```

### Agents Not Collaborating Well

```yaml
# Improve system messages for better coordination
agents:
  - id: "Agent 1"
    system_message: "Focus on research. Share key findings clearly."
  - id: "Agent 2"  
    system_message: "Build on Agent 1's research. Synthesize insights."
```

### Memory Issues with Large Tasks

```bash
# Use fewer agents or smaller models
uv run python -m massgen.cli --model gpt-5-nano "Your task"
```

## Next Steps

Now that you've created your first agents:

1. [Explore Configuration Options](configuration.md) - Deep dive into all settings
2. [Learn About Backends](../user_guide/backends.md) - Understand different AI providers
3. [Discover Tools](../user_guide/tools.md) - Add powerful capabilities
4. [View Examples](../examples/index.md) - See real-world use cases