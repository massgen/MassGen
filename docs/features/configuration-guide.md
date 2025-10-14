# Configuration Guide

**Configuration System:** Evolved since v0.0.3
**Major Reorganization:** v0.0.22 (September 2025) - Hierarchical structure introduced

MassGen uses YAML configuration files to define agent setups, backends, tools, and orchestration behavior. With 98 pre-built configurations available, this guide helps you understand how configs work and find the right one for your use case.

## Configuration File Structure

### Single Agent Configuration

Single agent configs use the `agent` (singular) key:

```yaml
# Single agent configuration
agent:
  id: "gemini_agent"
  backend:
    type: "gemini"
    model: "gemini-2.5-flash"
    enable_web_search: true
  system_message: "You are a helpful assistant"

ui:
  display_type: "rich_terminal"
  logging_enabled: true
```

**Example**: [`single_agent.yaml`](../../massgen/configs/basic/single/single_agent.yaml)

### Multi-Agent Configuration

Multi-agent configs use the `agents` (plural) key with an array:

```yaml
# Multi-agent configuration
agents:
  - id: "gemini2.5flash"
    backend:
      type: "gemini"
      model: "gemini-2.5-flash"
      enable_web_search: true

  - id: "gpt5nano"
    backend:
      type: "openai"
      model: "gpt-5-nano"
      enable_web_search: true
      enable_code_interpreter: true

  - id: "grok3mini"
    backend:
      type: "grok"
      model: "grok-3-mini"
      enable_web_search: true

ui:
  display_type: "rich_terminal"
  logging_enabled: true
```

**Example**: [`three_agents_default.yaml`](../../massgen/configs/basic/multi/three_agents_default.yaml)

## Core Configuration Sections

### 1. Agent Definition

```yaml
agent:  # or agents: for multi-agent
  id: "unique_agent_id"
  system_message: "Custom instructions for this agent"
  backend:
    # Backend configuration (see below)
```

**Fields:**
- `id`: Unique identifier for the agent (required)
- `system_message`: Custom system prompt/instructions (optional)
- `backend`: Backend configuration (required)

### 2. Backend Configuration

```yaml
backend:
  type: "gemini"           # Backend type: openai, claude, gemini, grok, etc.
  model: "gemini-2.5-pro"  # Model name

  # Built-in tools (varies by backend)
  enable_web_search: true
  enable_code_execution: true
  enable_code_interpreter: true

  # MCP servers (optional)
  mcp_servers:
    - name: "discord"
      type: "stdio"
      command: "npx"
      args: ["-y", "mcp-discord"]

  # Tool filtering (optional)
  exclude_tools:
    - tool_name_to_exclude
  allowed_tools:
    - tool_name_to_allow
```

### 3. UI Configuration

```yaml
ui:
  display_type: "rich_terminal"  # or "simple", "json"
  logging_enabled: true           # Enable logging
```

### 4. Orchestrator Configuration

```yaml
orchestrator:
  snapshot_storage: "massgen_logs/snapshots"
  agent_temporary_workspace: "massgen_logs/temp_workspaces"

  # Multi-turn session storage (enabled by default in config wizard)
  session_storage: "sessions"

  # Context paths - give agents access to your project files
  context_paths:
    - path: "."  # Current directory (absolute or relative)
      permission: "write"  # "read" or "write" (final agent only)
    - path: "src"  # Additional paths
      permission: "write"
      protected_paths:  # Optional: files immune from modification
        - "config.json"
        - "secrets.env"

  # Coordination settings (optional)
  coordination:
    enable_planning_mode: true
    planning_mode_instruction: |
      Custom planning mode instructions
```

## Directory Structure

MassGen's 98 configurations are organized by category:

```
massgen/configs/
├── basic/                    # Basic configurations (20 configs)
│   ├── single/               # Single agent examples
│   └── multi/                # Multi-agent examples
├── providers/                # Provider-specific (15 configs)
│   ├── openai/
│   ├── claude/
│   ├── gemini/
│   ├── azure/
│   ├── local/
│   └── others/
├── tools/                    # Tool-focused configs (45+ configs)
│   ├── mcp/                  # MCP server examples
│   ├── planning/             # Planning mode examples
│   ├── filesystem/           # Filesystem operations
│   ├── web-search/           # Web search examples
│   └── code-execution/       # Code execution examples
├── teams/                    # Specialized teams (5 configs)
│   ├── creative/
│   └── research/
├── ag2/                      # AG2 framework (4 configs)
└── debug/                    # Debug configurations
```

## Finding the Right Configuration

### By Use Case

