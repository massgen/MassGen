# MassGen v0.0.27 Roadmap

## Overview

Version 0.0.27 builds upon the filesystem infrastructure of v0.0.26 by focusing on coding agent capabilities, multimodal support, and finishing core refactoring work. Key enhancements include:

- **Coding Agent** (Required): 👨‍💻 Specialized agent for code generation, debugging, and refactoring with enhanced iteration and multi-turn support
- **Multimodal Support** (Required): 🖼️ Complete implementation of image, audio, and video processing capabilities
- **Finish Refactoring Various Aspects of MassGen** (Required): 🏗️ Complete orchestrator and messaging system refactoring for better maintainability
- **Additional Agent Backends from Other Frameworks** (Optional): 🔗 Integration with AG2, LangChain, and other agent frameworks

## Key Technical Priorities

1. **Coding Agent** (REQUIRED): Enhanced system prompts, multi-turn sessions, workspace visibility, and consolidated directory structure
2. **Multimodal Support** (REQUIRED): Complete image, audio, and video processing capabilities
3. **Finish Refactoring Various Aspects of MassGen** (REQUIRED): Complete orchestrator and messaging system refactoring
4. **Additional Agent Backends from Other Frameworks** (OPTIONAL): Integration with AG2, LangChain, and other frameworks

## Key Milestones

### 🎯 Milestone 1: Coding Agent (REQUIRED)

**Goal**: Specialized agent for code generation, debugging, and refactoring with enhanced iteration and multi-turn support

