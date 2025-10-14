# MassGen v0.0.17 Release Notes

**Release Date:** September 10, 2025

---

## Overview

Version 0.0.17 extends **MCP Support to OpenAI Backend**, enabling OpenAI models to use external tools through MCP servers with both stdio and HTTP-based transports.

---

## What's New

### OpenAI Backend MCP Support

**Complete MCP Integration:**

Extended MCP to OpenAI Response API.

**Key Features:**
- Full MCP tool discovery and execution for OpenAI models
- Support for stdio and HTTP-based MCP servers
- Seamless integration with OpenAI function calling
- Robust error handling and retry mechanisms

**Configuration Example:**
```yaml
agents:
  - id: "gpt5_mcp"
    backend:
      type: "openai"
      model: "gpt-4o-mini"
      filesystem_support: "MCP"
      mcp_servers:
        - name: "filesystem"
          command: "npx"
          args: ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"]
```

**Try It Out:**
```bash
# OpenAI MCP test
massgen --config @examples/gpt5_mini_mcp_test \
  "Test MCP integration"

# OpenAI MCP example
massgen --config @examples/gpt5_mini_mcp_example \
  "Weather service integration"

# HTTP transport test
massgen --config @examples/gpt5_mini_streamable_http_test \
  "Test HTTP MCP"
```

---

## New Configurations

**3 OpenAI MCP Configurations:**
- `gpt5_mini_mcp_test.yaml`
- `gpt5_mini_mcp_example.yaml`
- `gpt5_mini_streamable_http_test.yaml`

---

## Documentation Updates

**New Documentation:**
- `unified-filesystem-mcp-integration.md` - Case study demonstrating unified filesystem capabilities
- `MCP_INTEGRATION_RESPONSE_BACKEND.md` - Technical documentation for MCP integration

---

## Contributors

- @praneeth999
- @qidanrui
- @sonichi
- @ncrispino
- @a5507203
- @Henry-811
- And the MassGen team

---

## Resources

- **CHANGELOG:** [CHANGELOG.md](../../../CHANGELOG.md#0017---2025-09-10)
- **Next Release:** [v0.0.18 Release Notes](../v0.0.18/release-notes.md)
- **Previous Release:** [v0.0.16 Release Notes](../v0.0.16/release-notes.md)

---

*Released with ❤️ by the MassGen team*
