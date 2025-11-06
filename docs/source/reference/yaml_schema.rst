YAML Configuration Reference
============================

Complete YAML configuration schema for MassGen.

.. note::

   For a complete overview of supported models and capabilities, see :doc:`supported_models`.

Configuration Hierarchy
-----------------------

MassGen configurations have a clear hierarchy of settings. Understanding this structure helps you place parameters in the correct location.

**Configuration Levels:**

1. **Top Level** - Global settings

   - ``agents`` or ``agent``: List of agents (or single agent)
   - ``memory``: Memory system configuration (conversation + persistent)
   - ``orchestrator``: Coordination and workspace settings
   - ``ui``: Display and logging settings

2. **Agent Level** - Per-agent settings (inside ``agents[]``)

   - ``id``: Unique agent identifier
   - ``backend``: Backend configuration object
   - ``system_message``: Agent-specific instructions

3. **Backend Level** - Model and tool settings (inside ``agent.backend``)

   - Core: ``type``, ``model``, ``api_key``, ``temperature``, ``max_tokens``
   - Tool Enablement: ``enable_web_search``, ``enable_code_execution``, ``enable_code_interpreter``
   - MCP Integration: ``mcp_servers``, ``exclude_tools``
   - Backend-Specific: ``cwd``, ``permission_mode``, ``allowed_tools``, etc.

4. **MCP Server Level** - Tool server settings (inside ``backend.mcp_servers[]``)

   - Connection: ``name``, ``type``, ``command``, ``args``, ``url``, ``env``
   - Security: ``security`` object (``level``, ``allow_localhost``, ``allow_private_ips``)
   - Tool Filtering: ``allowed_tools``, ``exclude_tools``

5. **Orchestrator Level** - Multi-agent coordination (top-level ``orchestrator``)

   - Workspace: ``snapshot_storage``, ``agent_temporary_workspace``
   - Project Integration: ``context_paths``
   - Coordination: ``coordination.enable_planning_mode``, ``coordination.planning_mode_instruction``, ``coordination.max_orchestration_restarts``
   - Debug: ``debug_final_answer``
   - Advanced: ``skip_coordination_rounds``, ``timeout``

6. **UI Level** - Display settings (top-level ``ui``)

   - ``display_type``: "rich_terminal" or "simple"
   - ``logging_enabled``: Enable/disable logging

Backend Types Overview
----------------------

MassGen supports multiple backend types with varying capabilities:

**API-Based Backends:**

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Backend Type
     - Description & Key Features
   * - ``claude``
     - Anthropic's Claude API with full tool support and MCP integration
   * - ``claude_code``
     - Claude Code SDK with native dev tools (Read, Write, Edit, Bash, etc.)
   * - ``gemini``
     - Google's Gemini API with planning mode and MCP support
   * - ``openai``
     - OpenAI's GPT models with full tool and MCP support
   * - ``grok``
     - xAI's Grok models with web search and MCP integration
   * - ``azure_openai``
     - Azure-deployed OpenAI models (limited tool support)
   * - ``zai``
     - ZhipuAI's GLM models with basic MCP support
   * - ``chatcompletion``
     - **Generic OpenAI-compatible backend** - Works with Cerebras, Together AI, Fireworks, Groq, OpenRouter, etc. Requires ``base_url`` parameter

**Local/Inference Backends:**

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Backend Type
     - Description & Key Features
   * - ``lmstudio``
     - Local LM Studio server for running open-weight models
   * - ``vllm``
     - vLLM inference server (auto-detects port 8000)
   * - ``sglang``
     - SGLang inference server (auto-detects port 30000)

**Framework Backends:**

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Backend Type
     - Description & Key Features
   * - ``ag2``
     - AG2 framework integration with code execution support

Basic Structure
---------------

.. code-block:: yaml

   # Agent definitions (required)
   agents:
     - id: "agent1"
       backend:
         # Backend configuration
       system_message: "..."

   # Orchestrator settings (optional)
   orchestrator:
     # Coordination and workspace settings

   # UI settings (optional)
   ui:
     # Display and logging configuration

Agent Configuration
-------------------

Single Agent
~~~~~~~~~~~~

.. code-block:: yaml

   agent:  # Singular for single agent
     id: "my_agent"
     backend:
       type: "claude"
       model: "claude-sonnet-4"
     system_message: "You are a helpful assistant"

Multiple Agents
~~~~~~~~~~~~~~~

