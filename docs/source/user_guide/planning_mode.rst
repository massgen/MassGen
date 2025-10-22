:orphan:

Planning Mode
=============

Planning Mode enables agents to coordinate and plan their approaches **without executing irreversible actions**. Only the winning agent executes the final plan during presentation, preventing conflicts and unintended side effects during multi-agent coordination.

.. note::

   **New in v0.0.29**: Planning mode is especially powerful for MCP tool usage, preventing agents from executing external API calls, file operations, or database modifications during coordination.

Quick Start
-----------

**Five agents planning with filesystem tools:**

.. code-block:: bash

   massgen \
     --config @examples/tools/planning/five_agents_filesystem_mcp_planning_mode.yaml \
     "Create a comprehensive project structure with documentation"

**Example with MCP tools:**

.. code-block:: bash

   massgen \
     --config @examples/tools/mcp/five_agents_weather_mcp_test.yaml \
     "Compare weather forecasts for New York, London, and Tokyo"

What is Planning Mode?
-----------------------

Planning mode separates multi-agent coordination into two distinct phases:

1. **Coordination Phase** - Agents discuss, analyze, and vote on approaches **without executing actions**
2. **Presentation Phase** - Only the winning agent executes the agreed-upon plan

Without Planning Mode
~~~~~~~~~~~~~~~~~~~~~~

**Standard coordination** allows all agents to execute actions immediately:

.. code-block:: text

   ❌ Agent A creates file "output.txt" with content X
   ❌ Agent B creates file "output.txt" with content Y (overwrites!)
   ❌ Agent C creates file "output.txt" with content Z (overwrites again!)
   → Result: Chaos, lost work, conflicting changes

With Planning Mode
~~~~~~~~~~~~~~~~~~

**Planning mode** prevents execution during coordination:

.. code-block:: text

   ✅ Agent A: "I would create output.txt with content X because..."
   ✅ Agent B: "I would create output.txt with content Y because..."
   ✅ Agent C: "I agree with Agent B's approach" [votes for B]
   ✅ Agent A: "Agent B's approach is better" [votes for B]
   → Winner: Agent B
   → Agent B executes: Creates output.txt with content Y (no conflicts!)

When to Use Planning Mode
--------------------------

Use planning mode for tasks involving irreversible or conflicting operations:

File System Operations
~~~~~~~~~~~~~~~~~~~~~~

* ✅ File creation, modification, deletion
* ✅ Directory structure changes
* ✅ Batch file operations

.. code-block:: yaml

   orchestrator:
     coordination:
       enable_planning_mode: true

**Why**: Prevents multiple agents from creating/deleting the same files during coordination.

MCP External Tools
~~~~~~~~~~~~~~~~~~

* ✅ API calls (weather, search, notifications)
* ✅ Database operations
* ✅ External service integrations (Twitter, Discord, Notion)

.. code-block:: bash

   # Weather API example with planning mode
   massgen \
     --config @examples/tools/mcp/five_agents_weather_mcp_test.yaml \
     "Get weather data for multiple cities"

**Why**: Prevents redundant API calls, rate limiting issues, and conflicting external state changes.

State-Changing Operations
~~~~~~~~~~~~~~~~~~~~~~~~~

* ✅ Database writes
* ✅ Sending messages/emails
* ✅ Creating issues/tickets
* ✅ Publishing content

**Why**: These operations can't be easily undone or rolled back.

When NOT to Use Planning Mode
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Planning mode adds coordination overhead. Skip it for:

* ❌ Pure analysis tasks (no side effects)
* ❌ Read-only operations
* ❌ Single-agent tasks
* ❌ Tasks where parallel execution is beneficial

Configuration
-------------

Basic Configuration
~~~~~~~~~~~~~~~~~~~

Enable planning mode in the ``orchestrator`` section:

.. code-block:: yaml

   orchestrator:
     coordination:
       enable_planning_mode: true

Agents will automatically plan without executing during coordination.

