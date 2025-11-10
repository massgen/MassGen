# MassGen Configuration Guide

This guide explains the organization and usage of MassGen configuration files.

## Directory Structure

```
massgen/configs/
├── basic/                 # Simple configs to get started
│   ├── single/           # Single agent examples
│   └── multi/            # Multi-agent examples
├── tools/                 # Tool-enabled configurations
│   ├── mcp/              # MCP server integrations
│   ├── web-search/       # Web search enabled configs
│   ├── code-execution/   # Code interpreter/execution
│   └── filesystem/       # File operations & workspace
├── providers/             # Provider-specific examples
│   ├── openai/           # GPT-5 series configs
│   ├── claude/           # Claude API configs
│   ├── gemini/           # Gemini configs
│   ├── azure/            # Azure OpenAI
│   ├── local/            # LMStudio, local models
│   └── others/           # Cerebras, Grok, Qwen, ZAI
├── teams/                # Pre-configured specialized teams
│   ├── creative/         # Creative writing teams
│   ├── research/         # Research & analysis
│   └── development/      # Coding teams
└── docs/                 # Setup guides and documentation
```

## CLI Command Line Arguments

| Parameter          | Description |
|-------------------|-------------|
| `--config`         | Path to YAML configuration file with agent definitions, model parameters, backend parameters and UI settings |
| `--backend`        | Backend type for quick setup without a config file (`claude`, `claude_code`, `gemini`, `grok`, `openai`, `azure_openai`, `zai`). Optional for [models with default backends](../utils.py).|
| `--model`          | Model name for quick setup (e.g., `gemini-2.5-flash`, `gpt-5-nano`, ...). `--config` and `--model` are mutually exclusive - use one or the other. |
| `--system-message` | System prompt for the agent in quick setup mode. If `--config` is provided, `--system-message` is omitted. |
| `--no-display`     | Disable real-time streaming UI coordination display (fallback to simple text output).|
| `--no-logs`        | Disable real-time logging.|
| `--debug`          | Enable debug mode with verbose logging (NEW in v0.0.13). Shows detailed orchestrator activities, agent messages, backend operations, and tool calls. Debug logs are saved to `agent_outputs/log_{time}/massgen_debug.log`. |
| `"<your question>"`         | Optional single-question input; if omitted, MassGen enters interactive chat mode. |

## Quick Start Examples

### 🌟 Recommended Showcase Example

**Best starting point for multi-agent collaboration:**
```bash
# Three powerful agents (Gemini, GPT-5, Grok) with enhanced workspace tools
massgen --config @examples/basic/multi/three_agents_default "Your complex task"
```

This configuration combines:
- **Gemini 2.5 Flash** - Fast, versatile with web search
- **GPT-5 Nano** - Advanced reasoning with code interpreter
- **Grok-3 Mini** - Efficient with real-time web search

### Quick Setup Without Config Files

**Single agent with model name only:**
```bash
# Quick test with any supported model - no configuration needed
massgen --model claude-3-5-sonnet-latest "What is machine learning?"
massgen --model gemini-2.5-flash "Explain quantum computing"
massgen --model gpt-5-nano "Summarize the latest AI developments"
```

**Interactive Mode:**
```bash
# Start interactive chat (no initial question)
massgen --config @examples/basic/multi/three_agents_default

# Debug mode for troubleshooting
massgen --config @examples/basic/multi/three_agents_default --debug "Your question"
```

### Basic Usage

For simple single-agent setups:
```bash
massgen --config @examples/basic/single/single_agent "Your question"
```

### Tool-Enabled Configurations

#### MCP (Model Context Protocol) Servers
MCP enables agents to use external tools and services:
```bash
# Weather queries
massgen --config @examples/tools/mcp/gemini_mcp_example "What's the weather in Tokyo?"

# Discord integration
massgen --config @examples/tools/mcp/claude_code_discord_mcp_example "Extract latest messages"
```

#### Web Search
For agents with web search capabilities:
```bash
massgen --config @examples/tools/web-search/claude_streamable_http_test "Search for latest news"
```

#### Code Execution
For code interpretation and execution:
```bash
massgen --config @examples/tools/code-execution/multi_agent_playwright_automation \
  "Browse three issues in https://github.com/Leezekun/MassGen and suggest documentation improvements. Include screenshots and suggestions in a website."
```

#### Filesystem Operations
For file manipulation, workspace management, and copy tools:
```bash
# Single agent with enhanced file operations
massgen --config @examples/tools/filesystem/claude_code_single "Analyze this codebase"

# Multi-agent workspace collaboration with copy tools (NEW in v0.0.22)
massgen --config @examples/tools/filesystem/claude_code_context_sharing "Create shared workspace files"
```

### Provider-Specific Examples

Each provider has unique features and capabilities:

#### OpenAI (GPT-5 Series)
```bash
massgen --config @examples/providers/openai/gpt5 "Complex reasoning task"
```

#### Claude
```bash
massgen --config @examples/providers/claude/claude_mcp_example "Creative writing task"
```

#### Gemini
```bash
massgen --config @examples/providers/gemini/gemini_mcp_example "Research task"
```

#### Local Models
```bash
massgen --config @examples/providers/local/lmstudio "Run with local model"
```

### Pre-Configured Teams

Teams are specialized multi-agent setups for specific domains:

#### Creative Teams
```bash
massgen --config @examples/teams/creative/creative_team "Write a story"
```

#### Research Teams
```bash
massgen --config @examples/teams/research/research_team "Analyze market trends"
```

#### Development Teams
```bash
massgen --config @examples/teams/development/zai_coding_team "Build a web app"
```

## Configuration File Format

