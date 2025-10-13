# Web UI Track

**Lead:** Justin | **Status:** 🟢 Active | **Updated:** 2025-01-15

**Mission:** Provide excellent visual interfaces for observing and interacting with multi-agent coordination.

---

## 🎯 Current Sprint (v0.0.30+)

### P0 - Critical
- None currently

### P1 - High
- [ ] Test displays with all terminal types (iTerm, Alacritty, Windows Terminal)
- [ ] Optimize rich display performance for long conversations
- [ ] Document UI configuration options

### P2 - Medium
- [ ] Explore Textual TUI implementation
- [ ] Add display customization options
- [ ] Create UI showcase examples

---

## 🔄 In Progress

### Web UI Development
**Status:** Active development | **Assignee:** Justin | **PR:** [#257](https://github.com/Leezekun/MassGen/pull/257)

Building a web-based interface for MassGen to provide enhanced visualization and interaction capabilities beyond terminal displays.

### Performance Optimization
**Status:** Active | **Assignee:** Justin

Rich terminal display can be slow with many agents or long responses.

**Findings:**
- Character-by-character streaming adds latency
- Many agents updating simultaneously causes flicker
- Token bars redraw frequently

**Potential Solutions:**
- Batch character updates
- Smarter redraw logic
- Optional streaming (instant display mode)

### Textual TUI Prototype
**Status:** Research | **Assignee:** Open

Exploring Textual framework for interactive TUI.

**Desired Features:**
- Split panes for each agent
- Scrollable conversation history
- Interactive controls (pause, skip, retry)
- Real-time metrics dashboard

**Challenges:**
- Integration with async orchestrator
- Performance with many agents
- Keyboard shortcut design

---

## ✅ Recently Completed

- [x] Streaming output performance improvements (Oct 8)
- [x] Token usage display refinements (Oct 8)
- [x] Color scheme consistency across displays (Oct 8)
- [x] **v0.0.25:** Rich terminal display with streaming
- [x] **v0.0.27:** Token usage tracking
- [x] **v0.0.28:** Final presentation mode
- [x] **v0.0.29:** Display performance improvements

---

## 🚧 Blocked

None currently

---

## 📝 Notes & Decisions Needed

**Discussion Topics:**
- Should we support web-based dashboard (future)?
- Accessibility requirements for screen readers
- Keyboard shortcuts for interactive mode

**Metrics:**
- Display Usage (Estimated from configs):
  - Rich Terminal: ~70%
  - Simple: ~20% (CI/CD, scripting)
  - Standard Terminal: ~10%

---

## Track Information

### Scope

**In Scope:**
- Terminal-based displays (rich, simple, standard)
- Real-time agent coordination visualization
- Progress indicators and status updates
- Log display and filtering
- Interactive controls (future)
- Web dashboard (future)

**Out of Scope (For Now):**
- Mobile applications
- Desktop GUI (Electron/Qt)
- 3D visualizations
- VR/AR interfaces

### Current State

**Display Types:**
- ✅ **Rich Terminal** - Fancy formatting with Rich library
- ✅ **Simple Display** - Minimal text output
- ✅ **Terminal Display** - Standard terminal output
- 🔄 **Textual Terminal** - TUI with Textual (in development)

**Configuration:**
```yaml
ui:
  display_type: "rich_terminal"  # or "simple", "terminal", "textual_terminal"
  logging_enabled: true
```

**Coordination UI Features:**
- Real-time agent status display
- Token usage tracking per agent
- Turn-by-turn conversation flow
- Winner announcement
- Final presentation mode
- Streaming output with character-by-character display

### Team & Resources

**Contributors:** Open to community contributors
**GitHub Label:** `track:web-ui`
**Code:** `massgen/frontend/`
**Examples:** All configurations support `ui:` section

**Related Tracks:**
- **Memory:** Display conversation history
- **All Tracks:** UI displays all agent coordination

### Architecture

**Display System:**
```
massgen/frontend/
├── coordination_ui.py               # Main coordination interface
└── displays/
    ├── base_display.py              # Abstract base
    ├── simple_display.py            # Minimal output
    ├── terminal_display.py          # Standard terminal
    ├── rich_terminal_display.py     # Rich formatting
    └── textual_terminal_display.py  # TUI (future)
```

**Design Pattern:** Strategy pattern for display selection

### Dependencies

**Internal:**
- `massgen.orchestrator` - Agent coordination data
- `massgen.backend.response` - Response formatting

**External:**
- **Rich** - Terminal formatting (optional)
- **Textual** - TUI framework (future)

### Key Features by Display Type

**Rich Terminal:**
- Color-coded agent responses
- Progress spinners
- Token usage bars
- Formatted code blocks
- Emoji indicators
- Streaming text effect

**Simple Display:**
- Clean, minimal output
- No dependencies (pure Python)
- Excellent for logs and CI/CD
- Fast and lightweight

**Terminal Display:**
- Standard terminal output
- Basic formatting
- Wide compatibility
- Good for scripting

---

## Long-Term Vision

See **[roadmap.md](./roadmap.md)** for 3-6 month goals including Textual TUI, web dashboard, and interactive controls.

---

*Track lead: Update sprint section weekly. Update long-term vision in roadmap.md monthly.*
