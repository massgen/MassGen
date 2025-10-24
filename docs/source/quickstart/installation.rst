============
Installation
============

Prerequisites
=============

MassGen requires **Python 3.11 or higher**. You can check your Python version with:

.. code-block:: bash

   python --version

If you need to install or upgrade Python, visit `python.org/downloads <https://www.python.org/downloads/>`_.

Quick Start Installation
========================

**Method 1: PyPI Installation** (Recommended)
----------------------------------------------

The easiest way to get started with MassGen is via pip or uv:

.. code-block:: bash

   # Install MassGen with uv (recommended - faster)
   uv pip install massgen

   # Or with pip
   pip install massgen

Getting Started - Complete First-Run Flow
------------------------------------------

**The simplest way to start:** Just run ``massgen`` and you'll be guided through everything:

.. code-block:: bash

   massgen

**What happens next:**

1. **API Key Setup** (only if needed)

   * MassGen detects if you have cloud provider API keys configured
   * If not, shows an interactive wizard to configure OpenAI, Anthropic, Google, etc.
   * Keys are saved to ``~/.config/massgen/.env`` for future use
   * If you already have keys, this step is skipped automatically

2. **Choose Your Configuration**

   You'll see two options:

   * **📦 Browse ready-to-use configs/examples** - Select from 100+ pre-built configurations
   * **Build from template** - Create custom agents with guided setup (Simple Q&A, Research & Analysis, Code & Files, etc.)

3. **Save as Default** (optional)

   * When browsing existing configs or examples, you'll be asked: "Save this as your default config?"
   * Choose **Yes** to use it automatically on future ``massgen`` runs
   * Choose **No** to try it once without saving

4. **Start Chatting Immediately**

   * After selection, you're **launched directly into interactive mode**
   * Multi-turn conversation with your chosen configuration
   * Type your questions and get collaborative agent responses
   * Session history is automatically saved

**After first-run setup:**

.. code-block:: bash

   # Start conversation with your default config
   massgen

   # Or run a single query
   massgen "Your question here"

.. tip::
   **The entire flow takes 1-2 minutes.** You'll be in an interactive conversation with your agents immediately after setup!

Supported API Key Providers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Main backends:**

* OpenAI, Anthropic (Claude), Google Gemini, xAI (Grok)
* Azure OpenAI

**ChatCompletion providers:**

* Cerebras AI, Together AI, Fireworks AI, Groq, Nebius AI Studio, OpenRouter
* ZAI (Zhipu.ai), Kimi/Moonshot AI, POE, Qwen (Alibaba)

.. note::
   You can skip all providers if you're using local models (vLLM, Ollama, etc.) which don't require API keys.

Manual API Key Setup (Optional)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If you prefer to set up API keys manually before running MassGen:

.. code-block:: bash

   # Unix/Mac: Create the .env file
   mkdir -p ~/.config/massgen
   vim ~/.config/massgen/.env

   # Windows: Create the .env file
   mkdir %USERPROFILE%\.config\massgen
   notepad %USERPROFILE%\.config\massgen\.env

   # Add your API keys (same format for all platforms)
   OPENAI_API_KEY=sk-your-key-here
   ANTHROPIC_API_KEY=sk-ant-your-key
   GEMINI_API_KEY=your-gemini-key
   XAI_API_KEY=xai-your-key

**Complete API Key Reference:**

.. code-block:: bash

   # Main backends
   OPENAI_API_KEY=sk-...
   ANTHROPIC_API_KEY=sk-ant-...
   GEMINI_API_KEY=...
   XAI_API_KEY=xai-...

   # Azure
   AZURE_OPENAI_API_KEY=...
   AZURE_OPENAI_ENDPOINT=...

   # ChatCompletion providers
   CEREBRAS_API_KEY=...
   TOGETHER_API_KEY=...
   FIREWORKS_API_KEY=...
   GROQ_API_KEY=...
   NEBIUS_API_KEY=...
   OPENROUTER_API_KEY=...
   ZAI_API_KEY=...
   MOONSHOT_API_KEY=...        # Also accepts KIMI_API_KEY
   POE_API_KEY=...
   QWEN_API_KEY=...

MassGen API Key Lookup Order
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

MassGen looks for API keys in this order:

1. Environment variables (``OPENAI_API_KEY``, ``ANTHROPIC_API_KEY``, etc.)
2. ``~/.config/massgen/.env`` (user config - recommended)
3. Project-specific ``.env`` file in current directory (highest priority)

Reconfiguring API Keys
~~~~~~~~~~~~~~~~~~~~~~~

You can re-run the API key wizard anytime:

.. code-block:: bash

   # Launch API key setup
   massgen --setup

First-Run Setup Flow Walkthrough
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When you run ``massgen`` for the first time, here's what you'll see:

.. code-block:: text

   ╔══════════════════════════════════════════════════════════╗
   ║             👋  Welcome to MassGen!                      ║
   ╚══════════════════════════════════════════════════════════╝

   ✅ API keys detected

   Let's set up your default configuration...

   Step 1 of 4: Select Your Use Case

   Browse ready-to-use configs, or pick a template to build your own.

 » 📦  Browse ready-to-use configs / examples

   ─ or build from template ─

   ⚙️  Custom Configuration           [Choose your own tools]
   💬  Simple Q&A                     [Basic chat (no special tools)]
   🔍  Research & Analysis            [Web search enabled]
   💻  Code & Files                   [File ops + code execution]
   🐳  Code & Files (Docker)          [File ops + isolated Docker execution]
   📊  Data Analysis                  [Files + code + image analysis]
   🎨  Multimodal Analysis            [Images, audio, video understanding]

**Option 1: Browse Ready-to-Use Configs** (Fastest)

Select this to browse 100+ pre-built configurations organized by category:

.. code-block:: text

   📦  Browse ready-to-use configs / examples

   ┌─────────────────────────────────────────────────────────┐
   │ 👤 Your Configs                    1                    │
   │ 📂 Project Configs                 0                    │
   │ 📂 Current Directory               2                    │
   │ 📦 Package Examples                107                  │
   └─────────────────────────────────────────────────────────┘

   Select a configuration:
   » three_agents_default.yaml  (3 agents, diverse perspectives)
     research_team.yaml          (Web search + analysis)
     coding_assistant.yaml       (File ops + code execution)

After selecting, you'll be asked:

.. code-block:: text

   📦 You selected a package example
      /path/to/massgen/configs/basic/multi/three_agents_default.yaml

   Save this as your default config? [y/N]:

* Choose **y** to save and use automatically on future runs
* Choose **n** to try it once without saving

Then immediately launches into interactive mode! 🚀

**Option 2: Build from Template** (Customized)

Select a template to create a custom configuration with guided setup:

.. code-block:: text

   🔍  Research & Analysis            [Web search enabled]

   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
     Step 2 of 4: Agent Setup
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

   Available providers:
   • ✅ OpenAI - gpt-5, gpt-5-mini, gpt-5-nano...
   • ✅ Claude - claude-sonnet-4, claude-opus-4...
   • ✅ Gemini - gemini-2.5-flash, gemini-2.5-pro...

   How many agents? 3 agents (recommended)
   Select provider: OpenAI
   Select models: gpt-5-mini, gpt-5-mini, gpt-5-mini

   ✅ Configuration saved to: ~/.config/massgen/config.yaml

   🚀 Launching interactive mode...

Your configuration is saved to ``~/.config/massgen/config.yaml`` and will be used for all future runs.

Available Build Templates
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The wizard offers several **preset configurations** that auto-configure tools and capabilities for common use cases:

**Custom Configuration**
  Full flexibility to choose any combination of agents, models, and tools. You'll configure everything manually.
  * Choose your own tools
  * Use for: Specialized workflows with specific requirements

**Simple Q&A**
  Basic question answering with multiple perspectives. No special tools configured.
  * Multiple agents provide diverse perspectives and cross-verification
  * Use for: General questions, discussions, brainstorming

**Research & Analysis** *(Auto-configured)*
  * ✓ **Web Search**: Real-time internet search for current information, fact-checking, and source verification
  * ✓ **Multi-Agent Collaboration**: 3 agents recommended for diverse perspectives and cross-verification
  * Available for: OpenAI, Claude, Gemini, Grok
  * Use for: Research queries, current events, fact-checking, comparative analysis

**Code & Files** *(Auto-configured)*
  * ✓ **Filesystem Access**: File read/write operations in isolated workspace
  * ✓ **Code Execution**: OpenAI Code Interpreter or Claude/Gemini native code execution
  * Claude Code recommended for best filesystem support
  * Use for: Code generation, refactoring, testing, file operations

**Code & Files (Docker)** *(Auto-configured)*
  * ✓ **Filesystem Access**: File read/write operations
  * ✓ **Code Execution**: Backend-native code execution
  * ✓ **Docker Isolation**: Fully isolated container execution via MCP, persistent packages, network controls
  * ⚠️ **Setup Required**: Docker Engine 28.0.0+, docker Python library, and massgen-executor image (see massgen/docker/README.md)
  * Use for: Secure code execution with full isolation and persistent dependencies

**Data Analysis** *(Auto-configured)*
  * ✓ **Filesystem Access**: Read/write data files (CSV, JSON, etc.), save visualizations
  * ✓ **Code Execution**: Data processing, transformation, statistical analysis, visualization generation
  * ✓ **Image Understanding**: Analyze charts, graphs, and visualizations; extract data from images
  * Available for: OpenAI, Claude Code, Gemini, Azure OpenAI
  * Use for: Data analysis, chart interpretation, statistical processing, visualization

