# MassGen Configuration Guide

This guide explains the organization and usage of MassGen configuration files.

## Directory Structure

```
massgen/configs/
├── basic/                 # Simple configs to get started
│   ├── single/           # Single agent examples
│   └── multi/            # Multi-agent examples
├── tools/                 # Tool-enabled configurations
│   ├── mcp/              # MCP server integrations
│   ├── web-search/       # Web search enabled configs
│   ├── code-execution/   # Code interpreter/execution
│   └── filesystem/       # File operations & workspace
├── providers/             # Provider-specific examples
│   ├── openai/           # GPT-5 series configs
│   ├── claude/           # Claude API configs
│   ├── gemini/           # Gemini configs
│   ├── azure/            # Azure OpenAI
│   ├── local/            # LMStudio, local models
│   └── others/           # Cerebras, Grok, Qwen, ZAI
├── teams/                # Pre-configured specialized teams
│   ├── creative/         # Creative writing teams
│   ├── research/         # Research & analysis
│   └── development/      # Coding teams
└── docs/                 # Setup guides and documentation
```

## CLI Command Line Arguments

| Parameter          | Description |
|-------------------|-------------|
| `--config`         | Path to YAML configuration file with agent definitions, model parameters, backend parameters and UI settings |
| `--backend`        | Backend type for quick setup without a config file (`claude`, `claude_code`, `gemini`, `grok`, `openai`, `azure_openai`, `zai`). Optional for [models with default backends](../utils.py).|
| `--model`          | Model name for quick setup (e.g., `gemini-2.5-flash`, `gpt-5-nano`, ...). `--config` and `--model` are mutually exclusive - use one or the other. |
| `--system-message` | System prompt for the agent in quick setup mode. If `--config` is provided, `--system-message` is omitted. |
| `--no-display`     | Disable real-time streaming UI coordination display (fallback to simple text output).|
| `--no-logs`        | Disable real-time logging.|
| `--debug`          | Enable debug mode with verbose logging (NEW in v0.0.13). Shows detailed orchestrator activities, agent messages, backend operations, and tool calls. Debug logs are saved to `agent_outputs/log_{time}/massgen_debug.log`. |
| `"<your question>"`         | Optional single-question input; if omitted, MassGen enters interactive chat mode. |

## Quick Start Examples

### 🌟 Recommended Showcase Example

**Best starting point for multi-agent collaboration:**
```bash
# Three powerful agents (Gemini, GPT-5, Grok) with enhanced workspace tools
uv run python -m massgen.cli --config massgen/configs/basic/multi/three_agents_default.yaml "Your complex task"
```

This configuration combines:
- **Gemini 2.5 Flash** - Fast, versatile with web search
- **GPT-5 Nano** - Advanced reasoning with code interpreter
- **Grok-3 Mini** - Efficient with real-time web search

### Quick Setup Without Config Files

**Single agent with model name only:**
```bash
# Quick test with any supported model - no configuration needed
uv run python -m massgen.cli --model claude-3-5-sonnet-latest "What is machine learning?"
uv run python -m massgen.cli --model gemini-2.5-flash "Explain quantum computing"
uv run python -m massgen.cli --model gpt-5-nano "Summarize the latest AI developments"
```

**Interactive Mode:**
```bash
# Start interactive chat (no initial question)
uv run python -m massgen.cli --config massgen/configs/basic/multi/three_agents_default.yaml

# Debug mode for troubleshooting
uv run python -m massgen.cli --config massgen/configs/basic/multi/three_agents_default.yaml --debug "Your question"
```

### Basic Usage

For simple single-agent setups:
```bash
uv run python -m massgen.cli --config massgen/configs/basic/single/single_agent.yaml "Your question"
```

### Tool-Enabled Configurations

#### MCP (Model Context Protocol) Servers
MCP enables agents to use external tools and services:
```bash
# Weather queries
uv run python -m massgen.cli --config massgen/configs/tools/mcp/gemini_mcp_example.yaml "What's the weather in Tokyo?"

# Discord integration
uv run python -m massgen.cli --config massgen/configs/tools/mcp/claude_code_discord_mcp_example.yaml "Extract latest messages"
```

#### Web Search
For agents with web search capabilities:
```bash
uv run python -m massgen.cli --config massgen/configs/tools/web-search/claude_streamable_http_test.yaml "Search for latest news"
```

#### Code Execution
For code interpretation and execution:
```bash
uv run python -m massgen.cli --config massgen/configs/tools/code-execution/multi_agent_playwright_automation.yaml "Browse and analyze websites"
```

