# Backend & Model Support

**Backend System:** Evolved since v0.0.3 (August 2025)

MassGen supports a wide range of AI models and backends, from frontier commercial APIs to local open-source models. This guide covers all supported backends, their capabilities, and how to configure them.

## Backend Release History

| Backend | Version | Date | Description |
|---------|---------|------|-------------|
| OpenAI, Claude, Gemini, Grok | v0.0.3 | Aug 2025 | Initial backend support |
| GPT-5 Series | v0.0.4 | Aug 2025 | GPT-5, GPT-5-mini, GPT-5-nano |
| Claude Code | v0.0.5 | Aug 2025 | Claude Code CLI integration |
| GLM-4.5 | v0.0.6 | Aug 2025 | ZhipuAI GLM models |
| LM Studio, Chat Completions Providers | v0.0.7 | Aug 2025 | Local models, extended providers |
| Azure OpenAI | v0.0.10 | Aug 2025 | Enterprise Azure deployments |
| vLLM | v0.0.24 | Sept 2025 | High-performance local inference |
| SGLang | v0.0.25 | Sept 2025 | Unified with vLLM as InferenceBackend |
| Claude Sonnet 4.5 | v0.0.27 | Oct 2025 | Latest Claude model |
| AG2 Framework | v0.0.28 | Oct 2025 | External framework integration |
| Multimodal Extensions | v0.0.30 | Oct 2025 | Audio/video support for Chat Completions & Claude |
| Universal Code Execution | v0.1.0 | Oct 2025 | MCP-based execute_command tool for all backends |
| AG2 Group Chat | v0.1.0 | Oct 2025 | Native multi-agent conversations |

## Supported Backends Overview

