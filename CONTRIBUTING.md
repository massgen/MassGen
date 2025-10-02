# Contributing to MassGen

Thank you for your interest in contributing to MassGen (Multi-Agent Scaling System for GenAI)! We welcome contributions from the community and are excited to see what you'll bring to the project.

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
5. Update configuration templates in `massgen/configs/`
6. Add tests in `massgen/tests/`
7. Update documentation

## 📋 Prerequisites

- Python 3.10 or higher
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

> **Important**: Our next version is v0.0.27. If you want to contribute, please contribute to the `dev/v0.0.27` branch.

### 1. Create Feature Branch

```bash
# Fetch latest changes from upstream
git fetch upstream

# Create feature branch from dev/v0.0.27
git checkout -b feature/your-feature-name upstream/dev/v0.0.27
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
uv run python -m massgen.cli --config massgen/configs/single_4omini.yaml "Test question"
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
- Base branch: `dev/v0.0.27`
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

## 🎯 Contributing Areas

We welcome contributions in these areas:

- **New Model Backends**: Add support for additional AI models (Claude, local models via vLLM/SGLang, etc.)
- **Enhanced User Interface**: Improve the web interface, terminal displays, and visualization features
- **Performance & Scalability**: Optimize streaming, logging, coordination, and resource management
- **Advanced Agent Collaboration**: Improve communication patterns and consensus-building protocols
- **AG2 Integration**: Support AG2 agents in MassGen
- **Tool Ecosystem Integration**: Add support for MCP Servers and additional tool capabilities
- **Configuration & Templates**: Expand agent configuration options and pre-built templates
- **Documentation**: Add guides, examples, use cases, and comprehensive API documentation
- **Testing & Benchmarking**: Add test coverage and benchmarking frameworks
- **Bug Fixes**: Fix issues and edge cases

## 📝 Pull Request Guidelines

### Before Submitting

- [ ] Code passes all pre-commit hooks
- [ ] Tests pass locally
- [ ] Documentation is updated if needed
- [ ] Commit messages follow convention
- [ ] PR targets `dev/v0.0.27` branch

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

## 📚 Additional Resources

- [Main README](README.md)
- [MCP Documentation](massgen/mcp_tools/README.md)
- [Backend Implementation Guide](massgen/backend/README.md)
- [Testing Guide](massgen/tests/README.md)

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

## 📄 License

By contributing, you agree that your contributions will be licensed under the same Apache License 2.0 that covers the project.

---

Thank you for contributing to MassGen! 🚀