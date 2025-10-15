# Changelog

All notable changes to MassGen will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Recent Releases

**v0.1.0 (October 2025)** - PyPI Package & Documentation
Official PyPI release with enhanced documentation and installation via `pip install massgen`.

**v0.0.32 (October 2025)** - Docker Execution Mode
Isolated command execution in Docker containers with resource limits and multi-agent support.

**v0.0.31 (October 2025)** - Code Execution, AG2 Integration, Multimodal
MCP-based command execution across all backends, AG2 framework integration, and audio/video generation.

---

## [0.1.0] - 2025-10-15 (PyPI Release)

### Added
- **PyPI Package Release**: Official MassGen package available on PyPI for easy installation via pip
- **Enhanced Documentation**: Comprehensive Sphinx documentation with improved structure and clarity
  - Rebuilt documentation with v0.1.0 version numbers
  - Improved backend capabilities table with split multimodal columns
  - Enhanced explanations for multimodal capabilities (Both, Understanding, Generation)
  - Updated homepage with v0.1.0 features

### Changed
- **Documentation Updates**: Major documentation improvements for PyPI release
  - Updated version numbers across all documentation files
  - Clarified multimodal capability terminology
  - Enhanced backend configuration guides

### Technical Details
- **Major Focus**: PyPI distribution and documentation improvements
- **Contributors**: @ncrispino @qidanrui @sonichi @Henry-811 and the MassGen team

## [0.0.32] - 2025-10-15

### Added
- **Docker Execution Mode**: Isolated command execution via Docker containers
  - New `DockerManager` class for persistent container lifecycle management
  - Container-based isolation with volume mounts for workspace and context paths
  - Configurable resource limits (CPU, memory) and network isolation modes (none/bridge/host)
  - Multi-agent support with dedicated containers per agent
  - Build script and comprehensive Dockerfile for massgen/mcp-runtime image
  - Enable via `command_line_execution_mode: "docker"` in agent configuration
  - Test suite in `test_code_execution.py` covering Docker and local execution modes

### Changed
- **Code Execution via MCP**: Extended v0.0.31's execute_command tool with Docker execution mode
  - Docker environment detection for automatic image verification
  - Local command execution remains available via `command_line_execution_mode: "local"`
  - Enhanced security layers for both local and Docker modes

- **Claude Code Backend**: Docker mode integration and MCP tool handling improvements
  - Automatic Bash tool disablement when Docker mode is enabled
  - MCP tool auto-permission support via `can_use_tool` hook
  - MCP server configuration format conversion (list to dict format)
  - System message enhancements to prevent git repository confusion in Docker

- **MCP Tools Architecture**: Major refactoring for simplicity and maintainability
  - Renamed `MultiMCPClient` to `MCPClient` reflecting simplified architecture
  - Removed deprecated `converters.py` module (275 lines removed)
  - Streamlined `client.py` with 1,029 lines removed through consolidation
  - Standardized type hints and module-level constants in `backend_utils.py`
  - Simplified exception handling in `exceptions.py` and security validation in `security.py`

### Fixed
- **Configuration Examples**: Improved configuration organization and usability
  - Renamed configuration files for better discoverability
  - Fixed CPU limits in example configurations to be runnable
  - Reverted gemini_mcp_test.yaml for consistency

- **Orchestrator Timeout and Cleanup**: Enhanced timeout handling and resource management
  - Improved timeout mechanisms for better reliability
  - Better cleanup of resources after orchestration sessions

### Documentations, Configurations and Resources

- **Docker Documentation**: New comprehensive Docker mode guide in `massgen/docker/README.md`
  - Complete Docker setup and usage documentation
  - Build scripts and Dockerfile with detailed comments
  - Security considerations for container-based execution
  - Resource management and isolation strategies

- **Code Execution Design**: Updated `CODE_EXECUTION_DESIGN.md` with Docker architecture details

- **New Configuration Files**: Added 5 Docker-specific example configurations
  - `docker_simple.yaml`: Basic single-agent Docker execution
  - `docker_multi_agent.yaml`: Multi-agent Docker deployment
  - `docker_with_resource_limits.yaml`: Resource-constrained Docker setup
  - `docker_claude_code.yaml`: Claude Code with Docker execution
  - `docker_verification.yaml`: Docker setup verification configuration

### Technical Details
- **Commits**: 17 commits including Docker execution, MCP refactoring, and Claude Code enhancements
- **Files Modified**: 32 files across backend, filesystem manager, MCP tools, and configurations
- **Major Features**: Docker execution mode, MCP architecture simplification, Claude Code Docker integration
- **New Module**: `_docker_manager.py` with DockerManager class (438 lines)
- **Dependencies Updated**: `docker>=7.0.0` added as optional dependency
- **Contributors**: @ncrispino @praneeth999 @qidanrui @sonichi @Henry-811 and the MassGen team

## [0.0.31] - 2025-10-14

### Added
- **Code Execution via MCP**: Universal command execution through MCP
  - New `execute_command` MCP tool enabling bash/shell execution across Claude, Gemini, OpenAI (Response API), and Chat Completions providers (Grok, ZAI, etc.)
  - AG2-inspired security with multi-layer protection: dangerous command sanitization, command filtering (whitelist/blacklist), PathPermissionManager hooks, path validation, timeout enforcement
  - Command filtering with regex patterns for whitelist/blacklist control
  - New MCP server `_code_execution_server.py` with subprocess-based local execution
  - Test coverage in `test_code_execution.py` covering basics, path validation, command sanitization, output handling, and virtual environment detection

- **Audio Generation Tools**: Text-to-speech and audio transcription capabilities via OpenAI APIs
  - New `generate_and_store_audio_no_input_audios` tool for generating audio from text using gpt-4o-audio-preview model
  - New `generate_text_with_input_audio` tool for transcribing audio files using OpenAI's Transcription API
  - New `convert_text_to_speech` tool for converting text to speech with gpt-4o-mini-tts model
  - Support for multiple voices (alloy, echo, fable, onyx, nova, shimmer, coral, sage) and audio formats (wav, mp3, opus, aac, flac)
  - Optional speaking instructions for tone and style control in TTS
  - Automatic workspace organization with timestamp-based filenames

- **Video Generation Tools**: Text-to-video generation via OpenAI's Sora-2 API
  - New `generate_and_store_video_no_input_images` tool for generating videos from text prompts
  - Support for Sora-2 model with configurable video duration
  - Asynchronous video generation with progress monitoring
  - Automatic MP4 format with workspace storage and organization

### Changed
- **AG2 Group Chat Support**: Enhanced AG2 adapter with native multi-agent group chat coordination
  - New group chat manager integration with AG2's `GroupChat` and `GroupChatManager`
  - Configurable speaker selection modes: auto (LLM-based), round_robin, manual
  - Support for nested conversations and workflow tools within group chat sessions
  - Automatic tool registration/unregistration for clean group chat lifecycle
  - Enhanced adapter architecture with group chat state management
  - Better agent reinitialization and termination logic for multi-turn group conversations
  - Test coverage in `test_ag2_adapter.py` and `test_ag2_utils.py`

- **File Operation Tracker**: Enhanced with auto-generated file exemptions
  - New `_is_auto_generated()` method to identify build artifacts and cache files
  - Prevents permission errors when agents clean up after running tests or builds

