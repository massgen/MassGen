# MassGen Roadmap

**Current Version:** v0.1.2
**Release Schedule:** Mondays, Wednesdays, Fridays @ 9am PT
**Last Updated:** October 23, 2025

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
| Irreversible Actions Safety | [@franklinnwren](https://github.com/franklinnwren) | zhichengren |
| Memory Module | [@qidanrui](https://github.com/qidanrui) [@ncrispino](https://github.com/ncrispino) | danrui2020, nickcrispino |
| Final Agent Submit/Restart | [@ncrispino](https://github.com/ncrispino) | nickcrispino |
| Coding Agent Enhancements | [@ncrispino](https://github.com/ncrispino) | nickcrispino |
| DSPy Integration | [@praneeth999](https://github.com/praneeth999) | ram2561 |
| Web UI | [@voidcenter](https://github.com/voidcenter) | justin_zhang |

*For general questions, join the #massgen channel on [Discord](https://discord.gg/VVrT2rQaz5)*

---


| Release | Target | Feature | Owner | Use Case |
|---------|--------|---------|-------|----------|
| **v0.1.4** | 10/27/25 | Running MCP Tools in Docker | @qidanrui | Enhanced security and isolation for MCP tool execution |
| | | Enhanced File Operations | @ncrispino | Advanced coding agent workspace management |
| **v0.1.5** | 10/29/25 | General Interoperability | @qidanrui | Enable MassGen to orchestrate agents from multiple frameworks seamlessly |
| | | Memory Module (Phase 1) | @qidanrui @ncrispino | Long-term memory for reasoning tasks and document understanding |
| **v0.1.6** | 10/31/25 | DSPy Integration | @praneeth999 | Automated prompt optimization for domain-specific tasks |
| | | Advanced Voting Mechanism | @qidanrui | Improved decision-making in multi-agent scenarios |

*All releases ship on MWF @ 9am PT when ready*

---

## 📋 v0.1.4 - Docker Integration & Enhanced Coding

### Features

**1. Running MCP Tools in Docker** (@qidanrui)
- Issue: [#346](https://github.com/Leezekun/MassGen/issues/346)
- Containerized execution environment for MCP tools
- Enhanced security and isolation for tool operations
- **Use Case**: Secure execution of third-party tools in isolated environments

**2. Enhanced File Operations** (@ncrispino)
- Issue: [#357](https://github.com/Leezekun/MassGen/issues/357)
- Advanced workspace management for coding agents
- Improved file handling and operations
- **Use Case**: Complex coding tasks requiring sophisticated file manipulation

### Success Criteria
- ✅ MCP tools run securely in Docker containers
- ✅ Enhanced file operations improve coding agent capabilities

---

## 📋 v0.1.5 - Interoperability & Memory

### Features

**1. General Interoperability** (@qidanrui)
- Issue: [#341](https://github.com/Leezekun/MassGen/issues/341)
- Framework integration for external agent systems
- Unified agent interface for seamless integration
- **Use Case**: Complex research workflows requiring specialized agent roles from proven frameworks, enabling MassGen to orchestrate agents from any source

**2. Memory Module (Phase 1)** (@qidanrui, @ncrispino)
- Long-term memory implementation using mem0
- Persistent context across sessions
- **Use Case**: Long-term reasoning tasks and document understanding requiring memory persistence

### Success Criteria
- ✅ External agents can be integrated seamlessly
- ✅ Memory module provides persistent context across sessions

---

## 📋 v0.1.6 - Intelligent Optimization & Advanced Voting

### Features

**1. DSPy Integration** (@praneeth999)
- Automated system prompt optimization for case studies
- Question rephrasing for increased diversity and clarity
- Issue: [#316](https://github.com/Leezekun/MassGen/issues/316)
- **Use Case**: Improve agent performance on domain-specific tasks through automated prompt tuning

**2. Advanced Voting Mechanism** (@qidanrui)
- Issue: [#358](https://github.com/Leezekun/MassGen/issues/358)
- Sophisticated voting strategies for multi-agent decision-making
- Configurable voting rules and consensus mechanisms
- **Use Case**: Complex scenarios requiring nuanced decision-making across multiple agents

### Success Criteria
- ✅ DSPy-optimized prompts outperform manual prompts on benchmarks
- ✅ Advanced voting improves multi-agent coordination quality

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
- PR: TODO
- Long-term memory implementation using mem0
- **Target:** v0.1.5 (Phase 1), later releases (Phase 2)

### Track: Coding Agent Enhancements (@ncrispino, nickcrispino)
- PR: [#251](https://github.com/Leezekun/MassGen/pull/251)
- Enhanced file operations and workspace management
- **Shipping:** Continuous improvement

### Track: Web UI (@voidcenter, justin_zhang)
- PR: [#257](https://github.com/Leezekun/MassGen/pull/257)
- Visual multi-agent coordination interface
- **Target:** ~v0.1.10

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

**Last Updated:** October 24, 2025
**Maintained By:** MassGen Team
