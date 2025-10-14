# MassGen v0.0.25 Release Notes

**Release Date:** September 30, 2025

---

## Overview

Version 0.0.25 introduces **Multi-Turn Filesystem Support**, enabling persistent file context across conversation turns. This release also adds **SGLang Backend Integration** for high-performance local inference alongside the existing vLLM support, and enhances the path permission system with exclusion patterns and better validation.

With multi-turn filesystem support, agents can maintain consistent workspace state across multiple conversation turns, making MassGen ideal for iterative development workflows and long-running projects.

---

## What's New

### Multi-Turn Filesystem Support

The headline feature of v0.0.25 is **Multi-Turn Filesystem Support** for persistent context across conversation turns.

**Key Capabilities:**
- **Automatic Session Management:** When `session_storage` is configured, multi-turn mode activates automatically (no flag needed)
- **Persistent Workspace:** Maintains workspace state across conversation turns in `.massgen` directory
- **Snapshot Preservation:** Workspace snapshots saved and restored between turns
- **File Context Continuity:** Modifications persist throughout multi-turn sessions

**Implementation:**
- Session storage management in `.massgen` directory
- Workspace snapshot system for state preservation
- Automatic workspace restoration on session resume
- Integration with filesystem manager for seamless operation

**Configuration Example:**
```yaml
orchestrator:
  session_storage: "./.massgen/sessions"
  context_paths:
    - path: "./workspace"
      permission: WRITE
```

**Try It Out:**
```bash
# Multi-turn filesystem session
massgen --config @examples/two_gemini_flash_filesystem_multiturn \
  "Create a simple website"

# Continue in next turn (workspace persists)
# > "Add a contact form to the website"
# > "Update the styling to use a dark theme"
```

**Use Cases:**
- Iterative website development
- Long-running coding projects
- Multi-stage content creation
- Progressive refinement workflows

**New Configurations:**
- `two_gemini_flash_filesystem_multiturn.yaml`: Two Gemini agents with multi-turn filesystem
- `grok4_gpt5_gemini_filesystem_multiturn.yaml`: Three agents with multi-turn filesystem
- `grok4_gpt5_claude_code_filesystem_multiturn.yaml`: Mixed backends with multi-turn filesystem

**Design Documentation:**
- `multi_turn_filesystem_design.md`: Complete implementation details and architecture

---

### SGLang Backend Integration

**SGLang Support** added alongside existing vLLM for local model serving.

**Key Features:**
- **SGLang Server Support:** Default port 30000 with `SGLANG_API_KEY` environment variable
- **SGLang-Specific Parameters:** Support for `separate_reasoning` and other SGLang features
- **Auto-Detection:** Automatic detection between vLLM and SGLang servers
- **Unified Backend:** Single `InferenceBackend` class replacing separate `vllm.py`

**Configuration Example:**
```yaml
agents:
  - id: "sglang_agent"
    backend:
      type: "inference"
      base_url: "http://localhost:30000"
      model: "Qwen/Qwen2.5-7B-Instruct"
      backend_params:
        separate_reasoning: true  # SGLang-specific parameter
```

**Try It Out:**
```bash
# Mixed vLLM and SGLang deployment
massgen --config @examples/two_qwen_vllm_sglang \
  "Your task"
```

**Benefits:**
- Choice between vLLM and SGLang for different use cases
- Leverage SGLang's guided generation features
- Unified interface for both backends
- Easy migration between servers

**Documentation:**
- Renamed `vllm_implementation.md` to `inference_backend.md` for unified documentation

---

### Enhanced Path Permission System

Improved path validation and exclusion patterns.

**New Features:**
- **Default Exclusion Patterns:** Common directories automatically excluded (.git, node_modules, .venv, etc.)
- **will_be_writable Flag:** Better permission state tracking
- **Improved Path Validation:** Different handling for context vs workspace paths
- **Enhanced Test Coverage:** Comprehensive tests in `test_path_permission_manager.py`

**Default Excluded Patterns:**
- `.git`, `.svn`, `.hg` (version control)
- `node_modules`, `.venv`, `venv` (dependencies)
- `__pycache__`, `.pytest_cache` (build artifacts)
- `.DS_Store`, `Thumbs.db` (system files)

**Benefits:**
- Prevents agents from accessing unnecessary directories
- Better performance with large codebases
- Safer workspace operations
- Cleaner permission model

---

## What Changed

### CLI Enhancements

**Improvements:**
- Enhanced logging with configurable log levels and file output
- Improved error handling and user feedback
- Better command-line argument processing
- More informative status messages

---

### System Prompt Improvements

**Refinements:**
- Clearer instructions for file context handling
- Better guidance for multi-turn conversations
- Improved prompt templates for filesystem operations
- Enhanced agent coordination prompts

---

### Documentation Updates

- Updated README with clearer installation instructions
- Multi-turn filesystem usage examples
- SGLang backend setup guide
- Improved configuration examples

---

## What Was Fixed

### Filesystem Manager

**Resolved Issues:**
- Fixed warnings for non-existent temporary workspaces
- Better cleanup of old workspaces
- Fixed relative path issues in workspace copy operations
- Improved workspace state management

---

### Configuration Issues

**Fixes:**
- Fixed multi-agent configuration templates
- Fixed code generation prompts for consistency
- Corrected parameter handling in various configs