#### Code Generation & Execution
- **Single agent with code**: [`ag2_coder.yaml`](../../massgen/configs/ag2/ag2_coder.yaml)
- **Claude Code filesystem**: [`claude_code_single.yaml`](../../massgen/configs/tools/filesystem/claude_code_single.yaml)
- **Multi-agent filesystem**: [`five_agents_filesystem_mcp_planning_mode.yaml`](../../massgen/configs/tools/planning/five_agents_filesystem_mcp_planning_mode.yaml)

#### Research & Analysis
- **Research team**: [`research_team.yaml`](../../massgen/configs/teams/research/research_team.yaml)
- **News analysis**: [`news_analysis.yaml`](../../massgen/configs/teams/research/news_analysis.yaml)
- **Technical analysis**: [`technical_analysis.yaml`](../../massgen/configs/teams/research/technical_analysis.yaml)

#### Content Creation
- **Creative team**: [`creative_team.yaml`](../../massgen/configs/teams/creative/creative_team.yaml)
- **Image generation**: [`gpt4o_image_generation.yaml`](../../massgen/configs/basic/multi/gpt4o_image_generation.yaml)
- **Travel planning**: [`travel_planning.yaml`](../../massgen/configs/teams/creative/travel_planning.yaml)

#### Social Media & Communication
- **Discord integration**: [`five_agents_discord_mcp_planning_mode.yaml`](../../massgen/configs/tools/planning/five_agents_discord_mcp_planning_mode.yaml)
- **Twitter integration**: [`five_agents_twitter_mcp_planning_mode.yaml`](../../massgen/configs/tools/planning/five_agents_twitter_mcp_planning_mode.yaml)
- **Notion management**: [`five_agents_notion_mcp_planning_mode.yaml`](../../massgen/configs/tools/planning/five_agents_notion_mcp_planning_mode.yaml)

### By Backend

#### OpenAI / GPT Models
- **Single GPT-5 Nano**: [`gpt5_nano.yaml`](../../massgen/configs/providers/openai/gpt5_nano.yaml)
- **GPT-5**: [`gpt5.yaml`](../../massgen/configs/providers/openai/gpt5.yaml)
- **Multi-agent with GPT**: [`two_agents_gpt5.yaml`](../../massgen/configs/basic/multi/two_agents_gpt5.yaml)

#### Claude Models
- **Single Claude**: [`claude.yaml`](../../massgen/configs/providers/claude/claude.yaml)
- **Claude Code**: [`claude_code_single.yaml`](../../massgen/configs/tools/filesystem/claude_code_single.yaml)

#### Gemini Models
- **Single Gemini**: [`single_agent.yaml`](../../massgen/configs/basic/single/single_agent.yaml) (uses Gemini by default)
- **Gemini with Notion**: [`gemini_notion_mcp.yaml`](../../massgen/configs/tools/mcp/gemini_notion_mcp.yaml)

#### Grok Models
- **Single Grok**: [`grok_single_agent.yaml`](../../massgen/configs/providers/others/grok_single_agent.yaml)

#### Azure OpenAI
- **Azure single**: [`azure_openai_single.yaml`](../../massgen/configs/providers/azure/azure_openai_single.yaml)
- **Azure multi**: [`azure_openai_multi.yaml`](../../massgen/configs/providers/azure/azure_openai_multi.yaml)

#### Local Models
- **LM Studio**: [`lmstudio.yaml`](../../massgen/configs/providers/local/lmstudio.yaml)
- **vLLM**: [`three_agents_vllm.yaml`](../../massgen/configs/basic/multi/three_agents_vllm.yaml)

### By Agent Count

#### Single Agent (8+ configs)
- [`single_agent.yaml`](../../massgen/configs/basic/single/single_agent.yaml) - Gemini Flash
- [`single_gpt5nano.yaml`](../../massgen/configs/basic/single/single_gpt5nano.yaml) - GPT-5 Nano
- [`single_flash2.5.yaml`](../../massgen/configs/basic/single/single_flash2.5.yaml) - Gemini Flash 2.5

#### Two Agents (5+ configs)
- [`two_agents_gemini.yaml`](../../massgen/configs/basic/multi/two_agents_gemini.yaml)
- [`two_agents_gpt5.yaml`](../../massgen/configs/basic/multi/two_agents_gpt5.yaml)

#### Three Agents (8+ configs)
- [`three_agents_default.yaml`](../../massgen/configs/basic/multi/three_agents_default.yaml)
- [`three_agents_opensource.yaml`](../../massgen/configs/basic/multi/three_agents_opensource.yaml)
- [`gemini_4o_claude.yaml`](../../massgen/configs/basic/multi/gemini_4o_claude.yaml)

