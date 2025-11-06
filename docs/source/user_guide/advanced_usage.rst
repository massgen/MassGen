:orphan:

Advanced Features
=================

This guide covers advanced MassGen features for power users, including multi-turn sessions, planning mode, workspace management, context paths, and AG2 framework integration.

.. note::

   All features are configured through YAML and CLI flags, not Python code.

Multi-Turn Sessions
-------------------

MassGen supports interactive multi-turn conversations with persistent context across turns. Sessions are automatically saved with conversation history.

**Quick Start:**

.. code-block:: bash

   # Start interactive session (omit the question)
   massgen \
     --config @examples/basic/multi/three_agents_default.yaml

.. seealso::
   :doc:`multi_turn_mode` - Complete interactive mode guide including commands (/clear, /quit), session storage, coordination tracking, and debugging

MCP Planning Mode
-----------------

Planning mode (v0.0.29) prevents MCP tools from executing during coordination, making multi-agent collaboration safer for operations with side effects.

**How It Works:**

* Agents **plan** tool usage without execution during coordination
* Only the winning agent **executes** MCP tools
* Prevents irreversible actions and conflicting operations

**Quick Example:**

.. code-block:: yaml

   orchestrator:
     coordination:
       enable_planning_mode: true   # Only winning agent executes MCP tools

.. seealso::
   :doc:`mcp_integration` - Complete MCP planning mode guide including configuration, supported backends, and safety considerations

**Demo:**

See the `MCP Planning Mode demo video <https://youtu.be/jLrMMEIr118>`_ for planning mode in action.

Workspace Management
--------------------

MassGen provides sophisticated workspace management for agents working with files, including isolated workspaces, snapshots, and automatic organization under the ``.massgen/`` directory.

.. seealso::
   :doc:`file_operations` - Complete workspace management guide including workspace isolation, snapshots, temporary workspaces, and .massgen directory structure

Context Paths & Project Integration
------------------------------------

Context paths allow agents to access your existing projects with granular permissions.

Basic Context Paths
~~~~~~~~~~~~~~~~~~~

Share specific directories with all agents:

.. code-block:: yaml

   agents:
     - id: "code_reviewer"
       backend:
         type: "claude_code"
         model: "claude-sonnet-4"
         cwd: "workspace"             # Agent's isolated work area

   orchestrator:
     context_paths:
       - path: "/absolute/path/to/project/src"
         permission: "read"           # Agents can analyze code
       - path: "/absolute/path/to/project/docs"
         permission: "write"          # Agents can update docs

**Important:**

* Context paths must be **absolute paths**
* Context paths must point to **directories**, not files
* Paths are validated during startup

Permission Levels
~~~~~~~~~~~~~~~~~

**read permission:**

* Agents can read files in the directory
* No modifications allowed
* Safe for code analysis, documentation review

**write permission:**

* Agents can read and modify files
* Can create, edit, and delete files
* Use with caution

Safety Features
~~~~~~~~~~~~~~~

**During Coordination:**

* All agents have **read-only** access to context paths
* Prevents multiple agents from modifying files simultaneously

**Final Agent (Winner):**

* Gets the configured permission (read or write)
* Only one agent modifies files

**File Operation Safety (v0.0.29):**

* Read-before-delete enforcement
* Agents must read a file before deleting it
* Prevents accidental data loss

**Example:**

.. code-block:: bash

   # Multi-agent project collaboration
   massgen \
     --config @examples/tools/filesystem/gpt5mini_cc_fs_context_path.yaml \
     "Analyze the codebase and suggest improvements"

See :doc:`project_integration` for comprehensive project integration guide.

AG2 Framework Integration
--------------------------

MassGen integrates with the AG2 framework for advanced code execution and external agent capabilities.

Basic AG2 Configuration
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   agents:
     - id: "ag2_agent"
       backend:
         type: "ag2"
         agent_type: "ConversableAgent"
         llm_config:
           config_list:
             - model: "gpt-4"
               api_key: "${OPENAI_API_KEY}"

AG2 Code Execution
~~~~~~~~~~~~~~~~~~

Configure code execution environments:

.. code-block:: yaml

   agents:
     - id: "ag2_coder"
       backend:
         type: "ag2"
         agent_type: "ConversableAgent"
         llm_config:
           config_list:
             - model: "gpt-4"
               api_key: "${OPENAI_API_KEY}"
         code_execution_config:
           executor: "local"           # or "docker", "jupyter", "yepcode"
           work_dir: "coding"

**Execution Environments:**