.. code-block:: yaml

   agents:  # Plural for multiple agents
     - id: "agent1"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
       system_message: "You are a researcher"

     - id: "agent2"
       backend:
         type: "openai"
         model: "gpt-5-nano"
       system_message: "You are an analyst"

Backend Configuration
---------------------

Basic Backend
~~~~~~~~~~~~~

.. code-block:: yaml

   backend:
     type: "openai"              # Backend type (required)
     model: "gpt-5-mini"         # Model name (required)
     api_key: "${API_KEY}"       # Optional, uses env var by default
     temperature: 0.7            # Optional
     max_tokens: 2000            # Optional

Claude Code Backend
~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   backend:
     type: "claude_code"
     model: "sonnet"
     cwd: "workspace"            # Working directory for file operations
     permission_mode: "bypassPermissions"  # Optional

With MCP Servers
~~~~~~~~~~~~~~~~

.. code-block:: yaml

   backend:
     type: "gemini"
     model: "gemini-2.5-flash"
     mcp_servers:
       - name: "weather"
         type: "stdio"
         command: "npx"
         args: ["-y", "@modelcontextprotocol/server-weather"]
       - name: "search"
         type: "stdio"
         command: "npx"
         args: ["-y", "@modelcontextprotocol/server-brave-search"]
         env:
           BRAVE_API_KEY: "${BRAVE_API_KEY}"

Tool Filtering
~~~~~~~~~~~~~~

.. code-block:: yaml

   backend:
     type: "openai"
     model: "gpt-4o-mini"
     exclude_tools:  # Backend-level exclusions
       - mcp__discord__send_webhook
     mcp_servers:
       - name: "discord"
         type: "stdio"
         command: "npx"
         args: ["-y", "@modelcontextprotocol/server-discord"]
         allowed_tools:  # Server-specific whitelist
           - mcp__discord__read_messages
           - mcp__discord__send_message

AG2 Backend
~~~~~~~~~~~

.. code-block:: yaml

   backend:
     type: ag2
     agent_config:
       type: assistant           # or "conversable"
       name: "AG2_Coder"
       system_message: "You write Python code"
       llm_config:
         api_type: "openai"
         model: "gpt-4o"
       code_execution_config:
         executor:
           type: "LocalCommandLineCodeExecutor"
           timeout: 60
           work_dir: "./workspace"

Orchestrator Configuration
--------------------------

Basic Orchestrator
~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   orchestrator:
     snapshot_storage: "snapshots"
     agent_temporary_workspace: "temp_workspaces"
     session_storage: "sessions"  # For interactive mode

Context Paths
~~~~~~~~~~~~~

.. code-block:: yaml

   orchestrator:
     context_paths:
       - path: "/absolute/path/to/src"
         permission: "read"       # Read-only access
       - path: "/absolute/path/to/docs"
         permission: "write"      # Write access for final agent

Coordination Config
~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   orchestrator:
     coordination:
       enable_planning_mode: true
       planning_mode_instruction: |
         PLANNING MODE: Describe intended actions.
         Do not execute during coordination phase.

UI Configuration
----------------

.. code-block:: yaml

   ui:
     display_type: "rich_terminal"  # or "simple"
     logging_enabled: true

Complete Example
----------------

Full multi-agent configuration demonstrating all 6 configuration levels:

.. code-block:: yaml

   # ========================================
   # LEVEL 1: TOP LEVEL - Global Settings
   # ========================================
   # Define agents, orchestrator, and UI at the top level

   # ========================================
   # LEVEL 2: AGENT LEVEL - Per-Agent Settings
   # ========================================
   agents:
     # Agent 1: Gemini with web search and tool enablement
     - id: "researcher"
       system_message: "You are a researcher with web search and weather tools"

       # ========================================
       # LEVEL 3: BACKEND LEVEL - Model & Tools
       # ========================================
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
         temperature: 0.7
         max_tokens: 2000

         # Tool Enablement Flags (Backend Level)
         enable_web_search: true           # Gemini built-in web search
         enable_code_execution: true       # Gemini code execution

         # Backend-level tool filtering
         exclude_tools:
           - mcp__weather__set_location    # Prevent location changes

         # ========================================
         # LEVEL 4: MCP SERVER LEVEL - Tool Servers
         # ========================================
         mcp_servers:
           - name: "search"
             type: "stdio"
             command: "npx"
             args: ["-y", "@modelcontextprotocol/server-brave-search"]
             env:
               BRAVE_API_KEY: "${BRAVE_API_KEY}"

             # MCP Server-level security configuration
             security:
               level: "high"                # Strict security
               allow_localhost: true        # Allow local connections
               allow_private_ips: false     # Block private IPs

             # MCP Server-level tool filtering
             allowed_tools:
               - mcp__search__web_search
               - mcp__search__local_search

           - name: "weather"
             type: "stdio"
             command: "npx"
             args: ["-y", "@modelcontextprotocol/server-weather"]
             security:
               level: "permissive"          # Relaxed for testing

     # Agent 2: Claude Code with native tools
     - id: "coder"
       system_message: "You write and execute code with file operations"
       backend:
         type: "claude_code"
         model: "claude-sonnet-4-20250514"
         cwd: "coder_workspace"             # Working directory
         permission_mode: "bypassPermissions"

         # Claude Code-specific parameters
         max_thinking_tokens: 10000         # Extended reasoning
         system_prompt: "You are an expert Python developer"
         disallowed_tools:                  # Blacklist dangerous ops
           - "Bash(rm*)"
           - "Bash(sudo*)"
           - "WebSearch"                    # Block web access

         # File operations handled via cwd parameter

     # Agent 3: OpenAI with code interpreter
     - id: "analyst"
       system_message: "You analyze data and generate reports"
       backend:
         type: "openai"
         model: "gpt-5-nano"

         # OpenAI-specific tool enablement
         enable_web_search: true            # OpenAI web search
         enable_code_interpreter: true      # Code interpreter tool

         cwd: "analyst_workspace"  # File operations handled via cwd

   # ========================================
   # LEVEL 5: ORCHESTRATOR LEVEL - Coordination
   # ========================================
   orchestrator:
     # Workspace management
     snapshot_storage: "snapshots"
     agent_temporary_workspace: "temp_workspaces"

     # Project integration
     context_paths:
       - path: "/Users/me/project/src"
         permission: "read"                 # Read-only access
       - path: "/Users/me/project/docs"
         permission: "write"                # Write access for winner

     # Coordination settings
     coordination:
       enable_planning_mode: true           # Enable planning mode
       max_orchestration_restarts: 2        # Allow up to 2 restarts (3 total attempts)
       planning_mode_instruction: |
         PLANNING MODE ACTIVE: You are in coordination phase.
         1. Describe your intended actions
         2. Analyze other agents' proposals
         3. Use only vote/new_answer tools
         4. DO NOT execute MCP commands
         5. Save execution for final presentation

     # Voting and answer control
     voting_sensitivity: "balanced"         # How critical agents are when voting (lenient/balanced)
     max_new_answers_per_agent: 2           # Cap new answers per agent (null=unlimited)
     answer_novelty_requirement: "balanced" # How different new answers must be (lenient/balanced/strict)

     # Advanced settings
     skip_coordination_rounds: false        # Normal coordination
     timeout:
       orchestrator_timeout_seconds: 1800   # 30 minute timeout

   # ========================================
   # LEVEL 6: UI LEVEL - Display Settings
   # ========================================
   ui:
     display_type: "rich_terminal"          # Rich terminal display
     logging_enabled: true                  # Enable logging

Parameter Reference
-------------------

Agents
~~~~~~

.. list-table::
   :header-rows: 1

   * - Parameter
     - Type
     - Required
     - Description
   * - ``id``
     - string
     - Yes
     - Unique agent identifier
   * - ``backend``
     - object
     - Yes
     - Backend configuration
   * - ``system_message``
     - string
     - No
     - System prompt for the agent

Backend
~~~~~~~

