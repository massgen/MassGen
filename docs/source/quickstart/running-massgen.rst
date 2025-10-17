Running MassGen
===============

This guide shows you how to run MassGen with different configurations.

.. tip::
   **Configuration File Paths:** Example commands use ``@examples/...`` paths which work from **any directory** because they're part of MassGen's installed package. See `Configuration File Paths`_ below for all path options.

Basic Usage
-----------

Run MassGen from the command line:

.. code-block:: bash

   massgen [OPTIONS] ["<your question>"]

For the complete list of CLI parameters and options, see :doc:`../reference/cli`

Default Configuration Mode
---------------------------

The simplest way to use MassGen - no configuration needed on first run:

.. code-block:: bash

   # First time: Launches setup wizard
   massgen

The wizard helps you:

* Configure API keys for your preferred AI models
* Create your default agent team
* Save configuration to ``~/.config/massgen/config.yaml`` (Windows: ``%USERPROFILE%\.config\massgen\config.yaml``)

**After setup:**

.. code-block:: bash

   # Start interactive conversation
   massgen

   # Or run a single query
   massgen "What is machine learning?"

Your default configuration is automatically used when you run ``massgen`` without ``--config`` or ``--model`` flags.

Single Agent (Quick Test)
--------------------------

The fastest way to test MassGen - no configuration file needed:

.. code-block:: bash

   # Quick test with any supported model
   massgen --model claude-3-5-sonnet-latest "What is machine learning?"
   massgen --model gemini-2.5-flash "Explain quantum computing"
   massgen --model gpt-5-nano "Summarize the latest AI developments"

**With specific backend:**

.. code-block:: bash

   massgen \
     --backend gemini \
     --model gemini-2.5-flash \
     "What are the latest developments in AI?"

.. seealso::
   :doc:`configuration` - Complete configuration reference for all setup options

Multi-Agent Collaboration
--------------------------

The recommended way to use MassGen - multiple agents working together:

.. code-block:: bash

   # Three powerful agents collaborate
   massgen \
     --config @examples/basic/multi/three_agents_default.yaml \
     "Analyze the pros and cons of renewable energy"

This configuration uses:

* **Gemini 2.5 Flash** - Fast research with web search
* **GPT-5 Nano** - Advanced reasoning with code execution
* **Grok-3 Mini** - Real-time information and alternative perspectives

The agents work in parallel, share observations, vote for solutions, and converge on the best answer.

.. seealso::
   :doc:`configuration` - Learn how to create and customize multi-agent configurations

Interactive Multi-Turn Mode
----------------------------

Start MassGen without a question to enter interactive chat mode:

.. code-block:: bash

   # Single agent interactive mode
   massgen --model gemini-2.5-flash

   # Multi-agent interactive mode
   massgen \
     --config @examples/basic/multi/three_agents_default.yaml

**The Interactive Experience:**

.. code-block:: text

   ╭──────────────────────────────────────────────────────────────────────────────╮
   │                                                                              │
   │       ███╗   ███╗ █████╗ ███████╗███████╗ ██████╗ ███████╗███╗   ██╗         │
   │       ████╗ ████║██╔══██╗██╔════╝██╔════╝██╔════╝ ██╔════╝████╗  ██║         │
   │       ██╔████╔██║███████║███████╗███████╗██║  ███╗█████╗  ██╔██╗ ██║         │
   │       ██║╚██╔╝██║██╔══██║╚════██║╚════██║██║   ██║██╔══╝  ██║╚██╗██║         │
   │       ██║ ╚═╝ ██║██║  ██║███████║███████║╚██████╔╝███████╗██║ ╚████║         │
   │       ╚═╝     ╚═╝╚═╝  ╚═╝╚══════╝╚══════╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝         │
   │                                                                              │
   │            🤖 🤖 🤖  →  💬 collaborate  →  🎯 winner  →  📢 final            │
   │                                                                              │
   ╰──────────────────────────────────────────────────────────────────────────────╯

   ╭──────────────────────────────────────────────────────────────────────────────╮
   │    🤝 Mode:                Multi-Agent (3 agents)                            │
   │      ├─ openai_agent_1:    gpt-5 (Response)                                  │
   │      ├─ gemini_agent_2:    gemini-2.5-flash (Gemini)                         │
   │      └─ grok_agent_3:      grok-4-fast-reasoning (Grok)                      │
   ╰──────────────────────────────────────────────────────────────────────────────╯

