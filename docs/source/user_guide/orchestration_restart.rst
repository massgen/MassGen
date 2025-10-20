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
- Tasks with planning mode where execution needs to follow
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

Evaluation Modes
----------------

MassGen supports two evaluation modes for restart decisions:

Pre-Presentation Evaluation (Default)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The final agent decides **before** presenting the answer:

- Reviews all agent answers and votes
- Decides to submit or restart
- **If submit:** Presents the final answer
- **If restart:** Loops back immediately

**Pros:**
- Faster (skips presentation if restarting)
- Less token usage if restart is needed

**Cons:**
- Evaluates the plan, not the execution
- May miss issues with the actual presentation

Post-Presentation Evaluation (Recommended)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The final agent evaluates **after** completing the presentation:

- Final answer is fully presented first
- Fresh evaluation with completed content
- Reviews actual execution, not just plans
- More realistic quality assessment

**Pros:**
- Evaluates actual output quality
- Fresh context = better decisions
- Sees if execution matched the plan

**Cons:**
- Extra API call per coordination
- Wastes tokens if restart is needed

Configuration
-------------

Basic Configuration
~~~~~~~~~~~~~~~~~~~

Set the maximum number of restarts in your configuration:

.. code-block:: yaml

   # config.yaml
   orchestrator:
     coordination:
       max_orchestration_restarts: 2  # Default: 2 restarts (3 total attempts)
       enable_post_presentation_evaluation: false  # Default: false (pre-evaluation)

Programmatic Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from massgen.agent_config import CoordinationConfig, AgentConfig

   # Pre-presentation evaluation (default, faster)
   coordination_config = CoordinationConfig(
       max_orchestration_restarts=2,
       enable_post_presentation_evaluation=False
   )

   # Post-presentation evaluation (recommended, more accurate)
   coordination_config = CoordinationConfig(
       max_orchestration_restarts=2,
       enable_post_presentation_evaluation=True
   )

   config = AgentConfig(
       coordination_config=coordination_config
   )

Which Mode Should I Use?
~~~~~~~~~~~~~~~~~~~~~~~~~

**Use Post-Presentation Evaluation when:**

- Tasks involve actual execution (file modifications, API calls)
- Quality of final presentation matters
- You want to verify execution matched the plan
- Extra token cost is acceptable

**Use Pre-Presentation Evaluation when:**

- Tasks are primarily analytical/planning
- Speed is critical
- Token budget is limited
- Coordination answers are good indicators of final quality

**Recommendation:** Start with post-presentation evaluation for better restart decisions, switch to pre-presentation if cost/speed becomes an issue.

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

Example 1: Planning to Execution
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Scenario**: Agents use planning mode and describe changes without executing them.

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

Pre-Presentation Evaluation Logs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   [2025-01-18 17:09:44] Final agent selected: agent_1
   [2025-01-18 17:09:45] 🔄 Final agent agent_1 chose to RESTART orchestration
      Reason: Agents only planned without executing
      Instructions: Please actually modify the files
   [2025-01-18 17:09:45] 🔄 Handling orchestration restart (attempt 1 -> 2)

Post-Presentation Evaluation Logs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

   [2025-01-18 17:09:44] Final agent selected: agent_1
   [2025-01-18 17:09:45] 🎤 [agent_1] presenting final answer
   [2025-01-18 17:10:15] 🔍 Starting post-presentation evaluation
   [2025-01-18 17:10:16] 🔍 Post-presentation evaluation by agent_1
   [2025-01-18 17:10:20] 🔄 Post-evaluation: agent_1 requests RESTART
      Reason: Final answer describes changes but doesn't execute them
      Instructions: Actually modify the files instead of describing changes
   [2025-01-18 17:10:20] 🔄 Handling orchestration restart (attempt 1 -> 2)

Search logs for:

- ``"Post-presentation evaluation"`` - Post-eval mode active
- ``"Post-evaluation:"`` - Post-eval decision
- ``"chose to RESTART"`` - Pre-eval decision

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

