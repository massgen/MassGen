# MassGen Roadmap

**Current Version:** v0.1.1
**Release Schedule:** Mondays, Wednesdays, Fridays @ 9am PT
**Last Updated:** October 20, 2025

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
| Memory Module | [@kitrakrev](https://github.com/kitrakrev) | kitrak_23536 |
| Final Agent Submit/Restart | [@ncrispino](https://github.com/ncrispino) | nickcrispino |
| Coding Agent Enhancements | [@ncrispino](https://github.com/ncrispino) | nickcrispino |
| DSPy Integration | [@praneeth999](https://github.com/praneeth999) | ram2561 |
| Web UI | [@voidcenter](https://github.com/voidcenter) | justin_zhang |

*For general questions, join the #massgen channel on [Discord](https://discord.gg/VVrT2rQaz5)*

---

## 🚀 Upcoming Releases

| Release | Target | Feature | Owner | Use Case |
|---------|--------|---------|-------|----------|
| **v0.1.1** | ✅ 10/20/25 | Custom Tools System | @qidanrui | User-defined Python functions as tools alongside MCP servers |
| | | Voting Sensitivity Controls | @qidanrui | Three-tier voting system for multi-agent quality control |
| | | Interactive Config Builder | @ncrispino | Wizard for creating YAML configurations |
| **v0.1.2** | 10/22/25 | General Interoperability | @qidanrui | Enable MassGen to orchestrate agents from multiple frameworks seamlessly |
| | | Final Agent Submit/Restart Tools | @ncrispino | Multi-step task verification and intelligent restart decisions |
| | | Memory Module (Phase 1) | @kitrakrev | Long-term memory for reasoning tasks and document understanding |
| **v0.1.3** | 10/24/25 | DSPy Integration | @praneeth999 | Automated prompt optimization for domain-specific tasks |
| | | Irreversible Actions Safety | @franklinnwren | Safety controls for production deployments with dangerous operations |

*All releases ship on MWF @ 9am PT when ready*

---

## 📋 v0.1.1 - Custom Tools & Quality Controls ✅ COMPLETED

**Released:** October 20, 2025

### Features Delivered

**1. Custom Tools System** (@qidanrui) ✅
- Complete framework for registering user-defined Python functions as tools
- New `ToolManager` class for centralized tool registration and lifecycle management
- Support for custom tools alongside MCP servers across all backends
- 40+ example configurations demonstrating custom tool usage
- **Use Case**: Domain-specific workflows with custom Python functions (data processing, API integration, specialized computations)

**2. Voting Sensitivity & Answer Novelty Controls** (@qidanrui) ✅
- Three-tier voting system: "lenient", "balanced", "strict"
- Answer novelty detection preventing duplicate submissions
- Configurable quality thresholds for multi-agent coordination
- **Use Case**: Quality control for multi-agent systems requiring high-quality consensus

**3. Interactive Configuration Builder** (@ncrispino) ✅
- Wizard for creating YAML configurations with step-by-step prompts
- Backend selection, model configuration, and API key setup
- Integration via `massgen --config-builder` command
- **Use Case**: Simplified onboarding for new users and rapid prototyping

### Success Criteria
- ✅ Custom tools system fully functional across all backends
- ✅ Voting sensitivity controls improving answer quality
- ✅ Configuration builder simplifying setup process

---

## 📋 v0.1.2 - General Interoperability & Enterprise Collaboration

### Features

**1. General Interoperability** (@qidanrui)
- Issue: [#341](https://github.com/Leezekun/MassGen/issues/341)
- Framework integration for external agent systems
- Unified agent interface for seamless integration
- **Use Case**: Complex research workflows requiring specialized agent roles from proven frameworks, enabling MassGen to orchestrate agents from any source

**2. Final Agent Submit/Restart Tools** (@ncrispino)
- Issue: [#325](https://github.com/Leezekun/MassGen/issues/325)
- Enable final agent to decide whether to submit answer or restart orchestration
- Agent can access previous agents' responses and workspaces when restarting
- **Use Case**: Multi-step tasks where completion requires verification (repository cloning + issue resolution, planning-mode scenarios)

### Success Criteria
- ✅ Final agent can intelligently decide to restart when task is incomplete
- ✅ Documentation with use case examples

---

## 📋 v0.1.3 - Intelligent Optimization & Safety

### Features

**1. DSPy Integration** (@praneeth999)
- Automated system prompt optimization for case studies
- Question rephrasing for increased diversity and clarity
- Issue: [#316](https://github.com/Leezekun/MassGen/issues/316)
- **Use Case**: Improve agent performance on domain-specific tasks through automated prompt tuning

**2. Irreversible Actions Safety** (@franklinnwren)
- LLM-generated detection of irreversible MCP tools
- Optional human-in-the-loop approval
- Per-user customizable tool lists
- **Use Case**: Writing to real-world documents, database operations, production deployments where safety is critical

### Success Criteria
- ✅ DSPy-optimized prompts outperform manual prompts on benchmarks
- ✅ Safety controls prevent accidental irreversible operations

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

### Track: Memory Module (@kitrakrev, kitrak_23536)
- PR: TODO
- Long-term memory implementation using mem0
- **Target:** v0.1.1 (Phase 1), v0.1.2 (Phase 2)

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

**Last Updated:** October 20, 2025
**Maintained By:** MassGen Team
