Running MassGen
===============

This guide shows you how to run MassGen with different configurations.

.. tip::
   **Configuration File Paths:** Example commands use ``@examples/...`` paths which work from **any directory** because they're part of MassGen's installed package. See `Using Config Files from Anywhere`_ below for all path options.

CLI Parameters
--------------

MassGen is run via command line with the following parameters:

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Parameter
     - Description
   * - ``--config``
     - Path to YAML configuration file with agent definitions, model parameters, backend parameters and UI settings
   * - ``--backend``
     - Backend type for quick setup without a config file (``claude``, ``claude_code``, ``gemini``, ``grok``, ``openai``, ``azure_openai``, ``zai``)
   * - ``--model``
     - Model name for quick setup (e.g., ``gemini-2.5-flash``, ``gpt-5-nano``). Mutually exclusive with ``--config``
   * - ``--system-message``
     - System prompt for the agent in quick setup mode. Omitted if ``--config`` is provided
   * - ``--no-display``
     - Disable real-time streaming UI coordination display (fallback to simple text output)
   * - ``--no-logs``
     - Disable real-time logging
   * - ``--debug``
     - Enable debug mode with verbose logging. Debug logs saved to ``agent_outputs/log_{time}/massgen_debug.log``
   * - ``"<your question>"``
     - Optional single-question input; if omitted, MassGen enters interactive chat mode

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

Using Config Files from Anywhere
---------------------------------

Understanding Configuration Paths
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

MassGen supports multiple ways to specify configuration files, with different path resolution behaviors:

**1. Package Configs with @examples/ (Recommended)**

Configs prefixed with ``@examples/`` are **built into MassGen's package** and work from any directory:

.. code-block:: bash

   # Works from any directory!
   cd ~/my-project
   massgen --config @examples/basic/multi/three_agents_default "Your question"

   cd ~/Documents
   massgen --config @examples/tools/mcp/gpt5_nano_mcp_example "Another question"

The ``@examples/`` prefix tells MassGen to search in its installed package configs. Use slashes (``/``) to match the actual directory structure:

* ✅ ``@examples/basic/single/single_gpt5nano``
* ✅ ``@examples/tools/mcp/multimcp_gemini``
* ✅ ``@examples/providers/claude/claude``

**List all available package configs:**

.. code-block:: bash

   massgen --list-examples

**2. Relative and Absolute Paths**

Standard filesystem paths work as expected:

.. code-block:: bash

   # Relative to current directory
   massgen --config ./my-config.yaml "Question"
   massgen --config ../configs/custom.yaml "Question"

   # Absolute paths
   massgen --config /Users/you/configs/my-setup.yaml "Question"

**3. User Config Directory (Coming Soon)**

Save frequently-used configs to ``~/.config/massgen/agents/`` for easy access:

.. code-block:: bash

   # Save your config
   mkdir -p ~/.config/massgen/agents
   cp my-config.yaml ~/.config/massgen/agents/my-setup.yaml

   # Access by name (planned feature)
   massgen --config my-setup "Question"

Path Resolution Priority
~~~~~~~~~~~~~~~~~~~~~~~~

When you specify ``--config``, MassGen searches in this order:

1. **Package configs** - If path starts with ``@examples/``, search installed package
2. **Filesystem paths** - Check if file exists at the given path (relative or absolute)
3. **User configs** - Search ``~/.config/massgen/agents/`` (if basename provided)
4. **Error** - Config not found

Examples:

.. code-block:: bash

   # Package config - searches MassGen's installed configs
   --config @examples/basic/multi/three_agents_default

   # Relative path - looks in current directory
   --config ./my-config.yaml

   # Absolute path - exact file location
   --config /Users/you/MassGen/massgen/configs/basic/multi/three_agents_default.yaml

Working with GitHub Repository Configs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. note::
   **For GitHub Users:** If you're working directly with the MassGen repository (not using the installed package), configs are located in ``massgen/configs/`` directory.

**From within repository:**

.. code-block:: bash

   # You're in /Users/you/MassGen/
   massgen --config massgen/configs/basic/multi/three_agents_default.yaml "Question"

   # Or use the package syntax (if installed in editable mode)
   massgen --config @examples/basic/multi/three_agents_default "Question"

**From outside repository:**

.. code-block:: bash

   # Use absolute path
   massgen \
     --config /Users/you/MassGen/massgen/configs/basic/multi/three_agents_default.yaml \
     "Question"

   # Or copy the config to your project
   cp /Users/you/MassGen/massgen/configs/basic/multi/three_agents_default.yaml ./my-config.yaml
   massgen --config ./my-config.yaml "Question"

Common Issues and Solutions
~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Issue: "Config not found" error with @examples/ path**

This means MassGen isn't installed properly or you're using an old version.

**Solution:**

.. code-block:: bash

   # Reinstall MassGen
   cd /path/to/MassGen
   uv pip install -e .

   # Verify installation
   massgen --list-examples

**Issue: Relative path works in one directory but not another**

Relative paths like ``./config.yaml`` depend on your current working directory.

**Solution:**

Use ``@examples/`` for package configs, or absolute paths for custom configs:

.. code-block:: bash

   # Package config - works anywhere
   massgen --config @examples/basic/multi/three_agents_default "Question"

   # Absolute path - always works
   massgen --config /Users/you/configs/my-setup.yaml "Question"

Quick Reference
~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Config Path Type
     - Example & Behavior
   * - **Package Config** (Recommended)
     - ``@examples/basic/multi/three_agents_default``

       ✅ Works from any directory

       ✅ Always available after installation
   * - **Relative Path**
     - ``./my-config.yaml`` or ``../configs/setup.yaml``

       📂 Relative to current directory
   * - **Absolute Path**
     - ``/Users/you/configs/my-setup.yaml``

       ✅ Always works from any location
   * - **User Config**
     - ``~/.config/massgen/agents/my-setup.yaml``

       🏠 Personal config storage
   * - **Repository Path** (GitHub)
     - ``massgen/configs/basic/multi/three_agents_default.yaml``

       📦 Direct repository access (for development)

Next Steps
----------

* :doc:`configuration` - Learn YAML configuration syntax
* :doc:`../user_guide/concepts` - Understand core concepts
* :doc:`../user_guide/mcp_integration` - Deep dive into MCP tools
* :doc:`../user_guide/multi_turn_mode` - Master interactive mode
