=============================
LLM Agent Automation Guide
=============================

This guide shows how to automate MassGen coordination using LLM agents and programmatic workflows.

.. contents:: Table of Contents
   :local:
   :depth: 2

Overview
========

MassGen provides **automation mode** (introduced in v0.1.8) designed specifically for LLM agents and background execution:

- ✅ **Silent output** (~10 lines instead of 250-3,000+)
- ✅ **Real-time status tracking** via ``status.json`` (updated every 2 seconds)
- ✅ **Meaningful exit codes** (success, timeout, error, interrupted)
- ✅ **Structured result files** (machine-readable JSON and text)
- ✅ **Parallel execution** support (isolated log directories)

.. seealso::
   **Real-World Example:** See the :doc:`../examples/case_studies/meta-self-analysis-automation-mode` case study demonstrating MassGen agents using automation mode to analyze MassGen itself and propose performance improvements.

Quick Start
===========

Basic Automation Mode
----------------------

.. code-block:: bash

   uv run massgen --automation --config your_config.yaml "Your question here"

**Output** (minimal, parseable):

.. code-block:: text

   LOG_DIR: /path/to/.massgen/massgen_logs/log_20251103_143022
   STATUS: /path/to/.massgen/massgen_logs/log_20251103_143022/status.json
   QUESTION: Your question here
   [Coordination in progress - monitor status.json for real-time updates]

   WINNER: agent_a
   ANSWER_FILE: /path/to/final/agent_a/answer.txt
   DURATION: 45.3s
   ANSWER_PREVIEW: The answer starts here...

   COMPLETED: 2 agents, 45.3s total

**Exit codes**:

- ``0`` = Success (coordination completed)
- ``1`` = Configuration error
- ``2`` = Execution error (agent failure, API error)
- ``3`` = Timeout
- ``4`` = Interrupted (Ctrl+C)

Using BackgroundShellManager
=============================

MassGen provides ``BackgroundShellManager`` for robust background execution. **Always use this instead of subprocess directly.**

Basic Usage
-----------

.. code-block:: python

   from massgen.filesystem_manager.background_shell import (
       start_shell,
       get_shell_output,
       get_shell_status,
       kill_shell,
   )

   # Start MassGen in background
   shell_id = start_shell(
       "uv run massgen --automation --config config.yaml 'Your question'"
   )

   # Monitor progress
   import time
   while True:
       status = get_shell_status(shell_id)
       if status["status"] != "running":
           break
       time.sleep(2)

   # Get results
   output = get_shell_output(shell_id)
   print(f"Exit code: {output['exit_code']}")
   print(f"Output:\n{output['stdout']}")

Parallel Execution
==================

Parallel Execution Safety
--------------------------

**✅ Parallel execution is AUTOMATIC and SAFE in ALL modes!**

MassGen automatically isolates all resources when running multiple instances:

1. **Generates unique instance IDs** - Appends random 8-character ID to prevent conflicts

   Example: ``workspace1`` → ``workspace1_a1b2c3d4``

2. **Isolates all resources automatically**:

   ✅ **Log directories** - Microsecond-precision timestamps

   ✅ **Workspaces** - Auto-generated unique suffixes

   ✅ **Snapshot storage** - Per-agent subdirectories

   ✅ **Docker containers** - Auto-generated unique container names (includes instance ID suffix)

**No manual configuration needed!** Just use the same config multiple times:

.. code-block:: bash

   # ✅ SAFE - Run the same config 5 times in parallel (with or without --automation)
   for i in {1..5}; do
       uv run massgen --config my_config.yaml "Task $i" &
   done
   wait

**Each instance automatically gets unique workspace paths and Docker containers:**

.. code-block:: text

   Instance 1: workspace1_a1b2c3d4, massgen-agent_a-a1b2c3d4
   Instance 2: workspace1_e5f6a7b8, massgen-agent_a-e5f6a7b8
   Instance 3: workspace1_c9d0e1f2, massgen-agent_a-c9d0e1f2

**Note:** This works in both automation mode (``--automation``) and normal mode. The difference is that automation mode provides silent output and status.json tracking, while normal mode shows the full UI.

Running Multiple Experiments Simultaneously
-------------------------------------------

**Programmatic Parallel Execution:**

Use the BackgroundShellManager for robust programmatic parallel execution:

.. code-block:: python

   from massgen.filesystem_manager.background_shell import start_shell, get_shell_status
   import time

   def run_experiments_in_parallel(configs_and_questions):
       """
       Run multiple MassGen experiments in parallel.

       Args:
           configs_and_questions: List of (config_path, question) tuples

       Returns:
           list: Results from all experiments
       """
       experiments = []

       # Start all experiments
       for config, question in configs_and_questions:
           shell_id = start_shell(
               f'uv run massgen --automation --config {config} "{question}"'
           )
           experiments.append({
               "shell_id": shell_id,
               "config": config,
               "question": question,
           })
           print(f"Started experiment {shell_id}: {question[:50]}...")

       # Wait for all to complete
       while True:
           all_done = True
           for exp in experiments:
               status = get_shell_status(exp["shell_id"])
               if status["status"] == "running":
                   all_done = False

           if all_done:
               break

           time.sleep(2)

       # Collect results
       results = []
       for exp in experiments:
           status = get_shell_status(exp["shell_id"])
           output = get_shell_output(exp["shell_id"])
           results.append({
               "config": exp["config"],
               "question": exp["question"],
               "exit_code": output["exit_code"],
               "duration": status["duration_seconds"],
               "status": status["status"],
           })

       return results


   # Example: Run the SAME config with different questions (parallel isolation is automatic!)
   experiments = [
       ("my_config.yaml", "Create a webpage about Bob Dylan"),
       ("my_config.yaml", "Write a Python script to analyze data"),
       ("my_config.yaml", "Design a REST API for a blog"),
   ]

   results = run_experiments_in_parallel(experiments)

   for result in results:
       print(f"{result['question']}: {result['status']} in {result['duration']}s")

Status File Overview
====================

The ``status.json`` file is updated every 2 seconds during coordination.

.. note::
   **For complete status.json reference with all fields documented:** See :doc:`../reference/status_file`

File Location
-------------

.. code-block:: text

   .massgen/massgen_logs/log_YYYYMMDD_HHMMSS_ffffff/status.json

Quick Reference
---------------

.. code-block:: json

   {
     "meta": {
       "last_updated": 1730678901.234,
       "session_id": "log_20251103_143022_123456",
       "log_dir": ".massgen/massgen_logs/log_20251103_143022_123456",
       "question": "Your question here",
       "start_time": 1730678800.000,
       "elapsed_seconds": 101.234
     },
     "coordination": {
       "phase": "enforcement",
       "active_agent": "agent_b",
       "completion_percentage": 65,
       "is_final_presentation": false
     },
     "agents": {
       "agent_a": {
         "status": "voted",
         "answer_count": 1,
         "latest_answer_label": "agent1.1",
         "vote_cast": {
           "voted_for_agent": "agent_a",
           "voted_for_label": "agent1.1",
           "reason_preview": "Strong JSON structure..."
         },
         "times_restarted": 1,
         "last_activity": 1730678850.123,
         "error": null
       },
       "agent_b": {
         "status": "streaming",
         "answer_count": 0,
         "latest_answer_label": null,
         "vote_cast": null,
         "times_restarted": 1,
         "last_activity": 1730678900.456,
         "error": {
           "type": "timeout",
           "message": "Agent timeout after 180s",
           "timestamp": 1730678900.0
         }
       }
     },
     "results": {
       "votes": {
         "agent1.1": 1,
         "agent1.2": 0
       },
       "winner": null,
       "final_answer_preview": null
     }
   }

Agent Status Values
-------------------

- **streaming**: Agent is actively generating content
- **answered**: Agent has provided an answer this round
- **voted**: Agent has cast their vote
- **restarting**: Agent is restarting due to new answer
- **error**: Agent encountered an error
- **timeout**: Agent timed out
- **completed**: Agent finished all work

Coordination Phases
-------------------

- **initial_answer**: Agents providing initial answers
- **enforcement**: Voting phase
- **presentation**: Final answer presentation

Reading Results
===============

Log Directory Structure
-----------------------

After coordination completes, find results in the log directory:

.. code-block:: text

   .massgen/massgen_logs/log_YYYYMMDD_HHMMSS/
   ├── execution_metadata.yaml       # Session metadata
   ├── coordination_events.json      # Complete event log
   ├── status.json                   # Final status snapshot
   ├── snapshot_mappings.json        # Answer/vote file mappings
   ├── final/
   │   └── {winner_agent}/
   │       ├── answer.txt            # ⭐ Final answer here
   │       ├── context.txt           # Agent's context
   │       └── workspace/            # Agent's workspace snapshot
   ├── agent_outputs/
   │   ├── agent_a.txt              # Full agent log
   │   └── agent_b.txt
   └── massgen.log                   # Detailed debug log

