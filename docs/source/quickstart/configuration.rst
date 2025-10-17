Configuration
=============

MassGen is configured using environment variables for API keys and YAML files for agent definitions and orchestrator settings. This guide shows you how to set up your configuration.

.. note::

   MassGen provides both a CLI and a Python API. Configuration is primarily done via the interactive setup wizard or YAML files.

   **Python API Note:** The Python API is currently in early development with basic functionality only. For advanced features and full control, use the CLI with YAML configuration files. See :doc:`../reference/python_api` for Python API details and status.

Configuration Methods
=====================

MassGen offers three ways to configure your agents:

1. **Interactive Setup Wizard** (Recommended for beginners)
2. **YAML Configuration Files** (For advanced customization)
3. **CLI Flags** (For quick one-off queries)

Interactive Setup Wizard
-------------------------

The easiest way to configure MassGen is through the interactive wizard:

.. code-block:: bash

   # First run automatically triggers the wizard
   massgen

   # Or manually launch it
   massgen --init

**The Config Builder Interface:**

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
   │  Interactive Configuration Builder                                           │
   │  Create custom multi-agent configurations in minutes!                        │
   ╰──────────────────────────────────────────────────────────────────────────────╯

The wizard guides you through 4 simple steps:

1. **Select Your Use Case**: Choose from pre-built templates (Research, Coding, Q&A, etc.)
2. **Configure Agents**: Select providers and models (wizard detects available API keys)
3. **Configure Tools**: Enable web search, code execution, file operations, etc.
4. **Review & Save**: Save to ``~/.config/massgen/config.yaml``

After completing the wizard, your configuration is ready to use:

.. code-block:: bash

   massgen "Your question"  # Uses default config automatically

Configuration Directory Structure
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

MassGen uses two directories for configuration:

**User Configuration** (``~/.config/massgen/``):

.. code-block:: text

   ~/.config/massgen/
   ├── config.yaml              # Default configuration (from wizard)
   ├── agents/                  # Your custom named configurations
   │   ├── research-team.yaml
   │   └── coding-agents.yaml
   └── .env                     # API keys (optional)

**Project Workspace** (``.massgen/`` in your project):

MassGen also creates a ``.massgen/`` directory in your project for sessions, workspaces, and snapshots. See :doc:`../user_guide/concepts` for details.

**Creating Named Configurations:**

.. code-block:: bash

   # Run the wizard in named config mode
   massgen --init

   # Choose to save to ~/.config/massgen/agents/ instead of default
   # Then use it:
   massgen --config research-team "Your question"

Environment Variables
---------------------

API keys are configured through environment variables or a ``.env`` file. After pip install, the setup wizard can create ``~/.config/massgen/.env`` for you.

Creating Your .env File
~~~~~~~~~~~~~~~~~~~~~~~

Copy the example environment file and add your API keys:

.. code-block:: bash

   # Copy the example file
   cp .env.example .env

   # Edit the file with your API keys
   # (Only add keys for the models you plan to use)

Example .env File
~~~~~~~~~~~~~~~~~

.. code-block:: bash

   # OpenAI (for GPT-5, GPT-4, etc.)
   OPENAI_API_KEY=sk-...

   # Anthropic Claude
   ANTHROPIC_API_KEY=sk-ant-...

   # Google Gemini
   GOOGLE_API_KEY=...

   # xAI Grok
   XAI_API_KEY=...

   # Azure OpenAI
   AZURE_OPENAI_API_KEY=...
   AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
   AZURE_OPENAI_API_VERSION=YOUR-AZURE-OPENAI-API-VERSION

   # Other providers (optional)
   CEREBRAS_API_KEY=...
   MOONSHOT_API_KEY=...
   ZHIPUAI_API_KEY=...

**Getting API Keys:**

* `OpenAI <https://platform.openai.com/api-keys>`_
* `Anthropic Claude <https://docs.anthropic.com/en/api/overview>`_
* `Google Gemini <https://ai.google.dev/gemini-api/docs>`_
* `xAI Grok <https://docs.x.ai/docs/overview>`_
* `Azure OpenAI <https://learn.microsoft.com/en-us/azure/ai-services/openai/>`_

YAML Configuration Files
-------------------------

MassGen uses YAML files to define agents, their backends, and orchestrator settings. Configuration files are stored in ``@examples/`` and can be referenced using the ``--config`` flag.

Basic Configuration Structure
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A minimal MassGen configuration has these top-level keys:

.. code-block:: yaml

   agents:              # List of agents (required)
     - id: "agent_id"   # Agent definitions
       backend: ...     # Backend configuration
       system_message: ...  # Optional system prompt

   orchestrator:        # Orchestrator settings (optional, required for file ops)
     snapshot_storage: "snapshots"
     agent_temporary_workspace: "temp_workspaces"
     context_paths: ...

   ui:                  # UI settings (optional)
     display_type: "rich_terminal"
     logging_enabled: true

