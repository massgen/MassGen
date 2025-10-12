# MassGen Features

This directory contains comprehensive documentation for all MassGen features. Each document provides detailed explanations, configuration examples, and use cases drawn from the 98+ real configurations available in the project.

## Quick Navigation

### Essential Features

| Feature | Description | Status |
|---------|-------------|--------|
| [Configuration Guide](./configuration-guide.md) | Understanding and finding the right config from 98 options | ✅ Complete |
| [MCP Integration](./mcp-integration.md) | Model Context Protocol servers and tools | ✅ Complete |
| [Planning Mode](./planning-mode.md) | Coordinate before executing irreversible actions | ✅ Complete |
| [Backend Support](./backend-support.md) | All supported backends (OpenAI, Claude, Gemini, Grok, etc.) | ✅ Complete |
| [Filesystem Tools](./filesystem-tools.md) | File operations, workspaces, and safety features | ✅ Complete |
| [Multi-Agent Coordination](./multi-agent-coordination.md) | How agents collaborate and reach consensus | ✅ Complete |

### Advanced Features

| Feature | Description | Status |
|---------|-------------|--------|
| [AG2 Integration](./ag2-integration.md) | AG2 framework integration | ✅ Complete |
| [Multimodal Capabilities](./multimodal-capabilities.md) | Image generation and understanding | 📝 Coming Soon |
| [Advanced Features](./advanced-features.md) | Cost tracking, terminal displays, context management | 📝 Coming Soon |

## Feature Documentation Overview

### [Configuration Guide](./configuration-guide.md)
**Start here if you're new to MassGen configurations.**

Learn how to:
- Understand config file structure (single vs multi-agent)
- Navigate the 98 available configurations
- Find the right config for your use case
- Customize configs for your needs
- Use environment variables
- Troubleshoot configuration issues

**Key Topics:**
- Directory structure
- Finding configs by use case, backend, or feature
- Common customizations
- Best practices

### [MCP Integration](./mcp-integration.md)
**Connect agents to external tools and services.**

Comprehensive guide to Model Context Protocol in MassGen:
- What MCP is and how it works
- Setting up MCP servers (Discord, Notion, Twitter, Weather, etc.)
- Tool filtering and access control
- Multiple MCP servers
- Backend-specific configuration
- 26+ working examples

**Available MCP Servers:**
- Discord - Team communication
- Notion - Knowledge management
- Twitter - Social media
- Filesystem - File operations (Gemini native)
- Weather - Weather information
- Travel - Travel planning

### [Planning Mode](./planning-mode.md)
**Prevent duplicate actions during multi-agent coordination.**

Introduced in v0.0.29, Planning Mode enables:
- Separation of planning and execution phases
- Prevention of duplicate MCP tool calls
- Collaborative planning before action
- Support across all backends

**Use Cases:**
- Social media posts (Discord, Twitter)
- Database operations (Notion)
- File operations (Filesystem)
- Any irreversible MCP actions

**Includes:** 5 complete example configurations

### [Backend Support](./backend-support.md)
**Choose the right AI model for your task.**

Comprehensive guide to all supported backends and models:
- OpenAI (GPT-4o, GPT-5 series, o4-mini)
- Claude (Sonnet 4, Haiku, Opus)
- Claude Code (filesystem tools)
- Gemini (2.5 Flash, 2.5 Pro)
- Grok (Grok-3, Grok-4)
- Azure OpenAI (enterprise)
- AG2 framework (code execution)
- Local models (LM Studio, vLLM, SGLang)

**Key Topics:**
- Feature comparison table
- Model capabilities (web search, code execution, filesystem)
- Configuration examples
- Multi-backend mixing
- Choosing the right backend for your use case

### [Filesystem Tools](./filesystem-tools.md)
**Safe and powerful file operations for multi-agent collaboration.**

Comprehensive filesystem capabilities with built-in safety:
- Workspace isolation (per-agent directories)
- Context paths (controlled file access)
- Protected paths (read-only files)
- File operation tracker (read-before-delete)
- Permission system (fine-grained control)
- Multi-turn sessions (persistent state)

**Safety Features:**
- Read-before-delete enforcement (v0.0.29)
- Agent workspace isolation
- Protected file mechanisms
- Permission hierarchy

