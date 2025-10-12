# AgentAdapter Backends Track

**Lead:** Eric | **Status:** 🟢 Active | **Updated:** 2025-01-15

**Mission:** Enable MassGen to work with any LLM provider through consistent, well-tested backend adapters.

---

## 🎯 Current Sprint (v0.0.30)

### P0 - Critical
- None currently

### P1 - High
- [ ] Test all backends with latest API versions
- [ ] Document cost tracking for each backend
- [ ] Standardize error messages across backends

### P2 - Medium
- [ ] Add DeepSeek backend support
- [ ] Improve streaming performance for Gemini
- [ ] Create backend comparison matrix

---

## 🔄 In Progress

### AG2 Framework Integration
**Status:** Active development | **Assignee:** Eric | **PR:** [#283](https://github.com/Leezekun/MassGen/pull/283)

Integrating agents from the AG2 (formerly AutoGen) framework into MassGen.

**Phase 1 (PR #283):** Single agent integration
**Phase 2 (upcoming PRs):** Group chat patterns
- Summarization method
- AutoPattern
- Round robin pattern
- Nested chat

### Backend Reliability Improvements
**Status:** Active development | **Assignee:** Open

Improving error handling, retries, and failover across all backends.

**Current Issues:**
- Some backends don't handle rate limits gracefully
- Streaming interruptions need better recovery
- Token limit errors need better user messaging

### MCP Tools Integration
**Status:** Testing phase | **Assignee:** Open

Ensuring all MCP-enabled backends work consistently with MCP tools.

---

## ✅ Recently Completed

- [x] GPT-5 nano/mini support added (v0.0.27)
- [x] Grok 3/4 integration (v0.0.28)
- [x] Enhanced MCP tools backend integration (v0.0.29)
- [x] Streaming response optimization ongoing

---

## 🚧 Blocked

None currently

---

## 📝 Notes & Decisions Needed

**Discussion Topics:**
- Should we add DeepSeek backend for cost-effective options?
- Best practices for handling provider-specific features
- How to handle model deprecations gracefully

**Supported Backends:**
- Commercial: OpenAI, Anthropic Claude, Google Gemini, xAI Grok, Azure OpenAI, Inference.net
- Local/Open Source: LM Studio, vLLM, Chat Completions API
- Specialized: External backend, MCP Tools integration

---

## Track Information

### Scope

**In Scope:**
- Backend adapters for major LLM providers
- Consistent API abstraction across backends
- Model capability detection and validation
- Cost tracking and optimization
- Streaming response handling
- Error handling and retries

**Out of Scope (For Now):**
- Training custom models
- Fine-tuning integrations
- Model hosting infrastructure

### Unified Interface

All backends implement:
- `generate()` - Single turn generation
- `stream()` - Streaming responses
- `tool_use()` - Function calling
- `vision()` - Image understanding (if supported)

### Model Capabilities

Auto-detect:
- Context window size
- Tool calling support
- Vision capabilities
- Streaming availability
- Cost per token

### Error Handling

- Automatic retries with exponential backoff
- Rate limit handling
- API error translation to common format
- Graceful degradation

### Team & Resources

**Contributors:** Open to community contributors
**GitHub Label:** `track:backends`
**Examples:** `massgen/configs/basic/multi/`
**Code:** `massgen/backend/`
**Tests:** `massgen/tests/` (backend tests)

**Related Tracks:**
- **Multimodal:** Vision capabilities
- **Coding Agent:** MCP tools integration
- **All Tracks:** All depend on backends

### Architecture

**Backend Structure:**
```
massgen/backend/
├── base.py              # Abstract base class
├── base_with_mcp.py     # MCP tools mixin
├── response.py          # Response format
├── openai.py            # OpenAI models
├── claude.py            # Anthropic Claude
├── claude_code.py       # Claude Code variant
├── gemini.py            # Google Gemini
├── grok.py              # xAI Grok
├── azure_openai.py      # Azure OpenAI
├── lmstudio.py          # LM Studio local
├── inference.py         # Inference.net
├── chat_completions.py  # Generic OpenAI-compatible
└── external.py          # Custom integrations
```

### Dependencies

**Internal:**
- `massgen.message_templates` - Message formatting
- `massgen.orchestrator` - Agent coordination
- `massgen.mcp_tools` - Tool integration

**External:**
- OpenAI Python SDK
- Anthropic Python SDK
- Google Generative AI SDK
- Various API clients

---

## Long-Term Vision

See **[roadmap.md](./roadmap.md)** for 3-6 month goals including additional providers, advanced error recovery, and performance optimization.

---

*Track lead: Update sprint section weekly. Update long-term vision in roadmap.md monthly.*
