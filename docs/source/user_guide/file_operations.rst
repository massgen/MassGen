File Operations & Workspace Management
=======================================

MassGen provides comprehensive file system support, enabling agents to read, write, and manipulate files in organized, isolated workspaces.

Quick Start
-----------

**Single agent with file operations (using uv tool - recommended for coding):**

.. code-block:: bash

   # Run from your project directory
   cd /path/to/your-project
   uv tool run massgen "Create a Python web scraper and save results to CSV"

**Or with explicit config:**

.. code-block:: bash

   massgen \
     --config @examples/tools/filesystem/claude_code_single.yaml \
     "Create a Python web scraper and save results to CSV"

**Multi-agent file collaboration:**

.. code-block:: bash

   massgen \
     --config @examples/tools/filesystem/claude_code_context_sharing.yaml \
     "Generate a comprehensive project report with charts and analysis"

.. warning::

   **Model Selection for Filesystem Operations**

   We **do not recommend** using weaker models like GPT-4o or GPT-4.1 for filesystem operations. These models do not handle file operations reliably and may produce unexpected behavior.

   **Recommended models:**

   * Claude Sonnet 4/4.5
   * GPT-5
   * Gemini 2.5 Pro
   * Grok 4
   * Other frontier models with strong tool-calling capabilities

   Weaker models may struggle with complex file operations, error handling, and workspace management.

Configuration
-------------

Basic Workspace Setup
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: yaml

   agents:
     - id: "file-agent"
       backend:
         type: "claude_code"        # Backend with file support
         model: "claude-sonnet-4"   # Your model choice
         cwd: "workspace"           # Isolated workspace for file operations

   orchestrator:
     snapshot_storage: "snapshots"                 # Shared snapshots directory
     agent_temporary_workspace: "temp_workspaces"  # Temporary workspace management

Multi-Agent Workspace Isolation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Each agent gets its own isolated workspace:

.. code-block:: yaml

   agents:
     - id: "analyzer"
       backend:
         type: "claude_code"
         cwd: "workspace1"      # Agent-specific workspace

     - id: "reviewer"
       backend:
         type: "gemini"
         cwd: "workspace2"      # Separate workspace

This ensures agents don't interfere with each other's files during coordination.

Configuration Parameters
~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - Parameter
     - Required
     - Description
   * - ``cwd``
     - Yes
     - Working directory for file operations (agent-specific workspace)
   * - ``snapshot_storage``
     - Yes
     - Directory for workspace snapshots (shared between agents)
   * - ``agent_temporary_workspace``
     - Yes
     - Parent directory for temporary workspaces

Available File Operations
-------------------------

Claude Code Backend
~~~~~~~~~~~~~~~~~~~

Claude Code has built-in file operation tools:

* **Read** - Read file contents
* **Write** - Create or overwrite files
* **Edit** - Make targeted edits to existing files
* **MultiEdit** - Edit multiple locations in one file
* **Bash** - Execute shell commands (including file operations)
* **Grep** - Search file contents with regex
* **Glob** - Find files matching patterns
* **LS** - List directory contents

**Example:**

.. code-block:: bash

   massgen \
     --backend claude_code \
     --model sonnet \
     "Create a Python project with src/, tests/, and docs/ directories"

MCP Filesystem Server
~~~~~~~~~~~~~~~~~~~~~

All backends can use the MCP Filesystem Server for file operations:

.. code-block:: yaml

   agents:
     - id: "gemini_agent"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
         mcp_servers:
           - name: "filesystem"
             type: "stdio"
             command: "npx"
             args: ["-y", "@modelcontextprotocol/server-filesystem", "."]

**MCP Filesystem Operations:**

* ``read_file`` - Read file contents
* ``write_file`` - Write or create files
* ``create_directory`` - Create directories
* ``list_directory`` - List directory contents
* ``delete_file`` - Delete files (with safety checks)
* ``move_file`` - Move or rename files

MassGen Workspace Tools
~~~~~~~~~~~~~~~~~~~~~~~

MassGen provides additional workspace management tools via the Workspace Tools MCP Server:

.. code-block:: yaml

   agents:
     - id: "advanced_agent"
       backend:
         type: "claude"
         model: "claude-sonnet-4"
         mcp_servers:
           - name: "workspace_tools"
             type: "stdio"
             command: "uv"
             args: ["run", "python", "-m", "massgen.filesystem_manager._workspace_tools_server"]