.. list-table::
   :header-rows: 1

   * - Parameter
     - Type
     - Required
     - Supported Backends
     - Description
   * - ``type``
     - string
     - Yes
     - All
     - Backend type: ``claude``, ``claude_code``, ``gemini``, ``openai``, ``grok``, ``azure_openai``, ``zai``, ``chatcompletion``, ``lmstudio``, ``vllm``, ``sglang``, ``ag2``
   * - ``model``
     - string
     - Yes
     - All
     - Model name (provider-specific)
   * - ``api_key``
     - string
     - No
     - All API backends
     - API key (uses env var by default)
   * - ``base_url``
     - string
     - Yes*
     - ``chatcompletion``, ``lmstudio``, ``vllm``, ``sglang``
     - API endpoint URL (required for chatcompletion)
   * - ``cwd``
     - string
     - No
     - ``claude_code``
     - Working directory for file operations
   * - ``mcp_servers``
     - list
     - No
     - All except ``ag2``, ``azure_openai``
     - MCP server configurations
   * - ``exclude_tools``
     - list
     - No
     - All with tool support
     - Tools to exclude from this backend
   * - ``temperature``
     - float
     - No
     - All
     - Sampling temperature (0.0-1.0)
   * - ``max_tokens``
     - integer
     - No
     - All
     - Maximum response tokens
   * - ``permission_mode``
     - string
     - No
     - ``claude_code``
     - Permission handling: ``bypassPermissions`` or default
   * - ``agent_config``
     - object
     - Yes*
     - ``ag2``
     - AG2-specific agent configuration (required for AG2)
   * - ``enable_web_search``
     - boolean
     - No
     - ``claude``, ``gemini``, ``openai``, ``grok``, ``chatcompletion``
     - Enable built-in web search capability
   * - ``enable_code_execution``
     - boolean
     - No
     - ``claude``, ``gemini``
     - Enable built-in code execution tool
   * - ``enable_code_interpreter``
     - boolean
     - No
     - ``openai``
     - Enable OpenAI code interpreter tool
   * - ``allowed_tools``
     - list
     - No
     - ``claude_code``
     - Whitelist of allowed Claude Code tools (legacy - use disallowed_tools instead)
   * - ``disallowed_tools``
     - list
     - No
     - ``claude_code``
     - Blacklist of dangerous tools to block (e.g., ["Bash(rm*)", "Bash(sudo*)"])
   * - ``max_thinking_tokens``
     - integer
     - No
     - ``claude_code``
     - Maximum tokens for internal thinking (default: 8000)
   * - ``system_prompt``
     - string
     - No
     - ``claude_code``
     - Custom system prompt for Claude Code agent
   * - ``api_version``
     - string
     - Yes*
     - ``azure_openai``
     - Azure OpenAI API version (required, default: "2024-02-15-preview")

MCP Server
~~~~~~~~~~

.. list-table::
   :header-rows: 1

   * - Parameter
     - Type
     - Required
     - Description
   * - ``name``
     - string
     - Yes
     - Server name
   * - ``type``
     - string
     - Yes
     - "stdio" or "streamable-http"
   * - ``command``
     - string
     - stdio only
     - Command to launch server
   * - ``args``
     - list
     - stdio only
     - Command arguments
   * - ``url``
     - string
     - http only
     - Server URL
   * - ``env``
     - object
     - No
     - Environment variables
   * - ``allowed_tools``
     - list
     - No
     - Whitelist of allowed tools
   * - ``exclude_tools``
     - list
     - No
     - Tools to exclude
   * - ``security``
     - object
     - No
     - Security configuration for the MCP server

MCP Server Security
~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1

   * - Parameter
     - Type
     - Required
     - Description
   * - ``level``
     - string
     - No
     - Security level: ``"high"`` (strict, default) or ``"permissive"`` (relaxed for testing)
   * - ``allow_localhost``
     - boolean
     - No
     - Allow connections to localhost (required for local MCP servers)
   * - ``allow_private_ips``
     - boolean
     - No
     - Allow connections to private IP ranges (for testing environments)

Orchestrator
~~~~~~~~~~~~

.. list-table::
   :header-rows: 1

   * - Parameter
     - Type
     - Required
     - Description
   * - ``snapshot_storage``
     - string
     - No
     - Directory for workspace snapshots
   * - ``agent_temporary_workspace``
     - string
     - No
     - Directory for temporary workspaces
   * - ``context_paths``
     - list
     - No
     - Shared project directories
   * - ``coordination``
     - object
     - No
     - Coordination configuration (planning mode settings)
   * - ``skip_coordination_rounds``
     - boolean
     - No
     - Debug/test mode: skip voting rounds and go straight to final presentation (default: false)
   * - ``debug_final_answer``
     - string
     - No
     - Debug mode for restart feature: override final answer on attempt 1 only to test restart flow (default: null). Example: "I only created one file."
   * - ``timeout``
     - object
     - No
     - Timeout configuration

Coordination Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1

   * - Parameter
     - Type
     - Required
     - Description
   * - ``enable_planning_mode``
     - boolean
     - No
     - Enable planning mode during coordination (default: false). When enabled, agents plan without executing MCP tools during the coordination phase. Only the winning agent executes actions during final presentation.
   * - ``planning_mode_instruction``
     - string
     - No
     - Custom instruction added to agent prompts when planning mode is enabled. Should explain to agents that they should describe intended actions without executing them.
   * - ``max_orchestration_restarts``
     - integer
     - No
     - Maximum number of orchestration restarts allowed (default: 0). When set > 0, enables post-evaluation where the winning agent reviews the final answer and can request a restart with specific improvement instructions. Recommended values: 1-2.

