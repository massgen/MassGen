<p align="center">
  <img src="assets/logo.png" alt="MassGen Logo" width="360" />
</p>

<p align="center">
  <a href="https://www.python.org/downloads/">
    <img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+" style="margin-right: 5px;">
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="License" style="margin-right: 5px;">
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
    <img src="assets/massgen-demo.gif" alt="MassGen case study -- Berkeley Agentic AI Summit Question" width="800">
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

- [v0.0.29 Features](#-latest-features-v0029)
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
  - [v0.0.29](#recent-achievements-v0029)
  - [v0.0.3 - v0.0.28](#previous-achievements-v003---v0028)
- [Key Future Enhancements](#key-future-enhancements)
  - Bug Fixes & Backend Improvements
  - Advanced Agent Collaboration
  - Expanded Model, Tool & Agent Integrations
  - Improved Performance & Scalability
  - Enhanced Developer Experience
- [v0.0.30 Roadmap](#v0030-roadmap)
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

## 🆕 Latest Features (v0.0.29)

**Experience v0.0.29 MCP Planning Mode:**

See the new MCP Planning Mode in action:

[![MassGen v0.0.29 MCP Planning Mode Demo](https://img.youtube.com/vi/jLrMMEIr118/0.jpg)](https://youtu.be/jLrMMEIr118)

**What's New in v0.0.29:**
- **MCP Planning Mode** - New coordination strategy that plans MCP tool usage without execution, preventing irreversible actions during collaboration
- **File Operation Safety** - Read-before-delete enforcement ensures agents review files before deletion
- **Enhanced MCP Tool Filtering** - Multi-level filtering with backend-level and per-MCP-server control
- **Gemini Planning Mode Support** - Extended planning mode compatibility to Gemini backend

**Try v0.0.29 MCP Planning Mode:**
```bash
# Five agents collaborating with planning mode (no execution during coordination)
uv run python -m massgen.cli \
  --config massgen/configs/tools/planning/five_agents_filesystem_mcp_planning_mode.yaml \
  "Create a comprehensive project structure with documentation"

# Test MCP tools with multiple agents
uv run python -m massgen.cli \
  --config massgen/configs/tools/mcp/five_agents_weather_mcp_test.yaml \
  "Compare weather forecasts for New York, London, and Tokyo"
```

→ [See all release examples](massgen/configs/README.md#release-history--examples)

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

## 🚀 Quick Start

### 1. 📥 Installation

**Core Installation** (requires Python 3.11+):
```bash
git clone https://github.com/Leezekun/MassGen.git
cd MassGen

pip install uv
uv venv

# Optional: Install AG2 framework integration (only needed for AG2 configs)
# uv pip install -e ".[external]"
```

**Global Installation using `uv tool` (Recommended for multi-directory usage):**

Install MassGen using `uv tool` for isolated, global access:

```bash
# Clone the repository
git clone https://github.com/Leezekun/MassGen.git
cd MassGen

# Install MassGen as a global tool in editable mode
uv tool install -e .

# Optional: Install AG2 framework integration (only needed for AG2 configs)
# uv pip install -e ".[external]"

# Now run from any directory
cd ~/projects/website
uv tool run massgen --config tools/filesystem/gemini_gpt5_filesystem_multiturn.yaml

cd ~/documents/research
uv tool run massgen --config tools/filesystem/gemini_gpt5_filesystem_multiturn.yaml
```

**Benefits of `uv tool` installation:**
- ✅ Isolated Python environment (no conflicts with system Python)
- ✅ Available globally from any directory
- ✅ Editable mode (`-e .`) allows live development
- ✅ Easy updates with `git pull` (editable mode)
- ✅ Clean uninstall with `uv tool uninstall massgen`

**Optional Dependencies:**
```bash
# AG2 Framework Integration (for external agent frameworks)
uv pip install -e ".[external]"
```

**Optional CLI Tools** (for enhanced capabilities):
```bash
# Claude Code CLI - Advanced coding assistant
npm install -g @anthropic-ai/claude-code

# LM Studio - Local model inference
# For MacOS/Linux
sudo ~/.lmstudio/bin/lms bootstrap
# For Windows
cmd /c %USERPROFILE%/.lmstudio/bin/lms.exe bootstrap
```

### 2. 🔐 API Configuration

Using the template file `.env.example` to create a `.env` file in the `massgen` directory with your API keys. Note that only the API keys of the models used by your MassGen agent team is needed.

```bash
# Copy example configuration
cp .env.example .env
```

**Useful links to get API keys:**
 - [Azure OpenAI](https://learn.microsoft.com/en-us/azure/ai-services/openai/)
 - [Cerebras](https://inference-docs.cerebras.ai/introduction)
 - [Claude](https://docs.anthropic.com/en/api/overview)
 - [Gemini](https://ai.google.dev/gemini-api/docs)
 - [Grok](https://docs.x.ai/docs/overview)
 - [Kimi/Moonshot](https://platform.moonshot.ai/)
 - [OpenAI](https://platform.openai.com/api-keys)
 - [POE](https://poe.com/)
 - [Z AI](https://docs.z.ai/guides/overview/quick-start)

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

More providers and local inference engines (sglang) are welcome to be added.

#### Tools

MassGen agents can leverage various tools to enhance their problem-solving capabilities. Both API-based and CLI-based backends support different tool capabilities.

**Supported Built-in Tools by Backend:**

| Backend | Live Search | Code Execution | File Operations | MCP Support | Advanced Features |
|---------|:-----------:|:--------------:|:---------------:|:-----------:|:-----------------|
| **Azure OpenAI** (NEW in v0.0.10) | ❌ | ❌ | ❌ | ❌ | Code interpreter, Azure deployment management |
| **Claude API**  | ✅ | ✅ | ✅ | ✅ | Web search, code interpreter, **MCP integration** |
| **Claude Code** | ✅ | ✅ | ✅ | ✅ | **Native Claude Code SDK, comprehensive dev tools, MCP integration** |
| **Gemini API** | ✅ | ✅ | ✅ | ✅ | Web search, code execution, **MCP integration**|
| **Grok API** | ✅ | ❌ | ✅ | ✅ | Web search, **MCP integration** |
| **OpenAI API** | ✅ | ✅ | ✅ | ✅ | Web search, code interpreter, **MCP integration** |
| **ZAI API** | ❌ | ❌ | ✅ | ✅ | **MCP integration** |


### 4. 🏃 Run MassGen

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
uv run python -m massgen.cli \
  --config massgen/configs/basic/multi/three_agents_default.yaml \
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
uv run python -m massgen.cli \
  --config massgen/configs/tools/mcp/gpt5_nano_mcp_example.yaml \
  "What's the weather forecast for New York this week?"

# Multi-tool MCP with Gemini - Search + Weather + Filesystem (Requires BRAVE_API_KEY in .env)
uv run python -m massgen.cli \
  --config massgen/configs/tools/mcp/multimcp_gemini.yaml \
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
uv run python -m massgen.cli \
  --config massgen/configs/tools/filesystem/claude_code_single.yaml \
  "Create a Python web scraper and save results to CSV"

# Multi-agent file collaboration
uv run python -m massgen.cli \
  --config massgen/configs/tools/filesystem/claude_code_context_sharing.yaml \
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
  - id: "analyzer"
    backend:
      type: "claude_code"
      cwd: "workspace1"            # Agent-specific workspace

  - id: "reviewer"
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

#### **5. Project Integration & User Context Paths (NEW in v0.0.21)**

Work directly with your existing projects! User Context Paths allow you to share specific directories with all agents while maintaining granular permission control. This enables secure multi-agent collaboration on your real codebases, documentation, and data.

MassGen automatically organizes all its working files under a `.massgen/` directory in your project root, keeping your project clean and making it easy to exclude MassGen's temporary files from version control.

**Project Integration Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `context_paths` | list | **Yes** (for project integration) | Shared directories for all agents |
| └─ `path` | string | Yes | Absolute path to your project directory (**must be directory, not file**) |
| └─ `permission` | string | Yes | Access level: `"read"` or `"write"` |

**⚠️ Important:** Context paths must point to **directories**, not individual files. MassGen validates all paths during startup and will show clear error messages for missing paths or file paths.


**Quick Start Commands:**

```bash
# Multi-agent collaboration to improve the website in `massgen/configs/resources/v0.0.21-example
uv run python -m massgen.cli --config massgen/configs/tools/filesystem/gpt5mini_cc_fs_context_path.yaml "Enhance the website with: 1) A dark/light theme toggle with smooth transitions, 2) An interactive feature that helps users engage with the blog content (your choice - could be search, filtering by topic, reading time estimates, social sharing, reactions, etc.), and 3) Visual polish with CSS animations or transitions that make the site feel more modern and responsive. Use vanilla JavaScript and be creative with the implementation details."
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
    - path: "/home/user/my-project/src"
      permission: "read"           # Agents can analyze your code
    - path: "/home/user/my-project/docs"
      permission: "write"          # Final agent can update docs

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
    - path: "/home/user/legacy-app/src"
      permission: "read"           # Read existing codebase
    - path: "/home/user/legacy-app/tests"
      permission: "write"          # Write new tests
    - path: "/home/user/modernized-app"
      permission: "write"          # Create modernized version
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
uv run python -m massgen.cli \
  --config massgen/configs/tools/mcp/claude_mcp_example.yaml \
  "Research and compare weather in Beijing and Shanghai"
```

**OpenAI (GPT-5 Series with MCP - v0.0.17+)**
```bash
# GPT-5 with weather and external tools
uv run python -m massgen.cli \
  --config massgen/configs/tools/mcp/gpt5_mini_mcp_example.yaml \
  "What's the weather of Tokyo"
```

**Gemini (Multi-Server MCP - v0.0.15+)**
```bash
# Gemini with multiple MCP services
uv run python -m massgen.cli \
  --config massgen/configs/tools/mcp/multimcp_gemini.yaml \
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
uv run python -m massgen.cli \
  --config massgen/configs/providers/local/lmstudio.yaml \
  "Explain machine learning concepts"
```

→ [Browse by provider](massgen/configs/providers/) | [Browse by tools](massgen/configs/tools/) | [Browse teams](massgen/configs/teams/)

#### Additional Use Case Examples

**Question Answering & Research:**
```bash
# Complex research with multiple perspectives
uv run python -m massgen.cli \
  --config massgen/configs/basic/multi/gemini_4o_claude.yaml \
  "What's best to do in Stockholm in October 2025"

# Specific research requirements
uv run python -m massgen.cli \
  --config massgen/configs/basic/multi/gemini_4o_claude.yaml \
  "Give me all the talks on agent frameworks in Berkeley Agentic AI Summit 2025"
```

**Creative Writing:**
```bash
# Story generation with multiple creative agents
uv run python -m massgen.cli \
  --config massgen/configs/basic/multi/gemini_4o_claude.yaml \
  "Write a short story about a robot who discovers music"
```

**Development & Coding:**
```bash
# Full-stack development with file operations
uv run python -m massgen.cli \
  --config  massgen/configs/tools/filesystem/claude_code_single.yaml \
  "Create a Flask web app with authentication"
```

**Web Automation:** (still in test)
```bash
# Browser automation with screenshots and reporting
# Prerequisites: npm install @playwright/mcp@latest (for Playwright MCP server)
uv run python -m massgen.cli \
  --config massgen/configs/tools/code-execution/multi_agent_playwright_automation.yaml \
  "Browse three issues in https://github.com/Leezekun/MassGen and suggest documentation improvements. Include screenshots and suggestions in a website."

# Data extraction and analysis
uv run python -m massgen.cli \
  --config massgen/configs/tools/code-execution/multi_agent_playwright_automation.yaml \
  "Navigate to https://news.ycombinator.com, extract the top 10 stories, and create a summary report"
```

→ [**See detailed case studies**](docs/case_studies/README.md) with real session logs and outcomes

#### Interactive Mode & Advanced Usage

**Multi-Turn Conversations:**
```bash
# Start interactive chat (no initial question)
uv run python -m massgen.cli \
  --config massgen/configs/basic/multi/three_agents_default.yaml

# Debug mode for troubleshooting
uv run python -m massgen.cli \
  --config massgen/configs/basic/multi/three_agents_default.yaml \
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

All sessions are automatically logged with detailed information. The file can be viewed throught the interaction with UI.

##### Logging Storage Structure
Logging storage are organized in the following directory hierarchy:

```
massgen_logs/
└── log_{timestamp}/
    ├── agent_outputs/
    │   ├── agent_id.txt
    │   ├── final_presentation_agent_id.txt
    │   └── system_status.txt
    ├── agent_id/
    │   └── {answer_generation_timestamp}/
    │       └── files_included_in_generated_answer
    ├── final_workspace/
    │   └── agent_id/
    │       └── {answer_generation_timestamp}/
    │           └── files_included_in_generated_answer
    └── massgen.log / massgen_debug.log
```

##### Directory Structure Explanation
- `log_{timestamp}`: Main log directory identified by session timestamp
- `agent_outputs/`: Contains text outputs from each agent
  - `agent_id.txt`: Raw output from each agent
  - `final_presentation_agent_id.txt`: Final presentation for the selected agent
  - `system_status.txt`: System status information
- `agent_id/`: Directory for each agent containing answer versions
  - `{answer_generation_timestamp}/`: Timestamp directory for each answer version
    - `files_included_in_generated_answer`: All relevant files in that version
- `final_workspace/`: Final presentation for selected agents
  - `agent_id/`: Selected agent id
    - `{answer_generation_timestamp}/`: Timestamp directory for final presentation
      - `files_included_in_generated_answer`: All relevant files in final presentation
- `massgen.log` or `massgen_debug.log`: Main log file, `massgen.log` for general logging, `massgen_debug.log` for verbose debugging information.

##### Important Note
The final presentation continues to be stored in each Claude Code Agent's workspace as before. After generating the final presentation, the relevant files will be copied to the `final_workspace/` directory.

## 💡 Case Studies

### Case Studies

To see how MassGen works in practice, check out these detailed case studies based on real session logs:

- [**MassGen Case Studies**](docs/case_studies/README.md)

---


## 🗺️ Roadmap

MassGen is currently in its foundational stage, with a focus on parallel, asynchronous multi-agent collaboration and orchestration. Our roadmap is centered on transforming this foundation into a highly robust, intelligent, and user-friendly system, while enabling frontier research and exploration. An earlier version of MassGen can be found [here](./massgen/v1).

⚠️ **Early Stage Notice:** As MassGen is in active development, please expect upcoming breaking architecture changes as we continue to refine and improve the system.

### Recent Achievements (v0.0.29)

**🎉 Released: October 8, 2025**

#### MCP Planning Mode
- **Strategic Planning**: New `CoordinationConfig` class with `enable_planning_mode` flag for safer MCP tool usage
- **Multi-Backend Support**: Planning mode available for Response API, Chat Completions, and Gemini backends
- **Safer Collaboration**: Agents plan tool usage without execution during coordination phase, only the winning agent executes

#### File Operation Safety
- **Read-Before-Delete Enforcement**: New `FileOperationTracker` class prevents agents from deleting files they haven't read
- **PathPermissionManager Integration**: Enhanced with read/write/delete operation tracking methods

#### Enhanced MCP Tool Filtering
- **Multi-Level Control**: Combined backend-level and per-MCP-server tool filtering
- **Server-Specific Overrides**: MCP-server `allowed_tools` can override backend-level settings

#### New Configuration Files
- **Planning Mode Configs**: `five_agents_discord_mcp_planning_mode.yaml`, `five_agents_filesystem_mcp_planning_mode.yaml`, `five_agents_notion_mcp_planning_mode.yaml`, `five_agents_twitter_mcp_planning_mode.yaml`, `gpt5_mini_case_study_mcp_planning_mode.yaml`
- **MCP Test Configs**: `five_agents_travel_mcp_test.yaml`, `five_agents_weather_mcp_test.yaml`
- **Debug Config**: `skip_coordination_test.yaml`

#### Testing
- **New Test Suites**: `test_mcp_blocking.py` and `test_gemini_planning_mode.py`

### Previous Achievements (v0.0.3 - v0.0.28)

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

### v0.0.30 Roadmap

Version 0.0.30 focuses on fixing backend issues and extending multimodal support:

#### Required Features
- **Backend Issues & Organization**: Fix Claude Code backend reliability issues and reorganize configuration structure for better discoverability
- **Multimodal Support Extension**: Enable image processing capabilities in Claude and Chat Completions backends

#### Optional Features
- **Group Chat Integration**: Complete AG2 group chat orchestration integration for multi-agent group conversations
- **Tool Registration Refactoring**: Refactor tool registration architecture for better extensibility and plugin support

Key technical approach:
- **Backend Stability**: Comprehensive error handling, fallback mechanisms, and test coverage for Claude Code
- **Multimodal Extension**: Image input handling for Claude and Chat Completions backends with provider compatibility
- **Configuration Cleanup**: Standardize naming conventions and improve documentation for easier navigation
- **Extensible Architecture**: New tool registration system supporting dynamic discovery and plugin-based extensions

For detailed milestones and technical specifications, see the [full v0.0.30 roadmap](ROADMAP_v0.0.30.md).

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
