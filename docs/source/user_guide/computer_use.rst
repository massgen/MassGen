Computer Use Tools
==================

MassGen provides powerful computer use tools that allow AI agents to autonomously control browsers and desktop environments. These tools enable agents to browse websites, interact with applications, execute commands, and complete complex multi-step workflows.

.. note::

   **Three Tools for Different Needs:**

   * ``gemini_computer_use`` - Google Gemini Computer Use (requires ``gemini-2.5-computer-use-preview-10-2025`` model)
   * ``claude_computer_use`` - Anthropic Claude Computer Use (requires ``claude-sonnet-4-5`` or newer)
   * ``browser_automation`` - Simple browser automation (works with ANY model: gpt-4.1, gpt-4o, etc.)

Overview
--------

Computer use tools transform AI agents from text processors into active automation systems capable of:

* **Browser Automation** - Navigate websites, fill forms, extract data, search for information
* **Desktop Control** - Interact with applications, manage files, execute system commands
* **Visual Understanding** - Take screenshots and use visual feedback to guide actions
* **Multi-Step Workflows** - Chain together complex sequences of actions autonomously

Tool Comparison
---------------

.. list-table::
   :header-rows: 1
   :widths: 20 20 20 20 20

   * - Feature
     - ``computer_use``
     - ``gemini_computer_use``
     - ``claude_computer_use``
     - ``browser_automation``
   * - **Model Support**
     - ``computer-use-preview`` only
     - ``gemini-2.5-computer-use-preview`` only
     - ``claude-sonnet-4-5`` or newer
     - Any model
   * - **Provider**
     - OpenAI
     - Google
     - Anthropic
     - Any
   * - **Environments**
     - Browser, Linux, Mac, Windows
     - Browser, Linux
     - Browser, Linux
     - Browser only
   * - **Action Planning**
     - Autonomous multi-step
     - Autonomous multi-step
     - Autonomous multi-step
     - User-directed
   * - **Complexity**
     - High (full agentic)
     - High (full agentic)
     - High (full agentic)
     - Low (simple)
   * - **Safety Checks**
     - Built-in
     - Built-in + confirmations
     - Built-in
     - Manual
   * - **Performance**
     - Fast (~1-2 sec/action)
     - Fast (~1-2 sec/action)
     - Thorough (~2-5 sec/action)
     - Very Fast (~1 sec)
   * - **Best Use Case**
     - Complex workflows (OpenAI)
     - Complex workflows (Google)
     - Precision tasks (Anthropic)
     - Simple automation

Quick Start
-----------

**1. Simple Browser Automation (Works with Any Model)**

.. code-block:: bash

   # Install dependencies
   pip install playwright
   playwright install

   # Run with gpt-4.1 or any other model
   massgen \
     --config massgen/configs/tools/custom_tools/simple_browser_automation_example.yaml \
     "Go to Wikipedia and search for Jimmy Carter"

**2. Gemini Computer Use**

Browser automation:

.. code-block:: bash

   # Set API key
   export GEMINI_API_KEY="your-api-key"

   # Run Gemini browser automation
   massgen \
     --config massgen/configs/tools/custom_tools/gemini_computer_use_example.yaml \
     "Go to cnn.com and get the top headline"

Docker/Linux desktop automation:

.. code-block:: bash

   # Set API key
   export GEMINI_API_KEY="your-api-key"

   # Setup Docker container (one-time)
   ./scripts/setup_docker_cua.sh

   # Run Gemini desktop automation
   massgen \
     --config massgen/configs/tools/custom_tools/gemini_computer_use_docker_example.yaml \
     "Open Firefox and search for Python documentation"

**3. Claude Computer Use (Docker/Linux)**

.. code-block:: bash

   # Set API key
   export ANTHROPIC_API_KEY="your-api-key"

   # Setup Docker container (one-time)
   ./scripts/setup_docker_cua.sh

   # Run Claude desktop automation
   massgen \
     --config massgen/configs/tools/custom_tools/claude_computer_use_docker_example.yaml \
     "Navigate to Wikipedia and search for Artificial Intelligence"

