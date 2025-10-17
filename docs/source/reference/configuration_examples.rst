Configuration Examples
======================

This reference provides a comprehensive catalog of MassGen configuration examples organized by use case, backend provider, and feature set.

Directory Structure
-------------------

All configuration files are located in ``@examples/``:

.. code-block:: text

   @examples/
   ├── basic/                 # Simple configs to get started
   │   ├── single/           # Single agent examples
   │   └── multi/            # Multi-agent examples
   ├── tools/                 # Tool-enabled configurations
   │   ├── mcp/              # MCP server integrations
   │   ├── planning/         # Planning mode examples
   │   ├── web-search/       # Web search enabled configs
   │   ├── code-execution/   # Code interpreter/execution
   │   └── filesystem/       # File operations & workspace
   ├── providers/             # Provider-specific examples
   │   ├── openai/           # GPT-5 series configs
   │   ├── claude/           # Claude API configs
   │   ├── gemini/           # Gemini configs
   │   ├── azure/            # Azure OpenAI
   │   ├── local/            # LMStudio, local models
   │   └── others/           # Cerebras, Grok, Qwen, ZAI
   ├── teams/                # Pre-configured specialized teams
   │   ├── creative/         # Creative writing teams
   │   ├── research/         # Research & analysis
   │   └── development/      # Coding teams
   └── ag2/                  # AG2 framework integration

Quick Start Examples
--------------------

Recommended Showcase Example
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Best starting point for multi-agent collaboration:**

.. code-block:: bash

   # Three powerful agents (Gemini, GPT-5, Grok) with enhanced workspace tools
   massgen \
     --config @examples/basic/multi/three_agents_default.yaml \
     "Your complex task"

This configuration combines:

* **Gemini 2.5 Flash** - Fast, versatile with web search
* **GPT-5 Nano** - Advanced reasoning with code interpreter
* **Grok-3 Mini** - Efficient with real-time web search

Quick Setup Without Config Files
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Single agent with model name only:**

.. code-block:: bash

   # Quick test with any supported model - no configuration needed
   massgen --model claude-3-5-sonnet-latest "What is machine learning?"
   massgen --model gemini-2.5-flash "Explain quantum computing"
   massgen --model gpt-5-nano "Summarize the latest AI developments"

**Interactive Mode:**

.. code-block:: bash

   # Start interactive chat (no initial question)
   massgen \
     --config @examples/basic/multi/three_agents_default.yaml

   # Debug mode for troubleshooting
   massgen \
     --config @examples/basic/multi/three_agents_default.yaml \
     --debug "Your question"

Tool-Enabled Configurations
----------------------------

MCP (Model Context Protocol) Servers
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

MCP enables agents to use external tools and services:

.. code-block:: bash

   # Weather queries
   massgen \
     --config @examples/tools/mcp/gemini_mcp_example.yaml \
     "What's the weather in Tokyo?"

   # Discord integration
   massgen \
     --config @examples/tools/mcp/claude_code_discord_mcp_example.yaml \
     "Extract latest messages"

See :doc:`../user_guide/mcp_integration` for complete MCP documentation.

Planning Mode
~~~~~~~~~~~~~

Prevent irreversible actions during coordination:

.. code-block:: bash

   # Five agents with planning mode enabled
   massgen \
     --config @examples/tools/planning/five_agents_filesystem_mcp_planning_mode.yaml \
     "Create a comprehensive project structure"

See :doc:`../user_guide/planning_mode` for complete planning mode documentation.

Web Search
~~~~~~~~~~

For agents with web search capabilities:

.. code-block:: bash

   massgen \
     --config @examples/tools/web-search/claude_streamable_http_test.yaml \
     "Search for latest news"

Code Execution
~~~~~~~~~~~~~~

For code interpretation and execution:

.. code-block:: bash

   massgen \
     --config @examples/tools/code-execution/multi_agent_playwright_automation.yaml \
     "Browse three issues in https://github.com/Leezekun/MassGen and suggest improvements"