#### Filesystem Operations
For file manipulation, workspace management, and copy tools:
```bash
# Single agent with enhanced file operations
uv run python -m massgen.cli --config massgen/configs/tools/filesystem/claude_code_single.yaml "Analyze this codebase"

# Multi-agent workspace collaboration with copy tools (NEW in v0.0.22)
uv run python -m massgen.cli --config massgen/configs/tools/filesystem/claude_code_context_sharing.yaml "Create shared workspace files"
```

### Provider-Specific Examples

Each provider has unique features and capabilities:

#### OpenAI (GPT-5 Series)
```bash
uv run python -m massgen.cli --config massgen/configs/providers/openai/gpt5.yaml "Complex reasoning task"
```

#### Claude
```bash
uv run python -m massgen.cli --config massgen/configs/providers/claude/claude_mcp_example.yaml "Creative writing task"
```

#### Gemini
```bash
uv run python -m massgen.cli --config massgen/configs/providers/gemini/gemini_mcp_example.yaml "Research task"
```

#### Local Models
```bash
uv run python -m massgen.cli --config massgen/configs/providers/local/lmstudio.yaml "Run with local model"
```

### Pre-Configured Teams

Teams are specialized multi-agent setups for specific domains:

#### Creative Teams
```bash
uv run python -m massgen.cli --config massgen/configs/teams/creative/creative_team.yaml "Write a story"
```

#### Research Teams
```bash
uv run python -m massgen.cli --config massgen/configs/teams/research/research_team.yaml "Analyze market trends"
```

#### Development Teams
```bash
uv run python -m massgen.cli --config massgen/configs/teams/development/zai_coding_team.yaml "Build a web app"
```

## Configuration File Format

### Single Agent
```yaml
agent:
  id: "agent_name"
  backend:
    type: "provider_type"
    model: "model_name"
    # Additional backend settings
  system_message: "Agent instructions"

ui:
  display_type: "rich_terminal"
  logging_enabled: true
```

### Multi-Agent
```yaml
agents:
  - id: "agent1"
    backend:
      type: "provider1"
      model: "model1"
    system_message: "Agent 1 role"

  - id: "agent2"
    backend:
      type: "provider2"
      model: "model2"
    system_message: "Agent 2 role"

ui:
  display_type: "rich_terminal"
  logging_enabled: true
```

### MCP Server Configuration
```yaml
backend:
  type: "provider"
  model: "model_name"
  mcp_servers:
    server_name:
      type: "stdio"
      command: "command"
      args: ["arg1", "arg2"]
      env:
        KEY: "${ENV_VAR}"
```

## Finding the Right Configuration

1. **New Users**: Start with `basic/single/` or `basic/multi/`
2. **Need Tools**: Check `tools/` subdirectories for specific capabilities
3. **Specific Provider**: Look in `providers/` for your provider
4. **Complex Tasks**: Use pre-configured `teams/`

## Environment Variables

Most configurations use environment variables for API keys:
- Set up your `.env` file based on `.env.example`
- Provider-specific keys: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.
- MCP server keys: `DISCORD_BOT_TOKEN`, `BRAVE_API_KEY`, etc.

## Release History & Examples

### v0.0.23 - Latest
**New Features:** Backend Architecture Refactoring, Formatter Module
- Major code consolidation with new `base_with_mcp.py` class reducing ~1,932 lines across backends
- Extracted message and tool formatting logic into dedicated `massgen/formatter/` module
- Streamlined chat_completions.py, claude.py, and response.py for better maintainability

### v0.0.22
**New Features:** Workspace Copy Tools via MCP, Configuration Organization
- All configs now organized by provider & use case (basic/, providers/, tools/, teams/)
- Use same configs as v0.0.21 for compatibility, but now with improved performance

**Case Study:** [Advanced Filesystem with User Context Path Support](../../docs/case_studies/v0.0.21-v0.0.22-filesystem-permissions.md)
```bash
# Multi-agent collaboration with granular filesystem permissions
uv run python -m massgen.cli --config massgen/configs/tools/filesystem/gpt5mini_cc_fs_context_path.yaml "Enhance the website in massgen/configs/resources with: 1) A dark/light theme toggle with smooth transitions, 2) An interactive feature that helps users engage with the blog content (your choice - could be search, filtering by topic, reading time estimates, social sharing, reactions, etc.), and 3) Visual polish with CSS animations or transitions that make the site feel more modern and responsive. Use vanilla JavaScript and be creative with the implementation details."
```

### v0.0.21
**New Features:** Advanced Filesystem Permissions, Grok MCP Integration
- `massgen/configs/tools/mcp/grok3_mini_mcp_example.yaml` - Grok with MCP tools
- `massgen/configs/tools/filesystem/fs_permissions_test.yaml` - Permission-controlled file sharing
- `massgen/configs/tools/filesystem/claude_code_context_sharing.yaml` - Agent workspace sharing