- **Path Permission Manager**: Added execute_command tool validation
  - Added `execute_command` to command_tools set for bash-like security validation
  - PreToolUse hooks now validate execute_command calls for dangerous patterns and path restrictions
  - Enhanced test coverage with 93 new test lines for command tool validation

- **Message Templates**: Added code execution result guidance
  - New system message guidance when `enable_command_execution=True` instructing agents to explain test results and command outputs in their answers
  - Better agent behavior for explaining what was tested and what results mean

### Documentations, Configurations and Resources

- **Code Execution Design Documentation**: Comprehensive technical design document
  - `CODE_EXECUTION_DESIGN.md`: Design doc covering architecture, security layers, implementation plan, virtual environment support, and future Docker enhancements

- **New Configuration Files**: Added 8 new example configurations
  - **AG2 Group Chat**: `ag2_groupchat.yaml`, `ag2_groupchat_gpt.yaml`
  - **Code Execution**: `basic_command_execution.yaml`, `code_execution_use_case_simple.yaml`, `command_filtering_whitelist.yaml`, `command_filtering_blacklist.yaml`,
  - **Audio Generation**: `single_gpt4o_audio_generation.yaml`, `gpt4o_audio_generation.yaml`
  - **Video Generation**: `single_gpt4o_video_generation.yaml`

### Technical Details
- **Commits**: 29 commits including AG2 group chat, code execution, audio/video generation, and enhancements
- **Files Modified**: 39 files with 3,649 insertions and 154 deletions
- **Major Features**: AG2 group chat, universal code execution via MCP, audio/video generation tools
- **New Tests**: `test_ag2_adapter.py`, `test_ag2_utils.py`, `test_code_execution.py`
- **Contributors**: @Eric-Shang @ncrispino @qidanrui @sonichi @Henry-811 and the MassGen team

## [0.0.30] - 2025-10-10

### Changed
- **Multimodal Support - Audio and Video Processing**: Extended v0.0.27's image-only multimodal foundation
  - Audio file support with WAV and MP3 formats for Chat Completions and Claude backends
  - Video file support with MP4, AVI, MOV, WEBM formats for Chat Completions and Claude backends
  - Audio/video path parameters (`audio_path`, `video_path`) for local files and HTTP/HTTPS URLs
  - Base64 encoding for local audio/video files with automatic MIME type detection
  - Configurable media file size limits (default 64MB, configurable via `media_max_file_size_mb`)
  - New audio/video content formatters in `_chat_completions_formatter.py` and `_claude_formatter.py`
  - Enhanced `base_with_mcp.py` with 340+ lines of multimodal content processing

- **Claude Code Backend SDK Update**: Updated to newer Agent SDK package
  - Migrated from `claude-code-sdk>=0.0.19` to `claude-agent-sdk>=0.0.22`
  - Updated internal SDK classes: `ClaudeCodeOptions` → `ClaudeAgentOptions`
  - Enhanced bash tool permission validation in `PathPermissionManager`
  - Improved system message handling with SDK preset support
  - New bash/shell/exec tool detection for dangerous operation prevention

- **Chat Completions Backend Enhancement**: Qwen API provider integration
  - Added Qwen API support to existing Chat Completions provider ecosystem
  - New `QWEN_API_KEY` environment variable support
  - Qwen-specific configuration examples for video understanding

### Fixed
- **Planning Mode Configuration**: Fixed crash when configuration lacks `coordination_config`
  - Added null check in `orchestrator.py` to prevent AttributeError
  - Improved graceful handling of missing planning mode configuration

- **Claude Code System Message Handling**: Resolved system message processing issues
  - Fixed system message extraction and formatting in `claude_code.py`
  - Better integration with Agent SDK for message handling

- **AG2 Adapter Import Ordering**: Resolved import sequence issues
  - Fixed import statements in `adapters/utils/ag2_utils.py`
  - Pre-commit isort formatting corrections

### Documentations, Configurations and Resources

- **Case Studies**: Comprehensive documentation for v0.0.28 and v0.0.29 features
  - `ag2-framework-integration.md`: AG2 adapter system and external framework integration
  - `mcp-planning-mode.md`: MCP Planning Mode design and implementation guide

- **New Configuration Files**: Added 7 new example configurations
  - `ag2/ag2_case_study.yaml`: AG2 framework integration case study configuration
  - `filesystem/cc_gpt5_gemini_filesystem.yaml`: Claude Code, GPT-5, and Gemini filesystem collaboration
  - `basic/single/single_gemini2.5pro.yaml`: Gemini 2.5 Pro single agent setup
  - `basic/single/single_openrouter_audio_understanding.yaml`: Audio understanding with OpenRouter
  - `basic/single/single_qwen_video_understanding.yaml`: Video understanding with Qwen API
  - `debug/test_sdk_migration.yaml`: Claude Code SDK migration testing

### Technical Details
- **Commits**: 20 commits including multimodal enhancements, Claude Code SDK migration, and documentation
- **Files Modified**: 25 files with 2,501 insertions and 84 deletions
- **Major Features**: Audio/video multimodal support, Claude Code Agent SDK migration, Qwen API integration
- **Dependencies Updated**: `anthropic>=0.61.0`, `claudecode>=0.0.12`
- **Contributors**: @ncrispino @praneeth999 @qidanrui @sonichi @Henry-811 and the MassGen team

## [0.0.29] - 2025-10-08

### Added
- **MCP Planning Mode**: New coordination strategy for irreversible MCP actions
  - New `CoordinationConfig` class with `enable_planning_mode` flag
  - Agents plan without executing during coordination, winning agent executes during final presentation
  - Orchestrator and frontend coordination UI support
  - Support for multiple backends: Response API, Chat Completions, and Gemini
  - Test suites in `test_mcp_blocking.py` and `test_gemini_planning_mode.py`

- **File Operation Tracker**: Read-before-delete enforcement for safer file operations
  - New `FileOperationTracker` class in `filesystem_manager/_file_operation_tracker.py`
  - Prevents agents from deleting files they haven't read first
  - Tracks read files and agent-created files (created files exempt from read requirement)
  - Directory deletion validation with comprehensive error messages

- **Path Permission Manager Enhancements**: Integration with FileOperationTracker
  - Added read/write/delete operation tracking methods to `PathPermissionManager`
  - Integration with `FileOperationTracker` for read-before-delete enforcement
  - Enhanced delete validation for files and batch operations
  - Extended test coverage in `test_path_permission_manager.py`

### Changed
- **Message Templates**: Improved multi-agent coordination guidance
  - Added `has_irreversible_actions` support for context path write access
  - Explicit temporary workspace path structure display for better agent understanding
  - Task handling priority hierarchy and simplified new_answer requirements
  - Unified evaluation guidance

- **MCP Tool Filtering**: Enhanced multi-level filtering capabilities
  - Combined backend-level and per-MCP-server tool filtering
  - MCP-server-specific `allowed_tools` can override backend-level settings
  - Merged `exclude_tools` from both backend and MCP server configurations

- **Backend Planning Mode Support**: Extended planning mode to multiple backends
  - Enhanced `base.py`, `response.py`, `chat_completions.py`, and `gemini.py`
  - Gemini backend now supports planning mode with session-based tool execution
  - Planning mode support across all major backend types


