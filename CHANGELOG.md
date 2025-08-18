# Changelog

All notable changes to MassGen will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.8] - 2025-08-18

### Added
- **Timeout Management System**: Timeout capabilities for better control and time management
  - New `TimeoutConfig` class for configuring timeout settings at different levels
  - Orchestrator-level timeout with graceful fallback
  - Added `fast_timeout_example.yaml` configuration demonstrating conservative timeout settings
  - Test suite for timeout mechanisms in `test_timeout.py`
  - Timeout indicators in Rich Terminal Display showing remaining time
- **Enhanced Display Features**: Improved visual feedback and user experience
  - Optimized message display formatting for better readability
  - Enhanced status indicators for timeout warnings and fallback notifications
  - Improved coordination UI with better multi-agent status tracking

### Fixed
- **Display Optimization**: Multiple improvements to message rendering
  - Fixed message display synchronization issues
  - Optimized terminal display refresh rates
  - Improved handling of concurrent agent outputs
  - Better formatting for multi-line responses
- **Configuration Management**: Enhanced robustness of configuration loading
  - Fixed import ordering issues in CLI module
  - Improved error handling for missing configurations
  - Better validation of timeout settings

### Changed
- **Orchestrator Architecture**: Simplified and enhanced timeout implementation
  - Refactored timeout handling to be more efficient and maintainable
  - Improved graceful degradation when timeouts occur
  - Better integration with frontend displays for timeout notifications
  - Enhanced error messages for timeout scenarios
- **Code Cleanup**: Removed deprecated configurations and improved code organization
  - Removed obsolete `two_agents_claude_code` configuration
  - Cleaned up unused imports and redundant code
  - Reformatted files for better consistency
- **CLI Enhancements**: Improved command-line interface functionality
  - Better timeout configuration parsing
  - Enhanced error reporting for timeout scenarios
  - Improved help documentation for timeout settings

### Technical Details
- **Commits**: 18 commits including various optimizations and bug fixes
- **Files Modified**: 13+ files across orchestrator, frontend, configuration, and test modules
- **Key Features**: Timeout management system with graceful fallback, enhanced display optimizations
- **New Configuration**: `fast_timeout_example.yaml` for time-conscious usage
- **Contributors**: @qidanrui @Leezekun @sonichi @voidcenter

## [0.0.7] - 2025-08-15

### Added
- **Local Model Support**: Complete integration with LM Studio for running open-weight models locally
  - New `lmstudio.py` backend with automatic server management
  - Automatic model downloading and loading capabilities
  - Zero-cost reporting for local model usage
- **Extended Provider Support**: Enhanced ChatCompletionsBackend to support multiple providers
  - Cerebras AI, Together AI, Fireworks AI, Groq, Nebius AI Studio, OpenRouter
  - Provider-specific environment variable detection
  - Automatic provider name inference from base URLs
- **New Configuration Files**: Added configurations for local and hybrid model setups
  - `lmstudio.yaml`: Single agent configuration for LM Studio
  - `two_agents_opensource_lmstudio.yaml`: Hybrid setup with GPT-5 and local Qwen model
  - `gpt5nano_glm_qwen.yaml`: Three-agent setup combining Cerebras, ZAI GLM-4.5, and local Qwen
  - Updated `three_agents_opensource.yaml` for open-source model combinations

### Fixed
- **Backend Stability**: Improved error handling across all backend systems
  - Fixed API key resolution and client initialization
  - Enhanced provider name detection and configuration
  - Resolved streaming issues in ChatCompletionsBackend
- **Documentation**: Corrected references and updated model naming conventions
  - Fixed GPT model references in documentation diagrams
  - Updated case study file naming consistency

### Changed
- **Backend Architecture**: Refactored ChatCompletionsBackend for better extensibility
  - Improved provider registry and configuration management
  - Enhanced logging and debugging capabilities
  - Streamlined message processing and tool handling
- **Dependencies**: Added new requirements for local model support
  - Added `lmstudio==1.4.1` for LM Studio Python SDK integration
- **Documentation Updates**: Enhanced documentation for local model usage
  - Updated environment variables documentation
  - Added setup instructions for LM Studio integration
  - Improved backend configuration examples

