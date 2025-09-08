# Configuration Guide

This comprehensive guide covers all configuration options in MassGen, from basic setups to advanced multi-agent orchestrations.

## Configuration Methods

### 1. Command Line (Quick Setup)

For simple single-agent tasks:

```bash
# Basic usage
uv run python -m massgen.cli --model <model_name> "Your query"

# With backend specification
uv run python -m massgen.cli --backend <backend_type> --model <model_name> "Your query"

# With system message
uv run python -m massgen.cli --model <model_name> --system-message "You are a helpful assistant" "Your query"
```

### 2. YAML Configuration Files (Recommended)

For complex setups and multi-agent systems:

```bash
uv run python -m massgen.cli --config your_config.yaml "Your query"
```

## Configuration File Structure

### Basic Structure

```yaml
# Single agent configuration
agent:
  id: "Agent Name"
  backend:
    type: "backend_type"
    model: "model_name"
  system_message: "Agent instructions"

# OR Multi-agent configuration
agents:
  - id: "Agent 1"
    backend: {...}
    system_message: "..."
  - id: "Agent 2"
    backend: {...}
    system_message: "..."

# UI settings
ui:
  display_type: "rich_terminal"
  logging_enabled: true

# Timeout settings
timeout_settings:
  orchestrator_timeout_seconds: 30

# Orchestrator settings
orchestrator:
  snapshot_storage: "snapshots"
  agent_temporary_workspace: "workspaces"
```

## Backend Configurations

### OpenAI / GPT Models

```yaml
backend:
  type: "openai"
  model: "gpt-5-mini"  # or gpt-4, gpt-5, gpt-5-nano
  api_key: "${OPENAI_API_KEY}"  # Uses environment variable
  temperature: 0.7
  max_tokens: 2500
  
  # GPT-5 specific features
  text:
    verbosity: "medium"  # low/medium/high
  reasoning:
    effort: "medium"  # low/medium/high
    summary: "auto"
  
  # Tools
  enable_web_search: true
  enable_code_interpreter: true
```

### Claude (Anthropic)

```yaml
backend:
  type: "claude"
  model: "claude-3-5-sonnet-latest"  # or claude-3-5-haiku, claude-3-5-opus
  api_key: "${ANTHROPIC_API_KEY}"
  temperature: 0.7
  max_tokens: 4096
  
  # Tools
  enable_web_search: true
  enable_code_execution: true
```

### Claude Code (Advanced Development)

```yaml
backend:
  type: "claude_code"
  cwd: "workspace"  # Working directory
  api_key: "${ANTHROPIC_API_KEY}"
  
  # Claude Code specific
  system_prompt: "Custom system prompt"
  append_system_prompt: "Additional instructions"
  max_thinking_tokens: 4096
  
  # MCP servers
  mcp_servers:
    playwright:
      type: "stdio"
      command: "npx"
      args: ["@playwright/mcp@latest", "--browser=chrome"]
  
  # Allowed tools
  allowed_tools:
    - "Read"
    - "Write"
    - "Edit"
    - "Bash"
    - "WebSearch"
```

### Gemini (Google)

```yaml
backend:
  type: "gemini"
  model: "gemini-2.5-flash"  # or gemini-2.5-pro
  api_key: "${GEMINI_API_KEY}"
  temperature: 0.7
  max_tokens: 2500
  
  # Tools
  enable_web_search: true
  enable_code_execution: true
  
  # MCP servers (v0.0.15+)
  mcp_servers:
    weather:
      type: "stdio"
      command: "npx"
      args: ["-y", "@fak111/weather-mcp"]
    
    brave_search:
      type: "stdio"
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-brave-search"]
      env:
        BRAVE_API_KEY: "${BRAVE_API_KEY}"
```

### Grok (xAI)

```yaml
backend:
  type: "grok"
  model: "grok-3-mini"  # or grok-3, grok-4
  api_key: "${XAI_API_KEY}"
  temperature: 0.7
  max_tokens: 2500
  
  # Web search
  enable_web_search: true
  
  # OR manual search configuration
  extra_body:
    search_parameters:
      mode: "auto"
      return_citations: true
```

### Azure OpenAI

```yaml
backend:
  type: "azure_openai"
  model: "gpt-4"  # Your deployment name
  base_url: "https://your-resource.openai.azure.com/"
  api_key: "${AZURE_OPENAI_API_KEY}"
  api_version: "2024-02-15-preview"
  temperature: 0.7
  max_tokens: 2500
  enable_code_interpreter: true
```

### Local Models (LM Studio)

```yaml
backend:
  type: "lmstudio"
  model: "qwen2.5-7b-instruct"  # Model to load
  temperature: 0.7
  max_tokens: 2000
```

### Custom API Endpoints

```yaml
backend:
  type: "chatcompletion"
  model: "custom-model"
  base_url: "https://your-api.com/v1"
  api_key: "${CUSTOM_API_KEY}"
  temperature: 0.7
  max_tokens: 2500
```

## MCP (Model Context Protocol) Configuration

### Basic MCP Setup

```yaml
mcp_servers:
  # Simple server
  server_name:
    type: "stdio"
    command: "command_to_run"
    args: ["arg1", "arg2"]
    
  # Server with environment variables
  api_server:
    type: "stdio"
    command: "npx"
    args: ["@org/mcp-server"]
    env:
      API_KEY: "${ENV_API_KEY}"
```

### Streamable HTTP MCP

```yaml
mcp_servers:
  http_server:
    type: "streamable-http"
    url: "http://localhost:5173/sse"
```

### Tool Management

```yaml
# Whitelist specific tools
allowed_tools:
  - "mcp__server__tool_name"
  - "Read"
  - "Write"

# Blacklist specific tools  
exclude_tools:
  - "mcp__server__dangerous_tool"
```