Detailed Tool Guides
--------------------

1. Gemini Computer Use
~~~~~~~~~~~~~~~~~~~~~~

**Description:** Full implementation of Google's Gemini 2.5 Computer Use API with native computer control capabilities and built-in safety checks.

**Model Requirement:**

* **MUST use** ``gemini-2.5-computer-use-preview-10-2025`` model
* Will NOT work with other Gemini models

**Example Configuration (Browser)**

.. code-block:: yaml

   agents:
     - id: "gemini_automation_agent"
       backend:
         type: "google"
         model: "gemini-2.5-computer-use-preview-10-2025"  # Required!
         custom_tools:
           - name: ["gemini_computer_use"]
             path: "massgen/tool/_gemini_computer_use/gemini_computer_use_tool.py"
             function: ["gemini_computer_use"]
             preset_args:
               environment: "browser"
               display_width: 1440  # Recommended by Gemini
               display_height: 900  # Recommended by Gemini
               environment_config:
                 headless: false  # Set to true for headless
                 browser_type: "chromium"

   ui:
     display_type: "rich_terminal"

**Supported Actions:**

* ``open_web_browser`` - Open browser
* ``click_at`` - Click at coordinates (normalized 0-1000)
* ``hover_at`` - Hover at coordinates
* ``type_text_at`` - Type text at coordinates
* ``key_combination`` - Press key combinations
* ``scroll_document`` - Scroll entire page
* ``scroll_at`` - Scroll specific area
* ``navigate`` - Go to URL
* ``go_back`` / ``go_forward`` - Browser navigation
* ``search`` - Go to search engine
* ``wait_5_seconds`` - Wait for content
* ``drag_and_drop`` - Drag elements

**Safety Features:**

* Built-in safety system checks all actions
* ``require_confirmation`` - User must approve risky actions
* Automatically handles safety acknowledgements
* All actions logged for auditing

**Use Cases:**

* Complex multi-step browser workflows
* Research and information gathering
* E-commerce product research
* Form filling with validation
* Web scraping with navigation
* Automated testing

**Supported Environments:**

* **Browser** - Playwright-based web automation (Chromium recommended)
* **Linux/Docker** - Desktop automation in Docker container (xdotool)

**Example Docker Configuration:**

.. code-block:: yaml

   agents:
     - id: "gemini_desktop_agent"
       backend:
         type: "openai"  # Orchestration backend
         model: "gpt-4.1"
         custom_tools:
           - name: ["gemini_computer_use"]
             path: "massgen/tool/_gemini_computer_use/gemini_computer_use_tool.py"
             function: ["gemini_computer_use"]
             preset_args:
               environment: "linux"  # Use Docker
               display_width: 1024
               display_height: 768
               max_iterations: 30
               environment_config:
                 container_name: "cua-container"
                 display: ":99"

**Prerequisites:**

* ``GEMINI_API_KEY`` environment variable
* For browser: ``pip install playwright && playwright install``
* For Docker: Docker running + ``./scripts/setup_docker_cua.sh``
* ``pip install google-genai docker`` (included in requirements.txt)

2. Claude Computer Use
~~~~~~~~~~~~~~~~~~~~~~~

**Description:** Full implementation of Anthropic's Claude Computer Use API with enhanced actions and thorough execution capabilities.

**Model Requirement:**

* **Recommended:** ``claude-sonnet-4-5`` (latest with computer use)
* Compatible with Claude models supporting computer use
* Will NOT work with older Claude models

**Example Configuration (Docker/Linux)**

.. code-block:: yaml

   agents:
     - id: "claude_automation_agent"
       backend:
         type: "anthropic"
         model: "claude-sonnet-4-5"  # Recommended!
         custom_tools:
           - name: ["claude_computer_use"]
             path: "massgen/tool/_claude_computer_use/claude_computer_use_tool.py"
             function: ["claude_computer_use"]
             preset_args:
               environment: "linux"
               display_width: 1024
               display_height: 768
               max_iterations: 25
               environment_config:
                 container_name: "cua-container"
                 display: ":99"

