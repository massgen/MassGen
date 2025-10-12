Project Integration & Context Paths
====================================

**NEW in v0.0.21**

Work directly with your existing projects! Context paths allow you to share specific directories with all agents while maintaining granular permission control.

Quick Start
-----------

.. code-block:: bash

   # Multi-agent collaboration on your website
   uv run python -m massgen.cli \
     --config massgen/configs/tools/filesystem/gpt5mini_cc_fs_context_path.yaml \
     "Enhance the website with dark/light theme toggle and interactive features"

Configuration
-------------

Context Paths Setup
~~~~~~~~~~~~~~~~~~~

Share directories with all agents using ``context_paths``:

.. code-block:: yaml

   agents:
     - id: "code-reviewer"
       backend:
         type: "claude_code"
         cwd: "workspace"          # Agent's isolated work area

   orchestrator:
     context_paths:
       - path: "/home/user/my-project/src"
         permission: "read"        # Agents can analyze your code
       - path: "/home/user/my-project/docs"
         permission: "write"       # Final agent can update docs

Configuration Parameters
~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - Parameter
     - Required
     - Description
   * - ``context_paths``
     - Yes
     - List of shared directories for all agents
   * - ``path``
     - Yes
     - **Absolute path to directory** (must be directory, not file)
   * - ``permission``
     - Yes
     - Access level: ``"read"`` or ``"write"``

.. warning::

   Context paths must point to **directories**, not individual files. MassGen validates all paths during startup and will show clear error messages for missing or invalid paths.

Permissions Model
-----------------

Context vs Final Agent Permissions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Different permission levels during different phases:

**During Coordination (Context Agents):**
   All context paths are **READ-ONLY**, regardless of configuration. This protects your files during multi-agent discussion.

**Final Presentation (Winning Agent):**
   The winning agent gets the **configured permission** (read or write) for final execution.

**Example:**

.. code-block:: yaml

   orchestrator:
     context_paths:
       - path: "/home/user/project/src"
         permission: "write"

**What happens:**

1. **Coordination phase** → All agents have READ access to ``/src``
2. **Final presentation** → Winning agent has WRITE access to ``/src``

Read Permission
~~~~~~~~~~~~~~~

Agents can:

* Read all files in the directory
* Analyze code structure
* Extract information
* Reference content in responses

Agents **cannot:**

* Create new files
* Modify existing files
* Delete files

**Use cases:**

* Code review and analysis
* Documentation generation from source code
* Data extraction and reporting
* Pattern detection and recommendations

Write Permission
~~~~~~~~~~~~~~~~

Final agent can:

* Read all files
* Create new files
* Modify existing files
* Delete files (with read-before-delete safety)

**Use cases:**

* Code refactoring and updates
* Documentation updates
* Test generation
* Project modernization

Multi-Agent Project Collaboration
----------------------------------

Advanced Example
~~~~~~~~~~~~~~~~

.. code-block:: yaml

   agents:
     - id: "analyzer"
       backend:
         type: "gemini"
         cwd: "analysis_workspace"

     - id: "implementer"
       backend:
         type: "claude_code"
         cwd: "implementation_workspace"

   orchestrator:
     context_paths:
       - path: "/home/user/legacy-app/src"
         permission: "read"           # Read existing codebase
       - path: "/home/user/legacy-app/tests"
         permission: "write"          # Write new tests
       - path: "/home/user/modernized-app"
         permission: "write"          # Create modernized version

This configuration:

* All agents can read the legacy codebase
* All agents can discuss modernization approaches
* Winning agent can write tests and create modernized version

Clean Project Organization
---------------------------

The .massgen/ Directory
~~~~~~~~~~~~~~~~~~~~~~~

All MassGen working files are organized under ``.massgen/`` in your project root:

.. code-block:: text

   your-project/
   ├── .massgen/                          # All MassGen state
   │   ├── sessions/                      # Multi-turn conversation history
   │   │   └── session_20250108_143022/
   │   │       ├── turn_1/                # Results from turn 1
   │   │       ├── turn_2/                # Results from turn 2
   │   │       └── SESSION_SUMMARY.txt    # Human-readable summary
   │   ├── workspaces/                    # Agent working directories
   │   │   ├── analysis_workspace/        # Analyzer's isolated workspace
   │   │   └── implementation_workspace/  # Implementer's workspace
   │   ├── snapshots/                     # Workspace snapshots for coordination
   │   └── temp_workspaces/               # Previous turn results for context
   ├── src/                               # Your actual project files
   ├── tests/                             # Your tests
   └── docs/                              # Your documentation

Benefits
~~~~~~~~

✅ **Clean Projects**
   All MassGen files contained in one directory

✅ **Easy .gitignore**
   Just add ``.massgen/`` to your ``.gitignore``

✅ **Portable**
   Move or delete ``.massgen/`` without affecting your project

✅ **Multi-Turn Sessions**
   Conversation history preserved across sessions

Configuration Auto-Organization
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

You specify simple names, MassGen organizes under ``.massgen/``:

.. code-block:: yaml

   orchestrator:
     snapshot_storage: "snapshots"         # → .massgen/snapshots/
     session_storage: "sessions"           # → .massgen/sessions/
     agent_temporary_workspace: "temp"     # → .massgen/temp/

   agents:
     - backend:
         cwd: "workspace1"                 # → .massgen/workspaces/workspace1/

Adding to .gitignore
~~~~~~~~~~~~~~~~~~~~

.. code-block:: gitignore

   # MassGen state and working files
   .massgen/

This excludes all MassGen temporary files, sessions, and workspaces from version control while keeping your project clean.

Use Cases
---------

Code Review
~~~~~~~~~~~

Agents analyze your source code and suggest improvements:

.. code-block:: yaml

   orchestrator:
     context_paths:
       - path: "/home/user/project/src"
         permission: "read"
       - path: "/home/user/project/review-notes"
         permission: "write"

.. code-block:: bash

   uv run python -m massgen.cli \
     --config code_review.yaml \
     "Review the authentication module for security issues and best practices"

Documentation Generation
~~~~~~~~~~~~~~~~~~~~~~~~~

Agents read project code to understand context and generate/update documentation:

.. code-block:: yaml

   orchestrator:
     context_paths:
       - path: "/home/user/project/src"
         permission: "read"
       - path: "/home/user/project/docs"
         permission: "write"

.. code-block:: bash

   uv run python -m massgen.cli \
     --config doc_generator.yaml \
     "Update the API documentation to reflect recent changes in the auth module"

Data Processing
~~~~~~~~~~~~~~~

Agents access shared datasets and generate analysis reports:

.. code-block:: yaml

   orchestrator:
     context_paths:
       - path: "/home/user/datasets"
         permission: "read"
       - path: "/home/user/reports"
         permission: "write"

.. code-block:: bash

   uv run python -m massgen.cli \
     --config data_analysis.yaml \
     "Analyze the Q4 sales data and create a comprehensive report with visualizations"

Project Migration
~~~~~~~~~~~~~~~~~

Agents examine existing projects and create modernized versions:

.. code-block:: yaml

   orchestrator:
     context_paths:
       - path: "/home/user/old-project"
         permission: "read"
       - path: "/home/user/new-project"
         permission: "write"

.. code-block:: bash

   uv run python -m massgen.cli \
     --config migration.yaml \
     "Migrate the Flask 1.x application to Flask 3.x with modern best practices"

Security Considerations
-----------------------

.. warning::

   **Agents can autonomously read/write files** in context paths with write permission.

Before granting write access:

* ✅ **Backup your code** - Ensure you have version control or backups
* ✅ **Test first** - Try with read-only permission first
* ✅ **Isolated projects** - Consider testing on a copy of your project
* ✅ **Review permissions** - Double-check which paths have write access
* ✅ **Use version control** - Git/VCS allows easy rollback

Path Validation
~~~~~~~~~~~~~~~

MassGen validates all context paths at startup:

* ✅ Paths must exist
* ✅ Paths must be directories (not files)
* ✅ Paths must be absolute (not relative)

**Error messages:**

.. code-block:: text

   Error: Context path '/home/user/project/file.txt' is not a directory
   Error: Context path '/home/user/missing' does not exist
   Error: Context path must be absolute, got 'relative/path'

Best Practices
--------------

1. **Start with read-only** - Analyze before modifying
2. **Granular permissions** - Only grant write where needed
3. **Use .gitignore** - Exclude ``.massgen/`` from version control
4. **Review agent work** - Check ``.massgen/workspaces/`` before accepting changes
5. **Backup important projects** - Use Git or other VCS
6. **Test configurations** - Try on sample projects first

Example: Complete Project Setup
--------------------------------

.. code-block:: yaml

   agents:
     - id: "analyzer"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
         cwd: "analyzer_workspace"

     - id: "developer"
       backend:
         type: "claude_code"
         model: "claude-sonnet-4"
         cwd: "developer_workspace"

   orchestrator:
     # Project integration
     context_paths:
       - path: "/Users/me/myproject/src"
         permission: "read"           # Analyze existing code
       - path: "/Users/me/myproject/tests"
         permission: "write"          # Generate tests
       - path: "/Users/me/myproject/docs"
         permission: "write"          # Update documentation

     # MassGen state (auto-organized under .massgen/)
     snapshot_storage: "snapshots"
     session_storage: "sessions"
     agent_temporary_workspace: "temp"

   ui:
     display_type: "rich_terminal"
     logging_enabled: true

**Project structure after running:**

.. code-block:: text

   myproject/
   ├── .massgen/                    # All MassGen state
   │   ├── workspaces/
   │   │   ├── analyzer_workspace/
   │   │   └── developer_workspace/
   │   ├── snapshots/
   │   ├── sessions/
   │   └── temp/
   ├── src/                         # Your source (read access)
   ├── tests/                       # Generated tests (write access)
   ├── docs/                        # Updated docs (write access)
   └── .gitignore                   # Contains .massgen/

Next Steps
----------

* :doc:`file_operations` - Learn more about workspace management
* :doc:`mcp_integration` - Additional tools for project work
* :doc:`multi_turn_mode` - Iterative project development across turns
* :doc:`../quickstart/running-massgen` - More examples
