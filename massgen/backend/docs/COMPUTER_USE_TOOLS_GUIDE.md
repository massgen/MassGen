# Computer Use Tools Guide

This document explains the four different computer use tools available in MassGen and when to use each.

## Overview

MassGen provides four separate tools for computer automation:

1. **`computer_use`** - Full OpenAI Computer Using Agent (CUA) implementation
2. **`gemini_computer_use`** - Google Gemini 2.5 Computer Use implementation
3. **`claude_computer_use`** - Anthropic Claude Computer Use implementation
4. **`browser_automation`** - Simple browser automation for any model

## Tool Comparison

| Feature | `computer_use` | `gemini_computer_use` | `claude_computer_use` | `browser_automation` |
|---------|----------------|----------------------|----------------------|---------------------|
| **Model Support** | `computer-use-preview` only | `gemini-2.5-computer-use-preview-10-2025` only | `claude-3-7-sonnet-20250219` or newer | Any model (gpt-4.1, gpt-4o, etc.) |
| **Provider** | OpenAI | Google | Anthropic | Any |
| **Environments** | Browser, Linux/Docker, Mac, Windows | Browser only | Browser, Linux/Docker | Browser only |
| **Implementation** | OpenAI hosted tool with CUA loop | Gemini native computer use API | Anthropic Computer Use API | Direct Playwright automation |
| **Action Planning** | Autonomous multi-step | Autonomous multi-step | Autonomous multi-step | User directs each action |
| **Complexity** | High (full agentic control) | High (full agentic control) | High (full agentic control) | Low (simple commands) |
| **Safety Checks** | Built-in | Built-in with confirmations | Built-in | Manual |
| **Enhanced Actions** | Standard | Standard | Extended (triple_click, mouse_down/up, hold_key, wait) | Standard |
| **Performance** | Fast (~1-2 sec/action) | Fast (~1-2 sec/action) | Thorough (~2-5 sec/action) | Very Fast (~1 sec/action) |
| **Use Case** | Complex workflows (OpenAI) | Complex workflows (Google) | Complex workflows (Anthropic) | Simple automation, testing |

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

## 3. claude_computer_use Tool

### Description
Full implementation of Anthropic's Claude Computer Use API that allows the model to autonomously control a browser or desktop environment. Uses Claude's native computer use capabilities with the beta API.

### Model Requirement
- **Recommended: `claude-3-7-sonnet-20250219`** (latest with computer use)
- **Compatible with Claude models supporting computer use**
- Will NOT work with older Claude models

### Configuration File
- `claude_computer_use_docker_example.yaml` - Uses Claude 3.7 Sonnet
- `claude_computer_use_browser_example.yaml` - Uses Claude 3.7 Sonnet

### Example YAML Config
```yaml
agents:
  - id: "claude_automation_agent"
    backend:
      type: "anthropic"
      model: "claude-3-7-sonnet-20250219"  # Recommended!
      custom_tools:
        - name: ["claude_computer_use"]
          path: "massgen/tool/_claude_computer_use/claude_computer_use_tool.py"
          function: ["claude_computer_use"]
          preset_args:
            environment: "linux"
            environment_config:
              container_name: "cua-container"
              display: ":99"
            # For browser environment:
            # environment: "linux"
            # preset_args:
            #   environment: "browser"
            #   headless: true
            # default_params:
            #   display_width: 1024
            #   display_height: 768
            #   max_iterations: 25
```

### How It Works
1. User provides high-level task description
2. Model receives task + initial screenshot
3. Claude plans and executes actions autonomously using tool calls
4. Loop continues until task complete or max iterations (typically 25-40 for simple tasks)
5. Returns detailed action log and final output

### Supported Environments
- **Browser** - Playwright-based web automation (Chromium)
- **Linux** - Docker container with desktop (xdotool, similar to OpenAI implementation)

### Supported Actions

**Standard Actions:**
- `screenshot` - Capture current screen
- `mouse_move` - Move mouse to coordinates
- `left_click` - Click at coordinates
- `left_click_drag` - Click and drag
- `right_click` - Right-click at coordinates
- `middle_click` - Middle-click at coordinates
- `double_click` - Double-click at coordinates
- `type` - Type text
- `key` - Press single key
- `scroll` - Scroll up/down

**Enhanced Actions (Claude-specific):**
- `triple_click` - Triple-click to select lines
- `left_mouse_down` / `left_mouse_up` - Precise drag control
- `hold_key` - Hold key while performing action
- `wait` - Wait for specified duration

**Text Editor Actions:**
- `str_replace_based_edit_tool` - File editing with find/replace
- `bash` - Execute bash commands (if enabled)

### Tool Types
Claude uses versioned tool types:
- `computer_20250124` - Computer control tool
- `text_editor_20250728` - Text editor tool
- `bash_20250124` - Bash command tool

### Performance Characteristics
- **Thorough but slower**: ~2-5 seconds per action (vs 1-2 sec for other tools)
- **High iteration count**: Typically 25-40 iterations for simple web tasks
- **Recommended for**: Complex tasks where thoroughness matters more than speed
- **Not recommended for**: Simple tasks requiring quick execution

### Example Performance
```
Task: "Go to cnn.com and get the top headline"
- Claude Computer Use: 25-40 iterations, ~60-100 seconds
- Browser Automation: 2-3 actions, ~5-10 seconds
```

**Choose based on task complexity vs speed requirements.**

### Headless Mode
- **Automatically enforced on Linux servers** without DISPLAY environment variable
- **Can be overridden** for systems with X server
- Check logs: "Forcing headless mode on Linux without X server"

