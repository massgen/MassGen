Timeout Configuration
=====================

MassGen provides timeout configuration to control how long coordination and agent operations can run before being terminated. This prevents runaway processes and ensures predictable execution times.

Quick Reference
---------------

**Default Timeout**:

* **Orchestrator**: 1800 seconds (30 minutes)

**CLI Override**:

.. code-block:: bash

   uv run python -m massgen.cli \
     --orchestrator-timeout 600 \
     --config config.yaml \
     "Your question"

**Config File**:

.. code-block:: yaml

   timeout_settings:
     orchestrator_timeout_seconds: 1800

Timeout Types
-------------

Orchestrator Timeout
~~~~~~~~~~~~~~~~~~~~

Controls the maximum time for multi-agent coordination:

* **Covers**: Entire coordination process (all rounds of voting and consensus)
* **Default**: 1800 seconds (30 minutes)
* **When it triggers**: Coordination exceeds the time limit
* **What happens**: Coordination terminates gracefully, current state is saved

.. code-block:: yaml

   timeout_settings:
     orchestrator_timeout_seconds: 600  # 10 minutes

Configuration Methods
---------------------

Method 1: CLI Flag (Highest Priority)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Override timeout for a single run:

.. code-block:: bash

   # Short timeout for simple task
   uv run python -m massgen.cli \
     --orchestrator-timeout 300 \
     --config config.yaml \
     "What is 2+2?"

   # Longer timeout for complex research
   uv run python -m massgen.cli \
     --orchestrator-timeout 3600 \
     --config config.yaml \
     "Conduct comprehensive market analysis with 5 agents"

Method 2: Configuration File
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Set timeout in your YAML configuration:

.. code-block:: yaml

   # Basic configuration with custom timeout
   agents:
     - id: "agent1"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"

   timeout_settings:
     orchestrator_timeout_seconds: 900  # 15 minutes

   ui:
     display_type: "rich_terminal"

Method 3: Default (No Configuration)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If not specified, MassGen uses the default 30-minute timeout:

.. code-block:: yaml

   # This configuration will use default 1800s timeout
   agents:
     - id: "agent1"
       backend:
         type: "openai"
         model: "gpt-4o"

Timeout Behavior
----------------

What Happens When Timeout Occurs
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When the orchestrator timeout is reached:

1. **Current coordination round completes** (not interrupted mid-operation)
2. **Partial results saved** (current state is preserved)
3. **Error message displayed** indicating timeout
4. **Graceful shutdown** (agents cleanup properly)

.. code-block:: text

   🔄 Round 5 of coordination...
   ⏰ Orchestrator timeout reached (1800 seconds)
   💾 Saving current state...
   ❌ Coordination incomplete - timeout exceeded

**Important**: The system attempts graceful termination. Individual agent operations may still complete if they're in progress.

Successful Completion Before Timeout
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If coordination completes normally:

.. code-block:: text

   ✅ Coordination complete!
   ⏱️  Total time: 245 seconds (well under 1800s limit)

Choosing the Right Timeout
---------------------------

Simple Tasks (5-10 minutes)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Recommended**: 300-600 seconds

.. code-block:: yaml

   timeout_settings:
     orchestrator_timeout_seconds: 600

**Examples**:

* Quick research questions
* Single-agent tasks
* Fast LLM models (GPT-4o-mini, Gemini Flash)
* Tasks with 2-3 agents

.. code-block:: bash

   uv run python -m massgen.cli \
     --orchestrator-timeout 600 \
     --model gemini-2.5-flash \
     "What are the key features of Python 3.12?"

Standard Tasks (15-30 minutes)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Recommended**: 900-1800 seconds (default)

.. code-block:: yaml

   timeout_settings:
     orchestrator_timeout_seconds: 1800  # Default

**Examples**:

* Multi-agent coordination (3-5 agents)
* Tasks with external API calls (MCP tools)
* Code generation with file operations
* Research with web search

.. code-block:: bash

   uv run python -m massgen.cli \
     --config multi_agent_config.yaml \
     "Analyze market trends and create a report"

Complex Tasks (30-60 minutes)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Recommended**: 1800-3600 seconds

.. code-block:: yaml

   timeout_settings:
     orchestrator_timeout_seconds: 3600  # 1 hour

