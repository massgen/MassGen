# Computer Use Tool for MassGen

Build computer-using agents that can perform tasks on your behalf using OpenAI's Computer-Using Agent (CUA) model.

## Overview

The Computer Use tool enables AI agents to control computer interfaces and perform tasks by simulating human actions like clicking, typing, scrolling, and more. It operates in a continuous loop:

1. **Send actions** - AI suggests computer actions (click, type, etc.)
2. **Execute** - Actions are executed in your chosen environment
3. **Capture** - Screenshots are taken after each action
4. **Repeat** - Process continues until task is complete

This implementation is based on OpenAI's [Computer Use API](https://platform.openai.com/docs/guides/tools-computer-use).

## Features

- **Multiple Environments**:
  - Browser automation (via Playwright)
  - Docker-based virtual machines (Ubuntu/Mac/Windows)

- **Comprehensive Actions**:
  - Click, double-click
  - Type text
  - Keyboard shortcuts
  - Mouse movement
  - Scrolling
  - Screenshots
  - Wait/delays

- **Safety Features**:
  - Malicious instruction detection
  - Domain validation
  - Sandboxed execution
  - Safety check acknowledgment

- **Reasoning Included**: Optional AI reasoning summaries for transparency

## Installation

### Browser Environment (Playwright)

```bash
pip install playwright
playwright install
```

### Docker Environment

