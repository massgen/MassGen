# MassGen v0.1.11 Roadmap

## Overview

Version 0.1.11 focuses on rate limiting and intelligent tool selection, bringing two key enhancements to the MassGen multi-agent coordination experience.

- **Gemini Rate Limiting System** (Required): ⚡ Multi-dimensional rate limiting for Gemini models to prevent API spam and manage costs
- **Automatic MCP Tool Selection** (Required): 🔧 Intelligent selection of MCP tools based on task requirements

## Key Technical Priorities

1. **Gemini Rate Limiting System**: Multi-dimensional rate limiting for Gemini models (RPM, TPM, RPD)
   **Use Case**: Prevent API spam and manage costs while ensuring smooth operation within Gemini's rate limits

2. **Automatic MCP Tool Selection**: Intelligent selection of MCP tools before task execution based on user prompts
   **Use Case**: Intelligently select appropriate MCP tools (e.g., Playwright for web testing) based on task requirements, improving performance without requiring users to know which tools to include

## Key Milestones

### 🎯 Milestone 1: Gemini Rate Limiting System (REQUIRED)

**Goal**: Multi-dimensional rate limiting for Gemini models to prevent API quota violations and manage costs

**Owner**: @AbhimanyuAryan (abhimanyuaryan on Discord)

**PR**: [#383](https://github.com/massgen/MassGen/pull/383) (Draft)

#### 1.1 Rate Limiting Core Implementation
- [ ] Multi-dimensional rate limiting (RPM, TPM, RPD)
- [ ] Model-specific limits: Flash (9 RPM), Pro (2 RPM)
- [ ] Sliding window tracking for precise rate management
- [ ] Request queue management and throttling
- [ ] Token count tracking and estimation

#### 1.2 Configuration System
- [ ] External YAML configuration for centralized limit control
- [ ] Model-specific configuration support
- [ ] Dynamic limit updates without restart
- [ ] Default limits for new models
- [ ] Configuration validation and error handling

#### 1.3 CLI Integration
- [ ] Optional `--rate-limit` CLI flag to enable/disable
- [ ] Runtime configuration override support
- [ ] Status reporting for rate limit state
- [ ] Cooldown period after agent startup
- [ ] Clear user messaging for rate limit events

#### 1.4 Testing and Validation
- [ ] Test sliding window accuracy
- [ ] Validate model-specific limits
- [ ] Test YAML configuration loading
- [ ] Verify mandatory cooldown behavior
- [ ] Documentation and usage examples

**Success Criteria**:
- ✅ Rate limiting prevents API quota violations
- ✅ Model-specific limits work correctly (Flash 9 RPM, Pro 2 RPM)
- ✅ Sliding window tracking is accurate and efficient
- ✅ YAML configuration loads and applies correctly
- ✅ CLI flag enables/disables rate limiting as expected
- ✅ Mandatory cooldown prevents API bursts on startup

---

### 🎯 Milestone 2: Automatic MCP Tool Selection (REQUIRED)

**Goal**: Intelligent selection of MCP tools based on task requirements to improve performance and reduce context pollution

**Owner**: @ncrispino (nickcrispino on Discord)

**Issue**: [#414](https://github.com/massgen/MassGen/issues/414)

#### 2.1 Pre-Execution Tool Selection
- [ ] Intelligent selection of MCP tools before task execution
- [ ] Analysis of user prompts to identify required tools
- [ ] Automatic tool loading based on task requirements
- [ ] Reduction of unnecessary tools in context
- [ ] Support for common tool categories (web, file, data, etc.)

#### 2.2 Dynamic Tool Refinement
- [ ] Dynamic tool refinement during execution
- [ ] Tool addition as task requirements evolve
- [ ] Tool removal when no longer needed
- [ ] Adaptive tool selection based on intermediate results
- [ ] Efficient context management throughout execution

#### 2.3 Filesystem-First Approach
- [ ] MCPs appear as files rather than in-context specifications
- [ ] File-based tool discovery and loading
- [ ] Reduced context pollution from excessive in-context tools
- [ ] Efficient tool metadata storage
- [ ] Fast tool lookup and activation

#### 2.4 User Experience & Testing
- [ ] Eliminate manual tool selection burden for users
- [ ] Automatic selection outperforms manual selection
- [ ] Clear logging of tool selection decisions
- [ ] Testing with various task types and requirements
- [ ] Documentation and usage examples

**Success Criteria**:
- ✅ Automatic tool selection improves task performance vs manual selection
- ✅ Context pollution reduced through filesystem-first approach
- ✅ Tool selection adapts dynamically during execution
- ✅ Users no longer need to manually specify tools
- ✅ Intelligent selection handles common use cases (Playwright for web, etc.)
- ✅ Tool discovery and loading is efficient and reliable

---

## Success Criteria

### Functional Requirements

**Gemini Rate Limiting:**
- [ ] Multi-dimensional rate limiting (RPM, TPM, RPD)
- [ ] Model-specific limits enforced
- [ ] Sliding window tracking implemented
- [ ] YAML configuration support
- [ ] CLI flag for enable/disable

**Automatic MCP Tool Selection:**
- [ ] Pre-execution tool selection based on prompts
- [ ] Dynamic tool refinement during execution
- [ ] Filesystem-first approach implemented
- [ ] Context pollution reduced
- [ ] Manual tool selection eliminated

### Performance Requirements
- [ ] Rate limiting has minimal overhead
- [ ] Tool selection is fast and efficient
- [ ] Overall system remains responsive
- [ ] Sliding window tracking is performant

### Quality Requirements
- [ ] All tests passing
- [ ] Comprehensive documentation
- [ ] YAML configuration examples provided
- [ ] Error handling is robust
- [ ] User-facing messages are clear
- [ ] Rate limit violations prevented

---

## Dependencies & Risks

### Dependencies
- **Gemini Rate Limiting**: Gemini API integration, YAML configuration system, sliding window implementation, request tracking infrastructure
- **Automatic MCP Tool Selection**: MCP tool registry, filesystem abstraction, prompt analysis capabilities, dynamic tool loading system

### Risks & Mitigations
1. **Rate Limit Accuracy**: *Mitigation*: Precise sliding window tracking, token estimation algorithms, extensive testing with real API calls
2. **Configuration Complexity**: *Mitigation*: Clear YAML schema, validation on load, sensible defaults, comprehensive documentation
3. **Tool Selection Accuracy**: *Mitigation*: Prompt analysis testing, fallback to manual selection, user feedback integration
4. **Performance Overhead**: *Mitigation*: Efficient rate tracking, lazy tool loading, minimal context pollution, performance benchmarking
5. **API Changes**: *Mitigation*: Flexible configuration system, monitoring for API updates, version-specific handling

---

## Future Enhancements (Post-v0.1.11)

### v0.1.12 Plans
- **Parallel File Operations** (@ncrispino): Increase parallelism of file read operations with standard efficiency evaluation
- **Semtools Integration** (@ncrispino): Semantic search for files, configs, and automated tool discovery

### v0.1.13 Plans
- **MassGen Terminal Evaluation** (@ncrispino): Self-evaluation and improvement of frontend/UI through terminal recording
- **NLIP Integration** (@qidanrui): Natural Language Integration Platform for hierarchy initialization and RL integration

### Long-term Vision
- **Universal Rate Limiting**: Rate limiting for all backends (OpenAI, Claude, etc.)
- **Advanced Tool Selection**: Machine learning-based tool selection with user preference learning
- **Cost Analytics**: Detailed cost tracking and budget management across all APIs
- **Tool Performance Metrics**: Analytics on tool usage patterns and effectiveness

---

## Timeline Summary

| Phase | Focus | Key Deliverables | Owner | Priority |
|-------|-------|------------------|-------|----------|
| Phase 1 | Rate Limiting | Multi-dimensional rate limiting, YAML config, CLI integration | @AbhimanyuAryan | **REQUIRED** |
| Phase 2 | Tool Selection | Intelligent MCP tool selection, filesystem-first approach, dynamic refinement | @ncrispino | **REQUIRED** |

**Target Release**: November 12, 2025 (Wednesday @ 9am PT)

---

## Getting Started

### For Contributors

**Phase 1 - Gemini Rate Limiting:**
1. Implement multi-dimensional rate limiting (PR #383)
2. Add model-specific limits (Flash 9 RPM, Pro 2 RPM)
3. Implement sliding window tracking
4. Create YAML configuration system
5. Add CLI flag support
6. Add comprehensive tests for rate limiting
7. Document rate limiting configuration and usage

**Phase 2 - Automatic MCP Tool Selection:**
1. Implement pre-execution tool selection (Issue #414)
2. Add dynamic tool refinement during execution
3. Create filesystem-first tool discovery
4. Integrate prompt analysis for tool detection
5. Add testing with various task types
6. Document automatic tool selection behavior

### For Users

- v0.1.11 brings rate limiting and intelligent tool selection:

  **Gemini Rate Limiting:**
  - Prevent API quota violations with multi-dimensional limits
  - Model-specific rate limits (Flash 9 RPM, Pro 2 RPM)
  - Configurable limits via YAML files
  - Optional CLI flag to enable/disable
  - Automatic cooldown on startup to prevent bursts
  - Better cost management and control

  **Automatic MCP Tool Selection:**
  - No more manual tool selection required
  - Intelligent tool selection based on your prompts
  - Dynamic tool loading during task execution
  - Reduced context pollution from unused tools
  - Better performance with optimized tool sets
  - Filesystem-first approach for efficient tool discovery

---

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Development setup and workflow
- Code standards and testing requirements
- Pull request process
- Documentation guidelines

**Contact Track Owners:**
- Gemini Rate Limiting: @AbhimanyuAryan on Discord (abhimanyuaryan)
- Automatic MCP Tool Selection: @ncrispino on Discord (nickcrispino)

---

*This roadmap reflects v0.1.11 priorities focusing on rate limiting and intelligent tool selection.*

**Last Updated:** November 10, 2025
**Maintained By:** MassGen Team
