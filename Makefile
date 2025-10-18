# MassGen Makefile
# Convenience commands for common development tasks

.PHONY: help docs-check docs-build docs-serve docs-clean docs-validate docs-duplication all-checks

# Default target - show help
help:
	@echo "MassGen Development Commands"
	@echo ""
	@echo "Documentation:"
	@echo "  make docs-check        Run all documentation checks (links + duplication)"
	@echo "  make docs-validate     Check for broken links"
	@echo "  make docs-duplication  Check for duplicated content"
	@echo "  make docs-build        Build HTML documentation"
	@echo "  make docs-serve        Build and serve docs locally (http://localhost:8000)"
	@echo "  make docs-clean        Clean documentation build artifacts"
	@echo ""
	@echo "Quick Commands:"
	@echo "  make check             Run all checks (docs + tests)"
	@echo "  make test              Run test suite"
	@echo "  make format            Format code with black and isort"
	@echo "  make lint              Run linting checks"
	@echo ""
	@echo "Installation:"
	@echo "  make install           Install MassGen in development mode"
	@echo "  make install-docs      Install documentation dependencies"
	@echo ""
	@echo "For deployment and testing GitHub Actions, see docs/DOCUMENTATION_DEPLOYMENT.md"
	@echo ""

# Documentation validation
docs-validate:
	@echo "🔍 Validating documentation links..."
	@uv run python scripts/validate_links.py
	@echo "✓ Link validation complete. See docs/LINK_VALIDATION_REPORT.md"

# Documentation duplication check
docs-duplication:
	@echo "🔍 Checking for duplicated content..."
	@uv run python scripts/check_duplication.py
	@echo "✓ Duplication check complete. See docs/DUPLICATION_REPORT.md"

# Run all documentation checks
docs-check: docs-validate docs-duplication
	@echo ""
	@echo "✅ All documentation checks passed!"

# Build documentation
docs-build:
	@echo "📚 Building documentation..."
	@cd docs && sphinx-build -b html source _build/html
	@echo "✓ Documentation built in docs/_build/html/index.html"

# Build and serve documentation locally
docs-serve: docs-build
	@echo "🌐 Starting documentation server..."
	@echo "   Open http://localhost:8000 in your browser"
	@echo "   Press Ctrl+C to stop"
	@cd docs/_build/html && python -m http.server 8000

# Clean documentation build
docs-clean:
	@echo "🧹 Cleaning documentation build..."
	@rm -rf docs/_build
	@rm -f docs/LINK_VALIDATION_REPORT.md
	@rm -f docs/DUPLICATION_REPORT.md
	@echo "✓ Documentation cleaned"

# Install development dependencies
install:
	@echo "📦 Installing MassGen in development mode..."
	@uv pip install -e .
	@echo "✓ MassGen installed"

# Install documentation dependencies
install-docs:
	@echo "📦 Installing documentation dependencies..."
	@uv pip install sphinx sphinx-book-theme sphinx-design sphinx-copybutton
	@echo "✓ Documentation dependencies installed"

# Run all checks (docs + tests)
check: docs-check test
	@echo ""
	@echo "✅ All checks passed!"

# Run tests
test:
	@echo "🧪 Running tests..."
	@uv run pytest massgen/tests/
	@echo "✓ Tests passed"

# Format code
format:
	@echo "✨ Formatting code..."
	@uv run black massgen/
	@uv run isort massgen/
	@echo "✓ Code formatted"

# Lint code
lint:
	@echo "🔍 Linting code..."
	@uv run flake8 massgen/
	@uv run mypy massgen/
	@echo "✓ Linting passed"

# Pre-commit checks (fast)
pre-commit: docs-validate
	@echo "🚀 Running pre-commit checks..."
	@echo "✓ Pre-commit checks passed"

# Pre-push checks (comprehensive)
pre-push: docs-check test
	@echo "🚀 Running pre-push checks..."
	@echo "✓ Pre-push checks passed"
