Custom Tools
============

MassGen allows you to give agents access to your own custom Python functions as tools. This enables agents to use your domain-specific functionality, business logic, or specialized algorithms alongside built-in tools and MCP servers.

.. note::

   **Quick Setup Summary:**

   1. Write a Python function that returns ``ExecutionResult``
   2. Reference it in your YAML config under ``custom_tools``
   3. Run MassGen - agents can now use your function

Quick Start: Try It Now
-----------------------

MassGen includes working examples you can try immediately:

.. code-block:: bash

   # Single agent with custom tool
   massgen \
     --config massgen/configs/tools/custom_tools/gemini_custom_tool_example.yaml \
     "What's the sum of 123 and 456?"

   # Custom tool + MCP weather integration
   massgen \
     --config massgen/configs/tools/custom_tools/gemini_custom_tool_with_mcp_example.yaml \
     "What's the sum of 123 and 456? And what's the weather in Tokyo?"

The agent will use the custom ``two_num_tool`` to calculate and respond with "The sum of 123 and 456 is 579".

How The Example Works
~~~~~~~~~~~~~~~~~~~~~~

**The Tool** (``massgen/tool/_basic/_two_num_tool.py``):

.. code-block:: python

   from massgen.tool._result import ExecutionResult, TextContent

   async def two_num_tool(x: int, y: int) -> ExecutionResult:
       """Add two numbers together.

       Args:
           x: First number
           y: Second number

       Returns:
           Sum of the two numbers
       """
       result = x + y
       return ExecutionResult(
           output_blocks=[
               TextContent(data=f"The sum of {x} and {y} is {result}"),
           ],
       )

**The Config** (``gemini_custom_tool_example.yaml``):

.. code-block:: yaml

   agents:
     - id: "gemini2.5flash_custom_tool"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
         custom_tools:
           - name: ["two_num_tool"]
             category: "math"
             path: "massgen/tool/_basic/_two_num_tool.py"
             function: ["two_num_tool"]
       system_message: |
         You are an AI assistant with access to a custom math calculation tool.
         When users ask about adding two numbers together, use the two_num_tool.

   ui:
     display_type: "rich_terminal"

That's the complete pattern! Now let's see how to create your own tools.

How It Works
------------

Custom tools in MassGen follow a simple pattern:

1. **Function Signature**: Write an async function with type hints
2. **Docstring**: Add a Google-style docstring (used for tool description)
3. **Return Type**: Return ``ExecutionResult`` with your output
4. **YAML Config**: Reference the function in your agent's ``custom_tools``

MassGen automatically:

* Generates JSON schema from your function signature
* Makes the tool available to agents
* Handles execution and result streaming
* Works across all backends (Claude, Gemini, OpenAI, etc.)

Creating Your Own Custom Tools
-------------------------------

To create your own custom tool, follow the same pattern as ``two_num_tool``.

Step-by-Step: Create a Custom Tool
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**1. Create your tool file** (e.g., ``my_tools/calculator.py``):

.. code-block:: python

   from massgen.tool import ExecutionResult, TextContent

   async def calculator(operation: str, x: float, y: float) -> ExecutionResult:
       """Perform basic math operations.

       Args:
           operation: The operation (add, subtract, multiply, divide)
           x: First number
           y: Second number

       Returns:
           ExecutionResult with calculation result
       """
       operations = {
           "add": x + y,
           "subtract": x - y,
           "multiply": x * y,
           "divide": x / y if y != 0 else None,
       }

       if operation in operations and operations[operation] is not None:
           result = operations[operation]
           return ExecutionResult(
               output_blocks=[TextContent(data=f"{operation}({x}, {y}) = {result}")]
           )
       else:
           return ExecutionResult(
               output_blocks=[TextContent(data=f"Error: Invalid operation or division by zero")]
           )

**2. Create a config file** (e.g., ``my_calculator_config.yaml``):

.. code-block:: yaml

   agents:
     - id: "calculator_agent"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
         custom_tools:
           - name: ["calculator"]
             category: "math"
             path: "my_tools/calculator.py"
             function: ["calculator"]
       system_message: |
         You are an AI assistant with access to a calculator tool.
         Use it when users ask for math operations.

   ui:
     display_type: "simple"

**3. Run it:**