### v0.0.20
**New Features:** Claude MCP Support with Recursive Execution
- `massgen/configs/tools/mcp/claude_mcp_example.yaml` - Claude with MCP tools
- `massgen/configs/tools/mcp/claude_mcp_test.yaml` - Testing Claude MCP capabilities

### v0.0.17
**New Features:** OpenAI MCP Integration
- `massgen/configs/tools/mcp/gpt5_mini_mcp_example.yaml` - GPT-5 with MCP tools
- `massgen/configs/tools/mcp/gpt5mini_claude_code_discord_mcp_example.yaml` - Multi-agent MCP

### v0.0.16
**New Features:** Unified Filesystem Support with MCP Integration
**Case Study:** [Cross-Backend Collaboration with Gemini MCP Filesystem](../../docs/case_studies/unified-filesystem-mcp-integration.md)
```bash
# Gemini and Claude Code agents with unified filesystem via MCP
uv run python -m massgen.cli --config massgen/configs/tools/mcp/gemini_mcp_filesystem_test_with_claude_code.yaml "Create a presentation that teaches a reinforcement learning algorithm and output it in LaTeX Beamer format. No figures should be added."
```

### v0.0.15
**New Features:** Gemini MCP Integration
- `massgen/configs/tools/mcp/gemini_mcp_example.yaml` - Gemini with weather MCP
- `massgen/configs/tools/mcp/multimcp_gemini.yaml` - Multiple MCP servers

### v0.0.12 - v0.0.14
**New Features:** Enhanced Logging and Workspace Management
**Case Study:** [Claude Code Workspace Management with Comprehensive Logging](../../docs/case_studies/claude-code-workspace-management.md)
```bash
# Multi-agent Claude Code collaboration with enhanced workspace isolation
uv run python -m massgen.cli --config massgen/configs/tools/filesystem/claude_code_context_sharing.yaml "Create a website about a diverse set of fun facts about LLMs, placing the output in one index.html file"
```

### v0.0.10
**New Features:** Azure OpenAI Support
- `massgen/configs/providers/azure/azure_openai_single.yaml` - Azure single agent
- `massgen/configs/providers/azure/azure_openai_multi.yaml` - Azure multi-agent

### v0.0.7
**New Features:** Local Model Support with LM Studio
- `massgen/configs/providers/local/lmstudio.yaml` - Local model inference

### v0.0.5
**New Features:** Claude Code Integration
- `massgen/configs/tools/filesystem/claude_code_single.yaml` - Claude Code with dev tools
- `massgen/configs/tools/filesystem/claude_code_flash2.5.yaml` - Multi-agent with Claude Code

## Naming Convention

To improve clarity and discoverability, we follow this naming pattern:

**Format: `{agents}_{features}_{description}.yaml`**

### 1. Agents (who's participating)
- `single-{provider}` - Single agent (e.g., `single-claude`, `single-gemini`)
- `{provider1}-{provider2}` - Two agents (e.g., `claude-gemini`, `gemini-gpt5`)
- `three-mixed` - Three agents from different providers
- `team-{type}` - Specialized teams (e.g., `team-creative`, `team-research`)

### 2. Features (what tools/capabilities)
- `basic` - No special tools, just conversation
- `mcp` - MCP server integration
- `mcp-{service}` - Specific MCP service (e.g., `mcp-discord`, `mcp-weather`)
- `mcp-multi` - Multiple MCP servers
- `websearch` - Web search enabled
- `codeexec` - Code execution/interpreter
- `filesystem` - File operations and workspace management

### 3. Description (purpose/context - optional)
- `showcase` - Demonstration/getting started example
- `test` - Testing configuration
- `research` - Research and analysis tasks
- `dev` - Development and coding tasks
- `collab` - Collaboration example

### Examples
```
# Current → Suggested
three_agents_default.yaml → three-mixed_basic_showcase.yaml
grok3_mini_mcp_example.yaml → single-grok_mcp-weather_test.yaml
claude_code_discord_mcp_example.yaml → single-claude_mcp-discord_demo.yaml
gpt5mini_claude_code_discord_mcp_example.yaml → claude-gpt5_mcp-discord_collab.yaml
```

**Note:** Existing configs maintain their current names for compatibility. New configs should follow this convention.

## Additional Documentation

For detailed setup guides:
- Discord MCP: `docs/DISCORD_MCP_SETUP.md`
- Twitter MCP: `docs/TWITTER_MCP_ENESCINAR_SETUP.md`
- Main README: See repository root for comprehensive documentation
