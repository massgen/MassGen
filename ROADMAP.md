# MassGen Roadmap

**Current Version:** v0.1.9

**Release Schedule:** Mondays, Wednesdays, Fridays @ 9am PT

**Last Updated:** November 8, 2025

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
| Parallel File Operations | [@ncrispino](https://github.com/ncrispino) | nickcrispino |
| Web UI | [@voidcenter](https://github.com/voidcenter) | justin_zhang |

*For general questions, join the #massgen channel on [Discord](https://discord.gg/VVrT2rQaz5)*

---


| Release | Target | Feature | Owner | Use Case |
|---------|--------|---------|-------|----------|
| **v0.1.10** | 11/10/25 | Stream LangGraph & SmoLAgent Steps | @Eric-Shang | Real-time intermediate step streaming for external framework tools |
| | | MassGen Handbook | @a5507203 | Centralized policies and resources for development and research teams |
| **v0.1.11** | 11/12/25 | Gemini Rate Limiting System | @AbhimanyuAryan | Prevent API spam and manage costs within rate limits |
| **v0.1.12** | 11/14/25 | Parallel File Operations | @ncrispino | Increase parallelism and standard efficiency evaluation |

*All releases ship on MWF @ 9am PT when ready*

---

## 📋 v0.1.10 - Framework Streaming & Documentation

### Features

**1. Stream LangGraph & SmoLAgent Intermediate Steps** (@Eric-Shang)
- PR: [#462](https://github.com/massgen/MassGen/pull/462)
- Real-time streaming of intermediate steps for LangGraph framework integration
- Real-time streaming of intermediate steps for SmoLAgent framework integration
- Enhanced user visibility into multi-step agent reasoning processes
- Improved debugging and monitoring for external framework tools
- Consistent streaming experience across all framework integrations
- **Use Case**: Real-time visibility into LangGraph and SmoLAgent reasoning steps, enabling better debugging and monitoring of complex multi-agent workflows

**2. MassGen Handbook** (@a5507203)
- Issue: [#387](https://github.com/massgen/MassGen/issues/387)
- Centralized policies and resources for development and research teams
- Comprehensive user documentation and handbook for MassGen
- Detailed guides covering installation, configuration, and usage patterns
- Best practices and troubleshooting documentation
- Integration examples and case studies
- **Use Case**: Provide centralized policies and resources for development and research teams

### Success Criteria
- ✅ LangGraph intermediate steps stream in real-time
- ✅ SmoLAgent intermediate steps stream in real-time
- ✅ Streaming performance maintains acceptable latency
- ✅ Error handling works correctly during streaming
- ✅ MassGen Handbook provides comprehensive user documentation
- ✅ Documentation updated with streaming examples

---

## 📋 v0.1.11 - Rate Limiting System

### Features

**1. Gemini Rate Limiting System** (@AbhimanyuAryan)
- PR: [#383](https://github.com/Leezekun/MassGen/pull/383) (Draft)
- Multi-dimensional rate limiting for Gemini models (RPM, TPM, RPD)
- Model-specific limits: Flash (9 RPM), Pro (2 RPM)
- Sliding window tracking for precise rate management
- External YAML configuration for centralized limit control
- Optional `--rate-limit` CLI flag to enable/disable
- Mandatory cooldown after agent startup to prevent API bursts
- **Use Case**: Prevent API spam and manage costs while ensuring smooth operation within Gemini's rate limits

### Success Criteria
- ✅ Rate limiting prevents API quota violations and manages costs
- ✅ Features are configurable and well-documented
- ✅ Rate limiting works across all Gemini model types
- ✅ Sliding window tracking is accurate and efficient

---

## 📋 v0.1.12 - Performance Optimization

### Features

**1. Parallel File Operations & Performance** (@ncrispino)
- Issue: [#441](https://github.com/massgen/MassGen/issues/441)
- Increase parallelism of file read operations for improved performance
- Standard methodology for efficiency evaluation and benchmarking
- Optimized file I/O for multi-agent scenarios
- Performance metrics and monitoring framework
- Comprehensive efficiency evaluation with standard metrics
- **Use Case**: Increase parallelism and efficiency with standard evaluation metrics, reducing file operation latency in multi-agent workflows

### Success Criteria
- ✅ Parallel file reads demonstrate measurable performance improvement
- ✅ Efficiency evaluation framework established with clear metrics
- ✅ Standard evaluation methodology implemented and documented
- ✅ Benchmarking shows improvements in real-world scenarios
- ✅ Feature maintains data consistency and safety

---

## 🔨 Ongoing Work & Continuous Releases

These features are being actively developed on **separate parallel tracks** and will ship incrementally on the MWF release schedule:

### Track: Agent Adapter System (@Eric-Shang, ericshang.)
- PR: [#283](https://github.com/Leezekun/MassGen/pull/283)
- Unified agent interface for easier backend integration
- **Shipping:** Continuous improvements

### Track: Irreversible Actions Safety (@franklinnwren, zhichengren)
- Human-in-the-loop approval system for dangerous operations
- LLM-based tool risk detection
- **Target:** v0.1.3 and beyond

### Track: Multimodal Support (@qidanrui, danrui2020)
- PR: [#252](https://github.com/Leezekun/MassGen/pull/252)
- Image, audio, video processing across backends
- **Shipping:** Incremental improvements each release

### Track: Memory Module (@qidanrui, @ncrispino, danrui2020, nickcrispino)
- Issues: [#347](https://github.com/Leezekun/MassGen/issues/347), [#348](https://github.com/Leezekun/MassGen/issues/348)
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
- **Target:** v0.1.10

### Track: Rate Limiting System (@AbhimanyuAryan, abhimanyuaryan)
- PR: [#383](https://github.com/Leezekun/MassGen/pull/383) (Draft)
- Multi-dimensional rate limiting for Gemini models
- Model-specific limits with sliding window tracking
- **Target:** v0.1.11

### Track: MassGen Handbook (@a5507203, @Henry-811, crinvo, henry_weiqi)
- Issue: [#387](https://github.com/massgen/MassGen/issues/387)
- Comprehensive user documentation and handbook
- Centralized policies and resources for development and research teams
- **Target:** v0.1.10

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

### Track: Parallel File Operations (@ncrispino, nickcrispino)
- Issue: [#441](https://github.com/massgen/MassGen/issues/441)
- Increase parallelism of file read operations
- Standard efficiency evaluation and benchmarking methodology
- **Target:** v0.1.12

### Track: Coding Agent Enhancements (@ncrispino, nickcrispino)
- PR: [#251](https://github.com/Leezekun/MassGen/pull/251)
- Enhanced file operations and workspace management
- **Shipping:** Continuous improvement

### Track: Web UI (@voidcenter, justin_zhang)
- PR: [#257](https://github.com/Leezekun/MassGen/pull/257)
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
- [Active Issues](https://github.com/Leezekun/MassGen/issues)
- [Pull Requests](https://github.com/Leezekun/MassGen/pulls)
- [Project Boards](https://github.com/Leezekun/MassGen/projects) (TODO)

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

**Last Updated:** November 8, 2025
**Maintained By:** MassGen Team
