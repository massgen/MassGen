# Available Example Configurations

MassGen includes a comprehensive library of example configurations demonstrating various features, integrations, and use cases. Use them from any directory with the `@examples/` prefix.

## Quick Start

```bash
# List all available configurations
massgen --list-examples

# Use any configuration from anywhere
massgen --config @examples/CATEGORY/SUBCATEGORY/FILENAME "Your question"
```

## Categories

### Basic Examples

#### Single Agent

Simple configurations to get started with single AI agents.

**`@examples/basic/single/single_agent`**
- Simple single agent configuration template for getting started
```bash
massgen --config @examples/basic/single/single_agent "What is machine learning?"
```

**`@examples/basic/single/single_gpt5nano`**
- Single GPT-5-nano agent with reasoning, web search, and code execution enabled
```bash
massgen --config @examples/basic/single/single_gpt5nano "Calculate the first 100 prime numbers and plot their distribution"
```

**`@examples/basic/single/single_flash2.5`**
- Single Gemini 2.5 Flash agent for quick tests and fast responses
```bash
massgen --config @examples/basic/single/single_flash2.5 "Explain quantum computing in simple terms"
```

**`@examples/basic/single/single_gemini2.5pro`**
- Single Gemini 2.5 Pro agent for more complex reasoning tasks
```bash
massgen --config @examples/basic/single/single_gemini2.5pro "Analyze the economic impact of renewable energy adoption"
```

**`@examples/basic/single/single_gptoss120b`**
- Single open-source GPT model (120B parameters) for local/privacy-focused use cases

#### Single Agent - Multimodal Capabilities

**`@examples/basic/single/single_gpt4o_audio_generation`**
- GPT-4o agent with audio output generation (text-to-speech)
```bash
massgen --config @examples/basic/single/single_gpt4o_audio_generation \
  "I want you to tell me a very short introduction about Sherlock Holmes in one sentence, and I want you to use emotion voice to read it out loud."
```

**`@examples/basic/single/single_gpt4o_video_generation`**
- GPT-4o agent with video generation capabilities
```bash
massgen --config @examples/basic/single/single_gpt4o_video_generation \
  "Generate a 4 seconds video for 'Cherry blossom petals falling in the spring breeze, sunlight filtering through the pink petals creating a soft halo, slow motion capture, aesthetically beautiful and romantic, depth of field effect.'"
```

**`@examples/basic/single/single_gpt4o_image_generation`**
- GPT-4o agent with image generation capabilities (DALL-E)
```bash
massgen --config @examples/basic/single/single_gpt4o_image_generation \
  "Generate an image of gray tabby cat hugging an otter with an orange scarf"
```

**`@examples/basic/single/single_gpt5nano_file_search`**
- GPT-5-nano with file search/retrieval capabilities
```bash
massgen --config @examples/basic/single/single_gpt5nano_file_search \
  "What is humanity's last exam score for OpenAI Deep Research? Also, provide details about the other models mentioned in the PDF?"
```

**`@examples/basic/single/single_gpt5nano_image_understanding`**
- GPT-5-nano with vision capabilities for image analysis
```bash
massgen --config @examples/basic/single/single_gpt5nano_image_understanding \
  "Please summarize the content in this image"
```

**`@examples/basic/single/single_openrouter_audio_understanding`**
- Audio understanding via OpenRouter integration

**`@examples/basic/single/single_qwen_video_understanding`**
- Qwen model for video analysis and understanding

#### Multi-Agent

Multiple AI agents collaborating on tasks.

**`@examples/basic/multi/three_agents_default`** ⭐ Recommended
- Three agents (Gemini 2.5 Flash, GPT-5-nano, Grok-3-mini) collaborating with web search enabled
```bash
massgen --config @examples/basic/multi/three_agents_default \
  "Analyze the pros and cons of renewable energy"
```

**`@examples/basic/multi/gemini_4o_claude`**
- Gemini, GPT-4o, and Claude collaboration
```bash
massgen --config @examples/basic/multi/gemini_4o_claude \
  "What's best to do in Stockholm in October 2025"
```

