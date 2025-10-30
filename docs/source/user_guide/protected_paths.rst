:orphan:

Protected Paths
===============

Protected paths allow you to make specific files or directories **read-only** within writable context paths, preventing agents from modifying or deleting critical reference files while allowing them to edit other files.

.. note::

   **Use Case**: You want agents to modify some files in a directory but keep certain reference files, configurations, or templates untouched.

Quick Start
-----------

**Protect a single file:**

.. code-block:: yaml

   orchestrator:
     context_paths:
       - path: "/path/to/project"
         permission: "write"
         protected_paths:
           - "config.json"  # Agents can read but not modify

**Example usage:**

.. code-block:: bash

   massgen \
     --config @examples/tools/filesystem/gemini_gpt5nano_protected_paths.yaml \
     "Review the HTML and CSS files, then improve the styling"

What Are Protected Paths?
--------------------------

Protected paths are files or directories within a **writable** context path that are explicitly marked as read-only. Agents can:

* ✅ **Read** protected files for reference
* ✅ **Write/Edit** non-protected files in the same directory
* ❌ **Modify or Delete** protected files

This gives you fine-grained control over what agents can change.

Why Use Protected Paths?
~~~~~~~~~~~~~~~~~~~~~~~~~

**Without protected paths:**

.. code-block:: text

   ❌ Context path: /project (write permission)
      → Agents can modify ALL files including critical configs

**With protected paths:**

.. code-block:: text

   ✅ Context path: /project (write permission)
      ├── config.json (protected - read only)
      ├── template.html (protected - read only)
      └── styles.css (writable)
      → Agents can only modify styles.css

Configuration
-------------

Basic Configuration
~~~~~~~~~~~~~~~~~~~

Protect specific files within a writable context path:

.. code-block:: yaml

   orchestrator:
     context_paths:
       - path: "/absolute/path/to/directory"
         permission: "write"
         protected_paths:
           - "important_file.txt"
           - "config.json"

**Result**:

* Agents can read and modify all files **except** ``important_file.txt`` and ``config.json``
* Protected files are readable but not writable

Multiple Protected Paths
~~~~~~~~~~~~~~~~~~~~~~~~~

Protect multiple files or directories:

.. code-block:: yaml

   orchestrator:
     context_paths:
       - path: "/project"
         permission: "write"
         protected_paths:
           - "README.md"              # File protection
           - "docs/"                  # Directory protection
           - ".github/workflows/"     # Protect CI/CD configs
           - "package.json"           # Protect dependencies

Relative Path Syntax
~~~~~~~~~~~~~~~~~~~~

Protected paths are **relative to the context path**:

.. code-block:: yaml

   orchestrator:
     context_paths:
       - path: "/Users/me/project"
         permission: "write"
         protected_paths:
           - "src/config.py"          # Protects /Users/me/project/src/config.py
           - "tests/fixtures/"        # Protects /Users/me/project/tests/fixtures/

Complete Example
~~~~~~~~~~~~~~~~

Realistic configuration for a web project:

.. code-block:: yaml

   agents:
     - id: "frontend_agent"
       backend:
         type: "claude_code"
         cwd: "workspace"

     - id: "reviewer_agent"
       backend:
         type: "gemini"
         model: "gemini-2.5-flash"

   orchestrator:
     snapshot_storage: "snapshots"
     agent_temporary_workspace: "temp_workspaces"
     context_paths:
       - path: "/Users/me/website"
         permission: "write"
         protected_paths:
           - "index.html"           # Keep original structure
           - "assets/logo.png"      # Don't modify brand assets
           - ".git/"                # Never touch version control
           # styles.css is NOT protected - agents can modify it

   ui:
     display_type: "rich_terminal"

**Usage**:

.. code-block:: bash

   massgen \
     --config website_config.yaml \
     "Improve the CSS styling while keeping the HTML structure intact"

**Result**:

* ✅ Agents can read ``index.html`` for structure understanding
* ✅ Agents can freely modify ``styles.css``
* ❌ Agents cannot change ``index.html`` or ``assets/logo.png``

Use Cases
---------

Use Case 1: Protect Reference Files
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Scenario**: Let agents improve code while keeping test fixtures unchanged.

.. code-block:: yaml

   context_paths:
     - path: "/project"
       permission: "write"
       protected_paths:
         - "tests/fixtures/"
         - "tests/expected_outputs/"

**Task**: "Refactor the parser module to improve performance"

**Result**: Agents can modify parser code but test fixtures remain untouched for validation.

Use Case 2: Protect Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Scenario**: Allow code changes but prevent config file modifications.

.. code-block:: yaml

   context_paths:
     - path: "/app"
       permission: "write"
       protected_paths:
         - "config.yaml"
         - ".env.example"
         - "docker-compose.yml"

**Task**: "Add error handling to the API endpoints"

**Result**: Agents improve code without accidentally changing deployment configs.

Use Case 3: Protect Templates
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Scenario**: Let agents generate content based on templates without modifying the templates.