### Fixed
- **Circuit Breaker Logic**: Enhanced MCP server initialization in `base_with_mcp.py`
- **Final Answer Context**: Improved workspace copying when no new answer is provided
- **Multi-turn MCP Usage**: Addressed non-use of MCP in certain scenarios and improved final answer autonomy
- **Configuration Issues**: Updated Playwright automation configuration and fixed agent IDs

### Documentations, Configurations and Resources

- **MCP Planning Mode Examples**: 5 new planning mode configurations in `tools/planning/`
  - `five_agents_discord_mcp_planning_mode.yaml`: Discord MCP with planning mode (5 agents)
  - `five_agents_filesystem_mcp_planning_mode.yaml`: Filesystem MCP with planning mode
  - `five_agents_notion_mcp_planning_mode.yaml`: Notion MCP with planning mode (5 agents)
  - `five_agents_twitter_mcp_planning_mode.yaml`: Twitter MCP with planning mode (5 agents)
  - `gpt5_mini_case_study_mcp_planning_mode.yaml`: Case study configuration

- **MCP Example Configurations**: New example configurations for MCP integration in `tools/mcp/`
  - `five_agents_travel_mcp_test.yaml`: Travel planning MCP example (5 agents)
  - `five_agents_weather_mcp_test.yaml`: Weather service MCP example (5 agents)

- **Debug Configurations**: New debugging and testing utilities
  - `skip_coordination_test.yaml`: Test configuration for skipping coordination rounds

- **Documentation Updates**: Enhanced project documentation
  - Updated `permissions_and_context_files.md` in `backend/docs/` with file operation tracking details
  - Updated README with AG2 as optional installation and uv tool instructions

### Technical Details
- **Commits**: 23+ commits including planning mode, file operation tracking, and MCP enhancements
- **Files Modified**: 43 files across agent config, backend, filesystem manager, MCP tools, and configurations
- **Major Features**: MCP planning mode, FileOperationTracker, enhanced permissions, MCP tool filtering
- **New Tests**: `test_mcp_blocking.py`, `test_gemini_planning_mode.py` for planning mode validation
- **Contributors**: @ncrispino @franklinnwren @qidanrui @sonichi @praneeth999 and the MassGen team

## [0.0.28] - 2025-10-06

### Added
- **AG2 Framework Integration**: Complete adapter system for external agent frameworks
  - New `massgen/adapters/` module with base adapter architecture (`base.py`, `ag2_adapter.py`)
  - Support for AG2 ConversableAgent and AssistantAgent types
  - Code execution capabilities with multiple executor types: LocalCommandLineCodeExecutor, DockerCommandLineCodeExecutor, JupyterCodeExecutor, YepCodeCodeExecutor
  - Function/tool calling support for AG2 agents
  - Async execution with `a_generate_reply` for autonomous operation
  - AG2 utilities module for agent setup and API key management (`adapters/utils/ag2_utils.py`)

- **External Agent Backend**: New backend type for integrating external frameworks
  - New `ExternalAgentBackend` class supporting adapter registry pattern
  - Bridge between MassGen orchestration and external agent frameworks via adapters
  - Framework-specific configuration extraction and validation
  - Currently supports AG2 with extensible architecture for future frameworks

- **AG2 Test Suite**: Comprehensive test coverage for AG2 integration
  - `test_ag2_adapter.py`: AG2 adapter functionality tests
  - `test_agent_adapter.py`: Base adapter interface tests
  - `test_external_agent_backend.py`: External backend integration tests

### Fixed
- **MCP Circuit Breaker Logic**: Enhanced initialization for MCP servers
  - Improved circuit breaker state management in `base_with_mcp.py`
  - Better error handling during MCP server initialization

### Documentations, Configurations and Resources

- **AG2 Configuration Examples**: New YAML configurations demonstrating AG2 integration
  - `ag2/ag2_single_agent.yaml`: Basic single AG2 agent setup
  - `ag2/ag2_coder.yaml`: AG2 agent with code execution
  - `ag2/ag2_coder_case_study.yaml`: Multi-agent setup with AG2 and Gemini
  - `ag2/ag2_gemini.yaml`: AG2-Gemini hybrid configuration

- **Design Documentation**: Enhanced multi-source agent integration design
  - Updated `MULTI_SOURCE_AGENT_INTEGRATION_DESIGN.md` with AG2 adapter architecture

### Technical Details
- **Commits**: 12 commits including AG2 integration, testing, and configuration examples
- **Files Modified**: 18 files with 1,423 insertions and 71 deletions
- **Major Features**: AG2 framework integration, external agent backend, adapter architecture
- **New Module**: `massgen/adapters/` with AG2 support
- **Contributors**: @Eric-Shang @praneeth999 @qidanrui @sonichi @Henry-811 and the MassGen team

## [0.0.27] - 2025-10-03

### Added
- **Multimodal Support - Image Processing**: Foundation for multimodal content processing
  - New `stream_chunk` module with base classes for multimodal content (`base.py`, `text.py`, `multimodal.py`)
  - Support for image input and output in conversation messages
  - Image generation and understanding capabilities for multi-agent workflows
  - Multimodal content structure supporting images, audio, video, and documents (architecture ready)

- **File Upload and File Search**: Extended backend capabilities for document operations
  - File upload support integrated into Response backend via `_response_api_params_handler.py`
  - File search functionality for enhanced context retrieval and Q&A
  - Vector store management for file search operations
  - Cleanup utilities for uploaded files and vector stores

- **Workspace Tools Enhancements**: Extended MCP-based workspace management
  - Added `read_multimodal_files` tool for reading images as base64 data with MIME type

- **Claude Sonnet 4.5 Support**: Added latest Claude model to model mappings
  - Support for Claude Sonnet 4.5 (`claude-sonnet-4-5-20250929`)
  - Updated model registry in `utils.py`

### Changed
- **Message Architecture Refactoring**: Extracted and refactored messaging system for multimodal support
  - Extracted `StreamChunk` classes into dedicated module (`massgen/stream_chunk/`)
  - Enhanced message templates for image generation workflows
  - Improved orchestrator and chat agent for multimodal message handling

- **Backend Enhancements**: Extended backends for multimodal and file operations
  - Enhanced `response.py` with image generation, understanding, and saving capabilities
  - Improved `base_with_mcp.py` with image handling for MCP-based workflows
  - New `api_params_handler` module for centralized parameter management including file uploads
  - Better streaming and error handling for multimodal content

- **Frontend Display Improvements**: Enhanced terminal UI for multimodal content
  - Refactored `rich_terminal_display.py` for rendering images in terminal
  - Improved message formatting and visual presentation

### Documentations, Configurations and Resources

- **New Configuration Files**: Added multimodal and enhanced filesystem examples
  - `gpt4o_image_generation.yaml`: Multi-agent image generation setup
  - `gpt5nano_image_understanding.yaml`: Multi-agent image understanding configuration
  - `single_gpt4o_image_generation.yaml`: Single agent image generation
  - `single_gpt5nano_image_understanding.yaml`: Single agent image understanding
  - `single_gpt5nano_file_search.yaml`: Single agent file search example
  - `grok4_gpt5_gemini_filesystem.yaml`: Enhanced filesystem configuration
  - Updated `claude_code_gpt5nano.yaml` with improved filesystem settings