Custom Planning Instructions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Customize the planning behavior with instructions:

.. code-block:: yaml

   orchestrator:
     coordination:
       enable_planning_mode: true
       planning_mode_instruction: |
         PLANNING MODE ACTIVE: You are in the coordination phase.

         During this phase:
         1. Describe your intended approach and reasoning
         2. Analyze other agents' proposals
         3. Use 'vote' or 'new_answer' tools for coordination
         4. DO NOT execute filesystem operations, API calls, or state changes
         5. Save all execution for the final presentation phase

         Focus on planning, analysis, and coordination rather than execution.

Complete Example
~~~~~~~~~~~~~~~~

Full configuration with planning mode for filesystem operations:

.. code-block:: yaml

   agents:
     - id: "agent_a"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
         cwd: "workspace_a"  # File operations handled via cwd

     - id: "agent_b"
       backend:
         type: "openai"
         model: "gpt-5-nano"
         cwd: "workspace_b"  # File operations handled via cwd

   orchestrator:
     snapshot_storage: "snapshots"
     agent_temporary_workspace: "temp_workspaces"
     coordination:
       enable_planning_mode: true
       planning_mode_instruction: |
         During coordination, describe what you would do without executing.
         Only the winning agent will implement the plan.

   ui:
     display_type: "rich_terminal"
     logging_enabled: true

Orchestration Restart
---------------------

**New in v0.1.1**: Orchestration restart enables automatic quality checks after coordination completes. If the final answer is incomplete or incorrect, the system can automatically restart with specific improvement instructions.

What is Orchestration Restart?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

After the winning agent presents the final answer, an optional post-evaluation phase reviews the answer and decides whether to:

* ✅ **Submit** - Answer is complete and ready for the user
* 🔄 **Restart** - Answer needs improvement with specific guidance

This creates a self-correcting loop that improves answer quality without manual intervention.

Quick Example
~~~~~~~~~~~~~

.. code-block:: yaml

   orchestrator:
     coordination:
       enable_planning_mode: true
       max_orchestration_restarts: 2  # Allow up to 2 restarts (3 total attempts)

**Task**: "Describe two Beatles members: John Lennon and Paul McCartney"

**Attempt 1** - Initial coordination produces incomplete answer:

.. code-block:: text

   Final Answer: "John Lennon was born in 1940 and was a founding member..."

   Post-Evaluation: ❌ "Only described John Lennon, missing Paul McCartney"

   🔄 RESTART with instructions:
   "Provide TWO descriptions (John Lennon AND Paul McCartney).
   Each should include: birth year, role in band, notable songs."

**Attempt 2** - Agents see restart instructions and improve:

.. code-block:: text

   Fresh coordination with guidance...
   Final Answer: [Complete descriptions of both Beatles]

   Post-Evaluation: ✅ Answer approved!

Configuration Options
~~~~~~~~~~~~~~~~~~~~~

**Basic Configuration**:

.. code-block:: yaml

   orchestrator:
     coordination:
       max_orchestration_restarts: 2  # 0 = disabled (default), 1-3 = allow restarts

**With Debug Mode** (for testing):

.. code-block:: yaml

   orchestrator:
     debug_final_answer: "I only created one file."  # Forces bad answer on attempt 1

Post-Evaluation Process
~~~~~~~~~~~~~~~~~~~~~~~~

The post-evaluation phase runs **automatically** after final presentation (except on the final attempt):

1. **Winning agent evaluates its own answer** with a fresh system prompt
2. **Agent has MCP tools access** - can verify files, check workspace, etc.
3. **Agent calls one tool**:

   * ``submit(confirmed=True)`` - Answer is complete
   * ``restart_orchestration(reason, instructions)`` - Needs improvement

4. **If restart requested**: Show yellow banner with reason + instructions
5. **Reset orchestration state** and run coordination again with guidance

Key Features
~~~~~~~~~~~~