Features:

* Each response builds on previous conversation context
* Session history preserved in ``.massgen/sessions/``
* Multi-agent collaboration on each turn
* Real-time coordination visualization

.. seealso::
   :doc:`../user_guide/multi_turn_mode` - Complete guide to interactive sessions, commands, and session management

MCP Integration
---------------

Add tools to your agents using Model Context Protocol:

.. code-block:: bash

   # Single MCP tool (weather)
   massgen \
     --config @examples/tools/mcp/gpt5_nano_mcp_example.yaml \
     "What's the weather forecast for New York this week?"

   # Multiple MCP tools (search + weather + filesystem)
   massgen \
     --config @examples/tools/mcp/multimcp_gemini.yaml \
     "Find the best restaurants in Paris and save the recommendations to a file"

See :doc:`../user_guide/mcp_integration` for detailed MCP configuration.

File Operations
---------------

Agents can work with files in isolated workspaces:

.. code-block:: bash

   # Single agent with file operations
   massgen \
     --config @examples/tools/filesystem/claude_code_single.yaml \
     "Create a Python web scraper and save results to CSV"

   # Multi-agent file collaboration
   massgen \
     --config @examples/tools/filesystem/claude_code_context_sharing.yaml \
     "Generate a comprehensive project report with charts and analysis"

Features:

* Each agent gets an isolated workspace
* Read-before-delete enforcement for safety
* Snapshot storage for sharing context between agents
* Support via Claude Code or MCP filesystem server

See :doc:`../user_guide/file_operations` for details.

Project Integration
-------------------

Work directly with your existing codebase using context paths:

.. code-block:: bash

   # Multi-agent collaboration on your project
   massgen \
     --config @examples/tools/filesystem/gpt5mini_cc_fs_context_path.yaml \
     "Enhance the website with dark/light theme toggle and interactive features"

Configuration example:

.. code-block:: yaml

   orchestrator:
     context_paths:
       - path: "/home/user/my-project/src"
         permission: "read"    # Agents can analyze your code
       - path: "/home/user/my-project/docs"
         permission: "write"   # Final agent can update docs

All MassGen working files organized under ``.massgen/`` directory in your project root.

See :doc:`../user_guide/project_integration` for details.

AG2 Framework Integration
--------------------------

Integrate AG2 agents with code execution:

.. code-block:: bash

   # Single AG2 agent with code execution
   massgen \
     --config @examples/ag2/ag2_coder.yaml \
     "Write a Python script to analyze CSV data and create visualizations"

   # AG2 + Gemini hybrid collaboration
   massgen \
     --config @examples/ag2/ag2_coder_case_study.yaml \
     "Compare AG2 and MassGen frameworks, use code to fetch documentation"

See :doc:`../user_guide/ag2_integration` for configuration details.

Viewing Results
---------------

**Real-time Display**

By default, MassGen shows a rich terminal UI with:

* Agent coordination table showing voting and consensus
* Live streaming of agent responses
* Progress indicators and status updates

**Disable UI:**

.. code-block:: bash

   massgen --no-display --config config.yaml "Question"

**Debug Mode:**

.. code-block:: bash

   massgen --debug --config config.yaml "Question"

Debug logs saved to ``agent_outputs/log_{timestamp}/massgen_debug.log`` with detailed:

* Orchestrator activities
* Agent messages
* Backend operations
* Tool calls

Configuration File Paths
-------------------------

MassGen supports three ways to specify configuration files:

**1. Built-in Examples (Recommended)**

Use ``@examples/`` prefix to access built-in configurations from any directory:

.. code-block:: bash

   massgen --config @examples/basic/multi/three_agents_default "Your question"

   # List all available examples
   massgen --list-examples

The ``@examples/`` prefix works from any directory and is the easiest way to get started.

**2. Custom Configuration Files**

Use relative or absolute paths for your own configurations:

.. code-block:: bash

   # Relative to current directory
   massgen --config ./my-config.yaml "Question"

   # Absolute path
   massgen --config /path/to/my-config.yaml "Question"

**3. User Configuration Directory**

Store frequently-used configs in ``~/.config/massgen/agents/`` for easy access:

.. code-block:: bash

   # Unix/Mac
   mkdir -p ~/.config/massgen/agents
   cp my-config.yaml ~/.config/massgen/agents/my-setup.yaml

   # Windows
   mkdir %USERPROFILE%\.config\massgen\agents
   copy my-config.yaml %USERPROFILE%\.config\massgen\agents\my-setup.yaml

.. seealso::
   For detailed information on configuration files and examples, see :doc:`../reference/configuration_examples`

Next Steps
----------

**Congratulations! You've run MassGen successfully. Here's what to explore next:**

✅ **You are here:** You've run both single-agent and multi-agent examples

⬜ **Next:** :doc:`configuration` - Learn how to create custom agent teams

⬜ **Understand:** :doc:`../user_guide/concepts` - See how multi-agent coordination works

⬜ **Advanced:** :doc:`../user_guide/mcp_integration` - Add external tools to your agents

**Already know what you want to build?** Jump to :doc:`../examples/basic_examples` for ready-to-use configurations.

Backwards Compatibility
=======================

For Existing Users
------------------

If you previously used MassGen via git clone, **all your existing workflows continue to work**. The PyPI package introduces simplified commands and the ``@examples/`` prefix while maintaining full backwards compatibility.

Command Syntax Changes
~~~~~~~~~~~~~~~~~~~~~~

**Old Command Syntax** (still works):

.. code-block:: bash

   # Old way - using python -m from MassGen directory
   cd /path/to/MassGen
   python -m massgen.cli --config massgen/configs/basic/multi/three_agents_default.yaml "Question"

**New Command Syntax** (recommended):

.. code-block:: bash

   # New way - simple massgen command from anywhere
   massgen --config @examples/basic/multi/three_agents_default "Question"

Configuration Path Changes
~~~~~~~~~~~~~~~~~~~~~~~~~~

**Old Config Paths** (still work):

.. code-block:: bash

   # Relative paths from MassGen directory
   python -m massgen.cli --config massgen/configs/basic/multi/three_agents_default.yaml "Question"

**New @ Prefix for Built-in Configs** (recommended):

.. code-block:: bash

   # @ prefix works from any directory
   massgen --config @examples/basic/multi/three_agents_default "Question"

**What is the @ prefix?**

The ``@`` prefix is a convenient shortcut to access MassGen's built-in example configurations:

* ``@examples/`` maps to the installed package's example configurations
* Works from **any directory** (no need to be in MassGen folder)
* Easier to type and remember
* Part of the installed package, always available

.. code-block:: bash

   # List all available @examples/ configurations
   massgen --list-examples

Migration Guide
~~~~~~~~~~~~~~~

You have several options for migrating to the new PyPI package:

**Option 1: Global Install (Recommended)**

.. code-block:: bash

   # Install MassGen globally via pip
   pip install massgen

   # Now use the simple 'massgen' command from anywhere
   massgen --config @examples/basic/multi/three_agents_default "Question"

**Option 2: Keep Git Clone with Editable Install**

.. code-block:: bash

   # Keep your git clone and install in editable mode
   cd /path/to/MassGen
   pip install -e .

   # Now you can use 'massgen' from anywhere
   cd ~/other-project
   massgen --config @examples/basic/multi/three_agents_default "Question"

**Option 3: Continue Using Old Syntax**

.. code-block:: bash

   # Your existing commands still work
   cd /path/to/MassGen
   python -m massgen.cli --config massgen/configs/basic/multi/three_agents_default.yaml "Question"

Compatibility Summary
~~~~~~~~~~~~~~~~~~~~~

* ✅ ``massgen`` - New simplified command (recommended)
* ✅ ``python -m massgen.cli`` - Old command syntax (still works)
* ✅ ``@examples/...`` - New config prefix (recommended)
* ✅ ``massgen/configs/...`` - Old config paths (still work when in MassGen directory)
* ✅ Custom config paths (``./my-config.yaml``) - Work in both old and new syntax
