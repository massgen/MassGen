# Memory Track

**Lead:** TBD | **Status:** 🟢 Active | **Updated:** 2025-01-15

**Mission:** Enable MassGen agents to maintain context, remember conversations, and learn from past interactions across sessions.

---

## 🎯 Current Sprint (v0.0.30+)

### P0 - Critical
- [ ] Implement context window management (truncation)
- [ ] Context overflow protection

### P1 - High
- [ ] Test multi-turn with all backends
- [ ] Document session storage format
- [ ] Add context overflow warnings

### P2 - Medium
- [ ] Add context summarization
- [ ] Session cleanup utilities
- [ ] Privacy/encryption for sessions

---

## 🔄 In Progress

### Context Window Management
**Status:** Design phase | **Assignee:** Open | **Priority:** P0

**Challenge:** Long conversations exceed model context limits

**Strategies Being Considered:**
1. **Truncation:** Remove oldest messages (simple, fast, loses early context)
2. **Summarization:** Summarize old context (preserves info, requires API calls)
3. **Selective Context:** Keep only relevant messages (optimal, complex)

**Current Thinking:** Start with truncation, add summarization later

### Multi-Turn Testing
**Status:** Active | **Assignee:** Open | **Priority:** P1

**Testing Scenarios:**
- ✅ 2-turn conversations
- ✅ 5-turn conversations
- 🔄 10+ turn conversations
- ⏳ Context overflow scenarios
- ⏳ Session crash recovery

**Issues Found:**
- Some backends don't handle long context well
- Session files can get large (>1MB)
- Context overflow errors not user-friendly

---

## ✅ Recently Completed

- [x] Multi-turn filesystem configurations tested (Oct 8)
- [x] Session persistence verified (Oct 8)
- [x] Session recovery after interruption working (Oct 8)
- [x] **v0.0.27:** Multi-turn conversation support
- [x] **v0.0.28:** Session persistence to disk
- [x] **v0.0.29:** Session recovery and continuation

---

## 🚧 Blocked

None currently

---

## 📝 Notes & Decisions Needed

**Discussion Topics:**
- Context management: Truncation vs. Summarization vs. Selective?
- Should sessions be encrypted by default?
- Auto-cleanup: Age-based or size-based?

**Decisions Needed:**
- **Context Strategy:** Which approach for v0.0.30?
- **Storage Backend:** JSON files vs. database?
- **Privacy:** Encryption on by default?

**Metrics:**
- Configurations with multi-turn: 10+
- Longest conversation: 15 turns (in testing)
- Session file size: Average 500KB, max 2MB
- Session save time: <100ms
- Session save/load/recovery success: 100%

**Known Issues:**
- No context window overflow protection (High)
- Large session files not compressed (High)
- No warning when approaching context limits (High)
- Session cleanup not automated (Medium)
- No session search/query capability (Medium)

**Working Use Cases:**
- Multi-turn code refactoring with iterative improvements
- Conversational data analysis with follow-up questions
- Interrupted workflows with resume after crash

**Requested Features:**
- Cross-session context (remember across different sessions)
- Shared memory (agents learn from each other's history)
- Long-term memory (facts/knowledge beyond current session)
- Semantic search (find relevant past conversations)

---

## Track Information

### Scope

**In Scope:**
- Multi-turn conversation support
- Session persistence and recovery
- Context window management
- Conversation history
- Cross-session learning (future)
- Agent memory sharing
- Efficient context compression

**Out of Scope (For Now):**
- Long-term external memory (databases)
- Episodic memory systems
- Training data generation
- Model fine-tuning

### Current State

**Multi-Turn Support:** ✅ Implemented

**Configuration:**
```yaml
orchestrator:
  session_storage: "sessions"    # Enable multi-turn
```

**Features:**
- Conversation history preserved across turns
- Session saved to disk (JSON)
- Session recovery after crash
- Per-agent conversation context

**Examples:** `massgen/configs/tools/filesystem/multiturn/`

### Session Storage Format

```json
{
  "session_id": "uuid",
  "created_at": "timestamp",
  "agents": ["agent_a", "agent_b"],
  "turns": [
    {
      "turn_number": 1,
      "user_message": "...",
      "agent_responses": {...},
      "winner": "agent_a"
    }
  ]
}
```

**Directory Structure:**
```
sessions/
├── session-{uuid}.json          # Individual session
└── session-{uuid}-metadata.json # Session info
```

### Context Window Limits

Different backends have different limits:
- GPT-4o: 128k tokens
- Claude 3: 200k tokens
- Gemini 1.5: 1M tokens
- GPT-5 nano: 32k tokens

**Challenge:** Keep conversation within limits while maintaining relevant context.

**Current Strategy:**
- Truncation (planned)
- Summarization (future)
- Selective Context (future)

### Team & Resources

**Contributors:** Open to community contributors
**GitHub Label:** `track:memory`
**Examples:** `massgen/configs/tools/filesystem/multiturn/`
**Code:** `massgen/orchestrator.py` (session management)

**Related Tracks:**
- **Coding Agent:** Multi-turn filesystem operations
- **AgentAdapter backends:** Context window per backend
- **Web UI:** Display conversation history

### Dependencies

**Internal:**
- `massgen.orchestrator` - Session management
- `massgen.backend` - Context window info
- `massgen.message_templates` - Message formatting

**External:**
- JSON storage
- File system
- Future: Database (Redis, PostgreSQL)

### Key Challenges

1. **Context Window Management:** Long conversations exceed model limits
2. **Cross-Agent Memory:** Agents don't share learnings
3. **Efficient Storage:** Sessions can be large (MB)
4. **Privacy:** Sessions may contain sensitive info

---

## Long-Term Vision

See **[roadmap.md](./roadmap.md)** for 3-6 month goals including semantic memory, episodic memory systems, and agent learning from history.

---

*Track lead: Update sprint section weekly. Update long-term vision in roadmap.md monthly.*
