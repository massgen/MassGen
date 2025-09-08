# MassGen Documentation

This directory contains the source files for MassGen's documentation website, built with Sphinx.

## 📚 Documentation Structure

```
docs/
├── source/              # Documentation source files
│   ├── quickstart/      # Getting started guides
│   ├── user_guide/      # User documentation
│   ├── api/             # API reference
│   ├── examples/        # Code examples
│   └── development/     # Developer documentation
├── build/               # Built documentation (git-ignored)
├── Makefile             # Build commands for Unix/Linux
└── make.bat             # Build commands for Windows
```

## 🚀 Quick Start

### Prerequisites

```bash
# Install documentation dependencies
pip install -r docs/requirements-docs.txt

# Or install with the project
pip install -e ".[docs]"
```

### Building Documentation

```bash
# Navigate to docs directory
cd docs

# Build HTML documentation
make html

# View the built docs
open build/html/index.html  # macOS
xdg-open build/html/index.html  # Linux
start build/html/index.html  # Windows
```

### Live Development Server

For auto-reload during development:

```bash
# Install sphinx-autobuild
pip install sphinx-autobuild

# Run live server
make livehtml

# Visit http://localhost:8000
```

## 📝 Writing Documentation

### File Formats

- **Markdown (.md)**: Preferred for general documentation
- **reStructuredText (.rst)**: Required for index files and complex formatting

### Adding New Pages

1. Create your file in the appropriate directory
2. Add it to a `toctree` directive in an index file
3. Build and verify the documentation

Example:
```rst
.. toctree::
   :maxdepth: 2
   
   your_new_page
```

### Using Markdown

Thanks to MyST parser, you can use enhanced Markdown:

```markdown
# Heading

```{note}
This is a note admonition
```

```{code-block} python
:linenos:

def example():
    return "Hello, MassGen!"
```
```

### API Documentation

API docs are auto-generated from docstrings:

```python
def my_function(param1: str, param2: int) -> bool:
    """
    Brief description of the function.
    
    Args:
        param1: Description of param1
        param2: Description of param2
        
    Returns:
        Description of return value
        
    Example:
        >>> my_function("test", 42)
        True
    """
    pass
```

## 🎨 Customization

### Theme Settings

Edit `source/conf.py` to customize:

```python
html_theme_options = {
    'logo_only': False,
    'display_version': True,
    'style_nav_header_background': '#2980B9',
    # ... more options
}
```

### Custom CSS

Add styles to `source/_static/custom.css`

### Custom JavaScript

Add scripts to `source/_static/custom.js`

## 🚢 Deployment

### GitHub Pages

Documentation is automatically deployed via GitHub Actions:

1. Push to `main` or `doc_web` branch
2. GitHub Actions builds the docs
3. Deploys to GitHub Pages

### Read the Docs

For versioned documentation:

1. Connect your GitHub repo to Read the Docs
2. Configure using `.readthedocs.yaml`
3. Builds trigger automatically on push

### Manual Deployment

```bash
# Build for production
make clean html

# The built files are in build/html/
# Upload to your web server
```

## 🛠️ Useful Commands

```bash
# Clean build directory
make clean

# Build HTML docs
make html

# Build PDF (requires LaTeX)
make latexpdf

# Check for broken links
make linkcheck

# Run doctests
make doctest

# Start local server
make serve
```

## 📋 Documentation Standards

### Writing Style

- **Clear and Concise**: Use simple language
- **Examples**: Include code examples for all features
- **Consistency**: Follow existing patterns
- **Active Voice**: "Configure the agent" not "The agent is configured"

### Code Examples

- **Runnable**: Ensure examples actually work
- **Complete**: Include all necessary imports
- **Annotated**: Add comments explaining key points
- **Tested**: Verify examples with each release

### Versioning

- Document version-specific features clearly
- Mark deprecated features
- Include migration guides for breaking changes

## 🐛 Troubleshooting

### Common Issues

**Build Warnings**
```bash
# Show warnings during build
make html SPHINXOPTS="-W"
```

**Missing Module**
```bash
# Ensure MassGen is installed
pip install -e ..
```

**Theme Not Found**
```bash
# Reinstall documentation dependencies
pip install -r requirements-docs.txt
```

## 📚 Resources

- [Sphinx Documentation](https://www.sphinx-doc.org/)
- [MyST Parser](https://myst-parser.readthedocs.io/)
- [Read the Docs Theme](https://sphinx-rtd-theme.readthedocs.io/)
- [reStructuredText Primer](https://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html)

## 🤝 Contributing

1. Fork the repository
2. Create a documentation branch
3. Make your changes
4. Build and test locally
5. Submit a pull request

See [CONTRIBUTING.md](../CONTRIBUTING.md) for more details.