**Example Configuration (Browser)**

.. code-block:: yaml

   agents:
     - id: "claude_browser_agent"
       backend:
         type: "anthropic"
         model: "claude-sonnet-4-5"
         custom_tools:
           - name: ["claude_computer_use"]
             path: "massgen/tool/_claude_computer_use/claude_computer_use_tool.py"
             function: ["claude_computer_use"]
             preset_args:
               environment: "browser"
               display_width: 1024
               display_height: 768
               max_iterations: 25
               headless: false  # Set to true for headless
               browser_type: "chromium"

**Supported Actions:**

**Standard Actions:**

* ``screenshot`` - Capture current screen
* ``mouse_move`` - Move mouse to coordinates
* ``left_click`` / ``right_click`` / ``middle_click`` / ``double_click`` - Mouse control
* ``left_click_drag`` - Click and drag
* ``type`` - Type text
* ``key`` - Press single key
* ``scroll`` - Scroll up/down

**Enhanced Actions (Claude-specific):**

* ``triple_click`` - Triple-click to select lines
* ``left_mouse_down`` / ``left_mouse_up`` - Precise drag control
* ``hold_key`` - Hold key while performing action
* ``wait`` - Wait for specified duration

**Text Editor Actions:**

* ``str_replace_based_edit_tool`` - File editing with find/replace
* ``bash`` - Execute bash commands (if enabled)

**Supported Environments:**

* **Browser** - Playwright-based web automation (Chromium)
* **Linux** - Docker container with desktop (xdotool, similar to OpenAI implementation)

**Performance Characteristics:**

* **Thorough but slower**: ~2-5 seconds per action (vs 1-2 sec for other tools)
* **High iteration count**: Typically 25-40 iterations for simple web tasks
* **Recommended for**: Complex tasks where thoroughness matters more than speed
* **Not recommended for**: Simple tasks requiring quick execution

Example Performance:

.. code-block:: text

   Task: "Go to cnn.com and get the top headline"
   - Claude Computer Use: 25-40 iterations, ~60-100 seconds
   - Browser Automation: 2-3 actions, ~5-10 seconds

**Choose based on task complexity vs speed requirements.**

**Headless Mode:**

* **Automatically enforced** on Linux servers without DISPLAY environment variable
* **Can be overridden** for systems with X server
* Check logs: "Forcing headless mode on Linux without X server"

**Use Cases:**

* ✅ Complex research requiring deep navigation
* ✅ Multi-step workflows with verification
* ✅ Tasks requiring precision and thoroughness
* ✅ When using Anthropic's ecosystem
* ❌ Simple/quick automation tasks (use ``browser_automation`` instead)

**Prerequisites:**

* ``ANTHROPIC_API_KEY`` environment variable
* ``pip install playwright && playwright install``
* ``pip install anthropic`` (included in requirements.txt)
* Python 3.8+

3. Browser Automation
~~~~~~~~~~~~~~~~~~~~~

**Description:** Simple, direct browser automation tool using Playwright. User explicitly controls each action. Works with any LLM model.

**Model Support:**

* ✅ **gpt-4.1**
* ✅ **gpt-4o**
* ✅ **Gemini**
* ✅ **Claude** (with appropriate backend)
* ✅ Any other model

**Example Configuration:**

.. code-block:: yaml

   agents:
     - id: "browser_agent"
       backend:
         type: "openai"
         model: "gpt-4.1"  # Can be any model!
         custom_tools:
           - name: ["browser_automation"]
             path: "massgen/tool/_browser_automation/browser_automation_tool.py"
             function: ["browser_automation"]

   ui:
     display_type: "rich_terminal"

**Supported Actions:**

* ``navigate`` - Go to URL
* ``click`` - Click element by CSS selector
* ``type`` - Type text into element
* ``extract`` - Extract text from elements
* ``screenshot`` - Capture page image

**Example Usage:**

