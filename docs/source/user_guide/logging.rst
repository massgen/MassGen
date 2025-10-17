Logging & Debugging
===================

MassGen provides comprehensive logging to help you understand agent coordination, debug issues, and review decision-making processes.

Logging Directory Structure
----------------------------

All logs are stored in the ``.massgen/massgen_logs/`` directory with timestamped subdirectories:

.. code-block:: text

   .massgen/
   └── massgen_logs/
       └── log_YYYYMMDD_HHMMSS/           # Timestamped log directory
           ├── agent_a/                    # Agent-specific coordination logs
           │   └── YYYYMMDD_HHMMSS_NNNNNN/ # Timestamped coordination steps
           │       ├── answer.txt          # Agent's answer at this step
           │       ├── context.txt         # Context available to agent
           │       └── workspace/          # Agent workspace (if filesystem tools used)
           ├── agent_b/                    # Second agent's logs
           │   └── ...
           ├── agent_outputs/              # Consolidated output files
           │   ├── agent_a.txt             # Complete output from agent_a
           │   ├── agent_b.txt             # Complete output from agent_b
           │   ├── final_presentation_agent_X.txt  # Winning agent's final answer
           │   ├── final_presentation_agent_X_latest.txt  # Symlink to latest
           │   └── system_status.txt       # System status and metadata
           ├── final/                      # Final presentation phase
           │   └── agent_X/                # Winning agent's final work
           │       ├── answer.txt          # Final answer
           │       └── context.txt         # Final context
           ├── coordination_events.json    # Structured coordination events
           ├── coordination_table.txt      # Human-readable coordination table
           ├── vote.json                   # Final vote tallies and consensus data
           ├── massgen.log                 # Complete debug log (or massgen_debug.log in debug mode)
           ├── snapshot_mappings.json      # Workspace snapshot metadata
           └── execution_metadata.yaml     # Query, config, and execution details

.. note::
   When agents use filesystem tools, each coordination step will also contain a ``workspace/`` directory showing the files the agent created or modified during that step.

Log Files Explained
-------------------

Agent Coordination Logs
~~~~~~~~~~~~~~~~~~~~~~~~

**Location**: ``agent_<id>/YYYYMMDD_HHMMSS_NNNNNN/``

Each coordination step gets a timestamped directory containing:

* ``answer.txt`` - The agent's answer/proposal at this step
* ``context.txt`` - What answers/context the agent could see (recent answers from other agents)

**Use cases:**

* Review what each agent proposed during coordination
* Understand how agents' thinking evolved as they saw other agents' work
* Debug why specific decisions were made

Consolidated Agent Outputs
~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Location**: ``agent_outputs/``

Contains merged outputs from all coordination rounds:

* ``agent_<id>.txt`` - Complete output history for each agent
* ``final_presentation_agent_<id>.txt`` - Winning agent's final presentation
* ``final_presentation_agent_<id>_latest.txt`` - Symlink to latest (for automation)
* ``system_status.txt`` - System metadata and status

Final Presentation
~~~~~~~~~~~~~~~~~~

**Location**: ``final/agent_<id>/``

The winning agent's final answer after coordination:

* ``answer.txt`` - Complete final answer
* ``context.txt`` - Final context used for presentation

Coordination Events
~~~~~~~~~~~~~~~~~~~

**Location**: ``coordination_events.json``

Structured JSON log of all coordination events:

.. code-block:: json

   {
     "event_id": "E42",
     "timestamp": "2025-10-08T01:40:29",
     "agent_id": "agent_a",
     "event_type": "vote",
     "data": {
       "vote_for": "agent_b.2",
       "reason": "More comprehensive approach..."
     }
   }

**Event types:**

* ``started_streaming`` - Agent begins thinking
* ``new_answer`` - Agent provides labeled answer
* ``vote`` - Agent votes for an answer
* ``restart`` - Agent requests restart
* ``restart_completed`` - Agent finishes restart
* ``final_answer`` - Winner provides final response

Vote Summary
~~~~~~~~~~~~

**Location**: ``vote.json``

Final vote tallies and consensus information:

.. code-block:: json

   {
     "votes": {
       "agent_a": {
         "voted_for": "agent_b",
         "reason": "More comprehensive analysis"
       },
       "agent_b": {
         "voted_for": "agent_b",
         "reason": "Best captures key insights"
       }
     },
     "winner": "agent_b",
     "consensus_reached": true
   }

**Use cases:**

* Understand final consensus decision
* Review voting patterns across agents
* Analyze decision-making rationale

