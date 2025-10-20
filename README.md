<p align="center">
  <img src="https://raw.githubusercontent.com/Leezekun/MassGen/main/assets/logo.png" alt="MassGen Logo" width="360" />
</p>

<p align="center">
  <a href="https://www.python.org/downloads/">
    <img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+" style="margin-right: 5px;">
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="License" style="margin-right: 5px;">
  </a>
  <a href="https://docs.massgen.io">
    <img src="https://img.shields.io/badge/docs-massgen.ai-blue.svg" alt="Documentation" style="margin-right: 5px;">
  </a>
  <a href="https://discord.massgen.ai">
    <img src="https://img.shields.io/discord/1153072414184452236?color=7289da&label=chat&logo=discord&style=flat-square" alt="Join our Discord">
  </a>
</p>

<h1 align="center">🚀 MassGen: Multi-Agent Scaling System for GenAI</h1>

<p align="center">
  <i>MassGen is a cutting-edge multi-agent system that leverages the power of collaborative AI to solve complex tasks.</i>
</p>

<p align="center">
  <a href="https://www.youtube.com/watch?v=Dp2oldJJImw">
    <img src="https://raw.githubusercontent.com/Leezekun/MassGen/main/assets/massgen-demo.gif" alt="MassGen case study -- Berkeley Agentic AI Summit Question" width="800">
  </a>
</p>

<p align="center">
  <i>Multi-agent scaling through intelligent collaboration in Grok Heavy style</i>
</p>

MassGen is a cutting-edge multi-agent system that leverages the power of collaborative AI to solve complex tasks. It assigns a task to multiple AI agents who work in parallel, observe each other's progress, and refine their approaches to converge on the best solution to deliver a comprehensive and high-quality result. The power of this "parallel study group" approach is exemplified by advanced systems like xAI's Grok Heavy and Google DeepMind's Gemini Deep Think.

