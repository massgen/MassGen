# MassGen v0.0.18 Release Notes

**Release Date:** September 13, 2025

---

## Overview

Version 0.0.18 extends **MCP Support to ChatCompletions-Based Backends**, enabling all Chat Completions providers (Cerebras, Together AI, Fireworks, Groq, Nebius, OpenRouter) to use MCP tools for external integrations.

---

## What's New

### Chat Completions MCP Support

**Universal MCP Integration:**

Extended MCP framework to all ChatCompletions providers.

**Supported Providers:**
- Cerebras AI
- Together AI
- Fireworks AI
- Groq
- Nebius AI Studio
- OpenRouter

**Key Features:**
- Filesystem support through MCP servers
- Cross-provider function calling compatibility
- Universal MCP server compatibility (stdio and HTTP)
- Seamless MCP tool execution across providers

**Configuration Example:**
```yaml
agents:
  - id: "cerebras_mcp"
    backend:
      type: "chat_completions"
      provider: "cerebras"
      model: "llama-3.1-8b"
      filesystem_support: "MCP"
      mcp_servers:
        - name: "filesystem"
          command: "npx"
          args: ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"]
```

---

## New Configurations

**9 New Chat Completions MCP Configurations:**

**GPT-OSS:**
- `gpt_oss_mcp_example.yaml`
- `gpt_oss_mcp_test.yaml`
- `gpt_oss_streamable_http_test.yaml`

**Qwen API:**
- `qwen_api_mcp_example.yaml`
- `qwen_api_mcp_test.yaml`
- `qwen_api_streamable_http_test.yaml`

**Qwen Local:**
- `qwen_local_mcp_example.yaml`
- `qwen_local_mcp_test.yaml`
- `qwen_local_streamable_http_test.yaml`

---

## What Changed

### Backend Architecture

**MCP Framework Expansion:**
- Extended v0.0.15 MCP infrastructure to all ChatCompletions providers
- Refactored `chat_completions.py` with 1200+ lines of MCP integration
- Enhanced error handling for provider-specific quirks

---

### Enhanced LMStudio Backend

**Improvements:**
- Better tracking of attempted model loads
- Improved server output handling
- Better error reporting

---

## Technical Details

- **Main Feature:** Chat Completions MCP integration
- **Files Modified:** 20+ files
- **Lines Added:** 1200+ in chat_completions.py

---

## Contributors

- @praneeth999
- @qidanrui
- @sonichi
- @a5507203
- @ncrispino
- @Henry-811
- And the MassGen team

---

## Resources

- **CHANGELOG:** [CHANGELOG.md](../../../CHANGELOG.md#0018---2025-09-12)
- **Next Release:** [v0.0.19 Release Notes](../v0.0.19/release-notes.md)
- **Previous Release:** [v0.0.17 Release Notes](../v0.0.17/release-notes.md)

---

*Released with ❤️ by the MassGen team*