* ``local`` - Execute on local machine
* ``docker`` - Execute in Docker container (safe)
* ``jupyter`` - Execute in Jupyter kernel
* ``yepcode`` - Execute in YepCode environment

Hybrid Configurations
~~~~~~~~~~~~~~~~~~~~~

Combine MassGen and AG2 agents:

.. code-block:: yaml

   agents:
     # Native MassGen agent
     - id: "gemini_agent"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
         enable_web_search: true

     # AG2 agent with code execution
     - id: "ag2_coder"
       backend:
         type: "ag2"
         agent_type: "ConversableAgent"
         llm_config:
           config_list:
             - model: "gpt-4"
               api_key: "${OPENAI_API_KEY}"
         code_execution_config:
           executor: "docker"
           work_dir: "coding"

**Example:**

.. code-block:: bash

   # Hybrid MassGen + AG2 collaboration
   massgen \
     --config @examples/ag2/ag2_coder_case_study.yaml \
     "Build a data analysis pipeline with visualizations"

See :doc:`ag2_integration` for complete AG2 documentation.

Logging and Debugging
---------------------

MassGen provides comprehensive logging capabilities for debugging and monitoring multi-agent workflows (v0.0.13-v0.0.14).

Logging System
~~~~~~~~~~~~~~

**Unified Logging Infrastructure:**

* Centralized logger with colored console output
* File logging with automatic organization
* Consistent format across all backends
* Color-coded log levels for better visibility

**Log Levels:**

* **DEBUG** (cyan): Verbose information for troubleshooting
* **INFO** (green): General operational messages
* **WARNING** (yellow): Important notices
* **ERROR** (red): Error conditions

Debug Mode
~~~~~~~~~~

Enable verbose debugging with the ``--debug`` flag:

.. code-block:: bash

   # Enable debug mode
   massgen \
     --config @examples/basic/multi/three_agents_default.yaml \
     --debug \
     "Your question"

**Debug Output Includes:**

* Detailed orchestrator activities
* Agent messages and coordination events
* Backend operations and API calls
* Tool calls and responses
* MCP server interactions
* File operations and permissions
* Voting and consensus tracking

Log File Structure
~~~~~~~~~~~~~~~~~~

Logs are organized in a structured directory:

.. code-block:: text

   massgen_logs/
   └── log_{timestamp}/
       ├── agent_outputs/
       │   ├── agent_id.txt                    # Raw output from each agent
       │   ├── final_presentation_agent_id.txt # Final presentation
       │   └── system_status.txt               # System status information
       ├── agent_id/
       │   └── {answer_generation_timestamp}/
       │       └── files_included_in_generated_answer
       ├── final_workspace/
       │   └── agent_id/
       │       └── {answer_generation_timestamp}/
       │           └── files_included_in_generated_answer
       └── massgen.log / massgen_debug.log     # Main log file

**Log Files:**

* ``massgen.log``: General logging (INFO level)
* ``massgen_debug.log``: Verbose debugging (DEBUG level, when --debug is used)

Reading Logs
~~~~~~~~~~~~

**Find Your Logs:**

.. code-block:: bash

   # Logs are in massgen_logs/ directory
   ls -lt massgen_logs/          # List recent log directories

   # View debug log
   cat massgen_logs/log_*/massgen_debug.log

   # View agent output
   cat massgen_logs/log_*/agent_outputs/agent_id.txt

**What to Look For:**

* **Orchestrator Activities**: Coordination rounds, voting results, consensus detection
* **Agent Messages**: What each agent is thinking and proposing
* **Backend Operations**: API calls, response times, token usage
* **Tool Calls**: Which tools were called and their results
* **Errors**: Stack traces and error messages

Common Debug Scenarios
~~~~~~~~~~~~~~~~~~~~~~

**Problem: Agents not collaborating:**

.. code-block:: bash

   # Check debug log for coordination events
   grep "coordination" massgen_logs/log_*/massgen_debug.log

   # Check voting results
   grep "vote" massgen_logs/log_*/massgen_debug.log

**Problem: MCP tools not working:**

.. code-block:: bash

   # Check MCP server initialization
   grep "MCP" massgen_logs/log_*/massgen_debug.log

   # Check tool calls
   grep "tool_call" massgen_logs/log_*/massgen_debug.log

**Problem: File operations failing:**

.. code-block:: bash

   # Check file operations
   grep "file" massgen_logs/log_*/massgen_debug.log

   # Check permissions
   grep "permission" massgen_logs/log_*/massgen_debug.log

Coordination Tracking
---------------------

