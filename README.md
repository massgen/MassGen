<p align="center">
  <img src="assets/logo.png" alt="MassGen Logo" width="360" />
</p>

<p align="center">
  <a href="https://www.python.org/downloads/">
    <img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python 3.10+" style="margin-right: 5px;">
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
  <a href="https://youtu.be/eMBdoAYeujw">
    <img src="assets/thumbnail.png" alt="MassGen Demo Video" width="600">
  </a>
</p>


<!-- <div align="center">
  <img src="assets/MassGen-v1.gif" alt="MassGen Demo" width="800">
</div> -->

> 🧠 **Multi-agent scaling through intelligent collaboration in Grok Heavy style**

MassGen is a cutting-edge multi-agent system that leverages the power of collaborative AI to solve complex tasks. It assigns a task to multiple AI agents who work in parallel, observe each other's progress, and refine their approaches to converge on the best solution to deliver a comprehensive and high-quality result. The power of this "parallel study group" approach is exemplified by advanced systems like xAI's Grok Heavy and Google DeepMind's Gemini Deep Think.
This project started with the "threads of thought" and "iterative refinement" ideas presented in [The Myth of Reasoning](https://docs.ag2.ai/latest/docs/blog/2025/04/16/Reasoning/), and extends the classic "multi-agent conversation" idea in [AG2](https://github.com/ag2ai/ag2).

---

## 📋 Table of Contents

- [✨ Key Features](#-key-features)
- [🏗️ System Design](#️-system-design)
- [🚀 Quick Start](#-quick-start)
- [💡 Examples](#-examples)
- [🤝 Contributing](#-contributing)

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

## 🏗️ System Design

MassGen operates through a sophisticated architecture designed for **seamless multi-agent collaboration**:

```mermaid
graph TB
    O[🚀 MassGen Orchestrator<br/>📋 Task Distribution & Coordination]

    subgraph Collaborative Agents
        A1[Agent 1<br/>🏗️ Anthropic/Claude + Tools]
        A2[Agent 2<br/>🌟 Google/Gemini + Tools]
        A3[Agent 3<br/>🤖 OpenAI/GPT/O + Tools]
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

```bash
git clone https://github.com/Leezekun/MassGen.git
cd MassGen
pip install uv
uv venv
```

### 2. 🔐 API Configuration

Create a `.env` file in the `massgen` directory with your API keys:

```bash
# Copy example configuration
cp .env.example .env

# Edit with your API keys
OPENAI_API_KEY=your-openai-key-here
XAI_API_KEY=your-xai-key-here
ANTHROPIC_API_KEY=your-anthropic-key-here
GEMINI_API_KEY=your-gemini-key-here
```

Make sure you set up the API key for the model you want to use.

**Useful links to get API keys:**
 - [Claude](https://docs.anthropic.com/en/api/overview)
 - [OpenAI](https://platform.openai.com/api-keys)
 - [Grok](https://docs.x.ai/docs/overview)
 - [Gemini](https://ai.google.dev/gemini-api/docs)

### 3. 🧩 Supported Models and Tools

<!-- What does the following mean? If it can be clarified, then we can uncomment -->
<!-- Configure the models you wish to use by updating the model registry in `massgen/utils.py`.  -->

#### Models

The system currently supports four model providers with advanced reasoning capabilities: **Anthropic Claude**, **OpenAI**, **xAI Grok** and **Google Gemini**. 
More providers and local inference of open-sourced models (using vllm or sglang) will be added (help wanted!) and the extension will be made easier.

#### Tools

MassGen agents can leverage various tools to enhance their problem-solving capabilities. The Claude, OpenAI, and Grok models can use their own built-in search and code execution. 

**Supported Built-in Tools by Models:**

| Backend | Live Search | Code Execution |
|---------|:-----------:|:--------------:|
| **Claude** | ✅ | ✅ |
| **OpenAI** | ✅ | ✅ |
| **Grok** | ✅ | ❌ |
| **Gemini** | ✅ | ✅ |

### 4. 🏃 Run MassGen

#### Quick Setup with Backend and Model

```bash
uv run python -m massgen.cli --model gpt-4o-mini "Which AI won IMO in 2025?"
```

#### Multiple Agents from Config
```bash
# Use configuration file
uv run python -m massgen.cli --config three_agents_default.yaml "Compare different approaches to renewable energy"
```

#### Configuration Parameters

| Parameter          | Description |
|-------------------|-------------|
| `--config`         | Path to YAML/JSON configuration file with agent definitions, model parameters, and UI settings |
| `--backend`        | Backend type for quick setup without a config file (`openai`, `grok`, or `claude`) |
| `--model`          | Model name for quick setup (e.g., `gpt-4o-mini`, `claude-sonnet-4-20250514`) |
| `--system-message` | Custom system prompt for the agent in quick setup mode |
| `--create-samples` | Create example configuration files (`single_agent.yaml`, `multi_agent.yaml`) in a `configs/` directory |
| `--no-display`     | Disable real-time streaming UI coordination display (fallback to simple text output) |
| `--no-logs`        | Disable logging of session inputs/outputs to file |
| `question`         | Optional single-question input; if omitted, MassGen enters interactive chat mode |

#### Configuration File Format

MassGen v3 supports YAML/JSON configuration files with the following structure:

**Single Agent Configuration:**
```yaml
agent:
  id: "assistant"
  backend:
    type: "openai"              # Backend type: openai, claude, grok, or gemini (optional)
    model: "gpt-4o-mini"        # Model name specific to the backend
    enable_web_search: true     # Enable web search capability (optional)
    enable_code_interpreter: true # Enable code execution (optional)
    # api_key: "your-key"       # Optional, uses environment variables if not set
  system_message: "Custom system prompt"  # Optional custom system message

ui:
  display_type: "rich_terminal" # Display type: rich_terminal, terminal, or simple
  logging_enabled: true         # Enable session logging
```

**Multi-Agent Configuration:**
```yaml
agents:
  - id: "agent1"
    backend:
      type: "openai"
      model: "gpt-4o"
    system_message: "Specialized prompt for agent 1"
    
  - id: "agent2" 
    backend:
      type: "claude"
      model: "claude-3-5-sonnet-20241022"
    system_message: "Specialized prompt for agent 2"

ui:
  display_type: "rich_terminal"
  logging_enabled: true
```

**Note**: `--config` and `--model` are mutually exclusive - use one or the other.

#### Interactive Multi-Turn Mode

MassGen supports an interactive mode where you can have ongoing conversations with the system:

```bash
# Start interactive mode with multiple agents
uv run python -m massgen.cli --model gpt-4o-mini

# Start interactive mode with configuration file
uv run python -m massgen.cli --config three_agents_default.yaml
```

**Interactive Mode Features:**
- **Multi-turn conversations**: Multiple agents collaborate to chat with you in an ongoing conversation
- **Real-time feedback**: Displays real-time agent and system status
- **Easy exit**: Type `quit`, `exit`, or press `Ctrl+C` to stop


### 5. 📊 View Results

The system provides multiple ways to view and analyze results:

#### Real-time Display
- **Live Collaboration View**: See agents working in parallel through a multi-region terminal display
- **Status Updates**: Real-time phase transitions, voting progress, and consensus building
- **Streaming Output**: Watch agents' reasoning and responses as they develop

#### Comprehensive Logging
All sessions are automatically logged with detailed information. The file can be viewed throught the interaction with UI.

```bash
agent_outputs/
  ├── agent_1.txt       # The full logs by agent 1
  ├── agent_2.txt       # The full logs by agent 2
  ├── agent_3.txt       # The full logs by agent 3
  ├── system_status.txt # The full logs of system status
```
---

## 💡 Examples

Here are a few examples of how you can use MassGen for different tasks:

### Case Studies

To see how MassGen works in practice, check out these detailed case studies based on real session logs:

- [**MassGen Case Studies**](docs/case_studies/index.md)

<!-- Uncomment when we add coding agent support -->
<!-- ### 1. 📝 Code Generation

```bash
uv run python cli.py --config examples/fast_config.yaml "Design a logo for MassGen (multi-agent scaling system for GenAI) GitHub README"
``` -->

### 1. ❓ Question Answering

```bash
# Ask a question about a complex topic
uv run python -m massgen.cli --config massgen/configs/gemini_4o_claude.yaml "what's best to do in Stockholm in October 2025"

uv run python -m massgen.cli --config massgen/configs/gemini_4o_claude.yaml "give me all the talks on agent frameworks in Berkeley Agentic AI Summit 2025, note, the sources must include the word Berkeley, don't include talks from any other agentic AI summits"
```

### 2. 🧠 Creative Writing

```bash
# Generate a short story
uv run python -m massgen.cli --config massgen/configs/gemini_4o_claude.yaml "Write a short story about a robot who discovers music."
```

### 3. Research
```bash
uv run python -m massgen.cli --config massgen/configs/gemini_4o_claude.yaml "How much does it cost to run HLE benchmark with Grok-4"
```

---

## 🗺️ Roadmap

MassGen is currently in its foundational stage, with a focus on parallel, asynchronous multi-agent collaboration and orchestration. Our roadmap is centered on transforming this foundation into a highly robust, intelligent, and user-friendly system, while enabling frontier research and exploration.

⚠️ **Early Stage Notice:** As MassGen is in active development, please expect upcoming breaking architecture changes as we continue to refine and improve the system.

### Key Future Enhancements:

-   **Advanced Agent Collaboration:** Exploring improved communication patterns and consensus-building protocols to improve agent synergy.
-   **Expanded Model, Tool & Agent Integration:** Adding support for more models/tools/agents, including Claude, a wider range of tools like MCP Servers, and coding agents.
-   **Improved Performance & Scalability:** Optimizing the streaming and logging mechanisms for better performance and resource management.
-   **Enhanced Developer Experience:** Introducing a more modular agent design and a comprehensive benchmarking framework for easier extension and evaluation.
-   **Web Interface:** Developing a web-based UI for better visualization and interaction with the agent ecosystem.

We welcome community contributions to help us achieve these goals.

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