- **Case Study Documentation**: New `multi-turn-filesystem-support.md` demonstrating v0.0.25 multi-turn capabilities with Bob Dylan website example

- **Presentation Materials**: New `applied-ai-summit.html` presentation with updated build scripts and call-to-action slides

- **Example Resources**: New `multimodality.jpg` for testing multimodal capabilities under `massgen/configs/resources/v0.0.27-example/`


### Technical Details
- **Major Features**: Image processing foundation, StreamChunk architecture, file upload/search, workspace multimodal tools
- **New Module**: `massgen/stream_chunk/` with base, text, and multimodal classes
- **Contributors**: @qidanrui @sonichi @praneeth999 @ncrispino @Henry-811 and the MassGen team

## [0.0.26] - 2025-10-01

### Added
- **File Deletion and Workspace Management**: New MCP tools for workspace file operations
  - New workspace deletion tools: `delete_file`, `delete_files_batch` for managing workspace files
  - New comparison tools: `compare_directories`, `compare_files` for file diffing
  - Consolidated `_workspace_tools_server.py` replacing previous `_workspace_copy_server.py`
  - Improved workspace cleanup mechanisms for multi-turn sessions
  - Proper permission checks for all file operations

- **File-Based Context Paths**: Support for single file access without exposing entire directories
  - Context paths can now be individual files, not just directories
  - Better control over agent access to specific reference files
  - Enhanced path validation distinguishing between file and directory contexts

- **Protected Paths Feature**: Prevent agents from modifying specific reference files
  - Protected paths within write-permitted context paths
  - Agents can read but not modify protected files


### Changed
- **Code Refactoring**: Improved module structure and import paths
  - Moved utility modules from `backend/utils/` to top-level `massgen/` directory
  - Relocated `api_params_handler`, `formatter`, and `filesystem_manager` modules
  - Simplified import paths and improved code discoverability
  - Better separation of concerns between backend-specific and shared utilities

- **Path Permission Manager**: Major enhancements to permission system
  - Enhanced `will_be_writable` logic for better permission state tracking
  - Improved path validation distinguishing between context paths and workspace paths
  - Comprehensive test coverage in `test_path_permission_manager.py`
  - Better handling of edge cases and nested path scenarios

### Fixed
- **Path Permission Edge Cases**: Resolved various permission checking issues
  - Fixed file context path validation logic
  - Corrected protected path matching behavior
  - Improved handling of nested paths and symbolic links
  - Better error handling for non-existent paths

### Documentations, Configurations and Resources

- **Example Resources**: Added v0.0.26 example resources for testing new features
  - Bob Dylan themed website with multiple pages and styles
  - Additional HTML, CSS, and JavaScript examples
  - Resources organized under `massgen/configs/resources/v0.0.26-example/`

- **Design Documentation**: Added comprehensive design documentation
  - New `file_deletion_and_context_files.md` documenting file deletion and context file features
  - Updated `permissions_and_context_files.md` with v0.0.26 features
  - Added detailed examples for protected paths and file context paths

- **Release Workflow Documentation**: Added comprehensive release example checklist
  - Step-by-step guide for release preparation in `docs/workflows/release_example_checklist.md`
  - Best practices for testing new features

- **Configuration Examples**: New configuration examples for v0.0.26 features
  - `gemini_gpt5nano_protected_paths.yaml`: Protected paths example
  - `gemini_gpt5nano_file_context_path.yaml`: File-based context paths example
  - `gemini_gemini_workspace_cleanup.yaml`: Workspace cleanup example

### Technical Details
- **Commits**: 20+ commits including file deletion tools, protected paths, and refactoring
- **Files Modified**: 46 files with 4,343 insertions and 836 deletions
- **Major Features**: File deletion tools, protected paths, file-based context paths, enhanced CLI prompts
- **New Tools**: `delete_file`, `delete_files_batch`, `compare_directories`, `compare_files` MCP tools
- **Contributors**: @praneeth999 @ncrispino @qidanrui @sonichi @Henry-811 and the MassGen team

## [0.0.25] - 2025-09-29

### Added
- **Multi-Turn Filesystem Support**: Complete implementation for persistent filesystem context across conversation turns
  - Automatic session management when `session_storage` is configured (no flag needed)
  - Persistent workspace management across conversation turns with `.massgen` directory
  - Workspace snapshot preservation and restoration between turns
  - Support for maintaining file context and modifications throughout multi-turn sessions
  - New configuration examples: `two_gemini_flash_filesystem_multiturn.yaml`, `grok4_gpt5_gemini_filesystem_multiturn.yaml`, `grok4_gpt5_claude_code_filesystem_multiturn.yaml`
  - Design documentation in `multi_turn_filesystem_design.md`

- **SGLang Backend Integration**: Added SGLang support to inference backend alongside existing vLLM
  - New SGLang server support with default port 30000 and `SGLANG_API_KEY` environment variable
  - SGLang-specific parameters support (e.g., `separate_reasoning` for guided generation)
  - Auto-detection between vLLM and SGLang servers based on configuration
  - New configuration `two_qwen_vllm_sglang.yaml` for mixed server deployments
  - Unified `InferenceBackend` class replacing separate `vllm.py` implementation
  - Updated documentation renamed from `vllm_implementation.md` to `inference_backend.md`

- **Enhanced Path Permission System**: New exclusion patterns and validation improvements
  - Added `DEFAULT_EXCLUDED_PATTERNS` for common directories (.git, node_modules, .venv, etc.)
  - New `will_be_writable` flag for better permission state tracking
  - Improved path validation with different handling for context vs workspace paths
  - Enhanced test coverage in `test_path_permission_manager.py`

### Changed
- **CLI Enhancements**: Major improvements to command-line interface
  - Enhanced logging with configurable log levels and file output
  - Improved error handling and user feedback

- **System Prompt Improvements**: Refined agent system prompts for better performance
  - Clearer instructions for file context handling
  - Better guidance for multi-turn conversations
  - Improved prompt templates for filesystem operations

- **Documentation Updates**: Comprehensive documentation improvements
  - Updated README with clearer installation instructions

### Fixed
- **Filesystem Manager**: Resolved workspace and permission issues
  - Fixed warnings for non-existent temporary workspaces
  - Better cleanup of old workspaces
  - Fixed relative path issues in workspace copy operations

- **Configuration Issues**: Multiple configuration fixes
  - Fixed multi-agent configuration templates
  - Fixed code generation prompts for consistency

### Technical Details
- **Commits**: 30+ commits including multi-turn filesystem, SGLang integration, and bug fixes
- **Files Modified**: 33 files with 3,188 insertions and 642 deletions
- **Major Features**: Multi-turn filesystem support, unified vLLM/SGLang backend, enhanced permissions
- **New Backend**: SGLang integration alongside existing vLLM support
- **Contributors**: @praneeth999 @ncrispino @qidanrui @sonichi @Henry-811 and the MassGen team

## [0.0.24] - 2025-09-26

### Added
- **vLLM Backend Support**: Complete integration with vLLM for high-performance local model serving
  - New `vllm.py` backend supporting VLLM's OpenAI-compatible API
  - Configuration examples in `three_agents_vllm.yaml`
  - Comprehensive documentation in `vllm_implementation.md`
  - Support for large-scale model inference with optimized performance

