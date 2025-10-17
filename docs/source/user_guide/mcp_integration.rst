MCP Integration
================

MassGen supports the Model Context Protocol (MCP) for standardized tool integration. MCP enables agents to use external tools through a unified interface.

What is MCP?
------------

From the official documentation:

   MCP is an open protocol that standardizes how applications provide context to LLMs. Think of MCP like a USB-C port for AI applications. Just as USB-C provides a standardized way to connect your devices to various peripherals and accessories, MCP provides a standardized way to connect AI models to different data sources and tools.

MassGen integrates MCP through YAML configuration, allowing agents to access tools like:

* Web search (Brave, Google)
* Weather services
* File operations
* Browser automation (Playwright)
* Discord, Twitter, Notion APIs
* And many more MCP servers

Quick Start
-----------

**Single MCP tool (weather):**

.. code-block:: bash

   massgen \
     --config @examples/tools/mcp/gpt5_nano_mcp_example.yaml \
     "What's the weather forecast for New York this week?"

**Multiple MCP tools:**

.. code-block:: bash

   massgen \
     --config @examples/tools/mcp/multimcp_gemini.yaml \
     "Find the best restaurants in Paris and save the recommendations to a file"

Backend Support
---------------

MCP integration is available for most MassGen backends. For the complete backend capabilities matrix including MCP support status, see :doc:`backends`.

**Backends with MCP Support:**

* ✅ Claude API - Full MCP integration
* ✅ Claude Code - Native MCP + file tools
* ✅ Gemini API - Full MCP integration with planning mode
* ✅ Grok API - Full MCP integration
* ✅ OpenAI API - Full MCP integration
* ✅ Z AI - MCP integration available
* ❌ Azure OpenAI - Not yet supported

See :doc:`backends` for detailed backend capabilities and feature comparison.

Configuration
-------------

Basic MCP Setup
~~~~~~~~~~~~~~~

Add MCP servers to your agent's backend configuration:

.. code-block:: yaml

   agents:
     - id: "agent_with_mcp"
       backend:
         type: "openai"              # Your backend choice
         model: "gpt-5-mini"         # Your model choice

         # Add MCP servers here
         mcp_servers:
           - name: "weather"         # Server name (you choose this)
             type: "stdio"           # Communication type
             command: "npx"          # Command to run
             args: ["-y", "@modelcontextprotocol/server-weather"]

That's it! The agent can now check weather.

MCP Transport Types
~~~~~~~~~~~~~~~~~~~

**stdio (Standard Input/Output)**

Most MCP servers use stdio transport:

.. code-block:: yaml

   mcp_servers:
     - name: "weather"
       type: "stdio"                # stdio transport
       command: "npx"               # Command to launch server
       args: ["-y", "@modelcontextprotocol/server-weather"]

**streamable-http (HTTP/SSE)**

Some MCP servers use HTTP with Server-Sent Events:

.. code-block:: yaml

   mcp_servers:
     - name: "custom_api"
       type: "streamable-http"      # HTTP transport
       url: "http://localhost:8080/mcp/sse"

Configuration Parameters
~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - Parameter
     - Required
     - Description
   * - ``name``
     - Yes
     - Unique name for the MCP server
   * - ``type``
     - Yes
     - Transport: ``"stdio"`` or ``"streamable-http"``
   * - ``command``
     - stdio only
     - Command to run the MCP server
   * - ``args``
     - stdio only
     - Arguments for the command
   * - ``url``
     - http only
     - Server endpoint URL
   * - ``env``
     - No
     - Environment variables to pass

Variable Substitution
~~~~~~~~~~~~~~~~~~~~~

MassGen supports variable substitution in MCP configurations:

**Built-in Variables:**

* ``${cwd}`` - Replaced with the agent's working directory (from ``backend.cwd``)
* Works anywhere in the backend config (``args``, ``env``, etc.)

**Environment Variables:**

* Use ``${VARIABLE_NAME}`` syntax (must be UPPERCASE)
* Resolved from your ``.env`` file or system environment
* Work in both ``args`` and ``env`` parameters

.. code-block:: yaml

   mcp_servers:
     - name: "playwright"
       type: "stdio"
       command: "npx"
       args:
         - "@playwright/mcp@latest"
         - "--output-dir=${cwd}"                # Built-in: agent's working directory
         - "--user-data-dir=${cwd}/profile"
       env:
         API_KEY: "${API_KEY}"                  # Environment variable from .env file

**Important:**

* ``${cwd}`` is lowercase and refers to the agent's working directory
* Environment variables must be UPPERCASE (e.g., ``${API_KEY}``, ``${BRAVE_API_KEY}``)
* Both systems work together but are resolved separately

Common MCP Servers
------------------

Weather
~~~~~~~