**Self-Correcting**
   System catches its own mistakes automatically

**Specific Guidance**
   Each restart includes tailored instructions for improvement

**File Verification**
   Evaluation agent can inspect workspace with MCP tools to verify claims

**Max Restart Limit**
   Configurable safety limit (default: 0, recommended: 1-2)

**Auto-Submit on Timeout**
   If post-evaluation times out, answer is automatically submitted

**Skip Evaluation on Final Attempt**
   Last attempt auto-submits to prevent infinite loops

When to Use Orchestration Restart
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Orchestration restart is beneficial for tasks where:

* ✅ **Multi-part requirements**: "Do X AND Y AND Z" - easy to miss parts
* ✅ **File deliverables**: Verify that claimed files actually exist
* ✅ **Specific format requirements**: Check output matches expected structure
* ✅ **Quality thresholds**: Ensure answer meets certain standards

**Don't use for**:

* ❌ Open-ended creative tasks (no clear right/wrong)
* ❌ Simple single-step tasks
* ❌ Tasks where any reasonable answer is acceptable

Restart Workflow
~~~~~~~~~~~~~~~~

**Complete Flow with 2 Max Restarts**:

.. code-block:: text

   Attempt 1:
   ┌─────────────────────────────────────┐
   │ 🤖 Agents Coordinate                │
   │ 🗳️  Voting & Selection              │
   │ 🎤 Final Presentation (Streaming)   │
   │ 🔍 Post-Evaluation (Streaming)      │  ← Agent reviews answer
   │    → restart_orchestration() called │
   └─────────────────────────────────────┘
              ↓
   ┌─────────────────────────────────────┐
   │ 🔄 RESTART BANNER (Yellow Box)      │
   │ Reason: [Why insufficient]          │
   │ Instructions: [How to improve]      │
   └─────────────────────────────────────┘
              ↓
   Attempt 2:
   ┌─────────────────────────────────────┐
   │ 🚀 Fresh Coordination (with guidance)│
   │ 🤖 Agents See Restart Instructions  │
   │ 🎤 Final Presentation               │
   │ 🔍 Post-Evaluation                  │  ← Reviews again
   │ ✅ Inspection Menu                  │  ← Success!
   └─────────────────────────────────────┘

Restart Context Injection
~~~~~~~~~~~~~~~~~~~~~~~~~~

Restart instructions are injected into agent context **similar to multi-turn context**:

.. code-block:: text

   <PREVIOUS ATTEMPT FEEDBACK>
   The previous orchestration attempt was restarted because:
   [Reason from evaluation]

   **Instructions for this attempt:**
   [Detailed guidance from evaluation]

   Please address these specific issues in your coordination and final answer.
   <END OF PREVIOUS ATTEMPT FEEDBACK>

   <ORIGINAL MESSAGE> [Your task] <END OF ORIGINAL MESSAGE>

   <CURRENT ANSWERS from the agents>
   ...

This ensures all agents understand what went wrong and how to improve.

Complete Example
~~~~~~~~~~~~~~~~

**Config with Planning Mode + Restart**:

.. code-block:: yaml

   agents:
     - id: "agent_a"
       backend:
         type: "claude_code"
         model: "claude-sonnet-4-20250514"
         cwd: "workspace_a"

     - id: "agent_b"
       backend:
         type: "gemini"
         model: "gemini-2.0-flash-exp"
         cwd: "workspace_b"

     - id: "agent_c"
       backend:
         type: "openai"
         model: "gpt-4o"
         cwd: "workspace_c"

   orchestrator:
     snapshot_storage: "snapshots"
     coordination:
       enable_planning_mode: true
       max_orchestration_restarts: 2  # Allow up to 2 restarts

   ui:
     display_type: "rich_terminal"

**Usage**:

.. code-block:: bash

   massgen \
     --config my_config.yaml \
     "Create three Python files: main.py, utils.py, and tests.py"

If the first attempt only creates 2 files, post-evaluation will catch this and restart with instructions to create all 3.

