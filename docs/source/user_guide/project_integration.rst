Project Integration & Context Paths
====================================

**NEW in v0.0.21** - Directory-level context paths
**ENHANCED in v0.0.26** - File-level context paths

Work directly with your existing projects! Context paths allow you to share specific **directories or individual files** with all agents while maintaining granular permission control.

Quick Start
-----------

**For coding projects** (recommended - auto-detects context from current directory):

.. code-block:: bash

   # Run from your project directory - MassGen will offer to add it as context
   cd /path/to/your-project
   uv tool run massgen "Enhance the website with dark/light theme toggle and interactive features"

**Using explicit config** (for predefined setups):

.. code-block:: bash

   massgen \
     --config @examples/tools/filesystem/gpt5mini_cc_fs_context_path.yaml \
     "Enhance the website with dark/light theme toggle and interactive features"

Configuration
-------------

Context Paths Setup
~~~~~~~~~~~~~~~~~~~

Share directories **or individual files** with all agents using ``context_paths``:

.. code-block:: yaml

   agents:
     - id: "code-reviewer"
       backend:
         type: "claude_code"
         cwd: "workspace"          # Agent's isolated work area

   orchestrator:
     # Required for file operations
     snapshot_storage: "snapshots"
     agent_temporary_workspace: "temp_workspaces"

     # Context paths - directories OR individual files
     context_paths:
       - path: "/home/user/my-project/src"           # Directory access
         permission: "read"                          # Agents can analyze your code
       - path: "/home/user/my-project/docs"          # Directory access
         permission: "write"                         # Final agent can update docs
       - path: "/home/user/my-project/config.yaml"   # Single file access (v0.0.26+)
         permission: "read"                          # Access only this file

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
     - List of shared directories or files for all agents
   * - ``path``
     - Yes
     - **Absolute path to directory OR file** (both supported as of v0.0.26)
   * - ``permission``
     - Yes
     - Access level: ``"read"`` or ``"write"``
   * - ``snapshot_storage``
     - Yes
     - Directory for workspace snapshots (required for file operations)
   * - ``agent_temporary_workspace``
     - Yes
     - Parent directory for temporary workspaces (required for file operations)

.. note::

   **v0.0.26+**: Context paths can now point to **individual files** in addition to directories. This allows you to grant agents access to specific configuration files or reference documents without exposing the entire directory.

   **File-level access**: When a file path is provided, agents can only access that specific file - sibling files in the same directory are blocked for security.

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
     # Required for file operations
     snapshot_storage: "snapshots"
     agent_temporary_workspace: "temp_workspaces"

     # Context paths - mix of directories and files
     context_paths:
       - path: "/home/user/legacy-app/src"              # Directory access
         permission: "read"                             # Read existing codebase
       - path: "/home/user/legacy-app/.env.example"    # Single file access (v0.0.26+)
         permission: "read"                             # Access only env template
       - path: "/home/user/legacy-app/tests"            # Directory access
         permission: "write"                            # Write new tests
       - path: "/home/user/modernized-app"              # Directory access
         permission: "write"                            # Create modernized version

This configuration:

* All agents can read the legacy codebase directory
* Agents can access the `.env.example` template but not other config files
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
     snapshot_storage: "snapshots"         # → .massgen/snapshots/ (REQUIRED)
     session_storage: "sessions"           # → .massgen/sessions/ (optional)
     agent_temporary_workspace: "temp"     # → .massgen/temp/ (REQUIRED)

   agents:
     - backend:
         cwd: "workspace1"                 # → .massgen/workspaces/workspace1/

.. note::

   ``snapshot_storage`` and ``agent_temporary_workspace`` are **required** when using file operations or context paths.

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
     snapshot_storage: "snapshots"
     agent_temporary_workspace: "temp_workspaces"

     context_paths:
       - path: "/home/user/project/src"
         permission: "read"
       - path: "/home/user/project/review-notes"
         permission: "write"

.. code-block:: bash

   # Run from project directory - recommended for coding
   cd /home/user/project
   uv tool run massgen "Review the authentication module for security issues and best practices"

   # Or with explicit config
   massgen \
     --config code_review.yaml \
     "Review the authentication module for security issues and best practices"

Documentation Generation
~~~~~~~~~~~~~~~~~~~~~~~~~

Agents read project code to understand context and generate/update documentation:

.. code-block:: yaml

   orchestrator:
     snapshot_storage: "snapshots"
     agent_temporary_workspace: "temp_workspaces"

     context_paths:
       - path: "/home/user/project/src"
         permission: "read"
       - path: "/home/user/project/docs"
         permission: "write"

.. code-block:: bash

   # Run from project directory - recommended for coding
   cd /home/user/project
   uv tool run massgen "Update the API documentation to reflect recent changes in the auth module"

   # Or with explicit config
   massgen \
     --config doc_generator.yaml \
     "Update the API documentation to reflect recent changes in the auth module"

Data Processing
~~~~~~~~~~~~~~~

Agents access shared datasets and generate analysis reports:

.. code-block:: yaml

   orchestrator:
     snapshot_storage: "snapshots"
     agent_temporary_workspace: "temp_workspaces"

     context_paths:
       - path: "/home/user/datasets"
         permission: "read"
       - path: "/home/user/reports"
         permission: "write"

.. code-block:: bash

   # Run from project directory - recommended
   cd /home/user
   uv tool run massgen "Analyze the Q4 sales data and create a comprehensive report with visualizations"

   # Or with explicit config
   massgen \
     --config data_analysis.yaml \
     "Analyze the Q4 sales data and create a comprehensive report with visualizations"

Project Migration
~~~~~~~~~~~~~~~~~

Agents examine existing projects and create modernized versions:

.. code-block:: yaml

   orchestrator:
     snapshot_storage: "snapshots"
     agent_temporary_workspace: "temp_workspaces"

     context_paths:
       - path: "/home/user/old-project"
         permission: "read"
       - path: "/home/user/new-project"
         permission: "write"

.. code-block:: bash

   # Run from project directory - recommended for coding
   cd /home/user/old-project
   uv tool run massgen "Migrate the Flask 1.x application to Flask 3.x with modern best practices"

   # Or with explicit config
   massgen \
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
     # Required for file operations
     snapshot_storage: "snapshots"
     agent_temporary_workspace: "temp"

     # Optional: session management for multi-turn conversations
     session_storage: "sessions"

     # Project integration - mix of directories and files
     context_paths:
       - path: "/Users/me/myproject/src"                  # Directory: analyze existing code
         permission: "read"
       - path: "/Users/me/myproject/pytest.ini"           # File: read test config (v0.0.26+)
         permission: "read"
       - path: "/Users/me/myproject/tests"                # Directory: generate tests
         permission: "write"
       - path: "/Users/me/myproject/docs"                 # Directory: update documentation
         permission: "write"

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

Protected Paths
---------------

Protected paths allow you to make specific files or directories **read-only** within writable context paths, preventing agents from modifying or deleting critical reference files while allowing them to edit other files.

.. note::

   **Use Case**: You want agents to modify some files in a directory but keep certain reference files, configurations, or templates untouched.

Basic Configuration
~~~~~~~~~~~~~~~~~~~

Protect specific files within a writable context path:

.. code-block:: yaml

   orchestrator:
     snapshot_storage: "snapshots"
     agent_temporary_workspace: "temp_workspaces"

     context_paths:
       - path: "/absolute/path/to/directory"
         permission: "write"
         protected_paths:
           - "important_file.txt"
           - "config.json"

**Result**:

* Agents can read and modify all files **except** ``important_file.txt`` and ``config.json``
* Protected files are readable but not writable

Protected Paths Syntax
~~~~~~~~~~~~~~~~~~~~~~~

Protected paths are **relative to the context path**:

.. code-block:: yaml

   orchestrator:
     context_paths:
       - path: "/Users/me/project"
         permission: "write"
         protected_paths:
           - "src/config.py"          # Protects /Users/me/project/src/config.py
           - "tests/fixtures/"        # Protects /Users/me/project/tests/fixtures/
           - "README.md"              # File protection
           - "docs/"                  # Directory protection

Common Use Cases
~~~~~~~~~~~~~~~~

**1. Protect Reference Files**: Keep test fixtures unchanged while agents modify code

.. code-block:: yaml

   context_paths:
     - path: "/project"
       permission: "write"
       protected_paths:
         - "tests/fixtures/"
         - "tests/expected_outputs/"

**2. Protect Configuration**: Allow code changes but prevent config modifications

