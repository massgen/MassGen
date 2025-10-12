Basic Examples
==============

Real MassGen examples using the CLI and YAML configuration.

.. note::

   All examples use real CLI commands and YAML configurations. These examples work with actual MassGen.

Quick Start Examples
--------------------

Single Agent - Model Flag
~~~~~~~~~~~~~~~~~~~~~~~~~~

Test any model without configuration:

.. code-block:: bash

   # Test Claude
   uv run python -m massgen.cli --model claude-3-5-sonnet-latest "What is machine learning?"

   # Test Gemini
   uv run python -m massgen.cli --model gemini-2.5-flash "Explain quantum computing"

   # Test GPT-5
   uv run python -m massgen.cli --model gpt-5-nano "Summarize recent AI developments"

Single Agent - Configuration File
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Using a configuration file:

**Configuration:** ``massgen/configs/basic/single/single_gpt5nano.yaml``

.. code-block:: yaml

   agents:
     - id: "gpt-5-nano"
       backend:
         type: "openai"
         model: "gpt-5-nano"
         enable_web_search: true
         enable_code_interpreter: true

   ui:
     display_type: "rich_terminal"
     logging_enabled: true

**Run:**

.. code-block:: bash

   uv run python -m massgen.cli \
     --config massgen/configs/basic/single/single_gpt5nano.yaml \
     "Calculate the first 100 prime numbers and plot their distribution"

.. seealso::
   :doc:`../quickstart/configuration` - Complete configuration syntax and all available options

Multi-Agent Collaboration
--------------------------

Three Agents Working Together
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The recommended starting point for multi-agent collaboration:

**Configuration:** ``massgen/configs/basic/multi/three_agents_default.yaml``

.. code-block:: yaml

   agents:
     - id: "gemini2.5flash"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
         enable_web_search: true

     - id: "gpt5nano"
       backend:
         type: "openai"
         model: "gpt-5-nano"
         enable_web_search: true
         enable_code_interpreter: true

     - id: "grok3mini"
       backend:
         type: "grok"
         model: "grok-3-mini"
         enable_web_search: true

**This showcases:**

* **Gemini 2.5 Flash** - Fast research with web search
* **GPT-5 Nano** - Advanced reasoning with code execution
* **Grok-3 Mini** - Real-time information

**Run:**

.. code-block:: bash

   uv run python -m massgen.cli \
     --config massgen/configs/basic/multi/three_agents_default.yaml \
     "Analyze the pros and cons of renewable energy"

Interactive Mode
----------------

Multi-Turn Conversations
~~~~~~~~~~~~~~~~~~~~~~~~

Start interactive mode by omitting the question:

.. code-block:: bash

   # Start interactive session
   uv run python -m massgen.cli \
     --config massgen/configs/basic/multi/three_agents_default.yaml

.. seealso::
   :doc:`../user_guide/multi_turn_mode` - Complete interactive mode guide with commands and session management

Tool Usage Examples
-------------------

Web Search
~~~~~~~~~~

All agents have web search enabled by default:

.. code-block:: bash

   # Research with multiple agents
   uv run python -m massgen.cli \
     --config massgen/configs/basic/multi/three_agents_default.yaml \
     "What are the latest developments in quantum computing?"

   # Single agent web search
   uv run python -m massgen.cli \
     --model gemini-2.5-flash \
     "Research renewable energy adoption rates globally"

Code Execution
~~~~~~~~~~~~~~

GPT-5 and Gemini support code execution:

.. code-block:: bash

   # Code generation and execution
   uv run python -m massgen.cli \
     --model gpt-5-nano \
     "Write Python code to analyze CSV data and create visualizations"

   # Multi-agent coding
   uv run python -m massgen.cli \
     --config massgen/configs/basic/multi/three_agents_default.yaml \
     "Create a script to calculate Fibonacci numbers and plot the sequence"

MCP Integration Examples
-------------------------

Weather Information
~~~~~~~~~~~~~~~~~~~

Using MCP for external tools:

**Configuration:** ``massgen/configs/tools/mcp/gpt5_nano_mcp_example.yaml``

.. code-block:: yaml

   agents:
     - id: "gpt5_nano_mcp_weather"
       backend:
         type: "openai"
         model: "gpt-5-nano"
         mcp_servers:
           - name: "weather"
             type: "stdio"
             command: "npx"
             args: ["-y", "@fak111/weather-mcp"]

**Run:**

.. code-block:: bash

   uv run python -m massgen.cli \
     --config massgen/configs/tools/mcp/gpt5_nano_mcp_example.yaml \
     "What's the weather forecast for New York this week?"

Multi-Server MCP
~~~~~~~~~~~~~~~~