**`@examples/basic/multi/gemini_gpt5nano_claude`**
- Gemini, GPT-5-nano, and Claude collaboration

**`@examples/basic/multi/two_agents_gpt5`**
- Two GPT-5 agents collaborating on tasks

**`@examples/basic/multi/two_agents_gemini`**
- Two Gemini agents working together

**`@examples/basic/multi/geminicode_4o_claude`**
- Gemini Code, GPT-4o, and Claude for coding tasks

**`@examples/basic/multi/geminicode_gpt5nano_claude`**
- Gemini Code, GPT-5-nano, and Claude for coding tasks

**`@examples/basic/multi/glm_gemini_claude`**
- GLM, Gemini, and Claude multi-model collaboration

**`@examples/basic/multi/gpt5nano_glm_qwen`**
- GPT-5-nano, GLM, and Qwen working together

**`@examples/basic/multi/three_agents_opensource`**
- Three open-source models working together

**`@examples/basic/multi/three_agents_vllm`**
- Three agents using vLLM backend for high-performance inference

**`@examples/basic/multi/two_agents_opensource_lmstudio`**
- Two open-source models via LM Studio

**`@examples/basic/multi/two_qwen_vllm_sglang`**
- Two Qwen models using vLLM and SGLang backends

**`@examples/basic/multi/fast_timeout_example`**
- Multi-agent setup with short timeout for quick demos

#### Multi-Agent - Multimodal

**`@examples/basic/multi/gpt4o_audio_generation`**
- Multiple agents with audio generation capabilities

**`@examples/basic/multi/gpt4o_image_generation`**
- Multiple agents with image generation capabilities

**`@examples/basic/multi/gpt5nano_image_understanding`**
- Multiple agents with vision capabilities

### Provider-Specific Examples

#### Azure

**`@examples/providers/azure/azure_openai_single`**
- Single agent using Azure OpenAI deployment

**`@examples/providers/azure/azure_openai_multi`**
- Multiple agents using Azure OpenAI

#### OpenAI

**`@examples/providers/openai/gpt5`**
- GPT-5 model configuration

**`@examples/providers/openai/gpt5_nano`**
- GPT-5-nano model configuration

#### Claude

**`@examples/providers/claude/claude`**
- Claude model configuration via Anthropic API

#### Gemini

**`@examples/providers/gemini/gemini_gpt5nano`**
- Gemini and GPT-5-nano hybrid configuration

#### Local

**`@examples/providers/local/lmstudio`**
- Using LM Studio for local model inference
```bash
massgen --config @examples/providers/local/lmstudio \
  "Explain machine learning concepts"
```

#### Other Providers

**`@examples/providers/others/grok_single_agent`**
- Single Grok agent via xAI API

**`@examples/providers/others/zai_coding_team`**
- Team configuration using ZAI (Zhipu AI) models

**`@examples/providers/others/zai_glm45`**
- GLM-4.5 model via ZAI

### Tool Examples

#### Code Execution Tools

**`@examples/tools/code-execution/basic_command_execution`**
- Basic command-line code execution with auto-detected virtual environments
```bash
massgen --config @examples/tools/code-execution/basic_command_execution \
  "Write a Python function to calculate factorial and test it"
```

**`@examples/tools/code-execution/multi_agent_playwright_automation`**
- Multiple agents using Playwright for browser automation
```bash
massgen --config @examples/tools/code-execution/multi_agent_playwright_automation \
  "Browse three issues in https://github.com/Leezekun/MassGen and suggest documentation improvements. Include screenshots and suggestions in a website."
```

**`@examples/tools/code-execution/code_execution_use_case_simple`**
- Simple use case demonstrating code execution workflow

**`@examples/tools/code-execution/docker_simple`**
- Basic single-agent Docker execution (NEW in v0.0.32)

**`@examples/tools/code-execution/docker_multi_agent`**
- Multi-agent Docker deployment with isolated containers (NEW in v0.0.32)

**`@examples/tools/code-execution/docker_with_resource_limits`**
- Resource-constrained Docker setup with CPU/memory limits (NEW in v0.0.32)

**`@examples/tools/code-execution/docker_claude_code`**
- Claude Code with Docker execution and automatic tool management (NEW in v0.0.32)

