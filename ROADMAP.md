# MassGen Roadmap

**Current Version:** v0.1.8

**Release Schedule:** Mondays, Wednesdays, Fridays @ 9am PT

**Last Updated:** November 5, 2025

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
| Automation & Meta-Coordination | [@ncrispino](https://github.com/ncrispino) | nickcrispino |
| Rate Limiting System | [@AbhimanyuAryan](https://github.com/AbhimanyuAryan) | abhimanyuaryan |
| DSPy Integration | [@praneeth999](https://github.com/praneeth999) | ram2561 |
| MassGen Handbook | [@a5507203](https://github.com/a5507203) [@Henry-811](https://github.com/Henry-811) | crinvo, henry_weiqi |
| Web UI | [@voidcenter](https://github.com/voidcenter) | justin_zhang |

*For general questions, join the #massgen channel on [Discord](https://discord.gg/VVrT2rQaz5)*

---


| Release | Target | Feature | Owner | Use Case |
|---------|--------|---------|-------|----------|
| **v0.1.9** | 11/07/25 | Gemini Rate Limiting System | @AbhimanyuAryan | Prevent API spam and manage costs within rate limits |
| | | MassGen Handbook | @a5507203 | Centralized policies and resources for development and research teams |
| **v0.1.10** | 11/10/25 | Add computer use | @franklinnwren | Visual perception and automated computer interaction |
| | | Session Restart | @ncrispino | Resume previous conversations from log files |
| **v0.1.11** | 11/12/25 | Parallel File Operations & Performance | @ncrispino | Increase parallelism and efficiency with standard evaluation metrics |

*All releases ship on MWF @ 9am PT when ready*

---

## 📋 v0.1.9 - Rate Management & Documentation

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

**2. MassGen Handbook** (@a5507203, @Henry-811)
- Issue: [#387](https://github.com/massgen/MassGen/issues/387) (Open)
- Centralized handbook for MassGen development and research teams
- Common policies and resources for PR activities
- Case study guidelines and templates
- Review processes and standards
- Research documentation and best practices
- **Use Case**: Provide unified reference for contributors, streamlining onboarding and ensuring consistency across development, research, and documentation workflows

### Success Criteria
- ✅ Rate limiting prevents API quota violations and manages costs
- ✅ Handbook provides comprehensive contributor guidelines
- ✅ Features are configurable and well-documented

---

## 📋 v0.1.10 - Computer Use & Session Continuity

### Features

**1. Add computer use** (@franklinnwren)
- PR: [#402](https://github.com/massgen/MassGen/pull/402) (Draft)
- Custom computer use agent tool with Gemini API integration
- Visual perception capabilities through screenshot processing
- Dedicated tool module: `massgen/tool/_computer_using/computer_using_tool.py`
- Configuration support for multiple model types
- Integration with image understanding tools for screen content interpretation
- **Use Case**: Visual perception and automated computer interaction, enabling agents to interpret screen content and execute automated tasks

**2. Session Restart** (@ncrispino)
- Issue: [#412](https://github.com/massgen/MassGen/issues/412) (Open)
- Resume previous MassGen conversations by loading existing log files
- New CLI parameter: `massgen --continue [LOG_DIR]` to initiate fresh conversation with prior dialogue history
- System treats resumed session as "Nth turn in a multi-turn conversation" based on log history
- Default to using same configuration as original session
- Support for specifying different configuration if needed
- Optional: Continue most recent conversation without specifying log directory
- **Use Case**: Resume previous development sessions after closing, mirroring user experience with other LLM tools

### Success Criteria
- ✅ Computer use agent successfully integrated with Gemini API
- ✅ Screenshot processing and visual perception working
- ✅ Configuration examples provided for multiple models
- ✅ Session restart allows seamless continuation of previous conversations

---

## 📋 v0.1.11 - Performance Optimization

### Features

**1. Parallel File Operations & Performance** (@ncrispino)
- Issue: [#441](https://github.com/massgen/MassGen/issues/441) (Open)
- Parallel file read operations instead of sequential reads
- General parallelism enforcement for tool calls across MassGen workflows
- Batch filesystem writes with idempotent write primitives to reduce MCP round trips
- `read_multiple_files` and `write_files_batch` MCP tools for bulk operations
- Checkpoint/resume primitives for long-running workflows to avoid redoing work after interruption
- Standard efficiency evaluation framework to measure MCP call latency and reduction
- Performance metrics tracking for significant speedup verification
- **Use Case**: Address MassGen's inefficiency pain point by maximizing parallelism, reducing sequential operations, and enabling faster context loading for fresh runs

### Success Criteria
- ✅ File operations execute in parallel where possible (measured reduction in sequential reads)
- ✅ Batch write operations reduce MCP round trips
- ✅ Standard efficiency metrics track MCP call count and latency
- ✅ Checkpoint/resume capability supports long-running workflows
- ✅ Measurable performance improvements demonstrated through benchmarks

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

### Track: DSPy Integration (@praneeth999, ram2561)
- Question paraphrasing for multi-agent diversity
- Semantic validation and caching system
- **Status:** ✅ Completed in v0.1.8

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

**Last Updated:** November 5, 2025
**Maintained By:** MassGen Team