**File Operations:**

* ``copy_file`` - Copy single file/directory from any accessible path to workspace
* ``copy_files_batch`` - Copy multiple files with pattern matching and exclusions
* ``delete_file`` - Delete single file/directory from workspace
* ``delete_files_batch`` - Delete multiple files with pattern matching

**Directory Analysis:**

* ``compare_directories`` - Compare two directories and show differences
* ``compare_files`` - Compare two text files and show unified diff

**Image Generation** (requires OpenAI API key):

* ``generate_and_store_image_with_input_images`` - Create variations of existing images using gpt-4.1
* ``generate_and_store_image_no_input_images`` - Generate new images from text prompts using gpt-4.1

**Example - Workspace cleanup with batch operations:**

.. code-block:: text

   You: Copy all Python files from the previous turn's output
   [Agent uses copy_files_batch with include_patterns: ["*.py"]]

   You: Delete all temporary files
   [Agent uses delete_files_batch with include_patterns: ["*.tmp", "*.temp"]]

   You: Compare my workspace with the reference implementation
   [Agent uses compare_directories to show differences]

Workspace Management
--------------------

Workspace Isolation
~~~~~~~~~~~~~~~~~~~

Each agent's ``cwd`` is fully isolated:

* Agents can freely read/write within their workspace
* No risk of conflicting file operations
* Clean separation of work products

**Directory structure:**

.. code-block:: text

   .massgen/
   └── workspaces/
       ├── workspace1/     # Agent 1's isolated workspace
       │   ├── file1.py
       │   └── output.txt
       └── workspace2/     # Agent 2's isolated workspace
           ├── analysis.md
           └── data.csv

Snapshot Storage
~~~~~~~~~~~~~~~~

Workspace snapshots enable context sharing between agents:

* Winning agent's workspace is saved as snapshot
* Future coordination rounds can access previous results
* Enables building on past work

**How it works:**

1. Agent completes initial answer → Workspace snapshotted
2. Coordination phase → Agents can reference snapshot
3. Final agent selected → Can build on snapshot content

Temporary Workspaces
~~~~~~~~~~~~~~~~~~~~

Previous turn results available via temporary workspaces:

* Multi-turn sessions preserve context
* Agents can access files from earlier turns
* Organized by turn number

.. code-block:: text

   .massgen/
   └── temp_workspaces/
       ├── turn_1/
       │   └── agent1/
       │       └── previous_output.txt
       └── turn_2/
           └── agent2/
               └── refined_output.txt

File Operation Safety
---------------------

Read-Before-Delete Enforcement
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

MassGen prevents accidental file deletion with ``FileOperationTracker``:

**Safety Rules:**

1. Agents **must read a file before deleting it**
2. Exception: Agent-created files can be deleted without reading
3. Directory deletion requires validation
4. Clear error messages when operations blocked

**Example:**

.. code-block:: python

   # This will FAIL - file not read first
   Agent: Delete config.json
   Error: Cannot delete config.json - file has not been read

   # This will SUCCEED - file read first
   Agent: Read config.json
   Agent: Delete config.json
   Success: File deleted

Created File Exemption
~~~~~~~~~~~~~~~~~~~~~~

Files created by an agent can be freely deleted:

.. code-block:: python

   Agent: Write new_file.txt "content"
   Agent: Delete new_file.txt  # Allowed - agent created it

This allows agents to clean up their own temporary files.

PathPermissionManager
~~~~~~~~~~~~~~~~~~~~~

Integrated operation tracking:

* ``track_read_operation()`` - Records file reads
* ``track_write_operation()`` - Records file writes
* ``track_delete_operation()`` - Validates and records deletions
* Enhanced delete validation for files and batch operations

Protected Paths
~~~~~~~~~~~~~~~

Protected paths allow you to make specific files or directories **read-only** within writable context paths, preventing agents from modifying or deleting critical reference files while allowing them to edit other files.

**Use Case**: You want agents to modify some files in a directory but keep certain reference files, configurations, or templates untouched.

**Configuration Example:**

.. code-block:: yaml

   orchestrator:
     snapshot_storage: "snapshots"
     agent_temporary_workspace: "temp_workspaces"

     context_paths:
       - path: "/path/to/project"
         permission: "write"
         protected_paths:
           - "config.json"      # Read-only
           - "template.html"    # Read-only
           - "tests/fixtures/"  # Entire directory read-only