MassGen includes a comprehensive coordination tracking system for visualizing multi-agent interactions (v0.0.19).

Coordination Table
~~~~~~~~~~~~~~~~~~

Press ``r`` during execution to view the interactive coordination table:

.. code-block:: bash

   # Start MassGen
   massgen \
     --config @examples/basic/multi/three_agents_default.yaml

   # During execution, press 'r' to view coordination table

**Coordination Table Shows:**

* Agent status across all rounds
* Answers provided by each agent
* Votes cast by each agent
* Coordination events (NEW_ANSWER, VOTE, ERROR, TIMEOUT)
* Timestamps for all events
* Consensus detection

Agent Status Tracking
~~~~~~~~~~~~~~~~~~~~~

**Agent Status Types:**

* **STREAMING**: Agent is currently generating response
* **VOTED**: Agent has cast a vote
* **ANSWERED**: Agent has provided an answer
* **RESTARTING**: Agent is restarting based on new information
* **ERROR**: Agent encountered an error
* **TIMEOUT**: Agent exceeded time limit
* **COMPLETED**: Agent finished its task

**Action Types:**

* **NEW_ANSWER**: Agent provided a new answer
* **VOTE**: Agent voted for another agent's answer
* **VOTE_IGNORED**: Vote was not counted (late arrival, etc.)
* **ERROR**: Agent operation failed
* **TIMEOUT**: Agent operation timed out
* **CANCELLED**: Agent operation was cancelled

Understanding the Coordination Table
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Table Format:**

.. code-block:: text

   Round 1:
   ┌────────────┬────────────┬────────────┬────────────┐
   │ Agent      │ Status     │ Action     │ Timestamp  │
   ├────────────┼────────────┼────────────┼────────────┤
   │ agent1     │ ANSWERED   │ NEW_ANSWER │ 14:30:22   │
   │ agent2     │ VOTED      │ VOTE       │ 14:30:45   │
   │ agent3     │ ANSWERED   │ NEW_ANSWER │ 14:30:50   │
   └────────────┴────────────┴────────────┴────────────┘

**Reading the Table:**

1. **Round Number**: Shows which coordination round
2. **Agent Column**: Agent ID
3. **Status**: Current agent state (see Agent Status Types)
4. **Action**: What action the agent took
5. **Timestamp**: When the action occurred

**Coordination Events:**

* **Answer Generation**: Agent creates a new answer (NEW_ANSWER)
* **Voting**: Agent votes for another agent's answer (VOTE)
* **Coordination**: Multiple agents refine based on others' work
* **Consensus**: System detects when agents agree (multiple votes for same answer)

Using Coordination Data for Debugging
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Identify Stuck Agents:**

.. code-block:: text

   # Look for agents with TIMEOUT or ERROR status
   Round 3:
   agent1    COMPLETED    VOTE         14:35:10
   agent2    TIMEOUT      TIMEOUT      14:35:45  ← Agent stuck
   agent3    COMPLETED    VOTE         14:35:12

**Track Voting Patterns:**

.. code-block:: text

   # See which agents are influencing the group
   Round 2:
   agent1    ANSWERED     NEW_ANSWER   14:32:10
   agent2    VOTED        VOTE         14:32:30  ← Voted for agent1
   agent3    VOTED        VOTE         14:32:35  ← Voted for agent1
   # Consensus: agent1's answer is winning

**Detect Collaboration Issues:**

.. code-block:: text

   # All agents providing answers, no votes = poor collaboration
   Round 3:
   agent1    ANSWERED     NEW_ANSWER   14:33:00
   agent2    ANSWERED     NEW_ANSWER   14:33:05
   agent3    ANSWERED     NEW_ANSWER   14:33:10
   # Problem: No agent is voting for others' answers

Coordination Tracker API
~~~~~~~~~~~~~~~~~~~~~~~~~

The coordination tracker captures all events programmatically:

**Events Tracked:**

* Answer submissions with timestamps
* Vote submissions with target agent
* Agent status transitions
* Phase changes (coordination → final presentation)
* Error conditions
* Timeout events

**Use Cases:**

* Post-execution analysis
* Performance optimization
* Understanding agent behavior
* Debugging coordination issues
* Generating coordination reports

Advanced CLI Options
--------------------

Complete CLI reference:

.. code-block:: bash

   massgen \
     --config path/to/config.yaml \  # Configuration file
     --model model-name \            # Quick model setup (alternative to --config)
     --backend backend-type \        # Backend type for quick setup
     --system-message "prompt" \     # Custom system message
     --no-display \                  # Disable real-time UI
     --no-logs \                     # Disable logging
     --debug \                       # Enable debug mode
     "Your question"                 # Optional - omit for interactive mode