### Single Agent
```yaml
agent:
  id: "agent_name"
  backend:
    type: "provider_type"
    model: "model_name"
    # Additional backend settings
  system_message: "Agent instructions"

ui:
  display_type: "rich_terminal"
  logging_enabled: true
```

### Multi-Agent
```yaml
agents:
  - id: "agent1"
    backend:
      type: "provider1"
      model: "model1"
    system_message: "Agent 1 role"

  - id: "agent2"
    backend:
      type: "provider2"
      model: "model2"
    system_message: "Agent 2 role"

ui:
  display_type: "rich_terminal"
  logging_enabled: true
```

### MCP Server Configuration
```yaml
backend:
  type: "provider"
  model: "model_name"
  mcp_servers:
    server_name:
      type: "stdio"
      command: "command"
      args: ["arg1", "arg2"]
      env:
        KEY: "${ENV_VAR}"
```

## Finding the Right Configuration

1. **New Users**: Start with `basic/single/` or `basic/multi/`
2. **Need Tools**: Check `tools/` subdirectories for specific capabilities
3. **Specific Provider**: Look in `providers/` for your provider
4. **Complex Tasks**: Use pre-configured `teams/`

## Environment Variables

Most configurations use environment variables for API keys:so
- Set up your `.env` file based on `.env.example`
- Provider-specific keys: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.
- MCP server keys: `DISCORD_BOT_TOKEN`, `BRAVE_API_KEY`, etc.

## Release History & Examples

### v0.1.10 - Latest
**New Features:** Framework Interoperability Streaming & Docker Enhancements

**Configuration Files:**
- `docker_custom_image.yaml` - Custom Docker image with pre-installed packages
- `docker_github_readonly.yaml` - Docker with read-only GitHub access via gh CLI and git
- `docker_full_dev_setup.yaml` - Full development environment with authentication
- `langgraph_lesson_planner_example.yaml` - LangGraph workflow streaming
- `smolagent_lesson_planner_example.yaml` - SmoLAgent framework streaming
- `Dockerfile.custom-example` - Example Dockerfile for extending MassGen base image

**Key Features:**
- **Framework Interoperability Streaming**: Real-time intermediate step streaming for LangGraph and SmoLAgent with log/output distinction
- **Docker Authentication Restructuring**: Nested `command_line_docker_credentials` with separate `mount` array and `env_vars` array
- **Docker Custom Image Support**: Extend MassGen base image with your own packages via custom Dockerfiles
- **Docker Package Management**: Preinstall packages via `command_line_docker_packages` array before agent execution
- **Parallel Execution Safety**: Instance ID generation for safe parallel execution across all modes
- **MassGen Handbook**: Comprehensive contributor documentation at https://massgen.github.io/Handbook/

**Try It:**
```bash
# Install or upgrade
pip install --upgrade massgen

# LangGraph streaming - watch state graph workflow execution in real-time
# Prerequisites:
#   1. pip install langgraph langchain-openai langchain-core
#   2. OPENAI_API_KEY environment variable must be set
massgen --config @examples/tools/custom_tools/interop/langgraph_lesson_planner_example.yaml \
  "Create a lesson plan for photosynthesis"

# SmoLAgent streaming - see HuggingFace agent reasoning steps live
# Prerequisites:
#   1. pip install smolagents
#   2. OPENAI_API_KEY environment variable must be set
massgen --config @examples/tools/custom_tools/interop/smolagent_lesson_planner_example.yaml \
  "Create a lesson plan for photosynthesis"

# Docker custom image - use your own Docker image with preinstalled packages
# Prerequisites:
#   1. Docker daemon running
#   2. Build the example custom image:
#      docker build -t massgen-custom-test:v1 -f massgen/docker/Dockerfile.custom-example .
uv run massgen --config @examples/configs/tools/code-execution/docker_custom_image.yaml \
  "Verify custom packages: sklearn, matplotlib, seaborn, ipython, black, vim, htop, tree"

# Docker with GitHub authentication - read-only repository access
# Prerequisites:
#   1. Docker daemon running
#   2. Already logged in: gh auth login (or set GITHUB_TOKEN)
#   3. Build the Docker image: bash massgen/docker/build.sh
uv run massgen --config @examples/configs/tools/code-execution/docker_github_readonly.yaml \
  "Test to see the most recent issues in the massgen/MassGen repo with the github cli"
```

### v0.1.9
**New Features:** Session Management & Computer Use Tools

**Configuration Files:**
- `claude_computer_use_example.yaml` - Claude-specific computer use and browser automation
- `gemini_computer_use_example.yaml` - Gemini-specific computer use with screenshot analysis
- `computer_use_browser_example.yaml` - Lightweight browser automation focused on specific tasks
- `grok4_gpt5_gemini_mcp_filesystem_test_with_claude_code.yaml` - Multi-turn session with MCP filesystem

**Key Features:**
- **Session Management System**: Resume multi-turn conversations with complete state restoration across CLI invocations
- **Computer Use Tools**: Automate browsers and desktop using Claude and Gemini APIs with Playwright integration
- **Fuzzy Model Matching**: Type approximate model names to find exact matches (e.g., "sonnet" → "claude-sonnet-4-5-20250929")
- **Six New Backends**: Cerebras AI, Together AI, Fireworks AI, Groq, OpenRouter, Moonshot (Kimi)
- **Enhanced Memory**: Improved memory update logic focusing on actionable patterns and technical insights