---

## New Configurations

### Multi-Turn Filesystem Configurations (3)

1. **two_gemini_flash_filesystem_multiturn.yaml**
   - Two Gemini Flash 2.5 agents
   - Multi-turn filesystem support
   - Use Case: Iterative development with two agents
   - Example: "Build a website progressively across multiple turns"

2. **grok4_gpt5_gemini_filesystem_multiturn.yaml**
   - Three agents: Grok, GPT-5, Gemini
   - Multi-model multi-turn collaboration
   - Use Case: Complex projects requiring diverse perspectives
   - Example: "Develop a full-stack application iteratively"

3. **grok4_gpt5_claude_code_filesystem_multiturn.yaml**
   - Three agents: Grok, GPT-5, Claude Code
   - Mixed backends with filesystem support
   - Use Case: Leveraging different backend capabilities
   - Example: "Create a data analysis project with visualizations"

### SGLang Configuration

4. **two_qwen_vllm_sglang.yaml**
   - Mixed vLLM and SGLang deployment
   - Two Qwen agents on different servers
   - Use Case: Comparing vLLM and SGLang performance
   - Example: "Test both inference backends on the same task"

---

## Documentation Updates

### Enhanced Documentation

- **multi_turn_filesystem_design.md:** Complete design documentation for multi-turn filesystem
- **inference_backend.md:** Unified documentation for vLLM and SGLang (renamed from `vllm_implementation.md`)
- **README.md:** Updated with multi-turn examples and SGLang setup

---

## Technical Details

### Statistics

- **Commits:** 30+ commits
- **Files Modified:** 33 files
- **Insertions:** 3,188 lines
- **Deletions:** 642 lines
- **New Backend:** SGLang integration in unified InferenceBackend

### Major Components Changed

1. **Session Management:** Multi-turn filesystem implementation
2. **Backend System:** Unified vLLM/SGLang backend
3. **Permission System:** Enhanced path exclusions and validation
4. **CLI:** Improved logging and error handling

### Session Storage Structure

```
.massgen/
└── sessions/
    └── <session_id>/
        ├── workspace/          # Persistent workspace files
        ├── snapshot/           # Workspace snapshots
        └── metadata.json       # Session metadata
```

---

## Use Cases

### Iterative Website Development

**Progressive Enhancement:**
```bash
# Turn 1: Create basic structure
massgen --config @examples/two_gemini_flash_filesystem_multiturn \
  "Create a basic HTML website with home and about pages"

# Turn 2: Add features (workspace persists)
# > "Add a navigation menu and footer"

# Turn 3: Refine styling (workspace persists)
# > "Update the CSS to use a modern gradient design"
```

### Long-Running Coding Projects

**Multi-Stage Development:**
```bash
# Turn 1: Project setup
massgen --config @examples/grok4_gpt5_gemini_filesystem_multiturn \
  "Set up a FastAPI project with database models"

# Turn 2: Add endpoints
# > "Create REST API endpoints for user management"

# Turn 3: Add tests
# > "Write unit tests for all endpoints"
```

### Local Model Deployment

**SGLang vs vLLM:**
```bash
# Test with mixed deployment
massgen --config @examples/two_qwen_vllm_sglang \
  "Compare performance on code generation task"
```

---

## Migration Guide

### Upgrading from v0.0.24

**No Breaking Changes**

v0.0.25 is fully backward compatible with v0.0.24. All existing configurations will continue to work.

**Optional: Enable Multi-Turn Filesystem**

To use multi-turn filesystem support:

```yaml
orchestrator:
  session_storage: "./.massgen/sessions"
  context_paths:
    - path: "./your_workspace"
      permission: WRITE
```

**Optional: Use SGLang Backend**

To switch from vLLM to SGLang:

```yaml
agents:
  - id: "sglang_agent"
    backend:
      type: "inference"  # Same type as vLLM
      base_url: "http://localhost:30000"  # SGLang default port
      model: "your-model"
```

**Environment Variables:**

```bash
# For SGLang
export SGLANG_API_KEY="your-key"

# For vLLM (unchanged)
export VLLM_API_KEY="your-key"
```

---

## Contributors

Special thanks to all contributors who made v0.0.25 possible:

- @praneeth999
- @ncrispino
- @qidanrui
- @sonichi
- @Henry-811
- And the entire MassGen team

---

## Resources

- **CHANGELOG:** [CHANGELOG.md](../../../CHANGELOG.md#0025---2025-09-29)
- **Design Doc:** [multi_turn_filesystem_design.md](../../../backend/docs/multi_turn_filesystem_design.md)
- **Backend Doc:** [inference_backend.md](../../../backend/docs/inference_backend.md)
- **Next Release:** [v0.0.26 Release Notes](../v0.0.26/release-notes.md) - File Deletion and Context Files
- **Previous Release:** [v0.0.24 Release Notes](../v0.0.24/release-notes.md) - vLLM Backend
- **GitHub Release:** https://github.com/Leezekun/MassGen/releases/tag/v0.0.25

---

## What's Next

See the [v0.0.26 Release](../v0.0.26/release-notes.md) for what came after, including:
- **File Deletion Tools** - Workspace cleanup capabilities
- **Protected Paths** - Reference file protection
- **File Context Paths** - Single file access control

---

*Released with ❤️ by the MassGen team*
