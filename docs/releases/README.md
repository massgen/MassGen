# MassGen Releases

Complete documentation for all MassGen releases.

---

## 📋 Release Index

### Latest Releases

| Version | Date | Headline Feature | Documentation |
|---------|------|------------------|---------------|
| **[v0.0.29](#v0029---mcp-planning-mode)** | Oct 8, 2025 | MCP Planning Mode | [📄 Notes](v0.0.29/release-notes.md) · [📊 Case Study](v0.0.29/case-study.md) · [⚡ Quick Ref](v0.0.29/features-overview.md) |
| **[v0.0.28](#v0028---ag2-framework-integration)** | Oct 6, 2025 | AG2 Framework Integration | [📄 Notes](v0.0.28/release-notes.md) · [📊 Case Study](v0.0.28/case-study.md) · [⚡ Quick Ref](v0.0.28/features-overview.md) |

---

## v0.0.29 - MCP Planning Mode

**Release Date:** October 8, 2025

### Headline Feature
**MCP Planning Mode** - Separate planning from execution in multi-agent MCP tool usage, preventing irreversible actions during coordination.

### Key Features
- 🎯 **MCP Planning Mode** - Agents plan without executing during coordination
- 🛡️ **FileOperationTracker** - Read-before-delete enforcement for safety
- 🔧 **Enhanced MCP Tool Filtering** - Multi-level tool control
- 🎨 **Path Permission Manager Enhancements** - Better operation tracking
- 📝 **Message Template Improvements** - Better coordination guidance

### New Configurations (7)
- `tools/planning/five_agents_discord_mcp_planning_mode.yaml`
- `tools/planning/five_agents_filesystem_mcp_planning_mode.yaml`
- `tools/planning/five_agents_notion_mcp_planning_mode.yaml`
- `tools/planning/five_agents_twitter_mcp_planning_mode.yaml`
- `tools/planning/gpt5_mini_case_study_mcp_planning_mode.yaml`
- `tools/mcp/five_agents_travel_mcp_test.yaml`
- `tools/mcp/five_agents_weather_mcp_test.yaml`

### Documentation
- **[Release Notes](v0.0.29/release-notes.md)** - Complete feature documentation
- **[Case Study](v0.0.29/case-study.md)** - MCP Planning Mode with Discord example
- **[Features Overview](v0.0.29/features-overview.md)** - Quick reference guide

### Impact
- 80% reduction in unnecessary API calls during coordination
- 47% improvement in output quality
- 45% increase in user satisfaction
- Zero duplicate irreversible actions

### Try It
```bash
# Filesystem planning mode
massgen --config @examples/tools/planning/five_agents_filesystem_mcp_planning_mode \
  "Create a Python FastAPI project structure"

# Discord planning mode
massgen --config @examples/tools/planning/five_agents_discord_mcp_planning_mode \
  "Check #support channel and post helpful guidance"
```

### Video Demo
[📹 MassGen v0.0.29 MCP Planning Mode Demo](https://youtu.be/jLrMMEIr118)

---

## v0.0.28 - AG2 Framework Integration

**Release Date:** October 6, 2025

### Headline Feature
**AG2 Framework Integration** - Orchestrate agents from AG2 framework alongside native MassGen agents through extensible adapter architecture.

### Key Features
- 🔌 **AG2 Framework Integration** - External agent framework support
- 🖥️ **Code Execution** - Python code execution with multiple executors
- 🏗️ **External Agent Backend** - Adapter pattern for any framework
- ✅ **AG2 Test Suite** - Comprehensive integration testing
- 🔧 **MCP Circuit Breaker** - Enhanced MCP server initialization

### New Capabilities
- **AG2 Agent Types:** ConversableAgent, AssistantAgent
- **Code Executors:** Local, Docker, Jupyter, YepCode
- **Multi-Framework Collaboration:** AG2 + MassGen native agents
- **Extensible Architecture:** Ready for future framework integrations

### New Configurations (4)
- `ag2/ag2_single_agent.yaml`
- `ag2/ag2_coder.yaml`
- `ag2/ag2_coder_case_study.yaml`
- `ag2/ag2_gemini.yaml`

### Documentation
- **[Release Notes](v0.0.28/release-notes.md)** - Complete feature documentation
- **[Case Study](v0.0.28/case-study.md)** - Framework comparison example
- **[Features Overview](v0.0.28/features-overview.md)** - Quick reference guide

### Impact
- 23% quality improvement in hybrid workflows
- First multi-framework agent orchestration system
- Code execution capabilities unlocked
- Foundation for LangChain, CrewAI, AutoGPT integrations

### Try It
```bash
# Install AG2 first
pip install ag2

# Basic AG2 agent
massgen --config @examples/ag2/ag2_single_agent \
  "Explain quantum computing"

# AG2 with code execution
massgen --config @examples/ag2/ag2_coder \
  "Analyze CSV data and create visualizations"

# Hybrid: AG2 + Gemini
massgen --config @examples/ag2/ag2_coder_case_study \
  "Compare AG2 vs MassGen frameworks"
```

---

## 📊 Complete Release Timeline

```
v0.0.29 (Oct 8, 2025)  - MCP Planning Mode
    ↓
v0.0.28 (Oct 6, 2025)  - AG2 Framework Integration
    ↓
v0.0.27 (Oct 3, 2025)  - Multimodal Support (Image Processing)
    ↓
v0.0.26 (Oct 1, 2025)  - File Deletion & Protected Paths
    ↓
v0.0.25 (Sep 30, 2025) - Multi-Turn Filesystem Support
    ↓
v0.0.24 (Sep 27, 2025) - vLLM Backend Support
    ↓
v0.0.23 (Sep 25, 2025) - Backend Architecture Refactoring
    ↓
v0.0.22 (Sep 23, 2025) - Workspace Copy Tools
    ↓
v0.0.21 (Sep 20, 2025) - Advanced Filesystem Permissions
    ↓
v0.0.20 (Sep 18, 2025) - Claude Backend MCP Support
    ↓
v0.0.19 (Sep 15, 2025) - Coordination Tracking System
    ↓
v0.0.18 (Sep 13, 2025) - Chat Completions MCP Support
    ↓
v0.0.17 (Sep 10, 2025) - OpenAI Backend MCP Support
    ↓
v0.0.16 (Sep 9, 2025)  - Unified Filesystem with MCP
    ↓
v0.0.15 (Sep 5, 2025)  - MCP Integration Framework
    ↓
v0.0.14 (Sep 2, 2025)  - Enhanced Logging System
    ↓
v0.0.13 (Aug 29, 2025) - Unified Logging & Windows Support
```

---

## 📚 All Releases (Reverse Chronological)

### v0.0.27 - Multimodal Support
**Date:** October 3, 2025 | **[Release Notes](v0.0.27/release-notes.md)**

Image processing foundation with generation and understanding capabilities, file upload/search, and Claude Sonnet 4.5 support.

---

### v0.0.26 - File Deletion & Context Files
**Date:** October 2, 2025 | **[Release Notes](v0.0.26/release-notes.md)**

Workspace cleanup with file deletion tools, file-based context paths, and protected paths feature.

---

### v0.0.25 - Multi-Turn Filesystem Support
**Date:** September 30, 2025 | **[Release Notes](v0.0.25/release-notes.md)**

Persistent workspace across conversation turns with SGLang backend integration.

---

### v0.0.24 - vLLM Backend Support
**Date:** September 27, 2025 | **[Release Notes](v0.0.24/release-notes.md)**

High-performance local model serving with vLLM, POE provider support, and backend utility modules.

---

### v0.0.23 - Backend Architecture Refactoring
**Date:** September 25, 2025 | **[Release Notes](v0.0.23/release-notes.md)**

Major MCP consolidation into base_with_mcp.py, formatter module extraction, ~2000 lines removed.

---

### v0.0.22 - Workspace Copy Tools
**Date:** September 23, 2025 | **[Release Notes](v0.0.22/release-notes.md)**

MCP workspace copy capabilities and complete configuration organization (basic/, providers/, tools/, teams/).

---

### v0.0.21 - Advanced Filesystem Permissions
**Date:** September 20, 2025 | **[Release Notes](v0.0.21/release-notes.md)**

PathPermissionManager, user context paths with READ/WRITE permissions, and Grok MCP integration.

---

### v0.0.20 - Claude Backend MCP Support
**Date:** September 18, 2025 | **[Release Notes](v0.0.20/release-notes.md)**

Extended MCP support to Claude Messages API with recursive tool execution.

---

### v0.0.19 - Coordination Tracking System
**Date:** September 15, 2025 | **[Release Notes](v0.0.19/release-notes.md)**

CoordinationTracker for event capture, enhanced agent status management, and coordination visualization.

---

### v0.0.18 - Chat Completions MCP Support
**Date:** September 13, 2025 | **[Release Notes](v0.0.18/release-notes.md)**

Universal MCP integration for all Chat Completions providers (Cerebras, Together AI, Fireworks, Groq, etc.).

---

### v0.0.17 - OpenAI Backend MCP Support
**Date:** September 10, 2025 | **[Release Notes](v0.0.17/release-notes.md)**

Extended MCP to OpenAI Response API with stdio and HTTP-based MCP servers.

---

### v0.0.16 - Unified Filesystem with MCP
**Date:** September 9, 2025 | **[Release Notes](v0.0.16/release-notes.md)**

Complete FilesystemManager class with MCP-based operations and cross-agent collaboration.

---

### v0.0.15 - MCP Integration Framework
**Date:** September 5, 2025 | **[Release Notes](v0.0.15/release-notes.md)**

Foundation release with complete MCP framework, multi-server client, Gemini MCP support, and security framework.

---

### v0.0.14 - Enhanced Logging System
**Date:** September 2, 2025 | **[Release Notes](v0.0.14/release-notes.md)**

Improved log organization and preservation for multi-agent workflows.

---

### v0.0.13 - Unified Logging & Windows Support
**Date:** August 29, 2025 | **[Release Notes](v0.0.13/release-notes.md)**

Centralized logging infrastructure with colored console output, debug mode, and Windows platform support.

---

## 🗂️ Documentation Structure

Each release includes three key documents:

### 1. features-overview.md (~100-150 lines)
**Purpose:** Short, copy-pasteable into README.md

Content:
- High-level feature descriptions
- Key benefits (bullets with ✅)
- Quick start commands
- When to use guidance
- Links to full documentation

**Usage:** Automatically embedded in main README via script

### 2. release-notes.md (400+ lines)
**Purpose:** Complete technical documentation

Content:
- Full implementation details
- Code examples and architecture
- Migration guides and breaking changes
- All bug fixes and improvements
- Contributors and resources
- Technical specifications

**Usage:** Reference documentation for developers

### 3. case-study.md (optional)
**Purpose:** Real-world demonstration

Content:
- Problem and solution approach
- Step-by-step execution walkthrough
- Performance analysis and metrics
- Lessons learned
- Self-evolution insights

**Usage:** Learning resource and validation

---

## 🤖 Automated Release Workflow

### README Update Script

MassGen includes an automated script to update README.md with new release information:

```bash
# Run from repo root
uv run python scripts/update_readme_release.py v0.0.29
```

**What it does:**
1. ✅ Extracts content from `features-overview.md`
2. ✅ Updates README.md's "What's New" section
3. ✅ Archives previous release to "Previous Releases"
4. ✅ Adds proper links to full documentation

**Documentation:** [Release README Update Workflow](../workflows/release_readme_update.md)

### 2-Tier Documentation System

```
features-overview.md (SHORT)  →  Embedded in README.md
        ↓
release-notes.md (LONG)       →  Complete technical docs
```

**Benefits:**
- Users see concise updates in main README
- Developers get complete technical details
- Previous releases automatically archived
- Consistent documentation structure

### Release Checklist

- [ ] Create `docs/releases/vX.X.X/features-overview.md` (~100-150 lines)
- [ ] Create `docs/releases/vX.X.X/release-notes.md` (400+ lines)
- [ ] Create `docs/releases/vX.X.X/case-study.md` (optional)
- [ ] Run `python scripts/update_readme_release.py vX.X.X`
- [ ] Review `git diff README.md`
- [ ] Commit changes
- [ ] Tag release: `git tag vX.X.X && git push --tags`

---

## 🎯 Finding What You Need

### By Feature Type

**Multi-Agent Coordination:**
- v0.0.29: MCP Planning Mode
- v0.0.19: Coordination Tracking System

**Framework Integration:**
- v0.0.28: AG2 Framework Integration

**MCP Tools & Integration:**
- v0.0.29: Planning mode configs, tool filtering
- v0.0.28: Circuit breaker improvements
- v0.0.20: Claude MCP Support
- v0.0.18: Chat Completions MCP Support
- v0.0.17: OpenAI MCP Support
- v0.0.16: Unified Filesystem with MCP
- v0.0.15: MCP Integration Framework

**File Operations & Permissions:**
- v0.0.29: FileOperationTracker (read-before-delete)
- v0.0.26: File deletion tools, protected paths
- v0.0.25: Multi-turn filesystem support
- v0.0.22: Workspace copy tools
- v0.0.21: Advanced filesystem permissions

**Local Inference Backends:**
- v0.0.25: SGLang Backend
- v0.0.24: vLLM Backend

**Backend Architecture:**
- v0.0.23: MCP consolidation refactoring
- v0.0.22: Configuration organization

**Multimodal:**
- v0.0.27: Image generation and understanding

**Logging & Developer Experience:**
- v0.0.14: Enhanced logging system
- v0.0.13: Unified logging & Windows support

### By Use Case

**Code Execution:**
→ v0.0.28: AG2 integration with code executors

**Safe MCP Operations:**
→ v0.0.29: MCP Planning Mode

**Multi-Framework Workflows:**
→ v0.0.28: AG2 + MassGen agents

**File Safety:**
→ v0.0.29: FileOperationTracker
→ v0.0.26: Protected paths

---

## 🔗 Related Documentation

- **[CHANGELOG](../../CHANGELOG.md)** - All version changes
- **[README](../../README.md)** - Project overview
- **[Track Documentation](../source/tracks/)** - Feature-organized docs
  - [Memory Track](../source/tracks/memory/)
  - [Coding Agent Track](../source/tracks/coding-agent/)
  - [Irreversible Actions Track](../source/tracks/irreversible-actions/)
  - [Multimodal Track](../source/tracks/multimodal/)
  - [AgentAdapter Backends Track](../source/tracks/agentadapter-backends/)
  - [Web UI Track](../source/tracks/web-ui/)

---

## 📈 Release Cadence

**Current Pattern:**
- Major feature releases: Every 2-3 days
- Minor updates: As needed
- Hotfixes: Immediate

**Documentation Coverage:**
- v0.0.29: Full release documentation (notes, case study, overview)
- v0.0.28: Full release documentation (notes, case study, overview)
- v0.0.13-v0.0.27: Complete release notes documentation
- All releases: See CHANGELOG for summary

---

## 🤝 Contributing to Release Documentation

Want to help document a release?

1. **Template:** Use [`docs/_templates/case-study-template.md`](../_templates/case-study-template.md)
2. **Structure:** Follow v0.0.29 or v0.0.28 pattern
3. **Content:** Include release notes, case study, features overview
4. **Review:** Submit PR with documentation updates

---

## 💬 Feedback

Found an issue in release documentation?
- Open an issue: [GitHub Issues](https://github.com/Leezekun/MassGen/issues)
- Suggest improvement: [GitHub Discussions](https://github.com/Leezekun/MassGen/discussions)

---

*Last Updated: October 8, 2025 - Now with complete documentation for v0.0.13 through v0.0.29*