See :doc:`../reference/cli` for complete CLI documentation.

Configuration Best Practices
-----------------------------

1. **Incremental Testing**

   * Test single agent before multi-agent
   * Verify tools work individually
   * Add complexity gradually

2. **Workspace Organization**

   * See :doc:`file_operations` for workspace best practices

3. **Permission Management**

   * Start with read-only context paths
   * Test in isolated directories first
   * Use write permissions sparingly

4. **MCP Safety**

   * Enable planning mode for file operations
   * Use tool filtering (allowed_tools, exclude_tools)
   * Test MCP servers independently

5. **Multi-Turn Sessions**

   * Use clear conversation boundaries
   * Review session summaries
   * Clean up old sessions periodically

6. **Debugging**

   * Use ``--debug`` for troubleshooting
   * Check logs in ``agent_outputs/log_{time}/``
   * Verify configuration with simple tests first

Advanced Examples
-----------------

Complex Multi-Agent System
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   agents:
     # Research agent with web search
     - id: "researcher"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
         enable_web_search: true
       system_message: "Research specialist with web search capabilities"

     # Analysis agent with reasoning
     - id: "analyst"
       backend:
         type: "openai"
         model: "gpt-5"
         reasoning:
           effort: "high"
       system_message: "Deep analysis with advanced reasoning"

     # Development agent with file operations
     - id: "developer"
       backend:
         type: "claude_code"
         model: "claude-sonnet-4"
         cwd: "workspace"
       system_message: "Development specialist with file operations"

     # Testing agent with AG2 code execution
     - id: "tester"
       backend:
         type: "ag2"
         agent_type: "ConversableAgent"
         llm_config:
           config_list:
             - model: "gpt-4"
               api_key: "${OPENAI_API_KEY}"
         code_execution_config:
           executor: "docker"
           work_dir: "testing"

   orchestrator:
     max_rounds: 5
     voting_config:
       threshold: 0.6
     snapshot_storage: "snapshots"
     agent_temporary_workspace: "temp"
     coordination:
       enable_planning_mode: true
     context_paths:
       - path: "/path/to/project/src"
         permission: "read"
       - path: "/path/to/project/tests"
         permission: "write"

Performance Optimization
------------------------

Parallel Execution
~~~~~~~~~~~~~~~~~~

MassGen executes agents in parallel by default. No special configuration needed.

Resource Management
~~~~~~~~~~~~~~~~~~~

Control agent resources:

.. code-block:: yaml

   backend:
     type: "openai"
     model: "gpt-5-nano"
     max_tokens: 4096              # Limit response length
     timeout: 60                   # Request timeout

   orchestrator:
     max_rounds: 5                 # Limit coordination rounds

Cost Optimization
~~~~~~~~~~~~~~~~~

Strategies to reduce costs:

* Use **GPT-5-nano** instead of GPT-5
* Use **Gemini 2.5 Flash** for research (very cost-effective)
* Use **Grok-3-mini** instead of Grok-3
* Use **LM Studio** for local, free inference
* Limit ``max_rounds`` in orchestrator
* Reduce ``max_tokens`` for concise responses

Next Steps
----------

* :doc:`multi_turn_mode` - Interactive sessions and conversation management
* :doc:`file_operations` - Workspace management and file operations
* :doc:`project_integration` - Secure project access with context paths
* :doc:`ag2_integration` - AG2 framework integration
* :doc:`mcp_integration` - MCP planning mode and tool filtering
* :doc:`../examples/advanced_patterns` - Advanced configuration patterns
* :doc:`../reference/yaml_schema` - Complete YAML reference

Troubleshooting
---------------

**Workspace permissions error:**

See :doc:`file_operations` for workspace setup and troubleshooting.

**Context path not found:**

Verify paths are absolute and exist:

.. code-block:: yaml

   context_paths:
     - path: "/absolute/path/to/dir"  # ✅ Absolute
       permission: "read"

   # Not this:
     - path: "relative/path"           # ❌ Must be absolute
       permission: "read"

**Planning mode not working:**

Ensure backend supports planning mode:

.. code-block:: yaml

   # Supported backends for planning mode
   backend:
     type: "openai"      # ✅
     type: "claude"      # ✅
     type: "gemini"      # ✅

   # Not supported
   backend:
     type: "grok"        # ❌ Planning mode not available