.. note::

   **New in v0.1.3:** Orchestration restart enables automatic quality checks after coordination. The winning agent evaluates its own answer and can trigger a restart if the answer is incomplete or incorrect, with specific instructions for improvement.

.. note::

   **Planning Mode Support:** Planning mode works with all backends that support MCP integration (``claude``, ``claude_code``, ``gemini``, ``openai``, ``grok``, ``chatcompletion``, ``lmstudio``, ``vllm``, ``sglang``). It does NOT work with ``ag2`` or ``azure_openai``.

   **When to Use Planning Mode:**

   - When using MCP tools that perform irreversible actions (file deletion, database modifications, API calls)
   - When coordinating multiple agents that should agree on a plan before execution
   - When you want a "dry run" discussion phase before actual tool execution

   **How It Works:**

   1. **Coordination Phase** (with planning mode): Agents discuss and vote on approaches WITHOUT executing MCP tools
   2. **Final Presentation Phase**: The winning agent EXECUTES the planned actions

Voting and Answer Control
~~~~~~~~~~~~~~~~~~~~~~~~~~

These parameters control coordination behavior to balance quality and duration.

.. list-table::
   :header-rows: 1

   * - Parameter
     - Type
     - Required
     - Description
   * - ``voting_sensitivity``
     - string
     - No
     - Controls how critical agents are when evaluating answers. **Options:** ``"lenient"`` (default) - agents vote for existing answers more readily, faster convergence; ``"balanced"`` - agents apply detailed criteria (comprehensive, accurate, complete?) before voting, more thorough evaluation; ``"strict"`` - agents apply high standards of excellence (all aspects, edge cases, reference-quality) before voting, maximum quality.
   * - ``max_new_answers_per_agent``
     - integer or null
     - No
     - Maximum number of new answers each agent can provide. Once an agent reaches this limit, they can only vote (not provide new answers). **Options:** ``null`` (default) - unlimited answers; ``1``, ``2``, ``3``, etc. - cap at N answers per agent. Prevents endless coordination rounds.
   * - ``answer_novelty_requirement``
     - string
     - No
     - Controls how different new answers must be from existing ones to prevent rephrasing. **Options:** ``"lenient"`` (default) - no similarity checks (fastest); ``"balanced"`` - reject if >70% token overlap, requires meaningful differences; ``"strict"`` - reject if >50% token overlap, requires substantially different solutions.

**Example Configurations:**

Fast but thorough (recommended for balanced evaluation):

.. code-block:: yaml

   orchestrator:
     voting_sensitivity: "balanced"       # Critical evaluation
     max_new_answers_per_agent: 2         # But cap at 2 tries
     answer_novelty_requirement: "balanced"  # Must actually improve

Maximum quality with bounded time:

.. code-block:: yaml

   orchestrator:
     voting_sensitivity: "strict"          # Highest quality bar
     max_new_answers_per_agent: 3
     answer_novelty_requirement: "strict"   # Only accept real improvements

Quick convergence:

.. code-block:: yaml

   orchestrator:
     voting_sensitivity: "lenient"
     max_new_answers_per_agent: 1
     answer_novelty_requirement: "lenient"

Timeout Configuration
~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1

   * - Parameter
     - Type
     - Required
     - Description
   * - ``orchestrator_timeout_seconds``
     - integer
     - No
     - Maximum time for orchestrator coordination in seconds (default: 1800 = 30 minutes)

Context Path
~~~~~~~~~~~~

.. list-table::
   :header-rows: 1

   * - Parameter
     - Type
     - Required
     - Description
   * - ``path``
     - string
     - Yes
     - Absolute path to directory
   * - ``permission``
     - string
     - Yes
     - "read" or "write"

UI
~~

.. list-table::
   :header-rows: 1

   * - Parameter
     - Type
     - Required
     - Description
   * - ``display_type``
     - string
     - No
     - "rich_terminal" or "simple"
   * - ``logging_enabled``
     - boolean
     - No
     - Enable/disable logging

See Also
--------

* :doc:`../quickstart/configuration` - Configuration guide
* :doc:`../user_guide/mcp_integration` - MCP configuration details
* :doc:`../user_guide/project_integration` - Context paths setup
* :doc:`cli` - CLI parameters