**What Agents Can Do:**

* ✅ **Read** protected files for reference
* ✅ **Write/Edit** non-protected files in the same directory
* ❌ **Modify or Delete** protected files

**Common Use Cases:**

1. **Protect Reference Files**: Keep test fixtures unchanged while agents modify code
2. **Protect Configuration**: Allow code changes but prevent config modifications
3. **Protect Templates**: Let agents generate content without modifying templates
4. **Protect Documentation Structure**: Allow content updates but preserve organization

For complete protected paths documentation including examples, troubleshooting, and best practices, see the **Protected Paths** section in :doc:`project_integration`.

Security Considerations
-----------------------

.. warning::

   **Agents can autonomously read, write, modify, and delete files** within their permitted directories.

Before running MassGen with filesystem access:

* ✅ Only grant access to directories you're comfortable with agents modifying
* ✅ Use permission system to restrict write access where needed
* ✅ Use protected paths for critical files within writable directories
* ✅ Test in an isolated directory first
* ✅ Back up important files before granting write access
* ✅ Review ``context_paths`` configuration carefully

The agents will execute file operations **without additional confirmation** once permissions are granted.

File Access Control
~~~~~~~~~~~~~~~~~~~

Use MCP server configurations to restrict access:

.. code-block:: yaml

   mcp_servers:
     - name: "filesystem"
       type: "stdio"
       command: "npx"
       args: ["-y", "@modelcontextprotocol/server-filesystem", "/safe/directory"]
       security:
         level: "high"

Workspace Organization
----------------------

Clean Project Structure
~~~~~~~~~~~~~~~~~~~~~~~

All MassGen state organized under ``.massgen/``:

.. code-block:: text

   your-project/
   ├── .massgen/                    # All MassGen state
   │   ├── sessions/                # Multi-turn conversation history
   │   ├── workspaces/              # Agent working directories
   │   ├── snapshots/               # Workspace snapshots
   │   └── temp_workspaces/         # Previous turn results
   ├── src/                         # Your project files
   └── docs/                        # Your documentation

**Benefits:**

* Clean projects - all MassGen files in one place
* Easy ``.gitignore`` - just add ``.massgen/``
* Portable - delete ``.massgen/`` without affecting project
* Multi-turn sessions preserved

Configuration Auto-Organization
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

MassGen automatically organizes under ``.massgen/``:

.. code-block:: yaml

   orchestrator:
     snapshot_storage: "snapshots"         # → .massgen/snapshots/
     session_storage: "sessions"           # → .massgen/sessions/
     agent_temporary_workspace: "temp"     # → .massgen/temp/

   agents:
     - backend:
         cwd: "workspace1"                 # → .massgen/workspaces/workspace1/

Example: Multi-Agent Document Processing
-----------------------------------------

.. code-block:: yaml

   agents:
     - id: "analyzer"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"
         cwd: "analyzer_workspace"
         mcp_servers:
           - name: "filesystem"
             type: "stdio"
             command: "npx"
             args: ["-y", "@modelcontextprotocol/server-filesystem", "."]

     - id: "writer"
       backend:
         type: "claude_code"
         cwd: "writer_workspace"

   orchestrator:
     snapshot_storage: "snapshots"
     agent_temporary_workspace: "temp"

**Usage:**

.. code-block:: bash

   massgen \
     --config document_processing.yaml \
     "Analyze data.csv and create a comprehensive report with visualizations"

**What happens:**

1. **Analyzer** reads data.csv, creates analysis in its workspace
2. **Writer** sees analyzer's snapshot, creates report with charts
3. Final output in winner's workspace, snapshot saved for future reference

Advanced Topics
---------------

.. toctree::
   :maxdepth: 1

   project_integration
   code_execution

The sections above cover basic file operations and workspace management. For advanced features, see:

* :doc:`project_integration` - Work with your existing codebase using context paths with file-level and directory-level access control, plus protected paths for fine-grained permission control
* :doc:`code_execution` - Execute bash commands and scripts with MCP-based code execution, supporting both local and Docker isolation modes

Next Steps
----------

* :doc:`code_execution` - Execute commands and scripts with local or Docker isolation
* :doc:`mcp_integration` - Additional MCP tools beyond filesystem
* :doc:`multi_turn_mode` - File operations across multiple conversation turns
* :doc:`../quickstart/running-massgen` - More examples
