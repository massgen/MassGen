# Available Example Configurations

MassGen includes a comprehensive library of example configurations demonstrating various features, integrations, and use cases. Use them from any directory with the `@examples/` prefix.

## Usage

```bash
# From any directory
massgen --config @examples/CATEGORY_FILENAME "Your question"

# Example
massgen --config @examples/basic/single/single_gpt5nano "Explain quantum computing"
```

## Categories

### Basic Examples

#### Single Agent

- `basic_single_single_agent` - Simple single agent configuration template for getting started
- `basic_single_single_flash2.5` - Single Gemini 2.5 Flash agent for quick tests and fast responses
- `basic_single_single_gemini2.5pro` - Single Gemini 2.5 Pro agent for more complex reasoning tasks
- `basic_single_single_gpt5nano` - Single GPT-5-nano agent with reasoning, web search, and code execution enabled
- `basic_single_single_gptoss120b` - Single open-source GPT model (120B parameters) for local/privacy-focused use cases

#### Single Agent - Multimodal Capabilities

- `basic_single_single_gpt4o_audio_generation` - GPT-4o agent with audio output generation (text-to-speech)
- `basic_single_single_gpt4o_video_generation` - GPT-4o agent with video generation capabilities
- `basic_single_single_gpt4o_image_generation` - GPT-4o agent with image generation capabilities (DALL-E)
- `basic_single_single_openrouter_audio_understanding` - Audio understanding via OpenRouter integration
- `basic_single_single_qwen_video_understanding` - Qwen model for video analysis and understanding
- `basic_single_single_gpt5nano_file_search` - GPT-5-nano with file search/retrieval capabilities
- `basic_single_single_gpt5nano_image_understanding` - GPT-5-nano with vision capabilities for image analysis

#### Multi-Agent

- `basic_multi_three_agents_default` - Three agents (Gemini 2.5 Flash, GPT-5-nano, Grok-3-mini) collaborating with web search enabled
- `basic_multi_three_agents_opensource` - Three open-source models working together
- `basic_multi_three_agents_vllm` - Three agents using vLLM backend for high-performance inference
- `basic_multi_two_agents_gpt5` - Two GPT-5 agents collaborating on tasks
- `basic_multi_two_agents_gemini` - Two Gemini agents working together
- `basic_multi_two_agents_opensource_lmstudio` - Two open-source models via LM Studio
- `basic_multi_two_qwen_vllm_sglang` - Two Qwen models using vLLM and SGLang backends
- `basic_multi_gemini_4o_claude` - Gemini, GPT-4o, and Claude collaboration
- `basic_multi_gemini_gpt5nano_claude` - Gemini, GPT-5-nano, and Claude collaboration
- `basic_multi_geminicode_4o_claude` - Gemini Code, GPT-4o, and Claude for coding tasks
- `basic_multi_geminicode_gpt5nano_claude` - Gemini Code, GPT-5-nano, and Claude for coding tasks
- `basic_multi_glm_gemini_claude` - GLM, Gemini, and Claude multi-model collaboration
- `basic_multi_gpt5nano_glm_qwen` - GPT-5-nano, GLM, and Qwen working together
- `basic_multi_fast_timeout_example` - Multi-agent setup with short timeout for quick demos

#### Multi-Agent - Multimodal

- `basic_multi_gpt4o_audio_generation` - Multiple agents with audio generation capabilities
- `basic_multi_gpt4o_image_generation` - Multiple agents with image generation capabilities
- `basic_multi_gpt5nano_image_understanding` - Multiple agents with vision capabilities

### Provider-Specific Examples

#### Azure

- `providers_azure_azure_openai_single` - Single agent using Azure OpenAI deployment
- `providers_azure_azure_openai_multi` - Multiple agents using Azure OpenAI

#### OpenAI

- `providers_openai_gpt5` - GPT-5 model configuration
- `providers_openai_gpt5_nano` - GPT-5-nano model configuration

#### Claude

- `providers_claude_claude` - Claude model configuration via Anthropic API

#### Gemini

- `providers_gemini_gemini_gpt5nano` - Gemini and GPT-5-nano hybrid configuration

#### Local

- `providers_local_lmstudio` - Using LM Studio for local model inference

