=======================
status.json Reference
=======================

The ``status.json`` file provides real-time monitoring of MassGen coordination. It is updated every 2 seconds during execution when using ``--automation`` mode.

.. contents:: Table of Contents
   :local:
   :depth: 2

File Location
=============

.. code-block:: text

   .massgen/massgen_logs/log_YYYYMMDD_HHMMSS_ffffff/status.json

The file appears in the log directory immediately after coordination begins and is continuously updated until completion.

Update Frequency
================

- **Updated every 2 seconds** during coordination
- **Final snapshot** written when coordination completes
- **Atomic writes** (temp file + rename) to prevent partial reads

Complete Schema
===============

Root Structure
--------------

.. code-block:: json

   {
     "meta": { ... },
     "coordination": { ... },
     "agents": { ... },
     "results": { ... }
   }

meta Section
------------

Session metadata and timing information.

.. list-table::
   :header-rows: 1
   :widths: 20 15 65

   * - Field
     - Type
     - Description
   * - ``last_updated``
     - float
     - Unix timestamp when this file was last updated
   * - ``session_id``
     - string
     - Log directory name (e.g., ``log_20251103_143022_123456``)
   * - ``log_dir``
     - string
     - Full path to log directory
   * - ``question``
     - string
     - The user's original question
   * - ``start_time``
     - float
     - Unix timestamp when coordination started
   * - ``elapsed_seconds``
     - float
     - Total time elapsed since coordination started

**Example:**

.. code-block:: json

   {
     "meta": {
       "last_updated": 1730678901.234,
       "session_id": "log_20251103_143022_123456",
       "log_dir": ".massgen/massgen_logs/log_20251103_143022_123456",
       "question": "Create a website about Bob Dylan",
       "start_time": 1730678800.000,
       "elapsed_seconds": 101.234
     }
   }

coordination Section
--------------------

Current state of the coordination process.

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - Field
     - Type
     - Description
   * - ``phase``
     - string
     - Current coordination phase: ``initial_answer``, ``enforcement``, or ``presentation``
   * - ``active_agent``
     - string|null
     - Agent ID currently streaming/working, or ``null`` if none active
   * - ``completion_percentage``
     - integer
     - Estimated completion (0-100). Based on answers submitted and votes cast.
   * - ``is_final_presentation``
     - boolean
     - Whether we're in the final presentation phase (winner presenting answer)

**Coordination Phases:**

1. **initial_answer**: Agents are providing their initial answers
2. **enforcement**: Agents are voting on the best answer
3. **presentation**: Winning agent is presenting the final answer

**Example:**

.. code-block:: json

   {
     "coordination": {
       "phase": "enforcement",
       "active_agent": "agent_b",
       "completion_percentage": 65,
       "is_final_presentation": false
     }
   }

agents Section
--------------

Per-agent detailed status. Each agent has its own entry keyed by agent ID.

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - Field
     - Type
     - Description
   * - ``status``
     - string
     - Current agent status (see Status Values below)
   * - ``answer_count``
     - integer
     - Number of answers this agent has provided (usually 0 or 1)
   * - ``latest_answer_label``
     - string|null
     - Label of most recent answer (e.g., ``agent1.1``), or ``null`` if no answer yet
   * - ``vote_cast``
     - object|null
     - Vote information if agent has voted, or ``null`` if not voted yet
   * - ``times_restarted``
     - integer
     - Number of times this agent has been restarted due to new answers from others
   * - ``last_activity``
     - float
     - Unix timestamp of agent's most recent activity
   * - ``error``
     - object|null
     - Error information if agent encountered error, or ``null`` if no error