Programmatic Access
-------------------

.. code-block:: python

   import json
   from pathlib import Path

   def read_massgen_results(log_dir: Path):
       """Read MassGen coordination results."""
       # Read final status
       status = json.load(open(log_dir / "status.json"))

       # Get winner
       winner = status["results"]["winner"]

       # Read final answer
       answer_file = log_dir / f"final/{winner}/answer.txt"
       answer = answer_file.read_text() if answer_file.exists() else None

       # Read execution metadata
       import yaml
       metadata = yaml.safe_load(open(log_dir / "execution_metadata.yaml"))

       return {
           "winner": winner,
           "answer": answer,
           "duration": status["meta"]["elapsed_seconds"],
           "votes": status["results"]["votes"],
           "config": metadata["config"],
           "question": metadata["question"],
       }

Meta-Coordination: MassGen Running MassGen
===========================================

MassGen can autonomously run and monitor itself, enabling self-improvement and automated experimentation.

.. tip::
   **Case Study:** The v0.1.8 release includes a complete :doc:`../examples/case_studies/meta-self-analysis-automation-mode` demonstrating meta-coordination in action. Agents successfully ran nested MassGen experiments, analyzed execution logs, and proposed 6 prioritized performance improvements with starter code.

Available Meta Configs
-----------------------

**1. massgen_runs_massgen.yaml** - Run MassGen experiments

.. code-block:: bash

   uv run massgen --config @examples/configs/meta/massgen_runs_massgen.yaml \
       "Run a MassGen experiment to create a webpage about Bob Dylan"

**2. massgen_suggests_to_improve_massgen.yaml** - Run experiments AND suggest improvements

.. code-block:: bash

   uv run massgen --config @examples/configs/meta/massgen_suggests_to_improve_massgen.yaml \
       "Run an experiment with MassGen then read the logs and suggest any improvements to help MassGen perform better along any dimension (quality, speed, cost, creativity, etc.)."

This configuration was used in the v0.1.8 case study where agents analyzed MassGen's architecture, ran controlled experiments, and identified optimization opportunities.

Example Configuration
---------------------

**Config**: ``@examples/configs/meta/massgen_runs_massgen.yaml``

.. code-block:: yaml

   agents:
     - id: "meta_agent"
       backend:
         type: "openai"
         model: "gpt-5-mini"
         cwd: "workspace_meta"
         enable_mcp_command_line: true
         command_line_execution_mode: "local"
       system_message: |
         You have access to MassGen through the command line and can:
         - Run MassGen in automation mode using: uv run massgen --automation --config [config] "[question]"
         - Monitor progress by reading status.json files
         - Read final results from log directories
         - Parse coordination outcomes
         - Always run MassGen in a background process to avoid blocking
   orchestrator:
     snapshot_storage: "snapshots_meta"
     agent_temporary_workspace: "temp_workspaces_meta"

Running the Example
-------------------

.. code-block:: bash

   uv run massgen --config massgen/configs/meta/massgen_runs_massgen.yaml \
       "Run a MassGen experiment to create a webpage about Bob Dylan"

**What happens:**

1. The meta_agent receives your request
2. It executes: ``uv run massgen --automation --config massgen/configs/tools/todo/example_task_todo.yaml "Create a simple HTML page about Bob Dylan"``
3. It monitors the nested MassGen's ``status.json`` file
4. It reads the final results
5. It reports which agent won (agent_a or agent_b) and shows the final HTML page

**Output demonstrates:**

- ✅ MassGen can autonomously run experiments
- ✅ Can monitor progress via status.json
- ✅ Can parse and report coordination outcomes
- ✅ Can read final results from log directories

Current Limitations
-------------------

.. note::
   **Local Execution Only**: The meta-config currently uses ``command_line_execution_mode: "local"``.
   Docker execution for nested MassGen requires:

   - API credential passing to nested instances
   - Automatic dependency installation (e.g., reinstalling MassGen in container)
   - See Issue #436 for planned Docker support

.. warning::
   **Cost Control**: Meta-coordination can result in significant API costs as agents run experiments
   autonomously. Always set strict timeout limits. See Issue #432 for planned cost tracking features.


Error Handling Best Practices
==============================

1. **Always use timeouts**

   .. code-block:: python

      result = run_massgen_automation(config, question, timeout_seconds=300)

