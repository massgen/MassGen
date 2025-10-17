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

   # Run MassGen for the first time
   massgen

That's it! On first run, MassGen will launch an interactive setup wizard to help you configure your agents.

.. note::
   **Why the setup wizard?**

   MassGen's power comes from thoughtfully configured multi-agent teams. Rather than requiring you to learn YAML syntax or understand complex configuration options upfront, the wizard guides you through creating an effective setup in minutes. You choose your use case (Research, Coding, Q&A, etc.), select your preferred AI models, and enable tools—all through simple prompts. This ensures you start with a configuration optimized for your needs, which you can refine later as you learn more.

First-Run Experience
~~~~~~~~~~~~~~~~~~~~

When you run ``massgen`` for the first time, you'll see a friendly setup wizard:

.. code-block:: text

   ╔═══════════════════════════════════════════════════════════════╗
   ║       🚀  MassGen Interactive Configuration Builder  🚀       ║
   ║                                                               ║
   ║     Create custom multi-agent configurations in minutes!     ║
   ╚═══════════════════════════════════════════════════════════════╝

   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
     Step 1 of 4: Select Your Use Case
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

   Choose your use case:
   1. Simple Q&A - Basic question answering
   2. Research & Analysis - Multi-agent research with web search
   3. Filesystem + Code Execution - Generate, test, and modify code
   4. Filesystem + Code Execution (Docker) - Secure isolated execution
   5. Data Analysis - Analyze data with code execution and visualizations
   6. Creative Writing - Collaborative creative content generation
   7. Web Automation - Browser automation and web scraping with MCP
   8. Custom Configuration - Full flexibility

   ✅ Selected: Research & Analysis

   ╔════════════════════════════════ Preset Configuration ═════════════════════════════╗
   ║                                                                                    ║
   ║   Features auto-configured for this preset:                                       ║
   ║                                                                                    ║
   ║     ✓ Web Search                                                                  ║
   ║       • Real-time internet search for current information                         ║
   ║       • Fact-checking and source verification                                     ║
   ║       • Available for: OpenAI, Claude, Gemini, Grok                               ║
   ║                                                                                    ║
   ║     ✓ Multi-Agent Collaboration                                                   ║
   ║       • 3 agents recommended for diverse perspectives                             ║
   ║       • Cross-verification of facts and sources                                   ║
   ║                                                                                    ║
   ║   Use this for: Research queries, current events, fact-checking                   ║
   ║                                                                                    ║
   ╚════════════════════════════════════════════════════════════════════════════════════╝

   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
     Step 2 of 4: Agent Setup
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

   Available providers:
   • ✅ OpenAI - gpt-5, gpt-5-mini, gpt-5-nano...
   • ✅ Claude - claude-sonnet-4-20250514, claude-opus-4-20250514...
   • ✅ Gemini - gemini-2.5-flash, gemini-2.5-pro...
   • ❌ Claude Code - Need: ANTHROPIC_API_KEY

   How many agents? 3 agents (recommended for diverse perspectives)
   Select provider: OpenAI

   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
     Step 3 of 4: Agent Configuration
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

   Select models for your agents:
   Agent 1: gpt-5-mini
   Agent 2: gpt-5-mini
   Agent 3: gpt-5-mini

   ✅ 3 agent(s) configured with preset

   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
     ✅  Review & Save Configuration
   ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

   ✅ Configuration saved to: ~/.config/massgen/config.yaml

Your configuration is saved to ``~/.config/massgen/config.yaml`` and will be used for all future runs.

Understanding Preset Configurations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The wizard offers several **preset configurations** that auto-configure tools and capabilities for common use cases:

**Simple Q&A**
  Basic question answering with no special tools. Start with 1 agent for straightforward queries, or add more for diverse perspectives. No auto-configuration needed.

**Research & Analysis** *(Auto-configured)*
  * ✓ **Web Search**: Real-time internet search for current information, fact-checking, and source verification
  * ✓ **Multi-Agent**: 3 agents recommended for diverse perspectives and cross-verification
  * Use for: Research queries, current events, fact-checking, comparative analysis

**Filesystem + Code Execution** *(Auto-configured)*
  * ✓ **Filesystem Access**: File read/write operations in isolated workspace
  * ✓ **Code Execution**: OpenAI Code Interpreter or Claude/Gemini native code execution
  * Use for: Code generation, refactoring, testing, file operations

**Filesystem + Code Execution (Docker)** *(Auto-configured)*
  * ✓ **Filesystem Access**: File read/write operations
  * ✓ **Code Execution**: Backend-native code execution
  * ✓ **Docker Isolation**: Fully isolated container execution, persistent packages, network controls
  * ⚠️ Requires: Docker Engine 28.0.0+, docker Python library, massgen-executor image
  * Use for: Secure code execution with full isolation and persistent dependencies