**Try It:**
```bash
# Install or upgrade
pip install --upgrade massgen

# Browser automation with Claude
# Prerequisites:
#   1. Set ANTHROPIC_API_KEY environment variable
#   2. Playwright installed: pip install playwright && playwright install
#   3. Virtual display setup (Xvfb) for desktop control
massgen --config @examples/tools/custom_tools/claude_computer_use_example "Search for Python documentation on the web"

# Browser automation with Gemini
# Prerequisites:
#   1. Set GOOGLE_API_KEY in your .env file
#   2. Install Playwright: pip install playwright
#   3. Install browsers: playwright install
#   4. Install Google GenAI SDK: pip install google-genai
massgen --config @examples/tools/custom_tools/gemini_computer_use_example "Navigate to GitHub and search for MassGen repository"

# Interactive model selection with fuzzy matching
massgen  # Run the interactive config builder with smart model search
```

### v0.1.8
**New Features:** Automation Mode & DSPy Integration

**Configuration Files:**
- `three_agents_dspy_enabled.yaml` - Three-agent setup with DSPy paraphrasing
- `massgen_runs_massgen.yaml` - Meta-coordination configuration
- `massgen_suggests_to_improve_massgen.yaml` - Autonomous MassGen experiments

**Key Features:**
- **Automation Mode**: Clean structured output (~10 lines vs 250-3,000+) for LLM agents with `--automation` flag
- **DSPy Integration**: Question paraphrasing with three strategies (diverse/balanced/conservative) for multi-agent diversity
- **Meta-Coordination**: MassGen running MassGen for self-improvement workflows
- **Status Monitoring**: Real-time `status.json` updated every 2 seconds with phase tracking and voting results

**Try It:**
```bash
# DSPy question paraphrasing for multi-agent diversity
massgen --config @examples/basic/multi/three_agents_dspy_enabled "Explain the differences between transformer architecture and recurrent neural networks"

# Automation mode - clean output for LLM agents
massgen --automation --config @examples/tools/todo/example_task_todo "Create a simple HTML page about Bob Dylan"

# Meta-coordination - MassGen running MassGen
massgen --config @examples/meta/massgen_runs_massgen "Run a MassGen experiment to create a webpage about Bob Dylan"
```

### v0.1.7
**New Features:** Agent Task Planning & Background Execution

**Configuration Files:**
- `example_task_todo.yaml` - Task planning with dependency management
- `background_shell_demo.yaml` - Background command execution demo

**Key Features:**
- **Agent Task Planning**: MCP-based planning tools with task dependencies and status tracking
- **Background Shell Execution**: Persistent shell sessions for long-running commands
- **Preemption Coordination**: Interrupt coordination without full restart

**Try It:**
```bash
# Agent task planning for complex multi-step projects
massgen --config @examples/configs/tools/todo/example_task_todo.yaml "Create a website about Bob Dylan"

# Background shell execution for parallel long-running commands
uv run massgen --config massgen/configs/tools/code-execution/background_shell_demo.yaml "Run three experiments in parallel using background shell commands: test sorting algorithms (bubble, quick, merge) on arrays of size 10000. Compare their execution times."
```

### v0.1.6
**New Features:** Framework Interoperability & Backend Refactoring

**Configuration Files:**
- `ag2_lesson_planner_example.yaml` - AG2 nested chat as custom tool (supports streaming)
- `langgraph_lesson_planner_example.yaml` - LangGraph workflows integrated as tools
- `agentscope_lesson_planner_example.yaml` - AgentScope agent system integration
- `openai_assistant_lesson_planner_example.yaml` - OpenAI Assistants as tools
- `smolagent_lesson_planner_example.yaml` - HuggingFace SmoLAgent integration
- `ag2_and_langgraph_lesson_planner.yaml` - Multi-framework collaboration (AG2 + LangGraph)
- `ag2_and_openai_assistant_lesson_planner.yaml` - AG2 + OpenAI Assistants combination
- `two_models_with_tools_example.yaml` - Multiple models with custom tools

**Key Features:**
- **Framework Interoperability**: Use agents from external frameworks (AG2, LangGraph, AgentScope, OpenAI Assistants, SmoLAgent) as MassGen tools
- **Streaming Support**: AG2 supports streaming; other frameworks return complete results
- **Configuration Validator**: Pre-flight YAML validation with detailed error messages
- **Unified Tool Execution**: ToolExecutionConfig dataclass for consistent tool handling
- **Gemini Simplification**: Major backend cleanup reducing codebase by 1,598 lines

**Try It:**
```bash
# Use AG2 agents for lesson planning (supports streaming)
# Requirements: pip install pyautogen, OPENAI_API_KEY must be set
massgen --config massgen/configs/tools/custom_tools/ag2_lesson_planner_example.yaml "Create a lesson plan for photosynthesis"

# Use LangGraph workflows as tools
# Requirements: pip install langgraph langchain-openai langchain-core, OPENAI_API_KEY must be set
massgen --config massgen/configs/tools/custom_tools/langgraph_lesson_planner_example.yaml "Create a lesson plan for photosynthesis"

# Use AgentScope multi-agent framework as tools
# Requirements: pip install agentscope, OPENAI_API_KEY must be set
massgen --config massgen/configs/tools/custom_tools/agentscope_lesson_planner_example.yaml "Create a lesson plan for photosynthesis"

# Use OpenAI Assistants API as tools
# Requirements: pip install openai, OPENAI_API_KEY must be set
massgen --config massgen/configs/tools/custom_tools/openai_assistant_lesson_planner_example.yaml "Create a lesson plan for photosynthesis"

# Use SmolAgent (HuggingFace) as tools
# Requirements: pip install smolagents, OPENAI_API_KEY must be set
massgen --config massgen/configs/tools/custom_tools/smolagent_lesson_planner_example.yaml "Create a lesson plan for photosynthesis"

# Combine multiple frameworks
# Requirements: pip install pyautogen langgraph langchain-openai langchain-core, OPENAI_API_KEY must be set
massgen --config massgen/configs/tools/custom_tools/ag2_and_langgraph_lesson_planner.yaml "Create a lesson plan for photosynthesis"
```