**Key Topics:**
- Claude Code native filesystem tools
- Gemini native filesystem MCP
- Context paths and permissions
- Deletion tools and workspace cleanup
- Multi-turn session persistence

### [Multi-Agent Coordination](./multi-agent-coordination.md)
**Leverage collective intelligence through agent collaboration.**

How multiple agents work together:
- Parallel processing
- Real-time collaboration and observation
- Voting and consensus building
- Convergence detection
- Model mixing strategies

**Agent Configurations:**
- 2 agents - Simple collaboration
- 3 agents - Balanced (recommended)
- 5 agents - Maximum diversity

**Key Topics:**
- When to use multiple vs single agents
- Homogeneous vs heterogeneous teams
- Specialized role assignment
- Live visualization
- Interactive multi-turn mode

### [AG2 Integration](./ag2-integration.md)
**Integrate AG2 agents with code execution capabilities.**

Introduced in v0.0.28, AG2 Integration enables:
- External framework agent integration
- Python code execution with multiple executor types
- Multi-framework agent collaboration
- Seamless mixing of AG2 and native MassGen agents

**Code Execution Capabilities:**
- LocalCommandLineCodeExecutor - Fast local execution
- DockerCommandLineCodeExecutor - Isolated containers
- JupyterCodeExecutor - Notebook integration
- YepCodeCodeExecutor - Cloud execution

**Use Cases:**
- Data analysis and visualization
- Algorithm implementation and testing
- Web scraping and processing
- Multi-framework collaboration

**Includes:** 4 complete example configurations

## Getting Started

### New to MassGen?

1. **Read**: [Configuration Guide](./configuration-guide.md) - Understand config structure
2. **Try**: Start with a basic config like [`single_agent.yaml`](../../massgen/configs/basic/single/single_agent.yaml)
3. **Explore**: Browse configs by use case in the Configuration Guide

### Want to Use External Tools?

1. **Read**: [MCP Integration](./mcp-integration.md) - Learn about MCP servers
2. **Choose**: Pick an MCP server (Discord, Notion, etc.)
3. **Configure**: Follow the setup guide for your chosen server
4. **Run**: Use one of the 26+ MCP example configs

### Building Multi-Agent Systems?

1. **Read**: [Planning Mode](./planning-mode.md) - Prevent duplicate actions
2. **Choose**: Multi-agent config (2, 3, or 5 agents)
3. **Enable**: Add planning mode to your orchestrator config
4. **Test**: Try with a planning mode example config

## Configuration Counts by Category

| Category | Count | Location |
|----------|-------|----------|
| Basic Configurations | 20 | [`massgen/configs/basic/`](../../massgen/configs/basic/) |
| Provider-Specific | 15 | [`massgen/configs/providers/`](../../massgen/configs/providers/) |
| MCP Tools | 26 | [`massgen/configs/tools/mcp/`](../../massgen/configs/tools/mcp/) |
| Planning Mode | 5 | [`massgen/configs/tools/planning/`](../../massgen/configs/tools/planning/) |
| Filesystem | 12 | [`massgen/configs/tools/filesystem/`](../../massgen/configs/tools/filesystem/) |
| Web Search | 7 | [`massgen/configs/tools/web-search/`](../../massgen/configs/tools/web-search/) |
| Teams | 5 | [`massgen/configs/teams/`](../../massgen/configs/teams/) |
| AG2 Framework | 4 | [`massgen/configs/ag2/`](../../massgen/configs/ag2/) |
| Debug | 2 | [`massgen/configs/debug/`](../../massgen/configs/debug/) |
| **Total** | **98** | All configs |

## Feature Index

### By Use Case

