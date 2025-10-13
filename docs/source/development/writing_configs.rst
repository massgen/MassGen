Writing Configuration Files
===========================

This guide explains how to create new YAML configuration files for MassGen agents. Whether you're contributing examples, creating case studies, or building custom multi-agent workflows, following these conventions ensures consistency and maintainability.

When to Create a New Config
----------------------------

Create a new configuration file when you want to:

* Demonstrate a new feature or capability
* Provide an example for a specific use case
* Create a case study for a release
* Share a reusable multi-agent workflow
* Test a new backend or tool integration

File Naming and Location
-------------------------

**Naming Pattern**

.. code-block:: text

   {agent_description}_{feature}.yaml

**Examples:**

* ``gpt5mini_gpt5nano_documentation_evolution.yaml``
* ``gemini_flash_claude_sonnet_web_research.yaml``
* ``three_agents_filesystem_mcp_planning.yaml``

**Location**

Place config files in the appropriate category directory:

.. code-block:: text

   @examples/tools/{category}/

**Categories:**

* ``basic/`` - Simple single/multi-agent examples without tools
* ``tools/filesystem/`` - Filesystem operations
* ``tools/web-search/`` - Web search capabilities
* ``tools/code-execution/`` - Code execution features
* ``tools/multimodal/`` - Image generation, vision, audio
* ``tools/mcp/`` - MCP tool integrations
* ``tools/planning/`` - Planning mode examples
* Create new categories as needed for new features

Critical Configuration Rules
-----------------------------

Before Creating a Config
~~~~~~~~~~~~~~~~~~~~~~~~~

**ALWAYS Read Existing Configs First**

.. warning::

   **NEVER hallucinate or invent config properties!**

   Always read 2-3 existing config files in the relevant category to understand:

   * Exact property names and spelling
   * Property placement (backend-level vs orchestrator-level)
   * Current model naming conventions
   * Structure and formatting style

Use this approach:

.. code-block:: bash

   # 1. Find similar configs
   ls @examples/tools/{relevant_category}/

   # 2. Read them to understand structure
   cat @examples/tools/multimodal/gpt5mini_gpt5nano_image_analysis.yaml
   cat @examples/basic/multi/three_agents_default.yaml

Configuration Rules
~~~~~~~~~~~~~~~~~~~

**DO:**

✅ **Prefer GPT-5 variants** (``gpt-5-nano``, ``gpt-5-mini``) over GPT-4o for cost-effectiveness

✅ **Use cost-effective backends** (Gemini Flash, GPT-5-mini) unless specific features are needed

✅ **Give both agents identical system_message** - Each agent should be able to complete the entire task independently (no specialized roles like "researcher" vs "writer")

✅ **Copy COMPLETE files** to resource directories - Never copy partial files that reference external dependencies

✅ **Use descriptive agent IDs** following conventions: ``agent_a``, ``agent_b`` or descriptive names

✅ **Separate agent workspaces**: ``workspace1``, ``workspace2``, or ``{agent_id}_workspace``

✅ **Include what happens comments** at the end explaining the expected execution flow

**DON'T:**

❌ **Never reference massgen v1** - Avoid any v1 paths or references to legacy versions

❌ **Don't invent properties** - Only use properties found in existing configs

❌ **Don't misplace properties**:

   * ``context_paths`` is an **ORCHESTRATOR property** (for read-only source files shared across agents)
   * ``cwd`` is a **BACKEND property** (for individual agent workspaces)
   * ``enable_web_search`` is a **BACKEND property**
   * ``enable_planning_mode`` is an **ORCHESTRATOR.COORDINATION property**

❌ **Don't include ``session_storage``** unless the config explicitly needs multi-turn mode

❌ **Don't suggest cleanup commands** that delete logs (avoid ``rm -rf .massgen/``)

Property Placement Reference
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Backend Level** (inside ``agent.backend``):

* ``type``, ``model``, ``api_key``
* ``temperature``, ``max_tokens``
* ``enable_web_search``, ``enable_code_execution``, ``enable_code_interpreter``
* ``enable_image_generation`` (for multimodal)
* ``cwd`` (working directory for this agent)
* ``mcp_servers`` (tool servers)
* ``exclude_tools``, ``allowed_tools``, ``disallowed_tools``
* ``max_thinking_tokens``, ``system_prompt`` (claude_code)

**Orchestrator Level** (top-level ``orchestrator``):

* ``snapshot_storage``, ``agent_temporary_workspace``
* ``session_storage`` (only for multi-turn)
* ``context_paths`` (shared read-only directories)
* ``coordination.enable_planning_mode``
* ``coordination.planning_mode_instruction``
* ``skip_coordination_rounds``, ``timeout``

**Top Level**:

* ``agents`` or ``agent``
* ``orchestrator``
* ``ui``

Complete Example Template
--------------------------

Here's a fully annotated config template showing all conventions:

.. code-block:: yaml

   # Example Configuration: {Feature Name}
   #
   # Use Case: {One sentence description}
   #
   # This configuration demonstrates:
   # - {Key capability 1}
   # - {Key capability 2}
   # - {Key capability 3}
   #
   # Run with:
   #   massgen \
   #     --config @examples/tools/{category}/{filename}.yaml \
   #     "{example prompt}"

   # ====================
   # AGENT DEFINITIONS
   # ====================
   agents:
     - id: "agent_a"
       system_message: |
         {Same system message for both agents - each should be able to complete the full task}

       backend:
         # Backend type and model
         type: "openai"           # Use openai for GPT-5 variants
         model: "gpt-5-mini"      # Prefer cost-effective models

         # Optional: LLM parameters
         temperature: 0.7
         max_tokens: 4000

         # Optional: Tool enablement (backend-level)
         enable_web_search: true           # For claude, gemini, openai, grok
         enable_code_execution: true       # For claude, gemini
         enable_image_generation: true     # For openai multimodal

         # Optional: Reasoning configuration (for o1/o3 models)
         text:
           verbosity: "medium"
         reasoning:
           effort: "medium"
           summary: "auto"

         # Optional: Agent workspace (backend-level)
         cwd: "workspace1"

         # Optional: MCP servers (backend-level)
         mcp_servers:
           - name: "filesystem"
             type: "stdio"
             command: "npx"
             args: ["-y", "@modelcontextprotocol/server-filesystem", "."]
             security:
               level: "high"
               allow_localhost: true

     - id: "agent_b"
       system_message: |
         {Same system message as agent_a}

       backend:
         type: "openai"
         model: "gpt-5-nano"      # Different model for diversity
         temperature: 0.7
         max_tokens: 4000

         # Agent workspace
         cwd: "workspace2"

   # ====================
   # ORCHESTRATOR CONFIGURATION
   # ====================
   orchestrator:
     # Workspace directories
     snapshot_storage: "massgen_logs/snapshots"
     agent_temporary_workspace: "massgen_logs/temp_workspaces"

     # Multi-turn mode (ONLY include if needed)
     # session_storage: "massgen_logs/sessions"

     # Optional: Planning mode coordination
     coordination:
       enable_planning_mode: true
       planning_mode_instruction: |
         PLANNING MODE: Describe your intended actions.
         Do not execute MCP tools during coordination.
         Save execution for final presentation phase.

     # Optional: Shared read-only context (orchestrator-level)
     context_paths:
       - path: "@examples/resources/v{X.Y.Z}-example/{subdirectory}"
         permission: "read"

   # ====================
   # UI CONFIGURATION
   # ====================
   ui:
     display_type: "rich_terminal"
     logging_enabled: true

   # ====================
   # EXECUTION FLOW
   # ====================
   # What happens:
   # 1. {Step 1 description}
   # 2. {Step 2 description}
   # 3. {Step 3 description}
   # 4. {Final outcome}

Resource Files
--------------

If your config needs source files for testing (e.g., code files to analyze, documents to process):

**Resource Directory Pattern:**

.. code-block:: text

   @examples/resources/v{X.Y.Z}-example/{subdirectory}/

**Examples:**

* ``@examples/resources/v0.0.29-example/python_project/``
* ``@examples/resources/v0.0.30-example/documentation/``

**Rules:**

1. Copy **COMPLETE, self-contained files** to resource directories
2. Never copy partial files that reference external dependencies
3. Files in resource directories shouldn't change when MassGen code evolves
4. Reference resources via ``context_paths`` at orchestrator level

Example resource setup:

.. code-block:: yaml

   orchestrator:
     context_paths:
       - path: "@examples/resources/v0.0.29-example/python_project"
         permission: "read"

Config Creation Workflow
-------------------------

Follow this workflow to create a new config:

**Step 1: Research Existing Configs**

.. code-block:: bash

   # Find similar configs
   ls @examples/tools/{relevant_category}/
   ls @examples/basic/multi/

   # Read 2-3 examples to understand structure
   cat @examples/tools/multimodal/example1.yaml
   cat @examples/tools/mcp/example2.yaml

**Step 2: Copy and Adapt Structure**

* Copy a similar existing config as your starting point
* Adapt values, never invent new properties
* Keep the same structure and organization

**Step 3: Configure Agents**

* Choose appropriate backend types and models
* Set identical ``system_message`` for all agents
* Configure separate ``cwd`` for each agent workspace
* Add tool enablement flags at backend level if needed

**Step 4: Configure Orchestrator**

