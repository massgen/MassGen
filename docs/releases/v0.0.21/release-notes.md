# MassGen v0.0.21 Release Notes

**Release Date:** September 20, 2025

---

## Overview

Version 0.0.21 introduces an **Advanced Filesystem Permissions System** providing granular control over agent file access. This release adds user context paths with configurable permissions, a per-agent function hook manager, and extends MCP support to the Grok backend.

---

## What's New

### Advanced Filesystem Permissions System

**PathPermissionManager:**

New comprehensive permission management for agent file access.

**Key Features:**
- **User Context Paths:** Configurable READ/WRITE permissions for multi-agent file sharing
- **Granular Permission Validation:** Fine-grained control over file operations
- **PathPermissionManager Class:** Centralized permission validation
- **Test Suite:** Comprehensive tests in `test_path_permission_manager.py`

**Configuration Example:**
```yaml
orchestrator:
  context_paths:
    - path: "/shared/data"
      permission: READ
    - path: "/workspace/output"
      permission: WRITE
```

**Try It Out:**
```bash
massgen --config @examples/fs_permissions_test \
  "Read from shared data and write results to output"
```

**Benefits:**
- Control which agents can read/write specific paths
- Share reference files safely (read-only)
- Isolate agent workspaces
- Prevent unauthorized file access

**Documentation:**
- Complete guide in `permissions_and_context_files.md`

---

### Function Hook Manager

**Per-Agent Permission System:**

Refactored function call permission management.

**Key Changes:**
- **Per-Agent Hooks:** Function hook manager now operates per-agent instead of globally
- **Pre-Tool-Use Hooks:** Validate file operations before execution
- **Write Permission Enforcement:** Enforced during context agent operations
- **Integration:** Works with all function-based backends (OpenAI, Claude, Chat Completions)

**How It Works:**
```python
# Hook validates permissions before tool execution
hook_manager.add_pre_hook("write_file", validate_write_permission)
```

**Benefits:**
- Agent-specific permission rules
- Prevent unauthorized operations
- Better security guarantees
- Clear error messages

---

### Grok MCP Integration

**Extended MCP Support:**

Grok backend now fully supports MCP servers.

**Implementation:**
- Migrated Grok backend to inherit from Chat Completions backend
- Full MCP server support (stdio and HTTP transports)
- Filesystem support through MCP servers
- Integration with existing Grok function calling

**Configuration Example:**
```yaml
agents:
  - id: "grok_mcp"
    backend:
      type: "grok"
      model: "grok-3-mini"
      filesystem_support: "MCP"
      mcp_servers:
        - name: "filesystem"
          command: "npx"
          args: ["-y", "@modelcontextprotocol/server-filesystem", "/path"]
```

**Try It Out:**
```bash
# Grok MCP test
massgen --config @examples/grok3_mini_mcp_test \
  "Your task"

# Grok streamable HTTP test
massgen --config @examples/grok3_mini_streamable_http_test \
  "Your task"
```

---

## What Changed

### Backend Architecture

**Unified Implementations:**
- Grok backend refactored to use Chat Completions backend
- All backends now support per-agent permission management
- Enhanced context file support across Claude, Gemini, and OpenAI backends
- More consistent behavior across backends

---

## New Configurations

### Configuration Examples (5)

1. **grok3_mini_mcp_test.yaml** - Grok MCP testing configuration
2. **grok3_mini_mcp_example.yaml** - Grok MCP usage example
3. **grok3_mini_streamable_http_test.yaml** - Grok HTTP streaming test
4. **grok_single_agent.yaml** - Single Grok agent configuration
5. **fs_permissions_test.yaml** - Filesystem permissions testing

---

## Technical Details

### Statistics

- **Commits:** 20+ commits
- **Files Modified:** 40+ files
- **New Features:** Filesystem permissions, per-agent hooks, Grok MCP

### Major Components Changed

1. **Permission System:** PathPermissionManager and per-agent hooks
2. **Grok Backend:** Migrated to Chat Completions inheritance
3. **MCP Integration:** Extended to Grok backend
4. **Function Hooks:** Refactored to per-agent scope

---

## Use Cases

### Multi-Agent File Sharing

**Read-Only Reference Files:**
```yaml
context_paths:
  - path: "/project/specs"
    permission: READ
  - path: "/project/output"
    permission: WRITE
```

### Agent Workspace Isolation

**Separate Workspaces:**
```yaml
agents:
  - id: "agent1"
    context_paths:
      - path: "/workspace/agent1"
        permission: WRITE
  - id: "agent2"
    context_paths:
      - path: "/workspace/agent2"
        permission: WRITE
```

---

## Migration Guide

### Upgrading from v0.0.20

**No Breaking Changes**

v0.0.21 is fully backward compatible with v0.0.20.

**Optional: Add Context Paths**

```yaml
orchestrator:
  context_paths:
    - path: "/your/path"
      permission: READ  # or WRITE
```

---

## Contributors

- @Eric-Shang
- @ncrispino
- @qidanrui
- @Henry-811
- And the entire MassGen team

---

## Resources

- **CHANGELOG:** [CHANGELOG.md](../../../CHANGELOG.md#0021---2025-09-19)
- **Permissions Doc:** [permissions_and_context_files.md](../../../backend/docs/permissions_and_context_files.md)
- **Next Release:** [v0.0.22 Release Notes](../v0.0.22/release-notes.md)
- **Previous Release:** [v0.0.20 Release Notes](../v0.0.20/release-notes.md)

---

*Released with ❤️ by the MassGen team*
