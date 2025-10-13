Running MassGen
===============

This guide shows you how to run MassGen with different configurations.

.. important::
   **Configuration File Paths:** Example commands show paths like ``@examples/...`` These are **relative paths** that only work when you're in the MassGen repository directory. See `Using Config Files from Anywhere`_ below for how to run from other directories.

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

Understanding Path Resolution
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

MassGen configuration paths work differently depending on your installation method:

**When Running from MassGen Directory:**

.. code-block:: bash

   # You're in /Users/you/MassGen/
   massgen \
     --config @examples/basic/multi/three_agents_default.yaml \
     "Your question"

This works because ``@examples/...`` is a **relative path** from the current directory.

**When Running from Other Directories:**

If you're in a different directory (like ``~/my-project/``), relative paths won't work:

.. code-block:: bash

   # You're in /Users/you/my-project/
   massgen \
     --config @examples/basic/multi/three_agents_default.yaml  # ❌ Won't work!
     "Your question"

**Solutions:**

1. **Use absolute paths:**

   .. code-block:: bash

      massgen \
        --config /Users/you/MassGen/@examples/basic/multi/three_agents_default.yaml \
        "Your question"

2. **Copy config to your project:**

   .. code-block:: bash

      # Copy the config you want to use
      cp /Users/you/MassGen/@examples/basic/multi/three_agents_default.yaml ./my-config.yaml

      # Run with local config
      massgen --config ./my-config.yaml "Your question"

3. **Use uv tool installation (recommended for multi-directory usage):**

   .. code-block:: bash

      # Install once (from MassGen directory)
      cd /Users/you/MassGen
      uv tool install -e .

      # Now configs are accessible from anywhere
      cd ~/my-project
      uv tool run massgen --config my-config.yaml "Your question"

See :doc:`installation` for more on ``uv tool`` installation.

Common Path Errors
~~~~~~~~~~~~~~~~~~

**Error: "FileNotFoundError: Configuration file not found"**

This means MassGen can't find the config file at the path you specified.

**Solution:**

1. Check your current directory: ``pwd``
2. Use an absolute path, or
3. Copy the config to your current directory

**Example of fixing path error:**

.. code-block:: bash

   # Check where you are
   pwd
   # Output: /Users/you/my-project

   # This won't work (relative path from MassGen repo)
   massgen --config @examples/basic/multi/three_agents_default.yaml

   # Solution 1: Use absolute path
   massgen \
     --config /Users/you/MassGen/@examples/basic/multi/three_agents_default.yaml \
     "Your question"

   # Solution 2: Copy config locally
   cp /Users/you/MassGen/@examples/basic/multi/three_agents_default.yaml ./agents.yaml
   massgen --config ./agents.yaml "Your question"

Quick Reference
~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - Situation
     - Solution
   * - Running from MassGen repo directory
     - Use relative paths: ``@examples/...``
   * - Running from another directory
     - Use absolute paths or copy config locally
   * - Want to run from any directory easily
     - Install with ``uv tool install -e .``
   * - Config file not found error
     - Check ``pwd``, then use absolute path or copy config

Next Steps
----------

* :doc:`configuration` - Learn YAML configuration syntax
* :doc:`../user_guide/concepts` - Understand core concepts
* :doc:`../user_guide/mcp_integration` - Deep dive into MCP tools
* :doc:`../user_guide/multi_turn_mode` - Master interactive mode