This project started with the "threads of thought" and "iterative refinement" ideas presented in [The Myth of Reasoning](https://docs.ag2.ai/latest/docs/blog/2025/04/16/Reasoning/), and extends the classic "multi-agent conversation" idea in [AG2](https://github.com/ag2ai/ag2). Here is a [video recording](https://www.youtube.com/watch?v=xM2Uguw1UsQ) of the background context introduction presented at the Berkeley Agentic AI Summit 2025.

---

## 📋 Table of Contents

<details open>
<summary><h3>✨ Key Features</h3></summary>

- [Cross-Model/Agent Synergy](#-key-features-1)
- [Parallel Processing](#-key-features-1)
- [Intelligence Sharing](#-key-features-1)
- [Consensus Building](#-key-features-1)
- [Live Visualization](#-key-features-1)
</details>

<details open>
<summary><h3>🆕 Latest Features</h3></summary>

- [v0.1.0 Features](#-latest-features-v010)
</details>

<details open>
<summary><h3>🏗️ System Design</h3></summary>

- [System Architecture](#%EF%B8%8F-system-design-1)
- [Parallel Processing](#%EF%B8%8F-system-design-1)
- [Real-time Collaboration](#%EF%B8%8F-system-design-1)
- [Convergence Detection](#%EF%B8%8F-system-design-1)
- [Adaptive Coordination](#%EF%B8%8F-system-design-1)
</details>

<details open>
<summary><h3>🚀 Quick Start</h3></summary>

- [📥 Installation](#1--installation)
- [🔐 API Configuration](#2--api-configuration)
- [🧩 Supported Models and Tools](#3--supported-models-and-tools)
  - [Models](#models)
  - [Tools](#tools)
- [🏃 Run MassGen](#4--run-massgen)
  - [CLI Configuration Parameters](#cli-configuration-parameters)
  - [1. Single Agent (Easiest Start)](#1-single-agent-easiest-start)
  - [2. Multi-Agent Collaboration (Recommended)](#2-multi-agent-collaboration-recommended)
  - [3. Model Context Protocol (MCP)](#3-model-context-protocol-mcp)
  - [4. File System Operations](#4-file-system-operations--workspace-management)
  - [5. Project Integration (NEW in v0.0.21)](#5-project-integration--user-context-paths-new-in-v0021)
  - [Backend Configuration Reference](#backend-configuration-reference)
  - [Interactive Multi-Turn Mode](#interactive-multi-turn-mode)
- [📊 View Results](#5--view-results)
  - [Real-time Display](#real-time-display)
  - [Comprehensive Logging](#comprehensive-logging)
</details>

<details open>
<summary><h3>💡 Case Studies & Examples</h3></summary>

- [Case Studies](#-case-studies)
</details>

<details open>
<summary><h3>🗺️ Roadmap</h3></summary>

- Recent Achievements
  - [v0.1.0](#recent-achievements-v010)
  - [v0.0.3 - v0.0.32](#previous-achievements-v003---v0032)
- [Key Future Enhancements](#key-future-enhancements)
  - Bug Fixes & Backend Improvements
  - Advanced Agent Collaboration
  - Expanded Model, Tool & Agent Integrations
  - Improved Performance & Scalability
  - Enhanced Developer Experience
- [v0.1.1 Roadmap](#v011-roadmap)
</details>

<details open>
<summary><h3>📚 Additional Resources</h3></summary>

- [🤝 Contributing](#-contributing)
- [📄 License](#-license)
- [⭐ Star History](#-star-history)
</details>

---

## ✨ Key Features

| Feature | Description |
|---------|-------------|
| **🤝 Cross-Model/Agent Synergy** | Harness strengths from diverse frontier model-powered agents |
| **⚡ Parallel Processing** | Multiple agents tackle problems simultaneously |
| **👥 Intelligence Sharing** | Agents share and learn from each other's work |
| **🔄 Consensus Building** | Natural convergence through collaborative refinement |
| **📊 Live Visualization** | See agents' working processes in real-time |

---

## 🆕 Latest Features (v0.1.0)

**🎉 Released: October 17, 2025**

**What's New in v0.1.0:**
- **📦 PyPI Package** - Official pip installation: `pip install massgen`
- **📖 Comprehensive Documentation** - Full Sphinx docs at [MassGen Official Documentation](https://docs.massgen.io/)
- **🎯 Interactive Setup Wizard** - Guided configuration for first-time users
- **🚀 Simplified Commands** - Clean `massgen` CLI with `@examples/` prefix for built-in configs

**Get Started with v0.1.0:**
```bash
# Install from PyPI
pip install massgen

# Run the interactive setup wizard
massgen

# Start using with example configurations
massgen --config @examples/basic/multi/three_agents_default \
  "Analyze the pros and cons of renewable energy"
```

→ [See full release history and examples](massgen/configs/README.md#release-history--examples)

---

## 🏗️ System Design

MassGen operates through an architecture designed for **seamless multi-agent collaboration**:

```mermaid
graph TB
    O[🚀 MassGen Orchestrator<br/>📋 Task Distribution & Coordination]

    subgraph Collaborative Agents
        A1[Agent 1<br/>🏗️ Anthropic/Claude + Tools]
        A2[Agent 2<br/>🌟 Google/Gemini + Tools]
        A3[Agent 3<br/>🤖 OpenAI/GPT + Tools]
        A4[Agent 4<br/>⚡ xAI/Grok + Tools]
    end

    H[🔄 Shared Collaboration Hub<br/>📡 Real-time Notification & Consensus]

    O --> A1 & A2 & A3 & A4
    A1 & A2 & A3 & A4 <--> H

    classDef orchestrator fill:#e1f5fe,stroke:#0288d1,stroke-width:3px
    classDef agent fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px
    classDef hub fill:#e8f5e8,stroke:#388e3c,stroke-width:2px

    class O orchestrator
    class A1,A2,A3,A4 agent
    class H hub
```

The system's workflow is defined by the following key principles:

**Parallel Processing** - Multiple agents tackle the same task simultaneously, each leveraging their unique capabilities (different models, tools, and specialized approaches).

**Real-time Collaboration** - Agents continuously share their working summaries and insights through a notification system, allowing them to learn from each other's approaches and build upon collective knowledge.

**Convergence Detection** - The system intelligently monitors when agents have reached stability in their solutions and achieved consensus through natural collaboration rather than forced agreement.

**Adaptive Coordination** - Agents can restart and refine their work when they receive new insights from others, creating a dynamic and responsive problem-solving environment.

This collaborative approach ensures that the final output leverages collective intelligence from multiple AI systems, leading to more robust and well-rounded results than any single agent could achieve alone.

---

> 📖 **Complete Documentation:** For comprehensive guides, API reference, and detailed examples, visit **[MassGen Official Documentation](https://docs.massgen.io/)**

---

## 🚀 Quick Start

### 1. 📥 Installation

**Method 1: PyPI Installation** (Recommended - Python 3.11+):

```bash
# Install MassGen via pip
pip install massgen

# Or with uv (faster)
uv pip install massgen

# Run the interactive setup wizard
massgen
```

The wizard will guide you through:
- Configuring API keys
- Selecting your use case (Research, Code, Q&A, etc.)
- Choosing AI models
- Saving your configuration

After setup, you can run MassGen with:
```bash
# Interactive mode
massgen

# Single query
massgen "Your question here"

# With example configurations
massgen --config @examples/basic/multi/three_agents_default "Your question"
```

→ See [Installation Guide](https://docs.massgen.io/en/latest/quickstart/installation.html) for complete setup instructions.

**Method 2: Development Installation** (for contributors):

```bash
# Clone the repository
git clone https://github.com/Leezekun/MassGen.git
cd MassGen

# Install in editable mode with pip
pip install -e .

# Or with uv (faster)
uv pip install -e .

# Optional: AG2 framework integration
pip install -e ".[external]"
```

<details>
<summary><b>Alternative Installation Methods</b> (click to expand)</summary>

**Using uv with venv:**
```bash
git clone https://github.com/Leezekun/MassGen.git
cd MassGen
uv venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
uv pip install -e .
```

**Using traditional Python venv:**
```bash
git clone https://github.com/Leezekun/MassGen.git
cd MassGen
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
```

**Global installation with uv tool:**
```bash
git clone https://github.com/Leezekun/MassGen.git
cd MassGen
uv tool install -e .
# Now run from any directory
uv tool run massgen --config @examples/basic/multi/three_agents_default "Question"
```

**Backwards compatibility (uv run):**
```bash
cd /path/to/MassGen
uv run massgen --config @examples/basic/multi/three_agents_default "Question"
uv run python -m massgen.cli --config config.yaml "Question"
```

</details>

**Optional CLI Tools:**
```bash
# Claude Code CLI - Advanced coding assistant
npm install -g @anthropic-ai/claude-code

# LM Studio - Local model inference
# MacOS/Linux:
sudo ~/.lmstudio/bin/lms bootstrap
# Windows:
cmd /c %USERPROFILE%\.lmstudio\bin\lms.exe bootstrap
```

### 2. 🔐 API Configuration

**Create a `.env` file in your working directory with your API keys:**

```bash
# Copy this template to .env and add your API keys
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
XAI_API_KEY=...

# Optional: Additional providers
CEREBRAS_API_KEY=...
TOGETHER_API_KEY=...
GROQ_API_KEY=...
OPENROUTER_API_KEY=...
```

MassGen automatically loads API keys from `.env` in your current directory.

→ **Complete setup guide with all providers:** See [API Key Configuration](https://docs.massgen.io/en/latest/quickstart/installation.html#api-key-configuration) in the docs

**Get API keys:**
 - [OpenAI](https://platform.openai.com/api-keys) | [Claude](https://docs.anthropic.com/en/api/overview) | [Gemini](https://ai.google.dev/gemini-api/docs) | [Grok](https://docs.x.ai/docs/overview)
 - [Azure OpenAI](https://learn.microsoft.com/en-us/azure/ai-services/openai/) | [Cerebras](https://inference-docs.cerebras.ai/introduction) | [More providers...](https://docs.massgen.io/en/latest/reference/supported_models.html)

### 3. 🧩 Supported Models and Tools

#### Models

The system currently supports multiple model providers with advanced capabilities:

**API-based Models:**
- **Azure OpenAI** (NEW in v0.0.10): GPT-4, GPT-4o, GPT-3.5-turbo, GPT-4.1, GPT-5-chat
- **Cerebras AI**: GPT-OSS-120B...
- **Claude**: Claude Haiku 3.5, Claude Sonnet 4, Claude Opus 4...
- **Claude Code**: Native Claude Code SDK with comprehensive dev tools
- **Gemini**: Gemini 2.5 Flash, Gemini 2.5 Pro...
- **Grok**: Grok-4, Grok-3, Grok-3-mini...
- **OpenAI**: GPT-5 series (GPT-5, GPT-5-mini, GPT-5-nano)...
- **Together AI**, **Fireworks AI**, **Groq**, **Kimi/Moonshot**, **Nebius AI Studio**, **OpenRouter**, **POE**: LLaMA, Mistral, Qwen...
- **Z AI**: GLM-4.5

**Local Model Support:**
- **vLLM & SGLang** (ENHANCED in v0.0.25): Unified inference backend supporting both vLLM and SGLang servers
  - Auto-detection between vLLM (port 8000) and SGLang (port 30000) servers
  - Support for both vLLM and SGLang-specific parameters (top_k, repetition_penalty, separate_reasoning)
  - Mixed server deployments with configuration example: `two_qwen_vllm_sglang.yaml`

- **LM Studio** (v0.0.7+): Run open-weight models locally with automatic server management
  - Automatic LM Studio CLI installation
  - Auto-download and loading of models
  - Zero-cost usage reporting
  - Support for LLaMA, Mistral, Qwen and other open-weight models

→ For complete model list and configuration details, see [Supported Models](https://docs.massgen.io/en/latest/reference/supported_models.html)

#### Tools

MassGen agents can leverage various tools to enhance their problem-solving capabilities. Both API-based and CLI-based backends support different tool capabilities.

**Supported Built-in Tools by Backend:**

| Backend | Live Search | Code Execution | File Operations | MCP Support | Multimodal (Image/Audio/Video) | Advanced Features |
|---------|:-----------:|:--------------:|:---------------:|:-----------:|:----------:|:-----------------|
| **Azure OpenAI** (NEW in v0.0.10) | ❌ | ❌ | ❌ | ❌ | ❌ | Code interpreter, Azure deployment management |
| **Claude API**  | ✅ | ✅ | ✅ | ✅ | ✅ | Web search, code interpreter, **MCP integration** |
| **Claude Code** | ✅ | ✅ | ✅ | ✅ | ✅<br/>*Image* | **Native Claude Code SDK, comprehensive dev tools, MCP integration** |
| **Gemini API** | ✅ | ✅ | ✅ | ✅ | ✅<br/>*Image* | Web search, code execution, **MCP integration**|
| **Grok API** | ✅ | ❌ | ✅ | ✅ | ❌ | Web search, **MCP integration** |
| **OpenAI API** | ✅ | ✅ | ✅ | ✅ | ✅<br/>*Image* | Web search, code interpreter, **MCP integration** |
| **ZAI API** | ❌ | ❌ | ✅ | ✅ | ❌ | **MCP integration** |

**Note:** Audio/video multimodal support (NEW in v0.0.30) is available through Chat Completions-based providers like OpenRouter and Qwen API. See configuration examples: [`single_openrouter_audio_understanding.yaml`](massgen/configs/basic/single/single_openrouter_audio_understanding.yaml), [`single_qwen_video_understanding.yaml`](massgen/configs/basic/single/single_qwen_video_understanding.yaml)

→ For detailed backend capabilities and tool integration guides, see [User Guide - Backends](https://docs.massgen.io/en/latest/user_guide/backends.html)

---

### 4. 🏃 Run MassGen

> **Complete Usage Guide:** For all usage modes, advanced features, and interactive multi-turn sessions, see [Running MassGen](https://docs.massgen.io/en/latest/quickstart/running-massgen.html)

#### 🚀 Getting Started

#### CLI Configuration Parameters

| Parameter          | Description |
|-------------------|-------------|
| `--config`         | Path to YAML configuration file with agent definitions, model parameters, backend parameters and UI settings |
| `--backend`        | Backend type for quick setup without a config file (`claude`, `claude_code`, `gemini`, `grok`, `openai`, `azure_openai`, `zai`). Optional for [models with default backends](massgen/utils.py).|
| `--model`          | Model name for quick setup (e.g., `gemini-2.5-flash`, `gpt-5-nano`, ...). `--config` and `--model` are mutually exclusive - use one or the other. |
| `--system-message` | System prompt for the agent in quick setup mode. If `--config` is provided, `--system-message` is omitted. |
| `--no-display`     | Disable real-time streaming UI coordination display (fallback to simple text output).|
| `--no-logs`        | Disable real-time logging.|
| `--debug`          | Enable debug mode with verbose logging (NEW in v0.0.13). Shows detailed orchestrator activities, agent messages, backend operations, and tool calls. Debug logs are saved to `agent_outputs/log_{time}/massgen_debug.log`. |
| `"<your question>"`         | Optional single-question input; if omitted, MassGen enters interactive chat mode. |


#### **1. Single Agent (Easiest Start)**

**Quick Start Commands:**
```bash
# Quick test with any supported model - no configuration needed
uv run python -m massgen.cli --model claude-3-5-sonnet-latest "What is machine learning?"
uv run python -m massgen.cli --model gemini-2.5-flash "Explain quantum computing"
uv run python -m massgen.cli --model gpt-5-nano "Summarize the latest AI developments"
```

**Configuration:**

Use the `agent` field to define a single agent with its backend and settings:

```yaml
agent:
  id: "<agent_name>"
  backend:
    type: "azure_openai" | "chatcompletion" | "claude" | "claude_code" | "gemini" | "grok" | "openai" | "zai" | "lmstudio" #Type of backend
    model: "<model_name>" # Model name
    api_key: "<optional_key>"  # API key for backend. Uses env vars by default.
  system_message: "..."    # System Message for Single Agent
```

→ [See all single agent configs](massgen/configs/basic/single/)


#### **2. Multi-Agent Collaboration (Recommended)**

**Configuration:**

Use the `agents` field to define multiple agents, each with its own backend and config:

**Quick Start Commands:**

```bash
# Three powerful agents working together - Gemini, GPT-5, and Grok
massgen --config @examples/basic/multi/three_agents_default \
  "Analyze the pros and cons of renewable energy"
```

**This showcases MassGen's core strength:**
- **Gemini 2.5 Flash** - Fast research with web search
- **GPT-5 Nano** - Advanced reasoning with code execution
- **Grok-3 Mini** - Real-time information and alternative perspectives

```yaml
agents:  # Multiple agents (alternative to 'agent')
  - id: "<agent1 name>"
    backend:
      type: "azure_openai" | "chatcompletion" | "claude" | "claude_code" | "gemini" | "grok" | "openai" |  "zai" | "lmstudio" #Type of backend
      model: "<model_name>" # Model name
      api_key: "<optional_key>"  # API key for backend. Uses env vars by default.
    system_message: "..."    # System Message for Single Agent
  - id: "..."
    backend:
      type: "..."
      model: "..."
      ...
    system_message: "..."
```

→ [Explore more multi-agent setups](massgen/configs/basic/multi/)


#### **3. Model context protocol (MCP)**

The [Model context protocol](https://modelcontextprotocol.io/) (MCP) standardises how applications expose tools and context to language models. From the official documentation:

>MCP is an open protocol that standardizes how applications provide context to LLMs. Think of MCP like a USB-C port for AI applications. Just as USB-C provides a standardized way to connect your devices to various peripherals and accessories, MCP provides a standardized way to connect AI models to different data sources and tools.

**MCP Configuration Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `mcp_servers` | dict | **Yes** (for MCP) | Container for MCP server definitions |
| └─ `type` | string | Yes | Transport: `"stdio"` or `"streamable-http"` |
| └─ `command` | string | stdio only | Command to run the MCP server |
| └─ `args` | list | stdio only | Arguments for the command |
| └─ `url` | string | http only | Server endpoint URL |
| └─ `env` | dict | No | Environment variables to pass |
| `allowed_tools` | list | No | Whitelist specific tools (if omitted, all tools available) |
| `exclude_tools` | list | No | Blacklist dangerous/unwanted tools |


**Quick Start Commands ([Check backend MCP support here](#tools)):**

```bash
# Weather service with GPT-5
massgen --config @examples/tools/mcp/gpt5_nano_mcp_example \
  "What's the weather forecast for New York this week?"

# Multi-tool MCP with Gemini - Search + Weather + Filesystem (Requires BRAVE_API_KEY in .env)
massgen --config @examples/tools/mcp/multimcp_gemini \
  "Find the best restaurants in Paris and save the recommendations to a file"
```

**Configuration:**

```yaml
agents:
  # Basic MCP Configuration:
  backend:
    type: "openai"              # Your backend choice
    model: "gpt-5-mini"         # Your model choice

    # Add MCP servers here
    mcp_servers:
      weather:                  # Server name (you choose this)
        type: "stdio"           # Communication type
        command: "npx"          # Command to run
        args: ["-y", "@modelcontextprotocol/server-weather"]  # MCP server package

  # That's it! The agent can now check weather.

  # Multiple MCP Tools Example:
  backend:
    type: "gemini"
    model: "gemini-2.5-flash"
    mcp_servers:
      # Web search
      search:
        type: "stdio"
        command: "npx"
        args: ["-y", "@modelcontextprotocol/server-brave-search"]
        env:
          BRAVE_API_KEY: "${BRAVE_API_KEY}"  # Set in .env file

      # HTTP-based MCP server (streamable-http transport)
      custodm_api:
        type: "streamable-http"   # For HTTP/SSE servers
        url: "http://localhost:8080/mcp/sse"  # Server endpoint


  # Tool configuration (MCP tools are auto-discovered)
  allowed_tools:                        # Optional: whitelist specific tools
    - "mcp__weather__get_current_weather"
    - "mcp__test_server__mcp_echo"
    - "mcp__test_server__add_numbers"

  exclude_tools:                        # Optional: blacklist specific tools
    - "mcp__test_server__current_time"
```

→ [View more MCP examples](massgen/configs/tools/mcp/)

→ For comprehensive MCP integration guide, see [MCP Integration](https://docs.massgen.io/en/latest/user_guide/mcp_integration.html)

#### **4. File System Operations & Workspace Management**

MassGen provides comprehensive file system support through multiple backends, enabling agents to read, write, and manipulate files in organized workspaces.


**Filesystem Configuration Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `cwd` | string | **Yes** (for file ops) | Working directory for file operations (agent-specific workspace) |
| `snapshot_storage` | string | Yes | Directory for workspace snapshots |
| `agent_temporary_workspace` | string | Yes | Parent directory for temporary workspaces |


**Quick Start Commands:**

```bash
# File operations with Claude Code
massgen --config @examples/tools/filesystem/claude_code_single \
  "Create a Python web scraper and save results to CSV"

# Multi-agent file collaboration
massgen --config @examples/tools/filesystem/claude_code_context_sharing \
  "Generate a comprehensive project report with charts and analysis"
```

**Configuration:**

```yaml
# Basic Workspace Setup:
agents:
  - id: "file-agent"
    backend:
      type: "claude_code"          # Backend with file support
      model: "claude-sonnet-4"     # Your model choice
      cwd: "workspace"             # Isolated workspace for file operations

# Multi-Agent Workspace Isolation:
agents:
  - id: "agent_a"
    backend:
      type: "claude_code"
      cwd: "workspace1"            # Agent-specific workspace

  - id: "agent_b"
    backend:
      type: "gemini"
      cwd: "workspace2"            # Separate workspace

orchestrator:
  snapshot_storage: "snapshots"              # Shared snapshots directory
  agent_temporary_workspace: "temp_workspaces" # Temporary workspace management
```
**Available File Operations:**
- **Claude Code**: Built-in tools (Read, Write, Edit, MultiEdit, Bash, Grep, Glob, LS, TodoWrite)
- **Other Backends**: Via [MCP Filesystem Server](https://github.com/modelcontextprotocol/servers/blob/main/src%2Ffilesystem%2FREADME.md)

**Workspace Management:**
- **Isolated Workspaces**: Each agent's `cwd` is fully isolated and writable
- **Snapshot Storage**: Share workspace context between Claude Code agents
- **Temporary Workspaces**: Agents can access previous coordination results

→ [View more filesystem examples](massgen/configs/tools/filesystem/)

> ⚠️ **IMPORTANT SAFETY WARNING**
>
> MassGen agents can **autonomously read, write, modify, and delete files** within their permitted directories.
>
> **Before running MassGen with filesystem access:**
> - Only grant access to directories you're comfortable with agents modifying
> - Use the permission system to restrict write access where needed
> - Consider testing in an isolated directory or virtual environment first
> - Back up important files before granting write access
> - Review the `context_paths` configuration carefully
>
> The agents will execute file operations without additional confirmation once permissions are granted.

→ For comprehensive file operations guide, see [File Operations](https://docs.massgen.io/en/latest/user_guide/file_operations.html)

#### **5. Project Integration & User Context Paths (NEW in v0.0.21)**

Work directly with your existing projects! User Context Paths allow you to share specific directories with all agents while maintaining granular permission control. This enables secure multi-agent collaboration on your real codebases, documentation, and data.

MassGen automatically organizes all its working files under a `.massgen/` directory in your project root, keeping your project clean and making it easy to exclude MassGen's temporary files from version control.

**Project Integration Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `context_paths` | list | **Yes** (for project integration) | Shared directories for all agents |
| └─ `path` | string | Yes | Absolute or relative path to your project directory (**must be directory, not file**) |
| └─ `permission` | string | Yes | Access level: `"read"` or `"write"` (write applies only to final agent) |
| └─ `protected_paths` | list | No | Files/directories immune from modification (relative to context path) |

**⚠️ Important Notes:**
- Context paths must point to **directories**, not individual files
- Paths can be **absolute** or **relative** (resolved against current working directory)
- **Write permissions** apply only to the **final agent** during presentation phase
- During coordination, all context paths are **read-only** to protect your files
- MassGen validates all paths during startup and will show clear error messages for missing paths or file paths


**Quick Start Commands:**

```bash
# Multi-agent collaboration to improve the website in `massgen/configs/resources/v0.0.21-example
massgen --config @examples/tools/filesystem/gpt5mini_cc_fs_context_path "Enhance the website with: 1) A dark/light theme toggle with smooth transitions, 2) An interactive feature that helps users engage with the blog content (your choice - could be search, filtering by topic, reading time estimates, social sharing, reactions, etc.), and 3) Visual polish with CSS animations or transitions that make the site feel more modern and responsive. Use vanilla JavaScript and be creative with the implementation details."
```

**Configuration:**

```yaml
# Basic Project Integration:
agents:
  - id: "code-reviewer"
    backend:
      type: "claude_code"
      cwd: "workspace"             # Agent's isolated work area

orchestrator:
  context_paths:
    - path: "."                    # Current directory (relative path)
      permission: "write"          # Final agent can create/modify files
      protected_paths:             # Optional: files immune from modification
        - ".env"
        - "config.json"
    - path: "/home/user/my-project/src"  # Absolute path example
      permission: "read"           # Agents can analyze your code

# Advanced: Multi-Agent Project Collaboration
agents:
  - id: "analyzer"
    backend:
      type: "gemini"
      cwd: "analysis_workspace"

  - id: "implementer"
    backend:
      type: "claude_code"
      cwd: "implementation_workspace"

orchestrator:
  context_paths:
    - path: "../legacy-app/src"   # Relative path to existing codebase
      permission: "read"           # Read existing codebase
    - path: "../legacy-app/tests"
      permission: "write"          # Final agent can write new tests
      protected_paths:             # Protect specific test files
        - "integration_tests/production_data_test.py"
    - path: "/home/user/modernized-app"  # Absolute path
      permission: "write"          # Final agent can create modernized version
```

**This showcases project integration:**
- **Real Project Access** - Work with your actual codebases, not copies
- **Secure Permissions** - Granular control over what agents can read/modify
- **Multi-Agent Collaboration** - Multiple agents safely work on the same project
- **Context Agents** (during coordination): Always READ-only access to protect your files
- **Final Agent** (final execution): Gets the configured permission (READ or write)

**Use Cases:**
- **Code Review**: Agents analyze your source code and suggest improvements
- **Documentation**: Agents read project docs to understand context and generate updates
- **Data Processing**: Agents access shared datasets and generate analysis reports
- **Project Migration**: Agents examine existing projects and create modernized versions

**Clean Project Organization:**
```
your-project/
├── .massgen/                          # All MassGen state
│   ├── sessions/                      # Multi-turn conversation history (if using interactively)
│   │   └── session_20240101_143022/
│   │       ├── turn_1/                # Results from turn 1
│   │       ├── turn_2/                # Results from turn 2
│   │       └── SESSION_SUMMARY.txt    # Human-readable summary
│   ├── workspaces/                    # Agent working directories
│   │   ├── agent1/                    # Individual agent workspaces
│   │   └── agent2/
│   ├── snapshots/                     # Workspace snapshots for coordination
│   └── temp_workspaces/               # Previous turn results for context
├── massgen/
└── ...
```

**Benefits:**
- ✅ **Clean Projects** - All MassGen files contained in one directory
- ✅ **Easy Gitignore** - Just add `.massgen/` to `.gitignore`
- ✅ **Portable** - Move or delete `.massgen/` without affecting your project
- ✅ **Multi-Turn Sessions** - Conversation history preserved across sessions

**Configuration Auto-Organization:**
```yaml
orchestrator:
  # User specifies simple names - MassGen organizes under .massgen/
  snapshot_storage: "snapshots"         # → .massgen/snapshots/
  session_storage: "sessions"           # → .massgen/sessions/
  agent_temporary_workspace: "temp"     # → .massgen/temp/

agents:
  - backend:
      cwd: "workspace1"                 # → .massgen/workspaces/workspace1/
```

→ [Learn more about project integration](massgen/mcp_tools/permissions_and_context_files.md)

→ For comprehensive project integration guide, see [Project Integration](https://docs.massgen.io/en/latest/user_guide/project_integration.html)

**Security Considerations:**
- **Agent ID Safety**: Avoid using agent+incremental digits for IDs (e.g., `agent1`, `agent2`). This may cause ID exposure during voting
- **File Access Control**: Restrict file access using MCP server configurations when needed
- **Path Validation**: All context paths are validated to ensure they exist and are directories (not files)
- **Directory-Only Context Paths**: Context paths must point to directories, not individual files

---

#### Additional Examples by Provider

**Claude (Recursive MCP Execution - v0.0.20+)**
```bash
# Claude with advanced tool chaining
massgen --config @examples/tools/mcp/claude_mcp_example \
  "Research and compare weather in Beijing and Shanghai"
```

**OpenAI (GPT-5 Series with MCP - v0.0.17+)**
```bash
# GPT-5 with weather and external tools
massgen --config @examples/tools/mcp/gpt5_nano_mcp_example \
  "What's the weather of Tokyo"
```

**Gemini (Multi-Server MCP - v0.0.15+)**
```bash
# Gemini with multiple MCP services
massgen --config @examples/tools/mcp/multimcp_gemini \
  "Find accommodations in Paris with neighborhood analysis"    # (requires BRAVE_API_KEY in .env)
```

**Claude Code (Development Tools)**
```bash
# Professional development environment with auto-configured workspace
uv run python -m massgen.cli \
  --backend claude_code \
  --model sonnet \
  "Create a Flask web app with authentication"

# Default workspace directories created automatically:
# - workspace1/              (working directory)
# - snapshots/              (workspace snapshots)
# - temp_workspaces/        (temporary agent workspaces)
```

**Local Models (LM Studio - v0.0.7+)**
```bash
# Run open-source models locally
massgen --config @examples/providers/local/lmstudio \
  "Explain machine learning concepts"
```

→ [Browse by provider](massgen/configs/providers/) | [Browse by tools](massgen/configs/tools/) | [Browse teams](massgen/configs/teams/)

#### Additional Use Case Examples

**Question Answering & Research:**
```bash
# Complex research with multiple perspectives
massgen --config @examples/basic/multi/gemini_4o_claude \
  "What's best to do in Stockholm in October 2025"

# Specific research requirements
massgen --config @examples/basic/multi/gemini_4o_claude \
  "Give me all the talks on agent frameworks in Berkeley Agentic AI Summit 2025"
```

**Creative Writing:**
```bash
# Story generation with multiple creative agents
massgen --config @examples/basic/multi/gemini_4o_claude \
  "Write a short story about a robot who discovers music"
```

**Development & Coding:**
```bash
# Full-stack development with file operations
massgen --config @examples/tools/filesystem/claude_code_single \
  "Create a Flask web app with authentication"
```

**Web Automation:** (still in test)
```bash
# Browser automation with screenshots and reporting
# Prerequisites: npm install @playwright/mcp@latest (for Playwright MCP server)
massgen --config @examples/tools/code-execution/multi_agent_playwright_automation \
  "Browse three issues in https://github.com/Leezekun/MassGen and suggest documentation improvements. Include screenshots and suggestions in a website."

# Data extraction and analysis
massgen --config @examples/tools/code-execution/multi_agent_playwright_automation \
  "Navigate to https://news.ycombinator.com, extract the top 10 stories, and create a summary report"
```

→ [**See detailed case studies**](docs/case_studies/README.md) with real session logs and outcomes

#### Interactive Mode & Advanced Usage

**Multi-Turn Conversations:**
```bash
# Start interactive chat (no initial question)
massgen --config @examples/basic/multi/three_agents_default

# Debug mode for troubleshooting
massgen --config @examples/basic/multi/three_agents_default \
  --debug "Your question"
```

## Configuration Files

MassGen configurations are organized by features and use cases. See the [Configuration Guide](massgen/configs/README.md) for detailed organization and examples.

**Quick navigation:**
- **Basic setups**: [Single agent](massgen/configs/basic/single/) | [Multi-agent](massgen/configs/basic/multi/)
- **Tool integrations**: [MCP servers](massgen/configs/tools/mcp/) | [Web search](massgen/configs/tools/web-search/) | [Filesystem](massgen/configs/tools/filesystem/)
- **Provider examples**: [OpenAI](massgen/configs/providers/openai/) | [Claude](massgen/configs/providers/claude/) | [Gemini](massgen/configs/providers/gemini/)
- **Specialized teams**: [Creative](massgen/configs/teams/creative/) | [Research](massgen/configs/teams/research/) | [Development](massgen/configs/teams/development/)

See MCP server setup guides: [Discord MCP](massgen/configs/docs/DISCORD_MCP_SETUP.md) | [Twitter MCP](massgen/configs/docs/TWITTER_MCP_ENESCINAR_SETUP.md)

#### Backend Configuration Reference

For detailed configuration of all supported backends (OpenAI, Claude, Gemini, Grok, etc.), see:

→ **[Backend Configuration Guide](massgen/configs/BACKEND_CONFIGURATION.md)**

#### Interactive Multi-Turn Mode

MassGen supports an interactive mode where you can have ongoing conversations with the system:

```bash
# Start interactive mode with a single agent (no tool enabled by default)
uv run python -m massgen.cli --model gpt-5-mini

# Start interactive mode with configuration file
uv run python -m massgen.cli \
  --config massgen/configs/basic/multi/three_agents_default.yaml
```

**Interactive Mode Features:**
- **Multi-turn conversations**: Multiple agents collaborate to chat with you in an ongoing conversation
- **Real-time coordination tracking**: Live visualization of agent interactions, votes, and decision-making processes
- **Interactive coordination table**: Press `r` to view complete history of agent coordination events and state transitions
- **Real-time feedback**: Displays real-time agent and system status with enhanced coordination visualization
- **Clear conversation history**: Type `/clear` to reset the conversation and start fresh
- **Easy exit**: Type `/quit`, `/exit`, `/q`, or press `Ctrl+C` to stop

**Watch the recorded demo:**

[![MassGen Case Study](https://img.youtube.com/vi/h1R7fxFJ0Zc/0.jpg)](https://www.youtube.com/watch?v=h1R7fxFJ0Zc)

### 5. 📊 View Results

The system provides multiple ways to view and analyze results:

#### Real-time Display
- **Live Collaboration View**: See agents working in parallel through a multi-region terminal display
- **Status Updates**: Real-time phase transitions, voting progress, and consensus building
- **Streaming Output**: Watch agents' reasoning and responses as they develop

**Watch an example here:**

[![MassGen Case Study](https://img.youtube.com/vi/Dp2oldJJImw/0.jpg)](https://www.youtube.com/watch?v=Dp2oldJJImw)

#### Comprehensive Logging

All sessions are automatically logged with detailed information for debugging and analysis.

**Real-time Interaction:**
- Press `r` during execution to view the coordination table in your terminal
- Watch agents collaborate, vote, and reach consensus in real-time

##### Logging Storage Structure

```
.massgen/
└── massgen_logs/
    └── log_YYYYMMDD_HHMMSS/           # Timestamped log directory
        ├── agent_<id>/                 # Agent-specific coordination logs
        │   └── YYYYMMDD_HHMMSS_NNNNNN/ # Timestamped coordination steps
        │       ├── answer.txt          # Agent's answer at this step
        │       ├── context.txt         # Context available to agent
        │       └── workspace/          # Agent workspace (if filesystem tools used)
        ├── agent_outputs/              # Consolidated output files
        │   ├── agent_<id>.txt          # Complete output from each agent
        │   ├── final_presentation_agent_<id>.txt       # Winning agent's final answer
        │   ├── final_presentation_agent_<id>_latest.txt # Symlink to latest
        │   └── system_status.txt       # System status and metadata
        ├── final/                      # Final presentation phase
        │   └── agent_<id>/             # Winning agent's final work
        │       ├── answer.txt          # Final answer
        │       └── context.txt         # Final context
        ├── coordination_events.json    # Structured coordination events
        ├── coordination_table.txt      # Human-readable coordination table
        ├── vote.json                   # Final vote tallies and consensus data
        ├── massgen.log                 # Complete debug log (or massgen_debug.log in debug mode)
        ├── snapshot_mappings.json      # Workspace snapshot metadata
        └── execution_metadata.yaml     # Query, config, and execution details
```

##### Key Log Files

- **Coordination Table** (`coordination_table.txt`): Complete visualization of multi-agent coordination with event timeline, voting patterns, and consensus building
- **Coordination Events** (`coordination_events.json`): Structured JSON log of all events (started_streaming, new_answer, vote, restart, final_answer)
- **Vote Summary** (`vote.json`): Final vote tallies, winning agent, and consensus information
- **Execution Metadata** (`execution_metadata.yaml`): Original query, timestamp, configuration, and execution context for reproducibility
- **Agent Outputs** (`agent_outputs/`): Complete output history and final presentations from all agents
- **Debug Log** (`massgen.log`): Complete system operations, API calls, tool usage, and error traces (use `--debug` for verbose logging)

→ For comprehensive logging guide and debugging techniques, see [Logging & Debugging](https://docs.massgen.io/en/latest/user_guide/logging.html)

## 💡 Case Studies

To see how MassGen works in practice, check out these detailed case studies based on real session logs:

- [**MassGen Case Studies**](docs/case_studies/README.md)
- [**Case Studies Documentation**](https://docs.massgen.io/en/latest/examples/case_studies.html) - Browse case studies online

---


## 🗺️ Roadmap

MassGen is currently in its foundational stage, with a focus on parallel, asynchronous multi-agent collaboration and orchestration. Our roadmap is centered on transforming this foundation into a highly robust, intelligent, and user-friendly system, while enabling frontier research and exploration. An earlier version of MassGen can be found [here](./massgen/v1).

⚠️ **Early Stage Notice:** As MassGen is in active development, please expect upcoming breaking architecture changes as we continue to refine and improve the system.

### Recent Achievements (v0.1.0)

**🎉 Released: October 17, 2025**

#### PyPI Package Release
- **Official Distribution**: MassGen now available via `pip install massgen`
- **Simplified Installation**: No need to clone repository for standard usage
- **Global Access**: Run `massgen` command from any directory after pip install

#### Comprehensive Documentation
- **Sphinx Documentation**: Full documentation site at [MassGen Official Documentation](https://docs.massgen.io/en/latest/)
- **Complete User Guide**: Installation, configuration, usage modes, and API reference
- **Case Studies**: Real-world examples with session logs and outcomes
- **Structured Navigation**: Getting Started, User Guide, Reference, Examples, and Development sections

#### Interactive Setup Wizard
- **Guided Configuration**: Step-by-step wizard for first-time users
- **Use Case Presets**: Research, Code, Q&A, Data Analysis, and more
- **API Key Management**: Centralized configuration in `~/.config/massgen/`
- **Smart Defaults**: Auto-configured tools based on selected use case

#### Enhanced CLI Experience
- **Simplified Commands**: Clean `massgen` command with intuitive syntax
- **Built-in Examples**: `@examples/` prefix for instant access to configurations
- **Backwards Compatibility**: Existing git clone workflows continue to work

### Previous Achievements (v0.0.3 - v0.0.32)

✅ **Docker Execution Mode (v0.0.32)**: Container-based isolation with secure command execution in isolated Docker containers preventing host filesystem access, persistent state management with packages and dependencies persisting across conversation turns, multi-agent support with dedicated isolated containers for each agent, configurable security with resource limits (CPU, memory), network isolation modes, and read-only volume mounts

✅ **MCP Architecture Refactoring (v0.0.32)**: Simplified client with renamed `MultiMCPClient` to `MCPClient` reflecting streamlined architecture, code consolidation by removing deprecated modules and consolidating duplicate MCP protocol handling, improved maintainability with standardized type hints, enhanced error handling, and cleaner code organization

✅ **Claude Code Docker Integration (v0.0.32)**: Automatic tool management with Bash tool automatically disabled in Docker mode routing commands through execute_command, MCP auto-permissions with automatic approval for MCP tools while preserving security validation, enhanced guidance with system messages preventing git repository confusion between host and container environments

✅ **Universal Command Execution (v0.0.31)**: MCP-based execute_command tool works across Claude, Gemini, OpenAI, and Chat Completions providers, AG2-inspired security with permission management and command filtering, code execution in planning mode for safer coordination

✅ **AG2 Group Chat Integration (v0.0.31)**: Multi-agent conversations using AG2's GroupChat and GroupChatManager frameworks, smart speaker selection (automatic, round-robin, manual) powered by LLMs, enhanced AG2 adapter supporting native group chat coordination

✅ **Audio & Video Generation (v0.0.31)**: Audio tools for text-to-speech and transcription, video generation using OpenAI's Sora-2 API, multimodal expansion beyond text and images

✅ **Multimodal Support Extension (v0.0.30)**: Audio and video processing for Chat Completions and Claude backends (WAV, MP3, MP4, AVI, MOV, WEBM formats), flexible media input via local paths or URLs, extended base64 encoding for audio/video files, configurable file size limits

✅ **Claude Agent SDK Migration (v0.0.30)**: Package migration from `claude-code-sdk` to `claude-agent-sdk>=0.0.22`, improved bash tool permission validation, enhanced system message handling

✅ **Qwen API Integration (v0.0.30)**: Added Qwen API provider to Chat Completions ecosystem with `QWEN_API_KEY` support, video understanding configuration examples

✅ **MCP Planning Mode (v0.0.29)**: Strategic planning coordination strategy for safer MCP tool usage, multi-backend support (Response API, Chat Completions, Gemini), agents plan without execution during coordination, 5 planning mode configurations

✅ **File Operation Safety (v0.0.29)**: Read-before-delete enforcement with `FileOperationTracker` class, `PathPermissionManager` integration with operation tracking methods, enhanced file operation safety mechanisms

✅ **AG2 Framework Integration (v0.0.28)**: Adapter system for external agent frameworks, AG2 ConversableAgent and AssistantAgent support with async execution, code execution in multiple environments (Local, Docker, Jupyter, YepCode), 4 ready-to-use AG2 configurations

✅ **Multimodal Support - Image Processing (v0.0.27)**: New `stream_chunk` module for multimodal content, image generation and understanding capabilities, file upload and search for document Q&A, Claude Sonnet 4.5 support, enhanced workspace multimodal tools

✅ **File Deletion and Workspace Management (v0.0.26)**: New MCP tools (`delete_file`, `delete_files_batch`, `compare_directories`, `compare_files`) for workspace cleanup and file comparison, consolidated `_workspace_tools_server.py`, enhanced path permission manager

✅ **Protected Paths and File-Based Context Paths (v0.0.26)**: Protect specific files within write-permitted directories, grant access to individual files instead of entire directories

✅ **Multi-Turn Filesystem Support (v0.0.25)**: Multi-turn conversation support with persistent context across turns, automatic `.massgen` directory structure, workspace snapshots and restoration, enhanced path permission system with smart exclusions, and comprehensive backend improvements

✅ **SGLang Backend Integration (v0.0.25)**: Unified vLLM/SGLang backend with auto-detection, support for SGLang-specific parameters like `separate_reasoning`, and dual server support for mixed vLLM and SGLang deployments

✅ **vLLM Backend Support (v0.0.24)**: Complete integration with vLLM for high-performance local model serving, POE provider support, GPT-5-Codex model recognition, backend utility modules refactoring, and comprehensive bug fixes including streaming chunk processing

✅ **Backend Architecture Refactoring (v0.0.23)**: Major code consolidation with new `base_with_mcp.py` class reducing ~1,932 lines across backends, extracted formatter module for better code organization, and improved maintainability through unified MCP integration

✅ **Workspace Copy Tools via MCP (v0.0.22)**: Seamless file copying capabilities between workspaces, configuration organization with hierarchical structure, and enhanced file operations for large-scale collaboration

✅ **Grok MCP Integration (v0.0.21)**: Unified backend architecture with full MCP server support, filesystem capabilities through MCP servers, and enhanced configuration files

✅ **Claude Backend MCP Support (v0.0.20)**: Extended MCP integration to Claude backend, full MCP protocol and filesystem support, robust error handling, and comprehensive documentation

✅ **Comprehensive Coordination Tracking (v0.0.19)**: Complete coordination tracking and visualization system with event-based tracking, interactive coordination table display, and advanced debugging capabilities for multi-agent collaboration patterns

✅ **Comprehensive MCP Integration (v0.0.18)**: Extended MCP to all Chat Completions backends (Cerebras AI, Together AI, Fireworks AI, Groq, Nebius AI Studio, OpenRouter), cross-provider function calling compatibility, 9 new MCP configuration examples

✅ **OpenAI MCP Integration (v0.0.17)**: Extended MCP (Model Context Protocol) support to OpenAI backend with full tool discovery and execution capabilities for GPT models, unified MCP architecture across multiple backends, and enhanced debugging

✅ **Unified Filesystem Support with MCP Integration (v0.0.16)**: Complete `FilesystemManager` class providing unified filesystem access for Gemini and Claude Code backends, with MCP-based operations for file manipulation and cross-agent collaboration

✅ **MCP Integration Framework (v0.0.15)**: Complete MCP implementation for Gemini backend with multi-server support, circuit breaker patterns, and comprehensive security framework

✅ **Enhanced Logging (v0.0.14)**: Improved logging system for better agents' answer debugging, new final answer directory structure, and detailed architecture documentation

✅ **Unified Logging System (v0.0.13)**: Centralized logging infrastructure with debug mode and enhanced terminal display formatting

✅ **Windows Platform Support (v0.0.13)**: Windows platform compatibility with improved path handling and process management

✅ **Enhanced Claude Code Agent Context Sharing (v0.0.12)**: Claude Code agents now share workspace context by maintaining snapshots and temporary workspace in orchestrator's side

✅ **Documentation Improvement (v0.0.12)**: Updated README with current features and improved setup instructions

✅ **Custom System Messages (v0.0.11)**: Enhanced system message configuration and preservation with backend-specific system prompt customization

✅ **Claude Code Backend Enhancements (v0.0.11)**: Improved integration with better system message handling, JSON response parsing, and coordination action descriptions

✅ **Azure OpenAI Support (v0.0.10)**: Integration with Azure OpenAI services including GPT-4.1 and GPT-5-chat models with async streaming

✅ **MCP (Model Context Protocol) Support (v0.0.9)**: Integration with MCP for advanced tool capabilities in Claude Code Agent, including Discord and Twitter integration

✅ **Timeout Management System (v0.0.8)**: Orchestrator-level timeout with graceful fallback and enhanced error messages

✅ **Local Model Support (v0.0.7)**: Complete LM Studio integration for running open-weight models locally with automatic server management

✅ **GPT-5 Series Integration (v0.0.6)**: Support for OpenAI's GPT-5, GPT-5-mini, GPT-5-nano with advanced reasoning parameters

✅ **Claude Code Integration (v0.0.5)**: Native Claude Code backend with streaming capabilities and tool support

✅ **GLM-4.5 Model Support (v0.0.4)**: Integration with ZhipuAI's GLM-4.5 model family

✅ **Foundation Architecture (v0.0.3)**: Complete multi-agent orchestration system with async streaming, builtin tools, and multi-backend support

✅ **Extended Provider Ecosystem**: Support for 15+ providers including Cerebras AI, Together AI, Fireworks AI, Groq, Nebius AI Studio, and OpenRouter

### Key Future Enhancements

-   **Bug Fixes & Backend Improvements:** Fixing image generation path issues and adding Claude multimodal support
-   **Advanced Agent Collaboration:** Exploring improved communication patterns and consensus-building protocols to improve agent synergy
-   **Expanded Model Integration:** Adding support for more frontier models and local inference engines
-   **Improved Performance & Scalability:** Optimizing the streaming and logging mechanisms for better performance and resource management
-   **Enhanced Developer Experience:** Completing tool registration system and web interface for better visualization

We welcome community contributions to achieve these goals.

### v0.1.1 Roadmap

Version 0.1.1 focuses on developer experience improvements and PyPI distribution:

#### Required Features
- **Configuration Builder CLI**: Interactive command-line tool for generating and validating MassGen configurations
- **PyPI Package Release v0.1.0**: Official PyPI package representing new usage paradigm with easy pip installation

#### Optional Features
- **Nested Chat Integration**: Complete AG2 nested chat pattern support for hierarchical agent conversations
- **DSPy Integration**: Framework integration for prompt optimization and systematic agent improvement

Key technical approach:
- **Config Builder**: Interactive prompts, configuration templates, validation and error checking, preset support
- **PyPI Package**: Production-ready distribution with proper dependencies, documentation, and migration guide
- **Nested Chat**: AG2 integration for hierarchical conversations with parent-child agent relationships
- **DSPy**: Prompt optimization, performance tuning, and systematic agent improvement workflows

For detailed milestones and technical specifications, see the [full v0.1.1 roadmap](ROADMAP.md).

---

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) for details.

---

## 📄 License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

---

<div align="center">

**⭐ Star this repo if you find it useful! ⭐**

Made with ❤️ by the MassGen team

</div>

## ⭐ Star History

[![Star History Chart](https://api.star-history.com/svg?repos=Leezekun/MassGen&type=Date)](https://www.star-history.com/#Leezekun/MassGen&Date)