### v0.1.5
**New Features:** Memory System with Semantic Retrieval

**Configuration Files:**
- `gpt5mini_gemini_context_window_management.yaml` - Multi-agent with automatic context compression
- `gpt5mini_gemini_research_to_implementation.yaml` - Research-to-implementation workflow (featured in case study)
- `gpt5mini_high_reasoning_gemini.yaml` - High reasoning agents with memory integration
- `gpt5mini_gemini_baseline_research_to_implementation.yaml` - Baseline research workflow
- `single_agent_compression_test.yaml` - Testing context compression behavior

**Key Features:**
- **Long-Term Memory**: Semantic storage via mem0 with vector database integration
- **Context Compression**: Automatic compression when approaching token limits
- **Cross-Agent Sharing**: Agents learn from each other's experiences
- **Session Management**: Memory persistence across conversations

**Try it:**
```bash
# Install or upgrade
pip install --upgrade massgen

# Multi-agent collaboration with context compression
massgen --config @examples/memory/gpt5mini_gemini_context_window_management \
  "Analyze the MassGen codebase comprehensively. Create an architecture document that explains: (1) Core components and their responsibilities, (2) How different modules interact, (3) Key design patterns used, (4) Main entry points and request flows. Read > 30 files to build a complete understanding."

# Research-to-implementation workflow with memory persistence
# Prerequisites: Start Qdrant and crawl4ai Docker containers
docker run -d -p 6333:6333 -p 6334:6334 \
  -v $(pwd)/.massgen/qdrant_storage:/qdrant/storage:z qdrant/qdrant
docker run -d -p 11235:11235 --name crawl4ai --shm-size=1g unclecode/crawl4ai:latest

# Session 1 - Research phase:
massgen --config @examples/memory/gpt5mini_gemini_research_to_implementation \
  "Use crawl4ai to research the latest multi-agent AI papers and techniques from 2025. Focus on: coordination mechanisms, voting strategies, tool-use patterns, and architectural innovations."

# Session 2 - Implementation analysis (continue in same session):
# "Based on the multi-agent research from earlier, which techniques should we implement in MassGen to make it more state-of-the-art? Consider MassGen's current architecture and what would be most impactful."
```

→ See [Multi-Turn Persistent Memory Case Study](../../docs/source/examples/case_studies/multi-turn-persistent-memory.md) for detailed analysis

```bash
# Test automatic context compression
massgen --config @examples/memory/single_agent_compression_test \
  "Analyze the MassGen codebase comprehensively. Create an architecture document that explains: (1) Core components and their responsibilities, (2) How different modules interact, (3) Key design patterns used, (4) Main entry points and request flows. Read > 30 files to build a complete understanding."
```

### v0.1.4
**New Features:** Multimodal Generation Tools, Binary File Protection, Crawl4AI Integration

**Configuration Files:**
- `text_to_image_generation_single.yaml` / `text_to_image_generation_multi.yaml` - Image generation
- `text_to_video_generation_single.yaml` / `text_to_video_generation_multi.yaml` - Video generation
- `text_to_speech_generation_single.yaml` / `text_to_speech_generation_multi.yaml` - Audio generation
- `text_to_file_generation_single.yaml` / `text_to_file_generation_multi.yaml` - Document generation
- `crawl4ai_example.yaml` - Web scraping configuration

**Key Features:**
- **Generation Tools**: Create images, videos, audio, and documents using OpenAI APIs
- **Binary File Protection**: Automatic blocking prevents text tools from reading 40+ binary file types
- **Web Scraping**: Crawl4AI integration for intelligent content extraction
- **Enhanced Security**: Smart tool suggestions guide users to appropriate specialized tools

**Try it:**
```bash
# Generate an image from text
massgen --config @examples/tools/custom_tools/multimodal_tools/text_to_image_generation_single \
  "Please generate an image of a cat in space."

# Generate a video from text
massgen --config @examples/tools/custom_tools/multimodal_tools/text_to_video_generation_single \
  "Generate a 4 seconds video with neon-lit alley at night, light rain, slow push-in, cinematic."

# Generate documents (PDF, DOCX, etc.)
massgen --config @examples/tools/custom_tools/multimodal_tools/text_to_file_generation_single \
  "Please generate a comprehensive technical report about the latest developments in Large Language Models (LLMs)."
```

### v0.1.3
**New Features:** Post-Evaluation Workflow, Custom Multimodal Understanding Tools, Docker Sudo Mode

**Configuration Files:**
- `understand_image.yaml`, `understand_audio.yaml`, `understand_video.yaml`, `understand_file.yaml`

**Key Features:**
- **Post-Evaluation Tools**: Submit and restart capabilities for winning agents
- **Multimodal Understanding**: Analyze images, audio, video, and documents
- **Docker Sudo Mode**: Execute privileged commands in containers

**Try it:**
```bash
# Try multimodal image understanding
massgen --config @examples/tools/custom_tools/multimodal_tools/understand_image \
  "Please summarize the content in this image."
```

### v0.1.2
**New Features:** Intelligent Planning Mode, Claude 4.5 Haiku Support, Grok Web Search Improvements

**Configuration Files:**
- `configs/tools/planning/` - 5 planning mode configurations with selective blocking
- `configs/basic/multi/three_agents_default.yaml` - Updated with Grok-4-fast model

**Documentation:**
- `docs/dev_notes/intelligent_planning_mode.md` - Complete intelligent planning mode guide