**Code Generation & Execution**
- [Configuration Guide](./configuration-guide.md#code-generation--execution)
- [Filesystem Tools](./filesystem-tools.md) - File operations and workspaces
- [Backend Support](./backend-support.md#for-code-generation) - AG2, Claude Code
- [AG2 Integration](./ag2-integration.md) - Code execution with AG2 framework

**Research & Analysis**
- [Configuration Guide](./configuration-guide.md#research--analysis)
- [Backend Support](./backend-support.md#for-research--analysis) - Web search capabilities

**Content Creation**
- [Multimodal Capabilities](./multimodal-capabilities.md) - Image generation (Coming Soon)
- [Configuration Guide](./configuration-guide.md#content-creation)

**Social Media & Communication**
- [MCP Integration](./mcp-integration.md#discord-integration)
- [Planning Mode](./planning-mode.md#social-media-management)

### By Backend

**OpenAI / GPT Models**
- [Backend Support](./backend-support.md#openai--gpt-models) - Full guide
- [Configuration Guide](./configuration-guide.md#openai--gpt-models) - Quick reference

**Claude Models**
- [Backend Support](./backend-support.md#claude-models) - Full guide
- [Filesystem Tools](./filesystem-tools.md#claude-code) - Claude Code native tools

**Gemini Models**
- [Backend Support](./backend-support.md#gemini-models) - Full guide
- [MCP Integration](./mcp-integration.md#filesystem-operations-gemini) - Native filesystem MCP

**Grok Models**
- [Backend Support](./backend-support.md#grok-models) - Full guide
- [Configuration Guide](./configuration-guide.md#grok-models) - Quick reference

**Local Models**
- [Backend Support](./backend-support.md#local-models) - Full guide (LM Studio, vLLM, SGLang)

### By Feature Category

**Tools & Integration**
- [MCP Integration](./mcp-integration.md) - External tool integration
- [Filesystem Tools](./filesystem-tools.md) - File operations and safety
- [AG2 Integration](./ag2-integration.md) - AG2 framework integration

**Safety & Security**
- [Filesystem Tools](./filesystem-tools.md#file-operation-tracker-v0029) - Read-before-delete, permissions
- [Filesystem Tools](./filesystem-tools.md#protected-paths) - Protected file paths
- [Filesystem Tools](./filesystem-tools.md) - Workspace isolation and context paths

**Coordination & Orchestration**
- [Multi-Agent Coordination](./multi-agent-coordination.md) - How agents collaborate
- [Planning Mode](./planning-mode.md) - Safe coordination with external tools

**Multimodal & Advanced**
- [Multimodal Capabilities](./multimodal-capabilities.md) - Images and more (Coming Soon)
- [Advanced Features](./advanced-features.md) - Cost tracking, etc. (Coming Soon)

## Recent Updates

### v0.0.29 (October 2025)
- ✨ [Planning Mode](./planning-mode.md) - New coordination strategy
- 🔒 File Operation Tracker - Read-before-delete enforcement
- 🎨 Enhanced MCP Tool Filtering
- 📝 5 new planning mode configurations

See [Release Notes](../releases/v0.0.29/release-notes.md) for full details.

### v0.0.28 (October 2025)
- 🤖 [AG2 Integration](./ag2-integration.md) - AG2 framework support
- 💻 Code execution with multiple executor types
- 🔧 External agent adapter architecture
- 📝 4 new AG2 configurations

See [Release Notes](../releases/v0.0.28/release-notes.md) for full details.

## Documentation Principles

All feature documentation follows these principles:

1. **Grounded in Reality** - Every example is from actual working configs
2. **Runnable Examples** - All code samples can be run as-is
3. **Use-Case Focused** - Organized by what you want to achieve
4. **No Duplication** - Links to related docs instead of copying content
5. **Living Documentation** - Updated with each release

## Contributing

Found an issue or want to improve documentation?

1. Check existing docs for accuracy
2. Test examples with real configs
3. Open an issue or PR on GitHub
4. Follow the documentation template style

## Additional Resources

- **Release Notes**: [`docs/releases/`](../releases/) - Version-specific features
- **Case Studies**: Real-world usage examples
- **API Documentation**: [`docs/source/api/`](../source/api/) - Code reference
- **User Guide**: [`docs/source/user_guide/`](../source/user_guide/) - General guides

## Need Help?

- **Configuration Issues**: Start with [Configuration Guide](./configuration-guide.md)
- **MCP Setup**: Check [MCP Integration](./mcp-integration.md)
- **Multi-Agent Problems**: See [Planning Mode](./planning-mode.md)
- **General Questions**: Visit project README or open an issue

---

**Last Updated**: October 2025 | **MassGen Version**: v0.0.29+