Filesystem Operations
~~~~~~~~~~~~~~~~~~~~~

For file manipulation, :term:`workspace` management, and :term:`context path` integration:

.. code-block:: bash

   # Single agent with enhanced file operations
   massgen \
     --config @examples/tools/filesystem/claude_code_single.yaml \
     "Analyze this codebase"

   # Multi-agent workspace collaboration
   massgen \
     --config @examples/tools/filesystem/claude_code_context_sharing.yaml \
     "Create shared workspace files"

See :doc:`../user_guide/file_operations` for complete filesystem documentation.

Provider-Specific Examples
--------------------------

Each provider has unique features and capabilities:

OpenAI (GPT-5 Series)
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   massgen \
     --config @examples/providers/openai/gpt5.yaml \
     "Complex reasoning task"

Claude
~~~~~~

.. code-block:: bash

   massgen \
     --config @examples/tools/mcp/claude_mcp_example.yaml \
     "Creative writing task"

Gemini
~~~~~~

.. code-block:: bash

   massgen \
     --config @examples/tools/mcp/gemini_mcp_example.yaml \
     "Research task"

Local Models
~~~~~~~~~~~~

.. code-block:: bash

   # Requires LM Studio running locally
   massgen \
     --config @examples/providers/local/lmstudio.yaml \
     "Run with local model"

See :doc:`../reference/supported_models` for choosing backends.

Pre-Configured Teams
--------------------

Teams are specialized multi-agent setups for specific domains:

Creative Teams
~~~~~~~~~~~~~~

.. code-block:: bash

   massgen \
     --config @examples/teams/creative/creative_team.yaml \
     "Write a story"

Research Teams
~~~~~~~~~~~~~~

.. code-block:: bash

   massgen \
     --config @examples/teams/research/research_team.yaml \
     "Analyze market trends"

Development Teams
~~~~~~~~~~~~~~~~~

.. code-block:: bash

   massgen \
     --config @examples/providers/others/zai_coding_team.yaml \
     "Build a web app"

Configuration File Format
-------------------------

Single Agent
~~~~~~~~~~~~

.. code-block:: yaml

   agents:
     - id: "agent_name"
       backend:
         type: "provider_type"
         model: "model_name"
         # Additional backend settings
       system_message: "Agent instructions"

   ui:
     display_type: "rich_terminal"
     logging_enabled: true

Multi-Agent
~~~~~~~~~~~

.. code-block:: yaml

   agents:
     - id: "agent1"
       backend:
         type: "provider1"
         model: "model1"
       system_message: "Agent 1 role"

     - id: "agent2"
       backend:
         type: "provider2"
         model: "model2"
       system_message: "Agent 2 role"

   ui:
     display_type: "rich_terminal"
     logging_enabled: true

See :doc:`yaml_schema` for complete configuration reference.

MCP Server Configuration
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   backend:
     type: "provider"
     model: "model_name"
     mcp_servers:
       - name: "server_name"
         type: "stdio"
         command: "command"
         args: ["arg1", "arg2"]
         env:
           KEY: "${ENV_VAR}"

See :doc:`../user_guide/mcp_integration` for complete MCP configuration.

Finding the Right Configuration
--------------------------------

1. **New Users**: Start with ``basic/single/`` or ``basic/multi/``
2. **Need Tools**: Check ``tools/`` subdirectories for specific capabilities
3. **Specific Provider**: Look in ``providers/`` for your provider
4. **Complex Tasks**: Use pre-configured ``teams/``
5. **Planning Mode**: Use ``tools/planning/`` for tasks with irreversible actions

Release History & Examples
---------------------------

v0.0.29 - Latest
~~~~~~~~~~~~~~~~

**New Features:** :doc:`../user_guide/planning_mode`, File Operation Safety, Enhanced MCP Tool Filtering