.. code-block:: bash

   massgen --config my_calculator_config.yaml "What's 15 times 27?"

Basic Tool Structure
~~~~~~~~~~~~~~~~~~~~

Every custom tool follows this pattern:

.. code-block:: python

   from massgen.tool import ExecutionResult, TextContent

   async def my_tool_name(param1: str, param2: int) -> ExecutionResult:
       """Brief description of what this tool does.

       Args:
           param1: Description of first parameter
           param2: Description of second parameter

       Returns:
           ExecutionResult with the tool output
       """
       # Your logic here
       output = f"Processed {param1} with {param2}"

       return ExecutionResult(
           output_blocks=[TextContent(data=output)]
       )

**Key Requirements:**

* Use ``async def`` (even if your function doesn't use await)
* Include type hints for all parameters
* Write a Google-style docstring with Args and Returns sections
* Return ``ExecutionResult`` with at least one content block

Understanding ExecutionResult
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``ExecutionResult`` is the container for all tool outputs. It tells MassGen what to return to the agent.

**Basic Usage:**

.. code-block:: python

   from massgen.tool import ExecutionResult, TextContent

   return ExecutionResult(
       output_blocks=[TextContent(data="Your output here")]
   )

**Available Content Types:**

1. **TextContent** - Plain text output (most common)

   .. code-block:: python

      TextContent(data="The result is 42")

2. **ImageContent** - Base64-encoded image data

   .. code-block:: python

      ImageContent(data="base64_encoded_image_string")

3. **AudioContent** - Base64-encoded audio data

   .. code-block:: python

      AudioContent(data="base64_encoded_audio_string")

**ExecutionResult Parameters:**

.. code-block:: python

   ExecutionResult(
       output_blocks=[...],        # Required: List of content blocks
       meta_info={"key": "value"}, # Optional: Metadata (not shown to agent)
       is_streaming=False,         # Optional: Is this a streaming result?
       is_final=True,              # Optional: Is this the final result?
       was_interrupted=False       # Optional: Was execution interrupted?
   )

Multimodal Results
~~~~~~~~~~~~~~~~~~

Tools can return multiple content types:

.. code-block:: python

   from massgen.tool import ExecutionResult, TextContent, ImageContent

   async def generate_chart(data: list) -> ExecutionResult:
       """Generate a chart from data."""
       # Generate chart (your code here)
       import base64
       chart_base64 = create_chart_image(data)

       return ExecutionResult(
           output_blocks=[
               TextContent(data="Chart generated successfully"),
               ImageContent(data=chart_base64)
           ],
           meta_info={"chart_type": "bar", "data_points": len(data)}
       )

Streaming Results
~~~~~~~~~~~~~~~~~

For long-running operations, stream progress updates:

.. code-block:: python

   from typing import AsyncGenerator
   import asyncio

   async def process_large_dataset(file_path: str) -> AsyncGenerator[ExecutionResult, None]:
       """Process a large dataset with progress updates."""

       # Initial status
       yield ExecutionResult(
           output_blocks=[TextContent(data="Starting processing...")],
           is_streaming=True,
           is_final=False
       )

       # Process in chunks
       for i in range(10):
           await asyncio.sleep(1)  # Simulate work
           yield ExecutionResult(
               output_blocks=[TextContent(data=f"Progress: {(i+1)*10}%")],
               is_streaming=True,
               is_final=False
           )

       # Final result
       yield ExecutionResult(
           output_blocks=[TextContent(data="Processing complete!")],
           is_streaming=True,
           is_final=True
       )

YAML Configuration
------------------

Basic Configuration
~~~~~~~~~~~~~~~~~~~

Reference your tool in the agent's backend config:

.. code-block:: yaml

   agents:
     - id: "agent_id"
       backend:
         type: "claude"
         model: "claude-sonnet-4"
         custom_tools:
           # Reference external file
           - name: "my_function"
             path: "path/to/my_tools.py"
             function: "my_function"
             category: "utilities"

           # Use built-in tool (no path needed)
           - name: "run_python_script"
             function: "run_python_script"

Configuration Options
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   custom_tools:
     - name: "tool_name"              # Unique identifier
       path: "path/to/file.py"        # Path to Python file (optional for built-ins)
       function: "function_name"      # Function name in the file
       category: "category_name"      # Group related tools (optional)
       description: "Tool description"  # Override auto-generated description (optional)

**Multiple Tools Example:**

.. code-block:: yaml

   custom_tools:
     - name: "calculator"
       path: "tools/math.py"
       function: "calculator"
       category: "math"

     - name: "text_analyzer"
       path: "tools/text.py"
       function: "analyze_text"
       category: "text_processing"

     # Use built-in tool
     - name: "run_python_script"
       function: "run_python_script"

Built-in Tool Functions
------------------------

.. important::

   **When to use the standard approach instead:**

   * **File Operations**: Use Claude Code's native tools or :doc:`file_operations` with MCP filesystem servers
   * **Code Execution**: Use backend built-in code execution or :doc:`code_execution` with MCP

   **These built-in functions are primarily for:**

   * Building blocks when creating your own custom tools (import and use them in your code)
   * Backends that don't have native file/code execution support

Available Functions
~~~~~~~~~~~~~~~~~~~

MassGen provides these built-in functions you can import and use in your custom tools as examples or building blocks to show custom tool capabilities:

**Code Execution:**

* ``run_python_script`` - Execute Python code in isolated subprocess
* ``run_shell_script`` - Execute shell commands

**File Operations:**

* ``read_file_content`` - Read files with optional line range
* ``save_file_content`` - Write content to files
* ``append_file_content`` - Append or insert content into files

See :doc:`../api/tools` for complete API documentation of these functions.

Example Configurations
----------------------

MassGen includes 58 working config examples in ``massgen/configs/tools/custom_tools/``. All examples use the ``two_num_tool`` shown above.

Example 1: Claude Code with Custom Tool
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   massgen \
     --config massgen/configs/tools/custom_tools/claude_code_custom_tool_example.yaml \
     "What's the sum of 15 and 27?"

**Config:** ``claude_code_custom_tool_example.yaml``

.. code-block:: yaml

   orchestrator:
     snapshot_storage: "claude_code_snapshots"
     agent_temporary_workspace: "claude_code_temp"

   agents:
     - id: "claude_code_custom_tools"
       backend:
         type: "claude_code"
         model: "claude-sonnet-4-20250514"
         cwd: "claude_code_workspace"
         custom_tools:
           - name: ["two_num_tool"]
             category: "math"
             path: "massgen/tool/_basic/_two_num_tool.py"
             function: ["two_num_tool"]
             description: ["Add two numbers together"]
       append_system_prompt: |
         You are an AI assistant with access to custom calculation tools
         in addition to your built-in Claude Code tools.

   ui:
     display_type: "simple"
     logging_enabled: true

Example 2: Gemini with Custom Tool
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   massgen \
     --config massgen/configs/tools/custom_tools/gemini_custom_tool_example.yaml \
     "What's the sum of 123 and 456?"

**Config:** ``gemini_custom_tool_example.yaml``

.. code-block:: yaml

   agents:
     - id: "gemini2.5flash_custom_tool"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
         custom_tools:
           - name: ["two_num_tool"]
             category: "math"
             path: "massgen/tool/_basic/_two_num_tool.py"
             function: ["two_num_tool"]
       system_message: |
         You are an AI assistant with access to a custom math calculation tool.
         When users ask about adding two numbers together, use the two_num_tool.

   ui:
     display_type: "rich_terminal"
     logging_enabled: true

Example 3: Custom Tool + MCP Integration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   massgen \
     --config massgen/configs/tools/custom_tools/gemini_custom_tool_with_mcp_example.yaml \
     "What's the sum of 123 and 456? And what's the weather in Tokyo?"

**Config:** ``gemini_custom_tool_with_mcp_example.yaml``

.. code-block:: yaml

   agents:
     - id: "gemini2.5flash_custom_tool"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"

         # Custom tools
         custom_tools:
           - name: ["two_num_tool"]
             category: "math"
             path: "massgen/tool/_basic/_two_num_tool.py"
             function: ["two_num_tool"]

         # MCP servers
         mcp_servers:
           - name: "weather"
             type: "stdio"
             command: "npx"
             args: ["-y", "@fak111/weather-mcp"]

       system_message: |
         You are an AI assistant with access to a custom math calculation tool
         and a weather information MCP tool.

   ui:
     display_type: "simple"
     logging_enabled: true

Example 4: Multimodal Understanding Tools
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**New in v0.1.3+**: MassGen provides custom tools for analyzing multimodal content (images, audio, video, documents) using OpenAI's gpt-4.1 API.

.. code-block:: bash

   # Analyze an image
   massgen \
     --config massgen/configs/tools/custom_tools/multimodal_tools/understand_image.yaml \
     "Describe the content in this image"

   # Transcribe audio
   massgen \
     --config massgen/configs/tools/custom_tools/multimodal_tools/understand_audio.yaml \
     "What is being said in this audio?"

   # Analyze video
   massgen \
     --config massgen/configs/tools/custom_tools/multimodal_tools/understand_video.yaml \
     "What's happening in this video?"

   # Process documents
   massgen \
     --config massgen/configs/tools/custom_tools/multimodal_tools/understand_file.yaml \
     "Summarize this PDF document"

**Config Example:** ``understand_image.yaml``

.. code-block:: yaml

   agents:
     - id: "understand_image_tool"
       backend:
         type: "openai"
         model: "gpt-5-nano"
         cwd: "workspace1"
         custom_tools:
           - name: ["understand_image"]
             category: "multimodal"
             path: "massgen/tool/_multimodal_tools/understand_image.py"
             function: ["understand_image"]
       system_message: |
         You are an AI assistant with access to image understanding capabilities.
         Use the understand_image tool to analyze and understand images using OpenAI's gpt-4.1 API.

   orchestrator:
     context_paths:
       - path: "massgen/configs/resources/v0.1.3-example/multimodality.jpg"
         permission: "read"

   ui:
     display_type: "rich_terminal"
     logging_enabled: true

**Available Multimodal Tools:**

* ``understand_image`` - Analyze images (PNG, JPEG, JPG)
* ``understand_audio`` - Transcribe and analyze audio files
* ``understand_video`` - Extract key frames and analyze videos
* ``understand_file`` - Process documents (PDF, DOCX, XLSX, PPTX)

**Key Features:**

* Works with any backend - uses OpenAI's gpt-4.1 for analysis
* Processes files from agent workspaces
* Structured JSON responses with detailed metadata
* Path validation for security

See :doc:`multimodal` for complete multimodal capabilities documentation.

Example 5: Crawl4AI Web Scraping Tools
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**New in v0.1.4**: Docker-based web scraping with multiple output formats via crawl4ai custom tools.

.. code-block:: bash

   # Start crawl4ai Docker container (one-time setup)
   docker pull unclecode/crawl4ai:latest
   docker run -d -p 11235:11235 --name crawl4ai --shm-size=1g unclecode/crawl4ai:latest

   # Use crawl4ai tools
   massgen \
     --config massgen/configs/tools/custom_tools/crawl4ai_example.yaml \
     "Please scrape the MassGen docs, take a screenshot, and explain that screenshot"

**Config Example:** ``crawl4ai_example.yaml``

.. code-block:: yaml

   agents:
     - id: "web_scraper_agent"
       backend:
         type: "openai"
         model: "gpt-5-mini"
         cwd: "workspace1"

         # Register crawl4ai custom tools
         custom_tools:
           - name: ["crawl4ai_md", "crawl4ai_html", "crawl4ai_screenshot", "crawl4ai_pdf", "crawl4ai_execute_js", "crawl4ai_crawl"]
             category: "web_scraping"
             path: "massgen/tool/_web_tools/crawl4ai_tool.py"
             function: ["crawl4ai_md", "crawl4ai_html", "crawl4ai_screenshot", "crawl4ai_pdf", "crawl4ai_execute_js", "crawl4ai_crawl"]

           - name: ["understand_image"]
             category: "multimodal"
             path: "massgen/tool/_multimodal_tools/understand_image.py"
             function: ["understand_image"]

   ui:
     display_type: "rich_terminal"
     logging_enabled: true

**Available Crawl4AI Tools:**

* ``crawl4ai_md`` - Extract clean markdown from web content
* ``crawl4ai_html`` - Get preprocessed HTML
* ``crawl4ai_screenshot`` - Capture webpage screenshots
* ``crawl4ai_pdf`` - Generate PDF documents
* ``crawl4ai_execute_js`` - Run JavaScript on web pages
* ``crawl4ai_crawl`` - Perform multi-URL crawling

**Key Features:**

* Docker-based isolation (no Python dependencies needed)
* Multiple output formats (markdown, HTML, screenshots, PDFs)
* JavaScript execution for dynamic content
* Concurrent crawling (up to 5 simultaneous crawls)
* Automatic Docker health checks with clear error messages

**Requirements:**

* Docker installed and running
* crawl4ai container accessible at ``http://localhost:11235``

If the Docker container isn't running, agents receive a helpful error message with setup instructions.

Example 6: Computer Use Tools
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**New in v0.1.8**: MassGen provides three computer use tools for browser and desktop automation, each optimized for different model providers and use cases.

.. note::

   **Three Tools for Different Needs:**

   * ``gemini_computer_use`` - Google Gemini Computer Use (requires ``gemini-2.5-computer-use-preview-10-2025`` model)
   * ``claude_computer_use`` - Anthropic Claude Computer Use (requires Claude 3.7 Sonnet or newer)
   * ``browser_automation`` - Simple browser automation (works with ANY model: gpt-4.1, gpt-4o, etc.)

**Example 6a: Google Gemini Computer Use (gemini_computer_use)**

For users with access to Google's Gemini 2.5 Computer Use model:

.. code-block:: bash

   massgen \
     --config massgen/configs/tools/custom_tools/gemini_computer_use_example.yaml \
     "Go to cnn.com and get the top headline"

**Config:** ``gemini_computer_use_example.yaml``

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
             default_params:
               environment: "browser"
               display_width: 1440
               display_height: 900

   ui:
     display_type: "rich_terminal"
     logging_enabled: true

**Features:**

* Native Gemini computer use API with built-in safety checks
* Requires user confirmation for risky actions
* Supports extensive action set (click, hover, type, scroll, drag-and-drop, etc.)
* Fast execution (~1-2 seconds per action)
* Browser-based automation

**Supported Actions:**

* ``open_web_browser`` - Open browser
* ``click_at`` / ``hover_at`` - Click/hover at coordinates
* ``type_text_at`` - Type text at coordinates
* ``key_combination`` - Press key combinations
* ``scroll_document`` / ``scroll_at`` - Scroll page or specific area
* ``navigate`` / ``go_back`` / ``go_forward`` - Browser navigation
* ``search`` - Go to search engine
* ``wait_5_seconds`` - Wait for content
* ``drag_and_drop`` - Drag elements

**Example 6b: Anthropic Claude Computer Use (claude_computer_use)**

For users with access to Claude 3.7 Sonnet or newer:

.. code-block:: bash

   massgen \
     --config massgen/configs/tools/custom_tools/claude_computer_use_docker_example.yaml \
     "Navigate to Wikipedia and search for 'Artificial Intelligence'"

**Config:** ``claude_computer_use_docker_example.yaml``

.. code-block:: yaml

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

   ui:
     display_type: "rich_terminal"
     logging_enabled: true

**Features:**

* Anthropic's beta computer use API with enhanced actions
* Extended action set: triple_click, mouse_down/up, hold_key, wait
* Thorough but slower execution (~2-5 seconds per action)
* Supports text editor and bash tools
* Best for complex tasks requiring precision over speed
* Browser and Linux desktop automation

**Supported Actions:**

**Standard Actions:**

* ``screenshot`` - Capture current screen
* ``mouse_move`` / ``left_click`` / ``right_click`` / ``middle_click`` / ``double_click`` - Mouse control
* ``left_click_drag`` - Click and drag
* ``type`` / ``key`` - Text input and key presses
* ``scroll`` - Scroll up/down

**Enhanced Actions (Claude-specific):**

* ``triple_click`` - Triple-click to select lines
* ``left_mouse_down`` / ``left_mouse_up`` - Precise drag control
* ``hold_key`` - Hold key while performing action
* ``wait`` - Wait for specified duration

**Text Editor Actions:**

* ``str_replace_based_edit_tool`` - File editing with find/replace
* ``bash`` - Execute bash commands (if enabled)

**Example 6c: Simple Browser Automation (browser_automation)**

For users with **any model** (gpt-4.1, gpt-4o, gemini-2.5-flash, etc.):

.. code-block:: bash

   massgen \
     --config massgen/configs/tools/custom_tools/simple_browser_automation_example.yaml \
     "Go to Wikipedia and search for Jimmy Carter"

**Config:** ``simple_browser_automation_example.yaml``

.. code-block:: yaml

   agents:
     - id: "browser_agent"
       backend:
         type: "openai"
         model: "gpt-4.1"  # Can be ANY model!
         custom_tools:
           - name: ["browser_automation"]
             path: "massgen/tool/_browser_automation/browser_automation_tool.py"
             function: ["browser_automation"]

   ui:
     display_type: "rich_terminal"
     logging_enabled: true

**Features:**

* Works with **any** model - no special requirements
* Direct Playwright-based browser control
* User explicitly controls each action (not autonomous)
* Very fast execution (~1 second per action)
* Simple action set: navigate, click, type, extract, screenshot
* Best for simple automation and testing

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

**When to Use Which Tool:**

* **Use gemini_computer_use** when you have Google's Gemini 2.5 Computer Use and want fast autonomous workflows with built-in safety
* **Use claude_computer_use** when you have Claude 3.7+ and need thorough, precise execution with enhanced actions
* **Use browser_automation** when using standard models (gpt-4.1, gpt-4o) or want simple, explicit control

**Requirements:**

.. code-block:: bash

   # Install Playwright (required for all computer use tools)
   pip install playwright
   playwright install

   # Set API keys as needed
   export GEMINI_API_KEY="your-key"        # For gemini_computer_use
   export ANTHROPIC_API_KEY="your-key"     # For claude_computer_use

.. seealso::

   * ``massgen/backend/docs/COMPUTER_USE_TOOLS_GUIDE.md`` - Comprehensive guide with performance comparisons, action references, and migration paths
   * ``massgen/tool/_computer_use/README.md`` - Technical implementation details
   * ``massgen/tool/_computer_use/QUICKSTART.md`` - Quick start guide

Available Example Configs
~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``massgen/configs/tools/custom_tools/`` directory contains examples for all backends:

**Basic Custom Tools:**

* **Claude API**: ``claude_custom_tool_example.yaml``
* **Claude Code**: ``claude_code_custom_tool_example.yaml``
* **Gemini**: ``gemini_custom_tool_example.yaml``
* **OpenAI (GPT)**: ``gpt5_nano_custom_tool_example.yaml``, ``gpt_oss_custom_tool_example.yaml``
* **Grok**: ``grok3_mini_custom_tool_example.yaml``
* **Qwen**: ``qwen_api_custom_tool_example.yaml``, ``qwen_local_custom_tool_example.yaml``
* **With MCP**: ``*_custom_tool_with_mcp_example.yaml`` variants for each backend

**Multimodal Understanding Tools:**

* ``multimodal_tools/understand_image.yaml`` - Image analysis
* ``multimodal_tools/understand_audio.yaml`` - Audio transcription
* ``multimodal_tools/understand_video.yaml`` - Video analysis
* ``multimodal_tools/understand_file.yaml`` - Document processing

**Web Scraping Tools:**

* ``crawl4ai_example.yaml`` - Docker-based web scraping with multiple output formats

**Computer Use Tools:**

* ``gemini_computer_use_example.yaml`` - Google Gemini computer use automation
* ``claude_computer_use_docker_example.yaml`` - Anthropic Claude computer use automation
* ``simple_browser_automation_example.yaml`` - Simple browser automation for any model

Backend Support
---------------

Custom tools work with **most** MassGen backends:

**✅ Supported Backends:**

* **OpenAI** (``openai``) - OpenAI's GPT models
* **Claude** (``claude``) - Anthropic's Claude API
* **Claude Code** (``claude_code``) - Claude with native file/code tools
* **Gemini** (``gemini``) - Google's Gemini models
* **Grok** (``grok``) - xAI's Grok models
* **Chat Completions** (``chatcompletion``) - Generic OpenAI-compatible APIs
* **LM Studio** (``lmstudio``) - Local model hosting
* **Inference** (``inference``) - vLLM, SGLang, custom inference servers

**❌ Not Supported:**

* **Azure OpenAI** (``azure_openai``) - Does not implement custom tools interface
* **AG2 Framework** (``ag2``) - Does not implement custom tools interface

**Why Some Backends Don't Support Custom Tools:**

Azure OpenAI and AG2 inherit from the base ``LLMBackend`` class directly without the custom tools layer. These backends focus on their native capabilities rather than custom tool integration.

Troubleshooting
---------------

Tool Not Found
~~~~~~~~~~~~~~

**Error:** ``ToolNotFound: No tool named 'my_tool' exists``

**Solutions:**

* Verify the file path is correct relative to where you run the command
* Check function name matches exactly
* Ensure the function is imported/defined in the file
* Custom tool names are prefixed with ``custom_tool__`` internally

Function Import Errors
~~~~~~~~~~~~~~~~~~~~~~~

**Error:** ``ModuleNotFoundError`` or ``ImportError``

**Solutions:**

* Use relative or absolute paths correctly
* Ensure all imports in your tool file are available
* Check that dependencies are installed

Schema Generation Fails
~~~~~~~~~~~~~~~~~~~~~~~~

**Error:** ``TypeError: cannot create schema for function``

**Solutions:**

* Add type hints to all parameters
* Use ``async def`` even for non-async functions
* Return ``ExecutionResult`` (not plain values)

Tool Execution Errors
~~~~~~~~~~~~~~~~~~~~~~

Check the error in the agent's output. Common issues:

* Missing required parameters
* Wrong parameter types
* Exceptions in your function code

Add error handling to your tools:

.. code-block:: python

   async def safe_tool(param: str) -> ExecutionResult:
       """A tool with error handling."""
       try:
           # Your logic
           result = process(param)
           return ExecutionResult(
               output_blocks=[TextContent(data=f"Success: {result}")]
           )
       except Exception as e:
           return ExecutionResult(
               output_blocks=[TextContent(data=f"Error: {str(e)}")]
           )

Best Practices
--------------

1. **Clear Function Names**: Use descriptive names that indicate what the tool does
2. **Type Hints Required**: Always include type hints for parameters and return type
3. **Detailed Docstrings**: Agents use these to understand when to use your tool
4. **Error Handling**: Return errors as ``ExecutionResult`` rather than raising exceptions
5. **Test Independently**: Test your function works before adding to MassGen
6. **Keep Functions Focused**: One tool should do one thing well
7. **Use Categories**: Group related tools together

Advanced Usage (Developer API)
-------------------------------

.. note::

   **The sections below are for advanced users and developers** who want to programmatically manage tools or understand internal APIs. Most users don't need this.

For most use cases, the YAML configuration above is sufficient. However, if you're building on top of MassGen or need programmatic control, you can use the ``ToolManager`` API.

ToolManager API
~~~~~~~~~~~~~~~

The ``ToolManager`` class provides programmatic control over tools:

.. code-block:: python

   from massgen.tool import ToolManager

   # Create manager
   manager = ToolManager()

   # Add tool from file
   manager.add_tool_function(
       path="my_tools/calculator.py",
       func="calculator",
       category="math"
   )

   # Get available tools
   schemas = manager.fetch_tool_schemas()

   # Execute a tool
   result = await manager.execute_tool({
       "name": "custom_tool__calculator",
       "input": {"operation": "add", "x": 5, "y": 3}
   })

Tool Categories
~~~~~~~~~~~~~~~

Programmatically manage tool categories:

.. code-block:: python

   # Create category
   manager.setup_category(
       category_name="data_science",
       description="Data analysis tools",
       enabled=True
   )

   # Enable/disable categories
   manager.modify_categories(["data_science"], enabled=False)

   # Delete categories
   manager.delete_categories("old_category")

.. seealso::

   :doc:`../api/tools` - Complete ToolManager API reference with all methods, parameters, and examples.

Next Steps
----------

* **Related Guides:**

  * :doc:`mcp_integration` - External tools via MCP
  * :doc:`tools` - Tools and capabilities overview
  * :doc:`backends` - Backend capabilities
  * :doc:`../reference/yaml_schema` - Complete YAML reference

* **Developer API Documentation:**

  For programmatic tool management and internal APIs:

  * :doc:`../api/tools` - Complete Tool System API reference (ToolManager, ExecutionResult, exceptions, built-in tools)

* **Examples:**

  * `Config Examples <https://github.com/Leezekun/MassGen/tree/main/massgen/configs/tools/custom_tools>`_ - 58 configuration examples
  * `Test Examples <https://github.com/Leezekun/MassGen/blob/main/massgen/tests/custom_tools_example.py>`_ - Python usage examples