#### Filesystem Tools

**`@examples/tools/filesystem/claude_code_single`**
- Single Claude Code agent with full filesystem access
```bash
massgen --config @examples/tools/filesystem/claude_code_single \
  "Create a Python web scraper and save results to CSV"
```

**`@examples/tools/filesystem/claude_code_context_sharing`**
- Demonstrates context sharing between agents with filesystem access
```bash
massgen --config @examples/tools/filesystem/claude_code_context_sharing \
  "Generate a comprehensive project report with charts and analysis"
```

**`@examples/tools/filesystem/gpt5mini_cc_fs_context_path`**
- GPT-5-mini and Claude Code with context path configuration
```bash
massgen --config @examples/tools/filesystem/gpt5mini_cc_fs_context_path \
  "Enhance the website with: 1) A dark/light theme toggle with smooth transitions, 2) An interactive feature that helps users engage with the blog content, and 3) Visual polish with CSS animations"
```

**`@examples/tools/filesystem/gemini_gpt5nano_protected_paths`**
- Demonstrates protected paths feature (read-only files within writable directories)
```bash
massgen --config @examples/tools/filesystem/gemini_gpt5nano_protected_paths \
  "Review the HTML and CSS files, then improve the styling"
```

**`@examples/tools/filesystem/gemini_gpt5nano_file_context_path`**
- Gemini and GPT-5-nano with custom context paths

**`@examples/tools/filesystem/claude_code_flash2.5`**
- Claude Code with Gemini 2.5 Flash filesystem tools

**`@examples/tools/filesystem/claude_code_gpt5nano`**
- Claude Code with GPT-5-nano filesystem integration

**`@examples/tools/filesystem/cc_gpt5_gemini_filesystem`**
- Claude Code, GPT-5, and Gemini with shared filesystem

**`@examples/tools/filesystem/grok4_gpt5_gemini_filesystem`**
- Grok-4, GPT-5, and Gemini with filesystem tools

**`@examples/tools/filesystem/gemini_gemini_workspace_cleanup`**
- Two Gemini agents for workspace management

**`@examples/tools/filesystem/gemini_gpt5_filesystem_casestudy`**
- Case study of Gemini and GPT-5 filesystem collaboration

**`@examples/tools/filesystem/fs_permissions_test`**
- Testing different filesystem permission levels

#### Filesystem Tools - Multi-turn

**`@examples/tools/filesystem/multiturn/grok4_gpt5_claude_code_filesystem_multiturn`**
- Multi-turn conversation with Grok-4, GPT-5, and Claude Code

**`@examples/tools/filesystem/multiturn/grok4_gpt5_gemini_filesystem_multiturn`**
- Multi-turn conversation with Grok-4, GPT-5, and Gemini

**`@examples/tools/filesystem/multiturn/two_claude_code_filesystem_multiturn`**
- Two Claude Code agents in multi-turn mode

**`@examples/tools/filesystem/multiturn/two_gemini_flash_filesystem_multiturn`**
- Two Gemini Flash agents in multi-turn mode

#### MCP (Model Context Protocol) Integration

**`@examples/tools/mcp/gpt5_nano_mcp_example`**
- GPT-5-nano with MCP integration
```bash
massgen --config @examples/tools/mcp/gpt5_nano_mcp_example \
  "What's the weather forecast for New York this week?"
```

**`@examples/tools/mcp/multimcp_gemini`**
- Gemini with multiple MCP servers (Requires BRAVE_API_KEY in .env)
```bash
massgen --config @examples/tools/mcp/multimcp_gemini \
  "Find the best restaurants in Paris and save the recommendations to a file"
```

**`@examples/tools/mcp/claude_mcp_example`**
- Basic Claude with MCP integration
```bash
massgen --config @examples/tools/mcp/claude_mcp_example \
  "Research and compare weather in Beijing and Shanghai"
```

**`@examples/tools/mcp/gemini_mcp_example`**
- Basic Gemini with MCP integration

**`@examples/tools/mcp/gemini_notion_mcp`**
- Gemini with Notion MCP integration