### Technical Details
- **Commits**: 16 commits including merge pull requests #80 and #100
- **Files Modified**: 17+ files across backend, configuration, documentation, and CLI modules
- **New Dependencies**: LM Studio SDK (`lmstudio==1.4.1`)
- **Contributors**: @qidanrui @sonichi @Leezekun @praneeth999 @voidcenter

## [0.0.6] - 2025-08-13

### Added
- **GLM-4.5 Model Support**: Integration with ZhipuAI's GLM-4.5 model family
  - Added GLM-4.5 backend support in `chat_completions.py`
  - New configuration file `zai_glm45.yaml` for GLM-4.5 agent setup
  - Updated `zai_coding_team.yaml` with GLM-4.5 integration
  - Added GLM-4.5 model mappings and environment variable support
- **Enhanced Reasoning Display**: Improved reasoning presentation for GLM models
  - Added reasoning start and completion indicators in frontend displays
  - Enhanced coordination UI to show reasoning progress
  - Better visual formatting for reasoning states in terminal display

### Fixed
- **Claude Code Backend**: Updated default allowed tools configuration
  - Fixed default tools setup in `claude_code.py` backend

### Changed
- **Documentation Updates**: Updated README.md with GLM-4.5 support information
  - Added GLM-4.5 to supported models list
  - Updated environment variables documentation for ZhipuAI integration
  - Enhanced model comparison and configuration examples
- **Configuration Management**: Enhanced agent configuration system
  - Updated `agent_config.py` with GLM-4.5 support
  - Improved CLI integration for GLM models
  - Better model parameter handling in utils.py

### Technical Details
- **Commits**: 6 major commits including merge pull requests #90 and #94
- **Files Modified**: 12+ files across backend, frontend, configuration, and documentation
- **New Dependencies**: ZhipuAI GLM-4.5 model integration
- **Contributors**: @Stanislas0 @qidanrui @sonichi @Leezekun @voidcenter

## [0.0.5] - 2025-08-11

### Added
- **Claude Code Integration**: Complete integration with Claude Code CLI backend
  - New `claude_code.py` backend with streaming capabilities and tool support
  - Support for Claude Code SDK with stateful conversation management
  - JSON tool call functionality and proper tool result handling
  - Session management with append system prompt support
- **New Configuration Files**: Added Claude Code specific YAML configurations
  - `claude_code_single.yaml`: Single agent setup using Claude Code backend
  - `claude_code_flash2.5.yaml`: Multi-agent setup with Claude Code and Gemini Flash 2.5
  - `claude_code_flash2.5_gptoss.yaml`: Multi-agent setup with Claude Code, Gemini Flash 2.5, and GPT-OSS
- **Test Coverage**: Added test suite for Claude Code functionality
  - `test_claude_code_orchestrator.py`: orchestrator testing
  - Backend-specific test coverage for Claude Code integration

### Fixed
- **Backend Stability**: Multiple critical bug fixes across all backend systems
  - Fixed parameter handling in `chat_completions.py`, `claude.py`, `gemini.py`, `grok.py`
  - Resolved response processing issues in `response.py`
  - Improved error handling and client existence validation
- **Tool Call Processing**: Enhanced tool call parsing and execution
  - Deduplicated tool call parsing logic across backends
  - Fixed JSON tool call functionality and result formatting
  - Improved builtin tool result handling in streaming contexts
- **Message Handling**: Resolved system message processing issues
  - Fixed SystemMessage to StreamChunk conversion
  - Proper session info extraction from system messages
  - Cleaned up message formatting and display consistency
- **Frontend Display**: Fixed output formatting and presentation
  - Improved rich terminal display formatting
  - Better coordination UI integration and multi-turn conversation display
  - Enhanced status message display with proper newline handling

### Changed
- **Code Architecture**: Significant refactoring and cleanup across the codebase
  - Renamed and consolidated backend files for consistency
  - Simplified chat agent architecture and removed redundant code
  - Streamlined orchestrator logic with improved error handling
- **Configuration Management**: Updated and cleaned up configuration files
  - Updated agent configuration with Claude Code support
- **Backend Infrastructure**: Enhanced backend parameter handling
  - Improved stateful conversation management across all backends
  - Better integration with orchestrator for multi-agent coordination
  - Enhanced streaming capabilities with proper chunk processing