Main Debug Log
~~~~~~~~~~~~~~

**Location**: ``massgen.log``

Complete debug log with all system operations:

* Backend API calls and responses
* Tool usage and results
* Coordination state transitions
* Error messages and stack traces

Enable with ``--debug`` flag for verbose logging.

Execution Metadata
~~~~~~~~~~~~~~~~~~

**Location**: ``execution_metadata.yaml``

This file captures the complete execution context for reproducibility:

.. code-block:: yaml

   query: "Your original question"
   timestamp: "2025-10-13T14:30:22"
   config_path: "@examples/basic/multi/three_agents_default"
   config:
     agents:
       - id: "agent1"
         backend:
           type: "gemini"
           model: "gemini-2.5-flash"
       # ... full config

**Contents:**

* ``query`` - The user's original query/prompt
* ``timestamp`` - When the execution started
* ``config_path`` - Path or description of config used
* ``config`` - Complete configuration (if available)

**Use cases:**

* Reproduce the exact same run later
* Debug configuration issues
* Share execution details with team members
* Create test cases from real runs

Coordination Table
------------------

The **coordination table** (``coordination_table.txt``) is a human-readable visualization of the entire multi-agent coordination process.

Structure
~~~~~~~~~

.. code-block:: text

   +-------------------------------------------------------------------+
   |   Event  |           Agent 1           |           Agent 2           |
   |----------+-----------------------------+-----------------------------+
   |   USER   | Original user question                                     |
   |==========+=============================+=============================+
   |     E1   |     📋 Context: []          |      ⏳ (waiting)            |
   |          |  💭 Started streaming       |                             |
   |----------+-----------------------------+-----------------------------+
   |     E2   |     🔄 (streaming)          |   ✨ NEW ANSWER: agent2.1   |
   |          |                             |👁️  Preview: Summary...      |
   |----------+-----------------------------+-----------------------------+

**Key sections:**

1. **Header** - Event symbols, status symbols, and terminology
2. **Event log** - Chronological coordination events
3. **Summary** - Final statistics per agent
4. **Totals** - Overall coordination metrics

Event Symbols
~~~~~~~~~~~~~

**Actions:**

* 💭 Started streaming - Agent begins thinking/processing
* ✨ NEW ANSWER - Agent provides a labeled answer
* 🗳️ VOTE - Agent votes for an answer
* 💭 Reason - Reasoning behind the vote
* 👁️ Preview - Content of the answer
* 🔁 RESTART TRIGGERED - Agent requests to restart
* ✅ RESTART COMPLETED - Agent finishes restart
* 🎯 FINAL ANSWER - Winner provides final response
* 🏆 Winner selected - System announces winner

**Status:**

* 💭 (streaming) - Currently thinking/processing
* ⏳ (waiting) - Idle, waiting for turn
* ✅ (answered) - Has provided an answer
* ✅ (voted) - Has cast a vote
* ✅ (completed) - Task completed
* 🎯 (final answer given) - Winner completed final answer

Answer Labels
~~~~~~~~~~~~~

Each answer gets a unique identifier:

**Format**: ``agent{N}.{attempt}``

* ``N`` = Agent number (1, 2, 3...)
* ``attempt`` = New answer number (1, 2, 3...)

**Examples:**

* ``agent1.1`` = Agent 1's first answer
* ``agent2.1`` = Agent 2's first answer
* ``agent1.2`` = Agent 1's second answer (after restart)
* ``agent1.final`` = Agent 1's final answer (if winner)

Coordination Flow
~~~~~~~~~~~~~~~~~

The table shows how agents coordinate:

1. **Agents see recent answers** - Each agent can view the most recent answers from other agents
2. **Decide next action** - Each agent chooses to either:

   * Provide a new/refined answer
   * Vote for an existing answer they think is best

3. **All agents vote** - Coordination continues until all agents have voted
4. **Final presentation** - The agent with the most votes delivers the final answer

**Example interpretation:**

.. code-block:: text

   E7: Agent 1 provides answer agent1.1
   E13: Agent 1 votes for agent1.1 (self-vote)
   E19: Agent 2 votes for agent1.1 (consensus!)
   E39: Agent 1 selected as winner
   E39: Agent 1 provides final answer

**What agents see:**

During coordination, agents see snapshots of each other's work through workspace snapshots and answer context. This allows agents to build on insights, catch errors, and converge on the best solution.

Summary Statistics
~~~~~~~~~~~~~~~~~~

