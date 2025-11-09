# Computer Use Tool - Quick Start Guide

## Installation

```bash
# 1. Install Playwright (for browser automation)
pip install playwright
playwright install chromium

# 2. (Optional) Install Docker SDK (for OS automation)
pip install docker

# 3. (Optional) Install Pillow (for image processing)
pip install pillow

# 4. Set API key
export OPENAI_API_KEY="your-api-key-here"
```

## Basic Usage

### Command Line

```bash
# Browser automation
massgen --config @massgen/configs/tools/custom_tools/computer_use_browser_example.yaml \
    "Search for Python documentation on Google"

# With vision capabilities
massgen --config @massgen/configs/tools/custom_tools/computer_use_with_vision.yaml \
    "Find the latest AI news and summarize"

# Using Gemini
massgen --config @massgen/configs/tools/custom_tools/gemini_computer_use_example.yaml \
    "Research quantum computing advancements"
```

### Python API

```python
from massgen.tool import computer_use
import asyncio

# Simple task
result = asyncio.run(computer_use(
    task="Navigate to example.com and describe the page",
    environment="browser"
))

print(result)
```

## Available Configs

| Config File | Model | Environment | Use Case |
|-------------|-------|-------------|----------|
| `computer_use_example.yaml` | gpt-4.1 | Browser | General automation |
| `computer_use_browser_example.yaml` | computer-use-preview | Browser | Browser-specific tasks |
| `computer_use_docker_example.yaml` | computer-use-preview | Docker/Ubuntu | OS-level automation |
| `computer_use_with_vision.yaml` | gpt-4.1 | Browser + Vision | Combined automation + analysis |
| `gemini_computer_use_example.yaml` | gemini-2.5-flash | Browser | Using Gemini model |

## Common Tasks

### Web Search
```bash
massgen --config @computer_use_browser_example.yaml \
    "Search for 'machine learning' on Google and click the first result"
```

### Form Filling
```bash
massgen --config @computer_use_browser_example.yaml \
    "Go to example.com/contact and fill in the form with name: John Doe, email: john@example.com"
```

### Screenshot Analysis
```bash
massgen --config @computer_use_with_vision.yaml \
    "Navigate to Wikipedia's homepage and describe what you see"
```

### Multi-step Workflow
```bash
massgen --config @computer_use_browser_example.yaml \
    "1. Go to GitHub, 2. Search for 'python automation', 3. Find the most starred repository"
```

## Customization

### Adjust Display Size
```python
result = await computer_use(
    task="Your task here",
    display_width=1280,
    display_height=800
)
```

### Set Max Iterations
```python
result = await computer_use(
    task="Your task here",
    max_iterations=20  # Prevent long-running tasks
)
```

### Use Headless Browser
```python
result = await computer_use(
    task="Your task here",
    environment_config={"headless": True}
)
```

## Troubleshooting

### "Playwright not installed"
```bash
pip install playwright
playwright install
```

### "OpenAI API key not found"
```bash
export OPENAI_API_KEY="sk-..."
```

### "Browser launch failed"
```bash
# Reinstall browsers
playwright install --force chromium
```

### "Container not found" (Docker)
```bash
# Create and start container
docker run -d --name cua-container ubuntu:22.04 sleep infinity
```

## Tips

1. **Start Simple** - Test with basic tasks first
2. **Use Vision** - Combine with `understand_image` for verification
3. **Set Limits** - Use `max_iterations` to prevent runaway processes
4. **Monitor Logs** - Enable logging to see what's happening
5. **Sandbox** - Always run in isolated environments

## Next Steps

- Read the full [README.md](README.md) for detailed documentation
- Explore [example configs](../../configs/tools/custom_tools/)
- Check [OpenAI's Computer Use Guide](https://platform.openai.com/docs/guides/tools-computer-use)

## Support

For issues or questions:
- Check the [README.md](README.md) troubleshooting section
- Review MassGen documentation
- Check OpenAI status page for API issues
