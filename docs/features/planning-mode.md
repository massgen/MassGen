# Planning Mode

**Introduced in:** v0.0.29 | **Video Demo:** [MassGen v0.0.29 MCP Planning Mode](https://youtu.be/jLrMMEIr118)

Planning Mode is a coordination strategy that enables agents to plan MCP tool usage without execution during collaboration phases. This prevents irreversible actions during coordination while allowing full execution by the winning agent during final presentation.

## The Problem

In multi-agent coordination, agents collaborate through multiple rounds of voting and refinement. Without Planning Mode:

- **Duplicate Actions**: Multiple agents might post to Discord/Twitter during coordination
- **Premature Execution**: File operations or API calls happen before the best approach is determined
- **Irreversible Mistakes**: External actions (tweets, Discord messages, file deletions) cannot be undone
- **Resource Waste**: API calls and rate limits consumed during planning phase

## How Planning Mode Solves This

Planning Mode introduces **separation of planning and execution**:

### Coordination Phase (Planning)
- Agents describe their intended actions
- Tools are planned but NOT executed
- Only coordination tools (`vote`, `new_answer`) are available
- Agents collaborate to determine the best approach

### Final Presentation (Execution)
- Planning mode is disabled
- The winning agent executes their plan
- All MCP tools are fully available
- Actual actions are performed

## Configuration

### Basic Setup

Enable Planning Mode in your orchestrator configuration:

```yaml
orchestrator:
  coordination:
    enable_planning_mode: true
    planning_mode_instruction: |
      PLANNING MODE ACTIVE: You are currently in the coordination phase.
      During this phase, you should:
      1. Describe your intended actions and reasoning
      2. Analyze other agents' proposals
      3. Use only the 'vote' or 'new_answer' tools for coordination
      4. DO NOT execute any actual MCP commands
      5. Save tool execution for the final presentation phase
```

### Custom Instructions

Customize the planning instruction based on your use case:

**For Discord/Social Media:**
```yaml
planning_mode_instruction: |
  PLANNING MODE ACTIVE: You are in the coordination phase.
  DO NOT execute any actual Discord commands or API calls.
  Example: "I would post: 'Hello team!'" rather than actually posting.
```

**For Filesystem Operations:**
```yaml
planning_mode_instruction: |
  PLANNING MODE ACTIVE: You are in the coordination phase.
  DO NOT execute any actual filesystem operations.
  Example: "I would create a 'src' directory and write main.py..." rather than creating them.
```

**For Notion/Database Operations:**
```yaml
planning_mode_instruction: |
  PLANNING MODE ACTIVE: You are in the coordination phase.
  DO NOT execute any Notion commands or database modifications.
  Example: "I would create a database with properties..." rather than actually creating it.
```

## Example Configurations

### Discord with Planning Mode

Prevent duplicate Discord messages during coordination:

```yaml
agents:
  - id: "gemini_discord_agent"
    backend:
      type: "gemini"
      model: "gemini-2.5-flash"
      mcp_servers:
        - name: "discord"
          type: "stdio"
          command: "npx"
          args: ["-y", "mcp-discord", "--config", "${DISCORD_TOKEN}"]

  - id: "openai_discord_agent"
    backend:
      type: "openai"
      model: "gpt-4o-mini"
      mcp_servers:
        - name: "discord"
          type: "stdio"
          command: "npx"
          args: ["-y", "mcp-discord", "--config", "${DISCORD_TOKEN}"]

orchestrator:
  coordination:
    enable_planning_mode: true
    planning_mode_instruction: |
      PLANNING MODE ACTIVE: Coordination phase.
      DO NOT execute Discord commands.
      Use only 'vote' or 'new_answer' tools.
```

**Usage:**
```bash
massgen --config @examples/tools/planning/five_agents_discord_mcp_planning_mode \
  "Check recent messages in #dev channel and post a summary"
```

**Configuration**: [`five_agents_discord_mcp_planning_mode.yaml`](../../massgen/configs/tools/planning/five_agents_discord_mcp_planning_mode.yaml)

### Filesystem with Planning Mode

Coordinate file operations before execution:

```yaml
agents:
  - id: "gemini_filesystem"
    backend:
      type: "gemini"
      model: "gemini-2.5-flash"
      mcp_servers:
        - name: "filesystem"
          type: "stdio"
          command: "npx"
          args: ["-y", "@modelcontextprotocol/server-filesystem", "."]

orchestrator:
  coordination:
    enable_planning_mode: true
    planning_mode_instruction: |
      PLANNING MODE ACTIVE: Coordination phase.
      DO NOT execute filesystem operations.
      Describe your intended file structure.
```

**Usage:**
```bash
massgen --config @examples/tools/planning/five_agents_filesystem_mcp_planning_mode \
  "Create a Python web app project structure with src, tests, and docs directories"
```

**Configuration**: [`five_agents_filesystem_mcp_planning_mode.yaml`](../../massgen/configs/tools/planning/five_agents_filesystem_mcp_planning_mode.yaml)

### Notion with Planning Mode

Plan database structure before creating pages:

```yaml
agents:
  - id: "gemini_notion"
    backend:
      type: "gemini"
      model: "gemini-2.5-pro"
      mcp_servers:
        - name: "notionApi"
          type: "stdio"
          command: "npx"
          args: ["-y", "@notionhq/notion-mcp-server"]
          env:
            NOTION_TOKEN: "${NOTION_TOKEN_ONE}"

orchestrator:
  coordination:
    enable_planning_mode: true
    planning_mode_instruction: |
      PLANNING MODE ACTIVE: Coordination phase.
      DO NOT execute Notion commands.
      Describe your database design.
```

**Configuration**: [`five_agents_notion_mcp_planning_mode.yaml`](../../massgen/configs/tools/planning/five_agents_notion_mcp_planning_mode.yaml)

### Twitter with Planning Mode

Draft tweets collaboratively before posting:

```yaml
orchestrator:
  coordination:
    enable_planning_mode: true
    planning_mode_instruction: |
      PLANNING MODE ACTIVE: Coordination phase.
      DO NOT execute Twitter commands.
      Draft your tweet content for review.
```

**Configuration**: [`five_agents_twitter_mcp_planning_mode.yaml`](../../massgen/configs/tools/planning/five_agents_twitter_mcp_planning_mode.yaml)

## Multi-Backend Support

Planning Mode works across all major backends:

- ✅ **OpenAI** (Chat Completions API)
- ✅ **Claude** (Anthropic API)
- ✅ **Gemini** (Google AI Studio) - includes session-based tool execution
- ✅ **Grok** (xAI API)
- ✅ **Claude Code** (native support)
- ✅ **Response API backends** (OpenAI-compatible)

## When to Use Planning Mode

### ✅ Enable Planning Mode When:

- **Using MCP tools with irreversible actions** (Discord, Twitter, file operations)
- **Multiple agents coordinating** with external services
- **You want collaborative planning** before execution
- **Preventing duplicate API calls** during coordination
- **Rate limits are a concern**

### ❌ Planning Mode Not Needed When:

- **Single agent workflows** (no coordination phase)
- **Read-only MCP tools** (weather queries, search)
- **No coordination rounds** (direct execution)
- **Non-destructive operations** only

## Example Workflows

### Social Media Management

Five agents collaborate on tweet strategy, winning agent posts:

```bash
massgen --config @examples/tools/planning/five_agents_twitter_mcp_planning_mode \
  "Analyze our brand voice and create an engaging tweet about our new feature"
```

**What happens:**
1. **Round 1**: Agents analyze requirements and draft approaches (planning only)
2. **Round 2**: Agents vote and refine tweet content (planning only)
3. **Final**: Winning agent posts the tweet (execution)

### Team Communication

Agents analyze Discord messages and coordinate response:

```bash
massgen --config @examples/tools/planning/five_agents_discord_mcp_planning_mode \
  "Check #support channel, summarize issues, post helpful guidance"
```

**Benefits:**
- No duplicate Discord messages during coordination
- Team agrees on best response before posting
- Single, well-crafted message instead of 5 competing messages

### Project Setup

Agents collaborate on project structure before creating files:

```bash
massgen --config @examples/tools/planning/five_agents_filesystem_mcp_planning_mode \
  "Create a FastAPI project with auth, database, and API endpoints"
```

**Benefits:**
- Agents agree on directory structure before creation
- No duplicate or conflicting files
- Clean, organized final structure

## Technical Details

### Implementation

Planning Mode is implemented at the backend level:

- **Backend Enhancement**: All backends check planning mode state
- **Tool Filtering**: MCP tools are blocked during coordination
- **Coordination Tools**: `vote` and `new_answer` remain available
- **State Management**: Planning mode toggles between coordination and execution phases

### Backend-Specific Features

**Gemini Backend:**
- Session-based tool execution in planning mode
- Native filesystem MCP support with planning integration

**OpenAI/Claude:**
- Tool filtering via Chat Completions API
- Consistent behavior across Response and Completion modes

**Claude Code:**
- Full planning mode support with native tools
- Workspace isolation during planning phase

### Orchestrator Integration

Planning Mode integrates with the orchestrator's coordination system:

1. **Coordination Phase**: Planning mode enabled, MCP tools blocked
2. **Voting**: Agents use `vote` tool to select best approach
3. **Refinement**: Agents use `new_answer` to improve proposals
4. **Final Presentation**: Planning mode disabled, full tool access restored
5. **Execution**: Winning agent executes their plan

## All Planning Mode Configurations

| Configuration | MCP Server | Agents | Description |
|--------------|------------|--------|-------------|
| [`five_agents_discord_mcp_planning_mode.yaml`](../../massgen/configs/tools/planning/five_agents_discord_mcp_planning_mode.yaml) | Discord | 5 | Prevent duplicate Discord messages |
| [`five_agents_filesystem_mcp_planning_mode.yaml`](../../massgen/configs/tools/planning/five_agents_filesystem_mcp_planning_mode.yaml) | Filesystem | 5 | Coordinate file operations |
| [`five_agents_notion_mcp_planning_mode.yaml`](../../massgen/configs/tools/planning/five_agents_notion_mcp_planning_mode.yaml) | Notion | 5 | Plan database structure |
| [`five_agents_twitter_mcp_planning_mode.yaml`](../../massgen/configs/tools/planning/five_agents_twitter_mcp_planning_mode.yaml) | Twitter | 5 | Draft tweets collaboratively |
| [`gpt5_mini_case_study_mcp_planning_mode.yaml`](../../massgen/configs/tools/planning/gpt5_mini_case_study_mcp_planning_mode.yaml) | Filesystem | Case Study | Planning mode demonstration |

## Troubleshooting

### Agents Still Executing During Coordination

**Problem**: Agents are executing MCP tools during coordination phase

**Solutions:**
- Verify `enable_planning_mode: true` is in orchestrator config
- Check that `planning_mode_instruction` is present and clear
- Ensure backend supports planning mode (all major backends do)

### Tools Not Available in Final Phase

**Problem**: Winning agent can't execute tools during final presentation

**Solutions:**
- Planning mode should automatically disable during final phase
- Check orchestrator logs for planning mode state transitions
- Verify MCP servers are running correctly

### Planning Instructions Ignored

**Problem**: Agents don't follow planning mode instructions

**Solutions:**
- Make planning instructions more explicit and detailed
- Use stronger language ("DO NOT execute", not "avoid executing")
- Customize instructions for specific MCP server being used

## Migration Guide

### Adding Planning Mode to Existing Config

To add planning mode to an existing MCP configuration:

1. Add orchestrator coordination section:
```yaml
orchestrator:
  coordination:
    enable_planning_mode: true
    planning_mode_instruction: |
      PLANNING MODE ACTIVE: Coordination phase.
      DO NOT execute MCP commands.
      Use only 'vote' or 'new_answer' tools.
```

2. Test with a safe operation first
3. Customize `planning_mode_instruction` for your use case

### Backward Compatibility

Planning Mode is **fully backward compatible**:
- If `enable_planning_mode` is not set, agents behave as before
- No changes required to existing configurations
- Opt-in feature that doesn't affect default behavior

## Next Steps

- [MCP Integration](./mcp-integration.md) - Learn about MCP servers and tools
- [Multi-Agent Coordination](./multi-agent-coordination.md) - Understanding coordination mechanics
- [Configuration Guide](./configuration-guide.md) - Customizing your setup

## Release Information

- **Introduced**: v0.0.29 (October 8, 2025)
- **Video Demo**: https://youtu.be/jLrMMEIr118
- **Release Notes**: [v0.0.29 Release Notes](../releases/v0.0.29/release-notes.md)
- **Case Study**: [MCP Planning Mode Case Study](../releases/v0.0.29/case-study.md)

---

**Last Updated:** October 2025 | **MassGen Version:** v0.0.29+