**Key Configurations:**

* ``@examples/tools/planning/five_agents_discord_mcp_planning_mode.yaml`` - Five agents with Discord MCP in planning mode
* ``@examples/tools/planning/five_agents_filesystem_mcp_planning_mode.yaml`` - Five agents with filesystem MCP in planning mode
* ``@examples/tools/planning/five_agents_notion_mcp_planning_mode.yaml`` - Five agents with Notion MCP in planning mode
* ``@examples/tools/mcp/five_agents_weather_mcp_test.yaml`` - Five agents testing weather MCP tools

**Try it:**

.. code-block:: bash

   # Planning mode with filesystem operations
   massgen \
     --config @examples/tools/planning/five_agents_filesystem_mcp_planning_mode.yaml \
     "Create a comprehensive project structure with documentation"

   # Multi-agent weather MCP testing
   massgen \
     --config @examples/tools/mcp/five_agents_weather_mcp_test.yaml \
     "Compare weather forecasts for New York, London, and Tokyo"

v0.0.28
~~~~~~~

**New Features:** :doc:`../user_guide/ag2_integration`, External Agent Backend, Code Execution Support

**Key Configurations:**

* ``@examples/ag2/ag2_single_agent.yaml`` - Basic single AG2 agent setup
* ``@examples/ag2/ag2_coder.yaml`` - AG2 agent with code execution capabilities
* ``@examples/ag2/ag2_gemini.yaml`` - AG2-Gemini hybrid configuration

**Try it:**

.. code-block:: bash

   # AG2 single agent with code execution
   massgen \
     --config @examples/ag2/ag2_coder.yaml \
     "Create a factorial function and calculate the factorial of 8"

   # Mixed team: AG2 agent + Gemini agent
   massgen \
     --config @examples/ag2/ag2_gemini.yaml \
     "what is quantum computing?"

v0.0.27
~~~~~~~

**New Features:** Multimodal Support (Image Processing), File Upload and File Search

**Key Configurations:**

* ``@examples/basic/multi/gpt4o_image_generation.yaml`` - Multi-agent image generation
* ``@examples/basic/multi/gpt5nano_image_understanding.yaml`` - Multi-agent image understanding
* ``@examples/basic/single/single_gpt5nano_file_search.yaml`` - File search for document Q&A

**Try it:**

.. code-block:: bash

   # Image generation
   massgen \
     --config @examples/basic/single/single_gpt4o_image_generation.yaml \
     "Generate an image of a gray tabby cat hugging an otter"

   # Image understanding
   massgen \
     --config @examples/basic/multi/gpt5nano_image_understanding.yaml \
     "Please summarize the content in this image"

v0.0.26
~~~~~~~

**New Features:** File Deletion, :doc:`../user_guide/protected_paths`, File-Based Context Paths

**Key Configurations:**

* ``@examples/tools/filesystem/gemini_gpt5nano_protected_paths.yaml`` - Protected paths configuration
* ``@examples/tools/filesystem/gemini_gpt5nano_file_context_path.yaml`` - File-based context paths
* ``@examples/tools/filesystem/grok4_gpt5_gemini_filesystem.yaml`` - Multi-agent filesystem collaboration

**Try it:**

.. code-block:: bash

   # Protected paths - keep reference files safe
   massgen \
     --config @examples/tools/filesystem/gemini_gpt5nano_protected_paths.yaml \
     "Review the HTML and CSS files, then improve the styling"

v0.0.25
~~~~~~~

**New Features:** :doc:`../user_guide/multi_turn_mode` Filesystem Support, SGLang Backend Integration

**Key Configurations:**

* ``@examples/tools/filesystem/multiturn/two_gemini_flash_filesystem_multiturn.yaml`` - Multi-turn with Gemini agents
* ``@examples/tools/filesystem/multiturn/grok4_gpt5_claude_code_filesystem_multiturn.yaml`` - Three-agent multi-turn
* ``@examples/basic/multi/two_qwen_vllm_sglang.yaml`` - Mixed vLLM and SGLang deployment