- **POE Provider Support**: Extended ChatCompletions backend to support POE (Platform for Open Exploration)
  - Added POE provider integration for accessing multiple AI models through a single platform
  - Seamless integration with existing ChatCompletions infrastructure

- **GPT-5-Codex Model Recognition**: Added GPT-5-Codex to model registry
  - Extended model mappings in `utils.py` to recognize gpt-5-codex as a valid OpenAI model

- **Backend Utility Modules**: Major refactoring for improved modularity
  - New `api_params_handler` module for centralized API parameter management
  - New `formatter` module for standardized message formatting across backends
  - New `token_manager` module for unified token counting and management
  - Extracted filesystem utilities into dedicated `filesystem_manager` module

### Changed
- **Backend Consolidation**: Significant code refactoring and simplification
  - Refactored `chat_completions.py` and `response.py` with cleaner API handler patterns
  - Moved filesystem management from `mcp_tools` to `backend/utils/filesystem_manager`
  - Improved separation of concerns with specialized handler modules
  - Enhanced code reusability across different backend implementations

- **Documentation Updates**: Improved documentation structure
  - Moved `permissions_and_context_files.md` to backend docs
  - Added multi-source agent integration design documentation
  - Updated filesystem permissions case study for v0.0.21 and v0.0.22 features

- **CI/CD Pipeline**: Enhanced automated release process
  - Updated auto-release workflow for better reliability
  - Improved GitHub Actions configuration

- **Pre-commit Configuration**: Updated code quality tools
  - Enhanced pre-commit hooks for better code consistency
  - Updated linting rules for improved code standards

### Fixed
- **Streaming Chunk Processing**: Resolved critical bugs in chunk handling
  - Fixed chunk processing errors in response streaming
  - Improved error handling for malformed chunks
  - Better resilience in stream processing pipeline

- **Gemini Backend Session Management**: Improved cleanup
  - Implemented proper session closure for google-genai aiohttp client
  - Added explicit cleanup of aiohttp sessions to prevent potential resource leaks

### Technical Details
- **Commits**: 35 commits including backend refactoring, vLLM integration, and bug fixes
- **Files Modified**: 50+ files across backend, utilities, configurations, and documentation
- **Major Refactor**: Complete restructuring of backend utilities
- **New Backend**: vLLM integration for high-performance local inference
- **Contributors**: @qidanrui @sonichi @praneeth999 @ncrispino @Henry-811 and the MassGen team

## [0.0.23] - 2025-09-24

### Added
- **Backend Architecture Refactoring**: Major consolidation of MCP functionality
  - New `base_with_mcp.py` base class consolidating common MCP functionality (488 lines)
  - Extracted shared MCP logic from individual backends into unified base class
  - Standardized MCP client initialization and error handling across all backends

- **Formatter Module**: Extracted message and tool formatting logic into dedicated module
  - New `massgen/formatter/` module with specialized formatters
  - `message_formatter.py`: Handles message formatting across backends
  - `tool_formatter.py`: Manages tool call formatting
  - `mcp_tool_formatter.py`: Specialized MCP tool formatting

### Changed
- **Backend Consolidation**: Massive code deduplication across backends
  - Reduced `chat_completions.py` by 700+ lines
  - Reduced `claude.py` by 700+ lines
  - Simplified `response.py` by 468+ lines
  - Total reduction: ~1,932 lines removed across core backend files

### Fixed
- **Coordination Table Display**: Fixed escape key handling on macOS
  - Updated `create_coordination_table.py` and `rich_terminal_display.py`

### Technical Details
- **Commits**: 20+ commits focusing on backend refactoring and infrastructure improvements
- **Files Modified**: 100+ files across backend, documentation, CI/CD, and presentation components
- **Lines Changed**: Net reduction of ~1,932 lines through backend consolidation
- **Major Refactor**: MCP functionality extracted into shared `base_with_mcp.py` base class
- **Contributors**: @qidanrui @ncrispino @Henry-811 and the MassGen team

## [0.0.22] - 2025-09-22

### Added
- **Workspace Copy Tools via MCP**: New file copying capabilities for efficient workspace operations
  - Added `workspace_copy_server.py` with MCP-based file copying functionality (369 lines)
  - Support for copying files and directories between workspaces
  - Efficient handling of large files with streaming operations
  - Testing infrastructure for copy operations

- **Configuration Organization**: Major restructuring of configuration files for better usability
  - New hierarchical structure: `basic/`, `providers/`, `tools/`, `teams/` directories
  - Added comprehensive `README.md` for configuration guide
  - New `BACKEND_CONFIGURATION.md` with detailed backend setup
  - Organized configs by use case and provider for easier navigation
  - Added provider-specific examples (Claude, OpenAI, Gemini, Azure)

- **Enhanced File Operations**: Improved file handling for large-scale operations
  - Clear all temporary workspaces at startup for clean state
  - Enhanced security validation in MCP tools

### Changed

- **Workspace Management**: Optimized workspace operations and path handling
  - Enhanced `filesystem_manager.py` with 193 additional lines
  - Run MCP servers through FastMCP to avoid banner displays

- **Backend Enhancements**: Improved backend capabilities
  - Improved `response.py` with better error handling

### Fixed
- **Write Tool Call Issues**: Resolved large character count problems
  - Fixed write tool call issues when dealing with large character counts

- **Path Resolution Issues**: Resolved various path-related bugs
  - Fixed relative/absolute path workspace issues
  - Improved path validation and normalization

- **Documentation Fixes**: Corrected multiple documentation issues
  - Fixed broken links in case studies
  - Fixed config file paths in documentation and examples
  - Corrected example commands with proper paths

### Technical Details
- **Commits**: 50+ commits including workspace copy, configuration restructuring, and documentation improvements
- **Files Modified**: 90+ files across configs, backend, mcp_tools, and documentation
- **Major Refactoring**: Configuration file reorganization into logical categories
- **New Documentation**: Added 762+ lines of documentation for configs and backends
- **Contributors**: @ncrispino @qidanrui @Henry-811 and the MassGen team

## [0.0.21] - 2025-09-19

### Added
- **Advanced Filesystem Permissions System**: Comprehensive permission management for agent file access
  - New `PathPermissionManager` class for granular permission validation
  - User context paths with configurable READ/WRITE permissions for multi-agent file sharing
  - Test suite for permission validation in `test_path_permission_manager.py`
  - Documentation in `permissions_and_context_files.md` for implementation guide

- **Function Hook Manager**: Per-agent function call permission system
  - Refactored `FunctionHookManager` to be per-agent rather than global
  - Pre-tool-use hooks for validating file operations before execution
  - Support for write permission enforcement during context agent operations
  - Integration with all function-based backends (OpenAI, Claude, Chat Completions)

- **Grok MCP Integration**: Extended MCP support to Grok backend
  - Migrated Grok backend to inherit from Chat Completions backend
  - Full MCP server support for Grok including stdio and HTTP transports
  - Filesystem support through MCP servers

- **New Configuration Files**: Added test and example configurations
  - `grok3_mini_mcp_test.yaml`: Grok MCP testing configuration
  - `grok3_mini_mcp_example.yaml`: Grok MCP usage example
  - `grok3_mini_streamable_http_test.yaml`: Grok HTTP streaming test
  - `grok_single_agent.yaml`: Single Grok agent configuration
  - `fs_permissions_test.yaml`: Filesystem permissions testing configuration

