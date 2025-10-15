# MassGen v0.0.29 Release Notes

**Release Date:** October 8, 2025

**Video Demo:** [MassGen v0.0.29 MCP Planning Mode](https://youtu.be/jLrMMEIr118)

---

## Overview

Version 0.0.29 introduces **MCP Planning Mode**, a groundbreaking coordination strategy that enables agents to plan MCP tool usage without execution during collaboration phases. This prevents irreversible actions during coordination while allowing full execution by the winning agent during final presentation.

Additionally, this release enhances file operation safety through read-before-delete enforcement and improves the permission system with better tracking capabilities.

---

## 🚀 What's New

### MCP Planning Mode

The headline feature of v0.0.29 is the new **MCP Planning Mode** coordination strategy.

**Key Capabilities:**
- **Separation of Planning and Execution:** Agents plan tool usage during coordination without executing, preventing duplicate or premature irreversible actions
- **Multi-Backend Support:** Planning mode works across Response API, Chat Completions, and Gemini backends
- **CoordinationConfig Integration:** New `enable_planning_mode` flag with customizable planning mode instructions
- **Orchestrator & Frontend Support:** Full integration with coordination UI to display planning vs execution phases

**Implementation Details:**
- New `CoordinationConfig` class with `enable_planning_mode` configuration
- Backend enhancements in `base.py`, `response.py`, `chat_completions.py`, and `gemini.py`
- Gemini backend now supports session-based tool execution in planning mode
- Comprehensive test coverage in `test_mcp_blocking.py` and `test_gemini_planning_mode.py`

**Configuration Example:**
```yaml
orchestrator:
  coordination:
    enable_planning_mode: true
    planning_mode_instruction: |
      PLANNING MODE ACTIVE: You are currently in the coordination phase.
      During this phase:
      1. Describe your intended actions and reasoning
      2. Analyze other agents' proposals
      3. Use only 'vote' or 'new_answer' tools for coordination
      4. DO NOT execute any actual MCP commands
      5. Save execution for final presentation phase
```

**Try It Out:**
```bash
# Five agents with filesystem MCP in planning mode
massgen --config @examples/tools/planning/five_agents_filesystem_mcp_planning_mode \
  "Create a project structure for a Python web app"

# Five agents with Discord MCP in planning mode
massgen --config @examples/tools/planning/five_agents_discord_mcp_planning_mode \
  "Check recent messages and post a summary"
```

---

### File Operation Tracker

New **FileOperationTracker** system ensures safer file operations by enforcing read-before-delete policies.

**Key Features:**
- **Read-Before-Delete Enforcement:** Prevents agents from deleting files they haven't read first
- **Created File Exemption:** Agent-created files are exempt from read requirement (can delete their own files)
- **Directory Validation:** Comprehensive directory deletion validation with detailed error messages
- **Operation Tracking:** Tracks all read and write operations per agent

**Implementation:**
- New `FileOperationTracker` class in `filesystem_manager/_file_operation_tracker.py`
- Integration with `PathPermissionManager` for unified permission checking
- Methods: `track_read()`, `track_write()`, `validate_delete()`, `validate_batch_delete()`

**How It Works:**
```python
# Agent must read a file before deleting it
tracker.track_read(agent_id, file_path)  # Agent reads the file
tracker.validate_delete(agent_id, file_path)  # Now deletion is allowed

# Agent-created files can be deleted without reading
tracker.track_write(agent_id, new_file_path)  # Agent creates file
tracker.validate_delete(agent_id, new_file_path)  # Deletion allowed
```

---

### Path Permission Manager Enhancements

**PathPermissionManager** has been enhanced with FileOperationTracker integration.

**New Capabilities:**
- Operation tracking methods: `track_read_operation()`, `track_write_operation()`, `track_delete_operation()`
- Integration with `FileOperationTracker` for read-before-delete enforcement
- Enhanced delete validation for files and batch operations
- Extended test coverage in `test_path_permission_manager.py`

**Benefits:**
- Unified permission and operation tracking system
- Better safety guarantees for file operations
- Clearer error messages when operations are blocked

---

### Message Template Improvements

Enhanced multi-agent coordination guidance through improved message templates.

**Changes:**
- **Irreversible Actions Context:** Added `has_irreversible_actions` support for context path write access
- **Explicit Workspace Paths:** Temporary workspace path structure displayed for better agent understanding
- **Priority Hierarchy:** Clearer task handling priority and simplified new_answer requirements
- **Unified Evaluation:** Consistent evaluation guidance across coordination phases

**Impact:**
- Agents better understand workspace isolation
- Clearer coordination during planning mode
- Improved decision-making in multi-agent scenarios

---

### Enhanced MCP Tool Filtering

Multi-level filtering capabilities for fine-grained MCP tool control.

**Features:**
- **Backend-Level Filtering:** Filter tools at the backend configuration level
- **MCP-Server-Specific Filtering:** Override backend settings per MCP server with `allowed_tools`
- **Merged Exclusions:** Combined `exclude_tools` from both backend and MCP server configurations
- **Flexible Control:** Different agents can have different tool access to the same MCP server

**Configuration Example:**
```yaml
backend:
  type: "openai"
  model: "gpt-4o-mini"
  exclude_tools:
    - mcp__discord__discord_send_webhook_message  # Excluded at backend level
  mcp_servers:
    - name: "discord"
      allowed_tools:  # MCP-server-specific filtering
        - mcp__discord__discord_read_messages
        - mcp__discord__discord_send_message
```

---

## 🔧 What Changed

### Backend Planning Mode Support

Extended planning mode support across multiple backend types:
- Enhanced `base.py` with planning mode abstractions
- Updated `response.py` and `chat_completions.py` for OpenAI/compatible backends
- Added Gemini backend planning mode with session-based tool execution
- Planning mode now works consistently across all major backend types

### Multi-turn MCP Improvements

- Fixed non-use of MCP tools in certain multi-turn scenarios
- Improved final answer autonomy when MCP tools are available
- Better workspace copying when no new answer is provided

### Configuration Updates

- Updated Playwright automation configuration
- Fixed agent ID consistency issues
- Enhanced circuit breaker logic in `base_with_mcp.py` for better MCP server initialization

---

## 🐛 What Was Fixed

### Critical Fixes

- **Circuit Breaker Logic:** Enhanced MCP server initialization reliability in `base_with_mcp.py`
- **Final Answer Context:** Improved workspace copying when no new answer is provided
- **Multi-turn MCP Usage:** Addressed scenarios where MCP tools weren't being used when they should be

### Configuration Fixes

- Updated Playwright automation configuration for better reliability
- Fixed agent ID consistency across configurations
- Corrected MCP server setup in various example configs

---

## 📦 New Configurations

### MCP Planning Mode Examples (5 configs)

Located in `massgen/configs/tools/planning/`:

1. **five_agents_discord_mcp_planning_mode.yaml**
   - Discord MCP integration with 5 agents (Gemini, GPT-4o-mini, Claude Code, Claude, Grok)
   - Planning mode prevents duplicate Discord messages during coordination
   - Example: "Check recent messages in our development channel and post a summary"

2. **five_agents_filesystem_mcp_planning_mode.yaml**
   - Filesystem MCP with planning mode
   - Safe file operations during multi-agent coordination
   - Example: "Create a project structure for a Python web application"

3. **five_agents_notion_mcp_planning_mode.yaml**
   - Notion MCP integration with 5 agents
   - Planning mode for safe Notion database operations
   - Example: "Read our project roadmap and create a progress summary page"

4. **five_agents_twitter_mcp_planning_mode.yaml**
   - Twitter MCP integration with planning mode
   - Prevents duplicate tweets during coordination
   - Example: "Analyze trending topics and draft an engaging tweet"

5. **gpt5_mini_case_study_mcp_planning_mode.yaml**
   - Case study configuration for testing planning mode
   - Demonstrates planning mode with filesystem operations

### MCP Example Configurations (2 configs)

Located in `massgen/configs/tools/mcp/`:

1. **five_agents_travel_mcp_test.yaml**
   - Travel planning MCP example with 5 agents
   - Demonstrates MCP integration for travel queries

2. **five_agents_weather_mcp_test.yaml**
   - Weather service MCP example with 5 agents
   - Shows MCP integration for weather information

### Debug Configurations

- **skip_coordination_test.yaml:** Test configuration for debugging by skipping coordination rounds

---

## 📚 Documentation Updates

### Enhanced Documentation

- **permissions_and_context_files.md:** Updated with FileOperationTracker details in `backend/docs/`
- **README.md:** Added AG2 as optional installation, updated uv tool instructions
- **CHANGELOG.md:** Comprehensive v0.0.29 changelog with all features and fixes

### New Documentation

This release includes comprehensive release documentation:
- **release-notes.md:** This document
- **case-study.md:** Detailed case study of MCP Planning Mode (see separate file)
- **features-overview.md:** Quick reference for all v0.0.29 features

---

## 📊 Technical Details

### Statistics

- **Commits:** 23+ commits
- **Files Modified:** 43 files across agent config, backend, filesystem manager, MCP tools, and configurations
- **New Tests:** `test_mcp_blocking.py`, `test_gemini_planning_mode.py`
- **New Configs:** 7 configuration files (5 planning mode + 2 MCP examples)

### Major Components Changed

1. **Orchestrator:** Planning mode coordination logic
2. **Backend System:** Planning mode support across multiple backends
3. **Filesystem Manager:** FileOperationTracker and permission enhancements
4. **Message Templates:** Improved coordination guidance
5. **Frontend:** Planning mode visualization support

### Testing

- Comprehensive test suite for MCP planning mode
- Gemini-specific planning mode tests
- FileOperationTracker unit tests
- Path permission manager integration tests

---

## 🎯 Use Cases

### When to Use MCP Planning Mode

**✅ Enable Planning Mode When:**
- Using MCP tools with irreversible actions (Discord, Twitter, file operations)
- Multiple agents coordinating with external services
- You want agents to plan collaboratively before execution
- Preventing duplicate API calls during coordination

**❌ Planning Mode Not Needed When:**
- Single agent workflows
- Read-only MCP tools (weather, search)
- No coordination rounds (direct execution)

### Example Workflows

**Social Media Management:**
```bash
# Five agents plan tweet strategy, winner posts
massgen --config @examples/tools/planning/five_agents_twitter_mcp_planning_mode \
  "Analyze our brand voice and create an engaging tweet about our new feature"
```

**Team Communication:**
```bash
# Agents analyze Discord, plan response, winner posts
massgen --config @examples/tools/planning/five_agents_discord_mcp_planning_mode \
  "Check #support channel, summarize issues, post helpful guidance"
```

**Project Management:**
```bash
# Agents collaborate on file structure, winner implements
massgen --config @examples/tools/planning/five_agents_filesystem_mcp_planning_mode \
  "Create a FastAPI project with auth, database, and API endpoints"
```

---

## 🚀 Migration Guide

### Upgrading from v0.0.28

**No Breaking Changes**

v0.0.29 is fully backward compatible with v0.0.28. All existing configurations will continue to work.

**Optional: Enable Planning Mode**

To use the new planning mode feature:

1. Add coordination configuration to your existing config:
```yaml
orchestrator:
  coordination:
    enable_planning_mode: true
    planning_mode_instruction: |
      PLANNING MODE ACTIVE: Describe your approach without executing tools.
      Use only 'vote' or 'new_answer' for coordination.
```

2. Your agents will now plan during coordination and execute during final presentation.

**File Operation Safety**

FileOperationTracker is automatically enabled - no configuration needed. Agents must now read files before deleting them (unless they created the file).

---

## 🤝 Contributors

Special thanks to all contributors who made v0.0.29 possible:

- @ncrispino
- @franklinnwren
- @qidanrui
- @sonichi
- @praneeth999
- And the entire MassGen team

---

## 🔗 Resources

- **CHANGELOG:** [CHANGELOG.md](../../../CHANGELOG.md)
- **Case Study:** [case-study.md](case-study.md)
- **Features Overview:** [features-overview.md](features-overview.md)
- **Video Demo:** https://youtu.be/jLrMMEIr118
- **GitHub Release:** https://github.com/Leezekun/MassGen/releases/tag/v0.0.29

---

## 🔮 What's Next

See the [v0.0.30 Roadmap](../../../README.md#v0030-roadmap) for upcoming features.

**Highlights for v0.0.30:**
- Context window management for long conversations
- Session compression and cleanup utilities
- Enhanced summarization capabilities
- Cross-session context support

---

*Released with ❤️ by the MassGen team*