**`@examples/tools/mcp/gemini_mcp_filesystem_test`**
- Gemini with MCP filesystem tools

**`@examples/tools/mcp/gemini_mcp_filesystem_test_sharing`**
- Gemini MCP filesystem with sharing between agents

**`@examples/tools/mcp/gemini_mcp_filesystem_test_single_agent`**
- Single Gemini agent with MCP filesystem

**`@examples/tools/mcp/gemini_mcp_filesystem_test_with_claude_code`**
- Gemini and Claude Code with shared MCP filesystem

**`@examples/tools/mcp/claude_code_simple_mcp`**
- Simple MCP server integration with Claude Code

**`@examples/tools/mcp/claude_code_discord_mcp_example`**
- Claude Code with Discord MCP server

**`@examples/tools/mcp/claude_code_twitter_mcp_example`**
- Claude Code with Twitter MCP server

**`@examples/tools/mcp/gpt5mini_claude_code_discord_mcp_example`**
- GPT-5-mini and Claude Code with Discord MCP

**`@examples/tools/mcp/grok3_mini_mcp_example`**
- Grok-3-mini with MCP integration

**`@examples/tools/mcp/qwen_api_mcp_example`**
- Qwen API with MCP integration

**`@examples/tools/mcp/qwen_local_mcp_example`**
- Local Qwen with MCP integration

**`@examples/tools/mcp/gpt_oss_mcp_example`**
- Open-source GPT with MCP integration

**`@examples/tools/mcp/five_agents_travel_mcp_test`**
- Five agents with travel planning MCP tools

**`@examples/tools/mcp/five_agents_weather_mcp_test`**
- Five agents with weather data MCP tools

**Testing configs:**
- `@examples/tools/mcp/claude_mcp_test`
- `@examples/tools/mcp/gemini_mcp_test`
- `@examples/tools/mcp/gpt5_nano_mcp_test`
- `@examples/tools/mcp/grok3_mini_mcp_test`
- `@examples/tools/mcp/qwen_api_mcp_test`
- `@examples/tools/mcp/gpt_oss_mcp_test`

#### Planning Mode

**`@examples/tools/planning/five_agents_discord_mcp_planning_mode`**
- Five agents with Discord MCP in planning mode

**`@examples/tools/planning/five_agents_filesystem_mcp_planning_mode`**
- Five agents with filesystem MCP in planning mode
```bash
massgen --config @examples/tools/planning/five_agents_filesystem_mcp_planning_mode \
  "Create a comprehensive project structure with documentation"
```

**`@examples/tools/planning/five_agents_notion_mcp_planning_mode`**
- Five agents with Notion MCP in planning mode

**`@examples/tools/planning/five_agents_twitter_mcp_planning_mode`**
- Five agents with Twitter MCP in planning mode

**`@examples/tools/planning/gpt5_mini_case_study_mcp_planning_mode`**
- Planning mode case study configuration

#### Web Search

- `@examples/tools/web-search/claude_streamable_http_test`
- `@examples/tools/web-search/gemini_streamable_http_test`
- `@examples/tools/web-search/gpt5_mini_streamable_http_test`
- `@examples/tools/web-search/gpt_oss_streamable_http_test`
- `@examples/tools/web-search/grok3_mini_streamable_http_test`
- `@examples/tools/web-search/qwen_api_streamable_http_test`
- `@examples/tools/web-search/qwen_local_streamable_http_test`

### Team Configurations

Pre-configured specialized teams for specific domains.

#### Creative Teams

**`@examples/teams/creative/creative_team`**
- Storyteller, Editor, and Critic agents optimized for creative writing and storytelling
```bash
massgen --config @examples/teams/creative/creative_team \
  "Write a short story about a robot who discovers music"
```

**`@examples/teams/creative/travel_planning`**
- Specialized team for travel itinerary planning and recommendations

#### Research Teams

**`@examples/teams/research/research_team`**
- Information gatherer, domain expert, and synthesizer for research tasks
```bash
massgen --config @examples/teams/research/research_team \
  "Analyze market trends in renewable energy"
```

**`@examples/teams/research/news_analysis`**
- Team specialized for analyzing news articles and current events