### Changed
- **Backend Architecture**: Unified backend implementations and permission support
  - Grok backend refactored to use Chat Completions backend
  - All backends now support per-agent permission management
  - Enhanced context file support across Claude, Gemini, and OpenAI backends

### Technical Details
- **Commits**: 20+ commits including permission system, Grok MCP, and terminal improvements
- **Files Modified**: 40+ files across backends, MCP tools, permissions, and display modules
- **New Features**: Filesystem permissions, per-agent hooks, Grok MCP via Chat Completions
- **Contributors**: @Eric-Shang @ncrispino @qidanrui @Henry-811 and the MassGen team

## [0.0.20] - 2025-09-17

### Added
- **Claude Backend MCP Support**: Extended MCP (Model Context Protocol) integration to Claude backend
  - Filesystem support through MCP servers (`FilesystemSupport.MCP`) for Claude backend
  - Support for both stdio and HTTP-based MCP servers with Claude Messages API
  - Seamless integration with existing Claude function calling and tool use
  - Recursive execution model allowing Claude to autonomously chain multiple tool calls in sequence without user intervention
  - Enhanced error handling and retry mechanisms for Claude MCP operations

- **MCP Configuration Examples**: New YAML configurations for Claude MCP usage
  - `claude_mcp_test.yaml`: Basic Claude MCP testing with test server
  - `claude_mcp_example.yaml`: Claude MCP integration example
  - `claude_streamable_http_test.yaml`: HTTP transport testing for Claude MCP

- **Documentation**: Enhanced MCP technical documentation
  - `MCP_IMPLEMENTATION_CLAUDE_BACKEND.md`: Complete technical documentation for Claude MCP integration
  - Detailed architecture diagrams and implementation guides

### Changed
- **Backend Enhancements**: Improved MCP support across backends
  - Extended MCP integration from Gemini and Chat Completions to include Claude backend
  - Enhanced error reporting and debugging for MCP operations
  - Added Kimi/Moonshot API key support in Chat Completions backend

### Technical Details
- **New Features**: Claude backend MCP integration with recursive execution model
- **Files Modified**: Claude backend modules (`claude.py`), MCP tools, configuration examples
- **MCP Coverage**: Major backends now support MCP (Claude, Gemini, Chat Completions including OpenAI)
- **Contributors**: @praneeth999 @qidanrui @sonichi @ncrispino @Henry-811 MassGen development team

## [0.0.19] - 2025-09-15

### Added
- **Coordination Tracking System**: Comprehensive tracking of multi-agent coordination events
  - New `coordination_tracker.py` with `CoordinationTracker` class for capturing agent state transitions
  - Event-based tracking with timestamps and context preservation
  - Support for recording answers, votes, and coordination phases
  - New `create_coordination_table.py` utility in `massgen/frontend/displays/` for generating coordination reports

- **Enhanced Agent Status Management**: New enums for better state tracking
  - Added `ActionType` enum in `massgen/utils.py`: NEW_ANSWER, VOTE, VOTE_IGNORED, ERROR, TIMEOUT, CANCELLED
  - Added `AgentStatus` enum in `massgen/utils.py`: STREAMING, VOTED, ANSWERED, RESTARTING, ERROR, TIMEOUT, COMPLETED
  - Improved state machine for agent coordination lifecycle

### Changed
- **Frontend Display Enhancements**: Improved terminal interface with coordination visualization
  - Modified `massgen/frontend/displays/rich_terminal_display.py` to add coordination table display method
  - Added new terminal menu option 'r' to display coordination table
  - Enhanced menu system with better organization of debugging tools
  - Support for rich-formatted tables showing agent interactions across rounds

### Technical Details
- **Commits**: 20+ commits including coordination tracking system and frontend enhancements
- **Files Modified**: 5+ files across coordination tracking, frontend displays, and utilities
- **New Features**: Coordination event tracking with visualization capabilities
- **Contributors**: @ncrispino @qidanrui @sonichi @a5507203 @Henry-811 and the MassGen team

## [0.0.18] - 2025-09-12

### Added
- **Chat Completions MCP Support**: Extended MCP (Model Context Protocol) integration to ChatCompletions-based backends
  - Full MCP support for all Chat Completions providers (Cerebras AI, Together AI, Fireworks AI, Groq, Nebius AI Studio, OpenRouter)
  - Filesystem support through MCP servers (`FilesystemSupport.MCP`) for Chat Completions backend
  - Cross-provider function calling compatibility enabling seamless MCP tool execution across different providers
  - Universal MCP server compatibility with existing stdio and streamable-http transports

- **New MCP Configuration Examples**: Added 9 new Chat Completions MCP configurations
  - GPT-OSS configurations: `gpt_oss_mcp_example.yaml`, `gpt_oss_mcp_test.yaml`, `gpt_oss_streamable_http_test.yaml`
  - Qwen API configurations: `qwen_api_mcp_example.yaml`, `qwen_api_mcp_test.yaml`, `qwen_api_streamable_http_test.yaml`
  - Qwen Local configurations: `qwen_local_mcp_example.yaml`, `qwen_local_mcp_test.yaml`, `qwen_local_streamable_http_test.yaml`

- **Enhanced LMStudio Backend**: Improved local model support
  - Better tracking of attempted model loads
  - Improved server output handling and error reporting

### Changed
- **Backend Architecture**: Major MCP framework expansion
  - Extended existing v0.0.15 MCP infrastructure to support all ChatCompletions providers
  - Refactored `chat_completions.py` with 1200+ lines of MCP integration code
  - Enhanced error handling and retry mechanisms for provider-specific quirks

- **CLI Improvements**: Better backend creation and provider detection
  - Enhanced backend creation logic for improved provider handling
  - Better system message handling for different backend types

### Technical Details
- **Main Feature**: Chat Completions MCP integration enabling all providers to use MCP tools
- **Files Modified**: 20+ files across backend, mcp_tools, configurations, and CLI
- **Contributors**: @praneeth999 @qidanrui @sonichi @a5507203 @ncrispino @Henry-811 and the MassGen team

## [0.0.17] - 2025-09-10

### Added
- **OpenAI Backend MCP Support**: Extended MCP (Model Context Protocol) integration to OpenAI backend
  - Full MCP tool discovery and execution capabilities for OpenAI models
  - Support for both stdio and HTTP-based MCP servers with OpenAI
  - Seamless integration with existing OpenAI function calling
  - Robust error handling and retry mechanisms

- **MCP Configuration Examples**: New YAML configurations for OpenAI MCP usage
  - `gpt5_mini_mcp_test.yaml`: Basic OpenAI MCP testing with test server
  - `gpt5_mini_mcp_example.yaml`: Weather service integration example for OpenAI
  - `gpt5_mini_streamable_http_test.yaml`: HTTP transport testing for OpenAI MCP
  - Enhanced existing multi-agent configurations with OpenAI MCP support

- **Documentation**: Added case studies and technical documentation
  - `unified-filesystem-mcp-integration.md`: Case study demonstrating unified filesystem capabilities with MCP integration across multiple backends (from v0.0.16)
  - `MCP_INTEGRATION_RESPONSE_BACKEND.md`: Technical documentation for MCP integration with response backends