Debug Mode for Testing
~~~~~~~~~~~~~~~~~~~~~~~

Test the restart feature without waiting for real failures:

.. code-block:: yaml

   orchestrator:
     coordination:
       max_orchestration_restarts: 2
     debug_final_answer: "I only created main.py"  # Override on attempt 1 only

This forces a bad answer on the first attempt, triggering post-evaluation and restart. Subsequent attempts use real answers.

Best Practices
~~~~~~~~~~~~~~

1. **Start with 1-2 restarts**: More attempts = longer execution time
2. **Clear task requirements**: Well-defined tasks get better restart guidance
3. **Use with planning mode**: Prevents execution conflicts during restarts
4. **Monitor logs**: Check ``.massgen/massgen_logs/`` to see restart reasons
5. **Test with debug mode**: Validate your restart configuration before production use

How Planning Mode Works
------------------------

Coordination Phase
~~~~~~~~~~~~~~~~~~

During coordination with planning mode enabled:

1. **Agents receive planning instructions** automatically
2. **Agents describe approaches** without execution
3. **Coordination tools remain available**: ``vote`` and ``new_answer``
4. **MCP/filesystem tools are NOT blocked** - agents must follow instructions not to use them
5. **Agents vote** for the best approach

.. note::

   Planning mode relies on agents following instructions. It's not a technical block but a behavioral guideline. Agents with strong instruction-following (Claude, GPT-4, Gemini) respect planning mode well.

Presentation Phase
~~~~~~~~~~~~~~~~~~

After coordination completes:

1. **Winner selected** based on votes
2. **Planning mode disabled** for winner
3. **Winner executes the plan** with full tool access
4. **Results saved** and returned to user

Example Workflow
~~~~~~~~~~~~~~~~

**Task**: "Create a project structure with src/, tests/, and docs/ directories"

**Coordination Phase** (Planning Mode Active):

.. code-block:: text

   Round 1:
   --------
   Agent A: "I would create three directories: src/ for source code,
            tests/ for test files, and docs/ for documentation.
            Then I would add README files to each." [new_answer]

   Agent B: "I would do the same but also add __init__.py files to
            make src/ and tests/ proper Python packages." [new_answer]

   Agent C: "Agent B's approach is more complete." [votes for B]

   Round 2:
   --------
   Agent A: "Good point about __init__.py" [votes for B]
   Agent B: [already provided answer]
   Agent C: [already voted]

   → All agents voted
   → Winner: Agent B (2 votes)

**Presentation Phase** (Planning Mode Disabled):

.. code-block:: text

   Agent B executes:
   - create_directory("src")
   - write_file("src/__init__.py", "")
   - create_directory("tests")
   - write_file("tests/__init__.py", "")
   - create_directory("docs")
   - write_file("docs/README.md", "# Documentation")

   ✅ Complete! Clean execution without conflicts.

Benefits
--------

Conflict Prevention
~~~~~~~~~~~~~~~~~~~

* ✅ No competing file operations
* ✅ No redundant API calls
* ✅ Single, coherent execution path

Quality Through Discussion
~~~~~~~~~~~~~~~~~~~~~~~~~~~

* ✅ Agents refine ideas through coordination
* ✅ Best approach wins through voting
* ✅ Implementation reflects consensus

Resource Efficiency
~~~~~~~~~~~~~~~~~~~

* ✅ Prevents wasted API calls during coordination
* ✅ Single execution reduces costs
* ✅ Avoids rate limiting issues

Auditability
~~~~~~~~~~~~

* ✅ Clear separation between planning and execution
* ✅ Easy to review proposed approach before execution
* ✅ Detailed logs of coordination decisions

Examples by Use Case
--------------------

Example 1: Project Structure Creation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Config**: ``@examples/tools/planning/five_agents_filesystem_mcp_planning_mode.yaml``

