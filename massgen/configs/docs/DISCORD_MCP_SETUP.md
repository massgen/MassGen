# Discord MCP Server Setup Guide (barryyip0625/mcp-discord)

## Overview
This guide provides detailed instructions for setting up the Discord MCP (Model Context Protocol) server with MassGen and Claude Code. The Discord MCP server enables AI assistants to interact with Discord platform features including sending messages, managing channels, handling reactions, and more.

## Prerequisites

### 1. System Requirements
- **Node.js**: Version 16.0.0 or higher
- **npm**: Version 7.0.0 or higher
- **Operating System**: Windows, macOS, or Linux

### 2. Discord Bot Setup

#### Step 1: Create a Discord Application
1. Navigate to [Discord Developer Portal](https://discord.com/developers/applications)
2. Click "New Application" button
3. Enter a name for your application (e.g., "MCP Bot")
4. Click "Create"

#### Step 2: Create a Bot
1. In your application, go to the "Bot" section in the left sidebar
2. Click "Add Bot"
3. Customize your bot's username and avatar if desired

#### Step 3: Configure Bot Permissions
1. In the Bot section, scroll down to "Privileged Gateway Intents"
2. Enable the following intents:
   - **Message Content Intent**: Required to read message content
   - **Server Members Intent**: Required to access member information
   - **Presence Intent**: Required to track user presence

#### Step 4: Get Your Bot Token
1. In the Bot section, click "Reset Token"
2. Copy the token immediately (you won't be able to see it again)
3. **Store this token securely** - never share it publicly

#### Step 5: Invite Bot to Your Server
1. Go to "OAuth2" → "URL Generator" in the left sidebar
2. Under "Scopes", select:
   - `bot`
   - `applications.commands` (if using slash commands)
3. Under "Bot Permissions", select the permissions your bot needs:
   - Send Messages
   - Read Messages/View Channels
   - Manage Messages
   - Add Reactions
   - Manage Channels (if needed)
   - Manage Webhooks (if needed)
4. Copy the generated URL and open it in your browser
5. Select the server you want to add the bot to
6. Click "Authorize"

## Configuration

### Using with MassGen Configuration File

#### Step 1: Create or Update Configuration File
Create a new YAML configuration file or use the provided example:

```yaml
agent:
  id: "claude_code_discord_mcp"
  backend:
    type: "claude_code"
    cwd: "claude_code_workspace_discord_mcp"
    permission_mode: "bypassPermissions"
    
    # Discord MCP server configuration
    mcp_servers:
      discord:
        type: "stdio"
        command: "npx"
        args: ["-y", "mcp-discord", "--config", "YOUR_DISCORD_BOT_TOKEN_HERE"]

    allowed_tools:
      - "Read"
      - "Write"
      - "Bash"
      - "LS"
      - "WebSearch"
      # MCP Discord tools will be auto-discovered

ui:
  display_type: "rich_terminal"
  logging_enabled: true
```

#### Step 2: Replace Token
Replace `YOUR_DISCORD_BOT_TOKEN_HERE` with your actual Discord bot token obtained earlier.

## Available MCP Tools

Once configured, the following Discord tools will be available:

### 1. Message Management
- **`mcp__discord__send_message`**: Send messages to channels
- **`mcp__discord__read_messages`**: Read messages from channels
- **`mcp__discord__delete_message`**: Delete messages

### 2. Channel Management
- **`mcp__discord__create_channel`**: Create new channels
- **`mcp__discord__delete_channel`**: Delete channels
- **`mcp__discord__list_channels`**: List available channels

### 3. Forum Posts
- **`mcp__discord__create_forum_post`**: Create forum posts
- **`mcp__discord__delete_forum_post`**: Delete forum posts

### 4. Reactions
- **`mcp__discord__add_reaction`**: Add reactions to messages
- **`mcp__discord__remove_reaction`**: Remove reactions from messages

### 5. Webhooks
- **`mcp__discord__create_webhook`**: Create webhooks
- **`mcp__discord__delete_webhook`**: Delete webhooks

## Usage

### Running with MassGen

```bash
# Navigate to MassGen directory
cd /path/to/MassGen

# Run with Discord MCP configuration
uv run python -m massgen.api --config massgen/configs/claude_code_discord_mcp_example.yaml "YOUR TASK"
```

### Example Commands

```bash
# Send a message to a Discord channel
uv run python -m massgen.api --config massgen/configs/claude_code_discord_mcp_example.yaml "Send a message saying 'Hello from MCP!' to the general channel"

# Read recent messages
uv run python -m massgen.api --config massgen/configs/claude_code_discord_mcp_example.yaml "Read the last 10 messages from the announcements channel"

# Create a new channel
uv run python -m massgen.api --config massgen/configs/claude_code_discord_mcp_example.yaml "Create a new text channel called 'mcp-testing'"
```

## Security Best Practices

### 1. Token Management
- **Never commit tokens to version control**: Add config files with tokens to `.gitignore`
- **Rotate tokens regularly**: Regenerate bot tokens periodically
- **Limit bot permissions**: Only grant necessary permissions to your bot

### 32 Permission Scoping
- Only enable intents that your bot actually needs
- Regularly review and audit bot permissions
- Use role-based permissions in Discord servers

## Troubleshooting

### Common Issues and Solutions

#### 1. Authentication Failed
**Symptoms**: Bot can't connect or authenticate
**Solutions**:
- Verify the bot token is correct and hasn't been regenerated
- Check if the bot is properly invited to your server
- Ensure required intents are enabled in Discord Developer Portal

#### 2. Missing Permissions
**Symptoms**: Bot can't perform certain actions
**Solutions**:
- Review bot role permissions in Discord server settings
- Check OAuth2 permissions used when inviting the bot
- Verify the bot's role is high enough in the server hierarchy

#### 3. MCP Server Not Starting
**Symptoms**: MCP server fails to initialize
**Solutions**:
- Ensure Node.js and npm are installed: `node --version` and `npm --version`
- Check internet connectivity for npx to download packages
- Try installing globally: `npm install -g mcp-discord`
- Clear npm cache: `npm cache clean --force`

#### 4. Rate Limiting
**Symptoms**: Commands stop working after multiple uses
**Solutions**:
- Discord API has rate limits per endpoint
- Implement delays between bulk operations
- Check Discord's rate limit documentation

#### 5. Intent Errors
**Symptoms**: Bot can't read message content or see members
**Solutions**:
- Enable Message Content Intent in Discord Developer Portal
- Enable Server Members Intent if accessing member data
- Restart the bot after changing intents

## References and Resources

- **GitHub Repository**: [https://github.com/barryyip0625/mcp-discord](https://github.com/barryyip0625/mcp-discord)
- **Discord Developer Portal**: [https://discord.com/developers/applications](https://discord.com/developers/applications)
- **Discord.js Documentation**: [https://discord.js.org/](https://discord.js.org/)
- **Discord API Documentation**: [https://discord.com/developers/docs/intro](https://discord.com/developers/docs/intro)
- **MCP Protocol Specification**: [https://modelcontextprotocol.io/](https://modelcontextprotocol.io/)

## Support

For issues specific to:
- **mcp-discord**: Open an issue at [GitHub Issues](https://github.com/barryyip0625/mcp-discord/issues)
- **MassGen**: Check the MassGen documentation or repository
- **Discord API**: Refer to [Discord Developer Support](https://support.discord.com/hc/en-us)