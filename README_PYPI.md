<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/Leezekun/MassGen/main/assets/logo-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/Leezekun/MassGen/main/assets/logo.png">
    <img src="https://raw.githubusercontent.com/Leezekun/MassGen/main/assets/logo.png" alt="MassGen Logo" width="360" />
  </picture>
</p>

<div align="center">

[![Docs](https://img.shields.io/badge/docs-massgen.ai-blue?style=flat-square&logo=readthedocs&logoColor=white)](https://docs.massgen.ai)
[![GitHub Stars](https://img.shields.io/github/stars/Leezekun/MassGen?style=flat-square&logo=github&color=181717&logoColor=white)](https://github.com/Leezekun/MassGen)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green?style=flat-square)](LICENSE)

</div>

<div align="center">

[![Follow on X](https://img.shields.io/badge/FOLLOW%20ON%20X-000000?style=for-the-badge&logo=x&logoColor=white)](https://x.massgen.ai)
[![Follow on LinkedIn](https://img.shields.io/badge/FOLLOW%20ON%20LINKEDIN-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/company/massgen-ai)
[![Join our Discord](https://img.shields.io/badge/JOIN%20OUR%20DISCORD-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.massgen.ai)

</div>

<h1 align="center">🚀 MassGen: Multi-Agent Scaling System for GenAI</h1>

<p align="center">
  <i>MassGen is a cutting-edge multi-agent system that leverages the power of collaborative AI to solve complex tasks.</i>
</p>

<p align="center">
  <a href="https://www.youtube.com/watch?v=Dp2oldJJImw">
    <img src="https://raw.githubusercontent.com/Leezekun/MassGen/main/docs/source/_static/images/thumbnail.png" alt="MassGen case study -- Berkeley Agentic AI Summit Question" width="800">
  </a>
</p>

<p align="center">
  <i>Scaling AI with collaborative, continuously improving agents</i>
</p>

MassGen is a cutting-edge multi-agent system that leverages the power of collaborative AI to solve complex tasks. It assigns a task to multiple AI agents who work in parallel, observe each other's progress, and refine their approaches to converge on the best solution to deliver a comprehensive and high-quality result. The power of this "parallel study group" approach is exemplified by advanced systems like xAI's Grok Heavy and Google DeepMind's Gemini Deep Think.

This project started with the "threads of thought" and "iterative refinement" ideas presented in [The Myth of Reasoning](https://docs.ag2.ai/latest/docs/blog/2025/04/16/Reasoning/), and extends the classic "multi-agent conversation" idea in [AG2](https://github.com/ag2ai/ag2). Here is a [video recording](https://www.youtube.com/watch?v=xM2Uguw1UsQ) of the background context introduction presented at the Berkeley Agentic AI Summit 2025.

<p align="center">
  <b>🤖 For LLM Agents:</b> <a href="AI_USAGE.md">AI_USAGE.md</a> - Complete automation guide to run MassGen inside an LLM
</p>

<p align="center">
  <b>📚 For Contributors:</b> See <a href="https://massgen.github.io/Handbook/">MassGen Contributor Handbook</a> - Centralized policies and resources for development and research teams
</p>

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

- [v0.1.11 Features](#-latest-features-v0111)
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
<summary><h3>🤖 Automation & LLM Integration</h3></summary>

- [Automation Mode](#-automation--llm-integration)
- [BackgroundShellManager](#using-backgroundshellmanager)
- [Status File Reference](#statusjson-structure)
- [Full Automation Guide](https://docs.massgen.ai/en/latest/user_guide/automation.html)
</details>

<details open>
<summary><h3>💡 Case Studies & Examples</h3></summary>

- [Case Studies](#-case-studies)
</details>

<details open>
<summary><h3>🗺️ Roadmap</h3></summary>

- Recent Achievements
  - [v0.1.11](#recent-achievements-v0111)
  - [v0.0.3 - v0.1.10](#previous-achievements-v003---v0110)
- [Key Future Enhancements](#key-future-enhancements)
  - Bug Fixes & Backend Improvements
  - Advanced Agent Collaboration
  - Expanded Model, Tool & Agent Integrations
  - Improved Performance & Scalability
  - Enhanced Developer Experience
- [v0.1.12 Roadmap](#v0112-roadmap)
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

## 🆕 Latest Features (v0.1.11)

**🎉 Released: November 12, 2025**

**What's New in v0.1.11:**
- **🎯 Skills System** - Modular prompting framework for enhanced agent capabilities
- **💾 Memory MCP Tool & Filesystem Integration** - Persistent memory management with filesystem integration for advanced workflows
- **⚙️ Rate Limiting System (Gemini)** - Multi-dimensional API rate control for Gemini models

**Key Improvements:**
- Always-available file search skill with automatic skill discovery from `massgen/skills/`
- MCP server for memory CRUD operations with markdown-based persistence and filesystem integration
- RPM, TPM, and RPD rate limiting for Gemini models with graceful cooldowns
- Enhanced Claude Code backend for Windows with improved system prompt handling

**Try v0.1.11 Features:**
```bash
# Install or upgrade from PyPI
pip install --upgrade massgen

# Skills System - enable domain-specific capabilities
# Prerequisites:
# - Docker daemon running (call `massgen/docker/build.sh [--sudo]` for updated containers)
# - openskills installed and placed in ./agents/skills.
#   - Run `npm i -g openskills` followed by `openskills install anthropics/skills --universal -y`
uv run massgen --config massgen/configs/skills/skills_basic.yaml \
  "Create cool algorithmic art we can use in GitHub repo"

# Memory with Skills and Task Planning - combined filesystem coordination
# Prerequisites: Docker daemon running
uv run massgen --config massgen/configs/skills/skills_with_memory.yaml \
  "Research neural architectures and document findings"

# Skills with Existing Filesystem - self-extension case study
# Prerequisites: Docker daemon running
uv run massgen --config massgen/configs/skills/skills_existing_filesystem.yaml \
  "Analyze the MassGen codebase to identify common development workflows that could benefit from being codified as skills. Create 1-2 optional skills that would help future agents work more efficiently with the codebase."

# Rate Limiting - manage API costs with multi-dimensional limits
# Enable rate limiting for any configuration with --enable-rate-limiting flag
massgen --backend gemini --model gemini-2.5-flash --enable-rate-limiting \
  "Explain quantum computing"
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

> 📖 **Complete Documentation:** For comprehensive guides, API reference, and detailed examples, visit **[MassGen Official Documentation](https://docs.massgen.ai/)**

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

→ See [Installation Guide](https://docs.massgen.ai/en/latest/quickstart/installation.html) for complete setup instructions.

**Method 2: Development Installation** (for contributors):

```bash
# Clone the repository
git clone https://github.com/Leezekun/MassGen.git
cd MassGen

# Install in editable mode with pip
pip install -e .

# Or with uv (faster)
uv pip install -e .

# Optional: External framework integration
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

→ **Complete setup guide with all providers:** See [API Key Configuration](https://docs.massgen.ai/en/latest/quickstart/installation.html#api-key-configuration) in the docs

**Get API keys:**
 - [OpenAI](https://platform.openai.com/api-keys) | [Claude](https://docs.anthropic.com/en/api/overview) | [Gemini](https://ai.google.dev/gemini-api/docs) | [Grok](https://docs.x.ai/docs/overview)
 - [Azure OpenAI](https://learn.microsoft.com/en-us/azure/ai-services/openai/) | [Cerebras](https://inference-docs.cerebras.ai/introduction) | [More providers...](https://docs.massgen.ai/en/latest/reference/supported_models.html)

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

→ For complete model list and configuration details, see [Supported Models](https://docs.massgen.ai/en/latest/reference/supported_models.html)

#### Tools

MassGen agents can leverage various tools to enhance their problem-solving capabilities. Both API-based and CLI-based backends support different tool capabilities.

**Supported Built-in Tools by Backend:**

| Backend | Live Search | Code Execution | File Operations | MCP Support | Multimodal Understanding | Multimodal Generation | Advanced Features |
|---------|:-----------:|:--------------:|:---------------:|:-----------:|:------------------------:|:---------------------:|:-----------------|
| **Azure OpenAI** (NEW in v0.0.10) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | Code interpreter, Azure deployment management |
| **Claude API**  | ✅ | ✅ | ✅ | ✅ | ✅<br/>*via custom tools* | ✅<br/>*via custom tools* | Web search, code interpreter, **MCP integration** |
| **Claude Code** | ✅ | ✅ | ✅ | ✅ | ✅<br/>*Image (native)*<br/>*Audio/Video/Docs (custom tools)* | ✅<br/>*via custom tools* | **Native Claude Code SDK, comprehensive dev tools, MCP integration** |
| **Gemini API** | ✅ | ✅ | ✅ | ✅ | ✅<br/>*Image (native)*<br/>*Audio/Video/Docs (custom tools)* | ✅<br/>*via custom tools* | Web search, code execution, **MCP integration**|
| **Grok API** | ✅ | ❌ | ✅ | ✅ | ✅<br/>*via custom tools* | ✅<br/>*via custom tools* | Web search, **MCP integration** |
| **OpenAI API** | ✅ | ✅ | ✅ | ✅ | ✅<br/>*Image (native)*<br/>*Audio/Video/Docs (custom tools)* | ✅<br/>*via custom tools* | Web search, code interpreter, **MCP integration** |
| **ZAI API** | ❌ | ❌ | ✅ | ✅ | ✅<br/>*via custom tools* | ✅<br/>*via custom tools* | **MCP integration** |

**Notes:**
- **Multimodal Understanding** (NEW in v0.1.3): Analyze images, audio, video, and documents via custom tools using OpenAI GPT-4.1 - works with any backend
- **Multimodal Generation** (NEW in v0.1.4): Generate images, videos, audio, and documents via custom tools using OpenAI APIs - works with any backend
- **Semantic Search Skills** (NEW in v0.1.12): Optional skills for advanced code understanding - `serena` (LSP-based symbol tracking) and `semtools` (embedding-based semantic search)
- See custom tool configurations: [`understand_image.yaml`](massgen/configs/tools/custom_tools/multimodal_tools/understand_image.yaml), [`text_to_image_generation_single.yaml`](massgen/configs/tools/custom_tools/multimodal_tools/text_to_image_generation_single.yaml)

→ For detailed backend capabilities and tool integration guides, see [User Guide - Backends](https://docs.massgen.ai/en/latest/user_guide/backends.html)

→ For skills system documentation, see [User Guide - Skills](https://docs.massgen.ai/en/latest/user_guide/skills.html)

---

### 4. 🏃 Run MassGen

> **Complete Usage Guide:** For all usage modes, advanced features, and interactive multi-turn sessions, see [Running MassGen](https://docs.massgen.ai/en/latest/quickstart/running-massgen.html)

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

→ For comprehensive MCP integration guide, see [MCP Integration](https://docs.massgen.ai/en/latest/user_guide/mcp_integration.html)

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

→ For comprehensive file operations guide, see [File Operations](https://docs.massgen.ai/en/latest/user_guide/file_operations.html)

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
  agent_temporary_workspace: "temp"     # → .massgen/temp/

agents:
  - backend:
      cwd: "workspace1"                 # → .massgen/workspaces/workspace1/
```

→ For comprehensive project integration guide, see [Project Integration](https://docs.massgen.ai/en/latest/user_guide/project_integration.html)

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

→ [**See detailed case studies**](docs/source/examples/case_studies/README.md) with real session logs and outcomes

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

→ For comprehensive logging guide and debugging techniques, see [Logging & Debugging](https://docs.massgen.ai/en/latest/user_guide/logging.html)

---

## 🤖 Automation & LLM Integration

**→ For LLM agents: See [AI_USAGE.md](AI_USAGE.md) for complete command-line usage guide**

MassGen provides **automation mode** designed for LLM agents and programmatic workflows:

### Quick Start - Automation Mode

```bash
# Run with minimal output and status tracking
uv run massgen --automation --config your_config.yaml "Your question"
```

### Comprehensive Guide

→ **Full automation guide with examples:** [Automation Guide](https://docs.massgen.ai/en/latest/user_guide/automation.html)

Topics covered:
- Complete automation patterns with error handling
- Parallel experiment execution
- Performance tips and troubleshooting

---

## 💡 Case Studies

To see how MassGen works in practice, check out these detailed case studies based on real session logs:

**Featured:**
- [**Multi-Turn Persistent Memory**](docs/source/examples/case_studies/multi-turn-persistent-memory.md) - Research-to-implementation workflow demonstrating memory system (v0.1.5) | [📹 Watch Demo](https://youtu.be/wWxxFgyw40Y)

**All Case Studies:**
- [**MassGen Case Studies**](docs/source/examples/case_studies/README.md)
- [**Case Studies Documentation**](https://docs.massgen.ai/en/latest/examples/case_studies.html) - Browse case studies online

---


## 🗺️ Roadmap

MassGen is currently in its foundational stage, with a focus on parallel, asynchronous multi-agent collaboration and orchestration. Our roadmap is centered on transforming this foundation into a highly robust, intelligent, and user-friendly system, while enabling frontier research and exploration.

⚠️ **Early Stage Notice:** As MassGen is in active development, please expect upcoming breaking architecture changes as we continue to refine and improve the system.

### Recent Achievements (v0.1.11)

**🎉 Released: November 12, 2025**

#### Skills System
- **Modular Prompting Framework**: SkillsManager class for dynamic skill loading and injection (`massgen/filesystem_manager/skills_manager.py`)
- **File Search Skill**: Always-available skill for searching files and code across workspace (`massgen/skills/always/file_search/SKILL.md`)
- **Automatic Discovery**: Skills organized into `always/` (auto-included) and `optional/` categories with Docker-compatible mounting
- **Configuration Examples**: `skills_basic.yaml`, `skills_existing_filesystem.yaml`, `skills_with_memory.yaml`

#### Memory MCP Tool & Filesystem Integration
- **Memory MCP Server**: MCP server for memory management with filesystem persistence (`massgen/mcp_tools/memory/`)
- **Memory Data Models**: Short-term and long-term memory tiers with markdown-based storage format
- **Workspace Integration**: Automatic persistence to workspace under `memory/short_term/` and `memory/long_term/` directories
- **Cross-Agent Sharing**: Orchestrator integration for memory sharing across agents
- **Combined Workflows**: Simultaneous memory MCP tools and filesystem operations enable advanced workflows for long-running projects requiring both code changes and learned context
- **Enhanced Windows Support**: Improved Claude Code backend handling of long system prompts on Windows
- **Planning MCP Updates**: Tasks saved to agent workspace instead of separate directory

#### Rate Limiting System (Gemini)
- **Multi-Dimensional Limiting**: Support for RPM (requests per minute), TPM (tokens per minute), and RPD (requests per day) (`massgen/rate_limiter.py`)
- **Model-Specific Limits**: Configurable thresholds for Gemini models with graceful cooldown periods
- **Configuration System**: YAML-based configuration in `massgen/configs/rate_limits/rate_limits.yaml`
- **CLI Integration**: Optional `--enable-rate-limiting` flag for opt-in rate limiting
- **Asyncio Lock Fix**: Resolved rate limiter lock reuse across different event loops

### Previous Achievements (v0.0.3 - v0.1.10)

✅ **Framework Interoperability Streaming (v0.1.10)**: Real-time intermediate step streaming for LangGraph and SmoLAgent with log/output distinction, enhanced debugging for external framework reasoning steps

✅ **Docker Configuration Enhancements (v0.1.10)**: Nested authentication with separate mount and environment variable arrays, custom image support via Dockerfile.custom-example, automatic package installation

✅ **Universal Workspace Isolation (v0.1.10)**: Instance ID generation extended to all execution modes ensuring safe parallel execution, enhanced workspace path uniqueness across concurrent sessions

✅ **Session Management System (v0.1.9)**: Complete session state tracking and restoration with SessionState dataclass and SessionRegistry for multi-turn persistence across CLI invocations, workspace continuity preserving agent states and coordination history between turns

✅ **Computer Use Tools (v0.1.9)**: Native Claude and Gemini computer use API integration for browser and desktop automation with screenshot analysis and action generation, lightweight browser automation for specific tasks without full computer use overhead

✅ **Fuzzy Model Matching (v0.1.9)**: Intelligent model name search with approximate inputs (e.g., "sonnet" → "claude-sonnet-4-5-20250929"), model catalog system with curated lists across providers, enhanced config builder with automatic model search

✅ **Backend Capabilities Expansion (v0.1.9)**: Comprehensive backend registry with detailed specifications for all providers, audio/video support, hardware acceleration, unified access across diverse model families, enhanced memory update logic focusing on actionable patterns

✅ **Automation Mode for LLM Agents (v0.1.8)**: Complete infrastructure for running MassGen inside LLM agents with SilentDisplay class for minimal output (~10 lines vs 250-3,000+), real-time status.json monitoring updated every 2 seconds, meaningful exit codes (0=success, 1=config error, 2=execution error, 3=timeout, 4=interrupted), automatic workspace isolation for parallel execution, meta-coordination capabilities allowing MassGen to run MassGen

✅ **DSPy Question Paraphrasing Integration (v0.1.8)**: Intelligent question diversity for multi-agent coordination with semantic-preserving paraphrasing module supporting three strategies (diverse/balanced/conservative), automatic semantic validation to ensure meaning preservation, thread-safe caching system with SHA-256 hashing, support for all backends as paraphrasing engines, orchestrator integration for automatic question variant distribution

✅ **Agent Task Planning System (v0.1.7)**: MCP-based planning server with task lifecycle management, dependency tracking with automatic validation and blocking, status transitions between pending/in_progress/completed/blocked states, orchestrator integration for plan-aware multi-agent coordination

✅ **Background Shell Execution (v0.1.7)**: Persistent shell sessions for long-running commands with BackgroundShell class supporting async execution, real-time output streaming and monitoring, automatic timeout handling, enhanced code execution server with background capabilities

✅ **Preemption Coordination (v0.1.7)**: Agents can interrupt ongoing coordination to submit better answers without full restart, partial progress preservation during preemption, enhanced coordination tracker logging preemption events

✅ **Framework Interoperability (v0.1.6)**: AG2 nested chat, LangGraph workflows, AgentScope agents, OpenAI Assistants, and SmoLAgent integrated as custom tools with cross-framework collaboration and streaming support for AG2

✅ **Configuration Validator (v0.1.6)**: Comprehensive YAML validation with ConfigValidator class, pre-commit integration, and detailed error messages with actionable suggestions

✅ **Unified Tool Execution (v0.1.6)**: ToolExecutionConfig dataclass standardizing tool handling across ResponseBackend, ChatCompletionsBackend, and ClaudeBackend with consistent error reporting

✅ **Gemini Backend Simplification (v0.1.6)**: Removed gemini_mcp_manager and gemini_trackers modules, consolidated code reducing codebase by 1,598 lines

✅ **Memory System (v0.1.5)**: Long-term semantic memory via mem0 integration with fact extraction and retrieval across sessions, short-term conversational memory for active context, automatic context compression when approaching token limits, cross-agent memory sharing with turn-aware filtering, session management for memory isolation and continuation, Qdrant vector database integration for semantic search

✅ **Multimodal Generation Tools (v0.1.4)**: Create images from text via DALL-E API, generate videos from descriptions, text-to-speech with audio transcription support, document generation for PDF/DOCX/XLSX/PPTX formats, image transformation capabilities for existing images

✅ **Binary File Protection (v0.1.4)**: Automatic blocking prevents text tools from accessing 40+ binary file types including images, videos, audio, archives, and Office documents, intelligent error messages guide users to appropriate specialized tools for binary content

✅ **Crawl4AI Integration (v0.1.4)**: Intelligent web scraping with LLM-powered content extraction and customizable extraction patterns for structured data retrieval from websites

✅ **Post-Evaluation Workflow (v0.1.3)**: Winning agents evaluate their own answers before submission with submit and restart capabilities, supports answer confirmation and orchestration restart with feedback across all backends

✅ **Multimodal Understanding Tools (v0.1.3)**: Analyze images, transcribe audio, extract video frames, and process documents (PDF/DOCX/XLSX/PPTX) with structured JSON output, works across all backends via OpenAI GPT-4.1 integration

✅ **Docker Sudo Mode (v0.1.3)**: Privileged command execution in Docker containers for system-level operations requiring elevated permissions

✅ **Intelligent Planning Mode (v0.1.2)**: Automatic question analysis determining operation irreversibility via `_analyze_question_irreversibility()` in orchestrator, selective tool blocking with `set_planning_mode_blocked_tools()` and `is_mcp_tool_blocked()` methods, read-only MCP operations during coordination with write operations blocked, zero-configuration transparent operation, multi-workspace support

✅ **Model Updates (v0.1.2)**: Claude 4.5 Haiku model `claude-haiku-4-5-20251001`, reorganized Claude model priorities with `claude-sonnet-4-5-20250929` default, Grok web search fix with `_add_grok_search_params()` method for proper `extra_body` parameter handling

✅ **Custom Tools System (v0.1.1)**: User-defined Python function registration using `ToolManager` class in `massgen/tool/_manager.py`, cross-backend support alongside MCP servers, builtin/MCP/custom tool categories with automatic discovery, 40+ examples in `massgen/configs/tools/custom_tools/`, voting sensitivity controls with three-tier quality system (lenient/balanced/strict), answer novelty detection preventing duplicates

✅ **Backend Enhancements (v0.1.1)**: Gemini architecture refactoring with extracted MCP management (`gemini_mcp_manager.py`), tracking (`gemini_trackers.py`), and utilities, new capabilities registry in `massgen/backend/capabilities.py` documenting feature support across all backends

✅ **PyPI Package Release (v0.1.0)**: Official distribution via `pip install massgen` with simplified installation, global `massgen` command accessible from any directory, comprehensive Sphinx documentation at [docs.massgen.ai](https://docs.massgen.ai/), interactive setup wizard with use case presets and API key management, enhanced CLI with `@examples/` prefix for built-in configurations

✅ **Docker Execution Mode (v0.0.32)**: Container-based isolation with secure command execution in isolated Docker containers preventing host filesystem access, persistent state management with packages and dependencies persisting across conversation turns, multi-agent support with dedicated isolated containers for each agent, configurable security with resource limits (CPU, memory), network isolation modes, and read-only volume mounts

✅ **MCP Architecture Refactoring (v0.0.32)**: Simplified client with renamed `MultiMCPClient` to `MCPClient` reflecting streamlined architecture, code consolidation by removing deprecated modules and consolidating duplicate MCP protocol handling, improved maintainability with standardized type hints, enhanced error handling, and cleaner code organization

✅ **Claude Code Docker Integration (v0.0.32)**: Automatic tool management with Bash tool automatically disabled in Docker mode routing commands through execute_command, MCP auto-permissions with automatic approval for MCP tools while preserving security validation, enhanced guidance with system messages preventing git repository confusion between host and container environments

✅ **Universal Command Execution (v0.0.31)**: MCP-based execute_command tool works across Claude, Gemini, OpenAI, and Chat Completions providers, comprehensive security with permission management and command filtering, code execution in planning mode for safer coordination

✅ **External Framework Integration (v0.0.31)**: Multi-agent conversations using external framework group chat patterns, smart speaker selection (automatic, round-robin, manual) powered by LLMs, enhanced adapter supporting native group chat coordination

✅ **Audio & Video Generation (v0.0.31)**: Audio tools for text-to-speech and transcription, video generation using OpenAI's Sora-2 API, multimodal expansion beyond text and images

✅ **Multimodal Support Extension (v0.0.30)**: Audio and video processing for Chat Completions and Claude backends (WAV, MP3, MP4, AVI, MOV, WEBM formats), flexible media input via local paths or URLs, extended base64 encoding for audio/video files, configurable file size limits

✅ **Claude Agent SDK Migration (v0.0.30)**: Package migration from `claude-code-sdk` to `claude-agent-sdk>=0.0.22`, improved bash tool permission validation, enhanced system message handling

✅ **Qwen API Integration (v0.0.30)**: Added Qwen API provider to Chat Completions ecosystem with `QWEN_API_KEY` support, video understanding configuration examples

✅ **MCP Planning Mode (v0.0.29)**: Strategic planning coordination strategy for safer MCP tool usage, multi-backend support (Response API, Chat Completions, Gemini), agents plan without execution during coordination, 5 planning mode configurations

✅ **File Operation Safety (v0.0.29)**: Read-before-delete enforcement with `FileOperationTracker` class, `PathPermissionManager` integration with operation tracking methods, enhanced file operation safety mechanisms

✅ **External Framework Integration (v0.0.28)**: Adapter system for external agent frameworks with async execution, code execution in multiple environments (Local, Docker, Jupyter, YepCode), ready-to-use configurations for framework integration

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

### v0.1.12 Roadmap

Version 0.1.12 focuses on intelligent tool selection and semantic search capabilities:

#### Planned Features
- **Automatic MCP Tool Selection**: Intelligent selection of MCP tools based on task requirements to improve performance
- **Semtools/Serena Semantic Search Skill**: Advanced semantic search capabilities as a reusable skill

Key technical approach:
- **Tool Selection**: Pre-execution tool selection based on prompts, dynamic tool refinement during execution, filesystem-first approach to reduce context pollution
- **Semantic Search**: Implement semtools and serena for semantic code discovery, multiple embedding models support, skills framework integration

**Target Release**: November 14, 2025 (Friday @ 9am PT)

For detailed milestones and technical specifications, see the [full v0.1.12 roadmap](ROADMAP_v0.1.12.md).

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