2. **Check exit codes**

   .. code-block:: python

      if result["exit_code"] == 0:
          # Success
      elif result["exit_code"] == 3:
          # Timeout - may need longer timeout or simpler query
      elif result["exit_code"] == 2:
          # Execution error - check logs

3. **Monitor agent errors in status.json**

   .. code-block:: python

      if status["agents"]["agent_a"]["error"]:
          # Handle agent-specific error

4. **Always clean up on failure**

   .. code-block:: python

      try:
          result = run_massgen_automation(config, question)
      finally:
          # Ensure shell is killed if still running
          if shell_id:
              kill_shell(shell_id)

5. **Validate results exist before reading**

   .. code-block:: python

      if answer_file.exists():
          answer = answer_file.read_text()
      else:
          # Handle missing results

Performance Tips
================

1. **Use automation mode** - Reduces output overhead significantly
2. **Poll status.json every 2-5 seconds** - Balances responsiveness and overhead
3. **Limit concurrent experiments** - BackgroundShellManager limits to 10 by default
4. **Clean up old logs** - Remove `.massgen/massgen_logs/log_*` directories periodically
5. **Use appropriate timeouts** - Simple tasks: 60s, Complex tasks: 300-600s

Troubleshooting
===============

Issue: Can't find log directory
--------------------------------

**Symptom**: LOG_DIR not printed in output

**Solutions**:

- Ensure ``--automation`` flag is used
- Check stderr for startup errors
- Verify config file exists and is valid

Issue: status.json not updating
--------------------------------

**Symptom**: status.json file not changing

**Solutions**:

- Ensure logging is enabled (``--automation`` enables it by default)
- Check if coordination is actually running
- Verify file permissions on log directory

Issue: Process hangs
--------------------

**Symptom**: Process runs indefinitely

**Solutions**:

- Set timeout in your automation script
- Monitor status.json for stuck agents
- Use ``kill_shell()`` to terminate gracefully

Issue: Exit code always 1
-------------------------

**Symptom**: Getting config errors

**Solutions**:

- Validate config with ``uv run massgen --validate --config your_config.yaml``
- Check that all required API keys are set
- Verify model names are correct

Limitations
===========

Current Constraints
-------------------

**1. Local Code Execution Only (for MassGen-running-MassGen)**

When using MassGen to run MassGen (meta-coordination), currently only local code execution is supported:

.. code-block:: yaml

   # ✅ Supported
   agents:
     - backend:
         enable_mcp_command_line: true
         command_line_execution_mode: "local"

   # ❌ Not yet supported for meta-coordination
   agents:
     - backend:
         command_line_execution_mode: "docker"
         # Issue: Requires credential passing to nested instances

**Why:** Docker execution requires API credentials, which need to be securely passed to nested MassGen instances. This will be addressed in a future PR.

**2. Cost Control**

.. warning::
   **IMPORTANT:** When using automation mode for autonomous experiments, agents can potentially execute many API calls without human oversight. This can result in unexpected costs.

**Best Practices:**
The configs you have MassGen run itself should include cost control measures:

- Set explicit timeout limits in configs to prevent indefinite hangs:

  .. code-block:: yaml

     timeout_settings:
       orchestrator_timeout_seconds: 1800  # 30 minutes max (recommended for meta-coordination)
       agent_timeout_seconds: 600          # 10 minutes per agent

  **Note**: Meta-coordination typically takes 10-30 minutes. Regular tasks: 2-10 minutes.

- Limit answers per agent for better progress tracking:

  .. code-block:: yaml

     orchestrator:
       max_new_answers_per_agent: 2  # Helps track progress more accurately

  Setting this helps estimate completion percentage more reliably. Without it, agents can provide unlimited answers, making progress tracking less predictable.

- Monitor costs via your API provider dashboards
- Use less expensive models for automated experimentation:

  .. code-block:: yaml

     agents:
       - backend:
           model: "gpt-4o-mini"  # More economical than gpt-4o

- Set API rate limits at the provider level
- Start with small experiments before scaling

**Future Enhancement:** Built-in cost tracking and limits (planned).

Next Steps
==========

- **Read** :doc:`../reference/cli` for all CLI options
- **See** :doc:`../reference/status_file` for complete status.json documentation
- **See** :doc:`../reference/yaml_schema` for configuration details
- **Check** :doc:`../examples/basic_examples` for working examples
- **Review** ``massgen/filesystem_manager/background_shell.py`` source code