- **Documentation**: Updated project documentation
  - Added Claude Code setup instructions in README
  - Updated backend architecture documentation
  - Improved reasoning and streaming integration notes

### Technical Details
- **Commits**: 50+ commits since version 0.0.4
- **Files Modified**: 25+ files across backend, configuration, frontend, and test modules
- **Major Components Updated**: Backend systems, orchestrator, frontend display, configuration management
- **New Dependencies**: Added Claude Code SDK integration
- **Contributors**: @qidanrui @randombet @sonichi

## [0.0.4] - 2025-08-08

### Added
- **GPT-5 Series Support**: Full support for OpenAI's GPT-5 model family
  - GPT-5: Full-scale model with advanced capabilities
  - GPT-5-mini: Efficient variant for faster responses
  - GPT-5-nano: Lightweight model for resource-constrained deployments
- **New Model Parameters**: Introduced GPT-5 specific configuration options
  - `text.verbosity`: Control response detail level (low/medium/high)
  - `reasoning.effort`: Configure reasoning depth (minimal/medium/high)
  - Note: reasoning parameter is mutually exclusive with web search capability
- **Configuration Files**: Added dedicated YAML configurations
  - `gpt5.yaml`: Three-agent setup with GPT-5, GPT-5-mini, and GPT-5-nano
  - `gpt5_nano.yaml`: Three GPT-5-nano agents with different reasoning levels
- **Extended Model Support**: Added GPT-5 series to model mappings in utils.py
- **Reasoning for All Models**: Extended reasoning parameter support beyond GPT-5 models

### Fixed
- **Tool Output Formatting**: Added proper newline formatting for provider tool outputs
  - Web search status messages now display on new lines
  - Code interpreter status messages now display on new lines
  - Search query display formatting improved
- **YAML Configuration**: Fixed configuration syntax in GPT-5 related YAML files
- **Backend Response Handling**: Multiple bug fixes in response.py for proper parameter handling

### Changed
- **Documentation Updates**: 
  - Updated README.md to highlight GPT-5 series support
  - Changed example commands to use GPT-5 models
  - Added new backend configuration examples with GPT-5 specific parameters
  - Updated models comparison table to show GPT-5 as latest OpenAI model
- **Parameter Handling**: Improved backend parameter validation
  - Temperature parameter now excluded for GPT-5 series models (like o-series)
  - Max tokens parameter now excluded for GPT-5 series models
  - Added conditional logic for GPT-5 specific parameters (text, reasoning)
- **Version Number**: Updated to 0.0.4 in massgen/__init__.py

### Technical Details
- **Commits**: 9 commits since version 0.0.3
- **Files Modified**: 6 files (response.py, utils.py, README.md, __init__.py, and 2 new config files)
- **Contributors**: @qidanrui @sonichi @voidcenter @JeffreyCh0 @praneeth999

## [0.0.3] - 2025-08-03

### Added
- Complete architecture with foundation release
- Multi-backend support: Claude (Messages API), Gemini (Chat API), Grok (Chat API), OpenAI (Responses API)
- Builtin tools: Code execution and web search with streaming results
- Async streaming with proper chat agent interfaces and tool result handling
- Multi-agent orchestration with voting and consensus mechanisms
- Real-time frontend displays with multi-region terminal UI
- CLI with file-based YAML configuration and interactive mode
- Proper StreamChunk architecture separating tool_calls from builtin_tool_results
- Multi-turn conversation support with dynamic context reconstruction
- Chat interface with orchestrator supporting async streaming
- Case study configurations and specialized YAML configs
- Claude backend support with production-ready multi-tool API and streaming
- OpenAI builtin tools support for code execution and web search streaming

### Fixed
- Grok backend testing and compatibility issues
- CLI multi-turn conversation display with coordination UI integration
- Claude streaming handler with proper tool argument capture
- CLI backend parameter passing with proper ConfigurableAgent integration

### Changed
- Restructured codebase with new architecture
- Improved message handling and streaming capabilities
- Enhanced frontend features and user experience

## [0.0.1] - Initial Release

### Added
- Basic multi-agent system framework
- Support for OpenAI, Gemini, and Grok backends
- Simple configuration system
- Basic streaming display
- Initial logging capabilities
