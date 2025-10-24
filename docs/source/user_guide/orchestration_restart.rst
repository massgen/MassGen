Orchestration Restart
=====================

.. contents:: Table of Contents
   :local:
   :depth: 2

Overview
--------

The orchestration restart feature allows the final agent to recognize when the current coordinated answers are insufficient and request a restart of the entire orchestration process with detailed instructions for improvement.

This is particularly useful for:

- Multi-step tasks where early attempts miss key steps
- Complex problems requiring iterative refinement
- Scenarios where irreversible actions must be performed correctly

How It Works
------------

After MassGen completes the voting phase and selects a final agent, instead of immediately presenting the final answer, the system:

1. **Decision Phase**: Asks the final agent to review all answers
2. **Submit or Restart**: The agent chooses to either:

   - Call ``submit`` → Confirms the task is complete, proceeds with final presentation
   - Call ``restart_orchestration`` → Requests a restart with specific instructions

3. **Restart Execution**: If restart is chosen:

   - All agent states are reset
   - Instructions are injected into agent prompts
   - Coordination runs again with improved guidance

4. **Limits**: Maximum restarts are configurable (default: 2) to prevent infinite loops

Final Agent Tools
-----------------

The final agent has access to two special tools:

Submit Tool
~~~~~~~~~~~

Confirms that the coordinated answers are satisfactory:

.. code-block:: json

   {
     "name": "submit",
     "parameters": {
       "confirmed": true
     }
   }

Use this when:

- All answers adequately address the task
- The task is complete
- No further work is needed

Restart Orchestration Tool
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Requests a restart with detailed instructions:

.. code-block:: json

   {
     "name": "restart_orchestration",
     "parameters": {
       "reason": "Agents provided plans but didn't execute actual implementation",
       "instructions": "Please actually implement the solution by modifying the files, not just describing what changes should be made"
     }
   }

Use this when:

- Current answers are incomplete or incorrect
- A different approach is needed
- Key steps were missed
- More specific guidance would help agents

Evaluation Process
------------------

After the winning agent presents their final answer, they evaluate the result:

1. **Presentation**: Final agent delivers complete answer with full tool access
2. **Evaluation**: Agent reviews the actual output quality
3. **Decision**: Agent chooses to submit (complete) or restart with improvements

This approach ensures agents evaluate actual execution, not just plans.

Configuration
-------------

Basic Configuration
~~~~~~~~~~~~~~~~~~~

Set the maximum number of restarts in your configuration:

.. code-block:: yaml

   # config.yaml
   orchestrator:
     coordination:
       max_orchestration_restarts: 2  # Default: 0 (allows 3 total attempts: initial + 2 restarts)

Programmatic Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from massgen.agent_config import CoordinationConfig, AgentConfig

   coordination_config = CoordinationConfig(
       max_orchestration_restarts=2  # Allow up to 2 restarts (3 total attempts)
   )

   config = AgentConfig(
       coordination_config=coordination_config
   )

Setting Restart Limits
~~~~~~~~~~~~~~~~~~~~~~

Consider these factors when choosing ``max_orchestration_restarts``:

- **Token Budget**: Each restart = full coordination run
- **Time Budget**: Each attempt gets full timeout
- **Task Complexity**: Complex tasks may benefit from more attempts
- **Cost**: More restarts = higher API costs

Recommended values:

- Simple tasks: ``max_orchestration_restarts: 1``
- Standard tasks: ``max_orchestration_restarts: 2`` (default)
- Complex tasks: ``max_orchestration_restarts: 3``

Use Cases
---------

Example 1: Description to Implementation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Scenario**: Agents describe changes without executing them.

**First Attempt**:

.. code-block:: text

   Agent 1: "I would modify app.py to add the login function..."
   Agent 2: "I would create a database migration to add the users table..."

**Final Agent Decision**:

.. code-block:: python

   restart_orchestration(
       reason="Agents only planned but didn't execute implementation",
       instructions="Please actually implement the changes by modifying the files and running necessary commands. Make real changes, not just descriptions."
   )

**Second Attempt**:

.. code-block:: text

   Agent 1: *Actually modifies app.py*
   Agent 2: *Creates and runs database migration*
   Result: Task completed successfully!

Example 2: Multi-Step Task
~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Scenario**: Clone repository and solve an issue.

**First Attempt**:

.. code-block:: text

   Agents solve the issue but forget to clone the repo first

**Final Agent Decision**:

.. code-block:: python

   restart_orchestration(
       reason="Agents attempted to solve issue without cloning repository first",
       instructions="Step 1: Clone the repository. Step 2: Analyze the issue. Step 3: Implement the fix. Please follow these steps in order."
   )

**Second Attempt**:

.. code-block:: text

   Agents follow the steps correctly
   Repository is cloned, issue is analyzed and fixed
   Result: Success!

Example 3: Incomplete Solution
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Scenario**: Web application deployment task.

**First Attempt**:

.. code-block:: text

   Agents set up the server but don't configure the database

**Final Agent Decision**:

.. code-block:: python

   restart_orchestration(
       reason="Server setup complete but database configuration missing",
       instructions="In addition to server setup, please configure the PostgreSQL database, run migrations, and verify the application connects successfully."
   )

**Second Attempt**:

.. code-block:: text

   Complete setup including database
   Result: Fully functional deployment!

Logs and Visibility
-------------------

Evaluation Logs
~~~~~~~~~~~~~~~

.. code-block:: text

   [2025-01-18 17:09:44] Final agent selected: agent_1
   [2025-01-18 17:09:45] 🎤 [agent_1] presenting final answer
   [2025-01-18 17:10:15] 🔍 Evaluating final answer
   [2025-01-18 17:10:20] 🔄 Restart requested by agent_1
      Reason: Final answer describes changes but doesn't execute them
      Instructions: Actually modify the files instead of describing changes
   [2025-01-18 17:10:20] 🔄 Handling orchestration restart (attempt 1 -> 2)

Search logs for ``"restart"`` or ``"RESTART"`` to find restart decisions.

What Happens During Restart
----------------------------

Agent Context
~~~~~~~~~~~~~

When orchestration restarts, each agent receives context about previous attempts:

.. code-block:: text

   ## Previous Orchestration Attempts

   This is attempt 2 to solve the task. The final agent from the previous
   attempt was not satisfied and requested a restart.

   **Why the restart was requested:**
   Agents provided plans but didn't execute actual implementation

   **Instructions for improvement:**
   Please actually implement the solution by modifying the files, not just
   describing what changes should be made

   Please take these insights into account as you work on providing a better answer.

This context ensures agents understand:

- Why previous attempt failed
- What needs improvement
- How to avoid repeating mistakes

State Management
~~~~~~~~~~~~~~~~

During restart:

**Reset**:

- Agent answers
- Agent votes
- Coordination messages
- Selected agent

**Preserved**:

- Timeout flags (agents that timed out stay timed out)
- Session information
- Conversation history

User Visibility
~~~~~~~~~~~~~~~

Users see restart messages in the output:

.. code-block:: text

   🔄 Orchestration restart requested by final agent

   Reason: Agents only planned but didn't execute implementation

   ---

   🔄 Orchestration Restart - Attempt 2/3

   Reason: Agents only planned but didn't execute implementation

   Instructions: Please actually implement the solution...

   ---

   🚀 Starting multi-agent coordination...

Best Practices
--------------

- Set realistic ``max_orchestration_restarts`` based on task complexity (1-3 recommended)
- Provide clear task descriptions to reduce need for restarts
- The final agent should restart when critical steps are missing or implementation wasn't executed
- The final agent should submit when requirements are adequately met

Troubleshooting
---------------

**Max restarts exceeded**: Increase ``max_orchestration_restarts`` or provide more detailed initial instructions

**Agent doesn't restart when it should**: Use a more capable model for final agent or provide explicit success criteria

**Restarts don't improve results**: Provide more specific restart instructions or enable additional tools

See Also
--------

- :doc:`multi_turn_mode` - Multi-turn conversations
- :doc:`concepts` - Core MassGen concepts
