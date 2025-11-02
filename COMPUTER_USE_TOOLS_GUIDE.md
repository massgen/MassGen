# Computer Use Tools Guide

This document explains the three different computer use tools available in MassGen and when to use each.

## Overview

MassGen provides three separate tools for computer automation:

1. **`computer_use`** - Full OpenAI Computer Using Agent (CUA) implementation
2. **`gemini_computer_use`** - Google Gemini 2.5 Computer Use implementation
3. **`browser_automation`** - Simple browser automation for any model

## Tool Comparison

| Feature | `computer_use` | `gemini_computer_use` | `browser_automation` |
|---------|----------------|----------------------|---------------------|
| **Model Support** | `computer-use-preview` only | `gemini-2.5-computer-use-preview-10-2025` only | Any model (gpt-4.1, gpt-4o, etc.) |
| **Provider** | OpenAI | Google | Any |
| **Environments** | Browser, Linux/Docker, Mac, Windows | Browser only | Browser only |
| **Implementation** | OpenAI hosted tool with CUA loop | Gemini native computer use API | Direct Playwright automation |
| **Action Planning** | Autonomous multi-step | Autonomous multi-step | User directs each action |
| **Complexity** | High (full agentic control) | High (full agentic control) | Low (simple commands) |
| **Safety Checks** | Built-in | Built-in with confirmations | Manual |
| **Use Case** | Complex workflows (OpenAI) | Complex workflows (Google) | Simple automation, testing |

## 1. computer_use Tool

### Description
Full implementation of OpenAI's Computer Using Agent (CUA) that uses the hosted `computer_use_preview` tool type. The model autonomously plans and executes multiple actions in a loop.

### Model Requirement
- **MUST use `computer-use-preview` model**
- Will NOT work with gpt-4.1, gpt-4o, or other models

### Configuration Files
All these configs use `computer-use-preview` model:
- `computer_use_example.yaml` - Basic browser example
- `computer_use_browser_example.yaml` - Browser automation
- `computer_use_docker_example.yaml` - Linux/Docker automation
- `computer_use_with_vision.yaml` - Combined automation + vision

### Example YAML Config
```yaml
agents:
  - id: "automation_agent"
    backend:
      type: "openai"
      model: "computer-use-preview"  # Required!
      custom_tools:
        - name: ["computer_use"]
          path: "massgen/tool/_computer_use/computer_use_tool.py"
          function: ["computer_use"]
          default_params:
            environment: "browser"
            model: "computer-use-preview"  # Required!
```

### How It Works
1. User provides high-level task description
2. Model receives task + initial screenshot
3. Model plans and executes actions autonomously
4. Loop continues until task complete or max iterations
5. Returns action log and final output

### Supported Environments
- **Browser** - Playwright-based web automation
- **Linux** - Docker container with desktop (xdotool)
- **Mac** - (Future support planned)
- **Windows** - (Future support planned)

### Use Cases
- Complex multi-step workflows
- Research and information gathering
- Form filling with validation
- Web scraping with navigation
- Testing user workflows
- Autonomous task completion

## 2. gemini_computer_use Tool

### Description
Full implementation of Google's Gemini 2.5 Computer Use API that allows the model to autonomously control a browser. Uses Gemini's native computer use capabilities with built-in safety checks.

### Model Requirement
- **MUST use `gemini-2.5-computer-use-preview-10-2025` model**
- Will NOT work with other Gemini models or providers

### Configuration File
- `gemini_computer_use_example.yaml` - Uses Gemini 2.5 Computer Use model

### Example YAML Config
```yaml
agents:
  - id: "gemini_automation_agent"
    backend:
      type: "google"
      model: "gemini-2.5-computer-use-preview-10-2025"  # Required!
      custom_tools:
        - name: ["gemini_computer_use"]
          path: "massgen/tool/_gemini_computer_use/gemini_computer_use_tool.py"
          function: ["gemini_computer_use"]
          default_params:
            environment: "browser"
            display_width: 1440  # Recommended by Gemini
            display_height: 900  # Recommended by Gemini
```

### How It Works
1. User provides high-level task description
2. Model receives task + initial screenshot
3. Gemini plans and executes actions autonomously
4. Loop continues until task complete or max iterations
5. Returns action log and final output

### Supported Environments
- **Browser** - Playwright-based web automation (Chromium recommended)

### Supported Actions
- `open_web_browser` - Open browser
- `click_at` - Click at coordinates (normalized 0-1000)
- `hover_at` - Hover at coordinates
- `type_text_at` - Type text at coordinates
- `key_combination` - Press key combinations
- `scroll_document` - Scroll entire page
- `scroll_at` - Scroll specific area
- `navigate` - Go to URL
- `go_back` / `go_forward` - Browser navigation
- `search` - Go to search engine
- `wait_5_seconds` - Wait for content
- `drag_and_drop` - Drag elements

### Safety Features
- Built-in safety system checks actions
- `require_confirmation` - User must approve risky actions
- Automatically handles safety acknowledgements
- Logs all actions for auditing

### Use Cases
- Complex multi-step workflows
- Research and information gathering
- E-commerce product research
- Form filling with validation
- Web scraping with navigation
- Automated testing

### Prerequisites
- `GOOGLE_API_KEY` environment variable
- `pip install playwright && playwright install`
- `pip install google-genai` (included in requirements.txt)

## 3. browser_automation Tool

