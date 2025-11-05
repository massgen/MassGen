# Contributing to MassGen

Thank you for your interest in contributing to MassGen (Multi-Agent Scaling System for GenAI)! We welcome contributions from the community and are excited to see what you'll bring to the project.

---

**📍 Looking for what to work on?** Check [ROADMAP.md](ROADMAP.md) for:
- Active development tracks with owners
- Upcoming release features and priorities
- Long-term vision and goals

**This guide covers:** Development setup, code standards, testing, PR process, and documentation requirements.

---

## 🛠️ Development Guidelines

### Project Structure

```
massgen/
├── __init__.py              # Main package exports
├── cli.py                   # Command-line interface
├── orchestrator.py          # Multi-agent coordination
├── chat_agent.py            # Chat agent implementation
├── agent_config.py          # Agent configuration management
├── message_templates.py     # Message template system
├── logger_config.py         # Logging configuration
├── utils.py                 # Helper functions and model registry
├── backend/                 # Model-specific implementations
│   ├── __init__.py
│   ├── base.py             # Base backend interface
│   ├── cli_base.py         # CLI backend base class
│   ├── chat_completions.py # Chat completion utilities
│   ├── response.py         # Response handling
│   ├── azure_openai.py     # Azure OpenAI backend
│   ├── claude.py           # Anthropic Claude backend
│   ├── claude_code.py      # Claude Code CLI backend
│   ├── gemini.py           # Google Gemini backend
│   ├── grok.py             # xAI Grok backend
│   ├── lmstudio.py         # LMStudio backend
│   └── *.md                # Backend documentation and API research
├── mcp_tools/              # MCP (Model Context Protocol) integration
│   ├── __init__.py
│   ├── README.md           # Comprehensive MCP documentation
│   ├── backend_utils.py    # Backend utility functions for MCP
│   ├── circuit_breaker.py  # Circuit breaker pattern implementation
│   ├── client.py           # MCP client implementation
│   ├── config_validator.py # Configuration validation
│   ├── converters.py       # Data format converters
│   ├── exceptions.py       # Custom MCP exceptions
│   ├── security.py         # Security validation and sanitization
│   ├── filesystem_manager.py # Workspace and snapshot management
│   ├── hooks.py            # Function hooks for permission management
│   ├── workspace_copy_server.py # MCP server for file copying operations
│   └── *.md                # Individual component documentation
├── frontend/               # User interface components
│   ├── __init__.py
│   ├── coordination_ui.py  # Main UI coordination
│   ├── displays/           # Display implementations
│   │   ├── __init__.py
│   │   ├── base_display.py
│   │   ├── rich_terminal_display.py
│   │   ├── simple_display.py
│   │   └── terminal_display.py
├── configs/                # Configuration files
│   ├── *.yaml             # Various agent configurations
│   └── *.md               # MCP setup guides and documentation
├── tests/                  # Test files
│   ├── __init__.py
│   ├── test_*.py          # Test implementations
│   └── *.md               # Test documentation and case studies
└── v1/                     # Legacy version 1 code
    ├── __init__.py
    ├── agent.py
    ├── agents.py
    ├── backends/
    ├── cli.py
    ├── config.py
    ├── examples/
    ├── logging.py
    ├── main.py
    ├── orchestrator.py
    ├── streaming_display.py
    ├── tools.py
    ├── types.py
    └── utils.py
```

### Adding New Model Backends

To add support for a new model provider:

