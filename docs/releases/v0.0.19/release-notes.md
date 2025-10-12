# MassGen v0.0.19 Release Notes

**Release Date:** September 15, 2025

---

## Overview

Version 0.0.19 introduces a **Coordination Tracking System** for comprehensive tracking of multi-agent coordination events, along with enhanced agent status management and frontend visualization capabilities.

---

## What's New

### Coordination Tracking System

**Event-Based Coordination Tracking:**

New system for capturing and analyzing agent coordination events.

**Key Components:**
- **CoordinationTracker Class:** Captures agent state transitions with timestamps
- **Event Recording:** Track answers, votes, and coordination phases
- **Coordination Table:** Generate reports showing agent interactions across rounds

**Implementation:**
- New `coordination_tracker.py` module
- `create_coordination_table.py` utility for generating reports
- Integration with orchestrator for automatic tracking

**Try It Out:**
```bash
# During multi-agent session, press 'r' in menu to view coordination table
```

**Benefits:**
- Understand agent coordination patterns
- Debug coordination issues
- Analyze voting behavior
- Track agent performance across rounds

---

### Enhanced Agent Status Management

**New Status Enums:**

Better state tracking for agents during coordination.

**ActionType Enum:**
- NEW_ANSWER
- VOTE
- VOTE_IGNORED
- ERROR
- TIMEOUT
- CANCELLED

**AgentStatus Enum:**
- STREAMING
- VOTED
- ANSWERED
- RESTARTING
- ERROR
- TIMEOUT
- COMPLETED

**Benefits:**
- Clearer agent state tracking
- Better error handling
- Improved debugging
- More informative status displays

---

## What Changed

### Frontend Display Enhancements

**Coordination Visualization:**
- New coordination table display method in `rich_terminal_display.py`
- Terminal menu option 'r' to display coordination table
- Enhanced menu system with debugging tools
- Rich-formatted tables showing agent interactions

---

## Technical Details

### Statistics

- **Commits:** 20+ commits
- **Files Modified:** 5+ files
- **New Features:** Coordination tracking with visualization

---

## Contributors

- @ncrispino
- @qidanrui
- @sonichi
- @a5507203
- @Henry-811
- And the MassGen team

---

## Resources

- **CHANGELOG:** [CHANGELOG.md](../../../CHANGELOG.md#0019---2025-09-15)
- **Next Release:** [v0.0.20 Release Notes](../v0.0.20/release-notes.md)
- **Previous Release:** [v0.0.18 Release Notes](../v0.0.18/release-notes.md)

---

*Released with ❤️ by the MassGen team*
