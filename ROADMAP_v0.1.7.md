# MassGen v0.1.7 Roadmap

## Overview

Version 0.1.7 focuses on agent task planning and rate limiting for improved multi-step coordination and API management.

- **Agent Task Planning System** (Required): 📋 Enable agents to organize complex multi-step work with task plans and dependency tracking
- **Gemini Rate Limiting System** (Required): ⚡ Multi-dimensional rate limiting to prevent API spam and manage costs

## Key Technical Priorities

1. **Agent Task Planning System**: Complex multi-step workflows requiring task decomposition, dependency management, and coordinated execution
   **Use Case**: Multi-agent coordination for large projects with interdependent tasks

2. **Gemini Rate Limiting System**: Prevent API quota violations and manage costs while ensuring smooth operation
   **Use Case**: Enterprise deployments requiring cost control and API compliance

## Key Milestones

### 🎯 Milestone 1: Agent Task Planning System (REQUIRED)

**Goal**: Enable agents to organize complex multi-step work with task plans and dependency tracking

**Owner**: @ncrispino (nickcrispino)

**PR**: [#385](https://github.com/Leezekun/MassGen/pull/385) (Draft)

#### 1.1 MCP Planning Tools
- [ ] Implement 8 MCP planning tools for task management
- [ ] Create task plan creation and update tools
- [ ] Build dependency tracking system
- [ ] Add task status monitoring and updates
- [ ] Support for task prioritization

#### 1.2 Task Plan Data Structures
- [ ] Design task plan schema with dependencies
- [ ] Implement task status tracking (pending, in_progress, completed)
- [ ] Create dependency graph validation
- [ ] Add task metadata and context storage
- [ ] Maximum 100 tasks per plan safety limit

#### 1.3 Configuration and Integration
- [ ] Add `enable_agent_task_planning` configuration flag
- [ ] Integrate with existing agent workflows
- [ ] Support for multi-agent task coordination
- [ ] Automatic task status updates during execution
- [ ] Error handling and recovery mechanisms

#### 1.4 Testing and Validation
- [ ] Comprehensive test coverage (1,009+ lines of tests)
- [ ] Validate dependency resolution
- [ ] Test concurrent task execution
- [ ] Performance benchmarks for large task plans
- [ ] Documentation and examples

**Success Criteria**:
- ✅ Task planning tools enable multi-step workflows with dependencies
- ✅ Agents can create, update, and track complex task plans
- ✅ Dependency management works correctly
- ✅ Configuration is well-documented and easy to use

---

### 🎯 Milestone 2: Gemini Rate Limiting System (REQUIRED)

**Goal**: Multi-dimensional rate limiting for Gemini models to prevent API spam and manage costs

**Owner**: @AbhimanyuAryan (TBD on Discord)

**PR**: [#383](https://github.com/Leezekun/MassGen/pull/383) (Draft)

#### 2.1 Rate Limiting Implementation
- [ ] Multi-dimensional rate limiting (RPM, TPM, RPD)
- [ ] Model-specific limits: Flash (9 RPM), Pro (2 RPM)
- [ ] Sliding window tracking for precise rate management
- [ ] Configurable limits via external YAML configuration
- [ ] Mandatory cooldown periods after agent startup

#### 2.2 Configuration System
- [ ] External YAML configuration for centralized limit control
- [ ] Optional `--rate-limit` CLI flag to enable/disable
- [ ] `enable_rate_limit` configuration parameter
- [ ] Model-specific rate limit profiles
- [ ] Dynamic rate limit adjustments

#### 2.3 Rate Tracking and Enforcement
- [ ] Sliding window tracking for RPM, TPM, RPD
- [ ] Request queuing when limits approached
- [ ] Automatic cooldown enforcement
- [ ] Rate limit violation detection and handling
- [ ] Logging and monitoring for rate limit events

#### 2.4 Testing and Validation
- [ ] Test rate limiting accuracy
- [ ] Validate model-specific limits
- [ ] Stress testing with high request volumes
- [ ] Configuration validation
- [ ] Documentation and usage examples

**Success Criteria**:
- ✅ Rate limiting prevents API quota violations
- ✅ Model-specific limits work correctly
- ✅ Configuration is flexible and easy to use
- ✅ Minimal impact on performance
- ✅ Clear monitoring and debugging capabilities

---

## Success Criteria

### Functional Requirements

**Agent Task Planning:**
- [ ] Task planning tools fully functional
- [ ] Dependency tracking works correctly
- [ ] Multi-agent coordination supported
- [ ] Configuration flag enables/disables feature
- [ ] Maximum task limit enforced (100 tasks)

**Gemini Rate Limiting:**
- [ ] Multi-dimensional rate limiting active
- [ ] Model-specific limits enforced
- [ ] YAML configuration working
- [ ] CLI flag enables/disables feature
- [ ] Cooldown periods enforced

### Performance Requirements
- [ ] Task planning has minimal overhead
- [ ] Rate limiting doesn't significantly impact latency
- [ ] Overall system remains responsive
- [ ] Efficient tracking and monitoring

### Quality Requirements
- [ ] All tests passing for both features
- [ ] Comprehensive documentation
- [ ] Configuration examples provided
- [ ] Error handling is robust
- [ ] User-facing messages are clear

---

## Dependencies & Risks

### Dependencies
- **Task Planning**: Existing MCP infrastructure, agent system, orchestrator
- **Rate Limiting**: Gemini backend, configuration system, CLI infrastructure

### Risks & Mitigations
1. **Task Plan Complexity**: *Mitigation*: Limit to 100 tasks, comprehensive validation, clear error messages
2. **Rate Limit Accuracy**: *Mitigation*: Sliding window tracking, extensive testing, configurable safety margins
3. **Performance Impact**: *Mitigation*: Efficient tracking algorithms, minimal overhead design, performance benchmarks
4. **User Adoption**: *Mitigation*: Clear documentation, optional features with sensible defaults, usage examples

---

## Future Enhancements (Post-v0.1.7)

### v0.1.8 Plans
- **DSPy Integration**: Automated prompt optimization for domain-specific tasks

### v0.1.9 Plans
- **Computer Use Agent**: Automated UI testing and browser automation

### Long-term Vision
- **Advanced Task Planning**: Hierarchical task decomposition, parallel execution, automatic task generation
- **Universal Rate Limiting**: Rate limiting for all backends (OpenAI, Claude, etc.)
- **Cost Analytics**: Detailed cost tracking and budget management across all APIs

---

## Timeline Summary

| Phase | Focus | Key Deliverables | Owner | Priority |
|-------|-------|------------------|-------|----------|
| Phase 1 | Agent Task Planning | MCP tools, dependency tracking, configuration | @ncrispino | **REQUIRED** |
| Phase 2 | Gemini Rate Limiting | Multi-dimensional limits, YAML config, CLI flag | @AbhimanyuAryan | **REQUIRED** |

**Target Release**: November 3, 2025 (Monday @ 9am PT)

---

## Getting Started

### For Contributors

**Phase 1 - Agent Task Planning:**
1. Complete MCP planning tools implementation (PR #385)
2. Add comprehensive tests for task planning
3. Validate dependency tracking
4. Create documentation and examples
5. Test multi-agent coordination scenarios

**Phase 2 - Gemini Rate Limiting:**
1. Complete rate limiting implementation (PR #383)
2. Add comprehensive tests for rate tracking
3. Validate model-specific limits
4. Create YAML configuration examples
5. Document CLI usage and configuration

### For Users

- v0.1.7 brings two major capabilities:

  **Agent Task Planning:**
  - Break down complex projects into manageable tasks
  - Track dependencies between tasks
  - Monitor progress across multi-agent workflows
  - Enable/disable via `enable_agent_task_planning` config flag

  **Gemini Rate Limiting:**
  - Prevent API quota violations automatically
  - Manage costs with configurable limits
  - Model-specific rate management (Flash vs Pro)
  - Enable/disable via `--rate-limit` CLI flag

---

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Development setup and workflow
- Code standards and testing requirements
- Pull request process
- Documentation guidelines

**Contact Track Owners:**
- Agent Task Planning: @ncrispino on Discord (nickcrispino)
- Rate Limiting System: @AbhimanyuAryan on Discord (TBD)

---

*This roadmap reflects v0.1.7 priorities focusing on agent task planning and rate limiting. Both features are required for this release.*

**Last Updated:** November 1, 2025
**Maintained By:** MassGen Team
