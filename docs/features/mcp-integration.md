# MCP Integration

**Introduced in:** v0.0.15 (September 2025)
**Extended in:** v0.0.17 (OpenAI), v0.0.18 (Chat Completions), v0.0.20 (Claude), v0.0.21 (Grok)

Model Context Protocol (MCP) enables MassGen agents to interact with external tools and services through a standardized interface. This allows agents to perform actions like posting to Discord, managing Notion pages, querying weather services, and more.

## Release History

| Version | Date | What Changed |
|---------|------|-------------|
| v0.0.15 | Sept 5, 2025 | **Initial MCP Framework** - Gemini MCP support, multi-server client, stdio & HTTP transports, circuit breaker patterns |
| v0.0.17 | Sept 10, 2025 | **OpenAI MCP Support** - Extended MCP integration to OpenAI backend, function calling integration |
| v0.0.18 | Sept 12, 2025 | **Chat Completions MCP** - All Chat Completions providers (Cerebras, Together, Fireworks, Groq, etc.) |
| v0.0.20 | Sept 17, 2025 | **Claude MCP Support** - Extended to Claude Messages API with recursive execution model |
| v0.0.21 | Sept 19, 2025 | **Grok MCP Integration** - Extended MCP support to Grok backend |
| v0.0.29 | Oct 8, 2025 | **Enhanced Tool Filtering** - Multi-level tool filtering (backend + MCP-server specific) |

## What is MCP in MassGen?

MCP (Model Context Protocol) provides a standard way to connect AI agents with external tools:

- **Standardized Tool Interface**: Consistent way to expose tools across different services
- **Multi-Backend Support**: Works with OpenAI, Claude, Gemini, Grok, and other backends
- **Dynamic Tool Discovery**: Agents automatically discover available tools from MCP servers
- **Isolated Execution**: Each agent can have its own MCP server instance and configuration

## Basic MCP Configuration

### Single Agent with MCP

Here's a basic example using Discord MCP with Claude Code:

```yaml
agent:
  id: "claude_code_discord"
  backend:
    type: "claude_code"
    cwd: "claude_code_workspace"
    permission_mode: "bypassPermissions"

    # MCP server configuration
    mcp_servers:
      discord:
        type: "stdio"
        command: "npx"
        args: ["-y", "mcp-discord", "--config", "${DISCORD_TOKEN}"]
        env:
          DISCORD_TOKEN: "${DISCORD_TOKEN}"
```

**Configuration**: [`claude_code_discord_mcp_example.yaml`](../../massgen/configs/tools/mcp/claude_code_discord_mcp_example.yaml)

### Multi-Agent with MCP

For multi-agent setups, each agent can have its own MCP configuration:

```yaml
agents:
  - id: "gemini_agent1"
    backend:
      type: "gemini"
      model: "gemini-2.5-pro"
      enable_web_search: true

      mcp_servers:
        - name: "discord"
          type: "stdio"
          command: "npx"
          args: ["-y", "mcp-discord", "--config", "${DISCORD_TOKEN}"]
          env:
            DISCORD_TOKEN: "${DISCORD_TOKEN}"
          security:
            level: "high"

  - id: "openai_agent"
    backend:
      type: "openai"
      model: "gpt-4o-mini"

      mcp_servers:
        - name: "discord"
          type: "stdio"
          command: "npx"
          args: ["-y", "mcp-discord", "--config", "${DISCORD_TOKEN}"]
          env:
            DISCORD_TOKEN: "${DISCORD_TOKEN}"
```

**Configuration**: [`five_agents_discord_mcp_planning_mode.yaml`](../../massgen/configs/tools/planning/five_agents_discord_mcp_planning_mode.yaml)

## MCP Server Examples

### Discord Integration

Connect agents to Discord for reading messages, posting updates, and managing channels.

**Setup Requirements:**
1. Install Discord MCP server: `npm install -g mcp-discord`
2. Set `DISCORD_TOKEN` in your `.env` file