**`@examples/teams/research/technical_analysis`**
- Team focused on technical documentation and code analysis

### AG2 (AutoGen) Integration

**`@examples/ag2/ag2_groupchat`** ⭐ Recommended
- AG2 GroupChat with Coder, Reviewer, and Tester agents (entire group acts as one MassGen agent)
```bash
massgen --config @examples/ag2/ag2_groupchat \
  "Write a Python function to calculate factorial"
```

**`@examples/ag2/ag2_groupchat_gpt`**
- AG2 GroupChat using GPT models
```bash
massgen --config @examples/ag2/ag2_groupchat_gpt \
  "Write a Python function to calculate factorial"
```

**`@examples/ag2/ag2_single_agent`**
- Single AG2 agent demonstrating basic AG2 integration with MassGen

**`@examples/ag2/ag2_gemini`**
- AG2 agent using Gemini backend

**`@examples/ag2/ag2_coder`**
- AG2 coding agent with code execution capabilities
```bash
massgen --config @examples/ag2/ag2_coder \
  "Create a factorial function and calculate the factorial of 8. Show the result?"
```

**`@examples/ag2/ag2_coder_case_study`**
- Case study of AG2 coding workflow

**`@examples/ag2/ag2_case_study`**
- Comprehensive AG2 integration case study

### Debug and Testing

- `@examples/debug/skip_coordination_test` - Skip coordination rounds for testing final presentation mode
- `@examples/debug/test_sdk_migration` - Testing SDK migration features
- `@examples/debug/code_execution/command_filtering_blacklist` - Code execution with command blacklist filtering
- `@examples/debug/code_execution/command_filtering_whitelist` - Code execution with command whitelist filtering
- `@examples/debug/code_execution/docker_verification` - Docker setup verification configuration

## Path Format

Use slashes (`/`) in `@examples/` paths to match the actual directory structure:

```bash
# ✅ Correct - use slashes
massgen --config @examples/basic/single/single_gpt5nano "Question"
massgen --config @examples/tools/mcp/multimcp_gemini "Question"
massgen --config @examples/providers/claude/claude "Question"

# ❌ Incorrect - don't use underscores
massgen --config @examples/basic_single_single_gpt5nano "Question"
```

## Key Features Demonstrated

### Backend Integrations
- OpenAI (GPT-4o, GPT-5, GPT-5-nano, GPT-5-mini)
- Anthropic Claude (Claude 3, Claude Code)
- Google Gemini (2.5 Flash, 2.5 Pro, Gemini Code)
- xAI Grok (Grok-3-mini, Grok-4)
- Azure OpenAI
- OpenRouter
- Zhipu AI (GLM models)
- Qwen (local and API)
- Open-source models via LM Studio, vLLM, SGLang

### Capabilities
- Reasoning (o1/o3-style extended thinking)
- Web search integration
- Code execution and interpretation
- Filesystem operations (read/write/edit)
- Audio generation and understanding
- Image generation and understanding
- Video understanding
- Model Context Protocol (MCP) integrations

### Advanced Features
- Multi-agent collaboration and orchestration
- Context sharing between agents
- Protected paths (read-only protection)
- Custom context paths
- Multi-turn conversations
- AG2 (AutoGen) integration
- GroupChat patterns
- Workspace isolation and snapshot management
- Docker execution mode with container isolation

## Getting Started

1. **Simple single agent**: Start with `@examples/basic/single/single_gpt5nano`
2. **Multi-agent collaboration**: Try `@examples/basic/multi/three_agents_default`
3. **Filesystem tools**: Explore `@examples/tools/filesystem/claude_code_single`
4. **Specialized teams**: Use `@examples/teams/research/research_team` for research tasks
5. **Advanced integration**: Check out `@examples/ag2/ag2_groupchat` for AutoGen integration

## Creating Custom Configurations

All example configurations are located in `massgen/configs/`. You can:

1. Copy an example that's close to your needs
2. Modify agent configurations, models, and capabilities
3. Save to a custom location
4. Use with `massgen --config /path/to/your/config.yaml`

For detailed configuration options, see the [Configuration Guide](https://docs.massgen.ai).
