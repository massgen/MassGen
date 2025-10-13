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

The easiest way to get started with MassGen is via pip:

.. code-block:: bash

   # Install MassGen
   pip install massgen

   # Run MassGen for the first time
   massgen

That's it! On first run, MassGen will launch an interactive setup wizard to help you configure your agents.

First-Run Experience
~~~~~~~~~~~~~~~~~~~~

When you run ``massgen`` for the first time, you'll see a friendly setup wizard:

.. code-block:: text

   ╔═══════════════════════════════════════════════════════════╗
   ║   🚀 MassGen Interactive Configuration Builder 🚀        ║
   ║                                                           ║
   ║   Create custom multi-agent configurations in minutes!   ║
   ╚═══════════════════════════════════════════════════════════╝

   Step 1: Select Your Use Case
   -----------------------------
   1. Simple Q&A
   2. Research & Analysis
   3. Code Generation & Development
   4. Creative Writing
   5. Data Analysis
   6. Web Automation
   7. Custom Configuration

   Step 2: Configure Agents
   -------------------------
   Available providers:
   1. OpenAI (GPT-5, GPT-4, etc.) ✅
   2. Anthropic Claude ✅
   3. Google Gemini ✅
   4. xAI Grok ❌ (API key not found)
   ...

   Step 3: Configure Tools & Capabilities
   ---------------------------------------
   Enable web search? [Y/n]: y
   Enable code execution? [Y/n]: y
   Enable filesystem operations? [Y/n]: n
   ...

   Step 4: Review & Save Configuration
   ------------------------------------
   ✅ Configuration saved to: ~/.config/massgen/config.yaml

   Run with: massgen "Your question"

Your configuration is saved to ``~/.config/massgen/config.yaml`` and will be used for all future runs.

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

Multi-Turn Filesystem Setup
============================

Understanding the .massgen Directory
------------------------------------

When you work with MassGen using multi-turn conversations or file operations, MassGen automatically creates a clean, organized directory structure:

.. code-block:: text

   your-project/
   ├── .massgen/                          # All MassGen state
   │   ├── sessions/                      # Multi-turn conversation history
   │   │   └── session_20240101_143022/
   │   │       ├── turn_1/                # Results from turn 1
   │   │       ├── turn_2/                # Results from turn 2
   │   │       └── SESSION_SUMMARY.txt    # Human-readable summary
   │   ├── workspaces/                    # Agent working directories
   │   │   ├── agent1/                    # Individual agent workspaces
   │   │   └── agent2/
   │   ├── snapshots/                     # Workspace snapshots for coordination
   │   └── temp_workspaces/               # Previous turn results for context
   ├── your-project-files/
   └── ...

Benefits of .massgen Organization
----------------------------------

.. grid:: 2
   :gutter: 3

   .. grid-item-card:: 🧹 Clean Projects

      All MassGen files are contained in a single ``.massgen/`` directory, keeping your project organized.

   .. grid-item-card:: 📝 Easy .gitignore

      Simply add ``.massgen/`` to your ``.gitignore`` file to exclude all MassGen working files from version control.

   .. grid-item-card:: 🚚 Portable

      Move or delete the ``.massgen/`` directory without affecting your project files.

   .. grid-item-card:: 💬 Session Persistence

      Multi-turn conversation history is preserved across sessions for continuity.

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

Now that you have MassGen installed, you're ready to:

1. :doc:`running-massgen` - Learn how to run MassGen with different configurations
2. :doc:`configuration` - Understand configuration options and customization
3. :doc:`../user_guide/multi_turn_mode` - Explore multi-turn interactive conversations
4. :doc:`../reference/python_api` - Use MassGen programmatically from Python

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

   # Old commands still work
   cd /path/to/MassGen
   uv run python -m massgen.cli --config massgen/configs/basic/multi/three_agents_default.yaml "Question"

   # New commands also work in the same directory
   massgen --config @examples/basic_multi "Question"

You can install MassGen globally via pip even if you have a git clone:

.. code-block:: bash

   cd /path/to/MassGen
   pip install -e .  # Editable install

   # Now you can use 'massgen' from anywhere
   cd ~/other-project
   massgen "Question"

Both old paths (``massgen/configs/...``) and new paths (``@examples/...``) work interchangeably.