.. code-block:: yaml

   context_paths:
     - path: "/website"
       permission: "write"
       protected_paths:
         - "templates/"
         - "layouts/"

**Task**: "Generate blog posts using the templates"

**Result**: Agents create new content files without touching template structure.

Use Case 4: Protect Documentation Structure
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Scenario**: Allow content updates but preserve documentation organization.

.. code-block:: yaml

   context_paths:
     - path: "/docs"
       permission: "write"
       protected_paths:
         - "index.md"              # Keep main page structure
         - "_sidebar.md"           # Preserve navigation
         - "_config.yml"           # Don't change doc settings

**Task**: "Update the API reference documentation"

**Result**: Agents update specific doc pages without reorganizing the documentation structure.

Use Case 5: Mixed Permissions
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Scenario**: Multiple context paths with different protection levels.

.. code-block:: yaml

   context_paths:
     # Source code - most files writable, some protected
     - path: "/project/src"
       permission: "write"
       protected_paths:
         - "core/constants.py"
         - "version.py"

     # Docs - completely read-only (no protected_paths needed, just use "read")
     - path: "/project/docs"
       permission: "read"

     # Temp folder - fully writable (no protected_paths)
     - path: "/project/temp"
       permission: "write"

How It Works
------------

Permission Enforcement
~~~~~~~~~~~~~~~~~~~~~~

Protected paths are enforced by the ``PathPermissionManager``:

1. **Startup validation**: Checks that protected paths exist within their context path
2. **Runtime enforcement**: Blocks write/delete operations on protected paths
3. **Clear error messages**: Agents receive descriptive errors when blocked

.. code-block:: text

   Agent: Edit /project/config.json
   Error: Cannot modify /project/config.json - path is protected

Read Operations
~~~~~~~~~~~~~~~

Agents can always read protected files:

.. code-block:: python

   Agent: Read config.json        # ✅ Allowed
   Agent: Edit config.json         # ❌ Blocked
   Agent: Delete config.json       # ❌ Blocked

This allows agents to use protected files as reference material.

Directory Protection
~~~~~~~~~~~~~~~~~~~~

Protecting a directory protects all contents recursively:

.. code-block:: yaml

   protected_paths:
     - "tests/fixtures/"  # Protects all files inside

.. code-block:: text

   ✅ Read tests/fixtures/data.json
   ❌ Write tests/fixtures/data.json
   ❌ Delete tests/fixtures/
   ❌ Create tests/fixtures/new_file.txt

Interaction with File Operation Safety
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Protected paths work alongside read-before-delete enforcement:

1. **Protected files**: Cannot be deleted even if read first
2. **Non-protected files**: Follow standard read-before-delete rules
3. **Agent-created files**: Can be deleted (not affected by protection)

Interactive Mode
----------------

In interactive mode, you can add protected paths when prompted:

.. code-block:: text

   📂 Context Paths:
      No context paths configured

   ❓ Add current directory as context path?
      /Users/me/project
      [Y]es (default) / [P]rotected / [N]o / [C]ustom path: P

   Enter protected paths (relative to context path), one per line. Empty line to finish:
      → config.json
      → .env
      → tests/fixtures/
      →

   ✓ Added /Users/me/project (write)
     🔒 config.json
     🔒 .env
     🔒 tests/fixtures/

Advanced Patterns
-----------------

Pattern Matching (Future Enhancement)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. note::

   Currently, protected paths must be explicit file or directory names. Pattern matching (e.g., ``*.json``) is not yet supported but planned for future releases.

Current workaround - list files explicitly:

.. code-block:: yaml

   protected_paths:
     - "config.json"
     - "secrets.json"
     - "settings.json"

Nested Protection
~~~~~~~~~~~~~~~~~

You can have multiple levels of protection:

.. code-block:: yaml

   context_paths:
     # Parent directory mostly writable
     - path: "/project"
       permission: "write"
       protected_paths:
         - "src/core/"              # Protect entire core module

     # More specific protection for subdirectory
     - path: "/project/src"
       permission: "write"
       protected_paths:
         - "utils/constants.py"     # Additional specific protection

Troubleshooting
---------------

Protected Path Not Working
~~~~~~~~~~~~~~~~~~~~~~~~~~

**Problem**: Agent is modifying a file you marked as protected.

**Check**:

1. **Verify relative path is correct**:

   .. code-block:: yaml

      context_paths:
        - path: "/Users/me/project"
          protected_paths:
            - "config.json"         # ✅ Relative to /Users/me/project
            # NOT: "/Users/me/project/config.json"  # ❌ Would be treated as relative

2. **Check the file exists**:

   Protected paths must exist when MassGen starts. Check logs for validation errors.

3. **Verify the context path permission**:

   .. code-block:: yaml

      permission: "write"  # Required - protection only applies to writable paths

Path Not Found Error
~~~~~~~~~~~~~~~~~~~~

