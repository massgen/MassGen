# Changelog

All notable changes to MassGen will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.3] - 2025-08-03

### Added
- Complete architecture with foundation release
- Multi-backend support: Claude (Messages API), OpenAI (Responses API), Grok (Chat API), Gemini (Chat API)
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