**Key Features:**
- **Intelligent Planning Mode**: Automatic analysis of question irreversibility for dynamic MCP tool blocking
- **Selective Tool Blocking**: Granular control over which MCP tools are blocked during planning
- **Enhanced Safety**: Read-only operations allowed, write operations blocked during coordination
- **Latest Models**: Claude 4.5 Haiku support with updated model priorities

**Try it:**
```bash
# Try intelligent planning mode with MCP tools
# (Please read the YAML file for required API keys: DISCORD_TOKEN, OPENAI_API_KEY, etc.)
massgen --config @examples/tools/planning/five_agents_discord_mcp_planning_mode \
  "Check recent messages in our development channel, summarize the discussion, and post a helpful response about the current topic."

# Use latest Claude 4.5 Haiku model
# (Requires ANTHROPIC_API_KEY in .env)
massgen --model claude-haiku-4-5-20251001 \
  "Summarize the latest AI developments"
```

### v0.1.1
**New Features:** Custom Tools System, Voting Sensitivity Controls, Interactive Configuration Builder

**Key Features:**
- Custom tools registration using `ToolManager` class
- Three-tier voting system (lenient/balanced/strict)
- 40+ custom tool examples
- Backend capabilities registry

**Try it:**
```bash
# Try custom tools with agents
massgen --config @examples/tools/custom_tools/claude_custom_tool_example \
  "whats the sum of 123 and 456?"

# Test voting sensitivity controls
massgen --config @examples/voting/gemini_gpt_voting_sensitivity \
  "Your question here"
```

### v0.1.0
**New Features:** PyPI Package Release, Comprehensive Documentation, Interactive Setup Wizard, Enhanced CLI