**Configuration:**
```yaml
mcp_servers:
  - name: "discord"
    type: "stdio"
    command: "npx"
    args: ["-y", "mcp-discord", "--config", "${DISCORD_TOKEN}"]
    env:
      DISCORD_TOKEN: "${DISCORD_TOKEN}"
```

**Example Usage:**
```bash
uv run python -m massgen.cli \
  --config massgen/configs/tools/planning/five_agents_discord_mcp_planning_mode.yaml \
  "Check recent messages in our development channel and post a summary"
```

**Available Configs:**
- [`claude_code_discord_mcp_example.yaml`](../../massgen/configs/tools/mcp/claude_code_discord_mcp_example.yaml) - Single Claude Code agent
- [`five_agents_discord_mcp_planning_mode.yaml`](../../massgen/configs/tools/planning/five_agents_discord_mcp_planning_mode.yaml) - 5 agents with planning mode
- [`gpt5mini_claude_code_discord_mcp_example.yaml`](../../massgen/configs/tools/mcp/gpt5mini_claude_code_discord_mcp_example.yaml) - GPT-5 Mini with Claude Code

### Notion Integration

Manage Notion pages, databases, and content through MCP.

**Setup Requirements:**
1. Install Notion MCP server: `npm install -g @notionhq/notion-mcp-server`
2. Create a Notion integration at [notion.so/profile/integrations](https://www.notion.so/profile/integrations)
3. Share target pages with your integration
4. Set `NOTION_TOKEN_ONE` and `NOTION_TOKEN_TWO` in your `.env` file

**Configuration:**
```yaml
agents:
  - id: "gemini-2.5-pro1"
    backend:
      type: "gemini"
      model: "gemini-2.5-pro"

      mcp_servers:
        notionApi:
          type: "stdio"
          command: "npx"
          args: ["-y", "@notionhq/notion-mcp-server"]
          env:
            NOTION_TOKEN: "${NOTION_TOKEN_ONE}"

      # Exclude problematic tools
      exclude_tools:
        - post_search
```

**Example Usage:**
```bash
uv run python -m massgen.cli \
  --config massgen/configs/tools/mcp/gemini_notion_mcp.yaml \
  "Create a structured todo list in Notion under 'LLM Agent Research'"
```

**Available Configs:**
- [`gemini_notion_mcp.yaml`](../../massgen/configs/tools/mcp/gemini_notion_mcp.yaml) - Dual Gemini agents with separate Notion tokens
- [`five_agents_notion_mcp_planning_mode.yaml`](../../massgen/configs/tools/planning/five_agents_notion_mcp_planning_mode.yaml) - 5 agents with planning mode

### Twitter Integration

Post tweets, read timelines, and manage Twitter interactions.

**Setup Requirements:**
1. Install Twitter MCP server: `npm install -g mcp-twitter`
2. Set `TWITTER_API_KEY` and `TWITTER_API_SECRET` in your `.env` file

**Configuration:**
```yaml
mcp_servers:
  twitter:
    type: "stdio"
    command: "npx"
    args: ["-y", "mcp-twitter"]
    env:
      TWITTER_API_KEY: "${TWITTER_API_KEY}"
      TWITTER_API_SECRET: "${TWITTER_API_SECRET}"
```

**Available Configs:**
- [`claude_code_twitter_mcp_example.yaml`](../../massgen/configs/tools/mcp/claude_code_twitter_mcp_example.yaml) - Claude Code with Twitter
- [`five_agents_twitter_mcp_planning_mode.yaml`](../../massgen/configs/tools/planning/five_agents_twitter_mcp_planning_mode.yaml) - 5 agents with planning mode

### Weather Services

Query weather information through MCP.

**Configuration:**
```yaml
mcp_servers:
  - name: "weather"
    type: "stdio"
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-weather"]
```

**Available Configs:**
- [`five_agents_weather_mcp_test.yaml`](../../massgen/configs/tools/mcp/five_agents_weather_mcp_test.yaml) - 5 agents with weather API

### Travel Planning

Access travel information and planning tools.

**Available Configs:**
- [`five_agents_travel_mcp_test.yaml`](../../massgen/configs/tools/mcp/five_agents_travel_mcp_test.yaml) - 5 agents with travel planning tools

### Filesystem Operations (Gemini)

Gemini models have native filesystem MCP support for file operations.

**Configuration:**
```yaml
agents:
  - id: "gemini_agent1"
    backend:
      type: "gemini"
      model: "gemini-2.5-pro"
      cwd: "workspace1"  # Working directory for file operations
```

**Example Usage:**
```bash
uv run python -m massgen.cli \
  --config massgen/configs/tools/mcp/gemini_mcp_filesystem_test.yaml \
  "Create a Python script with hello world in different languages"
```

**Available Configs:**
- [`gemini_mcp_filesystem_test.yaml`](../../massgen/configs/tools/mcp/gemini_mcp_filesystem_test.yaml) - Dual agents with separate workspaces
- [`gemini_mcp_filesystem_test_single_agent.yaml`](../../massgen/configs/tools/mcp/gemini_mcp_filesystem_test_single_agent.yaml) - Single agent
- [`gemini_mcp_filesystem_test_sharing.yaml`](../../massgen/configs/tools/mcp/gemini_mcp_filesystem_test_sharing.yaml) - Agents sharing workspace
- [`gemini_mcp_filesystem_test_with_claude_code.yaml`](../../massgen/configs/tools/mcp/gemini_mcp_filesystem_test_with_claude_code.yaml) - Mixed Gemini + Claude Code

## Tool Filtering

MassGen provides flexible tool filtering to control which MCP tools agents can use.

### Backend-Level Filtering

Exclude tools at the backend configuration level:

```yaml
backend:
  type: "openai"
  model: "gpt-4o-mini"
  exclude_tools:
    - mcp__discord__discord_send_webhook_message
    - mcp__discord__discord_edit_webhook_message
  mcp_servers:
    - name: "discord"
      type: "stdio"
      command: "npx"
      args: ["-y", "mcp-discord"]
```

### MCP-Server-Specific Filtering

Override backend settings per MCP server with `allowed_tools`:

```yaml
backend:
  type: "openai"
  model: "gpt-4o-mini"
  mcp_servers:
    - name: "discord"
      type: "stdio"
      command: "npx"
      args: ["-y", "mcp-discord"]
      allowed_tools:
        - mcp__discord__discord_read_messages
        - mcp__discord__discord_send_message
```

### Combined Filtering

Both `exclude_tools` (backend-level) and `allowed_tools` (MCP-server-specific) can be combined for fine-grained control.

**Use Cases:**
- Prevent agents from using dangerous operations (webhooks, deletions)
- Limit agents to read-only operations during coordination
- Give different agents different tool access to the same MCP server

## Multiple MCP Servers

Agents can connect to multiple MCP servers simultaneously:

```yaml
backend:
  type: "gemini"
  model: "gemini-2.5-pro"

  mcp_servers:
    - name: "discord"
      type: "stdio"
      command: "npx"
      args: ["-y", "mcp-discord"]
      env:
        DISCORD_TOKEN: "${DISCORD_TOKEN}"

    - name: "weather"
      type: "stdio"
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-weather"]

    - name: "notion"
      type: "stdio"
      command: "npx"
      args: ["-y", "@notionhq/notion-mcp-server"]
      env:
        NOTION_TOKEN: "${NOTION_TOKEN}"
```

**Configuration**: [`multimcp_gemini.yaml`](../../massgen/configs/tools/mcp/multimcp_gemini.yaml)

## Backend-Specific MCP Configuration

### OpenAI / GPT Models

```yaml
backend:
  type: "openai"
  model: "gpt-4o-mini"
  mcp_servers:
    - name: "discord"
      type: "stdio"
      command: "npx"
      args: ["-y", "mcp-discord"]
```

### Claude Models

```yaml
backend:
  type: "claude"
  model: "claude-sonnet-4-20250514"
  mcp_servers:
    - name: "discord"
      type: "stdio"
      command: "npx"
      args: ["-y", "mcp-discord"]
```

### Claude Code

Claude Code uses a dictionary format instead of a list:

```yaml
backend:
  type: "claude_code"
  cwd: "workspace"
  permission_mode: "bypassPermissions"
  mcp_servers:
    discord:  # Dictionary key instead of name field
      type: "stdio"
      command: "npx"
      args: ["-y", "mcp-discord"]
```

### Gemini Models

```yaml
backend:
  type: "gemini"
  model: "gemini-2.5-pro"
  mcp_servers:
    - name: "discord"
      type: "stdio"
      command: "npx"
      args: ["-y", "mcp-discord"]
```

### Grok Models

```yaml
backend:
  type: "grok"
  model: "grok-3-mini"
  mcp_servers:
    - name: "discord"
      type: "stdio"
      command: "npx"
      args: ["-y", "mcp-discord"]
```

## Environment Variables

MCP configurations support environment variable substitution using `${VAR_NAME}` syntax:

```yaml
mcp_servers:
  discord:
    type: "stdio"
    command: "npx"
    args: ["-y", "mcp-discord", "--config", "${DISCORD_TOKEN}"]
    env:
      DISCORD_TOKEN: "${DISCORD_TOKEN}"
      CUSTOM_VAR: "${MY_CUSTOM_VAR}"
```

Store your credentials in a `.env` file:

```bash
# .env
DISCORD_TOKEN="your_discord_bot_token"
NOTION_TOKEN_ONE="your_notion_token_1"
NOTION_TOKEN_TWO="your_notion_token_2"
TWITTER_API_KEY="your_twitter_key"
```

## MCP with Planning Mode

When using MCP tools with irreversible actions (Discord posts, file operations), enable **Planning Mode** to prevent duplicate actions during coordination.

See [Planning Mode Documentation](./planning-mode.md) for details.

**Quick Example:**

```yaml
orchestrator:
  coordination:
    enable_planning_mode: true
    planning_mode_instruction: |
      PLANNING MODE ACTIVE: You are in the coordination phase.
      DO NOT execute any actual MCP commands.
      Use only 'vote' or 'new_answer' tools for coordination.
```

## Common Issues

### MCP Server Not Found

**Problem:** `npx: command not found` or MCP server fails to start

**Solutions:**
- Ensure Node.js and npm are installed: `node --version && npm --version`
- Install MCP server globally: `npm install -g mcp-discord`
- Check that npx is in your PATH

### Authentication Errors

**Problem:** MCP server fails with authentication errors

**Solutions:**
- Verify environment variables are set in `.env` file
- Check that tokens/API keys are valid
- For Notion: ensure integration has access to target pages
- For Discord: verify bot token and permissions

### Tool Not Available

**Problem:** Agent can't see MCP tools

**Solutions:**
- Check `exclude_tools` configuration isn't blocking the tool
- Verify MCP server started successfully (check logs)
- Ensure backend supports MCP (all major backends do)

### Rate Limiting

**Problem:** MCP operations fail due to rate limits

**Solutions:**
- Reduce number of agents using the same MCP server
- Use separate tokens/accounts for different agents (see Notion example)
- Enable planning mode to reduce duplicate API calls

## All MCP Configurations

Browse all available MCP configurations in:
- [`massgen/configs/tools/mcp/`](../../massgen/configs/tools/mcp/) - 26 MCP example configs
- [`massgen/configs/tools/planning/`](../../massgen/configs/tools/planning/) - MCP with planning mode

## Related Documentation

- [Planning Mode](./planning-mode.md) - Prevent duplicate MCP actions during coordination
- [Configuration Guide](./configuration-guide.md) - Understanding config file structure
- [Multi-Agent Coordination](./multi-agent-coordination.md) - How agents collaborate with MCP tools
- [Backend Support](./backend-support.md) - MCP support by backend

---

**Last Updated:** October 2025 | **MassGen Version:** v0.0.29+