### Changed
- **Backend Enhancements**: Improved MCP support across backends
  - Extended MCP integration from Gemini and Claude Code to include OpenAI backend
  - Unified MCP tool handling across all supported backends
  - Enhanced error reporting and debugging for MCP operations

### Technical Details
- **New Features**: OpenAI backend MCP integration
- **Documentation**: Added case study for unified filesystem MCP integration
- **Contributors**: @praneeth999 @qidanrui @sonichi @ncrispino @a5507203 @Henry-811 and the MassGen team

## [0.0.16] - 2025-09-08

### Added
- **Unified Filesystem Support with MCP Integration**: Advanced filesystem capabilities designed for all backends
  - Complete `FilesystemManager` class providing unified filesystem access with extensible backend support
  - Currently supports Gemini and Claude Code backends, designed for seamless expansion to all backends
  - MCP-based filesystem operations enabling file manipulation, workspace management, and cross-agent collaboration

- **Expanded Configuration Library**: New YAML configurations for various use cases
  - **Gemini MCP Filesystem Testing**: `gemini_mcp_filesystem_test.yaml`, `gemini_mcp_filesystem_test_sharing.yaml`, `gemini_mcp_filesystem_test_single_agent.yaml`, `gemini_mcp_filesystem_test_with_claude_code.yaml`
  - **Hybrid Model Setups**: `geminicode_gpt5nano.yaml`

- **Case Studies**: Added comprehensive case studies from previous versions
  - `gemini-mcp-notion-integration.md`: Gemini MCP Notion server integration and productivity workflows
  - `claude-code-workspace-management.md`: Claude Code context sharing and workspace management demonstrations


### Technical Details
- **Commits**: 30+ commits including workspace redesign and orchestrator enhancements
- **Files Modified**: 40+ files across orchestrator, mcp_tools, configurations, and case studies
- **New Architecture**: Complete workspace management system with FilesystemManager
- **Contributors**: @ncrispino @a5507203 @sonichi @Henry-811 and the MassGen team

## [0.0.15] - 2025-09-05

### Added
- **MCP (Model Context Protocol) Integration Framework**: Complete implementation for external tool integration
  - New `massgen/mcp_tools/` package with 8 core modules for MCP support
  - Multi-server MCP client supporting simultaneous connections to multiple MCP servers
  - Two transport types: stdio (process-based) and streamable-http (web-based)
  - Circuit breaker patterns for fault tolerance and reliability
  - Comprehensive security framework with command sanitization and validation
  - Automatic tool discovery with name prefixing for multi-server setups

- **Gemini MCP Support**: Full MCP integration for Gemini backend
  - Session-based tool execution via Gemini SDK
  - Automatic tool discovery and calling capabilities
  - Robust error handling with exponential backoff
  - Support for both stdio and HTTP-based MCP servers
  - Integration with existing Gemini function calling

- **Test Infrastructure for MCP**: Development and testing utilities
  - Simple stdio-based MCP test server (`mcp_test_server.py`)
  - FastMCP streamable-http test server (`test_http_mcp_server.py`)
  - Comprehensive test suite for MCP integration

- **MCP Configuration Examples**: New YAML configurations for MCP usage
  - `gemini_mcp_test.yaml`: Basic Gemini MCP testing
  - `gemini_mcp_example.yaml`: Weather service integration example
  - `gemini_streamable_http_test.yaml`: HTTP transport testing
  - `multimcp_gemini.yaml`: Multi-server MCP configuration
  - Additional Claude Code MCP configurations

### Changed
- **Dependencies**: Updated package requirements
  - Added `mcp>=1.12.0` for official MCP protocol support
  - Added `aiohttp>=3.8.0` for HTTP-based MCP communication
  - Updated `pyproject.toml` and `requirements.txt`

- **Documentation**: Enhanced project documentation
  - Created technical analysis documents for Gemini MCP integration
  - Added comprehensive MCP tools README with architecture diagrams
  - Added security and troubleshooting guides for MCP

### Technical Details
- **Commits**: 40+ commits including MCP integration, documentation, and bug fixes
- **Files Modified**: 35+ files across MCP modules, backends, configurations, and tests
- **Security Features**: Configurable security levels (strict/moderate/permissive)
- **Contributors**: @praneeth999 @qidanrui @sonichi @a5507203 @ncrispino @Henry-811 and the MassGen team

## [0.0.14] - 2025-09-02

### Added
- **Enhanced Logging System**: Improved logging infrastructure with add_log feature
  - Better log organization and preservation for multi-agent workflows
  - Enhanced workspace management for Claude Code agents
  - New final answer directory structure in Claude Code and logs for storing final results

### Documentation
- **Release Documents**: Updated release documentation and materials
  - Updated CHANGELOG.md for better release tracking
  - Removed unnecessary use case documentation

### Technical Details
- **Commits**: 19 commits
- **Files Modified**: Logging system enhancements, documentation updates
- **New Features**: Enhanced logging, improved final presentation logging for Claude Code
- **Contributors**: @qidanrui @sonichi and the MassGen team

## [0.0.13] - 2025-08-28

### Added
- **Unified Logging System**: Better logging infrastructure for better debugging and monitoring
  - New centralized `logger_config.py` with colored console output and file logging
  - Debug mode support via `--debug` CLI flag for verbose logging
  - Consistent logging format across all backends, including Claude, Gemini, Grok, Azure OpenAI, and other providers
  - Color-coded log levels for better visibility (DEBUG: cyan, INFO: green)

- **Windows Platform Support**: Enhanced cross-platform compatibility
  - Windows-specific fixes for terminal display and color output
  - Improved path handling for Windows file systems
  - Better process management on Windows platform

### Changed
- **Frontend Improvements**: Refined display
  - Enhanced rich terminal display formatting to not show debug info in the final presentation

- **Documentation Updates**: Improved project documentation
  - Updated CONTRIBUTING.md with better guidelines
  - Enhanced README with logging configuration details
  - Renamed roadmap from v0.0.13 to v0.0.14 for future planning

### Technical Details
- **Commits**: 35+ commits including new logging system and Windows support
- **Files Modified**: 24+ files across backend, frontend, logging, and CLI modules
- **New Features**: Unified logging system with debug mode, Windows platform support
- **Contributors**: @qidanrui @sonichi @Henry-811 @JeffreyCh0 @voidcenter and the MassGen team

## [0.0.12] - 2025-08-27

### Added
- **Enhanced Claude Code Agent Context Sharing**: Improved multiple Claude Code agent coordination with workspace sharing
  - New workspace snapshot stored in orchestrator's space for better context management
  - New temporary working directory for each agent, stored in orchestrator's space
  - Claude Code agents can now share context by referencing their own temporary working directory in the orchestrator's workspace
  - Anonymous agent context mapping when referencing temporary directories
  - Improved context preservation across agent coordination cycles

- **Advanced Orchestrator Configurations**: Enhanced orchestrator configurations
  - Configurable system message support for orchestrator
  - New snapshot and temporary workspace settings for better context management

### Changed
- **Documentation Updates**: documentation improvements
  - Updated README with current features and usage examples
  - Improved configuration examples and setup instructions

