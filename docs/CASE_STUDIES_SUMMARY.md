# MassGen Case Studies Summary

This document provides a comprehensive overview of all MassGen case studies, organized by category and version.

## Overview

MassGen is focused on **case-driven development**. Each case study demonstrates real-world multi-agent collaboration on complex tasks, with actual session logs and outcomes. All case studies follow the PLANNING → TESTING → EVALUATION cycle and include video demonstrations where available.

### Release Features & Technical Capabilities

| Title | Version | Short Description | Status | Link |
|-------|---------|-------------------|--------|------|
| **Session Management & Computer Use Tools** | v0.1.9 | Complete session state tracking and restoration for multi-turn conversations, computer use automation tools (Claude/Gemini/OpenAI) for browser and desktop control, enhanced config builder with fuzzy model matching | ✅ Ready | [📄 Guide](massgen/backend/docs/COMPUTER_USE_TOOLS_GUIDE.md) |
| **Automation Mode Enables Meta Self-Analysis** | v0.1.8 | Automation infrastructure with `--automation` flag providing clean structured output, enabling agents to run nested MassGen experiments and analyze results for meta-level self-analysis | ✅ Ready | [📄 Case Study](docs/source/examples/case_studies/meta-self-analysis-automation-mode.md) · [🎥 Video](https://youtu.be/W60TT7NwJSk) |
| **Agent Task Planning & Background Execution** | v0.1.7 | MCP-based task management with dependency tracking, background shell execution for long-running commands, and preemption-based coordination for improved multi-agent workflows | ✅ Ready | Documentation in v0.1.7 changelog |
| **Persistent Memory with Semantic Retrieval** | v0.1.5 | Research-to-implementation workflow demonstrating memory system with automatic fact extraction, vector storage, and semantic retrieval across multi-turn sessions | ✅ Ready | [📄 Case Study](docs/source/examples/case_studies/multi-turn-persistent-memory.md) · [🎥 Video](https://youtu.be/wWxxFgyw40Y) |
| **Multimodal Video Analysis** | v0.1.3 | Meta-level demonstration where agents autonomously download and analyze their own case study videos to identify improvements and automation opportunities | ✅ Ready | [📄 Case Study](docs/source/examples/case_studies/multimodal-case-study-video-analysis.md) · [🎥 Video](https://youtu.be/nRP34Bqz-D4) |
| **Custom Tools with GitHub Issue Market Analysis** | v0.1.1 | Self-evolution through market analysis using custom Python tools combined with web search to analyze GitHub issues, research trends, and drive feature prioritization | ✅ Ready | [📄 Case Study](docs/source/examples/case_studies/github-issue-market-analysis.md) |
| **Universal Code Execution via MCP** | v0.0.31 | Universal code execution capabilities through MCP enabling agents across all backends to run commands, execute tests, and validate code (pytest, uv run, npm test) | ✅ Ready | [📄 Case Study](docs/source/examples/case_studies/universal-code-execution-mcp.md) |
| **MCP Planning Mode for Safe Tool Coordination** | v0.0.29 | Strategic coordination approach allowing agents to plan MCP tool usage without execution during collaboration, preventing irreversible actions until consensus | ✅ Ready | [📄 Case Study](docs/source/examples/case_studies/mcp-planning-mode.md) |
| **AG2 Framework Integration** | v0.0.28 | External agent adapter system enabling MassGen to orchestrate agents from AG2 framework with code execution capabilities while maintaining consensus architecture | ✅ Ready | [📄 Case Study](docs/source/examples/case_studies/ag2-framework-integration.md) · [🎥 Video](https://www.youtube.com/watch?v=Ui2c-GpCqK0) |
| **Multi-Turn Filesystem Support** | v0.0.25 | Multi-turn filesystem support with persistent context enabling agents to build websites iteratively (Bob Dylan tribute site example) | ✅ Ready | [📄 Case Study](docs/source/examples/case_studies/multi-turn-filesystem-support.md) |
| **Advanced Filesystem with User Context Path Support** | v0.0.21-v0.0.22 | Advanced filesystem permissions with user context paths, copy MCP integration, and selective path exposure for secure multi-agent workspace collaboration | ✅ Ready | [📄 Case Study](docs/source/examples/case_studies/user-context-path-support-with-copy-mcp.md) · [🎥 Video](https://youtu.be/uGy7DufDbK4) |
| **Unified Filesystem Support with MCP Integration** | v0.0.16 | Unified filesystem capabilities demonstrating cross-workspace coordination, conflict-free development with per-agent versioning, and final workspace snapshots | ✅ Ready | [📄 Case Study](docs/source/examples/case_studies/unified-filesystem-mcp-integration.md) |
| **Gemini MCP Notion Integration** | v0.0.15 | Integration with Notion via MCP demonstrating seamless third-party tool integration for knowledge management and documentation workflows | ✅ Ready | [📄 Case Study](docs/source/examples/case_studies/gemini-mcp-notion-integration.md) |
| **Enhanced Logging and Workspace Management** | v0.0.12-v0.0.14 | Enhanced logging capabilities and workspace management for better debugging, session tracking, and coordination history analysis | ✅ Ready | [📄 Case Study](docs/source/examples/case_studies/claude-code-workspace-management.md) |

### Research & Analysis

| Title | Version | Short Description | Status | Link |
|-------|---------|-------------------|--------|------|
| **Berkeley Agentic AI Summit Summary** | v0.0.3 | Agents handle specialized research queries with strict source constraints, demonstrating precise adherence to academic standards and framework-specific talk analysis | ✅ Ready | [📄 Case Study](docs/source/examples/case_studies/berkeley-conference-talks.md) · [🎥 Video](https://www.youtube.com/watch?v=Dp2oldJJImw) |
| **AI News Synthesis** | v0.0.3 | Cross-verification and content aggregation excellence demonstrating how agents synthesize diverse AI news sources with fact-checking and consensus building | ✅ Ready | [📄 Case Study](docs/source/examples/case_studies/diverse_ai_news.md) |
| **Grok-4 HLE Benchmark Cost Analysis** | v0.0.3 | Unanimous expert consensus on complex pricing calculations through iterative refinement, demonstrating collaborative validation for technical analysis | ✅ Ready | [📄 Case Study](docs/source/examples/case_studies/grok_hle_cost.md) |

### Travel & Recommendations

| Title | Version | Short Description | Status | Link |
|-------|---------|-------------------|--------|------|
| **Stockholm Travel Guide** | v0.0.3 | Extended intelligence sharing and comprehensive convergence where agents collaborate to create detailed travel recommendations with diverse perspectives | ✅ Ready | [📄 Case Study](docs/source/examples/case_studies/stockholm_travel_guide.md) |

### Creative & Problem Solving

| Title | Version | Short Description | Status | Link |
|-------|---------|-------------------|--------|------|
| **Super Intelligence Approaches** | v0.0.4 | Complex philosophical and technical question exploration leveraging different reasoning capacities (minimal, medium, high) for comprehensive analysis | ✅ Ready | [📄 Case Study](docs/source/examples/case_studies/SuperIntelligence.md) · [🎥 Video](https://www.youtube.com/watch?v=ZLQ7b096hEU) |
| **Comprehensive Algorithm Enumeration** | v0.0.4 | Technical analysis demonstrating how agents collaboratively enumerate and compare different algorithmic approaches (Fibonacci algorithms) | ✅ Ready | [📄 Case Study](docs/source/examples/case_studies/fibonacci_number_algorithms.md) |
| **IMO 2025 AI Winners** | v0.0.3 | Agents tackle International Mathematical Olympiad problems demonstrating collaborative mathematical reasoning and problem-solving capabilities | ✅ Ready | [📄 Case Study](docs/source/examples/case_studies/imo_2025_winner.md) |
| **Collaborative Creative Writing** | v0.0.3 | Multi-agent creative writing collaboration showcasing diverse narrative perspectives and consensus-driven story development | ✅ Ready | [📄 Case Study](docs/source/examples/case_studies/collaborative_creative_writing.md) |

### In Development

| Title | Version | Short Description | Status | Link |
|-------|---------|-------------------|--------|------|
| **Web UI Development - Collaborative Design** | v0.1.x | Three agents competitively build complete dashboard implementations with peer review and voting. Demonstrated production-ready output in 12 minutes with unanimous consensus | ✅ Completed | [📄 Draft PR](https://github.com/Leezekun/MassGen/pull/375) · Session: `log_20251025_222849` |
| **Interactive Course Generator** | v0.1.x | 5-agent sequential pipeline transforming PDFs/textbooks into interactive courses with Q&A, drag-and-match exercises, flowcharts, and code examples | 📝 Planning | [📄 Quick Reference](docs/case_studies/interactive-course-generator-QUICKREF.md) |
| **Codebase Architecture Analysis** | v0.1.x | Multi-agent collaborative analysis of large codebases (FastAPI) creating comprehensive architecture documentation by reading 30+ files | 🧪 In Testing | Config: `tools/memory/gpt5mini_gemini_codebase_analysis_memory.yaml` |
| **Revert Feature After Final Agent Failure** | v0.1.1 | Automated rollback mechanism when final agent execution fails, ensuring safe multi-agent operations | ⏸️ Blocked | [📄 Issue #325](https://github.com/Leezekun/MassGen/issues/325) |
| **Twitter Integration Case Study** | v0.x | Multi-agent Twitter posting and engagement with MCP integration | ⏸️ Blocked | Blocked by Twitter rate limits, will revisit |

### Planned (Backlog)

| Title | Version | Short Description | Status | Link |
|-------|---------|-------------------|--------|------|
| **Web Agent Browsing** | Future | Agents autonomously browse and interact with web applications using Gemini 2.5 Computer Use and OpenAI Operator for complex web tasks | 📋 Planned | Target: [Online Mind2Web Leaderboard](https://huggingface.co/spaces/osunlp/Online_Mind2Web_Leaderboard) |
| **Map-Reduce Document Processing** | Future | Assign one document per agent to process, vote on which documents require manager attention. Applications: meeting notes prioritization, paper selection, email triage | 📋 Planned | Needs: separate document processing, scalable multi-agent, user-defined voting criteria |
| **Website Creation from Scratch** | Future | Produce high-quality website better than existing tools (e.g., Manus.im) with multi-agent collaboration | 📋 Planned | Needs: Playwright/Computer Use, image understanding, filesystem memory, multi-turn memory, OpenAI Operator/Gemini Computer Use |
| **MassGen Video Recording and Editing** | Future | Auto-generate case study videos: run command, record, edit (speed up, captions, log highlights), produce 1-min demo videos automatically | 📋 Planned | Needs: video understanding, cmd execution, video editing MCP, planning mode for >10min tasks |
| **Paper Reviewing** | Future | Provide detailed academic paper feedback competing with tools like Refine.ink | 📋 Planned | Research-focused multi-agent review with quality assessment |
| **Priority-Based Document Ranking** | Future | Vote on document importance for busy managers/researchers: meeting notes, conference papers, stock news, emails | 📋 Planned | Info-to-attention prediction with custom voting criteria |

## Case Study Template

For contributors who want to create their own case studies:

| Title | Description | Status | Link |
|-------|-------------|--------|------|
| **Case Study Template** | Comprehensive template with PLANNING → TESTING → EVALUATION structure, including baseline analysis, success criteria, and status tracking | 📝 Template | [📄 Template](docs/source/examples/case_studies/case-study-template.md) |

## Statistics

- **Total Case Studies**: 36
  - ✅ Ready: 22 (completed with documentation)
  - ✅ Completed: 1 (Web UI Development)
  - 📝 Planning: 1 (Interactive Course Generator)
  - 🧪 In Testing: 1 (Codebase Analysis)
  - ⏸️ Blocked: 2 (Revert Feature, Twitter Integration)
  - 📋 Planned: 7 (future backlog)
  - 📝 Template: 1
- **With Video Demonstrations**: 9
- **Release Versions Covered**: v0.0.3 to v0.1.9
- **Categories**: 6 (Release Features, Research, Travel, Creative, In Development, Planned)

## Key Features Demonstrated

### Technical Capabilities
- ✅ Session state tracking and restoration (v0.1.9)
- ✅ Computer use automation (browser & desktop control) (v0.1.9)
- ✅ Fuzzy model name matching and discovery (v0.1.9)
- ✅ Automation mode for meta-analysis (v0.1.8)
- ✅ DSPy question paraphrasing for diversity (v0.1.8)
- ✅ Agent task planning with dependencies (v0.1.7)
- ✅ Background shell execution (v0.1.7)
- ✅ Preemption coordination (v0.1.7)
- ✅ Multi-turn conversations with persistent memory
- ✅ Multimodal understanding (images, audio, video, PDFs)
- ✅ Custom Python tools integration
- ✅ MCP (Model Context Protocol) integration
- ✅ External framework adapters (AG2)
- ✅ Universal code execution across all backends
- ✅ Planning mode for safe tool coordination
- ✅ Advanced filesystem operations with permissions
- ✅ Cross-workspace coordination
- ✅ Semantic fact extraction and retrieval

### Collaboration Patterns
- ✅ Multi-agent consensus building
- ✅ Voting and refinement cycles
- ✅ Representative agent selection
- ✅ Diverse reasoning capacities
- ✅ Cross-verification and validation
- ✅ Iterative improvement workflows

### Real-World Applications
- ✅ Research and analysis
- ✅ Code development and testing
- ✅ Content creation and documentation
- ✅ Market analysis and feature prioritization
- ✅ Self-evolution and meta-analysis (v0.1.8)
- ✅ Multi-turn conversation continuation (v0.1.9)
- ✅ Browser and desktop automation (v0.1.9)
- ✅ External system integration (Discord, Notion, GitHub)
- 🔄 Web UI design and competitive development
- 🔄 Educational content generation (interactive courses)
- 📋 Web browsing and automation
- 📋 Document processing at scale
- 📋 Video creation and editing
- 📋 Academic paper reviewing

## Development Workflow

### Case Study Creation Process

1. **Issues First**: Submit a GitHub issue for case studies, add label `case study`
   - Use template: https://github.com/Leezekun/MassGen/blob/main/docs/case_studies/case-study-template.md

2. **Planning Phase**:
   - Write prompt
   - Define config file (agents, hyperparameters)
   - Specify command
   - Document current vs. expected behavior
   - Explain how it ties to self-improvement goals

3. **Development Phase**:
   - Feature created by dev team
   - Iterate with development team
   - Test early to address issues revealed by case study

4. **Evaluation Phase**:
   - Improve the prompt (ideally in same domain as planning)
   - Run prompt with provided cmd and config
   - Record video demonstration
   - Write report using Claude Code
   - Push to GitHub repo by release

### Release Schedule

**Goal**: Have case study planned the day after releasing previous feature

- Release n-1 feature: Morning
- Plan case study for feature n: Night sync (Tuesday, Thursday, Monday)

### Community Contributions

We want this to be a community document:
- Submit your own case studies
- Share interesting use cases
- Contribute to backlog of goals

## How to Use This Document

1. **Browse by Category**: Find case studies relevant to your use case
   - **Release Features**: Production-ready capabilities (19 completed)
   - **In Development**: Active development with PRs/testing (5 case studies)
   - **Planned**: Future roadmap items (7 in backlog)

2. **Check Status Icons**:
   - ✅ **Ready**: Complete with documentation and session logs
   - ✅ **Completed**: Executed successfully, documentation in progress
   - 📝 **Planning**: Design complete, ready for execution
   - 🧪 **In Testing**: Active testing and iteration
   - ⏸️ **Blocked**: Waiting on external dependencies
   - 📋 **Planned**: In backlog, not yet started

3. **Watch Videos**: Click video links (🎥) to see live demonstrations

4. **Read Documentation**: Click "📄 Case Study" links for detailed technical documentation

5. **Track Progress**: Use GitHub issues and PRs to follow development

6. **Create Your Own**: Use the template to contribute your own case studies

## Technical Requirements by Case Study Type

### Completed Features
- Session management with restoration (v0.1.9) ✅
- Computer use automation tools (v0.1.9) ✅
- Fuzzy model matching (v0.1.9) ✅
- Automation mode for LLM agents (v0.1.8) ✅
- DSPy question paraphrasing (v0.1.8) ✅
- Agent task planning (v0.1.7) ✅
- Background shell execution (v0.1.7) ✅
- Multi-turn conversations with persistent memory ✅
- Multimodal understanding (images, audio, video, PDFs) ✅
- Custom Python tools integration ✅
- MCP integration ✅
- Universal code execution ✅

### In Development
- Web UI competitive development ✅
- Sequential agent pipelines (course generation) 📝
- Large codebase analysis with memory 🧪

### Planned Requirements
- Advanced video understanding and editing 📋
- Map-reduce document processing 📋
- User-defined voting criteria 📋
- Scalable multi-agent backends 📋
- LangGraph & SmoLAgent streaming (v0.1.10 in progress) 🔄

## Long-Term Vision

**Website Creation from Scratch**
- Goal: Produce websites better than existing tools (e.g., Manus.im)
- Requirements: Playwright/Computer Use, image understanding, filesystem memory, multi-turn memory
- Timeline: After Computer Use integration complete

**MassGen Video Recording and Editing**
- Goal: Auto-generate case study videos (1-min demos with editing)
- Requirements: Video understanding, cmd execution, video editing MCP, planning mode
- Timeline: Could start soon, needs efficient handling of >10min videos

**Paper Reviewing**
- Goal: Compete with tools like Refine.ink for detailed paper feedback
- Requirements: Multi-agent review, quality assessment, research knowledge
- Timeline: Research-focused development phase

**Interactive Course Generation**
- Goal: Transform PDFs/textbooks into interactive courses automatically
- Requirements: 5-agent pipeline, component generation, quality review
- Status: Planning complete, ready for execution

## Contributing

We welcome community contributions! To create your own case study:

1. **Submit GitHub Issue**: Use the `case study` label
   - Template: https://github.com/Leezekun/MassGen/blob/main/docs/case_studies/case-study-template.md

2. **Planning Phase**:
   - Define prompt and expected behavior
   - Create config file
   - Explain connection to self-improvement goals

3. **Run MassGen**: Save session logs and outputs

4. **Record Demo**: Use OBS Studio or similar tools

5. **Write Documentation**: Follow the [case study template](docs/source/examples/case_studies/case-study-template.md)

6. **Submit PR**: Include case study doc and video (Claude Code can help)

See the [Contributing Guidelines](CONTRIBUTING.md) for submission instructions.

## TODO & Improvements

- [ ] Make it easier to share MassGen sessions online
- [ ] Auto-logging for users who opt in (currently just contributors)
- [ ] Better community organization for user-submitted case studies
- [ ] Automated case study video generation pipeline
- [ ] Case study quality metrics and benchmarking

## Resources

- **Documentation**: [https://docs.massgen.ai](https://docs.massgen.ai)
- **Case Studies Online**: [https://docs.massgen.ai/en/latest/examples/case_studies.html](https://docs.massgen.ai/en/latest/examples/case_studies.html)
- **GitHub Repository**: [https://github.com/Leezekun/MassGen](https://github.com/Leezekun/MassGen)
- **Website**: [https://massgen.ai](https://massgen.ai)
- **Case Studies Portal**: [https://case.massgen.ai](https://case.massgen.ai)

## Version History

This summary covers case studies from **MassGen v0.0.3** (initial release) through **v0.1.9** (latest), demonstrating the framework's evolution and expanding capabilities over time.

### Recent Releases (Post v0.1.5)

**v0.1.9 (November 7, 2025)** - Session Management & Computer Use Tools
- Complete session state tracking and restoration for multi-turn conversations
- Computer use automation tools (Claude, Gemini, OpenAI) for browser and desktop control
- Enhanced config builder with fuzzy model matching
- Expanded backend support (Cerebras, Together, Fireworks, Groq, OpenRouter, Moonshot)

**v0.1.8 (November 5, 2025)** - Automation Mode & DSPy Integration
- Automation infrastructure with `--automation` flag for LLM agents
- Real-time `status.json` monitoring for programmatic workflows
- DSPy-powered question paraphrasing for multi-agent diversity
- Meta-coordination capabilities (MassGen running MassGen)

**v0.1.7 (November 3, 2025)** - Agent Task Planning & Background Execution
- MCP-based task management with dependency tracking
- Background shell execution for long-running commands
- Preemption coordination for multi-agent workflows

**v0.1.6 (November 1, 2025)** - Additional improvements and bug fixes

## Detailed Case Study Notes

### Web UI Development - Collaborative Design
- **Status**: ✅ Completed October 25, 2025
- **Duration**: 12 minutes, 25 seconds
- **Session**: `log_20251025_222849`
- **Agents**: GPT-5 (architecture), Claude 3.5 Haiku (technical), Gemini 2.5 Flash (visual)
- **Outcome**: Gemini won with unanimous 3/3 votes, 97KB production-ready code
- **Key Achievement**: Zero bugs, zero post-processing, professional dashboard in <15 minutes
- **Draft PR**: https://github.com/Leezekun/MassGen/pull/375

### Interactive Course Generator
- **Status**: 📝 Planning Complete, Ready for Execution
- **Pipeline**: 5-agent sequential (parser → structurer → builder → reviewer → publisher)
- **Expected Duration**: ~30 minutes from PDF to course
- **Components**: Q&A, drag-and-match, flowcharts, info bubbles, code examples
- **Quick Reference**: `docs/case_studies/interactive-course-generator-QUICKREF.md`

### Codebase Architecture Analysis
- **Status**: 🧪 In Testing
- **Target**: FastAPI repository analysis
- **Goal**: Read 30+ files, create comprehensive architecture documentation
- **Config**: `tools/memory/gpt5mini_gemini_codebase_analysis_memory.yaml`
- **Command**: Clone FastAPI, analyze components, interactions, design patterns, request flows

### Revert Feature After Final Agent Failure
- **Status**: ⏸️ Blocked
- **Issue**: https://github.com/Leezekun/MassGen/issues/325
- **Goal**: Automated rollback when final agent execution fails
- **Use Case**: Safe multi-agent operations with failure recovery

### Twitter Integration
- **Status**: ⏸️ Blocked by Twitter API rate limits
- **Goal**: Multi-agent Twitter posting and engagement
- **Will Revisit**: After API access issues resolved

### Web Agent Browsing
- **Status**: 📋 Planned
- **Goal**: Compete on Online Mind2Web Leaderboard
- **Requirements**: Gemini 2.5 Computer Use, OpenAI Operator support
- **Use Case**: Autonomous web navigation and interaction
- **Target**: https://huggingface.co/spaces/osunlp/Online_Mind2Web_Leaderboard

### Map-Reduce Document Processing
- **Status**: 📋 Planned
- **Goal**: Information-to-attention prediction for busy managers
- **Applications**:
  - Meeting notes prioritization
  - Conference paper selection (100+ papers)
  - Stock news analysis for traders
  - Email triage (top 10 important from past 10 days)
- **Requirements**:
  - Separate document processing per agent
  - Scalable multi-agent backend
  - User-defined voting criteria
- **Key Innovation**: Vote on which document requires attention, not which answer is better

### Website Creation from Scratch
- **Status**: 📋 Planned
- **Goal**: Produce websites better than Manus.im
- **Example**: https://manus.im/share/lFvPbN1H9dtI1zXIbuYAiF?replay=1
- **Technical Requirements**:
  - Playwright/Computer Use for browser automation
  - Image understanding (v0.1.3) for visual design
  - Filesystem memory to reduce re-reading
  - Multi-turn memory for follow-up queries
  - OpenAI Operator and Gemini 2.5 Computer Use

### MassGen Video Recording and Editing
- **Status**: 📋 Planned (could start soon)
- **Goal**: Auto-generate 1-min case study videos
- **Workflow**:
  1. Run command with full args
  2. Record entire session
  3. Edit: speed up, add captions, highlight logs
  4. Cut unnecessary parts
  5. Produce final demo video
- **Technical Requirements**:
  - Video understanding (v0.1.3+)
  - Command execution (v0.0.31)
  - Video editing MCP (need to find existing tool)
- **Challenge**: Handle >10min command execution + video watching/editing time
- **Approach**: May need planning mode, coordination power of MassGen

### Paper Reviewing
- **Status**: 📋 Planned
- **Goal**: Compete with Refine.ink for detailed paper feedback
- **Target**: https://www.refine.ink/
- **Requirements**: Multi-agent review, academic quality assessment
- **Use Case**: Provide constructive, thorough academic paper reviews

---

## Additional Resources

### Computer Use Tools (v0.1.9)
- **Comprehensive Guide**: [Computer Use Tools Guide](massgen/backend/docs/COMPUTER_USE_TOOLS_GUIDE.md)
- **Setup Instructions**: [Docker Setup for Computer Use](scripts/computer_use_setup.md)
- **Supported Tools**:
  - Claude Computer Use (Anthropic computer-use-2025-01-24 API)
  - Gemini Computer Use (Google gemini-2.5-computer-use-preview)
  - OpenAI Computer Use (computer-use-preview model)
  - General Browser Automation tool

### Automation Mode (v0.1.8)
- **LLM Agent Guide**: [AI Usage Guide](AI_USAGE.md)
- **Automation Documentation**: [Automation User Guide](docs/source/user_guide/automation.rst)
- **Status File Reference**: [status.json Schema](docs/source/reference/status_file.rst)
- **DSPy Integration**: [DSPy Implementation Guide](massgen/backend/docs/DSPY_IMPLEMENTATION_GUIDE.md)

### Diversity System (v0.1.8)
- **Diversity Documentation**: [Diversity User Guide](docs/source/user_guide/diversity.rst)
- Covers answer novelty requirements and DSPy question paraphrasing

---

*Last Updated: November 9, 2025*
