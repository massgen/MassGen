Core Concepts
=============

Understanding MassGen's core concepts is essential for using the system effectively.

What is MassGen?
-----------------

MassGen is a **multi-agent coordination system** that assigns tasks to multiple AI agents who work in parallel, share observations, vote for solutions, and converge on the best answer through natural consensus.

Think of it as a "parallel study group" for AI - agents learn from each other to produce better results than any single agent could achieve alone.

Configuration-Driven Architecture
----------------------------------

MassGen uses **YAML files** to configure everything, not Python code.

.. code-block:: yaml

   agents:
     - id: "researcher"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
       system_message: "You are a researcher"

     - id: "analyst"
       backend:
         type: "openai"
         model: "gpt-5-nano"
       system_message: "You are an analyst"

Run via command line:

.. code-block:: bash

   uv run python -m massgen.cli --config config.yaml "Your question"

This design makes MassGen:

* **Declarative** - Describe what you want, not how to do it
* **Version-controllable** - Config files in Git
* **Shareable** - Easy to share and reproduce setups
* **Language-agnostic** - No Python required for most users

.. seealso::
   :doc:`../quickstart/configuration` - Complete configuration guide with all options and examples

CLI-Based Execution
-------------------

MassGen is currently run via command line (a Python library API is planned for future releases):

**Quick single agent:**

.. code-block:: bash

   uv run python -m massgen.cli --model claude-3-5-sonnet-latest "Question"

**Multi-agent with config:**

.. code-block:: bash

   uv run python -m massgen.cli --config my_agents.yaml "Question"

**Interactive mode:**

.. code-block:: bash

   # Omit question for interactive chat
   uv run python -m massgen.cli --config my_agents.yaml

See :doc:`../reference/cli` for complete CLI reference.

Multi-Agent Coordination
-------------------------

How Coordination Works
~~~~~~~~~~~~~~~~~~~~~~

MassGen's coordination follows a natural collaborative flow where agents observe each other's work and converge on the best solution:

**At each step, agents can:**

1. **See recent answers** - Agents view the most recent answers from other agents
2. **Decide their action** - Each agent chooses to either:

   * **Provide a new answer** if they have a better approach or refinement
   * **Vote for an existing answer** they believe is best

3. **Share context through workspace snapshots** - When agents provide answers, their workspace state is captured, allowing other agents to see their work

**Coordination completes when:**

* All agents have voted for solutions
* The agent with most votes becomes the final presenter

**Final presentation:**

* The winning agent delivers the coordinated final answer using read/write permissions (if configured with context paths)

What Agents See
~~~~~~~~~~~~~~~

**Answer Context:**

Each agent sees the most recent labeled answers from other agents (e.g., "agent1.1", "agent2.1"). This lets agents:

* Compare different approaches
* Build on good insights
* Catch potential errors
* Decide whether to vote or provide a better answer

**Workspace Snapshots (for file operations):**

When an agent with filesystem capabilities provides an answer:

* Their workspace is saved as a snapshot
* Other agents can see this snapshot in their temporary workspace
* This enables code review, file analysis, and iterative refinement

Example: If Agent A writes code and provides answer "agent_a.1", Agent B can review that code in ``.massgen/temp_workspaces/agent_a/`` before deciding to vote or provide improvements.

Voting Mechanism
~~~~~~~~~~~~~~~~

Agents participate in democratic decision-making:

.. code-block:: text

   ┌─ Coordination Progress ─────────────────┐
   │ Agent      │ Status     │ Votes         │
   ├────────────┼────────────┼───────────────┤
   │ Researcher │ Voted      │ Analyst       │
   │ Analyst    │ Voted      │ Self          │
   │ Coder      │ Voted      │ Analyst       │
   └──────────────────────────────────────────┘

The system reaches natural consensus when all agents have voted. No forced agreement - agents vote for what they genuinely believe is best.

Benefits of Multi-Agent Approach
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

