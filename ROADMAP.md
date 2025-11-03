# MassGen Roadmap

**Current Version:** v0.1.7

**Release Schedule:** Mondays, Wednesdays, Fridays @ 9am PT

**Last Updated:** November 3, 2025

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
| Rate Limiting System | [@AbhimanyuAryan](https://github.com/AbhimanyuAryan) | TBD |
| DSPy Integration | [@praneeth999](https://github.com/praneeth999) | ram2561 |
| Web UI | [@voidcenter](https://github.com/voidcenter) | justin_zhang |

*For general questions, join the #massgen channel on [Discord](https://discord.gg/VVrT2rQaz5)*

---


| Release | Target | Feature | Owner | Use Case |
|---------|--------|---------|-------|----------|
| **v0.1.8** | 11/05/25 | Gemini Rate Limiting System | @AbhimanyuAryan | Prevent API spam and manage costs within rate limits |
| **v0.1.9** | 11/07/25 | Add computer use | @franklinnwren | Visual perception and automated computer interaction |
| | | Case study summary | @franklinnwren | Comprehensive case study documentation |
| **v0.1.10** | 11/10/25 | DSPy Integration | @praneeth999 | Automated prompt optimization for domain-specific tasks |

*All releases ship on MWF @ 9am PT when ready*

---

## 📋 v0.1.8 - Rate Management

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
- ✅ Feature is configurable and well-documented

---

## 📋 v0.1.9 - Computer Use Agent

### Features

**1. Add computer use** (@franklinnwren)
- PR: [#402](https://github.com/massgen/MassGen/pull/402) (Draft)
- Custom computer use agent tool with Gemini API integration
- Visual perception capabilities through screenshot processing
- Dedicated tool module: `massgen/tool/_computer_using/computer_using_tool.py`
- Configuration support for multiple model types
- Integration with image understanding tools for screen content interpretation
- **Use Case**: Visual perception and automated computer interaction, enabling agents to interpret screen content and execute automated tasks

**2. Case study summary** (@franklinnwren)
- PR: [#401](https://github.com/massgen/MassGen/pull/401) (Open)
- Case study summary documentation
- Comprehensive case study guide for MassGen features
- **Use Case**: Provide case study documentation demonstrating MassGen capabilities across different features

### Success Criteria
- ✅ Computer use agent successfully integrated with Gemini API
- ✅ Screenshot processing and visual perception working
- ✅ Configuration examples provided for multiple models
- ✅ Case study documentation completed and published

---

## 📋 v0.1.10 - Intelligent Optimization

### Features

**1. DSPy Integration** (@praneeth999)
- Branch: `mcp_refactor` (In Progress)
- Automated system prompt optimization for case studies
- Question rephrasing for increased diversity and clarity
- QuestionParaphraser module for multi-agent coordination
- **Use Case**: Improve agent performance on domain-specific tasks through automated prompt tuning

### Success Criteria
- ✅ DSPy-optimized prompts outperform manual prompts on benchmarks
- ✅ Question paraphrasing increases diversity and clarity
- ✅ Feature is well-documented with examples

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

**Last Updated:** November 3, 2025
**Maintained By:** MassGen Team