### Description
Simple, direct browser automation tool using Playwright. User explicitly controls each action. Works with any LLM model.

### Model Support
- ✅ **gpt-4.1**
- ✅ **gpt-4o**
- ✅ **Gemini**
- ✅ **Claude** (with appropriate backend)
- ✅ Any other model

### Configuration File
- `simple_browser_automation_example.yaml` - Uses `gpt-4.1`

### Example YAML Config
```yaml
agents:
  - id: "browser_agent"
    backend:
      type: "openai"
      model: "gpt-4.1"  # Can be any model!
      custom_tools:
        - name: ["browser_automation"]
          path: "massgen/tool/_browser_automation/browser_automation_tool.py"
          function: ["browser_automation"]
```

### How It Works
1. User calls tool with specific action
2. Tool executes single action immediately
3. Returns result + optional screenshot
4. User decides next action based on result

### Supported Actions
- `navigate` - Go to URL
- `click` - Click element by CSS selector
- `type` - Type text into element
- `extract` - Extract text from elements
- `screenshot` - Capture page image

### Example Usage
```python
# Navigate to a page
await browser_automation(
    task="Open Wikipedia",
    url="https://en.wikipedia.org",
    action="navigate"
)

# Type in search box
await browser_automation(
    task="Search for Jimmy Carter",
    action="type",
    selector="input[name='search']",
    text="Jimmy Carter"
)

# Click search button
await browser_automation(
    task="Click search",
    action="click",
    selector="button[type='submit']"
)

# Extract results
await browser_automation(
    task="Get first paragraph",
    action="extract",
    selector="p.first-paragraph"
)
```

### Use Cases
- Simple page navigation
- Data extraction
- Testing specific actions
- Screenshot capture
- Form interactions
- When you need precise control
- When computer-use-preview is not available

## Decision Guide

### Use `computer_use` when:
- ✅ You have access to `computer-use-preview` model (OpenAI)
- ✅ Task requires multiple autonomous steps
- ✅ Task is complex (e.g., "research topic and create report")
- ✅ You want the model to plan its own actions
- ✅ You need Linux/Docker/OS-level automation

### Use `gemini_computer_use` when:
- ✅ You have access to Gemini 2.5 Computer Use model (Google)
- ✅ You prefer Google's AI models
- ✅ Task requires autonomous browser control
- ✅ You want built-in safety confirmations
- ✅ Task is complex and browser-based

### Use `browser_automation` when:
- ✅ You don't have `computer-use-preview` access
- ✅ Using gpt-4.1, gpt-4o, or other models
- ✅ Task is simple and direct
- ✅ You want explicit control over each action
- ✅ You're testing specific workflows
- ✅ You only need browser automation

## Migration Path

If you're currently blocked by model availability:

**No access to computer-use-preview OR gemini-2.5?**
1. **Switch to `browser_automation`** for immediate functionality with gpt-4.1
2. **Use `simple_browser_automation_example.yaml`** as your config
3. **Break complex tasks into steps** and call the tool for each step

**Have access to Gemini but not OpenAI computer-use-preview?**
1. **Use `gemini_computer_use`** for autonomous workflows
2. **Use `gemini_computer_use_example.yaml`** as your config
3. **Set GOOGLE_API_KEY** in your environment

**When both become available**, choose based on your preferred AI provider and specific feature needs.

## File Structure

```
massgen/
├── tool/
│   ├── _computer_use/              # OpenAI CUA implementation
│   │   ├── __init__.py
│   │   ├── computer_use_tool.py    # Requires computer-use-preview
│   │   ├── README.md
│   │   └── QUICKSTART.md
│   │
│   ├── _gemini_computer_use/       # Google Gemini implementation
│   │   ├── __init__.py
│   │   └── gemini_computer_use_tool.py  # Requires gemini-2.5-computer-use
│   │
│   └── _browser_automation/        # Simple browser tool
│       ├── __init__.py
│       └── browser_automation_tool.py  # Works with any model
│
└── configs/tools/custom_tools/
    ├── computer_use_example.yaml            # OpenAI computer-use-preview
    ├── computer_use_browser_example.yaml    # OpenAI computer-use-preview
    ├── computer_use_docker_example.yaml     # OpenAI computer-use-preview
    ├── computer_use_with_vision.yaml        # OpenAI computer-use-preview
    ├── gemini_computer_use_example.yaml     # Google Gemini 2.5 ⭐
    └── simple_browser_automation_example.yaml  # Any model (gpt-4.1) ⭐
```

## Summary

- **For `computer-use-preview` users**: Use `computer_use` tool (OpenAI)
- **For Gemini 2.5 Computer Use users**: Use `gemini_computer_use` tool (Google)
- **For everyone else**: Use `browser_automation` tool with gpt-4.1 or any other model
- **All three tools** serve different purposes and can coexist in your toolbox
- **Clean separation** ensures no confusion about model requirements

## Getting Started

### Quick Start with browser_automation (gpt-4.1)
```bash
massgen --config simple_browser_automation_example.yaml
```

### Quick Start with gemini_computer_use (Gemini 2.5)
```bash
export GOOGLE_API_KEY="your-api-key"
massgen --config gemini_computer_use_example.yaml
```

### Quick Start with computer_use (computer-use-preview)
```bash
massgen --config computer_use_browser_example.yaml
```

Choose the tool that fits your needs and available models!
