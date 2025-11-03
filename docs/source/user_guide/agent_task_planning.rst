:orphan:

Agent Task Planning
===================

Agent Task Planning enables agents to organize their work into structured task lists with dependencies during coordination.

.. note::

   **New in v0.1.7**: Agents can create and manage task plans with dependency tracking.

Quick Start
-----------

Enable task planning in your config:

.. code-block:: yaml

   orchestrator:
     coordination:
       enable_agent_task_planning: true
       max_tasks_per_plan: 10

Or use the example:

.. code-block:: bash

   massgen --config @examples/configs/tools/todo/example_task_todo.yaml \
     "Create a website about Bob Dylan"

Available Tools
---------------

When enabled, agents receive 8 MCP planning tools:

* ``create_task_plan()`` - Create a task plan with optional dependencies
* ``add_task()`` - Add tasks dynamically
* ``update_task_status()`` - Mark tasks as in_progress or completed
* ``get_task_plan()`` - View current plan with statistics
* ``get_ready_tasks()`` - See tasks ready to start
* ``get_blocked_tasks()`` - See tasks waiting on dependencies
* ``edit_task()`` - Update task descriptions
* ``delete_task()`` - Remove tasks

Example Usage
-------------

Creating a plan with dependencies:

.. code-block:: python

   create_task_plan([
       "Research OAuth providers",
       {
           "description": "Implement OAuth flow",
           "depends_on": [0]  # Depends on task 0
       },
       {
           "description": "Write tests",
           "depends_on": [1]  # Depends on task 1
       }
   ])

Tracking progress:

.. code-block:: python

   update_task_status(task_id="task_0", status="completed")
   get_ready_tasks()  # Returns task_1 (now unblocked)

Configuration
-------------

.. list-table::
   :header-rows: 1
   :widths: 30 20 50

   * - Option
     - Default
     - Description
   * - ``enable_agent_task_planning``
     - false
     - Enable task planning tools
   * - ``max_tasks_per_plan``
     - 10
     - Maximum tasks per agent

Features
--------

* **Dependency management** - Automatic validation and circular dependency detection
* **Per-agent isolation** - Each agent has their own task plan
* **Progress tracking** - Track pending, in_progress, and completed tasks
* **Automatic unblocking** - Tasks become ready when dependencies complete

See Also
--------

* :doc:`planning_mode` - Combine with planning mode for complex workflows
* :doc:`mcp_integration` - Learn about other MCP tools
