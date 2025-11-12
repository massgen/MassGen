# MassGen Roadmap

**Current Version:** v0.1.11

**Release Schedule:** Mondays, Wednesdays, Fridays @ 9am PT

**Last Updated:** November 12, 2025

This roadmap outlines MassGen's development priorities for upcoming releases. Each release focuses on specific capabilities with real-world use cases.

---

## 👥 Contributors & Contact

Want to contribute or collaborate on a specific track? Reach out to the track owners below:

| Track | GitHub | Discord |
|-------|--------|---------|
| Tool System Refactoring | [@qidanrui](https://github.com/qidanrui) | danrui2020 |
| Multimodal Support | [@qidanrui](https://github.com/qidanrui) | danrui2020 |
| General Interoperability | [@qidanrui](https://github.com/qidanrui) | danrui2020 |
| Agent Adapter System | [@Eric-Shang](https://github.com/Eric-Shang) | ericshang. |
| Framework Streaming | [@Eric-Shang](https://github.com/Eric-Shang) | ericshang. |
| Irreversible Actions Safety | [@franklinnwren](https://github.com/franklinnwren) | zhichengren |
| Computer Use | [@franklinnwren](https://github.com/franklinnwren) | zhichengren |
| Memory Module | [@qidanrui](https://github.com/qidanrui) [@ncrispino](https://github.com/ncrispino) | danrui2020, nickcrispino |
| Rate Limiting System | [@AbhimanyuAryan](https://github.com/AbhimanyuAryan) | abhimanyuaryan |
| DSPy Integration | [@praneeth999](https://github.com/praneeth999) | ram2561 |
| MassGen Handbook | [@a5507203](https://github.com/a5507203) [@Henry-811](https://github.com/Henry-811) | crinvo, henry_weiqi |
| Session Management | [@ncrispino](https://github.com/ncrispino) | nickcrispino |
| Automatic MCP Tool Selection | [@ncrispino](https://github.com/ncrispino) | nickcrispino |
| Parallel File Operations | [@ncrispino](https://github.com/ncrispino) | nickcrispino |
| Semtools Integration | [@ncrispino](https://github.com/ncrispino) | nickcrispino |
| MassGen Terminal Evaluation | [@ncrispino](https://github.com/ncrispino) | nickcrispino |
| Multi-Agent Computer Use | TBD | TBD |
| Web UI | [@voidcenter](https://github.com/voidcenter) | justin_zhang |

*For general questions, join the #massgen channel on [Discord](https://discord.gg/VVrT2rQaz5)*

---


| Release | Target | Feature | Owner | Use Case |
|---------|--------|---------|-------|----------|
| **v0.1.12** | 11/14/25 | Automatic MCP Tool Selection | @ncrispino | Intelligently select MCP tools based on task requirements |
| | | Semtools/Serena Semantic Search Skill | @ncrispino | Implement semantic search capabilities as a reusable skill |
| **v0.1.13** | 11/17/25 | Parallel File Operations | @ncrispino | Increase parallelism and standard efficiency evaluation |
| | | Semtools Integration | @ncrispino | Semantic search for files, configs, and tool discovery |
| **v0.1.14** | 11/19/25 | MassGen Terminal Evaluation | @ncrispino | Self-evaluation and improvement of frontend/UI |
| | | NLIP Integration | @qidanrui | Natural Language Integration Platform for hierarchy initialization and RL integration |

*All releases ship on MWF @ 9am PT when ready*

---

## 📋 v0.1.12 - Intelligent Tool Selection & Semantic Search

### Features

**1. Automatic MCP Tool Selection** (@ncrispino)
- Issue: [#414](https://github.com/massgen/MassGen/issues/414)
- Intelligent selection of MCP tools before task execution based on user prompts
- Dynamic tool refinement during execution as task requirements evolve
- Filesystem-first approach where MCPs appear as files rather than in-context specifications
- Reduces context pollution from excessive in-context tools (currently >30)
- Eliminates manual tool selection burden for users
- **Use Case**: Intelligently select appropriate MCP tools (e.g., Playwright for web testing) based on task requirements, improving performance without requiring users to know which tools to include

**2. Semtools/Serena Semantic Search Skill** (@ncrispino)
- Issue: [#497](https://github.com/massgen/MassGen/issues/497)
- Implement semtools and serena for advanced semantic search capabilities
- Package as a reusable skill within the MassGen skills framework
- Enable semantic understanding of code, documentation, and configuration files
- Support for multiple embedding models and vector databases
- Integration with existing file search and discovery mechanisms
- **Use Case**: Provide intelligent semantic search across codebases, enabling agents to find relevant code and documentation based on meaning rather than just keywords

### Success Criteria
- ✅ Automatic tool selection improves task performance vs manual selection
- ✅ Context pollution reduced through filesystem-first approach
- ✅ Tool selection adapts dynamically during execution
- ✅ Semantic search skill successfully integrates with existing skills framework
- ✅ Semantic search outperforms keyword-based search for code discovery
- ✅ Support for multiple embedding models and configurable backends

---

## 📋 v0.1.13 - Performance Optimization & Semantic Search

### Features

**1. Parallel File Operations & Performance** (@ncrispino)
- Issue: [#441](https://github.com/massgen/MassGen/issues/441)
- Increase parallelism of file read operations for improved performance
- Standard methodology for efficiency evaluation and benchmarking
- Optimized file I/O for multi-agent scenarios
- Performance metrics and monitoring framework
- Comprehensive efficiency evaluation with standard metrics
- **Use Case**: Increase parallelism and efficiency with standard evaluation metrics, reducing file operation latency in multi-agent workflows

**2. Semtools Integration** (@ncrispino)
- Issue: [#465](https://github.com/massgen/MassGen/issues/465)
- Semantic search capabilities for file parsing and retrieval using [semtools](https://github.com/run-llama/semtools)
- Semantic understanding for filesystem efficiency (PDFs, various document formats)
- Intelligent configuration file and MCP tool discovery through semantic search
- Automatic identification of relevant tools before prompt execution
- Replaces keyword matching with semantic understanding for better accuracy
- **Use Case**: Enable semantic search for files, configurations, and automated tool discovery, improving search performance and reducing manual configuration effort

### Success Criteria
- ✅ Parallel file reads demonstrate measurable performance improvement
- ✅ Efficiency evaluation framework established with clear metrics
- ✅ Standard evaluation methodology implemented and documented
- ✅ Benchmarking shows improvements in real-world scenarios
- ✅ Feature maintains data consistency and safety
- ✅ Semtools semantic search outperforms keyword-based search
- ✅ Tool discovery automation reduces manual configuration
- ✅ Semantic search handles diverse document formats effectively

---

## 📋 v0.1.14 - Self-Evaluation & NLIP Integration

### Features

**1. MassGen Terminal Evaluation** (@ncrispino)
- Issue: [#476](https://github.com/massgen/MassGen/issues/476)
- Enable MassGen to evaluate and improve its own frontend/UI
- Terminal session recording using asciinema for visual analysis
- Automatic caption generation for recorded sessions
- Video editing integration for demonstration materials
- Comprehensive case study generation from terminal recordings
- Self-improvement capabilities extended to frontend (currently backend-only via automation mode)
- **Use Case**: Enable MassGen to analyze its own terminal interface, creating demonstration videos and documentation automatically, showcasing new features through automated workflows

**2. NLIP Integration** (@qidanrui)
- PR: [#475](https://github.com/massgen/MassGen/pull/475) (Draft)
- Natural Language Integration Platform for enhanced agent coordination
- Hierarchy initialization for structured multi-agent systems
- Reinforcement learning integration components
- Advanced orchestration patterns with NLIP architecture
- Foundation for sophisticated agent coordination strategies
- **Use Case**: Enable advanced multi-agent coordination through NLIP's hierarchy and reinforcement learning capabilities, improving agent collaboration and decision-making

### Success Criteria
- ✅ Terminal recording and playback system works reliably
- ✅ Video understanding capabilities accurately analyze terminal sessions
- ✅ Automated case study generation produces high-quality documentation
- ✅ MassGen successfully self-improves based on terminal analysis
- ✅ NLIP hierarchy initialization works correctly
- ✅ Reinforcement learning components integrate seamlessly
- ✅ Advanced orchestration patterns demonstrate improved performance

---

## 🔨 Ongoing Work & Continuous Releases

These features are being actively developed on **separate parallel tracks** and will ship incrementally on the MWF release schedule:

### Track: Agent Adapter System (@Eric-Shang, ericshang.)
- PR: [#283](https://github.com/massgen/MassGen/pull/283)
- Unified agent interface for easier backend integration
- **Shipping:** Continuous improvements

### Track: Irreversible Actions Safety (@franklinnwren, zhichengren)
- Human-in-the-loop approval system for dangerous operations
- LLM-based tool risk detection
- **Target:** v0.1.3 and beyond

### Track: Multimodal Support (@qidanrui, danrui2020)
- PR: [#252](https://github.com/massgen/MassGen/pull/252)
- Image, audio, video processing across backends
- **Shipping:** Incremental improvements each release

### Track: Memory Module (@qidanrui, @ncrispino, danrui2020, nickcrispino)
- Issues: [#347](https://github.com/massgen/MassGen/issues/347), [#348](https://github.com/massgen/MassGen/issues/348)
- Short and long-term memory implementation with persistence
- **Status:** ✅ Completed in v0.1.5

### Track: Agent Task Planning (@ncrispino, nickcrispino)
- Agent task planning with dependency tracking
- **Status:** ✅ Completed in v0.1.7

### Track: Automation & Meta-Coordination (@ncrispino, nickcrispino)
- LLM agent automation with status tracking and silent execution
- MassGen running MassGen for self-improvement workflows
- **Status:** ✅ Completed in v0.1.8
- **Case Study:** Meta-level self-analysis demonstrating automation mode (`meta-self-analysis-automation-mode.md`)

### Track: DSPy Integration (@praneeth999, ram2561)
- Question paraphrasing for multi-agent diversity
- Semantic validation and caching system
- **Status:** ✅ Completed in v0.1.8

### Track: Framework Streaming (@Eric-Shang, ericshang.)
- PR: [#462](https://github.com/massgen/MassGen/pull/462)
- Real-time streaming for LangGraph and SmoLAgent intermediate steps
- Enhanced debugging and monitoring for external framework tools
- **Status:** ✅ Completed in v0.1.10

### Track: Rate Limiting System (@AbhimanyuAryan, abhimanyuaryan)
- PR: [#383](https://github.com/massgen/MassGen/pull/383)
- Multi-dimensional rate limiting for Gemini models
- Model-specific limits with sliding window tracking
- **Status:** ✅ Completed in v0.1.11

### Track: MassGen Handbook (@a5507203, @Henry-811, crinvo, henry_weiqi)
- Issue: [#387](https://github.com/massgen/MassGen/issues/387)
- Comprehensive user documentation and handbook at https://massgen.github.io/Handbook/
- Centralized policies and resources for development and research teams
- **Status:** ✅ Completed in v0.1.10

### Track: Computer Use (@franklinnwren, zhichengren)
- PR: [#402](https://github.com/massgen/MassGen/pull/402)
- Browser and desktop automation with OpenAI, Claude, and Gemini integration
- Visual perception through screenshot processing and action execution
- **Status:** ✅ Completed in v0.1.9

### Track: Session Management (@ncrispino, nickcrispino)
- PR: [#466](https://github.com/massgen/MassGen/pull/466)
- Complete session state tracking and restoration
- Resume previous MassGen conversations with full context
- **Status:** ✅ Completed in v0.1.9

### Track: Automatic MCP Tool Selection (@ncrispino, nickcrispino)
- Issue: [#414](https://github.com/massgen/MassGen/issues/414)
- Intelligent selection of MCP tools based on task requirements
- Filesystem-first approach to reduce context pollution
- **Target:** v0.1.12

### Track: Parallel File Operations (@ncrispino, nickcrispino)
- Issue: [#441](https://github.com/massgen/MassGen/issues/441)
- Increase parallelism of file read operations
- Standard efficiency evaluation and benchmarking methodology
- **Target:** v0.1.13

### Track: Semtools Integration (@ncrispino, nickcrispino)
- Issue: [#465](https://github.com/massgen/MassGen/issues/465)
- Semantic search for files, configs, and automated tool discovery
- Replace keyword matching with semantic understanding
- **Target:** v0.1.13

### Track: MassGen Terminal Evaluation (@ncrispino, nickcrispino)
- Issue: [#476](https://github.com/massgen/MassGen/issues/476)
- Self-evaluation and improvement of frontend/UI through terminal recording
- Automated video generation and case study creation
- **Target:** v0.1.14

### Track: NLIP Integration (@qidanrui, danrui2020)
- PR: [#475](https://github.com/massgen/MassGen/pull/475) (Draft)
- Natural Language Integration Platform for enhanced agent coordination
- Hierarchy initialization and reinforcement learning integration
- **Target:** v0.1.14

### Track: Coding Agent Enhancements (@ncrispino, nickcrispino)
- PR: [#251](https://github.com/massgen/MassGen/pull/251)
- Enhanced file operations and workspace management
- **Shipping:** Continuous improvement

### Track: Web UI (@voidcenter, justin_zhang)
- PR: [#257](https://github.com/massgen/MassGen/pull/257)
- Visual multi-agent coordination interface
- **Target:** TBD

---

## 🎯 Long-Term Vision (v0.2.0+)

**Advanced Orchestration Patterns**
- Task/subtask decomposition and parallel coordination
- Assignment of agents to specific tasks and increasing of diversity
- Improvement in voting as tasks continue

**Visual Workflow Designer**
- No-code multi-agent workflow creation
- Drag-and-drop agent configuration
- Real-time testing and debugging

**Enterprise Features**
- Role-based access control (RBAC)
- Audit logs and compliance reporting
- Multi-user collaboration
- Advanced analytics and cost tracking

**Additional Framework Integrations**
- LangChain agent support
- CrewAI compatibility
- Custom framework adapters

**Complete Multimodal Pipeline**
- End-to-end audio processing (speech-to-text, text-to-speech)
- Video understanding and generation
- Advanced document processing (PDF, Word, Excel)

---

## 🔗 GitHub Integration

Track development progress:
- [Active Issues](https://github.com/massgen/MassGen/issues)
- [Pull Requests](https://github.com/massgen/MassGen/pulls)
- [Project Boards](https://github.com/massgen/MassGen/projects) (TODO)

---

## 🤝 Contributing

Interested in contributing? You have two options:

**Option 1: Join an Existing Track**
1. See [Contributors & Contact](#-contributors--contact) table above for active tracks
2. Contact the track owner via Discord to discuss your ideas
3. Follow [CONTRIBUTING.md](CONTRIBUTING.md) for development process

**Option 2: Create Your Own Track**
1. Have a significant feature idea? Propose a new track!
2. Reach out via the #massgen channel on [Discord](https://discord.gg/VVrT2rQaz5)
3. Work with the MassGen dev team to integrate your track into the roadmap
4. Become a track owner and guide other contributors

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, code standards, testing, and documentation requirements.

---

## 📚 Related Documentation

- [CHANGELOG.md](CHANGELOG.md) - Complete release history
- [CONTRIBUTING.md](CONTRIBUTING.md) - Contribution guidelines
- [Documentation](https://docs.massgen.ai/en/latest/) - Full user guide

---

*This roadmap is community-driven. Releases ship on **Mondays, Wednesdays, Fridays @ 9am PT**. Timelines may shift based on priorities and feedback. Open an issue to suggest changes!*

**Last Updated:** November 13, 2025
**Maintained By:** MassGen Team