**Agent Status Values:**

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Status
     - Description
   * - ``waiting``
     - Agent has not started work yet
   * - ``streaming``
     - Agent is actively generating content (thinking, reasoning, using tools)
   * - ``answered``
     - Agent has provided an answer but hasn't voted yet
   * - ``voted``
     - Agent has cast their vote
   * - ``restarting``
     - Agent is restarting due to new answer from another agent
   * - ``error``
     - Agent encountered an error
   * - ``timeout``
     - Agent exceeded timeout limit
   * - ``completed``
     - Agent has finished all work

**vote_cast Structure:**

.. code-block:: json

   {
     "voted_for_agent": "agent_b",
     "voted_for_label": "agent2.1",
     "reason_preview": "First 100 characters of vote reason..."
   }

**error Structure:**

.. code-block:: json

   {
     "type": "timeout",
     "message": "Agent timeout after 180s",
     "timestamp": 1730678900.0
   }

**Example:**

.. code-block:: json

   {
     "agents": {
       "agent_a": {
         "status": "voted",
         "answer_count": 1,
         "latest_answer_label": "agent1.1",
         "vote_cast": {
           "voted_for_agent": "agent_b",
           "voted_for_label": "agent2.1",
           "reason_preview": "More comprehensive solution with better structure..."
         },
         "times_restarted": 1,
         "last_activity": 1730678850.123,
         "error": null
       },
       "agent_b": {
         "status": "streaming",
         "answer_count": 1,
         "latest_answer_label": "agent2.1",
         "vote_cast": null,
         "times_restarted": 0,
         "last_activity": 1730678900.456,
         "error": null
       }
     }
   }

results Section
---------------

Aggregated coordination results.

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - Field
     - Type
     - Description
   * - ``votes``
     - object
     - Vote count by answer label. Keys are answer labels (e.g., ``agent1.1``), values are vote counts.
   * - ``winner``
     - string|null
     - Agent ID of the winning agent, or ``null`` if not yet determined
   * - ``final_answer_preview``
     - string|null
     - First 200 characters of final answer, or ``null`` if not available

**Example:**

.. code-block:: json

   {
     "results": {
       "votes": {
         "agent1.1": 1,
         "agent2.1": 2
       },
       "winner": "agent_b",
       "final_answer_preview": "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n    <meta charset=\"UTF-8\">..."
     }
   }

Complete Example
================

Full status.json during enforcement phase:

.. code-block:: json

   {
     "meta": {
       "last_updated": 1730678901.234,
       "session_id": "log_20251103_143022_123456",
       "log_dir": ".massgen/massgen_logs/log_20251103_143022_123456",
       "question": "Create a website about Bob Dylan",
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
           "voted_for_agent": "agent_b",
           "voted_for_label": "agent2.1",
           "reason_preview": "More comprehensive solution with better structure and styling..."
         },
         "times_restarted": 1,
         "last_activity": 1730678850.123,
         "error": null
       },
       "agent_b": {
         "status": "streaming",
         "answer_count": 1,
         "latest_answer_label": "agent2.1",
         "vote_cast": null,
         "times_restarted": 0,
         "last_activity": 1730678900.456,
         "error": null
       }
     },
     "results": {
       "votes": {
         "agent1.1": 0,
         "agent2.1": 1
       },
       "winner": null,
       "final_answer_preview": null
     }
   }

Usage Examples
==============

Monitoring Progress
-------------------

**Command line:**

.. code-block:: bash

   # Watch completion percentage
   watch -n 2 'cat .massgen/massgen_logs/log_*/status.json | jq ".coordination.completion_percentage"'

   # Watch which agent is active
   watch -n 2 'cat .massgen/massgen_logs/log_*/status.json | jq ".coordination.active_agent"'

   # Check for errors
   watch -n 2 'cat .massgen/massgen_logs/log_*/status.json | jq ".agents[].error"'

**Reading in scripts:**

.. code-block:: bash

   # Parse with jq
   STATUS_FILE=".massgen/massgen_logs/log_20251103_143022_123456/status.json"

   # Get completion percentage
   jq '.coordination.completion_percentage' $STATUS_FILE

   # Get winner (when done)
   jq '.results.winner' $STATUS_FILE

   # Check if any agent has error
   jq '.agents | to_entries[] | select(.value.error != null)' $STATUS_FILE