1. Install Docker from [docker.com](https://www.docker.com)
2. Create a Dockerfile (see example below)
3. Build and run the container

#### Example Dockerfile for Ubuntu Environment

```dockerfile
FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive

# Install Xfce, x11vnc, Xvfb, xdotool, etc.
RUN apt-get update && apt-get install -y \
    xfce4 \
    xfce4-goodies \
    x11vnc \
    xvfb \
    xdotool \
    imagemagick \
    x11-apps \
    sudo \
    software-properties-common \
    imagemagick \
 && apt-get remove -y light-locker xfce4-screensaver xfce4-power-manager || true \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

# Add Firefox
RUN add-apt-repository ppa:mozillateam/ppa \
 && apt-get update \
 && apt-get install -y --no-install-recommends firefox-esr \
 && update-alternatives --set x-www-browser /usr/bin/firefox-esr \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -ms /bin/bash myuser \
    && echo "myuser ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers
USER myuser
WORKDIR /home/myuser

# Set x11vnc password
RUN x11vnc -storepasswd secret /home/myuser/.vncpass

# Expose VNC port
EXPOSE 5900

CMD ["/bin/sh", "-c", " \
    Xvfb :99 -screen 0 1280x800x24 >/dev/null 2>&1 & \
    x11vnc -display :99 -forever -rfbauth /home/myuser/.vncpass -listen 0.0.0.0 -rfbport 5900 >/dev/null 2>&1 & \
    export DISPLAY=:99 && \
    startxfce4 >/dev/null 2>&1 & \
    sleep 2 && echo 'Container running!' && \
    tail -f /dev/null \
"]
```

#### Build and Run Docker Container

```bash
# Build the image
docker build -t cua-image .

# Run the container
docker run --rm -it --name cua-container -p 5900:5900 -e DISPLAY=:99 cua-image
```

## Usage

### Quick Start

Use one of the provided configuration files:

```bash
# Browser automation
massgen --config @examples/tools/custom_tools/computer_use_browser_example "Search for Python documentation on Google"

# Docker environment
massgen --config @examples/tools/custom_tools/computer_use_docker_example "Open calculator and compute 123 + 456"
```

### Python API

```python
from massgen.tool._computer_use import computer_use

# Browser automation
result = await computer_use(
    task="Search for the latest AI news on Google",
    environment="browser",
    display_width=1280,
    display_height=720,
    max_iterations=30,
    include_reasoning=True
)

# Docker environment
result = await computer_use(
    task="Open Firefox and navigate to example.com",
    environment="ubuntu",
    display_width=1280,
    display_height=800,
    environment_config={
        "container_name": "cua-container",
        "display": ":99"
    }
)
```

### Configuration Files

Three example configurations are provided:

1. **computer_use_example.yaml** - Basic example
2. **computer_use_browser_example.yaml** - Browser automation (recommended for web tasks)
3. **computer_use_docker_example.yaml** - Docker environment (for OS-level tasks)

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `task` | str | Required | The task to accomplish |
| `environment` | str | `"browser"` | Environment type: `"browser"`, `"mac"`, `"windows"`, `"ubuntu"` |
| `display_width` | int | `1024` | Screen width in pixels |
| `display_height` | int | `768` | Screen height in pixels |
| `model` | str | `"computer-use-preview"` | OpenAI model to use |
| `max_iterations` | int | `20` | Maximum action iterations |
| `include_reasoning` | bool | `True` | Include AI reasoning summaries |
| `initial_screenshot` | str | `None` | Path to initial screenshot |
| `environment_config` | dict | `{}` | Additional environment configuration |

## Examples

### Example 1: Web Search

```python
result = await computer_use(
    task="Go to Bing and search for 'OpenAI GPT-4'",
    environment="browser"
)
```

### Example 2: Form Filling

```python
result = await computer_use(
    task="Navigate to example.com/contact and fill in the form with name 'John Doe' and email 'john@example.com'",
    environment="browser",
    max_iterations=40
)
```

### Example 3: Desktop Application

```python
result = await computer_use(
    task="Open the calculator application and compute 123 + 456",
    environment="ubuntu",
    environment_config={
        "container_name": "cua-container"
    }
)
```

## Return Value

The tool returns an `ExecutionResult` object containing:

```json
{
  "success": true,
  "operation": "computer_use",
  "task": "Search for Python documentation",
  "environment": "browser",
  "iterations": 5,
  "actions_taken": [
    {
      "iteration": 1,
      "action_type": "click",
      "action": {"type": "click", "x": 512, "y": 100, "button": "left"},
      "safety_checks": []
    }
  ],
  "reasoning": [
    {
      "iteration": 1,
      "summary": "Clicking on the search bar"
    }
  ],
  "max_iterations_reached": false
}
```

Plus an `ImageContent` block with the final screenshot.

## Safety and Best Practices

### Security Recommendations

1. **Use Sandboxed Environments**: Always run in isolated containers/browsers
2. **Human-in-the-Loop**: Review actions for high-stakes tasks
3. **Blocklists/Allowlists**: Limit domains and actions in production
4. **Acknowledge Safety Checks**: Review and approve safety warnings
5. **No Sensitive Data**: Avoid fully authenticated environments
6. **Monitor Actions**: Log all actions for audit purposes

### Safety Checks

The tool implements three types of safety checks:

- **Malicious Instruction Detection**: Detects adversarial content in screenshots
- **Irrelevant Domain Detection**: Warns when navigating to unexpected domains
- **Sensitive Domain Detection**: Alerts when on sensitive websites

When safety checks trigger, a human should review before proceeding.

### Limitations

- The `computer-use-preview` model has constrained rate limits
- Browser environment is most reliable (38.1% success on OSWorld for OS tasks)
- Model may make mistakes requiring human correction
- Not recommended for fully autonomous high-stakes operations

## Troubleshooting

### Common Issues

**1. "Playwright not installed"**
```bash
pip install playwright
playwright install
```

**2. "Docker container not running"**
```bash
docker ps  # Check if container is running
docker start cua-container  # Start it if needed
```

**3. "OpenAI API key not found"**

Add to your `.env` file:
```
OPENAI_API_KEY=sk-...
```

**4. "Action execution failed"**

- Increase `max_iterations` for complex tasks
- Add wait times between actions
- Check display resolution matches your environment
- Verify the environment is properly initialized

### Debug Tips

1. Enable reasoning summaries: `include_reasoning=True`
2. Check action logs in the returned result
3. Review screenshots for visual confirmation
4. Use VNC to watch Docker containers (connect to port 5900)

## Architecture

```
massgen/tool/_computer_use/
├── __init__.py                  # Package exports
├── computer_use_tool.py         # Main tool implementation
├── action_handlers.py           # Action execution logic
├── environment_manager.py       # Environment abstraction
└── README.md                    # This file

massgen/configs/tools/custom_tools/
├── computer_use_example.yaml
├── computer_use_browser_example.yaml
└── computer_use_docker_example.yaml
```

## Contributing

To add new environments or actions:

1. **New Environment**: Extend `BaseEnvironment` in `environment_manager.py`
2. **New Action**: Add handler in `action_handlers.py`
3. **New Config**: Create YAML config in `massgen/configs/tools/custom_tools/`

## License

This tool follows MassGen's license. Use in compliance with OpenAI's [Usage Policy](https://openai.com/policies/usage-policies/).

## References

- [OpenAI Computer Use Documentation](https://platform.openai.com/docs/guides/tools-computer-use)
- [OpenAI CUA Sample App](https://github.com/openai/openai-cua-sample-app)
- [Playwright Documentation](https://playwright.dev/)
- [Docker Documentation](https://docs.docker.com/)

## Support

For issues or questions:
1. Check this README
2. Review example configurations
3. Consult OpenAI's Computer Use guide
4. File an issue in the MassGen repository