.. code-block:: python

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

**Use Cases:**

* Simple page navigation
* Data extraction
* Testing specific actions
* Screenshot capture
* Form interactions
* When you need precise control
* When specialized computer use models are not available

Decision Guide
--------------

When to Use Each Tool
~~~~~~~~~~~~~~~~~~~~~

**Use** ``computer_use`` **when:**

* ✅ You have access to ``computer-use-preview`` model (OpenAI)
* ✅ Task requires multiple autonomous steps
* ✅ Task is complex (e.g., "research topic and create report")
* ✅ You want the model to plan its own actions
* ✅ You need Linux/Docker/OS-level automation
* ✅ You need fast execution (1-2 sec/action)

**Use** ``gemini_computer_use`` **when:**

* ✅ You have access to Gemini 2.5 Computer Use model (Google)
* ✅ You prefer Google's AI models
* ✅ Task requires autonomous browser control
* ✅ You want built-in safety confirmations
* ✅ Task is complex and browser-based
* ✅ You need fast execution (1-2 sec/action)

**Use** ``claude_computer_use`` **when:**

* ✅ You have access to Claude Sonnet 4.5 or newer (Anthropic)
* ✅ You prefer Anthropic's AI models
* ✅ Task requires thorough, careful execution
* ✅ Task is complex and multi-step
* ✅ Quality and precision matter more than speed
* ✅ You need enhanced actions (triple_click, mouse_down/up, hold_key)
* ⚠️ Accept ~2-5 sec/action and 25-40+ iterations

**Use** ``browser_automation`` **when:**

* ✅ You don't have specialized computer use model access
* ✅ Using gpt-4.1, gpt-4o, or other standard models
* ✅ Task is simple and direct
* ✅ You want explicit control over each action
* ✅ You're testing specific workflows
* ✅ You only need browser automation
* ✅ You need very fast execution (~1 sec/action)

Performance Quick Reference
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 25 20 25 30

   * - Tool
     - Speed/Action
     - Iterations (Simple Task)
     - Best For
   * - ``browser_automation``
     - ~1 sec
     - 2-5
     - Simple tasks, explicit control
   * - ``computer_use``
     - ~1-2 sec
     - 10-20
     - Complex OpenAI workflows
   * - ``gemini_computer_use``
     - ~1-2 sec
     - 10-20
     - Complex Google workflows
   * - ``claude_computer_use``
     - ~2-5 sec
     - 25-40
     - Thorough Anthropic workflows

Visualization and Monitoring
-----------------------------

Visualizing computer use agents helps you understand what they're doing in real-time and debug issues.

VNC Viewer (Docker/Linux)
~~~~~~~~~~~~~~~~~~~~~~~~~~

For Claude Computer Use in Docker, you can watch the desktop in real-time using VNC.

**Quick Setup:**

.. code-block:: bash

   # 1. Enable VNC on the Docker container
   ./scripts/enable_vnc_viewer.sh

   # 2. Install a VNC viewer (one-time setup)
   # Ubuntu/Debian:
   sudo apt-get install tigervnc-viewer
   # Or:
   sudo snap install remmina

   # 3. Connect to the container
   # Get container IP:
   docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' cua-container
   # Connect with: <container-ip>:5900

**What You'll See:**

* Real-time desktop with Xfce window manager
* Mouse movements and clicks as the agent executes actions
* Terminal windows opening for bash commands
* Applications launching (Firefox, text editors, etc.)
* File browser operations
* All desktop interactions in real-time

Non-Headless Browser Mode
~~~~~~~~~~~~~~~~~~~~~~~~~~

For Gemini and Claude browser automation, watch the browser by disabling headless mode.

**Update Configuration:**

Use ``preset_args`` (not ``default_params``):

