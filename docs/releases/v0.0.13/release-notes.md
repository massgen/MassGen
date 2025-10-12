# MassGen v0.0.13 Release Notes

**Release Date:** August 29, 2025

---

## Overview

Version 0.0.13 introduces a **Unified Logging System** with colored console output and debug mode support, along with enhanced **Windows Platform Support** for better cross-platform compatibility.

---

## What's New

### Unified Logging System

**Centralized Logging Infrastructure:**

Better logging for debugging and monitoring.

**Key Features:**
- **Centralized logger_config.py:** Colored console output and file logging
- **Debug Mode:** Support via `--debug` CLI flag for verbose logging
- **Consistent Logging:** Unified format across all backends (Claude, Gemini, Grok, Azure OpenAI, etc.)
- **Color-Coded Levels:** DEBUG (cyan), INFO (green) for better visibility

**Usage:**
```bash
# Enable debug mode
uv run python -m massgen.cli --debug --config your_config.yaml "Your task"
```

**Benefits:**
- Easier debugging of complex multi-agent workflows
- Better visibility into agent interactions
- Consistent logging across all backends
- Colored output for quick issue identification

---

### Windows Platform Support

**Enhanced Cross-Platform Compatibility:**

Windows-specific improvements.

**Key Features:**
- Windows-specific terminal display fixes
- Improved color output on Windows
- Better path handling for Windows filesystems
- Enhanced process management on Windows

**Benefits:**
- Full MassGen support on Windows
- Consistent experience across platforms
- Better Windows terminal integration

---

## What Changed

### Frontend Improvements

**Display Refinements:**
- Enhanced rich terminal display formatting
- Debug info excluded from final presentation
- Better output organization

---

### Documentation Updates

**Enhanced Documentation:**
- Updated CONTRIBUTING.md with better guidelines
- Enhanced README with logging configuration details
- Renamed roadmap from v0.0.13 to v0.0.14

---

## Technical Details

- **Commits:** 35+ commits
- **Files Modified:** 24+ files
- **New Features:** Unified logging with debug mode, Windows support

---

## Contributors

- @qidanrui
- @sonichi
- @Henry-811
- @JeffreyCh0
- @voidcenter
- And the MassGen team

---

## Resources

- **CHANGELOG:** [CHANGELOG.md](../../../CHANGELOG.md#0013---2025-08-28)
- **Next Release:** [v0.0.14 Release Notes](../v0.0.14/release-notes.md)
- **GitHub Release:** https://github.com/Leezekun/MassGen/releases/tag/v0.0.13

---

*Released with ❤️ by the MassGen team*