**Key Features:**
- Official PyPI distribution: `pip install massgen` with global CLI command
- Interactive Setup Wizard with smart defaults for API keys and model selection
- Comprehensive documentation at [docs.massgen.ai](https://docs.massgen.ai/)
- Simplified command syntax: `massgen "question"` with `@examples/` prefix

**Try it:**
```bash
pip install massgen && massgen
massgen --config @examples/basic/multi/three_agents_default "What is 2+2?"
```

### v0.0.32
**New Features:** Docker Execution Mode, MCP Architecture Refactoring, Claude Code Docker Integration

**Configuration Files:**
- `massgen/configs/tools/code-execution/docker_simple.yaml` - Basic single-agent Docker execution
- `massgen/configs/tools/code-execution/docker_multi_agent.yaml` - Multi-agent Docker deployment with isolated containers
- `massgen/configs/tools/code-execution/docker_with_resource_limits.yaml` - Resource-constrained Docker setup with CPU/memory limits
- `massgen/configs/tools/code-execution/docker_claude_code.yaml` - Claude Code with Docker execution and automatic tool management
- `massgen/configs/debug/code_execution/docker_verification.yaml` - Docker setup verification configuration

**Key Features:**
- Docker-based command execution with container isolation preventing host filesystem access
- Persistent state across conversation turns (packages stay installed)
- Multi-agent support with dedicated containers per agent
- Resource limits (CPU, memory) and network isolation modes (none/bridge/host)
- Simplified MCP architecture with MCPClient (renamed from MultiMCPClient)
- Claude Code automatic Bash tool disablement in Docker mode

**Try it:**
```bash
# Docker isolated execution - secure command execution in containers
massgen --config @examples/tools/code-execution/docker_simple \
  "Write a factorial function and test it"

# Multi-agent Docker deployment - each agent in isolated container
massgen --config @examples/tools/code-execution/docker_multi_agent \
  "Build a Flask website about Bob Dylan"

# Claude Code with Docker - automatic tool management
massgen --config @examples/tools/code-execution/docker_claude_code \
  "Build a Flask website about Bob Dylan"

# Resource-limited Docker execution - production-ready setup
massgen --config @examples/tools/code-execution/docker_with_resource_limits \
  "Fetch data from an API and analyze it"
```

### v0.0.31
**New Features:** Universal Code Execution, AG2 Group Chat Integration, Audio & Video Generation Tools

**Configuration Files:**
- `massgen/configs/tools/code-execution/basic_command_execution.yaml` - Universal command execution across all backends
- `massgen/configs/debug/code_execution/command_filtering_whitelist.yaml` - Command execution with whitelist filtering
- `massgen/configs/debug/code_execution/command_filtering_blacklist.yaml` - Command execution with blacklist filtering
- `massgen/configs/tools/code-execution/code_execution_use_case_simple.yaml` - Multi-agent web automation with code execution
- `massgen/configs/ag2/ag2_groupchat.yaml` - Native AG2 group chat with multi-agent conversations
- `massgen/configs/ag2/ag2_groupchat_gpt.yaml` - Mixed MassGen and AG2 agents (GPT-5-nano + AG2 team)
- `massgen/configs/basic/single/single_gpt4o_audio_generation.yaml` - Single agent audio generation with GPT-4o
- `massgen/configs/basic/multi/gpt4o_audio_generation.yaml` - Multi-agent audio generation with GPT-4o
- `massgen/configs/basic/single/single_gpt4o_video_generation.yaml` - Video generation with OpenAI Sora-2

**Case Study:**
- [Universal Code Execution via MCP](../../docs/source/examples/case_studies/universal-code-execution-mcp.md)

**Key Features:**
- Universal `execute_command` tool works across Claude, Gemini, OpenAI (Response API), and Chat Completions providers (Grok, ZAI, etc.)
- Audio tools: text-to-speech, audio transcription, audio generation
- Video tools: text-to-video generation via Sora-2 API
- Code execution in planning mode for safer coordination
- Enhanced file operation tracking and path permission management

**Try it:**
```bash
# Universal code execution - works with any backend
massgen --config @examples/tools/code-execution/basic_command_execution \
  "Write a Python function to calculate factorial and test it"

# AG2 group chat - multi-agent conversations
massgen --config @examples/ag2/ag2_groupchat \
  "Write a Python function to calculate factorial."

# Mixed MassGen + AG2 agents - GPT-5-nano collaborating with AG2 team
massgen --config @examples/ag2/ag2_groupchat_gpt \
  "Write a Python function to calculate factorial."

# Audio generation
massgen --config @examples/basic/single/single_gpt4o_audio_generation \
  "I want to you tell me a very short introduction about Sherlock Homes in one sentence, and I want you to use emotion voice to read it out loud."

# Video generation with Sora-2
massgen --config @examples/basic/single/single_gpt4o_video_generation \
  "Generate a 4 seconds video with neon-lit alley at night, light rain, slow push-in, cinematic."
```

### v0.0.30
**New Features:** Multimodal Audio and Video Support, Claude Agent SDK Update, Qwen API Integration
- `massgen/configs/basic/single/single_openrouter_audio_understanding.yaml` - Audio understanding with OpenRouter
- `massgen/configs/basic/single/single_qwen_video_understanding.yaml` - Video understanding with Qwen API
- `massgen/configs/basic/single/single_gemini2.5pro.yaml` - Gemini 2.5 Pro single agent setup
- `massgen/configs/tools/filesystem/cc_gpt5_gemini_filesystem.yaml` - Claude Code, GPT-5, and Gemini filesystem collaboration
- `massgen/configs/ag2/ag2_case_study.yaml` - AG2 framework integration case study
- `massgen/configs/debug/test_sdk_migration.yaml` - Claude Code SDK migration testing
- Updated from `claude-code-sdk>=0.0.19` to `claude-agent-sdk>=0.0.22`
- Audio/video multimodal support for Chat Completions and Claude backends
- Qwen API provider integration with video understanding capabilities

**Try it:**
```bash
# Audio understanding with OpenRouter
massgen --config @examples/basic/single/single_openrouter_audio_understanding \
  "What is in this recording?"

# Video understanding with Qwen API
massgen --config @examples/basic/single/single_qwen_video_understanding \
  "Describe what happens in this video"

# Multi-agent filesystem collaboration
massgen --config @examples/tools/filesystem/cc_gpt5_gemini_filesystem \
  "Create a comprehensive project with documentation"
```

### v0.0.29
**New Features:** MCP Planning Mode, File Operation Safety, Enhanced MCP Tool Filtering
- `massgen/configs/tools/planning/five_agents_discord_mcp_planning_mode.yaml` - Five agents with Discord MCP in planning mode
- `massgen/configs/tools/planning/five_agents_filesystem_mcp_planning_mode.yaml` - Five agents with filesystem MCP in planning mode
- `massgen/configs/tools/planning/five_agents_notion_mcp_planning_mode.yaml` - Five agents with Notion MCP in planning mode
- `massgen/configs/tools/planning/five_agents_twitter_mcp_planning_mode.yaml` - Five agents with Twitter MCP in planning mode
- `massgen/configs/tools/planning/gpt5_mini_case_study_mcp_planning_mode.yaml` - Planning mode case study configuration
- `massgen/configs/tools/mcp/five_agents_travel_mcp_test.yaml` - Five agents testing travel-related MCP tools
- `massgen/configs/tools/mcp/five_agents_weather_mcp_test.yaml` - Five agents testing weather MCP tools
- `massgen/configs/debug/skip_coordination_test.yaml` - Debug configuration for testing coordination skipping
- New `CoordinationConfig` class with `enable_planning_mode` flag for safer MCP coordination
- New `FileOperationTracker` class for read-before-delete enforcement
- Enhanced PathPermissionManager with operation tracking methods

**Case Study:** [MCP Planning Mode](../../docs/source/examples/case_studies/mcp-planning-mode.md)

**Try it:**
```bash
# Planning mode with filesystem operations
massgen --config @examples/tools/planning/five_agents_filesystem_mcp_planning_mode \
  "Create a comprehensive project structure with documentation"

# Multi-agent weather MCP testing
massgen --config @examples/tools/mcp/five_agents_weather_mcp_test \
  "Compare weather forecasts for New York, London, and Tokyo"

# Planning mode with Twitter integration
massgen --config @examples/tools/planning/five_agents_twitter_mcp_planning_mode \
  "Draft and plan tweet series about AI advancements"
```

### v0.0.28
**New Features:** AG2 Framework Integration, External Agent Backend, Code Execution Support
- `massgen/configs/ag2/ag2_single_agent.yaml` - Basic single AG2 agent setup
- `massgen/configs/ag2/ag2_coder.yaml` - AG2 agent with code execution capabilities
- `massgen/configs/ag2/ag2_coder_case_study.yaml` - Multi-agent setup with AG2 and Gemini
- `massgen/configs/ag2/ag2_gemini.yaml` - AG2-Gemini hybrid configuration
- New `massgen/adapters/` module for external framework integration
- New `ExternalAgentBackend` class bridging MassGen with external frameworks
- Multiple code executor types: LocalCommandLineCodeExecutor, DockerCommandLineCodeExecutor, JupyterCodeExecutor, YepCodeCodeExecutor

**Case Study:** [AG2 Framework Integration](../../docs/source/examples/case_studies/ag2-framework-integration.md)

**Try it:**
```bash
# AG2 single agent with code execution
massgen --config @examples/ag2/ag2_coder \
  "Create a factorial function and calculate the factorial of 8. Show the result?"

# Mixed team: AG2 agent + Gemini agent
massgen --config @examples/ag2/ag2_gemini \
  "what is quantum computing?"

# AG2 case study: Compare AG2 and MassGen (requires external dependency)
uv pip install -e ".[external]"
massgen --config @examples/ag2/ag2_coder_case_study \
  "Output a summary comparing the differences between AG2 (https://github.com/ag2ai/ag2) and MassGen (https://github.com/Leezekun/MassGen) for LLM agents."
```

### v0.0.27
**New Features:** Multimodal Support (Image Processing), File Upload and File Search, Claude Sonnet 4.5
- `massgen/configs/basic/multi/gpt4o_image_generation.yaml` - Multi-agent image generation
- `massgen/configs/basic/multi/gpt5nano_image_understanding.yaml` - Multi-agent image understanding
- `massgen/configs/basic/single/single_gpt4o_image_generation.yaml` - Single agent image generation
- `massgen/configs/basic/single/single_gpt5nano_image_understanding.yaml` - Single agent image understanding
- `massgen/configs/basic/single/single_gpt5nano_file_search.yaml` - File search for document Q&A
- New `stream_chunk` module for multimodal content architecture
- Enhanced `read_multimodal_files` MCP tool for image processing

**Try it:**
```bash
# Image generation with single agent
massgen --config @examples/basic/single/single_gpt4o_image_generation \
  "Generate an image of gray tabby cat hugging an otter with an orange scarf. Limit image size within 5kb."

# Image understanding with multiple agents
massgen --config @examples/basic/multi/gpt5nano_image_understanding \
  "Please summarize the content in this image."

# File search for document Q&A
massgen --config @examples/basic/single/single_gpt5nano_file_search \
  "What is humanity's last exam score for OpenAI Deep Research? Also, provide details about the other models mentioned in the PDF?"
```

### v0.0.26
**New Features:** File Deletion, Protected Paths, File-Based Context Paths
- `massgen/configs/tools/filesystem/gemini_gpt5nano_protected_paths.yaml` - Protected paths configuration
- `massgen/configs/tools/filesystem/gemini_gpt5nano_file_context_path.yaml` - File-based context paths
- `massgen/configs/tools/filesystem/grok4_gpt5_gemini_filesystem.yaml` - Multi-agent filesystem collaboration
- New MCP tools: `delete_file`, `delete_files_batch`, `compare_directories`, `compare_files`

**Try it:**
```bash
# Protected paths - keep reference files safe
massgen --config @examples/tools/filesystem/gemini_gpt5nano_protected_paths \
  "Review the HTML and CSS files, then improve the styling"

# File-based context paths - grant access to specific files
massgen --config @examples/tools/filesystem/gemini_gpt5nano_file_context_path \
  "Analyze the CSS file and make modern improvements"
```

### v0.0.25
**New Features:** Multi-Turn Filesystem Support, SGLang Backend Integration
- `massgen/configs/tools/filesystem/multiturn/two_gemini_flash_filesystem_multiturn.yaml` - Multi-turn with Gemini agents
- `massgen/configs/tools/filesystem/multiturn/grok4_gpt5_claude_code_filesystem_multiturn.yaml` - Three-agent multi-turn
- `massgen/configs/basic/multi/two_qwen_vllm_sglang.yaml` - Mixed vLLM and SGLang deployment
- Automatic `.massgen` directory management for persistent conversation context
- Enhanced path permissions with `will_be_writable` flag and smart exclusion patterns

**Case Study:** [Multi-Turn Filesystem Support](../../docs/source/examples/case_studies/multi-turn-filesystem-support.md)
```bash
# Turn 1 - Initial creation
Turn 1: Make a website about Bob Dylan
# Creates workspace and saves state to .massgen/sessions/

# Turn 2 - Enhancement based on Turn 1
Turn 2: Can you (1) remove the image placeholder? we will not use image directly. (2) generally improve the appearance so it is more engaging, (3) make it longer and add an interactive element
# Note: Unlike pre-v0.0.25, Turn 2 automatically loads Turn 1's workspace state
# Agents can directly access and modify files from the previous turn
```

### v0.0.24
**New Features:** vLLM Backend Support, Backend Utility Modules
- `massgen/configs/basic/multi/three_agents_vllm.yaml` - vLLM with Cerebras and ZAI backends
- `massgen/configs/basic/multi/two_qwen_vllm.yaml` - Dual vLLM agents for testing
- POE provider support for accessing multiple AI models through single platform
- GPT-5-Codex model recognition for enhanced code generation capabilities

**Try it:**
```bash
# Try vLLM backend with local models (requires vLLM server running)
# First start vLLM server: python -m vllm.entrypoints.openai.api_server --model Qwen/Qwen3-0.6B --host 0.0.0.0 --port 8000
massgen --config @examples/basic/multi/two_qwen_vllm \
  "What is machine learning?"
```

### v0.0.23
**New Features:** Backend Architecture Refactoring, Formatter Module
- Major code consolidation with new `base_with_mcp.py` class reducing ~1,932 lines across backends
- Extracted message and tool formatting logic into dedicated `massgen/formatter/` module
- Streamlined chat_completions.py, claude.py, and response.py for better maintainability

### v0.0.22
**New Features:** Workspace Copy Tools via MCP, Configuration Organization
- All configs now organized by provider & use case (basic/, providers/, tools/, teams/)
- Use same configs as v0.0.21 for compatibility, but now with improved performance

**Case Study:** [Advanced Filesystem with User Context Path Support](../../docs/source/examples/case_studies/v0.0.21-v0.0.22-filesystem-permissions.md)
```bash
# Multi-agent collaboration with granular filesystem permissions
massgen --config @examples/tools/filesystem/gpt5mini_cc_fs_context_path "Enhance the website in massgen/configs/resources with: 1) A dark/light theme toggle with smooth transitions, 2) An interactive feature that helps users engage with the blog content (your choice - could be search, filtering by topic, reading time estimates, social sharing, reactions, etc.), and 3) Visual polish with CSS animations or transitions that make the site feel more modern and responsive. Use vanilla JavaScript and be creative with the implementation details."
```

### v0.0.21
**New Features:** Advanced Filesystem Permissions, Grok MCP Integration
- `massgen/configs/tools/mcp/grok3_mini_mcp_example.yaml` - Grok with MCP tools
- `massgen/configs/tools/filesystem/fs_permissions_test.yaml` - Permission-controlled file sharing
- `massgen/configs/tools/filesystem/claude_code_context_sharing.yaml` - Agent workspace sharing

**Try it:**
```bash
# Grok with MCP tools
massgen --config @examples/tools/mcp/grok3_mini_mcp_example \
  "What's the weather in Tokyo?"
```

### v0.0.20
**New Features:** Claude MCP Support with Recursive Execution
- `massgen/configs/tools/mcp/claude_mcp_example.yaml` - Claude with MCP tools
- `massgen/configs/tools/mcp/claude_mcp_test.yaml` - Testing Claude MCP capabilities

**Try it:**
```bash
# Claude with MCP tools
massgen --config @examples/tools/mcp/claude_mcp_example \
  "What's the current weather?"
```

### v0.0.17
**New Features:** OpenAI MCP Integration
- `massgen/configs/tools/mcp/gpt5_nano_mcp_example.yaml` - GPT-5 with MCP tools
- `massgen/configs/tools/mcp/gpt5mini_claude_code_discord_mcp_example.yaml` - Multi-agent MCP

**Try it:**
```bash
# Claude with MCP tools
massgen --config @examples/tools/mcp/gpt5_nano_mcp_example \
  "whats the weather of Tokyo?"
```


### v0.0.16
**New Features:** Unified Filesystem Support with MCP Integration
**Case Study:** [Cross-Backend Collaboration with Gemini MCP Filesystem](../../docs/source/examples/case_studies/unified-filesystem-mcp-integration.md)
```bash
# Gemini and Claude Code agents with unified filesystem via MCP
massgen --config @examples/tools/mcp/gemini_mcp_filesystem_test_with_claude_code "Create a presentation that teaches a reinforcement learning algorithm and output it in LaTeX Beamer format. No figures should be added."
```

### v0.0.15
**New Features:** Gemini MCP Integration
- `massgen/configs/tools/mcp/gemini_mcp_example.yaml` - Gemini with weather MCP
- `massgen/configs/tools/mcp/multimcp_gemini.yaml` - Multiple MCP servers

### v0.0.12 - v0.0.14
**New Features:** Enhanced Logging and Workspace Management
**Case Study:** [Claude Code Workspace Management with Comprehensive Logging](../../docs/source/examples/case_studies/claude-code-workspace-management.md)
```bash
# Multi-agent Claude Code collaboration with enhanced workspace isolation
massgen --config @examples/tools/filesystem/claude_code_context_sharing "Create a website about a diverse set of fun facts about LLMs, placing the output in one index.html file"
```

### v0.0.10
**New Features:** Azure OpenAI Support
- `massgen/configs/providers/azure/azure_openai_single.yaml` - Azure single agent
- `massgen/configs/providers/azure/azure_openai_multi.yaml` - Azure multi-agent

### v0.0.7
**New Features:** Local Model Support with LM Studio
- `massgen/configs/providers/local/lmstudio.yaml` - Local model inference

### v0.0.5
**New Features:** Claude Code Integration
- `massgen/configs/tools/filesystem/claude_code_single.yaml` - Claude Code with dev tools
- `massgen/configs/tools/filesystem/claude_code_flash2.5.yaml` - Multi-agent with Claude Code

## Naming Convention

To improve clarity and discoverability, we follow this naming pattern:

**Format: `{agents}_{features}_{description}.yaml`**

### 1. Agents (who's participating)
- `single-{provider}` - Single agent (e.g., `single-claude`, `single-gemini`)
- `{provider1}-{provider2}` - Two agents (e.g., `claude-gemini`, `gemini-gpt5`)
- `three-mixed` - Three agents from different providers
- `team-{type}` - Specialized teams (e.g., `team-creative`, `team-research`)

### 2. Features (what tools/capabilities)
- `basic` - No special tools, just conversation
- `mcp` - MCP server integration
- `mcp-{service}` - Specific MCP service (e.g., `mcp-discord`, `mcp-weather`)
- `mcp-multi` - Multiple MCP servers
- `websearch` - Web search enabled
- `codeexec` - Code execution/interpreter
- `filesystem` - File operations and workspace management

### 3. Description (purpose/context - optional)
- `showcase` - Demonstration/getting started example
- `test` - Testing configuration
- `research` - Research and analysis tasks
- `dev` - Development and coding tasks
- `collab` - Collaboration example

### Examples
```
# Current → Suggested
three_agents_default.yaml → three-mixed_basic_showcase.yaml
grok3_mini_mcp_example.yaml → single-grok_mcp-weather_test.yaml
claude_code_discord_mcp_example.yaml → single-claude_mcp-discord_demo.yaml
gpt5mini_claude_code_discord_mcp_example.yaml → claude-gpt5_mcp-discord_collab.yaml
```

**Note:** Existing configs maintain their current names for compatibility. New configs should follow this convention.

## Additional Documentation

For detailed setup guides:
- Discord MCP: `docs/DISCORD_MCP_SETUP.md`
- Twitter MCP: `docs/TWITTER_MCP_ENESCINAR_SETUP.md`
- Main README: See repository root for comprehensive documentation
