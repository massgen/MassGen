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

### Installation and Setup

#### Prerequisites

- Python 3.10 or higher
- API keys for the model providers you want to use

#### Development Setup

```bash
# Clone the repository
git clone https://github.com/Leezekun/MassGen.git
cd MassGen

# Install uv for dependency management
pip install uv

# Create virtual environment
uv venv

# Install dependencies (if requirements.txt exists)
uv pip install -r requirements.txt
```

#### Environment Configuration

Create a `.env` file in the `massgen` directory as described in [README](README.md)

### Contributing Areas

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

### Development Workflow

> **Important**: Our next version is v0.0.21. If you want to contribute, please contribute to the `dev/v0.0.21` branch.

1. **Fork the repository** and create a feature branch from `dev/v0.0.21`
2. **Set up the development environment** following the setup instructions above
3. **Make your changes** following the existing code style and patterns
4. **Add tests** for new functionality
5. **Update documentation** if needed
6. **Test your changes** thoroughly with different configurations
7. **Submit a pull request** with a clear description of your changes

### Testing

Run tests to ensure your changes work correctly:

```bash
# Run specific test files
uv run python -m pytest massgen/tests/test_*.py

# Test with different configurations
uv run python -m massgen.cli --config massgen/configs/single_4omini.yaml "Test question"
```

## 🤝 Community

- **Discord**: Join the #massgen channel of AG2 Discord server: https://discord.gg/VVrT2rQaz5
- **X**: Follow the official MassGen X account: https://x.com/massgen_ai
- **GitHub Issues**: Report bugs and request features
- **GitHub Discussions**: Ask questions and share ideas


## 📄 License

By contributing, you agree that your contributions will be licensed under the same Apache License 2.0 that covers the project.

---

Thank you for contributing to MassGen! 🚀