#### 1.1 Enhanced System Prompts for Coding (REQUIRED)
- [ ] Design enhanced system prompts encouraging more iterations (Issue #224)
- [ ] Implement coding-specific voting prompts focused on code quality
- [ ] Add iteration encouragement messaging for coding tasks
- [ ] Create prompts emphasizing independent exploration over convergence
- [ ] Test prompt effectiveness on coding task diversity

#### 1.2 Enhanced Multi-turn Conversation Support (REQUIRED)
- [ ] Create `CodingSessionManager` for specialized coding conversation history management
- [ ] Enhance turn-based context preparation with code-specific context
- [ ] Implement path normalization for multi-turn references
- [ ] Design interactive multi-turn CLI commands for coding tasks (Issue #231)


#### 1.3 Workspace Logging & Visibility (REQUIRED)
- [ ] Implement `WorkspaceDiffLogger` for iteration comparison
- [ ] Add automatic workspace diff generation between iterations
- [ ] Create cross-agent workspace comparison logging
- [ ] Add similarity scoring to detect convergence vs diversity
- [ ] Integrate diff logging with orchestrator workflow

#### 1.4 Enhanced `.massgen/` Directory Management (REQUIRED)
- [ ] Implement `MassGenProjectManager` for advanced directory management
- [ ] Add automatic `.gitignore` creation for `.massgen/`
- [ ] Create cleanup utilities for old session data


### 🎯 Milestone 2: Multimodal Support (REQUIRED)

**Goal**: Complete implementation of image, audio, and video processing capabilities

#### 2.1 Multimodal Message Architecture (REQUIRED)
- [ ] Design unified message format supporting text, images, audio, and video
- [ ] Implement stream chunks class for different media types
- [ ] Create serialization/deserialization for multimodal content
- [ ] Add support for media file streaming and chunking
- [ ] Design media metadata and content type handling

#### 2.2 Backend Multimodal Integration (REQUIRED)
- [ ] Extend existing backends (Claude, Gemini, OpenAI) with multimodal support
- [ ] Implement vision model support for image processing
- [ ] Add audio processing capabilities where supported
- [ ] Create multimodal tool integration framework
- [ ] Test multimodal capabilities across all backends

#### 2.3 Frontend and UI Multimodal Support (REQUIRED)
- [ ] Update CLI to handle multimodal inputs and outputs
- [ ] Implement media file upload and processing
- [ ] Add media preview and display capabilities
- [ ] Create multimodal conversation history management
- [ ] Add configuration options for media processing settings


### 🎯 Milestone 3: Finish Refactoring Various Aspects of MassGen (REQUIRED)

**Goal**: Complete orchestrator and messaging system refactoring for better maintainability and multimodal support

#### 3.1 Orchestrator Refactoring (REQUIRED)
- [ ] Extract coordination logic into separate modules
- [ ] Simplify agent communication flow and state management
- [ ] Remove duplicated code and consolidate utility functions
- [ ] Improve error handling and recovery mechanisms
- [ ] Add comprehensive unit tests for orchestrator components

#### 3.2 Messaging System Refactoring (REQUIRED)
- [ ] Extract messaging logic from backend implementations
- [ ] Implement unified stream chunks class for all message types
- [ ] Create abstraction layer separating messaging from backends
- [ ] Add support for multimodal message routing and processing
- [ ] Implement efficient message serialization and caching

#### 3.3 Performance and Testing (REQUIRED)
- [ ] Optimize agent coordination and message passing performance
- [ ] Add comprehensive integration tests for refactored components
- [ ] Create performance benchmarks and profiling tools
- [ ] Update architecture documentation and diagrams
- [ ] Ensure backward compatibility with existing configurations


### 🎯 Milestone 4: Additional Agent Backends from Other Frameworks (OPTIONAL)

**Goal**: Integration with AG2, LangChain, and other agent frameworks

#### 4.1 Framework Analysis and Design (OPTIONAL)
- [ ] Research AG2, LangChain, CrewAI, and AutoGen integration patterns
- [ ] Design unified adapter interface for external frameworks
- [ ] Analyze compatibility requirements and limitations
- [ ] Plan migration path for framework-specific features
- [ ] Document integration architecture and patterns

#### 4.2 Framework Adapters Implementation (OPTIONAL)
- [ ] Implement AG2 agent adapter with conversation support
- [ ] Create LangChain agent wrapper with tool integration
- [ ] Add CrewAI multi-agent coordination adapter
- [ ] Implement AutoGen conversation flow integration
- [ ] Add framework-specific configuration management

#### 4.3 Integration and Testing (OPTIONAL)
- [ ] Create mixed-framework multi-agent configurations
- [ ] Add comprehensive testing for framework adapters
- [ ] Implement framework-specific tool and capability mapping
- [ ] Create documentation and examples for each framework
- [ ] Add performance benchmarking for framework adapters

## Success Criteria

### Functional Requirements (REQUIRED)

**Coding Agent:**
- [ ] Enhanced system prompts encouraging more iterations
- [ ] Specialized `CodingSessionManager` for coding workflows
- [ ] Workspace diff logging with similarity scoring
- [ ] Advanced `.massgen/` directory management utilities

**Multimodal & Infrastructure:**
- [ ] Complete multimodal support (images, audio, video)
- [ ] Refactored orchestrator and messaging system
- [ ] Backward compatibility with v0.0.26 configurations

### Functional Requirements (OPTIONAL)
- [ ] Integration with at least two external agent frameworks (AG2, LangChain)
- [ ] Framework adapter system for external agent integration
- [ ] Docker-based overlay workspaces for advanced isolation (Future)
- [ ] Drop-in CLI usage with auto-detection (Future)
- [ ] Large-scale task decomposition (Future)

### Performance Requirements (REQUIRED)
- [ ] No performance degradation from orchestrator and messaging refactoring
- [ ] Efficient multimodal content processing and streaming
- [ ] Improved memory efficiency in long-running multimodal sessions
- [ ] Optimized message passing for multimodal content

### Quality Requirements (REQUIRED)
- [ ] Comprehensive test coverage for multimodal capabilities
- [ ] Documentation for refactored orchestrator and messaging architecture
- [ ] Integration tests for multimodal workflows
- [ ] Unit tests for all refactored components
- [ ] Migration guide for multimodal configuration changes

## Dependencies & Risks

### Dependencies
- **Media Processing Libraries**: PIL/Pillow, FFmpeg, audio processing libraries
- **Streaming I/O**: Support for chunked streaming of large media files
- **Memory Management**: Efficient handling of large multimodal content
- **External Frameworks**: AG2, LangChain, CrewAI, AutoGen SDKs and APIs

### Risks & Mitigations
1. **Large Media File Handling**: *Mitigation*: Streaming operations, chunking, size limits
2. **Multimodal Processing Performance**: *Mitigation*: Efficient algorithms, lazy loading, caching
3. **Framework Compatibility**: *Mitigation*: Abstraction layers, comprehensive testing
4. **Memory Usage with Media Content**: *Mitigation*: Memory monitoring, garbage collection
5. **Breaking Changes from Refactoring**: *Mitigation*: Backward compatibility, migration guides

## Post-v0.0.26 Considerations

### Future Enhancements (v0.0.27+)
- **Web UI**: Modern web interface for MassGen with real-time agent coordination visualization
- **Irreversible Actions Management**: Safety mechanisms when agents work in parallel to prevent conflicts
- **Address Minority Voting Problem**: Improved consensus mechanisms for multi-agent decision making
- **Enterprise MCP Marketplace**: Advanced marketplace features for organizations

### Long-term Vision
- **Enterprise File Management**: Advanced file operation capabilities for large organizations
- **AI-Powered Code Generation**: Sophisticated code generation with learning capabilities
- **Real-time Collaboration**: Multi-user file editing and collaboration features
- **Advanced Analytics**: Deep insights into agent performance and optimization opportunities

## Timeline Summary

| Week | Focus | Key Deliverables | Status |
|------|-------|------------------|--------|
| 1-2 | Multimodal Support | Complete image, audio, video processing | ⏳ **PENDING** |
| 3 | Refactoring Completion | Orchestrator and messaging system refactor | ⏳ **PENDING** |
| 4 | Optional Features | Framework integrations and coding agent | ⏳ **PENDING** |
| 5 | Release Preparation | Final testing and v0.0.26 release | ⏳ **PENDING** |

## Getting Started

### For Contributors

1. Implement complete multimodal support for images, audio, and video processing
2. Finish refactoring orchestrator and messaging systems for better maintainability
3. Consider integrating additional agent frameworks (AG2, LangChain)
4. Develop specialized coding agent capabilities
5. Create comprehensive tests for all new multimodal and refactored components

### For Users
- v0.0.26 will provide full multimodal capabilities across all supported backends
- Improved system architecture through completed refactoring work
- All v0.0.25 configurations will continue to work unchanged
- Optional integration with external agent frameworks for expanded capabilities

---

*This roadmap represents our commitment to delivering complete multimodal capabilities and finishing core architectural improvements, establishing MassGen as a comprehensive platform for multimodal multi-agent collaboration.*