* **Diverse Perspectives** - Different models, different insights
* **Error Correction** - Agents catch each other's mistakes
* **Collaborative Refinement** - Ideas build on each other
* **Quality Convergence** - Natural selection of best solutions
* **Robustness** - System works even if some agents fail

Coordination Termination
~~~~~~~~~~~~~~~~~~~~~~~~~

Coordination ends when one of these conditions is met:

**Normal Completion:**

* ✅ **All agents have voted** - Consensus reached naturally
* ✅ **Winner selected** - Agent with most votes presents final answer

**Timeout:**

* ⏰ **Orchestrator timeout reached** (default: 30 minutes)
* System saves current state and terminates gracefully
* Partial results preserved

**Typical Duration:**

* Simple tasks: 1-5 minutes (2-3 coordination rounds)
* Standard tasks: 5-15 minutes (3-5 rounds)
* Complex tasks: 15-30 minutes (5-10 rounds)

**Configuration:**

.. code-block:: yaml

   timeout_settings:
     orchestrator_timeout_seconds: 1800  # 30 minutes (default)

**CLI Override:**

.. code-block:: bash

   uv run python -m massgen.cli --orchestrator-timeout 600 --config config.yaml

See :doc:`../reference/timeouts` for complete timeout documentation.

Agents & Backends
-----------------

Agent Definition
~~~~~~~~~~~~~~~~

Each agent has:

* **ID**: Unique identifier
* **Backend**: LLM provider (Claude, Gemini, GPT, etc.)
* **Model**: Specific model version
* **System Message**: Role and instructions
* **Tools**: Optional MCP servers or native capabilities

Example:

.. code-block:: yaml

   agents:
     - id: "code_expert"
       backend:
         type: "claude_code"
         model: "sonnet"
         cwd: "workspace"
       system_message: "You are a coding expert with file operations"

Backend Types
~~~~~~~~~~~~~

MassGen supports multiple backend providers:

* **API-based**: Claude, Gemini, GPT, Grok, Azure OpenAI, Z AI
* **Local**: LM Studio, vLLM, SGLang
* **External Frameworks**: AG2

Each backend type has different capabilities. See :doc:`../reference/supported_models` for details.

Workspace Isolation
-------------------

Each agent gets an isolated workspace for file operations, preventing interference during coordination.

**Example:**

.. code-block:: yaml

   agents:
     - id: "writer"
       backend:
         type: "claude_code"
         cwd: "writer_workspace"    # Isolated workspace

     - id: "reviewer"
       backend:
         type: "gemini"
         cwd: "reviewer_workspace"  # Separate workspace

.. seealso::
   :doc:`file_operations` - Complete workspace management guide including directory structure, snapshots, and safety features

MCP Tool Integration
--------------------

MassGen integrates tools via Model Context Protocol (MCP), enabling access to web search, weather, file operations, and many other external services.

**Example:**

.. code-block:: yaml

   backend:
     type: "gemini"
     model: "gemini-2.5-flash"
     mcp_servers:
       - name: "search"
         type: "stdio"
         command: "npx"
         args: ["-y", "@modelcontextprotocol/server-brave-search"]

.. seealso::
   :doc:`mcp_integration` - Complete MCP guide including common servers, tool filtering, planning mode, and security considerations

Project Integration
-------------------

Work directly with your existing codebase using context paths with granular read/write permissions.

**Example:**

.. code-block:: yaml

   orchestrator:
     context_paths:
       - path: "/Users/me/project/src"
         permission: "read"       # Agents analyze code
       - path: "/Users/me/project/docs"
         permission: "write"      # Final agent updates docs

All MassGen state organized under ``.massgen/`` directory in your project root.

.. seealso::
   :doc:`project_integration` - Complete project integration guide including permission levels, safety features, and .massgen directory organization

Interactive Multi-Turn Mode
----------------------------

Start MassGen without a question for interactive chat with context preservation across turns.

.. code-block:: bash

   # Single agent interactive
   uv run python -m massgen.cli --model gemini-2.5-flash

   # Multi-agent interactive
   uv run python -m massgen.cli --config my_agents.yaml