#### Five Agents (10+ configs)
- Planning mode configs (5 configs in `tools/planning/`)
- MCP test configs (2 configs: weather, travel)

### By Features

#### MCP Integration (26 configs)
Browse: [`massgen/configs/tools/mcp/`](../../massgen/configs/tools/mcp/)

Popular examples:
- Discord: [`claude_code_discord_mcp_example.yaml`](../../massgen/configs/tools/mcp/claude_code_discord_mcp_example.yaml)
- Notion: [`gemini_notion_mcp.yaml`](../../massgen/configs/tools/mcp/gemini_notion_mcp.yaml)
- Filesystem: [`gemini_mcp_filesystem_test.yaml`](../../massgen/configs/tools/mcp/gemini_mcp_filesystem_test.yaml)

#### Planning Mode (5 configs)
Browse: [`massgen/configs/tools/planning/`](../../massgen/configs/tools/planning/)

All planning mode configs:
- Discord, Filesystem, Notion, Twitter variants
- See [Planning Mode](./planning-mode.md) for details

#### Filesystem Operations (12+ configs)
Browse: [`massgen/configs/tools/filesystem/`](../../massgen/configs/tools/filesystem/)

Examples:
- [`claude_code_single.yaml`](../../massgen/configs/tools/filesystem/claude_code_single.yaml)
- [`gemini_gpt5nano_file_context_path.yaml`](../../massgen/configs/tools/filesystem/gemini_gpt5nano_file_context_path.yaml)
- [`gemini_gpt5nano_protected_paths.yaml`](../../massgen/configs/tools/filesystem/gemini_gpt5nano_protected_paths.yaml)

#### Multi-turn Sessions (4 configs)
Browse: [`massgen/configs/tools/filesystem/multiturn/`](../../massgen/configs/tools/filesystem/multiturn/)

#### AG2 Framework (4 configs)
Browse: [`massgen/configs/ag2/`](../../massgen/configs/ag2/)

## Customizing Configurations

### Modifying an Existing Config

1. **Copy the base config:**
```bash
cp massgen/configs/basic/single/single_agent.yaml my_custom_config.yaml
```

2. **Edit the configuration:**
```yaml
agent:
  id: "my_custom_agent"
  backend:
    type: "gemini"
    model: "gemini-2.5-pro"  # Change model
    enable_web_search: true
  system_message: "You are a specialized assistant for..."  # Add custom prompt
```

3. **Run with your config:**
```bash
uv run python -m massgen.cli --config my_custom_config.yaml "Your query"
```

### Common Customizations

#### Change Model

```yaml
backend:
  type: "openai"
  model: "gpt-4o-mini"  # Change this to any supported model
```

#### Add Web Search

```yaml
backend:
  enable_web_search: true  # Add this line
```

#### Add MCP Server

```yaml
backend:
  mcp_servers:
    - name: "discord"
      type: "stdio"
      command: "npx"
      args: ["-y", "mcp-discord", "--config", "${DISCORD_TOKEN}"]
      env:
        DISCORD_TOKEN: "${DISCORD_TOKEN}"
```

#### Enable Planning Mode

```yaml
orchestrator:
  coordination:
    enable_planning_mode: true
    planning_mode_instruction: |
      PLANNING MODE ACTIVE: Coordination phase only.
```

#### Add Custom System Message

```yaml
agent:
  system_message: |
    You are a specialized assistant for technical documentation.
    Always provide code examples and clear explanations.
```

#### Add Current Directory as Context Path (Multi-Turn Sessions)

For multi-turn sessions with filesystem support, add the current directory so agents can work in your project:

```yaml
orchestrator:
  session_storage: "sessions"  # Enable multi-turn sessions
  snapshot_storage: "snapshots"
  agent_temporary_workspace: "temp_workspaces"

  context_paths:
    - path: "."  # Current directory where you run MassGen
      permission: "write"  # Allow final agent to modify files
```

**Path Types:**
- **Relative paths** (`.`, `src`, `docs`) - resolved against current working directory
- **Absolute paths** (`/home/user/project`) - used as-is

**Permission Levels:**
- `read` - Agents can view files (all agents during coordination)
- `write` - Final winning agent can create/modify files

**Note:** During coordination, all context paths are read-only. Write permission only applies to the final agent during presentation phase.

## Environment Variables

Many configs use environment variables for API keys and tokens:

### Setup .env File

Create a `.env` file in your project root:

```bash
# OpenAI
OPENAI_API_KEY="your_openai_key"

# Anthropic Claude
ANTHROPIC_API_KEY="your_anthropic_key"

# Google Gemini
GOOGLE_API_KEY="your_google_key"

# xAI Grok
XAI_API_KEY="your_xai_key"

# MCP Servers
DISCORD_TOKEN="your_discord_token"
NOTION_TOKEN_ONE="your_notion_token"
TWITTER_API_KEY="your_twitter_key"
```