**Multimodal Analysis** *(Auto-configured)*
  * ✓ **Image Understanding**: Analyze images, screenshots, charts; OCR and text extraction
    * Available for: OpenAI, Claude Code, Gemini, Azure OpenAI
  * ✓ **Audio Understanding**: Transcribe and analyze audio (where supported)
    * Available for: Claude, ChatCompletion
  * ✓ **Video Understanding**: Analyze video content (where supported)
    * Available for: Claude, ChatCompletion, OpenAI
  * Note: Different backends support different modalities
  * Use for: Image analysis, screenshot interpretation, multimedia content analysis

.. note::
   Presets marked *(Auto-configured)* automatically enable specific tools and capabilities during setup. You can still customize further if needed.

Quick Usage Examples
~~~~~~~~~~~~~~~~~~~

After setup, using MassGen is simple:

.. code-block:: bash

   # Use your default configuration
   massgen "What is quantum computing?"

   # Override with a specific model for this query
   massgen --model gpt-5-mini "Quick question"

   # Use a pre-built example configuration
   massgen --config @examples/basic/multi/three_agents_default "Compare renewable energy sources"

   # Start interactive multi-turn mode
   massgen

Example Configurations
~~~~~~~~~~~~~~~~~~~~~~

MassGen ships with ready-to-use example configurations:

.. code-block:: bash

   # List all available examples
   massgen --list-examples

   # Use an example configuration
   massgen --config @examples/basic/single/single_gpt5nano "Your question"
   massgen --config @examples/research_team "Research query"

   # Copy an example to customize
   massgen --example basic_multi > my-config.yaml

See :doc:`configuration` for more details on customizing configurations.

**Method 2: Development Installation** (For Developers)
-------------------------------------------------------

If you want to contribute to MassGen or customize the source code:

.. code-block:: bash

   # Clone the repository
   git clone https://github.com/Leezekun/MassGen.git
   cd MassGen

   # Install in editable mode
   pip install -e .

   # Or with uv (faster)
   pip install uv
   uv pip install -e .

Development installation gives you:

- 🔄 **Live changes**: Edits are immediately reflected
- 🛠️ **Full source access**: Modify any part of MassGen
- 📦 **All features**: Same as pip install, but with source code

**Using uv tool for Multi-Turn Sessions**

For the best experience with multi-turn conversations and working across different project directories, install MassGen as a uv tool:

.. code-block:: bash

   # Install as a global uv tool (from MassGen directory)
   cd MassGen
   uv tool install -e .

   # Now you can use massgen from anywhere
   cd ~/your-project
   massgen  # Start interactive multi-turn session

   # Sessions are saved to .massgen/sessions/ in your current directory
   # Context is preserved across turns automatically

**Benefits of uv tool for multi-turn:**

- 🌍 **Global Access**: Run ``massgen`` from any directory
- 💬 **Session Isolation**: Each project gets its own ``.massgen/sessions/`` directory
- 📁 **Clean Workspaces**: Sessions and workspaces stay organized per-project
- 🔄 **Live Updates**: Changes to MassGen source are immediately available (editable mode)

See :doc:`../user_guide/multi_turn_mode` for complete multi-turn conversation documentation.

Using MassGen After Installation
=================================

After installing via either method, you can use MassGen in several ways:

Command Line Interface
----------------------

.. code-block:: bash

   # Single query with default config
   massgen "Your question"

   # Interactive multi-turn mode
   massgen

   # Quick single-agent mode
   massgen --model gemini-2.5-flash "Quick question"

   # Use example configuration
   massgen --config @examples/basic/multi/three_agents_default "Complex question"

   # Use custom configuration file
   massgen --config ./my-agents.yaml "Your question"

Python API
----------

MassGen provides a simple async Python API:

.. code-block:: python

   import asyncio
   import massgen

   # Quick single-agent query
   result = await massgen.run(
       query="What is machine learning?",
       model="gpt-5-mini"
   )
   print(result['final_answer'])

   # Multi-agent with configuration
   result = await massgen.run(
       query="Analyze climate change trends",
       config="@examples/research_team"
   )

   # Or from sync code
   result = asyncio.run(
       massgen.run("Question", model="gemini-2.5-flash")
   )

See :doc:`../reference/python_api` for complete API documentation.

Configuration Management
========================

Configuration Files Location
----------------------------

MassGen uses the following directory structure:

.. code-block:: text

   ~/.config/massgen/                        # Windows: %USERPROFILE%\.config\massgen\
   ├── config.yaml              # Your default configuration (from wizard)
   ├── agents/                  # Your custom named configurations
   │   ├── research-team.yaml
   │   └── coding-agents.yaml
   └── .env                     # API keys (optional)