Single Agent Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~

For a single agent, use the ``agents`` field (plural) with one entry:

.. code-block:: yaml

   # @examples/basic_single
   agents:                # Note: plural 'agents' even for single agent
     - id: "gpt-5-nano"
       backend:
         type: "openai"
         model: "gpt-5-nano"
         enable_web_search: true
         enable_code_interpreter: true

   ui:
     display_type: "rich_terminal"
     logging_enabled: true

.. warning::

   **Common Mistake**: When converting a single-agent config to multi-agent, remember to keep ``agents:`` (plural).

   While ``agent:`` (singular) is supported for single-agent configs, always use ``agents:`` (plural) for consistency - this prevents errors when adding more agents later.

**Run this configuration:**

.. code-block:: bash

   massgen \
     --config @examples/basic_single \
     "What is machine learning?"

Multi-Agent Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~

For multiple agents, add more entries to the ``agents`` list:

.. code-block:: yaml

   # @examples/basic_multi
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

   ui:
     display_type: "rich_terminal"
     logging_enabled: true

**Run this configuration:**

.. code-block:: bash

   massgen \
     --config @examples/basic_multi \
     "Analyze the pros and cons of renewable energy"

Backend Configuration
---------------------

Each agent requires a ``backend`` configuration that specifies the model provider and settings.

.. important::
   **Choosing the right backend?** Different backends support different features (web search, code execution, file operations, etc.). Check the **Backend Capabilities Matrix** in :doc:`../user_guide/backends` to see which features are available for each backend type.

Backend Types
~~~~~~~~~~~~~

Available backend types:

* ``openai`` - OpenAI models (GPT-5, GPT-4, etc.)
* ``claude`` - Anthropic Claude models
* ``claude_code`` - Claude Code SDK with dev tools
* ``gemini`` - Google Gemini models
* ``grok`` - xAI Grok models
* ``azure_openai`` - Azure OpenAI deployment
* ``zai`` - ZhipuAI GLM models
* ``ag2`` - AG2 framework integration
* ``lmstudio`` - Local models via LM Studio
* ``chatcompletion`` - Generic OpenAI-compatible API

Basic Backend Structure
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   backend:
     type: "openai"           # Backend type (required)
     model: "gpt-5-nano"      # Model name (required)
     api_key: "..."           # Optional - uses env var by default
     temperature: 0.7         # Optional - model parameters
     max_tokens: 4096         # Optional - response length

Backend-Specific Features
~~~~~~~~~~~~~~~~~~~~~~~~~

Different backends support different built-in tools:

.. code-block:: yaml

   # OpenAI with tools
   backend:
     type: "openai"
     model: "gpt-5-nano"
     enable_web_search: true
     enable_code_interpreter: true

   # Gemini with tools
   backend:
     type: "gemini"
     model: "gemini-2.5-flash"
     enable_web_search: true
     enable_code_execution: true

   # Claude Code with workspace
   backend:
     type: "claude_code"
     model: "claude-sonnet-4"
     cwd: "workspace"          # Working directory for file operations

See :doc:`../reference/yaml_schema` for complete backend options.

System Messages
---------------

Customize agent behavior with system messages:

.. code-block:: yaml

   agents:
     - id: "research_agent"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
       system_message: |
         You are a research specialist. When answering questions:
         1. Always search for current information
         2. Cite your sources
         3. Provide comprehensive analysis

     - id: "code_agent"
       backend:
         type: "openai"
         model: "gpt-5-nano"
       system_message: |
         You are a coding expert. When solving problems:
         1. Write clean, well-documented code
         2. Use code execution to test solutions
         3. Explain your approach clearly

Orchestrator Configuration
--------------------------

Control workspace sharing and project integration:

.. code-block:: yaml

   orchestrator:
     snapshot_storage: "snapshots"              # Workspace snapshots for sharing
     agent_temporary_workspace: "temp_workspaces"  # Temporary workspaces
     context_paths:                             # Project integration
       - path: "/absolute/path/to/project"
         permission: "read"                     # read or write

Advanced Configuration
----------------------

MCP Integration
~~~~~~~~~~~~~~~

Add MCP (Model Context Protocol) servers for external tools:

.. code-block:: yaml

   agents:
     - id: "agent_with_mcp"
       backend:
         type: "openai"
         model: "gpt-5-nano"
         mcp_servers:
           - name: "weather"
             type: "stdio"
             command: "npx"
             args: ["-y", "@fak111/weather-mcp"]

See :doc:`../user_guide/mcp_integration` for details.

File Operations
~~~~~~~~~~~~~~~

Enable file system access for agents:

.. code-block:: yaml

   agents:
     - id: "file_agent"
       backend:
         type: "claude_code"
         model: "claude-sonnet-4"
         cwd: "workspace"       # Agent's working directory

   orchestrator:
     snapshot_storage: "snapshots"
     agent_temporary_workspace: "temp_workspaces"

See :doc:`../user_guide/file_operations` for details.

