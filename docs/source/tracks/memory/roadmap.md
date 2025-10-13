# Memory Track - Roadmap

**Lead:** TBD | **Last Updated:** 2025-01-15

> **Quick Update Template:** Project leads can update this file in <5 minutes

---

## 🎯 Current Sprint (v0.0.30+)

**Target Date:** TBD

### Critical (P0)
- [ ] Implement context window management (truncation)
- [ ] Context overflow protection

### High Priority (P1)
- [ ] Test multi-turn with all backends
- [ ] Document session storage format
- [ ] Add context overflow warnings

### Nice to Have (P2)
- [ ] Add context summarization
- [ ] Session cleanup utilities
- [ ] Privacy/encryption for sessions

---

## 📅 Upcoming Milestones

| Milestone | Target | Status |
|-----------|--------|--------|
| Context truncation | 2025-10-31 | 🔄 In Progress |
| Automatic summarization | 2025-11-30 | 📋 Planned |
| Cross-session context | 2025-12-31 | 📋 Planned |
| Shared memory | 2026-01-31 | 📋 Planned |
| Semantic memory | 2026-02-28 | 🔮 Future |

---

## ✅ Recent Completions

- [x] Multi-turn filesystem configurations tested (Oct 8)
- [x] Session persistence verified (Oct 8)
- [x] Session recovery after interruption working (Oct 8)
- [x] Multi-turn conversation support (v0.0.27)
- [x] Session persistence to disk (v0.0.28)
- [x] Session recovery and continuation (v0.0.29)

---

## 🚧 Blocked Items

None currently

---

## 💬 Quick Notes

**This Week:**
- Designing context window management strategy
- Testing multi-turn scenarios

**Next Week:**
- Implement truncation-based context management
- Add context limit warnings

**Decisions Needed:**
- Context strategy: Truncation vs. Summarization vs. Selective?
- Should sessions be encrypted by default?
- Auto-cleanup: Age-based or size-based?

**Metrics:**
- Configurations with multi-turn: 10+
- Longest conversation: 15 turns (in testing)
- Session file size: Average 500KB, max 2MB
- Session save/load/recovery success: 100%

**Known Issues:**
- No context window overflow protection (High)
- Large session files not compressed (High)
- No warning when approaching context limits (High)

---

*See [details.md](./details.md) for architecture, dependencies, and long-term vision*