### Using Environment Variables in Configs

Reference env vars with `${VAR_NAME}` syntax:

```yaml
backend:
  type: "openai"
  # OPENAI_API_KEY is automatically read from environment

mcp_servers:
  discord:
    env:
      DISCORD_TOKEN: "${DISCORD_TOKEN}"  # Explicit reference
```

## Configuration Best Practices

### 1. Start Simple

Begin with basic configs and add complexity:
- Start: [`single_agent.yaml`](../../massgen/configs/basic/single/single_agent.yaml)
- Add tools: [`single_gpt5nano.yaml`](../../massgen/configs/basic/single/single_gpt5nano.yaml) (web search + code)
- Add MCP: [`claude_code_discord_mcp_example.yaml`](../../massgen/configs/tools/mcp/claude_code_discord_mcp_example.yaml)
- Add coordination: [`five_agents_discord_mcp_planning_mode.yaml`](../../massgen/configs/tools/planning/five_agents_discord_mcp_planning_mode.yaml)

### 2. Choose the Right Agent Count

- **Single agent**: Simple tasks, direct execution
- **2-3 agents**: Quick consensus, lightweight coordination
- **5 agents**: Complex tasks, diverse perspectives, robust voting

### 3. Enable Relevant Tools

Only enable tools you'll use:
```yaml
# Good: Specific tools for the task
enable_web_search: true        # For research tasks
enable_code_execution: true    # For coding tasks

# Avoid: Enabling everything unnecessarily
```

### 4. Use Planning Mode for Irreversible Actions

If your config uses MCP tools that:
- Post to social media (Discord, Twitter)
- Modify databases (Notion)
- Delete files (Filesystem)

→ Enable planning mode to prevent duplicate/premature actions

### 5. Customize System Messages

Tailor agent behavior with clear system messages:
```yaml
system_message: |
  You are a Python expert focused on clean, well-documented code.
  Always include type hints and docstrings.
  Prefer composition over inheritance.
```

## Troubleshooting Configurations

### Config Not Found

```bash
# Error: Config file not found
uv run python -m massgen.cli --config my_config.yaml "query"
```

**Solution:** Use full path or path relative to project root:
```bash
massgen --config @examples/basic_single_single_agent "query"
```

### Invalid YAML Syntax

**Problem:** YAML parsing errors

**Solutions:**
- Check indentation (use spaces, not tabs)
- Ensure colons have spaces after them: `key: value` not `key:value`
- Quote strings with special characters: `message: "Hello: world"`
- Validate YAML syntax online or with `yamllint`

### Missing API Keys

**Problem:** API key errors when running config

**Solutions:**
- Create `.env` file in project root
- Add required API keys for backends you're using
- Verify environment variable names match config references

### Backend Not Available

**Problem:** Backend type not recognized

**Solutions:**
- Check backend type spelling: `openai`, `claude`, `gemini`, `grok`, `azure_openai`
- Ensure MassGen is up to date: `uv pip install --upgrade -r requirements.txt`
- Verify API key is set for that backend

## All Available Configurations

**Total Configurations**: 98

Browse by category:
- **Basic** (20): [`massgen/configs/basic/`](../../massgen/configs/basic/)
- **Providers** (15): [`massgen/configs/providers/`](../../massgen/configs/providers/)
- **MCP Tools** (26): [`massgen/configs/tools/mcp/`](../../massgen/configs/tools/mcp/)
- **Planning Mode** (5): [`massgen/configs/tools/planning/`](../../massgen/configs/tools/planning/)
- **Filesystem** (12): [`massgen/configs/tools/filesystem/`](../../massgen/configs/tools/filesystem/)
- **Web Search** (7): [`massgen/configs/tools/web-search/`](../../massgen/configs/tools/web-search/)
- **Teams** (5): [`massgen/configs/teams/`](../../massgen/configs/teams/)
- **AG2** (4): [`massgen/configs/ag2/`](../../massgen/configs/ag2/)
- **Debug** (2): [`massgen/configs/debug/`](../../massgen/configs/debug/)

## Related Documentation

- [MCP Integration](./mcp-integration.md) - Using MCP servers and tools
- [Planning Mode](./planning-mode.md) - Coordinating with planning mode
- [Backend Support](./backend-support.md) - Understanding different backends
- [Multi-Agent Coordination](./multi-agent-coordination.md) - How agents work together

---

**Last Updated:** October 2025 | **MassGen Version:** v0.0.29+