1. Create a new file in `massgen/backend/` (e.g., `new_provider.py`)
2. Inherit from the base backend class in `massgen/backend/base.py`
3. Implement the required methods for message processing and completion parsing
4. Add the model mapping in `massgen/utils.py`
5. **Add backend capabilities to `massgen/backend/capabilities.py`** - Required for config validation
6. Update configuration templates in `massgen/configs/`
7. Add tests in `massgen/tests/`
8. **Update the config validator** - See [Updating the Config Validator](#updating-the-config-validator) below
9. Update documentation

### Updating the Config Validator

**⚠️ IMPORTANT**: Whenever you add new configuration options, backends, or change the config schema, you MUST update the config validator.

The config validator (`massgen/config_validator.py`) ensures users get helpful error messages when they make configuration mistakes. When you add a new feature:

**1. Add to Backend Capabilities** (for new backends)
```python
# In massgen/backend/capabilities.py
BACKEND_CAPABILITIES = {
    # ...
    "your_backend": BackendCapabilities(
        backend_type="your_backend",
        provider_name="Your Backend Name",
        supported_capabilities={"mcp", "web_search", ...},
        builtin_tools=[...],
        filesystem_support="mcp",
        models=["model-1", "model-2"],
        default_model="model-1",
        env_var="YOUR_API_KEY",
        notes="Description of your backend",
    ),
}
```

**2. Update Validator Enums** (for new config options)
```python
# In massgen/config_validator.py
# If adding new valid values for existing fields:
VALID_PERMISSION_MODES = {"default", "acceptEdits", "bypassPermissions", "plan"}
VALID_DISPLAY_TYPES = {"rich_terminal", "simple"}
```

**3. Add Validation Logic** (for new config fields)
```python
# In massgen/config_validator.py
# Add validation in the appropriate _validate_* method
def _validate_your_feature(self, config, result):
    if "your_field" in config:
        # Validate type
        # Validate values
        # Add helpful error messages
```

**4. Add Tests for Common Mistakes**
```python
# In massgen/tests/test_config_validator.py
def test_invalid_your_feature(self):
    """Test invalid your_feature value."""
    config = {
        "your_field": "invalid_value",
        # ...
    }
    validator = ConfigValidator()
    result = validator.validate_config(config)
    assert not result.is_valid()
    assert any("your helpful error message" in error.message for error in result.errors)
```

**5. Test Validation**
```bash
# Validate all example configs still pass
uv run python scripts/validate_all_configs.py

# Run validator tests
uv run pytest massgen/tests/test_config_validator.py -v
```

**Why This Matters:**
- Users get clear, actionable error messages instead of cryptic failures
- Prevents common configuration mistakes
- Makes the framework more accessible to new users
- Pre-commit hooks automatically validate configs in `massgen/configs/`

## 🔒 API Stability & Versioning

MassGen is currently in **Beta** (v0.1.x). We're rapidly iterating on features and patterns. Here's what you can depend on:

### Stability Levels

**🟢 Stable - We Maintain Backward Compatibility**

- **CLI Command**: `massgen` executable and basic invocation patterns
  - `massgen --config <path>` will continue to work
  - Standard flags like `--help`, `--version`
  - Exit codes and basic output format

- **Core YAML Configuration Schema**: Basic structure for defining agents and running them
  - Top-level keys: `agents`, `orchestrator`, `providers`
  - Agent definition fields: `name`, `backend`, `system_prompt`
  - Model provider configuration structure
  - **Guarantee**: New fields may be added with sensible defaults. Breaking changes to existing fields require major version bump and migration guides.

**🟡 Experimental - Evolving Rapidly, May Change**

- **Orchestration & Coordination**: Agent coordination mechanisms and voting systems
  - Binary decision framework with voting tools
  - Planning mode vs execution mode
  - Coordination configuration and agent selection logic
  - New coordination patterns being explored

- **Backend Implementations**: Individual model provider adapters
  - Provider-specific settings and capabilities
  - Tool/MCP integration per backend
  - Multimodal support varies by provider

- **Advanced YAML Features**:
  - Memory module configuration
  - Tool system configuration
  - MCP server setup and permissions
  - Multi-turn conversation settings

- **Python Library API**: Internal APIs not yet released for public use
  - Use CLI + YAML for production workflows
  - Python API stability coming in future releases

- **Multimodal Support**: Image, audio, video processing
  - Backend capabilities evolving
  - Configuration schema may change

**🔴 Deprecated - Will Be Removed**

- **`v1/` directory**: Legacy code from version 1
  - Scheduled for removal in v1.0.0
  - Don't add features or dependencies on this code

### What This Means for Contributors

**When contributing to stable areas:**
- Breaking changes require team discussion
- Must provide deprecation warnings 2+ releases (1 week) in advance
- Update migration documentation in CHANGELOG.md

**When contributing to experimental areas:**
- Coordinate with track owners in [ROADMAP.md](ROADMAP.md) before major changes
- Document that features are experimental in user-facing docs
- Breaking changes allowed but should be documented

**When working with deprecated code:**
- No new features should be added
- Migrations and cleanup PRs welcome
- Help users migrate to new patterns

### Version Policy

**Current (v0.1.x)**:
- Minor breaking changes allowed for experimental features
- Migration guides provided in CHANGELOG.md for any breaking changes
- CLI and core YAML schema remain backward compatible

**Future (v0.2.x+)**:
- More features graduate to stable
- Deprecation warnings before all removals
- Broader stability guarantees

**v1.0.0 and beyond**:
- Full stability commitment for public APIs
- Semantic versioning strictly enforced
- Clear upgrade paths for all breaking changes

### Examples

**Stable - These will keep working:**
```yaml
# Basic agent configuration
agents:
  - name: researcher
    backend: openai
    model: gpt-5
    system_prompt: "You are a research assistant"
```

**Experimental - May change:**
```yaml
# Orchestrator settings (features evolving)
orchestrator:
  snapshot_storage: "snapshots"
  agent_temporary_workspace: "temp_workspaces"

# Memory configuration (implemented in v0.1.5 - see docs/source/user_guide/memory.rst)
memory:
  enabled: true
  persistent_memory:
    enabled: true
    vector_store: "qdrant"
```

## 📋 Prerequisites

- Python 3.11 or higher
- Git
- API keys for the model providers you want to use
- [uv](https://github.com/astral-sh/uv) for dependency management (recommended)

## 🚀 Development Setup

### 1. Fork and Clone

```bash
# Fork the repository on GitHub first, then:
git clone https://github.com/YOUR_USERNAME/MassGen.git
cd MassGen

# Add upstream remote
git remote add upstream https://github.com/Leezekun/MassGen.git
```

### 2. Create Development Environment

```bash
# Install uv for dependency management (if not already installed)
pip install uv

# Create virtual environment
uv venv

# Activate virtual environment
# On macOS/Linux:
source .venv/bin/activate
# On Windows:
.venv\Scripts\activate

# Install project in editable mode with all dependencies
uv pip install -e .

# Install development dependencies
uv pip install -e ".[dev]"
```

### 3. Set Up Pre-commit Hooks

Pre-commit hooks ensure code quality and consistency. Install them with:

```bash
# Install pre-commit hooks
pre-commit install
```

### 4. Environment Configuration

Create a `.env` file in the `massgen` directory as described in [README](README.md)

## 🔧 Development Workflow

> **Important**: Our next version is v0.1.9. If you want to contribute, please contribute to the `dev/v0.1.9` branch (or `main` if dev/v0.1.9 doesn't exist yet).

### 1. Create Feature Branch

```bash
# Fetch latest changes from upstream
git fetch upstream

# Create feature branch from dev/v0.1.9 (or main if dev branch doesn't exist yet)
git checkout -b feature/your-feature-name upstream/dev/v0.1.9
```

### 2. Make Your Changes

Follow these guidelines while developing:

- **Code Style**: Follow existing patterns and conventions in the codebase
- **Documentation**: Update docstrings and README if needed
- **Tests**: Add tests for new functionality
- **Type Hints**: Use type hints for better code clarity

### 3. Code Quality Checks

Before committing, ensure your code passes all quality checks:

```bash
# Run pre-commit hooks on staged files
pre-commit run

# Or to check specific files:
pre-commit run --files path/to/file1.py path/to/file2.py

# Run individual tools on changed files:

# Get list of changed Python files
git diff --name-only --cached --diff-filter=ACM | grep '\.py$'

# Format changed files with Black
git diff --name-only --cached --diff-filter=ACM | grep '\.py$' | xargs black --line-length=79

# Sort imports in changed files
git diff --name-only --cached --diff-filter=ACM | grep '\.py$' | xargs isort

# Check changed files with flake8
git diff --name-only --cached --diff-filter=ACM | grep '\.py$' | xargs flake8 --extend-ignore=E203

# Type checking on changed files
git diff --name-only --cached --diff-filter=ACM | grep '\.py$' | xargs mypy

# Security checks on changed files
git diff --name-only --cached --diff-filter=ACM | grep '\.py$' | xargs bandit

# Lint changed files with pylint
git diff --name-only --cached --diff-filter=ACM | grep '\.py$' | xargs pylint

# For testing all files (only when needed):
pre-commit run --all-files
```

### 4. Testing

```bash
# Run all tests
pytest massgen/tests/

# Run specific test file
pytest massgen/tests/test_specific.py

# Run with coverage
pytest --cov=massgen massgen/tests/

# Test with different configurations
massgen --config @examples/basic/single/single_agent "Test question"
```

### 5. Commit Your Changes

```bash
# Stage your changes
git add .

# Commit with descriptive message
# Pre-commit hooks will run automatically
git commit -m "feat: add support for new model provider"

# If pre-commit hooks fail, fix the issues and commit again
```

Commit message format:
- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `test:` Adding or updating tests
- `refactor:` Code refactoring
- `style:` Code style changes
- `perf:` Performance improvements
- `ci:` CI/CD changes

### 6. Push and Create Pull Request

```bash
# Push to your fork
git push origin feature/your-feature-name
```

Then create a pull request on GitHub:
- Base branch: `dev/v0.1.9` (or `main` if dev branch doesn't exist yet)
- Compare branch: `feature/your-feature-name`
- Add clear description of changes
- Link any related issues

## 🔍 Pre-commit Hooks Explained

Our pre-commit configuration includes:

### Python Code Quality
- **check-ast**: Verify Python AST is valid
- **black**: Code formatter (line length: 79)
- **isort**: Import sorting
- **flake8**: Style guide enforcement
- **pylint**: Advanced linting (with custom disabled rules)
- **mypy**: Static type checking

### File Checks
- **check-yaml**: Validate YAML syntax
- **check-json**: Validate JSON syntax
- **check-toml**: Validate TOML syntax
- **check-docstring-first**: Ensure docstrings come before code
- **trailing-whitespace**: Remove trailing whitespace
- **fix-encoding-pragma**: Add `# -*- coding: utf-8 -*-` when needed
- **add-trailing-comma**: Add trailing commas for better diffs

### Security
- **detect-private-key**: Prevent committing private keys

### Package Quality
- **pyroma**: Check package metadata quality

## 🎯 How to Find Where to Contribute

MassGen development is organized into **tracks** - focused areas with dedicated owners who can guide your contributions.

### Step 1: Explore Active Tracks

Visit [ROADMAP.md](ROADMAP.md#-contributors--contact) to see all active tracks with their owners and contact info:

- **Tool System Refactoring** - Unified tool system (@qidanrui)
- **Multimodal Support** - Image, audio, video processing (@qidanrui)
- **AG2 Group Chat Patterns** - Complex research workflows (@Eric-Shang)
- **Agent Adapter System** - Unified agent interface (@Eric-Shang)
- **Irreversible Actions Safety** - Safety controls (@franklinnwren)
- **Memory Module** - Long-term memory implementation (@kitrakrev, @qidanrui, @ncrispino)
- **Final Agent Submit/Restart** - Multi-step verification (@ncrispino)
- **Coding Agent Enhancements** - File operations (@ncrispino)
- **DSPy Integration** - Automated prompt optimization (@praneeth999)
- **Web UI** - Visual interface (@voidcenter)

### Step 2: Reach Out to Track Owner

**Before starting work:**

1. **Open a GitHub issue** describing your contribution idea
   - Include context, motivation, and approach
   - Link to related issues/PRs if applicable

2. **Start a Discord thread** in #massgen channel
   - @ mention the track owner (Discord handle from [ROADMAP.md](ROADMAP.md#-contributors--contact))
   - Link to your GitHub issue
   - Discuss your idea with the track owner who can:
     - Point you to existing work
     - Suggest good first issues
     - Explain current priorities
     - Review designs before implementation

**Example:**
- Open issue: "Add support for OpenAI o1-pro model"
- Discord: "@danrui2020 I'd like to contribute to multimodal support. Opened issue #123 with details."

### Step 3: Create Your Own Track (Optional)

Have a significant feature idea not covered by existing tracks?
1. Open a GitHub issue describing the proposed track
2. Start a thread in #massgen Discord channel linking to the issue
3. Work with the MassGen dev team to define the track
4. Become a track owner yourself!

### Quick Contribution Ideas (No Track Coordination Needed)

- 🐛 **Bug Fixes** - Open an issue/PR for any bugs you find
- 📝 **Documentation** - Improvements always welcome
- 🧪 **Tests** - Increase coverage in any module
- 🎨 **Examples** - New configuration templates or use cases
- 💡 **Feature Requests** - Open an issue to discuss ideas

### First-Time Contributors

**Good first issues:** Check GitHub issues tagged [`good first issue`](https://github.com/Leezekun/MassGen/labels/good%20first%20issue)

**Quick wins:**
- Add backend support for a new model provider (see [Adding New Model Backends](#adding-new-model-backends))
- Create example configurations for your use case
- Write case studies using MassGen


## 📝 Pull Request Guidelines

### Before Submitting

- [ ] Code passes all pre-commit hooks
- [ ] Tests pass locally
- [ ] Documentation is updated if needed
- [ ] Commit messages follow convention
- [ ] PR targets `dev/v0.1.9` branch (or `main` if dev branch doesn't exist yet)

### PR Description Should Include

- **What**: Brief description of changes
- **Why**: Motivation and context
- **How**: Technical approach taken
- **Testing**: How you tested the changes
- **Screenshots**: If UI changes (if applicable)

### Review Process

1. Automated checks will run on your PR
2. Maintainers will review your code
3. Address any feedback or requested changes
4. Once approved, PR will be merged

## 🐛 Reporting Issues

When reporting issues, please include:

- Python version
- Operating system
- Steps to reproduce
- Expected vs actual behavior
- Error messages/logs
- Minimal reproducible example

## 🤝 Community

- **Discord**: Join the #massgen channel of AG2 Discord server: https://discord.gg/VVrT2rQaz5
- **X**: Follow the official MassGen X account: https://x.com/massgen_ai
- **GitHub Issues**: Report bugs and request features
- **GitHub Discussions**: Ask questions and share ideas

## ⚠️ Important Notes

### Dependencies
- When adding new dependencies, update `pyproject.toml`
- Use optional dependency groups for non-core features
- Pin versions for critical dependencies

### Backward Compatibility
- Maintain backward compatibility when possible
- Document breaking changes clearly
- Update version numbers appropriately

### Performance Considerations
- Profile code for performance bottlenecks
- Consider memory usage for large-scale operations
- Optimize streaming and async operations

## 📚 Documentation Guidelines

### When Implementing a New Feature

Every feature needs documentation! Here's how to decide where and what to write.

#### 1. Decide Where to Document

**Add to existing user guide when:**
- ✅ Feature extends existing functionality (e.g., new backend → add to `backends.rst`)
- ✅ Natural fit in current documentation structure
- ✅ Small enhancement (< 200 words of documentation)

**Create new user guide when:**
- ✅ Feature is a major new capability (e.g., multi-turn mode)
- ✅ Deserves its own page (> 500 words of documentation)
- ✅ Introduces new concepts or workflows

**Examples:**
- Adding new backend → Update `user_guide/backends.rst`
- New MCP server → Add to `user_guide/mcp_integration.rst`
- Update multi-turn conversation system → Edit `user_guide/multi_turn_mode.rst`

#### 2. Required Documentation for Every Feature

**Always update these files:**

1. ✅ **User Guide** - How users interact with the feature
   - Location: `docs/source/user_guide/`
   - What to include: Usage examples, configuration, common patterns

2. ✅ **Configuration Docs** - If feature adds config options
   - Location: `docs/source/quickstart/configuration.rst`
   - What to include: YAML examples, parameter descriptions

3. ✅ **Config Validator** - **REQUIRED if feature changes config schema**
   - Location: `massgen/config_validator.py` and `massgen/backend/capabilities.py`
   - What to include: Validation logic, error messages, tests
   - **See**: [Updating the Config Validator](#updating-the-config-validator) section above

4. ✅ **API Reference** - If feature changes Python API
   - Location: `docs/source/api/`
   - What to include: Docstrings, function signatures, examples

5. ✅ **CHANGELOG.md** - What changed in this version
   - Location: Root directory
   - What to include: Brief description under "Added", "Changed", or "Fixed"

6. ✅ **Examples** - **REQUIRED for every feature**
   - Location: `docs/source/examples/basic_examples.rst` or feature-specific example files
   - What to include: Runnable code showing feature in action
   - **Note**: Examples are ALWAYS required, even if you write a case study. Case studies showcase real-world usage; examples show basic functionality.

#### 3. Optional Design Documentation

**When to write additional documentation:**

##### Design Doc (for complex implementation)

**Write when:**
- Implementation is complex and needs explanation for maintainers
- Future contributors need to understand the design choices
- Multiple approaches were considered

**Location:** `docs/dev_notes/feature_name_design.md`

**Examples:**
- `multi_turn_filesystem_design.md` - Complex state management
- `gemini_filesystem_mcp_design.md` - Integration architecture

##### Case Study (after feature is complete)

**Write when:**
- Want to demonstrate real-world usage
- Feature is significant enough to showcase
- Following case-driven development methodology

**Location:** `docs/source/examples/case_studies/feature_name.md`

**Examples:**
- `claude-code-workspace-management.md`
- `unified-filesystem-mcp-integration.md`

#### 4. Documentation Decision Flowchart

```
┌─────────────────────────────────────────┐
│  Implementing a New Feature             │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│  ALWAYS: Update user guide, config      │
│  docs, API docs, CHANGELOG.md           │
└────────────────┬────────────────────────┘
                 │
                 ▼
      Is implementation complex?
                 │
        Yes ──┬──┴──┬── No
              │     │
              ▼     └──────────────┐
   ┌──────────────────┐            │
   │ Write Design Doc │            │
   │ (dev_notes/)     │            │
   └──────┬───────────┘            │
          │                        │
          └────────────┬───────────┘
                       │
                       ▼
              Want to showcase
              real-world usage?
                       │
                  Yes──┼──No
                       │
                       ▼
                ┌──────────────┐
                │ Write Case   │
                │ Study        │
                │ (source/examples/case_studies/)│
                └──────────────┘
```

#### 5. Quick Reference

| Document Type | When to Use | Location | Required? |
|--------------|-------------|----------|-----------|
| **User Guide** | Every feature | `docs/source/user_guide/` | ✅ Yes |
| **Config Docs** | Config changes | `docs/source/quickstart/configuration.rst` | ✅ Yes |
| **Config Validator** | Config schema changes | `massgen/config_validator.py` | ✅ Yes (if config changes) |
| **API Docs** | API changes | `docs/source/api/` | ✅ Yes |
| **CHANGELOG** | Every PR | `CHANGELOG.md` | ✅ Yes |
| **Examples** | **Every feature** | `docs/source/examples/` | ✅ **ALWAYS** |
| **Design Doc** | Complex implementation | `docs/dev_notes/` | ⚠️ Optional |
| **Case Study** | Demonstrate real-world usage | `docs/source/examples/case_studies/` | ⚠️ Optional but expected |

#### 6. Documentation Quality Standards

**User-facing documentation must:**
- ✅ Include runnable code examples
- ✅ Show expected output
- ✅ Explain configuration options
- ✅ Link to related features
- ✅ Follow single source of truth principle (no duplication)

**Design documentation should:**
- ✅ Explain the "why" not just the "what"
- ✅ Document alternatives considered
- ✅ Include diagrams for complex flows
- ✅ Link to related code files

### Documentation Validation

Before submitting a PR with documentation changes:

```bash
# Run all documentation checks
make docs-check

# Build and preview locally
make docs-serve
# Visit http://localhost:8000

# Verify no broken links
make docs-validate

# Verify no duplication
make docs-duplication
```

See [docs/DOCUMENTATION_DEPLOYMENT.md](docs/DOCUMENTATION_DEPLOYMENT.md) for comprehensive testing guide.

## 📄 License

By contributing, you agree that your contributions will be licensed under the same Apache License 2.0 that covers the project.

---

Thank you for contributing to MassGen! 🚀