### Technical Details
- **Commits**: 10+ commits including context sharing enhancements, workspace management, and configuration improvements
- **Files Modified**: 20+ files across orchestrator, backend, configuration, and documentation
- **New Features**: Enhanced Claude Code agent workspace sharing with temporary working directories and snapshot mechanisms
- **Contributors**: @qidanrui @sonichi @Henry-811 @JeffreyCh0 @voidcenter and the MassGen team

## [0.0.11] - 2025-08-25

### Known Issues
- **System Message Handling in Multi-Agent Coordination**: Critical issues affecting Claude Code agents
  - **Lost System Messages During Final Presentation** (`orchestrator.py:1183`)
    - Claude Code agents lose domain expertise during final presentation
    - ConfigurableAgent doesn't properly expose system messages via `agent.system_message`
  - **Backend Ignores System Messages** (`claude_code.py:754-762`)
    - Claude Code backend filters out system messages from presentation_messages
    - Only processes user messages, causing loss of agent expertise context
    - System message handling only works during initial client creation, not with `reset_chat=True`
  - **Ambiguous Configuration Sources**
    - Multiple conflicting system message sources: `custom_system_instruction`, `system_prompt`, `append_system_prompt`
    - Backend parameters silently override AgentConfig settings
    - Unclear precedence and behavior documentation
  - **Architecture Violations**
    - Orchestrator contains Claude Code-specific implementation details
    - Tight coupling prevents easy addition of new backends
    - Violates separation of concerns principle

### Fixed
- **Custom System Message Support**: Enhanced system message configuration and preservation
  - Added `base_system_message` parameter to conversation builders for agent's custom system message
  - Orchestrator now passes agent's `get_configurable_system_message()` to conversation builders
  - Custom system messages properly combined with MassGen coordination instructions instead of being overwritten
  - Backend-specific system prompt customization (system_prompt, append_system_prompt)
- **Claude Code Backend Enhancements**: Improved integration and configuration
  - Better system message handling and extraction
  - Enhanced JSON structured response parsing
  - Improved coordination action descriptions
- **Final Presentation & Agent Logic**: Enhanced multi-agent coordination (#135)
  - Improved final presentation handling for Claude Code agents
  - Better coordination between agents during final answer selection
  - Enhanced CLI presentation logic
  - Agent configuration improvements for workflow coordination
- **Evaluation Message Enhancement**: Improved synthesis instructions
  - Changed to "digest existing answers, combine their strengths, and do additional work to address their weaknesses"
  - Added "well" qualifier to evaluation questions
  - More explicit guidance for agents to synthesize and improve upon existing answers

### Changed
- **Documentation Updates**: Enhanced project documentation
  - Renamed roadmap from v0.0.11 to v0.0.12 for future planning
  - Updated README with latest features and improvements
  - Improved CONTRIBUTING guidelines
  - Enhanced configuration examples and best practices

### Added
- **New Configuration Files**: Introduced additional YAML configuration files
  - Added `multi_agent_playwright_automation.yaml` for browser automation workflows

### Removed
- **Deprecated Configurations**: Cleaned up configuration files
  - Removed `gemini_claude_code_paper_search_mcp.yaml`
  - Removed `gpt5_claude_code_paper_search_mcp.yaml`
- **Gemini CLI Tests**: Removed Gemini CLI related tests

### Technical Details
- **Commits**: 25+ commits including bug fixes, feature additions, and improvements
- **Files Modified**: 35+ files across backend, orchestrator, frontend, configuration, and documentation
- **New Configuration**: `multi_agent_playwright_automation.yaml` for browser automation workflows
- **Contributors**: @qidanrui @Leezekun @sonichi @voidcenter @Daucloud @Henry-811 and the MassGen team

## [0.0.10] - 2025-08-22

### Added
- **Azure OpenAI Support**: Integration with Azure OpenAI services
  - New `azure_openai.py` backend with async streaming capabilities
  - Support for Azure-hosted GPT-4.1 and GPT-5-chat models
  - Configuration examples for single and multi-agent Azure setups
  - Test suite for Azure OpenAI functionality
- **Enhanced Claude Code Backend**: Major refactoring and improvements
  - Simplified MCP (Model Context Protocol) integration
- **Final Presentation Support**: New orchestrator presentation capabilities
  - Support for final answer presentation in multi-agent scenarios
  - Fallback mechanisms for presentation generation
  - Test coverage for presentation functionality

### Fixed
- **Claude Code MCP**: Cleaned up and simplified MCP implementation
  - Removed redundant MCP server and transport modules
- **Configuration Management**: Improved YAML configuration handling
  - Fixed Azure OpenAI deployment configurations
  - Updated model mappings for Azure services

### Changed
- **Backend Architecture**: Significant refactoring of backend systems
  - Consolidated Azure OpenAI implementation using AsyncAzureOpenAI
  - Improved error handling and streaming capabilities
  - Enhanced async support across all backends
- **Documentation Updates**: Enhanced project documentation
  - Updated README with Azure OpenAI setup instructions
  - Renamed roadmap from v0.0.10 to v0.0.11
  - Improved presentation materials for DataHack Summit 2025
- **Test Infrastructure**: Expanded test coverage
  - Added comprehensive Azure OpenAI backend tests
  - Integration tests for final presentation functionality
  - Simplified test structure with better coverage

### Removed
- **Deprecated MCP Components**: Removed unused MCP modules
  - Removed standalone MCP client, transport, and server implementations
  - Cleaned up MCP test files and testing checklist
  - Simplified Claude Code backend by removing redundant MCP code

### Technical Details
- **Commits**: 35+ commits including Azure OpenAI integration and Claude Code improvements
- **Files Modified**: 30+ files across backend, configuration, tests, and documentation
- **New Backend**: Azure OpenAI backend with full async support
- **Contributors**: @qidanrui @Leezekun @sonichi and the MassGen team

## [0.0.9] - 2025-08-22

### Added
- **Quick Start Guide**: Comprehensive quickstart documentation in README
  - Streamlined setup instructions for new users
  - Example configurations for getting started quickly
  - Clear installation and usage steps
- **Multi-Agent Configuration Examples**: New configuration files for various setups
  - Paper search configuration with GPT-5 and Claude Code
  - Multi-agent setups with different model combinations
- **Roadmap Documentation**: Added comprehensive roadmap for version 0.0.10
  - Focused on Claude Code context sharing between agents
  - Multi-agent context synchronization planning
  - Enhanced backend features and CLI improvements roadmap

### Fixed
- **Web Search Processing**: Fixed bug in response handling for web search functionality
  - Improved error handling in web search responses
  - Better streaming of search results
- **Rich Terminal Display**: Fixed rendering issues in terminal UI
  - Resolved display formatting problems
  - Improved message rendering consistency

### Changed
- **Claude Code Integration**: Optimized Claude Code implementation
  - MCP (Model Context Protocol) integration
  - Streamlined Claude Code backend configuration
- **Documentation Updates**: Enhanced project documentation
  - Updated README with quickstart guide
  - Added CONTRIBUTING.md guidelines
  - Improved configuration examples

### Technical Details
- **Commits**: 10 commits including bug fixes, code cleanup, and documentation updates
- **Files Modified**: Multiple files across backend, configurations, and documentation
- **Contributors**: @qidanrui @sonichi @Leezekun @voidcenter @JeffreyCh0 @stellaxiang

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