* Set up workspace directories
* Add ``context_paths`` if sharing read-only files
* Configure ``coordination`` if using planning mode
* Only add ``session_storage`` if multi-turn is needed

**Step 5: Test the Config**

.. code-block:: bash

   # Test with a simple prompt
   massgen \
     --config @examples/tools/{category}/{your_config}.yaml \
     "Test prompt that exercises the key features"

**Step 6: Document Expected Behavior**

Add comments at the end explaining:

* What the config demonstrates
* Expected execution flow
* Key features being showcased

Validation Checklist
---------------------

Before submitting your config, verify:

Configuration Structure
~~~~~~~~~~~~~~~~~~~~~~~

☐ Follows naming convention: ``{agent1}_{agent2}_{feature}.yaml``

☐ Located in correct category: ``@examples/tools/{category}/``

☐ Header comment includes: use case, description, run command

☐ All property names match existing configs (no invented properties)

☐ Properties are at correct level (backend vs orchestrator)

Agent Configuration
~~~~~~~~~~~~~~~~~~~

☐ Uses cost-effective models (GPT-5 variants, Gemini Flash) when possible

☐ All agents have identical ``system_message`` (no specialized roles)

☐ Each agent has separate ``cwd`` workspace

☐ Tool enablement flags (``enable_web_search``, etc.) at backend level

☐ No references to massgen v1 or legacy paths

Orchestrator Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~

☐ ``context_paths`` at orchestrator level (not per-agent)

☐ ``session_storage`` only included if multi-turn mode needed

☐ Planning mode properly configured if used

☐ Workspace directories follow convention

Resources & Testing
~~~~~~~~~~~~~~~~~~~

☐ Resource files copied to ``@examples/resources/v{X.Y.Z}-example/``

☐ Resource files are complete and self-contained

☐ Config tested and confirmed working

☐ "What happens" comments explain execution flow

Getting Help with Configs
--------------------------

AI-Assisted Config Creation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

You can use AI agents to help create configuration files:

**Option 1: Use Claude Code**

If you're using Claude Code (recommended for contributors):

.. code-block:: text

   "I need to create a config that demonstrates {feature}. Can you help me
   create a properly structured YAML config following MassGen conventions?"

Claude Code has access to all existing configs and can:

* Read existing configs to understand current conventions
* Suggest appropriate models and backends
* Ensure property placement is correct
* Validate against established patterns

**Option 2: Use the case-study-writer Agent**

The case-study-writer agent (defined in ``.claude/agents/case-study-writer.md``) is specifically trained to create configs for case studies and can:

* Propose multiple config options
* Create the actual YAML files
* Set up resource directories
* Ensure all conventions are followed

**Option 3: Manual Creation**

Follow this guide manually, using existing configs as templates.

Common Patterns
---------------

Single Agent
~~~~~~~~~~~~

.. code-block:: yaml

   agent:  # Singular
     id: "my_agent"
     backend:
       type: "claude"
       model: "claude-sonnet-4"
     system_message: "You are a helpful assistant"

Two Agents with Different Models
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   agents:  # Plural
     - id: "agent_a"
       backend:
         type: "openai"
         model: "gpt-5-mini"
       system_message: "Shared task description"

     - id: "agent_b"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
       system_message: "Shared task description"

Agents with Filesystem Access
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   agents:
     - id: "agent_a"
       backend:
         type: "openai"
         model: "gpt-5-mini"
         cwd: "workspace1"  # Agent workspace

   orchestrator:
     context_paths:
       - path: "@examples/resources/v0.0.29-example/source"
         permission: "read"  # Shared read-only source

Agents with MCP Tools
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   agents:
     - id: "agent_a"
       backend:
         type: "claude"
         model: "claude-sonnet-4"
         mcp_servers:
           - name: "filesystem"
             type: "stdio"
             command: "npx"
             args: ["-y", "@modelcontextprotocol/server-filesystem", "."]
             security:
               level: "high"

Planning Mode Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   orchestrator:
     coordination:
       enable_planning_mode: true
       planning_mode_instruction: |
         PLANNING MODE ACTIVE:
         1. Describe intended actions
         2. Analyze other agents' proposals
         3. Use only vote/new_answer tools
         4. DO NOT execute MCP commands
         5. Save execution for final presentation

Multi-Turn Interactive Mode
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   orchestrator:
     session_storage: "massgen_logs/sessions"  # Enables multi-turn mode

See Also
--------

* :doc:`contributing` - General contribution guidelines
* :doc:`../reference/yaml_schema` - Complete YAML schema reference
* :doc:`../reference/supported_models` - Supported backends and models
* :doc:`../user_guide/backends` - Backend configuration details
* :doc:`../user_guide/mcp_integration` - MCP tool configuration
* :doc:`../quickstart/configuration` - Configuration basics
