# MassGen Roadmap

**Current Version:** v0.1.6

**Release Schedule:** Mondays, Wednesdays, Fridays @ 9am PT

**Last Updated:** November 1, 2025

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
| Agent Task Planning | [@ncrispino](https://github.com/ncrispino) | nickcrispino |
| Rate Limiting System | [@AbhimanyuAryan](https://github.com/AbhimanyuAryan) | TBD |
| DSPy Integration | [@praneeth999](https://github.com/praneeth999) | ram2561 |
| Web UI | [@voidcenter](https://github.com/voidcenter) | justin_zhang |

*For general questions, join the #massgen channel on [Discord](https://discord.gg/VVrT2rQaz5)*

---


| Release | Target | Feature | Owner | Use Case |
|---------|--------|---------|-------|----------|
| **v0.1.7** | 11/03/25 | Agent Task Planning System | @ncrispino | Complex multi-step workflows with dependency management |
| | | Gemini Rate Limiting System | @AbhimanyuAryan | Prevent API spam and manage costs within rate limits |
| **v0.1.8** | 11/06/25 | DSPy Integration | @praneeth999 | Automated prompt optimization for domain-specific tasks |
| **v0.1.9** | 11/08/25 | Computer Use Agent | @qidanrui | Automated UI testing and browser automation |

*All releases ship on MWF @ 9am PT when ready*

---

## 📋 v0.1.7 - Agent Task Planning & Rate Limiting

### Features

**1. Agent Task Planning System** (@ncrispino)
- PR: [#385](https://github.com/Leezekun/MassGen/pull/385) (Draft)
- Enable agents to organize complex multi-step work with task plans
- 8 new MCP planning tools for task management and dependency tracking
- Automatic task status tracking and progress monitoring
- Configurable via `enable_agent_task_planning` flag
- Maximum 100 tasks per plan for safety
- **Use Case**: Complex multi-step workflows requiring task decomposition, dependency management, and coordinated execution across multiple agents

**2. Gemini Rate Limiting System** (@AbhimanyuAryan)
- PR: [#383](https://github.com/Leezekun/MassGen/pull/383) (Draft)
- Multi-dimensional rate limiting for Gemini models (RPM, TPM, RPD)
- Model-specific limits: Flash (9 RPM), Pro (2 RPM)
- Sliding window tracking for precise rate management
- External YAML configuration for centralized limit control
- Optional `--rate-limit` CLI flag to enable/disable
- Mandatory cooldown after agent startup to prevent API bursts
- **Use Case**: Prevent API spam and manage costs while ensuring smooth operation within Gemini's rate limits

### Success Criteria
- ✅ Task planning tools enable multi-step workflows with dependencies
- ✅ Rate limiting prevents API quota violations and manages costs
- ✅ Both features are configurable and well-documented

---

## 📋 v0.1.8 - Intelligent Optimization

### Features

**1. DSPy Integration** (@praneeth999)
- Issue: [#316](https://github.com/Leezekun/MassGen/issues/316)
- Automated system prompt optimization for case studies
- Question rephrasing for increased diversity and clarity
- **Use Case**: Improve agent performance on domain-specific tasks through automated prompt tuning

### Success Criteria
- ✅ DSPy-optimized prompts outperform manual prompts on benchmarks

---

## 📋 v0.1.9 - Computer Use Agent

### Features

**1. Computer Use Agent Integration** (@qidanrui)
- Issue: [#358](https://github.com/Leezekun/MassGen/issues/358)
- Computer use agent integration with custom tools system
- Enable agents to interact with computer interfaces
- **Use Case**: Automated UI testing, browser automation, and desktop application interaction

### Success Criteria
- ✅ Computer use agent successfully integrated with custom tools

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

**Last Updated:** November 1, 2025
**Maintained By:** MassGen Team