**Examples**:

* Large-scale code refactoring
* Comprehensive research with many sources
* Tasks involving multiple API calls
* 5+ agents coordination
* Planning mode with extensive discussion

.. code-block:: bash

   uv run python -m massgen.cli \
     --orchestrator-timeout 3600 \
     --config five_agents_research.yaml \
     "Conduct a complete competitive analysis of the AI market"

Long-Running Tasks (60+ minutes)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Recommended**: 3600+ seconds

.. code-block:: yaml

   timeout_settings:
     orchestrator_timeout_seconds: 7200  # 2 hours

.. warning::

   Very long timeouts can lead to expensive API costs. Consider breaking down the task or using checkpoints.

**Examples**:

* Full codebase analysis
* Large-scale data processing
* Multi-stage project generation
* Complex multi-turn conversations

Examples by Task Type
----------------------

Example 1: Quick Analysis
~~~~~~~~~~~~~~~~~~~~~~~~~

**Task**: Simple question, single agent

.. code-block:: bash

   uv run python -m massgen.cli \
     --orchestrator-timeout 300 \
     --backend openai \
     --model gpt-4o-mini \
     "Explain quantum entanglement in simple terms"

**Reasoning**: Single agent with fast model, expected completion in 1-2 minutes, 5-minute timeout gives buffer.

Example 2: Multi-Agent Research
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Task**: Three agents researching and comparing approaches

.. code-block:: yaml

   agents:
     - id: "researcher1"
       backend: {type: "gemini", model: "gemini-2.5-flash"}
     - id: "researcher2"
       backend: {type: "openai", model: "gpt-4o"}
     - id: "researcher3"
       backend: {type: "claude", model: "claude-sonnet-4"}

   timeout_settings:
     orchestrator_timeout_seconds: 1200  # 20 minutes

**Reasoning**: Multiple rounds of coordination expected, web search enabled, 20 minutes allows for thorough research and discussion.

Example 3: Code Generation with Files
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Task**: Generate project structure with multiple files

.. code-block:: yaml

   agents:
     - id: "architect"
       backend: {type: "claude_code", cwd: "workspace"}
     - id: "reviewer"
       backend: {type: "gemini", model: "gemini-2.5-flash"}

   orchestrator:
     coordination:
       enable_planning_mode: true

   timeout_settings:
     orchestrator_timeout_seconds: 1800  # 30 minutes

**Reasoning**: Planning mode discussion + file creation, default 30 minutes is appropriate.

Example 4: MCP Tool Integration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Task**: Use multiple MCP tools with planning mode

.. code-block:: yaml

   agents:
     - id: "agent1"
       backend:
         type: "openai"
         model: "gpt-5-nano"
         mcp_servers:
           - {name: "weather", ...}
           - {name: "search", ...}

   orchestrator:
     coordination:
       enable_planning_mode: true

   timeout_settings:
     orchestrator_timeout_seconds: 2400  # 40 minutes

**Reasoning**: MCP tools may have API latency, planning mode adds coordination time, 40 minutes provides safety margin.

Troubleshooting
---------------

Timeouts Occurring Too Frequently
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**:

* Tasks consistently hitting timeout
* Coordination incomplete messages
* Partial results only

**Solutions**:

1. **Increase timeout**:

   .. code-block:: yaml

      timeout_settings:
        orchestrator_timeout_seconds: 3600  # Double the default

2. **Reduce agent count**: Fewer agents = faster coordination

3. **Simplify task**: Break complex tasks into smaller subtasks

4. **Use faster models**: Consider GPT-4o-mini or Gemini Flash instead of larger models

5. **Disable planning mode** if not needed:

   .. code-block:: yaml

      orchestrator:
        coordination:
          enable_planning_mode: false

6. **Check for stuck agents**: Review debug logs for agents not responding

Tasks Completing Too Quickly
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Symptoms**:

* Coordination ends in seconds
* Agents immediately voting without discussion
* Short timeout may be unnecessarily limiting deeper analysis

**Solutions**:

* This is generally not a problem - fast completion is good!
* If you want more thorough discussion, adjust system messages to encourage analysis

Timeout But No Error Message
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Problem**: Timeout occurs but no clear indication in output.