Project Integration
~~~~~~~~~~~~~~~~~~~

Share directories with agents (read or write access):

.. code-block:: yaml

   agents:
     - id: "project_agent"
       backend:
         type: "claude_code"
         cwd: "workspace"

   orchestrator:
     context_paths:
       - path: "/absolute/path/to/project/src"
         permission: "read"      # Agents can analyze code
       - path: "/absolute/path/to/project/docs"
         permission: "write"     # Agents can update docs

See :doc:`../user_guide/project_integration` for details.

Protected Paths
~~~~~~~~~~~~~~~

Make specific files read-only within writable context paths:

.. code-block:: yaml

   orchestrator:
     context_paths:
       - path: "/project"
         permission: "write"
         protected_paths:
           - "config.json"        # Read-only
           - "template.html"      # Read-only
           # Other files remain writable

**Use Case**: Allow agents to modify most files while protecting critical configurations or templates.

See :doc:`../user_guide/protected_paths` for complete documentation.

Planning Mode
~~~~~~~~~~~~~

Prevent irreversible actions during multi-agent coordination:

.. code-block:: yaml

   orchestrator:
     coordination:
       enable_planning_mode: true
       planning_mode_instruction: |
         PLANNING MODE: Describe your intended actions without executing.
         Save execution for the final presentation phase.

**Use Case**: File operations, API calls, or any task with irreversible consequences.

See :doc:`../user_guide/planning_mode` for complete documentation.

Timeout Configuration
~~~~~~~~~~~~~~~~~~~~~

Control maximum coordination time:

.. code-block:: yaml

   timeout_settings:
     orchestrator_timeout_seconds: 1800  # 30 minutes (default)

**CLI Override**:

.. code-block:: bash

   massgen --orchestrator-timeout 600 --config config.yaml

See :doc:`../reference/timeouts` for complete timeout documentation.

Configuration Without Files
---------------------------

For quick tests, you can use CLI flags without a configuration file:

.. code-block:: bash

   # Single agent with model flag
   massgen --model gemini-2.5-flash "Your question"

   # With backend specification
   massgen --backend claude --model claude-sonnet-4 "Your question"

   # With custom system message
   massgen \
     --model gpt-5-nano \
     --system-message "You are a helpful coding assistant" \
     "Write a Python function to sort a list"

CLI Quick Setup
---------------

For quick single-agent testing without a configuration file:

.. code-block:: bash

   massgen --model gemini-2.5-flash "Your question"

You can also specify backend type and system messages:

.. code-block:: bash

   massgen --backend claude --model claude-sonnet-4 \
     --system-message "You are a helpful coding assistant" \
     "Write a Python function"

For the complete list of CLI parameters, see :doc:`../reference/cli`

Configuration Best Practices
-----------------------------

1. **Start Simple**: Use single agent configs for testing, then scale to multi-agent
2. **Use Environment Variables**: Never commit API keys to version control
3. **Organize Configs**: Group related configurations in directories
4. **Comment Your YAML**: Add comments to explain agent roles and settings
5. **Test Incrementally**: Verify each agent works before combining them
6. **Version Your Configs**: Track configuration changes in version control

Example Configuration Templates
-------------------------------

All configuration examples are in ``@examples/``:

* ``@examples/basic_single`` - Single agent configuration
* ``@examples/basic_multi`` - Multi-agent collaboration
* ``@examples/tools/mcp/*`` - MCP integration examples
* ``@examples/tools/filesystem/*`` - File operation examples
* ``@examples/ag2/*`` - AG2 framework integration

See the `Configuration Guide <https://github.com/Leezekun/MassGen/blob/main/@examples/README.md>`_ for the complete catalog.

Next Steps
----------

**Excellent! You understand configuration basics. Here's your path forward:**

✅ **You are here:** You know how to configure agents in YAML

⬜ **Put it to use:** :doc:`../examples/basic_examples` - Copy ready-made configurations

⬜ **Go deeper:** :doc:`../user_guide/concepts` - Understand how multi-agent coordination works

⬜ **Add capabilities:** :doc:`../user_guide/mcp_integration` - Integrate external tools

**Need a reference?** The complete configuration schema is at :doc:`../reference/yaml_schema`

Troubleshooting
---------------

**Configuration not found:**

Ensure the path is correct relative to the MassGen directory:

.. code-block:: bash

   # Correct - relative to MassGen root
   massgen --config @examples/basic_multi

   # Incorrect - missing massgen/ prefix
   massgen --config configs/basic/multi/three_agents_default.yaml

**API key not found:**

Check that your ``.env`` file exists and contains the correct key:

.. code-block:: bash

   # Verify .env file exists
   ls -la .env

   # Check for the required key
   grep "OPENAI_API_KEY" .env

**YAML syntax error:**

Validate your YAML syntax:

.. code-block:: bash

   python -c "import yaml; yaml.safe_load(open('your-config.yaml'))"