At the bottom of the coordination table:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Metric
     - Description
   * - **Answers**
     - Number of distinct answers provided
   * - **Votes**
     - Number of votes cast
   * - **Restarts**
     - Number of times agent restarted (cleared memory)
   * - **Status**
     - Final completion status

Accessing Logs
--------------

During Execution
~~~~~~~~~~~~~~~~

**Press 'r' key** during execution to view real-time coordination table in your terminal.

After Execution
~~~~~~~~~~~~~~~

**Find latest log directory:**

.. code-block:: bash

   ls -t .massgen/massgen_logs/ | head -1

**View coordination table:**

.. code-block:: bash

   cat .massgen/massgen_logs/log_20251008_013641/coordination_table.txt

**View specific agent output:**

.. code-block:: bash

   cat .massgen/massgen_logs/log_20251008_013641/agent_outputs/agent_a.txt

**View final answer:**

.. code-block:: bash

   cat .massgen/massgen_logs/log_20251008_013641/agent_outputs/final_presentation_*_latest.txt

Debug Mode
----------

Enable detailed logging with the ``--debug`` flag:

.. code-block:: bash

   uv run python -m massgen.cli \
     --debug \
     --config your_config.yaml \
     "Your question"

**What debug mode logs:**

* ✅ Full API request/response bodies
* ✅ Tool call arguments and results
* ✅ Coordination state transitions
* ✅ File operation details
* ✅ MCP server communication
* ✅ Error stack traces

**Debug log location**: ``.massgen/massgen_logs/log_YYYYMMDD_HHMMSS/massgen_debug.log``

Common Debugging Scenarios
---------------------------

Agent Not Converging
~~~~~~~~~~~~~~~~~~~~

**Check**: ``coordination_table.txt``

Look for:

* Agents changing votes frequently
* New answers in every round
* No clear vote majority

**Solution**: Review agent answers to understand disagreement points.

Agent Errors
~~~~~~~~~~~~

**Check**: ``massgen.log`` for error messages

**Search for**:

.. code-block:: bash

   grep -i "error" .massgen/massgen_logs/log_*/massgen.log
   grep -i "exception" .massgen/massgen_logs/log_*/massgen.log

Tool Failures
~~~~~~~~~~~~~

**Check**: ``agent_outputs/agent_<id>.txt``

Look for tool call failures and error messages.

**Also check**: ``massgen.log`` for detailed tool execution logs

Understanding Agent Decisions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Review coordination rounds:**

1. Open ``coordination_table.txt``
2. Find the round where decision changed
3. Check ``agent_<id>/YYYYMMDD_HHMMSS_NNNNNN/context.txt`` to see what the agent could see
4. Check ``agent_<id>/YYYYMMDD_HHMMSS_NNNNNN/answer.txt`` for the agent's reasoning

Performance Analysis
~~~~~~~~~~~~~~~~~~~~

**Check summary statistics** in ``coordination_table.txt``:

* High restart count = Agents changing approach frequently
* Low vote count = Quick consensus
* Many answers = Iterative refinement

Log Retention
-------------

Logs are stored indefinitely by default.

**Clean old logs manually:**

.. code-block:: bash

   # Remove logs older than 7 days
   find .massgen/massgen_logs/ -type d -name "log_*" -mtime +7 -exec rm -rf {} +

**Disk space check:**

.. code-block:: bash

   du -sh .massgen/massgen_logs/

Best Practices
--------------

1. **Review coordination table first** - Best overview of what happened
2. **Use debug mode for troubleshooting** - Full details when needed
3. **Archive important logs** - Move successful runs to separate directory
4. **Check final presentation** - Verify winning agent's work quality
5. **Monitor log size** - Clean old logs periodically

Integration with CI/CD
----------------------

**Automated log parsing:**

.. code-block:: python

   import json

   # Parse coordination events
   with open(".massgen/massgen_logs/log_latest/coordination_events.json") as f:
       events = json.load(f)

   # Extract final answer
   with open(".massgen/massgen_logs/log_latest/agent_outputs/final_presentation_*_latest.txt") as f:
       final_answer = f.read()

**Exit status:**

MassGen exits with status 0 on success, non-zero on failure.

.. code-block:: bash

   uv run python -m massgen.cli --config config.yaml "Question" && echo "Success"

See Also
--------

* :doc:`multi_turn_mode` - Session logging for interactive mode
* :doc:`file_operations` - Workspace and file operation logs
* :doc:`../reference/cli` - CLI options for logging control