Limitations and Best Practices
-------------------------------

Limitations
~~~~~~~~~~~

1. **Token Usage**: Each restart multiplies token consumption
2. **Time**: Each attempt adds latency (can be 2-3x with restarts)
3. **Cost**: More API calls = higher costs
4. **Max Limit**: Hard limit prevents infinite loops but may stop before task completion

Best Practices
~~~~~~~~~~~~~~

**For Users**:

- Set realistic ``max_orchestration_restarts`` based on task complexity
- Monitor costs when using expensive models
- Use cheaper models for coordination, expensive models for final presentation
- Combine with planning mode for multi-step tasks

**For System Prompts**:

- Encourage agents to be thorough on first attempt
- Provide clear task descriptions
- Break complex tasks into explicit steps
- Use planning mode when appropriate

**For Final Agent**:

The final agent should restart when:

- Critical steps are missing
- Implementation wasn't executed
- Approach is fundamentally flawed
- Specific guidance would significantly improve results

The final agent should submit when:

- All requirements are met
- Minor improvements wouldn't justify the cost
- Time/token budget is limited
- Task is adequately addressed even if not perfect

Troubleshooting
---------------

Max Restarts Exceeded
~~~~~~~~~~~~~~~~~~~~~

**Symptom**: Error message "Maximum orchestration restarts exceeded"

**Cause**: Reached the ``max_orchestration_restarts`` limit

**Solutions**:

1. Increase the limit in configuration
2. Simplify the task
3. Provide more detailed initial instructions
4. Use planning mode to help agents prepare better

Final Agent Doesn't Restart When It Should
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Symptom**: Task incomplete but final agent submits anyway

**Cause**: Final agent doesn't recognize issues

**Solutions**:

1. Improve final agent's evaluation capabilities
2. Use a more capable model for final agent
3. Provide explicit success criteria in task description
4. Add examples of complete vs incomplete solutions

Restarts Don't Improve Results
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Symptom**: Multiple attempts produce similar inadequate results

**Cause**: Instructions aren't specific enough or agents lack capabilities

**Solutions**:

1. Provide more specific restart instructions
2. Use different/better models for agents
3. Break task into smaller subtasks
4. Enable additional tools for agents (MCP, code execution, etc.)

Cost and Performance
--------------------

Token Usage Estimates
~~~~~~~~~~~~~~~~~~~~~

Approximate token usage with 5 agents:

.. list-table::
   :header-rows: 1
   :widths: 30 20 20 30

   * - Scenario
     - Attempts
     - Tokens
     - Notes
   * - No restart
     - 1
     - ~10K
     - Normal flow
   * - One restart
     - 2
     - ~20K
     - 2x base usage
   * - Two restarts
     - 3
     - ~30K
     - 3x base usage
   * - Context overhead
     - Per attempt
     - +2K
     - Restart instructions

Latency Impact
~~~~~~~~~~~~~~

Each restart adds approximately one full coordination duration:

- Single attempt: 30s (typical)
- With 1 restart: 60s
- With 2 restarts: 90s

Cost Optimization Tips
~~~~~~~~~~~~~~~~~~~~~~

1. **Use cheaper models for coordination**: e.g., GPT-4o-mini, Gemini 2.5 Flash
2. **Reserve expensive models for final agent**: e.g., o1, Claude 3.5 Sonnet
3. **Lower restart limits**: Set ``max_orchestration_restarts: 1`` for cost-sensitive scenarios
4. **Better initial prompts**: Reduce need for restarts with clear instructions
5. **Monitoring**: Track restart frequency to identify problematic tasks

See Also
--------

- :doc:`advanced_usage` - Advanced MassGen features
- :doc:`planning_mode` - Using planning mode for complex tasks
- :doc:`multi_turn_mode` - Multi-turn conversations
- :doc:`concepts` - Core MassGen concepts
