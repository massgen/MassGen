# Contributing to MassGen

Thank you for your interest in contributing to MassGen! We welcome contributions from the community.

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- Git

### Setup
1. Fork and clone the repository
2. Create a virtual environment:
   ```bash
   pip install uv
   uv venv
   source .venv/bin/activate  # macOS/Linux
   uv pip install -e .
   ```
3. Configure API keys:
   ```bash
   cp massgen/v3/backend/.env.example massgen/v3/backend/.env
   # Edit .env with your API keys
   ```
4. Run tests: `python -m pytest tests/ -v`

## 🤝 How to Contribute

### Bug Reports
Please include:
- Environment details (Python version, OS, MassGen version)
- Clear reproduction steps
- Expected vs actual behavior
- Error messages and stack traces

### Feature Requests
- Check existing issues first
- Describe the use case and proposed solution
- Consider impact on existing functionality

### Pull Requests
1. Create an issue first for major changes
2. Fork and create a feature branch
3. Follow our code style (PEP 8, type hints, docstrings)
4. Add tests for new functionality
5. Update documentation as needed
6. Format code with `black` and `isort`
7. Ensure tests pass

#### PR Checklist
- [ ] Descriptive title and description
- [ ] Linked to relevant issue
- [ ] Tests added/updated
- [ ] Documentation updated
- [ ] Code formatted
- [ ] Tests pass locally

## 🛠️ Development Areas

We welcome contributions in:
- **Model backends** - Add support for new AI providers
- **Tools and integrations** - Extend agent capabilities
- **Performance improvements** - Optimize coordination and communication
- **Documentation** - Improve guides and examples
- **Testing** - Increase test coverage
- **Bug fixes** - Resolve issues and edge cases

### Adding Model Backends
1. Create `massgen/v3/backend/your_model_backend.py`
2. Implement the `BaseBackend` interface
3. Register in `chat_agent.py`
4. Add tests and documentation

### Adding Tools
1. Define tools in the appropriate backend
2. Implement tool logic
3. Add comprehensive tests
4. Update documentation

## 📋 Code Standards
- Follow PEP 8
- Use type hints
- Write Google-style docstrings
- Maximum 88 character line length
- Use async/await for concurrent operations

## 🧪 Testing
```bash
# Run all tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=massgen --cov-report=html
```

## 📞 Community
- **GitHub Issues**: Bug reports and feature requests
- **Discord**: [MassGen community](https://discord.gg/VVrT2rQaz5)

## 📄 License
By contributing, you agree that your contributions will be licensed under the Apache License 2.0.

---

Thank you for contributing to MassGen! 🚀