.. code-block:: bash

   massgen \
     --config @examples/tools/planning/five_agents_filesystem_mcp_planning_mode.yaml \
     "Create a Python microservice project with src/, tests/, docker/, and docs/ directories. Add starter files."

**Result**: Agents discuss the ideal structure, vote on the best approach, then winning agent creates everything cleanly.

Example 2: Weather Data Collection
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Config**: ``@examples/tools/mcp/five_agents_weather_mcp_test.yaml``

.. code-block:: bash

   massgen \
     --config @examples/tools/mcp/five_agents_weather_mcp_test.yaml \
     "Fetch weather data for San Francisco, New York, and London. Compare temperatures."

**Result**: Agents plan the API calls, agree on data format, then winning agent makes the actual requests.

Example 3: Social Media Integration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Config**: ``@examples/tools/planning/five_agents_twitter_mcp_planning_mode.yaml``

.. code-block:: bash

   massgen \
     --config @examples/tools/planning/five_agents_twitter_mcp_planning_mode.yaml \
     "Analyze recent tweets about AI and post a summary"

**Result**: Agents plan search queries and post content without actually posting during coordination.

Backend Compatibility
---------------------

Planning mode works with all backends that support MCP or filesystem tools:

.. list-table::
   :header-rows: 1
   :widths: 25 25 50

   * - Backend
     - Planning Mode
     - Notes
   * - ``gemini``
     - ✅ Full support
     - Excellent instruction following
   * - ``openai``
     - ✅ Full support
     - GPT-4 and GPT-5 follow instructions well
   * - ``claude``
     - ✅ Full support
     - Strong instruction adherence
   * - ``claude_code``
     - ✅ Full support
     - Built-in tool control
   * - ``grok``
     - ✅ Full support
     - Reliable instruction following
   * - ``lmstudio``
     - ⚠️ Varies
     - Depends on local model quality

Troubleshooting
---------------

Agents Executing During Coordination
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Problem**: Agents are executing actions despite planning mode being enabled.

**Solutions**:

1. **Check your configuration**:

   .. code-block:: yaml

      orchestrator:
        coordination:
          enable_planning_mode: true  # Make sure this is set

2. **Strengthen planning instructions**:

   .. code-block:: yaml

      orchestrator:
        coordination:
          planning_mode_instruction: |
            IMPORTANT: DO NOT execute any operations during coordination.
            You are in PLANNING MODE - describe what you would do.

3. **Use backends with strong instruction following**: Claude, GPT-4/5, Gemini 2.0+

4. **Add explicit instructions to agent system messages**:

   .. code-block:: yaml

      agents:
        - id: "agent_a"
          system_message: |
            During coordination, you must ONLY plan and discuss.
            Do not execute filesystem, API, or state-changing operations.

Coordination Takes Too Long
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Problem**: Agents spend many rounds discussing without converging.

**Solutions**:

1. **Add timeout configuration**:

   .. code-block:: yaml

      timeout_settings:
        orchestrator_timeout_seconds: 600  # 10 minutes

2. **Use fewer agents** for simpler tasks

3. **Provide clearer task descriptions**

4. **Add voting guidance to system messages**

Best Practices
--------------

1. **Enable for irreversible operations**: Always use planning mode for file operations, API calls, or database changes

2. **Custom instructions for complex tasks**: Tailor ``planning_mode_instruction`` to your specific use case

3. **Clear task descriptions**: Help agents understand what needs planning vs immediate action

4. **Monitor coordination rounds**: Check logs to see if planning is effective

5. **Test with smaller agent teams first**: Start with 2-3 agents before scaling to 5+

6. **Set appropriate timeouts**: Some tasks need more coordination time

Next Steps
----------

* :doc:`mcp_integration` - Learn about MCP tools that benefit from planning mode
* :doc:`file_operations` - Understand filesystem operations in planning mode
* :doc:`../reference/yaml_schema` - Complete configuration reference
* :doc:`../examples/advanced_patterns` - Advanced planning mode patterns