**Solution**: Enable debug logging:

.. code-block:: bash

   uv run python -m massgen.cli \
     --debug \
     --orchestrator-timeout 600 \
     --config config.yaml \
     "Your question"

Check logs in ``agent_outputs/log_{timestamp}/massgen_debug.log``

Best Practices
--------------

1. **Start with defaults**: Use the 30-minute default unless you have specific needs

2. **Adjust based on task complexity**:

   * Simple: 300-600s
   * Standard: 900-1800s
   * Complex: 1800-3600s
   * Very complex: 3600+s

3. **Consider cost implications**: Longer timeouts = potentially higher API costs

4. **Use CLI overrides for testing**: Test with shorter timeouts first

   .. code-block:: bash

      # Test with 5-minute timeout
      uv run python -m massgen.cli --orchestrator-timeout 300 --config test.yaml "test"

      # Then use full timeout for production
      uv run python -m massgen.cli --config prod.yaml "real task"

5. **Monitor actual completion times**: Check logs to see typical durations for your tasks

6. **Set appropriate timeouts per environment**:

   .. code-block:: yaml

      # Development config
      timeout_settings:
        orchestrator_timeout_seconds: 600  # Fast feedback

   .. code-block:: yaml

      # Production config
      timeout_settings:
        orchestrator_timeout_seconds: 3600  # Allow full completion

7. **Document timeout choices**: Add comments explaining timeout rationale

   .. code-block:: yaml

      timeout_settings:
        # 40 minutes: allows for 5 agents, planning mode, and MCP tool latency
        orchestrator_timeout_seconds: 2400

API Cost Considerations
-----------------------

Longer timeouts can lead to higher costs:

**Estimated API Costs by Timeout**:

.. list-table::
   :header-rows: 1
   :widths: 20 20 30 30

   * - Timeout
     - Typical Duration
     - 3-Agent Scenario
     - 5-Agent Scenario
   * - 5 min
     - 2-3 min
     - $0.10-0.50
     - $0.20-0.80
   * - 30 min (default)
     - 5-15 min
     - $0.50-2.00
     - $1.00-4.00
   * - 1 hour
     - 20-40 min
     - $2.00-5.00
     - $4.00-10.00
   * - 2 hours
     - 40-90 min
     - $5.00-15.00
     - $10.00-30.00

.. note::

   These are rough estimates. Actual costs depend on:

   * Models used (GPT-4 vs GPT-4o-mini, etc.)
   * Number of coordination rounds
   * Tool usage (MCP, code execution, web search)
   * Response lengths

**Cost-Saving Tips**:

1. Use shorter timeouts for testing
2. Choose efficient models (GPT-4o-mini, Gemini Flash)
3. Limit agent count for simple tasks
4. Monitor actual usage and adjust timeouts accordingly

Debug and Monitoring
--------------------

Viewing Timeout Information
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Enable debug logging to see timeout details:

.. code-block:: bash

   uv run python -m massgen.cli --debug --config config.yaml "question"

Look for timeout-related messages in ``agent_outputs/log_{timestamp}/massgen_debug.log``:

.. code-block:: text

   [INFO] Orchestrator timeout configured: 1800 seconds
   [INFO] Starting coordination...
   [INFO] Round 1 complete (elapsed: 45s / 1800s)
   [INFO] Round 2 complete (elapsed: 128s / 1800s)
   ...

Monitoring Coordination Progress
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

In the terminal UI, watch for elapsed time indicators:

.. code-block:: text

   ┌─ Coordination Progress ─────────────────┐
   │ Round: 3/∞                              │
   │ Elapsed: 234s / 1800s (13%)             │
   │ Status: In progress                     │
   └──────────────────────────────────────────┘

Related Configuration
---------------------

* :doc:`../user_guide/concepts` - Understanding coordination mechanics
* :doc:`../user_guide/planning_mode` - Planning mode and coordination time
* :doc:`yaml_schema` - Complete configuration reference
* :doc:`cli` - CLI timeout flags

Next Steps
----------

* Test your configuration with appropriate timeouts
* Monitor actual completion times in your use cases
* Adjust timeouts based on observed patterns
* Consider cost vs. completion trade-offs