The ``config.yaml`` file is created by the setup wizard and used by default when you run ``massgen`` without specifying a config.

Reconfiguring MassGen
----------------------

You can re-run the setup wizard anytime:

.. code-block:: bash

   # Launch configuration wizard
   massgen --init

   # This will:
   # - Let you create a new default config (overwrites existing)
   # - Or save as a named config in ~/.config/massgen/agents/ (Windows: %USERPROFILE%\.config\massgen\agents\)

Understanding the .massgen Directory
=====================================

MassGen organizes all its working files in a ``.massgen/`` directory within your project. This keeps your project clean and makes it easy to exclude MassGen files from version control by adding ``.massgen/`` to your ``.gitignore``.

**What's inside?**

- ``sessions/`` - Multi-turn conversation history
- ``workspaces/`` - Agent working directories for file operations
- ``snapshots/`` - Workspace snapshots shared between agents
- ``temp_workspaces/`` - Previous turn results for context

**When is it created?**

The ``.massgen/`` directory is automatically created when you use multi-turn mode, file operations, or workspace features. Simple single-agent queries don't create it.

.. seealso::
   For a complete explanation of workspace management and directory structure, see :doc:`../user_guide/concepts` (State Management & .massgen Directory section)

Optional Dependencies
=====================

AG2 Framework Integration
--------------------------

If you want to use AG2 agents alongside native MassGen agents:

.. code-block:: bash

   pip install massgen[external]

This is **only required** if you plan to use AG2 configuration files.

Optional CLI Tools
==================

Enhanced Capabilities
---------------------

Install these optional tools for enhanced MassGen capabilities:

Claude Code CLI
~~~~~~~~~~~~~~~

Advanced coding assistant with comprehensive development tools:

.. code-block:: bash

   npm install -g @anthropic-ai/claude-code

LM Studio
~~~~~~~~~

Local model inference for running open-weight models:

**For MacOS/Linux:**

.. code-block:: bash

   sudo ~/.lmstudio/bin/lms bootstrap

**For Windows:**

.. code-block:: bash

   cmd /c %USERPROFILE%\.lmstudio\bin\lms.exe bootstrap

Verification Steps
==================

After installation, verify MassGen is correctly installed:

.. code-block:: bash

   # Check MassGen is available
   massgen --help

You should see the MassGen CLI help message with all available options.

Quick Test
----------

Try a simple query to verify everything works:

.. code-block:: bash

   # Single agent mode (no config needed)
   massgen --model gemini-2.5-flash "What is MassGen?"

   # Or run the wizard and try your default config
   massgen "Tell me about multi-agent systems"

Next Steps
==========

**Great! You've installed MassGen. Here's your learning path:**

✅ **You are here:** Installation complete

⬜ **Next:** :doc:`running-massgen` - Run your first command and see MassGen in action

⬜ **Then:** :doc:`configuration` - Learn how to customize agent teams

⬜ **Advanced:** :doc:`../user_guide/multi_turn_mode` - Explore interactive conversations

**Quick jump:** Want to dive into examples? Check out :doc:`../examples/basic_examples` for copy-paste configurations.

Troubleshooting
===============

Setup Wizard Not Appearing
---------------------------

If the wizard doesn't appear on first run:

.. code-block:: bash

   # Manually trigger the setup wizard
   massgen --init

   # Or check if a config already exists (Unix/Mac)
   ls ~/.config/massgen/config.yaml

   # Windows
   dir %USERPROFILE%\.config\massgen\config.yaml

To start fresh, remove the existing config and run again.

Python Version Issues
---------------------

If you encounter Python version errors:

.. code-block:: bash

   # Check your Python version
   python --version

   # If below 3.11, install a newer version from python.org
   # Then reinstall MassGen
   pip install --upgrade massgen

Missing Example Configurations
-------------------------------

If ``--list-examples`` shows no results:

.. code-block:: bash

   # Reinstall MassGen to ensure package data is included
   pip install --force-reinstall massgen

   # Verify installation
   massgen --list-examples

API Key Errors
--------------

If you see "API key not found" errors:

1. Check your ``.env`` file exists:

   * Unix/Mac: ``~/.config/massgen/.env``
   * Windows: ``%USERPROFILE%\.config\massgen\.env``

2. Verify the key is correctly named (e.g., ``OPENAI_API_KEY``)
3. Re-run the wizard: ``massgen --init``

For more help, visit our `GitHub Issues <https://github.com/Leezekun/MassGen/issues>`_ or join our community.

.. note::
   **Existing MassGen users:** If you previously used MassGen via git clone, all your existing workflows continue to work. See :doc:`running-massgen` (Backwards Compatibility section) for details on command syntax and migration.