**Example Multi-Turn Session:**

.. code-block:: bash

   # Turn 1 - Initial creation
   massgen \
     --config @examples/tools/filesystem/multiturn/two_gemini_flash_filesystem_multiturn.yaml

   Turn 1: Make a website about Bob Dylan
   # Creates workspace and saves state to .massgen/sessions/

   # Turn 2 - Enhancement based on Turn 1
   Turn 2: Remove the image placeholder and improve the appearance
   # Automatically loads Turn 1's workspace state

v0.0.24 and Earlier
~~~~~~~~~~~~~~~~~~~

See the `GitHub repository <https://github.com/Leezekun/MassGen/blob/main/@examples/README.md>`_ for complete release history including:

* v0.0.24 - vLLM Backend Support
* v0.0.23 - Backend Architecture Refactoring
* v0.0.22 - Workspace Copy Tools via MCP
* v0.0.21 - Advanced Filesystem Permissions
* v0.0.20 - Claude MCP Support
* v0.0.17 - OpenAI MCP Integration
* v0.0.16 - Unified Filesystem Support
* v0.0.15 - Gemini MCP Integration
* v0.0.12-14 - Enhanced Logging
* v0.0.10 - Azure OpenAI Support
* v0.0.7 - Local Model Support
* v0.0.5 - Claude Code Integration

Environment Variables
---------------------

Most configurations use environment variables for API keys. Set up your ``.env`` file based on ``.env.example``:

**Provider-specific keys:**

* ``OPENAI_API_KEY`` - OpenAI models
* ``ANTHROPIC_API_KEY`` - Claude models
* ``GOOGLE_API_KEY`` - Gemini models
* ``XAI_API_KEY`` - Grok models
* ``AZURE_OPENAI_API_KEY`` - Azure OpenAI

**MCP server keys:**

* ``DISCORD_BOT_TOKEN`` - Discord MCP integration
* ``BRAVE_API_KEY`` - Brave Search MCP integration

See :doc:`../quickstart/configuration` for complete environment setup.

Naming Convention
-----------------

MassGen configuration files follow this pattern for clarity:

**Format:** ``{agents}_{features}_{description}.yaml``

**1. Agents** (who's participating):

* ``single-{provider}`` - Single agent (e.g., ``single-claude``, ``single-gemini``)
* ``{provider1}-{provider2}`` - Two agents (e.g., ``claude-gemini``, ``gemini-gpt5``)
* ``three-mixed`` - Three agents from different providers
* ``team-{type}`` - Specialized teams (e.g., ``team-creative``, ``team-research``)

**2. Features** (what tools/capabilities):

* ``basic`` - No special tools, just conversation
* ``mcp`` - MCP server integration
* ``mcp-{service}`` - Specific MCP service (e.g., ``mcp-discord``, ``mcp-weather``)
* ``websearch`` - Web search enabled
* ``codeexec`` - Code execution/interpreter
* ``filesystem`` - File operations and workspace management

**3. Description** (purpose/context - optional):

* ``showcase`` - Demonstration/getting started example
* ``test`` - Testing configuration
* ``research`` - Research and analysis tasks
* ``dev`` - Development and coding tasks
* ``collab`` - Collaboration example

**Note:** Existing configs maintain their current names for compatibility. New configs should follow this convention.

Related Documentation
---------------------

* :doc:`../quickstart/configuration` - Configuration guide with step-by-step setup
* :doc:`yaml_schema` - Complete YAML schema reference
* :doc:`supported_models` - All supported models and backends
* :doc:`cli` - Command-line interface reference
* :doc:`../user_guide/mcp_integration` - MCP tool integration guide
* :doc:`../user_guide/planning_mode` - Planning mode documentation
* :doc:`../user_guide/protected_paths` - Protected paths feature