#### Other Providers

- `providers_others_grok_single_agent` - Single Grok agent via xAI API
- `providers_others_zai_coding_team` - Team configuration using ZAI (Zhipu AI) models
- `providers_others_zai_glm45` - GLM-4.5 model via ZAI

### Tool Examples

#### Filesystem Tools

- `tools_filesystem_claude_code_single` - Single Claude Code agent with full filesystem access
- `tools_filesystem_claude_code_flash2.5` - Claude Code with Gemini 2.5 Flash filesystem tools
- `tools_filesystem_claude_code_flash2.5_gptoss` - Claude Code with Gemini Flash and GPT OSS
- `tools_filesystem_claude_code_gpt5nano` - Claude Code with GPT-5-nano filesystem integration
- `tools_filesystem_claude_code_context_sharing` - Demonstrates context sharing between agents with filesystem access
- `tools_filesystem_cc_gpt5_gemini_filesystem` - Claude Code, GPT-5, and Gemini with shared filesystem
- `tools_filesystem_grok4_gpt5_gemini_filesystem` - Grok-4, GPT-5, and Gemini with filesystem tools
- `tools_filesystem_fs_permissions_test` - Testing different filesystem permission levels
- `tools_filesystem_gpt5mini_cc_fs_context_path` - GPT-5-mini and Claude Code with context path configuration
- `tools_filesystem_gemini_gemini_workspace_cleanup` - Two Gemini agents for workspace management
- `tools_filesystem_gemini_gpt5_filesystem_casestudy` - Case study of Gemini and GPT-5 filesystem collaboration
- `tools_filesystem_gemini_gpt5nano_file_context_path` - Gemini and GPT-5-nano with custom context paths
- `tools_filesystem_gemini_gpt5nano_protected_paths` - Demonstrates protected paths feature (read-only files within writable directories)

#### Filesystem Tools - Multi-turn

- `tools_filesystem_multiturn_grok4_gpt5_claude_code_filesystem_multiturn` - Multi-turn conversation with Grok-4, GPT-5, and Claude Code
- `tools_filesystem_multiturn_grok4_gpt5_gemini_filesystem_multiturn` - Multi-turn conversation with Grok-4, GPT-5, and Gemini
- `tools_filesystem_multiturn_two_claude_code_filesystem_multiturn` - Two Claude Code agents in multi-turn mode
- `tools_filesystem_multiturn_two_gemini_flash_filesystem_multiturn` - Two Gemini Flash agents in multi-turn mode

#### Code Execution Tools

- `tools_code-execution_basic_command_execution` - Basic command-line code execution with auto-detected virtual environments
- `tools_code-execution_code_execution_use_case_simple` - Simple use case demonstrating code execution workflow
- `tools_code-execution_multi_agent_playwright_automation` - Multiple agents using Playwright for browser automation

#### MCP (Model Context Protocol) Integration

- `tools_mcp_claude_code_simple_mcp` - Simple MCP server integration with Claude Code
- `tools_mcp_claude_code_discord_mcp_example` - Claude Code with Discord MCP server
- `tools_mcp_claude_code_twitter_mcp_example` - Claude Code with Twitter MCP server
- `tools_mcp_gpt5mini_claude_code_discord_mcp_example` - GPT-5-mini and Claude Code with Discord MCP
- `tools_mcp_claude_mcp_example` - Basic Claude with MCP integration
- `tools_mcp_claude_mcp_test` - Claude MCP testing configuration
- `tools_mcp_gemini_mcp_example` - Basic Gemini with MCP integration
- `tools_mcp_gemini_mcp_test` - Gemini MCP testing configuration
- `tools_mcp_gemini_mcp_filesystem_test` - Gemini with MCP filesystem tools
- `tools_mcp_gemini_mcp_filesystem_test_sharing` - Gemini MCP filesystem with sharing between agents
- `tools_mcp_gemini_mcp_filesystem_test_single_agent` - Single Gemini agent with MCP filesystem
- `tools_mcp_gemini_mcp_filesystem_test_with_claude_code` - Gemini and Claude Code with shared MCP filesystem
- `tools_mcp_gemini_notion_mcp` - Gemini with Notion MCP integration
- `tools_mcp_gpt5_nano_mcp_example` - GPT-5-nano with MCP integration
- `tools_mcp_gpt5_nano_mcp_test` - GPT-5-nano MCP testing configuration
- `tools_mcp_gpt_oss_mcp_example` - Open-source GPT with MCP integration
- `tools_mcp_gpt_oss_mcp_test` - Open-source GPT MCP testing
- `tools_mcp_grok3_mini_mcp_example` - Grok-3-mini with MCP integration
- `tools_mcp_grok3_mini_mcp_test` - Grok-3-mini MCP testing
- `tools_mcp_qwen_api_mcp_example` - Qwen API with MCP integration
- `tools_mcp_qwen_api_mcp_test` - Qwen API MCP testing
- `tools_mcp_qwen_local_mcp_example` - Local Qwen with MCP integration
- `tools_mcp_multimcp_gemini` - Gemini with multiple MCP servers
- `tools_mcp_five_agents_travel_mcp_test` - Five agents with travel planning MCP tools
- `tools_mcp_five_agents_weather_mcp_test` - Five agents with weather data MCP tools

