# MassGen v0.1.12 Roadmap

## Overview

Version 0.1.12 focuses on intelligent tool selection and semantic search capabilities, bringing key enhancements to the MassGen multi-agent coordination experience.

- **Automatic MCP Tool Selection** (Required): 🔧 Intelligent selection of MCP tools based on task requirements
- **Semtools/Serena Semantic Search Skill** (Required): 🔍 Implementation of semantic search capabilities as a reusable skill

## Key Technical Priorities

1. **Automatic MCP Tool Selection**: Intelligent selection of MCP tools before task execution based on user prompts
   **Use Case**: Intelligently select appropriate MCP tools (e.g., Playwright for web testing) based on task requirements, improving performance without requiring users to know which tools to include

2. **Semtools/Serena Semantic Search Skill**: Advanced semantic search capabilities packaged as a reusable skill
   **Use Case**: Provide intelligent semantic search across codebases, enabling agents to find relevant code and documentation based on meaning rather than just keywords

## Key Milestones

### 🎯 Milestone 1: Automatic MCP Tool Selection (REQUIRED)

**Goal**: Intelligent selection of MCP tools based on task requirements to improve performance and reduce context pollution

**Owner**: @ncrispino (nickcrispino on Discord)

**Issue**: [#414](https://github.com/massgen/MassGen/issues/414)

#### 1.1 Pre-Execution Tool Selection
- [ ] Intelligent selection of MCP tools before task execution
- [ ] Analysis of user prompts to identify required tools
- [ ] Automatic tool loading based on task requirements
- [ ] Reduction of unnecessary tools in context
- [ ] Support for common tool categories (web, file, data, etc.)

#### 1.2 Dynamic Tool Refinement
- [ ] Dynamic tool refinement during execution
- [ ] Tool addition as task requirements evolve
- [ ] Tool removal when no longer needed
- [ ] Adaptive tool selection based on intermediate results
- [ ] Efficient context management throughout execution

#### 1.3 Filesystem-First Approach
- [ ] MCPs appear as files rather than in-context specifications
- [ ] File-based tool discovery and loading
- [ ] Reduced context pollution from excessive in-context tools
- [ ] Efficient tool metadata storage
- [ ] Fast tool lookup and activation

#### 1.4 User Experience & Testing
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

### 🎯 Milestone 2: Semtools/Serena Semantic Search Skill (REQUIRED)

**Goal**: Implement semantic search capabilities as a reusable skill within the MassGen skills framework

**Owner**: @ncrispino (nickcrispino on Discord)

**Issue**: [#497](https://github.com/massgen/MassGen/issues/497)

#### 2.1 Core Semantic Search Implementation
- [ ] Implement semtools and serena for semantic search
- [ ] Support for multiple embedding models
- [ ] Vector database integration
- [ ] Efficient indexing and retrieval mechanisms
- [ ] Support for various file types and formats

#### 2.2 Skills Framework Integration
- [ ] Package as a reusable skill within MassGen skills framework
- [ ] Skill configuration and initialization
- [ ] Integration with existing file search mechanisms
- [ ] Compatibility with other skills
- [ ] Documentation for skill usage

#### 2.3 Semantic Understanding Capabilities
- [ ] Semantic understanding of code structures
- [ ] Documentation and comment analysis
- [ ] Configuration file comprehension
- [ ] Cross-file semantic relationships
- [ ] Context-aware search results

#### 2.4 Performance and Testing
- [ ] Benchmark against keyword-based search
- [ ] Optimize embedding generation and caching
- [ ] Test with various codebases and languages
- [ ] Validate search accuracy and relevance
- [ ] Documentation and usage examples

**Success Criteria**:
- ✅ Semantic search skill successfully integrates with existing skills framework
- ✅ Semantic search outperforms keyword-based search for code discovery
- ✅ Support for multiple embedding models and configurable backends
- ✅ Efficient indexing and retrieval performance
- ✅ Comprehensive documentation and examples provided
- ✅ Works seamlessly with other MassGen skills

---

## Success Criteria

### Functional Requirements

**Automatic MCP Tool Selection:**
- [ ] Pre-execution tool selection based on prompts
- [ ] Dynamic tool refinement during execution
- [ ] Filesystem-first approach implemented
- [ ] Context pollution reduced
- [ ] Manual tool selection eliminated

**Semtools/Serena Semantic Search:**
- [ ] Semantic search skill implemented and integrated
- [ ] Multiple embedding models supported
- [ ] Vector database integration functional
- [ ] Skills framework compatibility achieved
- [ ] Performance benchmarks completed

### Performance Requirements
- [ ] Tool selection is fast and efficient
- [ ] Semantic search indexing is optimized
- [ ] Overall system remains responsive
- [ ] Embedding generation is performant

### Quality Requirements
- [ ] All tests passing
- [ ] Comprehensive documentation
- [ ] Configuration examples provided
- [ ] Error handling is robust
- [ ] User-facing messages are clear
- [ ] Search relevance is validated

---

## Dependencies & Risks

### Dependencies
- **Automatic MCP Tool Selection**: MCP tool registry, filesystem abstraction, prompt analysis capabilities, dynamic tool loading system
- **Semtools/Serena Semantic Search**: Skills framework, embedding models, vector database, semtools/serena libraries, filesystem access

### Risks & Mitigations
1. **Tool Selection Accuracy**: *Mitigation*: Prompt analysis testing, fallback to manual selection, user feedback integration
2. **Semantic Search Performance**: *Mitigation*: Caching strategies, optimized indexing, lazy loading, performance benchmarking
3. **Embedding Model Compatibility**: *Mitigation*: Support multiple models, fallback options, clear documentation on model requirements
4. **Skills Framework Integration**: *Mitigation*: Thorough testing with existing skills, clear API contracts, backward compatibility
5. **Search Relevance**: *Mitigation*: Continuous tuning, user feedback loop, hybrid search fallback (semantic + keyword)

---

## Future Enhancements (Post-v0.1.12)

### v0.1.13 Plans
- **Parallel File Operations** (@ncrispino): Increase parallelism of file read operations with standard efficiency evaluation
- **Semtools Integration** (@ncrispino): Semantic search for files, configs, and automated tool discovery

### v0.1.14 Plans
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
| Phase 1 | Tool Selection | Intelligent MCP tool selection, filesystem-first approach, dynamic refinement | @ncrispino | **REQUIRED** |
| Phase 2 | Semantic Search | Semtools/serena implementation, skills framework integration, semantic capabilities | @ncrispino | **REQUIRED** |

**Target Release**: November 14, 2025 (Friday @ 9am PT)

---

## Getting Started

### For Contributors

**Phase 1 - Automatic MCP Tool Selection:**
1. Implement pre-execution tool selection (Issue #414)
2. Add dynamic tool refinement during execution
3. Create filesystem-first tool discovery
4. Integrate prompt analysis for tool detection
5. Add testing with various task types
6. Document automatic tool selection behavior

**Phase 2 - Semtools/Serena Semantic Search:**
1. Implement semtools and serena integration (Issue #497)
2. Create skill wrapper for semantic search
3. Add support for multiple embedding models
4. Integrate with vector database
5. Add benchmarking and performance tests
6. Document skill usage and configuration

### For Users

- v0.1.12 brings intelligent tool selection and semantic search capabilities:

  **Automatic MCP Tool Selection:**
  - No more manual tool selection required
  - Intelligent tool selection based on your prompts
  - Dynamic tool loading during task execution
  - Reduced context pollution from unused tools
  - Better performance with optimized tool sets
  - Filesystem-first approach for efficient tool discovery

  **Semtools/Serena Semantic Search:**
  - Advanced semantic search across codebases
  - Find code based on meaning, not just keywords
  - Support for multiple embedding models
  - Integrated as a reusable skill
  - Better code discovery and understanding
  - Works with various file types and languages

---

## 🤝 Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Development setup and workflow
- Code standards and testing requirements
- Pull request process
- Documentation guidelines

**Contact Track Owners:**
- Automatic MCP Tool Selection: @ncrispino on Discord (nickcrispino)
- Semtools/Serena Semantic Search: @ncrispino on Discord (nickcrispino)

---

*This roadmap reflects v0.1.12 priorities focusing on intelligent tool selection and semantic search capabilities.*

**Last Updated:** November 13, 2025
**Maintained By:** MassGen Team
