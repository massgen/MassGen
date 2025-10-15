# v0.0.29 Features Overview

**Release Date:** October 8, 2025 | [Full Release Notes](release-notes.md) | [Video Demo](https://youtu.be/jLrMMEIr118)

---

## What's New

### MCP Planning Mode
**Agents plan without executing during coordination** - Prevents duplicate actions when multiple agents use MCP tools

**Key Benefits:**
- ✅ No duplicate Discord posts, tweets, or file operations during coordination
- ✅ 80% reduction in unnecessary API calls
- ✅ Agents collaborate on strategy before winner executes
- ✅ Works across all backends (OpenAI, Claude, Gemini, Grok)

**Quick Start:**
```yaml
orchestrator:
  coordination:
    enable_planning_mode: true
    planning_mode_instruction: |
      PLANNING MODE: Plan without executing MCP tools.
      Winner executes during final presentation.
```

---

### File Operation Tracker
**Read-before-delete enforcement for safer file operations**

**Key Benefits:**
- ✅ Prevents accidental deletion of unread files
- ✅ Agents must review files before deleting them
- ✅ Agent-created files exempt (can delete own files)
- ✅ Clear error messages guide safe behavior

---

### Enhanced MCP Tool Filtering
**Multi-level filtering for fine-grained MCP tool control**

**Key Benefits:**
- ✅ Backend-level tool exclusions
- ✅ MCP-server-specific allowed tools
- ✅ Different agents can have different tool access
- ✅ Prevent dangerous operations (webhooks, deletions)

---

## New Configurations (8)

**MCP Planning Mode (5):**
- `five_agents_discord_mcp_planning_mode.yaml` - Team communication
- `five_agents_filesystem_mcp_planning_mode.yaml` - Project scaffolding
- `five_agents_notion_mcp_planning_mode.yaml` - Documentation management
- `five_agents_twitter_mcp_planning_mode.yaml` - Social media management
- `gpt5_mini_case_study_mcp_planning_mode.yaml` - Testing & validation

**MCP Examples (2):**
- `five_agents_weather_mcp_test.yaml` - Weather service integration
- `five_agents_travel_mcp_test.yaml` - Travel planning tools

**Debug (1):**
- `skip_coordination_test.yaml` - Skip coordination for debugging

---

## Quick Start Commands

```bash
# Discord planning mode
massgen --config @examples/tools/planning/five_agents_discord_mcp_planning_mode \
  "Check recent messages in #dev and post a summary"

# Filesystem planning mode
massgen --config @examples/tools/planning/five_agents_filesystem_mcp_planning_mode \
  "Create a Python web app project structure"

# Twitter planning mode
massgen --config @examples/tools/planning/five_agents_twitter_mcp_planning_mode \
  "Analyze our brand voice and draft an announcement"
```

---

## When to Use Planning Mode

**✅ Enable Planning Mode When:**
- Multiple agents using MCP tools with irreversible actions
- External services (Discord, Twitter, Notion, filesystems)
- Preventing duplicate API calls is important
- Collaborative strategy refinement before execution

**❌ Planning Mode Not Needed When:**
- Single agent workflows
- Read-only MCP tools (weather, search)
- No coordination rounds
- Time is more critical than quality

---

## Performance Impact

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| Duplicate Actions | 5 per round | 0 | -100% |
| Unnecessary API Calls | 100% | 20% | -80% |
| Output Quality | 3.2/5 | 4.7/5 | +47% |

---

## Migration from v0.0.28

**No Breaking Changes** - v0.0.29 is fully backward compatible

**To enable planning mode in your existing config:**
```yaml
# Add to orchestrator section
orchestrator:
  coordination:
    enable_planning_mode: true
    planning_mode_instruction: |
      PLANNING MODE ACTIVE: Plan without executing MCP tools.
```

---

## Resources

- 📝 [Full Release Notes](release-notes.md) - Complete technical documentation
- 📖 [Case Study](case-study.md) - Detailed MCP Planning Mode example
- 🎥 [Video Demo](https://youtu.be/jLrMMEIr118) - Watch planning mode in action
- 📋 [CHANGELOG](../../../CHANGELOG.md#0029---2025-10-08) - All version changes

---

## Contributors

@ncrispino @franklinnwren @qidanrui @sonichi @praneeth999 and the MassGen team

---

**MassGen v0.0.29** - Planning Mode for Intelligent Multi-Agent Coordination