.. code-block:: yaml

   # For Gemini Computer Use
   custom_tools:
     - name: ["gemini_computer_use"]
       path: "massgen/tool/_gemini_computer_use/gemini_computer_use_tool.py"
       function: ["gemini_computer_use"]
       preset_args:
         environment: "browser"
         display_width: 1440
         display_height: 900
         environment_config:
           headless: false  # Set to false for visible browser
           browser_type: "chromium"

   # For Claude Computer Use (browser mode)
   custom_tools:
     - name: ["claude_computer_use"]
       path: "massgen/tool/_claude_computer_use/claude_computer_use_tool.py"
       function: ["claude_computer_use"]
       preset_args:
         environment: "browser"
         headless: false  # Set to false for visible browser

**Running with Visible Browser:**

.. important::

   You must set the ``DISPLAY`` environment variable when running:

.. code-block:: bash

   # Check your available displays
   ls /tmp/.X11-unix/
   # Shows: X0, X20, etc.

   # Run MassGen with DISPLAY variable (example using :20)
   DISPLAY=:20 massgen --config gemini_computer_use_example.yaml

   # For Claude browser
   DISPLAY=:20 massgen --config claude_computer_use_browser_example.yaml

**What You'll See:**

* Actual browser window opens on your desktop
* For Claude: Browser opens with Google homepage loaded
* For Gemini: Browser opens at specified URL or blank page
* Pages loading and navigation
* Form filling and clicking in real-time
* Scrolling and text entry
* Mouse movements and interactions

**Requirements:**

* X11 display server running (check with ``echo $DISPLAY``)
* Desktop environment (GUI) or X server available
* DISPLAY environment variable set (e.g., ``:0``, ``:20``)
* Cannot run on headless servers without X forwarding or Xvfb

**Using Xvfb (Virtual Display on Headless Servers):**

.. code-block:: bash

   # Install Xvfb
   sudo apt-get install xvfb

   # Start virtual display
   Xvfb :20 -screen 0 1440x900x24 &

   # Run with visible browser on virtual display
   DISPLAY=:20 massgen --config config.yaml

   # To see it, use VNC or x11vnc
   x11vnc -display :20 -forever -shared -rfbport 5900 -nopw &
   vncviewer localhost:5900

Terminal Output Monitoring
~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Real-time Logs:**

.. code-block:: bash

   # Watch MassGen logs in real-time
   tail -f massgen_logs/log_*/agent_chat.log

   # Watch tool execution
   tail -f massgen_logs/log_*/tool_calls.log

**Verbose Mode:**

.. code-block:: bash

   # Enable debug logging
   export MASSGEN_LOG_LEVEL=DEBUG
   massgen --config config.yaml

Multi-Agent Computer Use
-------------------------

You can combine multiple computer use tools in a single configuration for complex workflows.

**Example: Claude (Desktop) + Gemini (Browser)**

.. code-block:: yaml

   agents:
     # Agent 1: Claude Computer Use with Docker
     - id: "claude_desktop_agent"
       backend:
         type: "claude"
         model: "claude-sonnet-4-5"
         betas: ["computer-use-2025-01-24"]
         custom_tools:
           - name: ["claude_computer_use"]
             path: "massgen/tool/_claude_computer_use/claude_computer_use_tool.py"
             function: ["claude_computer_use"]
             preset_args:
               environment: "linux"
               display_width: 1024
               display_height: 768
               max_iterations: 30

       system_message: |
         You are a Linux desktop automation specialist.
         Your specialty: File operations, bash scripts, system-level tasks.

     # Agent 2: Gemini Computer Use with Browser
     - id: "gemini_browser_agent"
       backend:
         type: "openai"
         model: "gpt-4.1"
         custom_tools:
           - name: ["gemini_computer_use"]
             path: "massgen/tool/_gemini_computer_use/gemini_computer_use_tool.py"
             function: ["gemini_computer_use"]
             preset_args:
               environment: "browser"
               display_width: 1440
               display_height: 900
               environment_config:
                 headless: false
                 browser_type: "chromium"

       system_message: |
         You are a web research and browser automation specialist.
         Your specialty: Web browsing, data extraction, online research.

**Example Use Cases:**

* "Search for the latest Python releases on the web, then create a summary document"
* "Download a file from the web and process it with a bash script"
* "Research information online and save it to a file on the desktop"