.. code-block:: yaml

   mcp_servers:
     - name: "weather"
       type: "stdio"
       command: "npx"
       args: ["-y", "@modelcontextprotocol/server-weather"]

Web Search (Brave)
~~~~~~~~~~~~~~~~~~

Requires ``BRAVE_API_KEY`` in your ``.env`` file:

.. code-block:: yaml

   mcp_servers:
     - name: "search"
       type: "stdio"
       command: "npx"
       args: ["-y", "@modelcontextprotocol/server-brave-search"]
       env:
         BRAVE_API_KEY: "${BRAVE_API_KEY}"

Playwright (Browser Automation)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Enables browser automation with screenshot and PDF capabilities:

.. code-block:: yaml

   mcp_servers:
     playwright:
       type: "stdio"
       command: "npx"
       args:
         - "@playwright/mcp@latest"
         - "--browser=chrome"              # Browser choice (chrome, firefox, webkit)
         - "--caps=vision,pdf"             # Enable vision and PDF capabilities
         - "--output-dir=${cwd}"           # Save screenshots/PDFs to workspace
         - "--user-data-dir=${cwd}/playwright-profile"  # Persistent browser profile

**Advanced Options:**

* ``--browser`` - Browser to use: ``chrome``, ``firefox``, or ``webkit``
* ``--caps`` - Capabilities: ``vision`` (screenshots), ``pdf`` (PDF generation)
* ``--output-dir`` - Directory for saving screenshots and PDFs
* ``--user-data-dir`` - Persistent browser profile directory
* ``--save-trace`` - Save Playwright traces for debugging (uncomment to enable)

Discord
~~~~~~~

Requires Discord bot token. See `Discord MCP Setup Guide <https://github.com/Leezekun/MassGen/blob/main/@examples/docs/DISCORD_MCP_SETUP.md>`_:

.. code-block:: yaml

   mcp_servers:
     - name: "discord"
       type: "stdio"
       command: "npx"
       args: ["-y", "@modelcontextprotocol/server-discord"]
       env:
         DISCORD_BOT_TOKEN: "${DISCORD_BOT_TOKEN}"

Twitter
~~~~~~~

Requires Twitter API credentials. See `Twitter MCP Setup Guide <https://github.com/Leezekun/MassGen/blob/main/@examples/docs/TWITTER_MCP_ENESCINAR_SETUP.md>`_:

.. code-block:: yaml

   mcp_servers:
     - name: "twitter"
       type: "stdio"
       command: "npx"
       args: ["-y", "mcp-server-twitter-unofficial"]
       env:
         TWITTER_USERNAME: "${TWITTER_USERNAME}"
         TWITTER_PASSWORD: "${TWITTER_PASSWORD}"

Multiple MCP Servers
--------------------

Agents can use multiple MCP servers simultaneously:

.. code-block:: yaml

   agents:
     - id: "multi_tool_agent"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
         mcp_servers:
           # Web search
           - name: "search"
             type: "stdio"
             command: "npx"
             args: ["-y", "@modelcontextprotocol/server-brave-search"]
             env:
               BRAVE_API_KEY: "${BRAVE_API_KEY}"

           # Weather data
           - name: "weather"
             type: "stdio"
             command: "npx"
             args: ["-y", "@modelcontextprotocol/server-weather"]

The agent can use all tools together. For example: "Search for weather apps and check the weather in Paris"

.. note::
   **File operations** are handled automatically via the ``cwd`` parameter in your backend configuration. You don't need to add a filesystem MCP server manually.

Tool Filtering
--------------

Control which MCP tools are available to agents.

Backend-Level Filtering
~~~~~~~~~~~~~~~~~~~~~~~

Exclude specific tools at the backend level:

.. code-block:: yaml

   backend:
     type: "openai"
     model: "gpt-4o-mini"
     exclude_tools:
       - mcp__discord__discord_send_webhook_message  # Exclude dangerous tools
     mcp_servers:
       - name: "discord"
         type: "stdio"
         command: "npx"
         args: ["-y", "@modelcontextprotocol/server-discord"]

MCP-Server-Specific Filtering
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Override with allowed tools per MCP server:

.. code-block:: yaml

   backend:
     type: "openai"
     model: "gpt-4o-mini"
     mcp_servers:
       - name: "discord"
         type: "stdio"
         command: "npx"
         args: ["-y", "@modelcontextprotocol/server-discord"]
         allowed_tools:  # Whitelist specific tools
           - mcp__discord__discord_read_messages
           - mcp__discord__discord_send_message

Merged Exclusions
~~~~~~~~~~~~~~~~~

``exclude_tools`` from both backend and MCP server configs are combined:

.. code-block:: yaml

   backend:
     exclude_tools:
       - mcp__discord__send_webhook  # Backend-level exclusion
     mcp_servers:
       - name: "discord"
         exclude_tools:
           - mcp__discord__delete_channel  # MCP-level exclusion
         # Both tools are excluded

MCP Planning Mode
-----------------

**NEW in v0.0.29**

Planning mode prevents irreversible actions during multi-agent coordination.

How It Works
~~~~~~~~~~~~

**Without planning mode:**

1. All agents execute MCP tools during coordination
2. Risk of duplicate or premature actions
3. Example: Multiple agents posting to Discord

**With planning mode:**

1. During coordination: Agents **plan** tool usage without execution
2. Agents discuss and vote on best approach
3. Final agent: **Executes** the planned tools

Configuration
~~~~~~~~~~~~~

Enable planning mode in orchestrator config:

.. code-block:: yaml

   orchestrator:
     coordination:
       enable_planning_mode: true
       planning_mode_instruction: |
         PLANNING MODE ACTIVE: You are currently in the coordination phase.
         During this phase:
         1. Describe your intended actions and reasoning
         2. Analyze other agents' proposals
         3. Use only 'vote' or 'new_answer' tools for coordination
         4. DO NOT execute any actual MCP commands
         5. Save execution for final presentation phase

Example Configuration
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   agents:
     - id: "gemini_agent"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
         # MCP servers can be added here (e.g., weather, search)
         # File operations are handled via cwd parameter

   orchestrator:
     coordination:
       enable_planning_mode: true
       planning_mode_instruction: |
         Focus on planning and coordination rather than execution.
         Describe what you would do, don't actually do it yet.

Usage
~~~~~

.. code-block:: bash

   # Five agents with planning mode (no execution during coordination)
   massgen \
     --config @examples/tools/planning/five_agents_filesystem_mcp_planning_mode.yaml \
     "Create a comprehensive project structure with documentation"

**What happens:**

1. **Coordination phase** → Agents discuss and plan file structure
2. **Voting** → Agents vote for best plan
3. **Final presentation** → Winning agent **executes** the plan

Multi-Backend Support
~~~~~~~~~~~~~~~~~~~~~

Planning mode works across:

* Response API (Claude)
* Chat Completions (OpenAI, Grok, etc.)
* Gemini with session-based tool execution

Complete Example
----------------

Full configuration with multiple MCP servers and planning mode:

.. code-block:: yaml

   agents:
     - id: "research_agent"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
         mcp_servers:
           # Web search
           - name: "search"
             type: "stdio"
             command: "npx"
             args: ["-y", "@modelcontextprotocol/server-brave-search"]
             env:
               BRAVE_API_KEY: "${BRAVE_API_KEY}"
             allowed_tools:
               - mcp__search__brave_web_search

           # Weather
           - name: "weather"
             type: "stdio"
             command: "npx"
             args: ["-y", "@modelcontextprotocol/server-weather"]

     - id: "analyst_agent"
       backend:
         type: "openai"
         model: "gpt-5-nano"
         # File operations handled via cwd parameter

   orchestrator:
     coordination:
       enable_planning_mode: true
       planning_mode_instruction: |
         PLANNING MODE: Describe your intended tool usage.
         Do not execute tools during coordination.

   ui:
     display_type: "rich_terminal"
     logging_enabled: true

Security Considerations
-----------------------

1. **Tool Filtering** - Use ``allowed_tools`` and ``exclude_tools`` to limit capabilities
2. **Planning Mode** - Enable for tasks with irreversible actions
3. **Environment Variables** - Store API keys in ``.env``, never in config files
4. **Path Restrictions** - Limit filesystem server to specific directories
5. **Review Permissions** - Check what each MCP server can do before enabling

Troubleshooting
---------------

**MCP server not found:**

Ensure the MCP server package is installed:

.. code-block:: bash

   npx -y @modelcontextprotocol/server-weather

**Tools not appearing:**

* Check backend MCP support (see table above)
* Verify ``mcp_servers`` configuration
* Check for tool filtering (``allowed_tools``, ``exclude_tools``)

**Environment variables not working:**

.. code-block:: bash

   # Set in .env file
   BRAVE_API_KEY=your_key_here

   # Reference in config
   env:
     BRAVE_API_KEY: "${BRAVE_API_KEY}"

**Planning mode not working:**

* Ensure backend supports planning mode
* Check ``enable_planning_mode: true`` in orchestrator config
* Verify ``planning_mode_instruction`` is set

Next Steps
----------

* :doc:`file_operations` - Filesystem MCP integration
* :doc:`project_integration` - Using MCP with context paths
* :doc:`multi_turn_mode` - MCP in interactive sessions
* :doc:`../quickstart/running-massgen` - More examples
* `MCP Server Registry <https://github.com/modelcontextprotocol/servers>`_ - Browse available MCP servers