**Problem**: "Protected path 'file.txt' not found in context path '/project'"

**Solution**: Ensure the protected path exists before starting MassGen:

.. code-block:: bash

   # Check if file exists
   ls /project/file.txt

   # If missing, either:
   # 1. Create the file first, or
   # 2. Remove it from protected_paths

Agent Still Modifying Files
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Problem**: Agent bypasses protection during coordination.

**Check**:

1. **Ensure you're using during final presentation**: Protection applies to all phases, but ensure agent is using the right context path

2. **Check file is within context path**: Protection only works for files within the specified context path

3. **Review logs**: Check ``massgen_debug.log`` for permission checks

Best Practices
--------------

1. **Be explicit about what to protect**: List all critical files rather than assuming default protection

2. **Test first**: Run with a test directory to verify protection works as expected

3. **Document in comments**: Add comments to your config explaining why files are protected

   .. code-block:: yaml

      protected_paths:
        - "schema.sql"        # Database schema - don't let agents modify structure
        - "LICENSE"           # Legal file - must not change

4. **Use read-only permission when appropriate**: If the entire directory should be read-only, use ``permission: "read"`` instead of protecting all paths

   .. code-block:: yaml

      # If you want everything read-only:
      - path: "/reference_docs"
        permission: "read"     # ← Simpler than listing all files as protected

      # If you want selective protection:
      - path: "/working_dir"
        permission: "write"
        protected_paths: [...]  # ← Use this for mixed permissions

5. **Combine with planning mode**: Use protected paths alongside planning mode for maximum safety

   .. code-block:: yaml

      orchestrator:
        context_paths:
          - path: "/project"
            permission: "write"
            protected_paths: ["config.json"]
        coordination:
          enable_planning_mode: true  # Prevents accidental modifications during coordination

Binary File Protection
----------------------

MassGen automatically prevents agents from using text-based read tools on binary files, directing them to use appropriate specialized tools instead.

What's Protected
~~~~~~~~~~~~~~~~

Text-based read tools (``read_file``, ``find_and_read_text``, ``grep``) are automatically blocked from accessing 40+ binary file types:

**Images**:
  ``.jpg``, ``.jpeg``, ``.png``, ``.gif``, ``.bmp``, ``.svg``, ``.webp``, ``.tiff``

**Videos**:
  ``.mp4``, ``.avi``, ``.mov``, ``.mkv``, ``.flv``, ``.wmv``, ``.webm``, ``.mpg``

**Audio**:
  ``.mp3``, ``.wav``, ``.ogg``, ``.flac``, ``.aac``, ``.m4a``, ``.wma``

**Archives**:
  ``.zip``, ``.tar``, ``.gz``, ``.7z``, ``.rar``

**Documents**:
  ``.pdf``, ``.docx``, ``.xlsx``, ``.pptx`` (use ``understand_file`` tool)

**Executables**:
  ``.exe``, ``.bin``, ``.dll``, ``.so``, ``.dylib``, ``.pyc``

How It Works
~~~~~~~~~~~~

When an agent attempts to read a binary file with a text tool, they receive a helpful error message:

.. code-block:: text

   Cannot read image file 'screenshot.png' with text-based tool 'read_file'.
   Please use 'understand_image' tool for image files.

.. code-block:: text

   Cannot read video file 'demo.mp4' with text-based tool 'grep'.
   Please use 'understand_video' tool for video files.

The error messages automatically suggest the correct tool for each file type:

* **Images** → ``understand_image``
* **Videos** → ``understand_video``
* **Audio** → ``understand_audio``
* **PDF/Office docs** → ``understand_file``
* **Archives** → Extract first, then read contents

Benefits
~~~~~~~~

1. **Prevents Confusion**: Agents can't accidentally try to read binary data as text
2. **Better Tool Usage**: Guides agents to use appropriate multimodal tools
3. **Clearer Errors**: Actionable error messages instead of garbled binary output
4. **No Configuration Needed**: Works automatically for all agents

Security Considerations
-----------------------

.. warning::

   Protected paths are a **convenience feature**, not a security boundary. They prevent accidental modifications but shouldn't be relied upon for security-critical files.

**For security-sensitive files:**

* Use file system permissions (chmod)
* Run MassGen with limited user accounts
* Store sensitive data outside agent-accessible directories
* Use read-only context paths instead of protected paths
* Review all agent operations before deploying

**Binary file protection** is also a convenience feature that guides agents to use correct tools, not a security boundary.

Related Features
----------------

* :doc:`file_operations` - File operation safety and read-before-delete enforcement
* :doc:`project_integration` - Context paths and permission system
* :doc:`planning_mode` - Prevent modifications during coordination
* :doc:`../reference/yaml_schema` - Complete YAML configuration reference

Next Steps
----------

* :doc:`project_integration` - Learn about context paths and permissions
* :doc:`file_operations` - Understand file operation safety features
* :doc:`planning_mode` - Combine with planning mode for extra safety