Troubleshooting
---------------

Common Configuration Mistake
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Issue:** Browser always runs in headless mode even with ``headless: false``

**Solution:** MassGen's custom tools use ``preset_args``, NOT ``default_params``:

.. code-block:: yaml

   # ❌ WRONG - Will not work
   custom_tools:
     - name: ["gemini_computer_use"]
       default_params:
         environment_config:
           headless: false

   # ✅ CORRECT - Use preset_args
   custom_tools:
     - name: ["gemini_computer_use"]
       preset_args:
         environment: "browser"
         display_width: 1440
         display_height: 900
         environment_config:
           headless: false
           browser_type: "chromium"

VNC Issues
~~~~~~~~~~

.. code-block:: bash

   # Check if VNC is running
   docker exec cua-container ps aux | grep x11vnc

   # Restart VNC
   docker exec cua-container pkill x11vnc
   ./scripts/enable_vnc_viewer.sh

   # Check firewall
   sudo ufw allow 5900/tcp

Browser Not Showing
~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   # 1. Check DISPLAY variable is set
   echo $DISPLAY
   # Should show something like: :0 or :20

   # 2. List available displays
   ls /tmp/.X11-unix/
   # Shows: X0, X20, etc.

   # 3. Test with simple X app
   DISPLAY=:20 xeyes  # Should open a window

   # 4. If no DISPLAY, create virtual display
   Xvfb :20 -screen 0 1440x900x24 &
   export DISPLAY=:20

   # 5. Verify config uses preset_args (not default_params)
   grep -A5 "preset_args" your_config.yaml

   # 6. Ensure headless: false in environment_config
   grep "headless" your_config.yaml

Best Practices
--------------

1. **Development:** Use VNC + non-headless browser for debugging
2. **Testing:** Use terminal logs with occasional screenshots
3. **Production:** Use headless mode with comprehensive logging
4. **Demos:** Record sessions with VNC/browser recording
5. **Remote Work:** Use X11 forwarding or VNC over SSH tunnel
6. **Iteration Limits:** Set appropriate ``max_iterations`` based on task complexity
7. **Safety:** Test actions in isolated environments before production use
8. **Error Handling:** Monitor logs for errors and adjust configurations

File Structure
--------------

.. code-block:: text

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
   │   │   └── gemini_computer_use_tool.py
   │   │
   │   ├── _claude_computer_use/       # Anthropic Claude implementation
   │   │   ├── __init__.py
   │   │   └── claude_computer_use_tool.py
   │   │
   │   └── _browser_automation/        # Simple browser tool
   │       ├── __init__.py
   │       └── browser_automation_tool.py
   │
   └── configs/tools/custom_tools/
       ├── gemini_computer_use_example.yaml
       ├── gemini_computer_use_docker_example.yaml
       ├── claude_computer_use_docker_example.yaml
       ├── claude_computer_use_browser_example.yaml
       ├── simple_browser_automation_example.yaml
       └── multi_agent_computer_use_example.yaml

Next Steps
----------

* **Related Guides:**

  * :doc:`custom_tools` - Learn about creating custom tools
  * :doc:`multimodal` - Multimodal capabilities
  * :doc:`mcp_integration` - External tools via MCP
  * :doc:`../reference/yaml_schema` - Complete YAML reference

* **Configuration Examples:**

  * `Computer Use Examples <https://github.com/Leezekun/MassGen/tree/main/massgen/configs/tools/custom_tools>`_
  * ``massgen/backend/docs/COMPUTER_USE_TOOLS_GUIDE.md`` - Comprehensive implementation guide
  * ``massgen/backend/docs/COMPUTER_USE_VISUALIZATION.md`` - Visualization guide

* **Setup Guides:**

  * ``scripts/computer_use_setup.md`` - Docker installation guide
  * ``./scripts/setup_docker_cua.sh`` - Docker setup script
  * ``./scripts/enable_vnc_viewer.sh`` - VNC visualization setup