Detecting Completion
--------------------

Coordination is complete when:

.. code-block:: bash

   # Method 1: Check winner field
   WINNER=$(jq -r '.results.winner' $STATUS_FILE)
   if [ "$WINNER" != "null" ]; then
       echo "Coordination complete! Winner: $WINNER"
   fi

   # Method 2: Check completion percentage
   COMPLETION=$(jq '.coordination.completion_percentage' $STATUS_FILE)
   if [ "$COMPLETION" -eq 100 ]; then
       echo "Coordination complete!"
   fi

   # Method 3: Check if final presentation
   IS_FINAL=$(jq '.coordination.is_final_presentation' $STATUS_FILE)
   if [ "$IS_FINAL" = "true" ]; then
       echo "In final presentation phase"
   fi

Detecting Errors
----------------

.. code-block:: bash

   # Check for any agent errors
   ERRORS=$(jq '[.agents[] | select(.error != null)] | length' $STATUS_FILE)
   if [ "$ERRORS" -gt 0 ]; then
       echo "Found $ERRORS agent(s) with errors:"
       jq '.agents | to_entries[] | select(.value.error != null) | {agent: .key, error: .value.error}' $STATUS_FILE
   fi

Reading Final Answer
--------------------

Once ``winner`` is not null:

.. code-block:: bash

   # Get winner agent ID
   WINNER=$(jq -r '.results.winner' $STATUS_FILE)

   # Read final answer
   LOG_DIR=$(jq -r '.meta.log_dir' $STATUS_FILE)
   cat "$LOG_DIR/final/$WINNER/answer.txt"

Typical Progression
===================

status.json evolves through these states during coordination:

**1. Initial State** (Just started):

.. code-block:: json

   {
     "coordination": {
       "phase": "initial_answer",
       "active_agent": "agent_a",
       "completion_percentage": 0,
       "is_final_presentation": false
     },
     "agents": {
       "agent_a": {"status": "streaming", "answer_count": 0},
       "agent_b": {"status": "waiting", "answer_count": 0}
     },
     "results": {"votes": {}, "winner": null}
   }

**2. First Answer Provided**:

.. code-block:: json

   {
     "coordination": {
       "phase": "initial_answer",
       "active_agent": "agent_b",
       "completion_percentage": 25
     },
     "agents": {
       "agent_a": {"status": "answered", "answer_count": 1},
       "agent_b": {"status": "streaming", "answer_count": 0}
     },
     "results": {"votes": {}, "winner": null}
   }

**3. Voting Phase**:

.. code-block:: json

   {
     "coordination": {
       "phase": "enforcement",
       "active_agent": "agent_a",
       "completion_percentage": 50
     },
     "agents": {
       "agent_a": {"status": "streaming", "answer_count": 1},
       "agent_b": {"status": "voted", "answer_count": 1, "vote_cast": {...}}
     },
     "results": {
       "votes": {"agent2.1": 1},
       "winner": null
     }
   }

**4. Completed**:

.. code-block:: json

   {
     "coordination": {
       "phase": "presentation",
       "active_agent": null,
       "completion_percentage": 100,
       "is_final_presentation": true
     },
     "agents": {
       "agent_a": {"status": "voted", "answer_count": 1},
       "agent_b": {"status": "voted", "answer_count": 1}
     },
     "results": {
       "votes": {"agent1.1": 1, "agent2.1": 1},
       "winner": "agent_a",
       "final_answer_preview": "<!DOCTYPE html>..."
     }
   }

See Also
========

- :doc:`../user_guide/automation` - Complete automation guide
- :doc:`cli` - CLI reference including ``--automation`` flag
- ``AI_USAGE.md`` - Quick reference for LLM agents
