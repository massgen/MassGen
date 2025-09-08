# Installation

This guide will help you install MassGen and set up your environment for multi-agent AI collaboration.

## Prerequisites

- **Python 3.10+** - MassGen requires Python 3.10 or higher
- **Git** - For cloning the repository
- **API Keys** - At least one API key from supported providers

## Quick Installation

### 1. Clone the Repository

```bash
git clone https://github.com/Leezekun/MassGen.git
cd MassGen
```

### 2. Set Up Python Environment

We recommend using `uv` for fast dependency management:

```bash
# Install uv (Python package manager)
pip install uv

# Create virtual environment
uv venv

# Activate the environment (optional, uv handles this automatically)
source .venv/bin/activate  # On Linux/Mac
# or
.venv\Scripts\activate  # On Windows
```

### 3. Install Dependencies

```bash
# Install all dependencies
uv pip install -r requirements.txt
```

## API Configuration

### 1. Create Configuration File

Copy the example environment file:

```bash
cp .env.example .env
```

### 2. Add Your API Keys

Edit the `.env` file with your API keys:

```bash
# OpenAI
OPENAI_API_KEY=your_openai_key_here

# Anthropic Claude
ANTHROPIC_API_KEY=your_anthropic_key_here

# Google Gemini
GEMINI_API_KEY=your_gemini_key_here

# xAI Grok
XAI_API_KEY=your_xai_key_here

# Azure OpenAI (optional)
AZURE_OPENAI_API_KEY=your_azure_key_here
AZURE_OPENAI_ENDPOINT=your_azure_endpoint_here

# Other providers...
```

### Getting API Keys

| Provider | How to Get API Key |
|----------|-------------------|
| **OpenAI** | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| **Claude** | [console.anthropic.com](https://console.anthropic.com) |
| **Gemini** | [makersuite.google.com/app/apikey](https://makersuite.google.com/app/apikey) |
| **Grok** | [docs.x.ai](https://docs.x.ai) |
| **Azure OpenAI** | [Azure Portal](https://portal.azure.com) |

## Optional: CLI Tools

For enhanced capabilities, install these optional CLI tools:

### Claude Code CLI

For advanced coding assistance:

```bash
npm install -g @anthropic-ai/claude-code
```

### LM Studio

For running local models:

```bash
# MacOS/Linux
sudo ~/.lmstudio/bin/lms bootstrap

# Windows
cmd /c %USERPROFILE%/.lmstudio/bin/lms.exe bootstrap
```

## Verify Installation

Test your installation with a simple command:

```bash
# Test with a single model
uv run python -m massgen.cli --model claude-3-5-sonnet-latest "Hello, MassGen!"

# If successful, you should see a response from the AI agent
```

## Docker Installation (Alternative)

For containerized deployment:

```bash
# Build the Docker image
docker build -t massgen .

# Run with environment variables
docker run -it --env-file .env massgen --model gpt-4 "Your question here"
```

## Development Installation

For contributors and developers:

```bash
# Install with development dependencies
uv pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Run tests
pytest
```

## Troubleshooting

### Common Issues

**Issue: Module not found errors**
```bash
# Ensure you're in the virtual environment
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate  # Windows

# Reinstall dependencies
uv pip install -r requirements.txt
```

**Issue: API key not recognized**
```bash
# Check if .env file is in the correct location
ls -la .env

# Verify key format (no quotes needed)
OPENAI_API_KEY=sk-abc123...  # Correct
OPENAI_API_KEY="sk-abc123..."  # Incorrect
```

**Issue: Permission denied on Linux/Mac**
```bash
# Add execution permissions
chmod +x scripts/*.sh
```

## Platform-Specific Notes

### Windows

- Use PowerShell or Command Prompt as Administrator for best results
- Path separators in config files should use forward slashes (`/`) or escaped backslashes (`\\`)

### macOS

- If using Apple Silicon (M1/M2), ensure you have Rosetta 2 installed for compatibility
- Some dependencies may require Xcode Command Line Tools: `xcode-select --install`

### Linux

- May need to install Python development headers: `sudo apt-get install python3-dev`
- For Ubuntu/Debian: `sudo apt-get install build-essential`

## Next Steps

Now that you have MassGen installed, proceed to:

- [Creating Your First Agent](first_agent.md) - Learn how to create and run your first AI agent
- [Configuration Guide](configuration.md) - Understand all configuration options
- [Examples](../examples/index.md) - Explore example use cases