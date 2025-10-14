# MassGen v0.0.15 Release Notes

**Release Date:** September 5, 2025

---

## Overview

Version 0.0.15 introduces the **MCP (Model Context Protocol) Integration Framework**, enabling MassGen to connect with external tools and services through standardized MCP servers. This foundational release includes full Gemini MCP support and comprehensive security features.

---

## What's New

### MCP Integration Framework

**Complete MCP Implementation:**

Foundation for external tool integration via Model Context Protocol.

**Key Components:**
- **Multi-Server MCP Client:** Simultaneous connections to multiple MCP servers
- **Two Transport Types:** stdio (process-based) and streamable-http (web-based)
- **Circuit Breaker Patterns:** Fault tolerance and reliability
- **Security Framework:** Command sanitization and validation
- **Auto Tool Discovery:** Automatic tool discovery with name prefixing

**New Module:**
```
massgen/mcp_tools/
├── client.py              # MCP client
├── transport/             # Transport implementations
├── security/              # Security validation
└── test_servers/          # Testing utilities
```

---

### Gemini MCP Support

**Full MCP Integration for Gemini:**

First backend with complete MCP support.

**Features:**
- Session-based tool execution via Gemini SDK
- Automatic tool discovery and calling
- Robust error handling with exponential backoff
- Support for stdio and HTTP-based MCP servers
- Integration with existing Gemini function calling

**Configuration Example:**
```yaml
agents:
  - id: "gemini_mcp"
    backend:
      type: "gemini"
      model: "gemini-2.5-flash"
      filesystem_support: "MCP"
      mcp_servers:
        - name: "filesystem"
          command: "npx"
          args: ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"]
```

**Try It Out:**
```bash
# Gemini MCP test
massgen --config @examples/gemini_mcp_test \
  "Test MCP integration"

# Weather service example
massgen --config @examples/gemini_mcp_example \
  "Get weather for San Francisco"

# HTTP transport test
massgen --config @examples/gemini_streamable_http_test \
  "Test HTTP MCP"

# Multi-server setup
massgen --config @examples/multimcp_gemini \
  "Use multiple MCP servers"
```

---

## New Configurations

**MCP Configurations (4+ configs):**
- `gemini_mcp_test.yaml` - Basic testing
- `gemini_mcp_example.yaml` - Weather service
- `gemini_streamable_http_test.yaml` - HTTP transport
- `multimcp_gemini.yaml` - Multi-server setup
- Additional Claude Code MCP configurations

---

## Test Infrastructure

**MCP Testing Utilities:**
- `mcp_test_server.py` - Simple stdio MCP test server
- `test_http_mcp_server.py` - FastMCP streamable-http test server
- Comprehensive test suite for MCP integration

---

## Dependencies

**New Requirements:**
- `mcp>=1.12.0` - Official MCP protocol support
- `aiohttp>=3.8.0` - HTTP-based MCP communication

---

## Documentation

**Enhanced Documentation:**
- Technical analysis for Gemini MCP integration
- Comprehensive MCP tools README with architecture diagrams
- Security and troubleshooting guides

---

## Technical Details

- **Commits:** 40+ commits
- **Files Modified:** 35+ files
- **New Module:** `massgen/mcp_tools/`
- **Security Levels:** Strict/Moderate/Permissive

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

- **CHANGELOG:** [CHANGELOG.md](../../../CHANGELOG.md#0015---2025-09-05)
- **Next Release:** [v0.0.16 Release Notes](../v0.0.16/release-notes.md)
- **Previous Release:** [v0.0.14 Release Notes](../v0.0.14/release-notes.md)

---

*Released with ❤️ by the MassGen team*
