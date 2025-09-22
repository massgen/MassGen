# Backend Configuration Guide

Complete configuration reference for all MassGen backends with examples and parameters.

## Quick Navigation

- [OpenAI](#openai)
- [Claude](#claude)
- [Claude Code](#claude-code)
- [Gemini](#gemini)
- [Grok](#grok)
- [Azure OpenAI](#azure-openai)
- [Chat Completions](#chat-completions)
- [Z AI](#z-ai)
- [LM Studio (Local Models)](#lm-studio)

## Common Parameters

These parameters are available across most backends:

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `type` | string | Backend type identifier | Required |
| `model` | string | Model name/identifier | Required |
| `api_key` | string | API key (uses env vars if not set) | From environment |
| `temperature` | float | Creativity (0.0-1.0) | 0.7 |
| `max_tokens` | int | Maximum response length | Model default |
| `cwd` | string | Working directory for file operations | None |

---

## OpenAI

Full support for GPT-5 series with advanced reasoning and MCP integration (v0.0.17+).

```yaml
backend:
  type: "openai"
  model: "gpt-5-mini"                # gpt-5, gpt-5-mini, gpt-5-nano, gpt-4, etc.
  api_key: "<optional_key>"          # Uses OPENAI_API_KEY env var by default
  temperature: 0.7                   # Not supported for GPT-5 series and o-series
  max_tokens: 2500                   # Not supported for GPT-5 series and o-series
  
  # GPT-5 specific parameters
  text: 
    verbosity: "medium"              # low/medium/high (GPT-5 only)
  reasoning:                         
    effort: "medium"                 # low/medium/high (GPT-5 and o-series)
    summary: "auto"                  # Automatic reasoning summaries
  
  # Builtin tools
  enable_web_search: true            # Web search capability
  enable_code_interpreter: true      # Code interpreter capability
  
  # MCP servers (v0.0.17+)
  mcp_servers:
    weather:
      type: "stdio"
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-weather"]
    
    brave_search:
      type: "stdio"
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-brave-search"]
      env:
        BRAVE_API_KEY: "${BRAVE_API_KEY}"
  
  # Tool control
  allowed_tools:                     # Whitelist specific tools
    - "mcp__weather__get_current_weather"
    - "mcp__brave_search__brave_web_search"
  
  exclude_tools:                     # Blacklist specific tools
    - "mcp__weather__debug_mode"
```

### OpenAI-Specific Features
- **GPT-5 Series**: Advanced reasoning with `text.verbosity` and `reasoning.effort` parameters
- **Code Interpreter**: Built-in code execution environment
- **Web Search**: Real-time web search capability
- **MCP Support**: Full MCP integration since v0.0.17

---

## Claude

Anthropic's Claude models with Messages API and MCP support (v0.0.20+).

```yaml
backend:
  type: "claude"
  model: "claude-sonnet-4-20250514"  # claude-opus-4, claude-sonnet-4, claude-haiku-3.5
  api_key: "<optional_key>"          # Uses ANTHROPIC_API_KEY env var by default
  temperature: 0.7                   
  max_tokens: 4096                   # Claude supports larger context
  
  # Builtin tools
  enable_web_search: true            
  enable_code_execution: true        
  
  # MCP servers (v0.0.20+)
  mcp_servers:
    test_server:
      type: "stdio"
      command: "python"
      args: ["-u", "-m", "massgen.tests.mcp_test_server"]
    
    weather:
      type: "stdio"
      command: "npx"
      args: ["-y", "@fak111/weather-mcp"]
    
    # HTTP-based MCP server
    api_server:
      type: "streamable-http"
      url: "http://localhost:5173/sse"
  
  # Tool control
  allowed_tools:
    - "mcp__test_server__mcp_echo"
    - "mcp__weather__get_current_weather"
  
  exclude_tools:
    - "mcp__test_server__current_time"
```

### Claude-Specific Features
- **Large Context Window**: Up to 200K tokens context
- **Recursive MCP Execution**: Autonomous tool chaining (v0.0.20+)
- **Web Search & Code Execution**: Built-in capabilities
- **Streaming Support**: Full async streaming with tool use

---

## Claude Code

Native Claude Code SDK integration with comprehensive development tools.

```yaml
backend:
  type: "claude_code"
  cwd: "claude_code_workspace"       # Working directory for file operations
  api_key: "<optional_key>"          # Uses ANTHROPIC_API_KEY env var by default
  
  # Claude Code specific options
  system_prompt: ""                  # Custom system prompt to replace default
  append_system_prompt: ""           # Custom system prompt to append
  max_thinking_tokens: 4096         # Maximum thinking tokens
  
  # MCP servers
  mcp_servers:
    discord:
      type: "stdio"
      command: "npx"
      args: ["-y", "mcp-discord", "--config", "YOUR_DISCORD_TOKEN"]
    
    playwright:
      type: "stdio"
      command: "npx"
      args: [
        "@playwright/mcp@latest",
        "--browser=chrome",
        "--caps=vision,pdf",
        "--user-data-dir=/tmp/playwright-profile",
        "--save-trace"
      ]
  
  # Native Claude Code tools
  allowed_tools:
    - "Read"           # Read files
    - "Write"          # Write files  
    - "Edit"           # Edit files
    - "MultiEdit"      # Multiple edits
    - "Bash"           # Shell commands
    - "Grep"           # Search in files
    - "Glob"           # Find files
    - "LS"             # List directory
    - "WebSearch"      # Web search
    - "WebFetch"       # Fetch web content
    - "TodoWrite"      # Task management
    - "NotebookEdit"   # Jupyter notebooks
    # MCP tools are auto-discovered
```

### Claude Code-Specific Features
- **Native File Operations**: Built-in filesystem tools
- **Development Environment**: Complete coding assistant
- **Task Management**: TodoWrite for tracking progress
- **Jupyter Support**: Notebook editing capabilities
- **MCP Integration**: Supports external MCP servers

---

## Gemini

Google's Gemini models with Chat API and comprehensive MCP support (v0.0.15+).

```yaml
backend:
  type: "gemini"
  model: "gemini-2.5-flash"          # gemini-2.5-flash, gemini-2.5-pro
  api_key: "<optional_key>"          # Uses GOOGLE_API_KEY env var by default
  temperature: 0.7                   
  max_tokens: 2500                   
  top_p: 0.95                        # Nucleus sampling parameter
  
  # Builtin tools
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
    
    airbnb:
      type: "stdio"
      command: "npx"
      args: ["-y", "@openbnb/mcp-server-airbnb", "--ignore-robots-txt"]
    
    # HTTP-based server
    custom_api:
      type: "streamable-http"
      url: "http://localhost:5173/sse"
  
  # Tool control
  allowed_tools:
    - "mcp__weather__get_current_weather"
    - "mcp__brave_search__brave_web_search"
    - "mcp__airbnb__airbnb_search"
  
  exclude_tools:
    - "mcp__airbnb__debug_mode"
```

### Gemini-Specific Features
- **Multimodal Support**: Image and text understanding
- **Fast Inference**: Optimized for speed (Flash models)
- **Code Execution**: Built-in code interpreter
- **Multi-Server MCP**: Support for multiple MCP servers simultaneously

---

## Grok

xAI's Grok models with Live Search and MCP integration (v0.0.21+).

```yaml
backend:
  type: "grok"
  model: "grok-3-mini"               # grok-3, grok-3-mini, grok-4
  api_key: "<optional_key>"          # Uses XAI_API_KEY env var by default
  temperature: 0.7                   
  max_tokens: 2500                   
  
  # Grok Live Search
  enable_web_search: true            # Uses default: mode="auto", return_citations=true
  
  # Automatic filesystem MCP when cwd is provided
  cwd: "workspace"                   # Enables filesystem MCP server
  
  # MCP servers (v0.0.21+)
  mcp_servers:
    weather:
      type: "stdio"
      command: "npx"
      args: ["-y", "@fak111/weather-mcp"]
  
  # Alternative: Manual search parameters (conflicts with enable_web_search)
  # extra_body:
  #   search_parameters:
  #     mode: "auto"                 
  #     return_citations: true       
```

### Grok-Specific Features
- **Live Search**: Real-time web search with citations
- **Automatic Filesystem MCP**: When `cwd` is set
- **Cost-Effective Mini Models**: Lower pricing for mini variants
- **Full MCP Support**: Since v0.0.21

---

## Azure OpenAI

Microsoft Azure-hosted OpenAI models with deployment management.

```yaml
backend:
  type: "azure_openai"
  model: "gpt-4.1"                   # Your Azure deployment name
  base_url: "https://your-resource.openai.azure.com/"  # Your Azure endpoint
  api_key: "<optional_key>"          # Uses AZURE_OPENAI_API_KEY env var by default
  api_version: "2024-02-15-preview"  # Azure API version
  temperature: 0.7                   
  max_tokens: 2500                   
  
  # Azure-specific features
  enable_code_interpreter: true      # Code interpreter capability
```

### Azure-Specific Features
- **Enterprise Security**: Azure AD integration
- **Regional Deployment**: Data residency compliance
- **Code Interpreter**: Built-in code execution
- **Custom Deployments**: Use your own fine-tuned models

---

## Chat Completions

Generic backend supporting multiple providers (v0.0.18+ with MCP).

Supports: Cerebras AI, Together AI, Fireworks AI, Groq, Nebius AI Studio, OpenRouter, Kimi/Moonshot, and any OpenAI-compatible API.

```yaml
backend:
  type: "chatcompletion"
  model: "llama3.3-70b"              # Model varies by provider
  base_url: "https://api.together.xyz/v1"  # Provider endpoint
  api_key: "<optional_key>"          # Provider-specific API key
  temperature: 0.7
  max_tokens: 2500
  
  # MCP servers (v0.0.18+)
  mcp_servers:
    weather:
      type: "stdio"
      command: "npx"
      args: ["-y", "@fak111/weather-mcp"]
    
    test_server:
      type: "stdio"
      command: "python"
      args: ["-u", "-m", "massgen.tests.mcp_test_server"]
  
  # Tool control
  allowed_tools:
    - "mcp__weather__get_current_weather"
    - "mcp__test_server__mcp_echo"
```

### Provider-Specific Base URLs
- **Cerebras**: `https://api.cerebras.ai/v1`
- **Together AI**: `https://api.together.xyz/v1`
- **Fireworks**: `https://api.fireworks.ai/inference/v1`
- **Groq**: `https://api.groq.com/openai/v1`
- **OpenRouter**: `https://openrouter.ai/api/v1`
- **Kimi/Moonshot**: `https://api.moonshot.cn/v1`

---

## Z AI

ZhipuAI's GLM models with advanced Chinese language support.

```yaml
backend:
  type: "zai"
  model: "glm-4.5"                   # GLM model variant
  base_url: "https://api.z.ai/api/paas/v4/"  # Z AI endpoint
  api_key: "<optional_key>"          # Uses ZAI_API_KEY env var by default
  temperature: 0.7                   
  top_p: 0.7                        # Nucleus sampling
```

### Z AI-Specific Features
- **Chinese Language**: Optimized for Chinese text
- **GLM-4.5 Series**: Latest GLM models
- **Competitive Pricing**: Cost-effective for Asian markets

---

## LM Studio

Run open-source models locally with automatic server management (v0.0.7+).

```yaml
backend:
  type: "lmstudio"
  model: "qwen2.5-7b-instruct"       # Model to load
  temperature: 0.7                   
  max_tokens: 2000                   
  
  # LM Studio automatically handles:
  # - Server startup
  # - Model downloading
  # - Model loading
```

### LM Studio-Specific Features
- **Zero Cost**: Run models locally
- **Privacy**: Data never leaves your machine
- **Model Library**: Support for LLaMA, Mistral, Qwen, etc.
- **Automatic Management**: Server and model handled automatically

### Installation
```bash
# MacOS/Linux
sudo ~/.lmstudio/bin/lms bootstrap

# Windows
cmd /c %USERPROFILE%/.lmstudio/bin/lms.exe bootstrap
```

---

## Environment Variables

Set these in your `.env` file:

```bash
# API Keys
OPENAI_API_KEY=your-openai-key
ANTHROPIC_API_KEY=your-anthropic-key
GOOGLE_API_KEY=your-google-key
XAI_API_KEY=your-xai-key
AZURE_OPENAI_API_KEY=your-azure-key
ZAI_API_KEY=your-zai-key

# Provider-specific
TOGETHER_API_KEY=your-together-key
CEREBRAS_API_KEY=your-cerebras-key
GROQ_API_KEY=your-groq-key
MOONSHOT_API_KEY=your-kimi-key

# MCP Services
BRAVE_API_KEY=your-brave-search-key
OPENWEATHER_API_KEY=your-weather-key
NOTION_API_KEY=your-notion-key
```

---

## Full Examples

- **Single Agent**: [massgen/configs/basic/single/](../../massgen/configs/basic/single/)
- **Multi-Agent**: [massgen/configs/basic/multi/](../../massgen/configs/basic/multi/)
- **MCP Integration**: [massgen/configs/tools/mcp/](../../massgen/configs/tools/mcp/)
- **Provider-Specific**: [massgen/configs/providers/](../../massgen/configs/providers/)

---

## Need Help?

- [Join our Discord](https://discord.massgen.ai)
- [Report Issues](https://github.com/Leezekun/MassGen/issues)
- [View Documentation](https://github.com/Leezekun/MassGen)