Key features: context preservation, session management, multi-agent collaboration on each turn, and real-time coordination visualization.

.. seealso::
   :doc:`multi_turn_mode` - Complete interactive mode guide including commands, session management, and debugging

External Framework Integration
-------------------------------

AG2 Integration
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Integrate AG2 agents with code execution:

.. code-block:: yaml

   agents:
     - id: "ag2_coder"
       backend:
         type: ag2
         agent_config:
           type: assistant
           llm_config:
             api_type: "openai"
             model: "gpt-4o"
           code_execution_config:
             executor:
               type: "LocalCommandLineCodeExecutor"

AG2 agents participate in MassGen's coordination system alongside native agents.

See :doc:`ag2_integration` for details.

File Operation Safety
---------------------

Read-Before-Delete Enforcement
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

MassGen prevents accidental file deletion:

* Agents must read a file before deleting it
* Exception: Agent-created files can be deleted
* Clear error messages when operations blocked

Directory Validation
~~~~~~~~~~~~~~~~~~~~

* All paths validated at startup
* Context paths must be directories, not files
* Absolute paths required

Permissions
~~~~~~~~~~~

* **During coordination**: All context paths are READ-ONLY
* **Final presentation**: Winning agent gets configured permission (read/write)

See :doc:`file_operations` for safety features.

System Architecture
-------------------

Execution Flow
~~~~~~~~~~~~~~

1. **Load Configuration**

   Parse YAML, validate paths, initialize agents

2. **Coordination**

   * Agents work in parallel, each seeing recent answers from others
   * Each agent decides: provide new answer or vote for existing answer
   * When agent provides answer, workspace snapshot is captured
   * Other agents see snapshots in their temporary workspace
   * Continues until all agents have voted

3. **Winner Selection**

   Agent with most votes is selected as final presenter

4. **Final Presentation**

   * Winning agent delivers the coordinated final answer
   * If using context paths with write permission, winning agent can update project files

5. **Output**

   Results displayed, logged, and workspace snapshots saved

Real-Time Visualization
~~~~~~~~~~~~~~~~~~~~~~~

MassGen provides rich terminal UI showing:

* Agent coordination table
* Voting progress
* Consensus detection
* Streaming responses
* Phase transitions

Disable with ``--no-display`` for simple text output.

Common Patterns
---------------

Research Tasks
~~~~~~~~~~~~~~

.. code-block:: yaml

   agents:
     - id: "gemini"  # Fast web search
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
     - id: "gpt5"   # Deep analysis
       backend:
         type: "openai"
         model: "gpt-5-nano"

Coding Tasks
~~~~~~~~~~~~

.. code-block:: yaml

   agents:
     - id: "coder"  # Code execution
       backend:
         type: "claude_code"
         cwd: "workspace"
     - id: "reviewer"  # Code review
       backend:
         type: "gemini"

Hybrid Teams
~~~~~~~~~~~~

.. code-block:: yaml

   agents:
     - id: "ag2_executor"  # Code execution
       backend:
         type: ag2
         # ... AG2 config
     - id: "claude_analyst"  # File operations
       backend:
         type: "claude_code"
         # ... MCP config
     - id: "gemini_researcher"  # Web search
       backend:
         type: "gemini"

Best Practices
--------------

1. **Start Simple** - Begin with 2-3 agents, add more as needed
2. **Diverse Models** - Mix different providers for varied perspectives
3. **Clear Roles** - Give each agent specific system messages
4. **Use MCP** - Leverage tools for enhanced capabilities
5. **Enable Planning Mode** - For tasks with irreversible actions
6. **Context Paths** - Work with existing projects safely
7. **Interactive Mode** - For iterative development

Next Steps
----------

* :doc:`../quickstart/running-massgen` - Practical examples
* :doc:`../reference/yaml_schema` - Complete configuration reference
* :doc:`mcp_integration` - Add tools to agents
* :doc:`multi_turn_mode` - Interactive conversations
* :doc:`project_integration` - Work with your codebase
* :doc:`ag2_integration` - External framework integration