**Data Analysis** *(Auto-configured)*
  * ✓ **Filesystem Access**: Read/write data files (CSV, JSON, etc.), save visualizations
  * ✓ **Code Execution**: Data processing, statistical analysis, visualization generation
  * ✓ **Image Understanding**: Analyze charts, graphs, and visualizations from images
  * Use for: Data analysis, chart interpretation, statistical processing, visualization

**Deep Reasoning & Problem Solving** *(Auto-configured)*
  * ✓ **Extended Reasoning**: Deep thinking for complex problems with chain-of-thought reasoning
  * ✓ **Web Search**: Real-time information retrieval and fact verification
  * Best with: OpenAI GPT-5, o4, or o4-mini models
  * Use for: Complex problem solving, mathematical proofs, logic puzzles, strategic planning

**Multimodal Analysis** *(Auto-configured)*
  * ✓ **Image Understanding**: Analyze images, screenshots, charts, OCR and text extraction
  * ✓ **Audio Understanding**: Transcribe and analyze audio (where supported)
  * ✓ **Video Understanding**: Analyze video content (where supported)
  * Note: Different backends support different modalities
  * Use for: Image analysis, screenshot interpretation, multimedia content analysis

**Creative Writing**
  Multiple agents collaborate for diverse creative ideas, styles, and perspectives. No special tools—pure creativity.

**Web Automation** *(Partial auto-configuration)*
  * ⚠ **MCP Servers**: Manual setup required for browser automation (Playwright MCP)
  * ✓ **Filesystem Access**: Save scraped data and screenshots
  * Use for: Web scraping, browser automation, screenshot capture, form filling

**Custom Configuration**
  Full flexibility to choose any combination of agents, models, and tools. You'll configure everything manually.

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
   massgen --config @examples/basic_multi "Compare renewable energy sources"

   # Start interactive multi-turn mode
   massgen

Example Configurations
~~~~~~~~~~~~~~~~~~~~~~

MassGen ships with ready-to-use example configurations:

.. code-block:: bash

   # List all available examples
   massgen --list-examples

   # Use an example configuration
   massgen --config @examples/basic_single "Your question"
   massgen --config @examples/research_team "Research query"

   # Copy an example to customize
   massgen --example basic_multi > my-config.yaml

See :doc:`configuration` for more details on customizing configurations.

**Method 2: Development Installation** (For Contributors)
----------------------------------------------------------

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
   massgen --config @examples/basic_multi "Complex question"

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

   ~/.config/massgen/
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
   # - Or save as a named config in ~/.config/massgen/agents/

API Key Configuration
---------------------

MassGen looks for API keys in the following order:

1. Environment variables (``OPENAI_API_KEY``, ``ANTHROPIC_API_KEY``, etc.)
2. ``~/.config/massgen/.env`` file (created by setup wizard)
3. Project-specific ``.env`` file in current directory

To set up API keys manually:

.. code-block:: bash

   # Create or edit the .env file
   vim ~/.config/massgen/.env

   # Add your API keys
   OPENAI_API_KEY=sk-your-key-here
   ANTHROPIC_API_KEY=sk-ant-your-key
   GOOGLE_API_KEY=your-gemini-key
   XAI_API_KEY=xai-your-key

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

   cmd /c %USERPROFILE%/.lmstudio/bin/lms.exe bootstrap

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

   # Or check if a config already exists
   ls ~/.config/massgen/config.yaml

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

1. Check your ``.env`` file exists: ``~/.config/massgen/.env``
2. Verify the key is correctly named (e.g., ``OPENAI_API_KEY``)
3. Re-run the wizard: ``massgen --init``

For more help, visit our `GitHub Issues <https://github.com/Leezekun/MassGen/issues>`_ or join our community.

Backwards Compatibility
=======================

For Existing Users
------------------

If you previously used MassGen via git clone, **all your existing workflows continue to work**:

.. code-block:: bash

   # Old command syntax still works
   cd /path/to/MassGen
   python -m massgen.cli --config massgen/configs/basic/multi/three_agents_default.yaml "Question"

   # New command syntax (simpler)
   massgen --config @examples/basic_multi "Question"

You can install MassGen globally via pip even if you have a git clone:

.. code-block:: bash

   cd /path/to/MassGen
   pip install -e .  # Editable install

   # Now you can use 'massgen' from anywhere
   cd ~/other-project
   massgen "Question"

**Command Compatibility:**

* ✅ ``massgen`` - New simplified command (recommended)
* ✅ ``python -m massgen.cli`` - Old command syntax (still works)
* ✅ Old config paths (``massgen/configs/...``) work interchangeably with new paths (``@examples/...``)