### Team Configurations

#### Creative Teams

- `teams_creative_creative_team` - Storyteller, Editor, and Critic agents optimized for creative writing and storytelling
- `teams_creative_travel_planning` - Specialized team for travel itinerary planning and recommendations

#### Research Teams

- `teams_research_research_team` - Information gatherer, domain expert, and synthesizer for research tasks
- `teams_research_news_analysis` - Team specialized for analyzing news articles and current events
- `teams_research_technical_analysis` - Team focused on technical documentation and code analysis

### AG2 (AutoGen) Integration

- `ag2_ag2_single_agent` - Single AG2 agent demonstrating basic AG2 integration with MassGen
- `ag2_ag2_gemini` - AG2 agent using Gemini backend
- `ag2_ag2_coder` - AG2 coding agent with code execution capabilities
- `ag2_ag2_coder_case_study` - Case study of AG2 coding workflow
- `ag2_ag2_case_study` - Comprehensive AG2 integration case study
- `ag2_ag2_groupchat` - AG2 GroupChat with Coder, Reviewer, and Tester agents (entire group acts as one MassGen agent)
- `ag2_ag2_groupchat_gpt` - AG2 GroupChat using GPT models

### Debug and Testing

- `debug_skip_coordination_test` - Skip coordination rounds for testing final presentation mode
- `debug_test_sdk_migration` - Testing SDK migration features
- `debug_code_execution_command_filtering_blacklist` - Code execution with command blacklist filtering
- `debug_code_execution_command_filtering_whitelist` - Code execution with command whitelist filtering

## Configuration File Naming Convention

When using the `@examples/` prefix:
- Replace directory separators `/` with underscores `_`
- Omit the `.yaml` extension
- Use the format: `@examples/CATEGORY_SUBCATEGORY_FILENAME`

### Examples:

```bash
# Directory: massgen/configs/basic/single/single_gpt5nano.yaml
massgen --config @examples/basic/single/single_gpt5nano "Your prompt"

# Directory: massgen/configs/tools/filesystem/claude_code_single.yaml
massgen --config @examples/tools/filesystem/claude_code_single "Your prompt"

# Directory: massgen/configs/ag2/ag2_groupchat.yaml
massgen --config @examples/ag2/ag2_groupchat "Your prompt"
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

## Getting Started

1. **Simple single agent**: Start with `@examples/basic/single/single_gpt5nano`
2. **Multi-agent collaboration**: Try `@examples/basic/multi/three_agents_default`
3. **Filesystem tools**: Explore `@examples/tools/filesystem/claude_code_single`
4. **Specialized teams**: Use `@examples/teams_research_research_team` for research tasks
5. **Advanced integration**: Check out `@examples/ag2/ag2_groupchat` for AutoGen integration

## Creating Custom Configurations

All example configurations are located in `/Users/ncrispin/GitHubProjects/MassGen/massgen/configs/`. You can:

1. Copy an example that's close to your needs
2. Modify agent configurations, models, and capabilities
3. Save to a custom location
4. Use with `massgen --config /path/to/your/config.yaml`

For detailed configuration options, see the [Configuration Guide](../features/configuration-guide.html).
