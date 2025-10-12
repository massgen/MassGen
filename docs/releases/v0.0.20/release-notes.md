# MassGen v0.0.20 Release Notes

**Release Date:** September 18, 2025

---

## Overview

Version 0.0.20 extends **MCP (Model Context Protocol) Support to Claude Backend**, enabling Claude agents to use external tools through MCP servers. This release brings filesystem support and recursive tool execution to Claude, matching the MCP capabilities previously available in Gemini and Chat Completions backends.

---

## What's New

### Claude Backend MCP Support

**Complete MCP Integration:**

Extended MCP support to Claude Messages API.

**Key Features:**
- **Filesystem Support:** Claude agents can use MCP servers for file operations
- **Stdio and HTTP Transports:** Support for both MCP transport types
- **Recursive Execution:** Claude can autonomously chain multiple tool calls without user intervention
- **Error Handling:** Enhanced retry mechanisms for Claude MCP operations
- **Seamless Integration:** Works with existing Claude function calling

**Configuration Example:**
```yaml
agents:
  - id: "claude_mcp"
    backend:
      type: "claude"
      model: "claude-3-5-sonnet-20241022"
      filesystem_support: "MCP"
      mcp_servers:
        - name: "filesystem"
          command: "npx"
          args: ["-y", "@modelcontextprotocol/server-filesystem", "/workspace"]
```

**Try It Out:**
```bash
# Claude MCP test
uv run python -m massgen.cli \
  --config massgen/configs/claude_mcp_test.yaml \
  "Create a file and read it back"

# Claude MCP example
uv run python -m massgen.cli \
  --config massgen/configs/claude_mcp_example.yaml \
  "Build a website with multiple pages"

# Claude streamable HTTP test
uv run python -m massgen.cli \
  --config massgen/configs/claude_streamable_http_test.yaml \
  "Test HTTP MCP transport"
```

**Recursive Execution Model:**

Claude agents can now:
1. Call MCP tool
2. Receive result
3. Autonomously decide to call another tool
4. Continue chaining tools without user intervention
5. Complete complex multi-step workflows

**Benefits:**
- More autonomous Claude agents
- Complex workflows without interruption
- Better integration with external services
- Consistent MCP experience across backends

---

## What Changed

### Backend Enhancements

**MCP Coverage:**
- Extended MCP from Gemini and Chat Completions to include Claude
- Enhanced error reporting and debugging for MCP operations
- Added Kimi/Moonshot API key support in Chat Completions backend
- Better retry logic for Claude MCP operations

---

## New Configurations

### Claude MCP Examples (3)

1. **claude_mcp_test.yaml** - Basic Claude MCP testing with test server
2. **claude_mcp_example.yaml** - Claude MCP integration example
3. **claude_streamable_http_test.yaml** - HTTP transport testing for Claude MCP

---

## Documentation Updates

### New Documentation

- **MCP_IMPLEMENTATION_CLAUDE_BACKEND.md:** Complete technical documentation for Claude MCP integration
- Architecture diagrams and implementation guides
- Best practices for Claude MCP usage

---

## Technical Details

### Statistics

- **New Features:** Claude backend MCP integration with recursive execution
- **Files Modified:** Claude backend modules (`claude.py`), MCP tools, configurations
- **MCP Coverage:** Major backends now support MCP (Claude, Gemini, Chat Completions/OpenAI)

### Major Backends with MCP Support

1. **Claude** (v0.0.20) - Messages API with MCP
2. **Gemini** (v0.0.15) - Chat API with MCP
3. **Chat Completions** (v0.0.18) - All providers with MCP
4. **OpenAI** (v0.0.17) - Response API with MCP

---

## Use Cases

### Claude with Filesystem MCP

**File Operations:**
```bash
# Claude creates and manages files
uv run python -m massgen.cli \
  --config massgen/configs/claude_mcp_example.yaml \
  "Create a Python project with tests and documentation"
```

### Recursive Tool Execution

**Multi-Step Workflows:**
```bash
# Claude autonomously chains multiple operations
uv run python -m massgen.cli \
  --config massgen/configs/claude_mcp_test.yaml \
  "Read config, process data, write results, verify output"
```

---

## Migration Guide

### Upgrading from v0.0.19

**No Breaking Changes**

v0.0.20 is fully backward compatible with v0.0.19.

**Optional: Enable Claude MCP**

```yaml
agents:
  - id: "claude_with_mcp"
    backend:
      type: "claude"
      model: "claude-3-5-sonnet-20241022"
      filesystem_support: "MCP"
      mcp_servers:
        - name: "filesystem"
          command: "npx"
          args: ["-y", "@modelcontextprotocol/server-filesystem", "/path"]
```

---

## Contributors

- @praneeth999
- @qidanrui
- @sonichi
- @ncrispino
- @Henry-811
- And the MassGen team

---

## Resources

- **CHANGELOG:** [CHANGELOG.md](../../../CHANGELOG.md#0020---2025-09-17)
- **MCP Claude Doc:** [MCP_IMPLEMENTATION_CLAUDE_BACKEND.md](../../../backend/docs/MCP_IMPLEMENTATION_CLAUDE_BACKEND.md)
- **Next Release:** [v0.0.21 Release Notes](../v0.0.21/release-notes.md)
- **Previous Release:** [v0.0.19 Release Notes](../v0.0.19/release-notes.md)

---

*Released with ❤️ by the MassGen team*
