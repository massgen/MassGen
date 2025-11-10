# Computer Use Tool for MassGen

## Overview

The Computer Use tool integrates OpenAI's Computer-Using Agent (CUA) model (`computer-use-preview`) into MassGen, enabling automated browser and computer interactions. This tool allows AI agents to:

- Control web browsers (click, type, scroll, navigate)
- Automate desktop applications (in Docker/VM environments)
- Perform multi-step workflows
- Verify actions using screenshot analysis
- Handle safety checks for secure operation

## Architecture

The implementation consists of:

1. **`computer_use_tool.py`** - Main tool implementation with:
   - Computer Use loop orchestration
   - Browser automation (Playwright)
   - Docker/VM automation (xdotool)
   - Screenshot capture and management
   - Safety check handling

2. **Integration with `understand_image`** - Vision capabilities for:
   - Screenshot analysis and verification
   - Content extraction from pages
   - Visual feedback loop

3. **YAML Configurations** - Pre-configured examples for:
   - Browser automation
   - Docker container automation
   - Combined vision + automation workflows
   - Multi-model support (OpenAI, Gemini)

## Installation

### Basic Requirements

```bash
# Install OpenAI SDK (if not already installed)
pip install openai>=2.2.0

# Set your API key
export OPENAI_API_KEY="your-openai-api-key"
```

### Browser Environment (Playwright)

```bash
# Install Playwright
pip install playwright

# Install browser binaries
playwright install

# Or install specific browser
playwright install chromium
```

### Docker Environment (Optional)

```bash
# Install Docker SDK for Python
pip install docker

# Pull and run a pre-configured container
# (See Docker Setup section below)
docker pull ubuntu:22.04
```

### Image Processing (Optional but Recommended)

```bash
# For image resizing and optimization
pip install pillow
```

## Usage

### Quick Start - Browser Automation

```python
from massgen.tool import computer_use
import asyncio

# Simple browser task
result = asyncio.run(computer_use(
    task="Search for Python documentation on Google",
    environment="browser",
    display_width=1920,
    display_height=1080
))

print(result)
```

### Using Configuration Files

#### Browser Automation
```bash
massgen --config @massgen/configs/tools/custom_tools/computer_use_browser_example.yaml \
    "Check the latest OpenAI news on bing.com"
```

#### With Vision Capabilities
```bash
massgen --config @massgen/configs/tools/custom_tools/claude_computer_use_docker_example.yaml \
    "Search for cats on Google Images and describe what you see"
```

#### Using Gemini
```bash
massgen --config @massgen/configs/tools/custom_tools/gemini_computer_use_example.yaml \
    "Research the latest AI news and summarize the top 3 articles"
```

#### Docker Environment
```bash
massgen --config @massgen/configs/tools/custom_tools/computer_use_docker_example.yaml \
    "Open calculator and compute 123 + 456"
```

## Configuration Parameters

### Tool Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `task` | str | Required | Description of the task to perform |
| `environment` | str | `"browser"` | Environment type: `"browser"`, `"ubuntu"`, `"mac"`, `"windows"`, `"docker"` |
| `display_width` | int | `1920` | Display width in pixels |
| `display_height` | int | `1080` | Display height in pixels |
| `max_iterations` | int | `50` | Maximum number of action iterations |
| `include_reasoning` | bool | `True` | Include reasoning summaries in responses |
| `initial_screenshot_path` | str | `None` | Optional path to initial screenshot |
| `environment_config` | dict | `{}` | Environment-specific configuration |

### Environment Config Options

#### Browser Environment
```python
environment_config = {
    "browser_type": "chromium",  # "chromium", "firefox", or "webkit"
    "headless": False            # True for headless mode
}
```

#### Docker Environment
```python
environment_config = {
    "container_name": "cua-container",  # Docker container name
    "display": ":99"                    # X11 display number
}
```

## Docker Setup

### Creating a Docker Container for Computer Use

```bash
# Create a Dockerfile
cat > Dockerfile << 'EOF'
FROM ubuntu:22.04

# Install desktop environment and tools
RUN apt-get update && apt-get install -y \
    xvfb \
    x11vnc \
    xfce4 \
    xfce4-terminal \
    firefox \
    scrot \
    xdotool \
    && rm -rf /var/lib/apt/lists/*

# Set up X11
ENV DISPLAY=:99

# Start Xvfb
CMD Xvfb :99 -screen 0 1280x800x24 &
EOF

# Build the container
docker build -t cua-ubuntu .

# Run the container
docker run -d --name cua-container cua-ubuntu \
    sh -c "Xvfb :99 -screen 0 1280x800x24 & sleep infinity"
```

### Verifying Docker Setup

```bash
# Check container is running
docker ps | grep cua-container

# Test X11 display
docker exec -e DISPLAY=:99 cua-container xdotool getmouselocation
```

## YAML Configuration Examples

### Minimal Browser Config

```yaml
agents:
  - id: "browser_agent"
    backend:
      type: "openai"
      model: "gpt-4.1"
      custom_tools:
        - name: ["computer_use"]
          category: "automation"
          path: "massgen/tool/_computer_use/computer_use_tool.py"
          function: ["computer_use"]
          default_params:
            environment: "browser"
            display_width: 1920
            display_height: 1080

    system_message: |
      You are a browser automation agent.
      Use the computer_use tool to perform web-based tasks.

ui:
  display_type: "simple"
  logging_enabled: true
```

### Advanced Config with Vision

