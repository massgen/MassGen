# Changelog

All notable changes to MassGen will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