.. code-block:: yaml

   context_paths:
     - path: "/app"
       permission: "write"
       protected_paths:
         - "config.yaml"
         - ".env.example"
         - "docker-compose.yml"

**3. Protect Templates**: Generate content without modifying templates

.. code-block:: yaml

   context_paths:
     - path: "/website"
       permission: "write"
       protected_paths:
         - "templates/"
         - "layouts/"

**4. Mixed Permissions**: Different protection levels across context paths

.. code-block:: yaml

   context_paths:
     # Source code - most files writable, some protected
     - path: "/project/src"
       permission: "write"
       protected_paths:
         - "core/constants.py"
         - "version.py"

     # Docs - completely read-only (no protected_paths needed)
     - path: "/project/docs"
       permission: "read"

     # Temp folder - fully writable
     - path: "/project/temp"
       permission: "write"

How Protection Works
~~~~~~~~~~~~~~~~~~~~

Protected paths are enforced by the ``PathPermissionManager``:

1. **Startup validation**: Checks that protected paths exist within their context path
2. **Runtime enforcement**: Blocks write/delete operations on protected paths
3. **Clear error messages**: Agents receive descriptive errors when blocked

.. code-block:: text

   Agent: Edit /project/config.json
   Error: Cannot modify /project/config.json - path is protected

**Read Operations**: Agents can always read protected files for reference:

.. code-block:: python

   Agent: Read config.json        # ✅ Allowed
   Agent: Edit config.json         # ❌ Blocked
   Agent: Delete config.json       # ❌ Blocked

**Directory Protection**: Protecting a directory protects all contents recursively:

.. code-block:: text

   protected_paths: ["tests/fixtures/"]

   ✅ Read tests/fixtures/data.json
   ❌ Write tests/fixtures/data.json
   ❌ Delete tests/fixtures/
   ❌ Create tests/fixtures/new_file.txt

Best Practices
~~~~~~~~~~~~~~

1. **Be explicit**: List all critical files rather than assuming default protection
2. **Test first**: Run with a test directory to verify protection works
3. **Document**: Add comments explaining why files are protected

   .. code-block:: yaml

      protected_paths:
        - "schema.sql"        # Database schema - don't modify structure
        - "LICENSE"           # Legal file - must not change

4. **Use read-only when appropriate**: If entire directory should be read-only, use ``permission: "read"`` instead of protecting all paths

   .. code-block:: yaml

      # If everything should be read-only:
      - path: "/reference_docs"
        permission: "read"     # Simpler than listing all files

      # If you want selective protection:
      - path: "/working_dir"
        permission: "write"
        protected_paths: [...]  # Mixed permissions

5. **Combine with planning mode**: Use protected paths with planning mode for maximum safety

   .. code-block:: yaml

      orchestrator:
        context_paths:
          - path: "/project"
            permission: "write"
            protected_paths: ["config.json"]
        coordination:
          enable_planning_mode: true  # Prevents modifications during coordination

Troubleshooting
~~~~~~~~~~~~~~~

**Problem**: Agent is modifying a file you marked as protected.

**Check**:

1. **Verify relative path is correct**:

   .. code-block:: yaml

      context_paths:
        - path: "/Users/me/project"
          protected_paths:
            - "config.json"         # ✅ Relative to /Users/me/project
            # NOT: "/Users/me/project/config.json"  # ❌ Would be treated as relative

2. **Check the file exists**: Protected paths must exist when MassGen starts
3. **Verify write permission**: Protection only applies to writable context paths

**Problem**: "Protected path 'file.txt' not found"

**Solution**: Ensure the file exists before starting MassGen:

.. code-block:: bash

   ls /project/file.txt  # Check if file exists

Security Note
~~~~~~~~~~~~~

.. warning::

   Protected paths are a **convenience feature**, not a security boundary. For security-critical files:

   * Use file system permissions (chmod)
   * Run MassGen with limited user accounts
   * Store sensitive data outside agent-accessible directories
   * Review all agent operations before deploying

Next Steps
----------

* :doc:`file_operations` - Learn more about workspace management and file operation safety
* :doc:`mcp_integration` - Additional tools for project work
* :doc:`planning_mode` - Combine with planning mode for safer coordination
* :doc:`multi_turn_mode` - Iterative project development across turns
* :doc:`../quickstart/running-massgen` - More examples