```yaml
agents:
  - id: "advanced_agent"
    backend:
      type: "openai"
      model: "gpt-4.1"
      custom_tools:
        - name: ["computer_use"]
          category: "automation"
          path: "massgen/tool/_computer_use/computer_use_tool.py"
          function: ["computer_use"]
          default_params:
            environment: "browser"
            max_iterations: 30
            include_reasoning: true
        - name: ["understand_image"]
          category: "multimodal"
          path: "massgen/tool/_multimodal_tools/understand_image.py"
          function: ["understand_image"]

    system_message: |
      You have both computer control and vision capabilities.
      Use computer_use for automation and understand_image for verification.

ui:
  display_type: "detailed"
  show_screenshots: true
  show_reasoning: true
```

## Action Types

The Computer Use tool supports the following actions:

### Click
```json
{
  "type": "click",
  "x": 100,
  "y": 200,
  "button": "left"  // "left", "right", or "middle"
}
```

### Double Click
```json
{
  "type": "double_click",
  "x": 100,
  "y": 200
}
```

### Type Text
```json
{
  "type": "type",
  "text": "Hello World"
}
```

### Key Press
```json
{
  "type": "keypress",
  "keys": ["enter"]  // Common keys: enter, space, tab, backspace, delete, escape
}
```

### Scroll
```json
{
  "type": "scroll",
  "x": 500,
  "y": 500,
  "scroll_x": 0,
  "scroll_y": 100  // Positive = down, negative = up
}
```

### Wait
```json
{
  "type": "wait",
  "duration": 2  // seconds
}
```

### Screenshot
```json
{
  "type": "screenshot"  // Automatically captured after each action
}
```

## Safety Features

### Built-in Safety Checks

The tool includes three types of safety checks:

1. **Malicious Instruction Detection** - Detects adversarial content in screenshots
2. **Irrelevant Domain Detection** - Warns when navigating to unexpected domains
3. **Sensitive Domain Detection** - Alerts when visiting sensitive sites

### Safety Check Handling

Safety checks are automatically acknowledged in the tool, but in production you should:

```python
# Example: Manual safety check handling
if pending_checks:
    for check in pending_checks:
        print(f"Safety Warning: {check.code} - {check.message}")
        user_approval = input("Continue? (yes/no): ")
        if user_approval.lower() != "yes":
            return {"success": False, "error": "User cancelled due to safety check"}
```

### Best Practices

1. **Sandbox Environments** - Always run in isolated browser/container
2. **Allowlists** - Implement domain allowlists for production
3. **Rate Limiting** - Respect API rate limits
4. **Human in the Loop** - Use for high-stakes tasks with human oversight
5. **Logging** - Enable comprehensive logging for audit trails

## Troubleshooting

### Playwright Issues

```bash
# Reinstall browsers
playwright install --force

# Check browser installation
playwright install --dry-run

# Use specific browser
# Set environment_config: {"browser_type": "firefox"}
```

### Docker Issues

```bash
# Check container logs
docker logs cua-container

# Restart container
docker restart cua-container

# Access container shell
docker exec -it cua-container bash

# Test X11 in container
docker exec -e DISPLAY=:99 cua-container scrot /tmp/test.png
```

### API Errors

```bash
# Verify API key
echo $OPENAI_API_KEY

# Check model access
# The computer-use-preview model may have limited availability

# Monitor rate limits
# Check OpenAI dashboard for usage and limits
```

### Screenshot Issues

```bash
# Install PIL if not available
pip install pillow

# Check file permissions
# Ensure agent has write access to workspace

# Verify display resolution
# Ensure display_width and display_height are reasonable (e.g., 1920x1080)
```

## Limitations

1. **Model Accuracy** - The `computer-use-preview` model may make mistakes, especially in non-browser environments (currently ~38% on OSWorld benchmark)

2. **Rate Limits** - Computer use model has constrained rate limits

3. **Environment Support** - Browser environments work best; OS automation is less reliable

4. **Long-running Tasks** - Max iterations default is 50 to prevent infinite loops

5. **Authentication** - Avoid fully authenticated environments for security

## Examples

### Example 1: Web Research

```python
result = await computer_use(
    task="""
    1. Navigate to Google
    2. Search for "Python asyncio tutorial"
    3. Click on the first result
    4. Take a screenshot
    """,
    environment="browser",
    max_iterations=20
)
```

### Example 2: Form Filling

```python
result = await computer_use(
    task="""
    Navigate to https://example.com/contact
    Fill out the form with:
    - Name: John Doe
    - Email: john@example.com
    - Message: Hello from MassGen!
    Click Submit
    """,
    environment="browser"
)
```

## API Reference

### `computer_use()`

Main function for computer automation.

**Returns**: `ExecutionResult` with structure:
```json
{
  "success": true,
  "operation": "computer_use",
  "task": "...",
  "environment": "browser",
  "iterations": 15,
  "action_log": [
    {
      "iteration": 1,
      "action": {...},
      "call_id": "call_..."
    }
  ],
  "final_output": ["Task completed successfully"]
}
```

**Error Response**:
```json
{
  "success": false,
  "operation": "computer_use",
  "error": "Error description",
  "action_log": [...],
  "iterations": 5
}
```

## Contributing

To extend the computer use tool:

1. Add new action types in `execute_browser_action()` or `execute_docker_action()`
2. Implement additional environment types
3. Add custom safety checks
4. Create new YAML configurations for specific use cases

## License

This tool is part of MassGen and follows the same license.

## References

- [OpenAI Computer Use Documentation](https://platform.openai.com/docs/guides/tools-computer-use)
- [Gemini Computer Use Documentation](https://blog.google/technology/google-deepmind/gemini-computer-use-model/)
- [Claude Computer Use Documentation](https://docs.claude.com/en/docs/agents-and-tools/tool-use/computer-use-tool)
- [Playwright Documentation](https://playwright.dev/python/)
- [Docker SDK for Python](https://docker-py.readthedocs.io/)