Using multiple MCP servers:

**Configuration:** ``massgen/configs/tools/mcp/multimcp_gemini.yaml``

**Run:**

.. code-block:: bash

   # Requires BRAVE_API_KEY in .env
   uv run python -m massgen.cli \
     --config massgen/configs/tools/mcp/multimcp_gemini.yaml \
     "Find the best restaurants in Paris and save recommendations to a file"

File Operations Examples
------------------------

Claude Code with Files
~~~~~~~~~~~~~~~~~~~~~~~

File operations with Claude Code:

**Configuration:** ``massgen/configs/tools/filesystem/claude_code_single.yaml``

**Run:**

.. code-block:: bash

   uv run python -m massgen.cli \
     --config massgen/configs/tools/filesystem/claude_code_single.yaml \
     "Create a Python project structure with tests and documentation"

Multi-Agent File Collaboration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Multiple agents working with files:

**Run:**

.. code-block:: bash

   uv run python -m massgen.cli \
     --config massgen/configs/tools/filesystem/claude_code_context_sharing.yaml \
     "Analyze code quality and generate improvement recommendations"

Common Use Cases
----------------

Question Answering
~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   # Simple question
   uv run python -m massgen.cli \
     --model gemini-2.5-flash \
     "What is the capital of France?"

   # Complex research
   uv run python -m massgen.cli \
     --config massgen/configs/basic/multi/three_agents_default.yaml \
     "Compare different programming paradigms and their use cases"

Research & Analysis
~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   # Current events research
   uv run python -m massgen.cli \
     --config massgen/configs/basic/multi/three_agents_default.yaml \
     "What's best to do in Stockholm in October 2025"

   # Technical research
   uv run python -m massgen.cli \
     --config massgen/configs/basic/multi/three_agents_default.yaml \
     "Compare cloud providers for machine learning workloads"

Creative Writing
~~~~~~~~~~~~~~~~

.. code-block:: bash

   # Story generation
   uv run python -m massgen.cli \
     --config massgen/configs/basic/multi/three_agents_default.yaml \
     "Write a short story about a robot who discovers music"

Development Tasks
~~~~~~~~~~~~~~~~~

.. code-block:: bash

   # Code generation
   uv run python -m massgen.cli \
     --config massgen/configs/tools/filesystem/claude_code_single.yaml \
     "Create a Flask web app with authentication"

   # Code review
   uv run python -m massgen.cli \
     --config massgen/configs/tools/filesystem/claude_code_single.yaml \
     "Review Python code in workspace/ and suggest improvements"

Configuration Examples Directory
---------------------------------

All examples are in ``massgen/configs/``:

**Basic:**

* ``basic/single/`` - Single agent configurations
* ``basic/multi/`` - Multi-agent configurations

**Tools:**

* ``tools/mcp/`` - MCP integration examples
* ``tools/filesystem/`` - File operation examples
* ``tools/web-search/`` - Web search configurations
* ``tools/code-execution/`` - Code execution examples

**Providers:**

* ``providers/openai/`` - OpenAI-specific examples
* ``providers/claude/`` - Claude-specific examples
* ``providers/gemini/`` - Gemini-specific examples
* ``providers/local/`` - Local model examples

See the `Configuration README <https://github.com/Leezekun/MassGen/blob/main/massgen/configs/README.md>`_ for the complete catalog.

Best Practices
--------------

1. **Start Simple**: Begin with single agent, then scale to multi-agent
2. **Test Incrementally**: Verify each feature before combining
3. **Use Real Configs**: Copy from ``massgen/configs/`` and modify
4. **Check Logs**: Use ``--debug`` for troubleshooting
5. **Read Documentation**: Each config file has usage comments

Next Steps
----------

* :doc:`advanced_patterns` - Advanced multi-agent patterns
* :doc:`../user_guide/mcp_integration` - MCP integration guide
* :doc:`../user_guide/file_operations` - File operations guide
* :doc:`../user_guide/multi_turn_mode` - Interactive mode guide
* :doc:`../reference/yaml_schema` - Complete YAML reference

Troubleshooting
---------------

**Example not working:**

1. Check API key in ``.env`` file
2. Verify configuration path is correct
3. Use ``--debug`` flag to see detailed logs
4. Test with simpler question first

**Configuration file not found:**

.. code-block:: bash

   # Correct - relative to MassGen root
   --config massgen/configs/basic/multi/three_agents_default.yaml

   # Incorrect - missing massgen/ prefix
   --config configs/basic/multi/three_agents_default.yaml

**MCP server not found:**

.. code-block:: bash

   # Install MCP server
   npx -y @fak111/weather-mcp

   # Or install globally
   npm install -g @fak111/weather-mcp