| Backend | Provider | Model Examples | Key Features |
|---------|----------|----------------|--------------|
| [OpenAI](#openai--gpt-models) | OpenAI | GPT-4o, GPT-5, o4-mini | Reasoning, web search, code interpreter |
| [Claude](#claude-models) | Anthropic | Claude Sonnet 4 | High-quality reasoning |
| [Claude Code](#claude-code) | Anthropic | Claude Code | Filesystem tools, MCP integration |
| [Gemini](#gemini-models) | Google | Gemini 2.5 Flash/Pro | Native MCP, web search, code execution |
| [Grok](#grok-models) | xAI | Grok-3, Grok-4 | Web search with citations |
| [Azure OpenAI](#azure-openai) | Microsoft Azure | GPT-4.1, GPT-5 | Enterprise deployments |
| [AG2](#ag2-framework) | AG2 | Any OpenAI-compatible | Code execution framework |
| [Local Models](#local-models) | Self-hosted | LLaMA, Qwen, Mistral | Privacy, cost control |

## OpenAI / GPT Models

### Supported Models

- **GPT-5 Series**: `gpt-5`, `gpt-5-mini`, `gpt-5-nano`
- **GPT-4o Series**: `gpt-4o`, `gpt-4o-mini`
- **o-Series**: `o4-mini` (reasoning-focused)
- **Open Source**: `gpt-oss-120b` (via Cerebras)

### Configuration

```yaml
agent:
  id: "gpt5_agent"
  backend:
    type: "openai"
    model: "gpt-5"

    # Text generation settings
    text:
      verbosity: "medium"  # low, medium, high

    # Reasoning configuration
    reasoning:
      effort: "high"      # low, medium, high
      summary: "auto"     # auto, always, never

    # Built-in tools
    enable_web_search: true
    enable_code_interpreter: true
```

**Example Configs:**
- [`gpt5.yaml`](../../massgen/configs/providers/openai/gpt5.yaml) - Three GPT-5 variants
- [`gpt5_nano.yaml`](../../massgen/configs/providers/openai/gpt5_nano.yaml) - Three GPT-5 Nano agents
- [`single_gpt5nano.yaml`](../../massgen/configs/basic/single/single_gpt5nano.yaml) - Single GPT-5 Nano

### Capabilities

**✅ Supported Features:**
- Web search (built-in)
- Code interpreter (sandbox execution)
- **Universal code execution** (v0.1.0) - MCP-based `execute_command` tool
- Reasoning mode with configurable effort
- MCP integration
- Planning mode
- Multi-turn sessions
- File upload/search (GPT-5 Nano)
- Image understanding (GPT-4o)
- Image generation (GPT-4o with DALL-E)
- Audio generation & understanding (v0.0.30+)
- Video generation (v0.1.0) - Sora-2 API

### Reasoning Models

GPT-5 and o4-mini support extended reasoning:

```yaml
backend:
  type: "openai"
  model: "gpt-5"
  reasoning:
    effort: "high"       # More thinking for complex problems
    summary: "auto"      # Auto-show reasoning when useful
```

**Effort Levels:**
- `low` - Fast responses, minimal reasoning
- `medium` - Balanced thinking and speed
- `high` - Deep reasoning for complex problems

### Web Search & Code Execution

```yaml
backend:
  type: "openai"
  model: "gpt-5-nano"
  enable_web_search: true          # Enable web search
  enable_code_interpreter: true    # Enable code execution
```

## Claude Models

### Supported Models

- **Claude Sonnet 4**: `claude-sonnet-4-20250514`
- **Claude Haiku**: Various versions
- **Claude Opus**: Various versions

### Configuration

```yaml
agent:
  id: "claude_agent"
  backend:
    type: "claude"
    model: "claude-sonnet-4-20250514"

    # MCP servers (optional)
    mcp_servers:
      - name: "discord"
        type: "stdio"
        command: "npx"
        args: ["-y", "mcp-discord"]
```

**Example Configs:**
- [`claude.yaml`](../../massgen/configs/providers/claude/claude.yaml) - Single Claude agent
- [`gemini_4o_claude.yaml`](../../massgen/configs/basic/multi/gemini_4o_claude.yaml) - Multi-backend mix

### Capabilities

**✅ Supported Features:**
- MCP integration
- Planning mode
- Multi-turn sessions
- Tool calling
- Long context windows
- **Universal code execution** (v0.1.0) - Via MCP `execute_command` tool
- Audio/video understanding (v0.0.30+)

**❌ Not Available:**
- Native web search (use MCP or external tools)
- Built-in code interpreter (use universal code execution or AG2)

## Claude Code

Claude Code provides filesystem operations and native tool integration.

### Configuration

```yaml
agent:
  id: "claude_code_agent"
  backend:
    type: "claude_code"
    cwd: "workspace"                    # Working directory
    permission_mode: "bypassPermissions" # or "strict"

    # MCP servers (dictionary format)
    mcp_servers:
      discord:
        type: "stdio"
        command: "npx"
        args: ["-y", "mcp-discord"]

    # Native tools
    allowed_tools:
      - "Read"
      - "Write"
      - "Bash"
      - "LS"
```

**Example Configs:**
- [`claude_code_single.yaml`](../../massgen/configs/tools/filesystem/claude_code_single.yaml) - Single agent with filesystem
- [`claude_code_discord_mcp_example.yaml`](../../massgen/configs/tools/mcp/claude_code_discord_mcp_example.yaml) - Discord MCP integration

### Capabilities

**✅ Supported Features:**
- Native filesystem operations (Read, Write, LS, Bash)
- MCP integration (dictionary format)
- Workspace isolation with `cwd`
- Permission system with context paths
- Planning mode
- Multi-turn sessions

**Key Differences from Other Backends:**
- MCP servers use dictionary format instead of list
- Native filesystem tools available
- `permission_mode` setting controls file access
- `cwd` sets agent's working directory

**Context Paths Support:**
Claude Code agents can access additional directories via orchestrator `context_paths`:
- Paths can be **absolute** or **relative** (resolved from current directory)
- `permission: "read"` or `"write"` (write applies only to final agent)
- `protected_paths` can mark specific files as read-only within writable directories

→ [Learn more about context paths](./filesystem-tools.md#context-paths)

## Gemini Models

### Supported Models

- **Gemini 2.5 Flash**: `gemini-2.5-flash` (fast, cost-effective)
- **Gemini 2.5 Pro**: `gemini-2.5-pro` (advanced reasoning)
- **Gemini Flash**: Earlier versions

### Configuration

```yaml
agent:
  id: "gemini_agent"
  backend:
    type: "gemini"
    model: "gemini-2.5-flash"

    # Built-in capabilities
    enable_web_search: true
    enable_code_execution: true

    # Working directory for filesystem operations
    cwd: "workspace"
```

**Example Configs:**
- [`single_agent.yaml`](../../massgen/configs/basic/single/single_agent.yaml) - Default Gemini Flash
- [`single_flash2.5.yaml`](../../massgen/configs/basic/single/single_flash2.5.yaml) - Gemini 2.5 Flash
- [`gemini_gpt5nano.yaml`](../../massgen/configs/providers/gemini/gemini_gpt5nano.yaml) - Gemini + GPT-5 Nano

### Capabilities

**✅ Supported Features:**
- **Native filesystem MCP** - Built-in file operations
- Web search (Google Search integration)
- Code execution (sandboxed Python)
- **Universal code execution** (v0.1.0) - MCP-based `execute_command` tool
- MCP integration
- Planning mode
- Multi-turn sessions
- Image understanding
- Long context (2M tokens on Pro)

### Native Filesystem MCP

Gemini has native filesystem MCP support:

```yaml
backend:
  type: "gemini"
  model: "gemini-2.5-pro"
  cwd: "workspace1"  # Each agent's isolated workspace

# In orchestrator section, add context paths for project access
orchestrator:
  context_paths:
    - path: "."              # Current directory (relative path)
      permission: "write"    # Write for final agent only
      protected_paths:       # Optional: protect specific files
        - ".env"
```

No MCP server installation needed - filesystem operations work out of the box!

**Context Paths Support:**
- Paths can be **absolute** (`/home/user/project`) or **relative** (`.`, `src/`)
- Write permissions apply **only to final agent** during presentation phase
- All agents have read access during coordination
- `protected_paths` prevent modification of sensitive files

**Example**: [`gemini_mcp_filesystem_test.yaml`](../../massgen/configs/tools/mcp/gemini_mcp_filesystem_test.yaml)

## Grok Models

### Supported Models

- **Grok-4**: `grok-4` (latest, most capable)
- **Grok-3 Mini**: `grok-3-mini` (faster, cost-effective)

### Configuration

```yaml
agent:
  id: "grok_agent"
  backend:
    type: "grok"
    model: "grok-3-mini"

    # Web search (native)
    enable_web_search: true

    # Search parameters
    extra_body:
      search_parameters:
        mode: "auto"               # Search strategy
        return_citations: true     # Include citations
        max_search_results: 3      # Max results
```

**Example Configs:**
- [`grok_single_agent.yaml`](../../massgen/configs/providers/others/grok_single_agent.yaml) - Single Grok agent
- [`three_agents_default.yaml`](../../massgen/configs/basic/multi/three_agents_default.yaml) - Includes Grok-3-mini

### Capabilities

**✅ Supported Features:**
- **Web search with citations** - Built-in with source attribution
- **Universal code execution** (v0.1.0) - MCP-based `execute_command` tool
- MCP integration
- Planning mode
- Multi-turn sessions
- Configurable search parameters

**Unique Features:**
- `return_citations: true` - Automatic source attribution
- `max_search_results` - Control search depth
- Real-time information access

## Azure OpenAI

Deploy OpenAI models through Azure for enterprise use.

### Configuration

```yaml
agent:
  id: "azure_agent"
  backend:
    type: "azure_openai"
    model: "gpt-4.1"  # Your Azure deployment name

    # Azure-specific settings (from environment)
    # AZURE_OPENAI_API_KEY
    # AZURE_OPENAI_ENDPOINT
    # AZURE_OPENAI_API_VERSION
```

**Example Configs:**
- [`azure_openai_single.yaml`](../../massgen/configs/providers/azure/azure_openai_single.yaml) - Single Azure agent
- [`azure_openai_multi.yaml`](../../massgen/configs/providers/azure/azure_openai_multi.yaml) - Multi-agent Azure

### Environment Variables

```bash
# .env file
AZURE_OPENAI_API_KEY="your_azure_key"
AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com"
AZURE_OPENAI_API_VERSION="2024-02-15-preview"
```

### Capabilities

Same as OpenAI backend but deployed through Azure:
- Enterprise SLA and support
- Data residency control
- Private networking
- Usage tracking and billing through Azure

## AG2 Framework

AG2 integration for advanced code execution and multi-agent collaboration.

### Configuration

```yaml
agent:
  id: "ag2_coder"
  backend:
    type: "ag2"
    agent_config:
      type: "assistant"
      name: "AG2_coder"
      system_message: "You are a coding assistant..."

      llm_config:
        api_type: "openai"
        model: "gpt-5"

      code_execution_config:
        executor:
          type: "LocalCommandLineCodeExecutor"
          timeout: 60
          work_dir: "./code_execution_workspace"
```

**Example Configs:**
- [`ag2_coder.yaml`](../../massgen/configs/ag2/ag2_coder.yaml) - Single AG2 coding agent
- [`ag2_gemini.yaml`](../../massgen/configs/ag2/ag2_gemini.yaml) - AG2 with Gemini backend

### Capabilities

**✅ Supported Features:**
- **Code execution** - Full Python code execution
- Multiple executor types
- Configurable timeouts and workspace
- Any OpenAI-compatible backend
- Multi-agent AG2 workflows

**Use Cases:**
- Data analysis and visualization
- Code generation and testing
- Scientific computing
- Automated debugging

### Code Execution

```yaml
code_execution_config:
  executor:
    type: "LocalCommandLineCodeExecutor"
    timeout: 60                           # Execution timeout
    work_dir: "./code_execution_workspace"  # Sandbox directory
```

## Local Models

Run open-source models locally for privacy and cost control.

### LM Studio

```yaml
agent:
  id: "local_agent"
  backend:
    type: "lmstudio"
    model: "qwen/qwen3-4b-2507"  # Any model loaded in LM Studio
```

**Example Config:** [`lmstudio.yaml`](../../massgen/configs/providers/local/lmstudio.yaml)

**Setup:**
1. Install [LM Studio](https://lmstudio.ai)
2. Download a model (LLaMA, Mistral, Qwen, etc.)
3. Start local server (default: `http://localhost:1234`)
4. Configure MassGen to use the model

### vLLM

High-performance local inference:

```yaml
agent:
  id: "vllm_agent"
  backend:
    type: "vllm"
    model: "Qwen/Qwen3-4B"
    base_url: "http://localhost:8000/v1"
```

**Example Config:** [`three_agents_vllm.yaml`](../../massgen/configs/basic/multi/three_agents_vllm.yaml)

**Setup:**
1. Install vLLM: `pip install vllm`
2. Start server: `python -m vllm.entrypoints.openai.api_server --model Qwen/Qwen3-4B`
3. Configure MassGen to connect

### SGLang

Optimized local inference with SGLang:

```yaml
agent:
  id: "sglang_agent"
  backend:
    type: "sglang"
    model: "Qwen/Qwen3-4B"
    base_url: "http://localhost:30000/v1"
```

**Example Config:** [`two_qwen_vllm_sglang.yaml`](../../massgen/configs/basic/multi/two_qwen_vllm_sglang.yaml)

### Generic OpenAI-Compatible

For any OpenAI-compatible API:

```yaml
agent:
  id: "custom_backend"
  backend:
    type: "chatcompletion"
    model: "your-model-name"
    base_url: "https://your-api-endpoint.com/v1"
```

**Supported Providers:**
- Cerebras (GPT-OSS-120B)
- Zhipu AI (GLM-4.5)
- Together AI
- Fireworks AI
- Any OpenAI-compatible endpoint

## Other Commercial Models

### Zhipu AI (GLM Models)

```yaml
agent:
  id: "glm_agent"
  backend:
    type: "chatcompletion"
    model: "glm-4.5"
    base_url: "https://api.z.ai/api/paas/v4"
```

**Models:**
- `glm-4.5` - Full capability
- `glm-4.5-air` - Lightweight version

**Example Config:** [`zai_glm45.yaml`](../../massgen/configs/providers/others/zai_glm45.yaml)

## Feature Comparison

<!-- AUTO-GENERATED TABLE - DO NOT EDIT MANUALLY -->
<!-- Source: massgen/backend/capabilities.py -->
<!-- To update: Run `python docs/scripts/generate_backend_tables.py` -->

| Feature | OpenAI | Claude | Claude Code | Gemini | Grok | Azure OpenAI | Chat Completions (Generic) | LM Studio | Inference (vLLM/SGLang) | AG2 (AutoGen) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Web Search** | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Code Execution** | ✅ | ✅ | ❌ | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ | ✅ |
| **Bash/Shell** | ❌ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Image** | ✅ Both | ❌ | ✅ Understanding | ✅ Understanding | ❌ | ✅ Both | ❌ | ❌ | ❌ | ❌ |
| **Audio** | ✅ Both | ✅ Understanding | ❌ | ❌ | ❌ | ❌ | ✅ Understanding | ❌ | ❌ | ❌ |
| **Video** | ✅ Generation | ✅ Understanding | ❌ | ❌ | ❌ | ❌ | ✅ Understanding | ❌ | ❌ | ❌ |
| **MCP Support** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| **Filesystem** | ✅ Via MCP | ✅ Via MCP | ✅ Native | ✅ Native | ✅ Via MCP | ✅ Via MCP | ✅ Via MCP | ✅ Via MCP | ✅ Via MCP | ❌ |

**Legend:**
- ✅ = Supported
- ❌ = Not supported

**Notes:**
- "Via MCP" means the feature is available through Model Context Protocol integration
- "Native" means the feature is built directly into the backend
- **Image**: "Both" = understanding + generation, "Understanding" = can analyze images, "Generation" = can create images
- **Audio**: "Both" = understanding + generation (v0.0.30+), "Understanding" = can analyze audio files
- **Video**: "Generation" = can create videos (OpenAI Sora-2 API v0.1.0), "Understanding" = can analyze video files (v0.0.30+)
- **Context Paths**: All filesystem-capable backends support context paths (absolute/relative paths with read/write permissions)
- **Protected Paths**: Specify files immune from modification within writable directories
- **Write Permissions**: Apply only to the final agent during presentation phase, protecting files during coordination
- Additional backend-specific features (Planning Mode, Multi-turn, etc.) are supported by all backends
- **AG2 (AutoGen)** provides code execution with multiple executor types; MCP support is planned for future releases

## Choosing the Right Backend

### For Research & Analysis
**Best:** Gemini 2.5 Pro, GPT-5, Grok-4
- Native web search
- Long context windows
- Strong reasoning

### For Code Generation
**Best:** AG2 + GPT-5, Claude Sonnet 4, Gemini 2.5 Pro
- Code execution capabilities
- Strong programming knowledge
- Debugging support

### For Filesystem Operations
**Best:** Claude Code, Gemini (native MCP)
- Native file operations
- Workspace isolation
- Safe file management

### For Social Media & APIs
**Best:** Any with MCP support + Planning Mode
- MCP integration for external services
- Planning mode prevents duplicate actions
- Multi-agent collaboration

### For Cost Optimization
**Best:** Local models (vLLM, LM Studio), GPT-5 Nano, Gemini 2.5 Flash
- No API costs (local)
- Efficient smaller models
- High throughput

### For Enterprise
**Best:** Azure OpenAI
- SLA guarantees
- Data residency
- Private deployment
- Enterprise support

## Multi-Backend Mixing

Combine different backends in a single configuration:

```yaml
agents:
  - id: "researcher"
    backend:
      type: "gemini"
      model: "gemini-2.5-pro"
      enable_web_search: true

  - id: "coder"
    backend:
      type: "ag2"
      agent_config:
        llm_config:
          model: "gpt-5"
      code_execution_config:
        executor:
          type: "LocalCommandLineCodeExecutor"

  - id: "writer"
    backend:
      type: "claude"
      model: "claude-sonnet-4-20250514"
```

**Benefits:**
- Leverage each model's strengths
- Cost optimization (expensive models for complex tasks)
- Redundancy and diversity

**Example Configs:**
- [`three_agents_default.yaml`](../../massgen/configs/basic/multi/three_agents_default.yaml) - Gemini + GPT + Grok
- [`gemini_4o_claude.yaml`](../../massgen/configs/basic/multi/gemini_4o_claude.yaml) - Gemini + GPT-4o + Claude

## Environment Variables

### Required API Keys

```bash
# .env file

# OpenAI
OPENAI_API_KEY="sk-..."

# Anthropic Claude
ANTHROPIC_API_KEY="sk-ant-..."

# Google Gemini
GOOGLE_API_KEY="AI..."

# xAI Grok
XAI_API_KEY="xai-..."

# Azure OpenAI
AZURE_OPENAI_API_KEY="..."
AZURE_OPENAI_ENDPOINT="https://..."
AZURE_OPENAI_API_VERSION="2024-02-15-preview"
```

### Optional Settings

```bash
# Base URLs for local/custom backends
OPENAI_BASE_URL="http://localhost:1234/v1"  # LM Studio
VLLM_BASE_URL="http://localhost:8000/v1"    # vLLM
SGLANG_BASE_URL="http://localhost:30000/v1" # SGLang
```

## Common Configuration Patterns

### Single Agent Template

```yaml
agent:
  id: "my_agent"
  backend:
    type: "BACKEND_TYPE"
    model: "MODEL_NAME"
  system_message: "Custom instructions"

ui:
  display_type: "rich_terminal"
  logging_enabled: true
```

### Multi-Agent Template

```yaml
agents:
  - id: "agent1"
    backend:
      type: "BACKEND_TYPE"
      model: "MODEL_NAME"

  - id: "agent2"
    backend:
      type: "BACKEND_TYPE"
      model: "MODEL_NAME"

ui:
  display_type: "rich_terminal"
  logging_enabled: true
```

## Troubleshooting

### API Key Errors

**Problem:** `AuthenticationError` or `Invalid API key`

**Solutions:**
- Verify API key is set in `.env` file
- Check key format matches provider requirements
- Ensure no extra spaces or quotes in `.env`
- Verify key has necessary permissions

### Model Not Found

**Problem:** `ModelNotFoundError` or `Invalid model`

**Solutions:**
- Check model name spelling exactly matches provider
- Verify you have access to the model (some require waitlist)
- For Azure: ensure deployment name matches your Azure setup
- For local: verify model is loaded in LM Studio/vLLM

### Connection Errors (Local Models)

**Problem:** Cannot connect to local backend

**Solutions:**
- Verify server is running: `curl http://localhost:1234/v1/models`
- Check port number matches config
- Ensure no firewall blocking connections
- Verify base_url includes `/v1` suffix

### Rate Limiting

**Problem:** `RateLimitError` from API

**Solutions:**
- Reduce number of parallel agents
- Add delays between requests
- Upgrade API tier if available
- Use local models as fallback

## Next Steps

- [Configuration Guide](./configuration-guide.md) - Using backends in configs
- [MCP Integration](./mcp-integration.md) - Adding external tools to any backend
- [Planning Mode](./planning-mode.md) - Multi-agent coordination with any backend
- [Multi-Agent Coordination](./multi-agent-coordination.md) - Mixing multiple backends

## All Backend Configurations

Browse configs by backend:
- **OpenAI**: [`massgen/configs/providers/openai/`](../../massgen/configs/providers/openai/)
- **Claude**: [`massgen/configs/providers/claude/`](../../massgen/configs/providers/claude/)
- **Gemini**: [`massgen/configs/providers/gemini/`](../../massgen/configs/providers/gemini/)
- **Azure**: [`massgen/configs/providers/azure/`](../../massgen/configs/providers/azure/)
- **Local**: [`massgen/configs/providers/local/`](../../massgen/configs/providers/local/)
- **Others**: [`massgen/configs/providers/others/`](../../massgen/configs/providers/others/)
- **AG2**: [`massgen/configs/ag2/`](../../massgen/configs/ag2/)

---

**Last Updated:** October 2025 | **MassGen Version:** v0.1.0+