### Safety Features
- Uses Anthropic's beta API with `computer-use-2025-01-24` betas
- All actions logged for auditing
- Screenshot after each action for verification
- Supports tool use confirmation workflows

### Use Cases
- ✅ Complex research requiring deep navigation
- ✅ Multi-step workflows with verification
- ✅ Tasks requiring precision and thoroughness
- ✅ When using Anthropic's ecosystem
- ❌ Simple/quick automation tasks (use `browser_automation` instead)

### Prerequisites
- `ANTHROPIC_API_KEY` environment variable
- `pip install playwright && playwright install`
- `pip install anthropic` (included in requirements.txt)
- Python 3.8+

### Example Usage
```python
result = await claude_computer_use(
    task="Navigate to Wikipedia and search for 'Artificial Intelligence'",
    display_width=1280,
    display_height=800,
    max_iterations=50
)
```

## 4. browser_automation Tool

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
- ✅ You need fast execution (1-2 sec/action)

### Use `gemini_computer_use` when:
- ✅ You have access to Gemini 2.5 Computer Use model (Google)
- ✅ You prefer Google's AI models
- ✅ Task requires autonomous browser control
- ✅ You want built-in safety confirmations
- ✅ Task is complex and browser-based
- ✅ You need fast execution (1-2 sec/action)

### Use `claude_computer_use` when:
- ✅ You have access to Claude 3.7 Sonnet or newer (Anthropic)
- ✅ You prefer Anthropic's AI models
- ✅ Task requires thorough, careful execution
- ✅ Task is complex and multi-step
- ✅ Quality and precision matter more than speed
- ✅ You need enhanced actions (triple_click, mouse_down/up, hold_key)
- ⚠️ Accept ~2-5 sec/action and 25-40+ iterations

### Use `browser_automation` when:
- ✅ You don't have specialized computer use model access
- ✅ Using gpt-4.1, gpt-4o, or other standard models
- ✅ Task is simple and direct
- ✅ You want explicit control over each action
- ✅ You're testing specific workflows
- ✅ You only need browser automation
- ✅ You need very fast execution (~1 sec/action)

## Migration Path

If you're currently blocked by model availability:

**No access to specialized computer use models?**
1. **Switch to `browser_automation`** for immediate functionality with gpt-4.1
2. **Use `simple_browser_automation_example.yaml`** as your config
3. **Break complex tasks into steps** and call the tool for each step

**Have access to Gemini but not OpenAI/Claude?**
1. **Use `gemini_computer_use`** for autonomous workflows
2. **Use `gemini_computer_use_example.yaml`** as your config
3. **Set GOOGLE_API_KEY** in your environment

**Have access to Claude but not OpenAI/Gemini?**
1. **Use `claude_computer_use`** for thorough autonomous workflows
2. **Use `claude_computer_use_docker_example.yaml`** as your config
3. **Set ANTHROPIC_API_KEY** in your environment
4. **Plan for 2-5x longer execution time** vs other tools

**When multiple options are available**, choose based on:
- **Speed priority**: OpenAI > Gemini > Claude >> Browser Automation
- **Thoroughness priority**: Claude > Gemini > OpenAI
- **Simplicity priority**: Browser Automation
- **Provider preference**: Your ecosystem choice

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
│   ├── _claude_computer_use/       # Anthropic Claude implementation
│   │   ├── __init__.py
│   │   └── claude_computer_use_tool.py  # Requires claude-3-7-sonnet+
│   │
│   └── _browser_automation/        # Simple browser tool
│       ├── __init__.py
│       └── browser_automation_tool.py  # Works with any model
│
└── configs/tools/custom_tools/
    ├── computer_use_example.yaml                # OpenAI computer-use-preview
    ├── computer_use_browser_example.yaml        # OpenAI computer-use-preview
    ├── computer_use_docker_example.yaml         # OpenAI computer-use-preview
    ├── computer_use_with_vision.yaml            # OpenAI computer-use-preview
    ├── gemini_computer_use_example.yaml         # Google Gemini 2.5 ⭐
    ├── claude_computer_use_docker_example.yaml         # Anthropic Claude 3.7+ ⭐
    ├── claude_computer_use_browser_example.yaml         # Anthropic Claude 3.7+ ⭐
    └── simple_browser_automation_example.yaml   # Any model (gpt-4.1) ⭐
```

## Summary

- **For `computer-use-preview` users**: Use `computer_use` tool (OpenAI) - Fast & powerful
- **For Gemini 2.5 Computer Use users**: Use `gemini_computer_use` tool (Google) - Fast with safety
- **For Claude 3.7+ users**: Use `claude_computer_use` tool (Anthropic) - Thorough & precise
- **For everyone else**: Use `browser_automation` tool with gpt-4.1 or any other model
- **All four tools** serve different purposes and can coexist in your toolbox
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

### Quick Start with claude_computer_use (Claude 3.7)
```bash
export ANTHROPIC_API_KEY="your-api-key"
massgen --config claude_computer_use_docker_example.yaml
```

### Quick Start with computer_use (computer-use-preview)
```bash
massgen --config computer_use_browser_example.yaml
```

## Performance Quick Reference

| Tool | Speed/Action | Iterations (Simple Task) | Best For |
|------|-------------|-------------------------|----------|
| `browser_automation` | ~1 sec | 2-5 | Simple tasks, explicit control |
| `computer_use` | ~1-2 sec | 10-20 | Complex OpenAI workflows |
| `gemini_computer_use` | ~1-2 sec | 10-20 | Complex Google workflows |
| `claude_computer_use` | ~2-5 sec | 25-40 | Thorough, complex Anthropic workflows |

Choose the tool that fits your needs, available models, and performance requirements!