## System Messages

### Effective System Messages

```yaml
agents:
  - id: "Research Expert"
    system_message: |
      You are a research expert specializing in scientific literature.
      Your responsibilities:
      1. Find accurate, peer-reviewed sources
      2. Verify information from multiple sources
      3. Cite all references properly
      4. Focus on recent developments (last 5 years)
      
  - id: "Writer"
    system_message: |
      You are a technical writer who creates clear documentation.
      Guidelines:
      - Use simple, direct language
      - Include examples for complex concepts
      - Organize content with clear headings
      - Build upon research from other agents
```

## UI Configuration

### Display Types

```yaml
ui:
  display_type: "rich_terminal"  # Full-featured display
  # Options:
  # - "rich_terminal": Multi-region layout with colors
  # - "terminal": Standard terminal with formatting
  # - "simple": Plain text output
  
  logging_enabled: true  # Save detailed logs
```

## Advanced Configurations

### Timeout Management

```yaml
timeout_settings:
  orchestrator_timeout_seconds: 60  # Max orchestration time
```

### Workspace Management

```yaml
orchestrator:
  snapshot_storage: "agent_snapshots"  # Where to save snapshots
  agent_temporary_workspace: "temp_workspaces"  # Temporary files
```

### Debug Mode

```bash
# Enable debug logging
uv run python -m massgen.cli --config config.yaml --debug "Your query"
```

## Multi-Agent Collaboration Patterns

### Research Team

```yaml
agents:
  - id: "Data Collector"
    backend:
      type: "gemini"
      model: "gemini-2.5-flash"
      enable_web_search: true
    system_message: "Gather raw data and statistics"
    
  - id: "Analyst"
    backend:
      type: "claude"
      model: "claude-3-5-sonnet-latest"
      enable_code_execution: true
    system_message: "Analyze data and identify patterns"
    
  - id: "Reporter"
    backend:
      type: "gpt-5-mini"
    system_message: "Synthesize findings into clear reports"
```

### Development Team

```yaml
agents:
  - id: "Architect"
    backend:
      type: "claude_code"
    system_message: "Design system architecture and interfaces"
    
  - id: "Developer"
    backend:
      type: "claude_code"
    system_message: "Implement features following architecture"
    
  - id: "Tester"
    backend:
      type: "gemini"
      model: "gemini-2.5-flash"
      enable_code_execution: true
    system_message: "Write and run comprehensive tests"
```

## Environment Variables

### Setting Up .env File

```bash
# OpenAI
OPENAI_API_KEY=sk-...

# Anthropic
ANTHROPIC_API_KEY=sk-ant-...

# Google
GEMINI_API_KEY=...

# xAI
XAI_API_KEY=...

# Azure
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=https://...

# MCP Tools
BRAVE_API_KEY=...
DISCORD_TOKEN=...
```

### Using Environment Variables in Config

```yaml
backend:
  api_key: "${OPENAI_API_KEY}"  # Reads from environment
  
mcp_servers:
  brave:
    env:
      API_KEY: "${BRAVE_API_KEY}"  # Passes to MCP server
```

## Performance Optimization

### Fast Response Configuration

```yaml
# Use fast models
agents:
  - backend:
      type: "gemini"
      model: "gemini-2.5-flash"
      temperature: 0.3  # Lower for consistency
      max_tokens: 1000  # Limit response length
```

### High Quality Configuration

```yaml
# Use powerful models with more resources
agents:
  - backend:
      type: "claude"
      model: "claude-3-5-sonnet-latest"
      temperature: 0.7
      max_tokens: 4096
      
timeout_settings:
  orchestrator_timeout_seconds: 120  # More time for complex tasks
```

## Validation and Testing

### Test Your Configuration

```bash
# Validate YAML syntax
python -c "import yaml; yaml.safe_load(open('config.yaml'))"

# Test with simple query
uv run python -m massgen.cli --config config.yaml "Hello"

# Debug mode for troubleshooting
uv run python -m massgen.cli --config config.yaml --debug "Test"
```

## Common Configuration Patterns

### Pattern 1: Fast Iteration

```yaml
agents:
  - id: "Quick Thinker"
    backend:
      type: "gemini"
      model: "gemini-2.5-flash"
      temperature: 0.5
      
timeout_settings:
  orchestrator_timeout_seconds: 15
```

### Pattern 2: Deep Analysis

```yaml
agents:
  - id: "Deep Thinker 1"
    backend:
      type: "claude"
      model: "claude-3-5-sonnet-latest"
      
  - id: "Deep Thinker 2"
    backend:
      type: "gpt-5"
      
timeout_settings:
  orchestrator_timeout_seconds: 90
```

### Pattern 3: Specialized Tools

```yaml
agents:
  - id: "Web Researcher"
    backend:
      type: "gemini"
      enable_web_search: true
      
  - id: "Code Writer"
    backend:
      type: "claude_code"
      
  - id: "Data Analyst"
    backend:
      type: "openai"
      enable_code_interpreter: true
```

## Best Practices

1. **Start Simple**: Begin with single agents, then add complexity
2. **Use Environment Variables**: Never hardcode API keys
3. **Set Appropriate Timeouts**: Balance speed vs completeness
4. **Clear System Messages**: Be specific about agent roles
5. **Monitor Logs**: Enable logging for debugging
6. **Test Incrementally**: Validate each change
7. **Version Control**: Keep configs in git

## Next Steps

- [Explore Backends](../user_guide/backends.md) - Detailed backend documentation
- [Learn About Tools](../user_guide/tools.md) - Tool capabilities and usage
- [View Examples](../examples/index.md) - Real-world configurations
- [MCP Integration](../user_guide/mcp_integration.md) - Advanced tool integration