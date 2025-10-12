# Coding Agent Track

**Lead:** Nick | **Status:** 🟢 Active | **Updated:** 2025-01-15

**Mission:** Enable MassGen agents to execute code, manipulate files, and interact with development tools safely and effectively.

---

## 🎯 Current Sprint (v0.0.30)

### P0 - Critical
- None currently

### P1 - High
- [ ] Document all filesystem configuration options
- [ ] Test multi-turn filesystem operations
- [ ] Validate planning mode with complex tasks

### P2 - Medium
- [ ] Create filesystem operations guide
- [ ] Improve MCP tool error messages
- [ ] Add more Playwright examples

---

## 🔄 In Progress

### Coding Agent Enhancements
**Status:** Active development | **Assignee:** Nick | **PR:** [#251](https://github.com/Leezekun/MassGen/pull/251)

Enhancing coding agent capabilities including advanced file operations, code generation, and development tool integration.

### Multi-Turn Filesystem Operations
**Status:** Testing | **Assignee:** Nick

Enable agents to maintain context across multiple filesystem operations in multi-turn mode.

**Configurations:**
- `two_claude_code_filesystem_multiturn.yaml`
- `two_gemini_flash_filesystem_multiturn.yaml`
- `grok4_gpt5_gemini_filesystem_multiturn.yaml`

**Testing:**
- ✅ Basic multi-turn works
- 🔄 Complex file editing scenarios
- ⏳ Large codebase handling

### Planning Mode for MCP Tools
**Status:** Testing | **Assignee:** Open

Test planning mode with complex tasks to ensure no irreversible actions during coordination.

---

## ✅ Recently Completed

- [x] Multi-turn filesystem configurations tested (Oct 8)
- [x] Planning mode implemented for Claude Code (Oct 8)
- [x] MCP filesystem integration validated (Oct 8)
- [x] **v0.0.26:** Filesystem operations with workspace isolation
- [x] **v0.0.27:** Protected paths and permission system
- [x] **v0.0.28:** MCP tools integration
- [x] **v0.0.29:** Planning mode enhancements

---

## 🚧 Blocked

None currently

---

## 📝 Notes & Decisions Needed

**Discussion Topics:**
- Best practices for coding agent workspace management
- When to use planning mode vs direct execution
- How to handle large codebases efficiently

**Key Capabilities:**
- File reading, writing, editing (via Claude Code or MCP filesystem)
- Multi-turn iterative development
- Planning mode for safe collaboration
- Workspace isolation per agent
- Context path integration for existing codebases
- Web automation via Playwright

**Metrics:**
- Filesystem configurations: 15+
- MCP configurations: 50+
- Multi-turn coding sessions: Tested up to 10 turns
- Planning mode adoption: Growing (v0.0.29 feature)

---

## Track Information

### Scope

**In Scope:**
- Filesystem operations (read, write, edit, delete)
- Workspace management and isolation
- Path permissions and security
- MCP (Model Context Protocol) tool integration
- Web automation (Playwright)
- Planning mode for complex tasks

**Out of Scope (For Now):**
- IDE integrations
- Git operations (beyond basic)
- Database management
- Container orchestration

### Current Capabilities

**Filesystem Operations:**
- Workspace-isolated file operations
- Context paths (read-only access)
- Protected paths (write restrictions)
- File operation tracking
- Permission management

**Configuration:**
```yaml
filesystem:
  cwd: "workspace1"                    # Agent's working directory
  context_paths:                        # Read-only access
    - path: "src/"
      permission: "read"
  protected_paths:                      # Write-protected
    - path: "important_data/"
      permission: "read"
```

**MCP Tools Integration:**
- ✅ Discord MCP (bot operations)
- ✅ Twitter MCP (tweet analysis)
- ✅ Notion MCP (database operations)
- ✅ Filesystem MCP (file operations)
- ✅ Multi-MCP coordination

**Examples:** 50+ configurations in `massgen/configs/tools/mcp/`

**Web Automation:**
- Playwright integration (Experimental)
- Multi-agent browser automation
- Example: `massgen/configs/tools/code-execution/multi_agent_playwright_automation.yaml`

**Planning Mode:**
- Planning mode for filesystem tasks
- Planning mode with MCP tools
- Enhanced planning strategies (In Progress)

### Team & Resources

**Contributors:** Open to community contributors
**GitHub Label:** `track:coding-agent`
**Examples:** `massgen/configs/tools/filesystem/`, `massgen/configs/tools/mcp/`
**Code:** `massgen/filesystem_manager/`, `massgen/mcp_tools/`
**Tests:** `massgen/tests/test_*_permission_*.py`

**Related Tracks:**
- **Memory:** Multi-turn context for iterative coding
- **Irreversible Actions:** Safety mechanisms for file operations
- **Multimodal:** Screenshot analysis for debugging

### Architecture

**Filesystem Manager:**
```
massgen/filesystem_manager/
├── _filesystem_manager.py         # Main filesystem interface
├── _workspace_tools_server.py     # MCP server for workspaces
├── _path_permission_manager.py    # Permission enforcement
└── _file_operation_tracker.py     # Operation logging
```

**Key Components:**
- Workspace Isolation: Each agent has separate workspace
- Permission System: Fine-grained control over file access
- Operation Tracking: Log all filesystem operations
- Safety Checks: Prevent dangerous operations

### Dependencies

**Internal:**
- `massgen.orchestrator` - Agent coordination
- `massgen.backend` - Tool calling support
- `massgen.message_templates` - Tool response formatting

**External:**
- MCP Protocol (Anthropic)
- Playwright (web automation)
- Various MCP servers (Discord, Twitter, etc.)

### Key Challenges

1. **Security:** Preventing agents from accessing/modifying sensitive files
2. **Multi-Agent Coordination:** Multiple agents working on same files
3. **Error Recovery:** Failed operations leave inconsistent state
4. **Performance:** Filesystem operations can be slow

---

## Long-Term Vision

See **[roadmap.md](./roadmap.md)** for 3-6 month goals including SWE-bench integration, advanced code generation, and automated testing capabilities.

---

*Track lead: Update sprint section weekly. Update long-term vision in roadmap.md monthly.*
