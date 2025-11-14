.. _user_guide_skills:

==========================
Skills System
==========================

The Skills System extends agent capabilities with specialized knowledge and workflows using `openskills <https://github.com/numman-ali/openskills>`_. Skills are modular, self-contained packages that provide domain-specific guidance and tools.

Overview
========

Skills transform agents from general-purpose to specialized agents with:

* **Domain Knowledge**: Specialized expertise (e.g., PDF manipulation, spreadsheet analysis)
* **Workflow Guidance**: Step-by-step procedures for complex tasks
* **Tool Integration**: Pre-configured toolchains for specific domains
* **Filesystem-Based**: Transparent, version-controllable approach

When enabled, agents can invoke skills via bash commands to access domain-specific guidance.

.. note::
   Skills complement MCP tools but work via filesystem instead of MCP protocol. This provides better transparency and allows skills to be version-controlled.

Installation
============

Install openskills and Anthropic's skills collection:

.. code-block:: bash

   # Install openskills CLI
   npm install -g openskills

   # Install Anthropic's skills collection
   openskills install anthropics/skills --universal -y

This creates ``.agent/skills/`` directory with all available skills.

.. important::
   Skills currently require Docker mode (``command_line_execution_mode: "docker"``). Local mode is not yet supported.

.. note::
   The Docker images include ripgrep and ast-grep for file search capabilities used by the built-in file search skill.

Configuration
=============

Basic Configuration
-------------------

Enable skills in your YAML config:

.. code-block:: yaml

   agents:
     Agent1:
       backend_name: "Anthropic"
       backend_params:
         model: "claude-sonnet-4"
         # REQUIRED: Skills need command line access
         enable_mcp_command_line: true
         command_line_execution_mode: "docker"  # or "local"

   orchestrator:
     coordination:
       # Enable skills system
       use_skills: true

       # Optional: Skills directory (default: .agent/skills)
       skills_directory: ".agent/skills"

.. important::
   **Skills require command line execution** (``enable_mcp_command_line: true``) to be enabled for at least one agent.

With Task Planning
------------------

Combine skills with task planning:

.. code-block:: yaml

   orchestrator:
     coordination:
       use_skills: true
       enable_agent_task_planning: true

Organized Workspace
-------------------

For cleaner organization, enable structured workspace:

.. code-block:: yaml

   orchestrator:
     coordination:
       use_skills: true
       organize_workspace: true  # Creates memory/ and workspace/ dirs

This creates:

.. code-block:: text

   agent_workspace/
     ├── memory/              # Long-term context (memory skill)
     └── workspace/           # Main working directory

Built-in Skills
===============

MassGen includes three built-in skills automatically available when ``use_skills: true``:

Memory Skill
------------

Filesystem-based memory for storing context across turns.

**Usage:**

.. code-block:: bash

   # Save memory
   echo "User prefers JSON format" > memory/preferences.txt

   # Load memory
   cat memory/context.txt

   # View another agent's memories
   # (Path shown in system prompt as "Shared Reference", typically temp_workspaces/)
   cat temp_workspaces/agent1/memory/decisions.json

**Best for:**

* Storing user preferences
* Saving important decisions
* Maintaining context across multi-turn conversations

File Search Skill
-----------------

Fast text and structural code search using ripgrep and ast-grep.

**Usage:**

.. code-block:: bash

   # Text search with ripgrep
   rg "function.*login" --type py

   # Structural search with ast-grep
   sg --pattern 'class $NAME { $$$ }'

**Best for:**

* Finding code patterns
* Analyzing codebases
* Refactoring workflows

External Skills
===============

Anthropic Skills Collection
----------------------------

When you install ``anthropics/skills``, you get access to:

* **pdf**: PDF manipulation toolkit
* **xlsx**: Spreadsheet creation and analysis
* **pptx**: PowerPoint presentation generation
* **docx**: Word document processing
* **skill-creator**: Guide for creating custom skills
* **And more...**

Using External Skills
---------------------

1. **Discover available skills:**

   Agents see skills listed in their system prompt automatically.

2. **Invoke a skill:**

   .. code-block:: bash

      openskills read pdf

   This loads the PDF skill's guidance and instructions.

3. **Follow skill guidance:**

   The skill content provides step-by-step instructions, examples, and best practices.

Creating Custom Skills
----------------------

Follow the ``skill-creator`` skill guidance:

.. code-block:: bash

   openskills read skill-creator

Or create manually:

1. Create skill directory:

   .. code-block:: bash

      mkdir .agent/skills/my-skill

2. Create ``SKILL.md`` with YAML frontmatter:

   .. code-block:: markdown

      ---
      name: my-skill
      description: Brief description of what this skill does
      ---

      # My Skill

      Detailed guidance and instructions...

3. Skill is automatically discovered when ``use_skills: true``

How Skills Work
===============

Discovery
---------

When ``use_skills: true``:

1. MassGen scans ``.agent/skills/`` (external) and ``massgen/skills/`` (built-in)
2. Parses ``SKILL.md`` files for metadata
3. Builds skills table in agent system prompt

Skills Table
------------

Agents see available skills in their system prompt:

.. code-block:: xml

   <skills_system priority="1">

   ## Available Skills

   <available_skills>

   <skill>
   <name>pdf</name>
   <description>PDF manipulation toolkit...</description>
   <location>project</location>
   </skill>

   <skill>
   <name>memory</name>
   <description>Filesystem-based memory operations...</description>
   <location>builtin</location>
   </skill>

   </available_skills>

   </skills_system>

Invocation
----------

Agents invoke skills using bash:

.. code-block:: bash

   openskills read <skill-name>

This loads the skill's full content and guidance.

Best Practices
==============

When to Use Skills
------------------

**Use skills when:**

* Task requires domain-specific knowledge
* Workflow is complex and benefits from guidance
* Want transparency (filesystem > MCP state)
* Multiple agents need to coordinate

**Don't use skills when:**

* Simple, one-off tasks
* MCP tools are sufficient
* Command line execution not available

Skill Selection
---------------

1. **Check available skills** in the system prompt first
2. **Read skill content** before using
3. **Follow skill guidance** - they provide best practices
4. **Don't mix approaches** - if using a skill, follow its patterns

Memory Management
-----------------

1. **Be selective** - only save important information
2. **Use clear names** - descriptive filenames
3. **Structured data** - JSON for data, Markdown for docs
4. **Clean up** - remove outdated memories

File Searching
--------------

1. **Start broad** - simple patterns first
2. **Add filters** - use file type and directory filters
3. **Use context** - ``-C`` flag shows surrounding code
4. **Combine tools** - ripgrep for text, ast-grep for structure

Troubleshooting
===============

Skills Not Found
----------------

**Error:** ``Skills directory is empty or doesn't exist``

**Solution:**

.. code-block:: bash

   # Local users: Install openskills
   npm install -g openskills
   openskills install anthropics/skills --universal -y

   # Docker users: Skills should be pre-installed
   # If missing, rebuild Docker image

Command Execution Required
---------------------------

**Error:** ``Skills require command line execution``

**Solution:**

Add to agent config:

.. code-block:: yaml

   agents:
     Agent1:
       backend_params:
         enable_mcp_command_line: true
         command_line_execution_mode: "docker"  # or "local"

Skill Not Appearing
-------------------

**Problem:** Installed skill not showing in skills table

**Solutions:**

1. Check skills directory path in config
2. Verify ``SKILL.md`` has YAML frontmatter
3. Check file permissions
4. Try ``openskills list`` to see installed skills

Performance Considerations
==========================

Skill Discovery Cost
--------------------

* Skills are scanned once at orchestration startup
* Minimal overhead for small skill collections
* For 50+ skills, consider using specific skills directory

System Prompt Size
------------------

* Skills table adds to system prompt length
* ~100 tokens per skill in the table
* Full skill content loaded on-demand via ``openskills read``

Integration with Other Features
================================

With Filesystem
---------------

Skills work seamlessly with filesystem features:

* ``memory/`` for skill-specific memory
* ``temp_workspaces/`` for viewing other agents' skill usage
* File tools for creating/reading skill outputs

With MCP Tools
--------------

Skills complement MCP tools:

* Use MCP tools for direct actions
* Use skills for guidance and workflows
* Skills can invoke MCP tools via instructions

With Multi-Turn
---------------

Skills persist across turns:

* Memories saved in ``memory/`` available in next turn
* Skill outputs visible in ``temp_workspaces/``

Example Workflows
=================

Complex Refactoring
-------------------

.. code-block:: yaml

   # Config: Enable skills with task planning
   coordination:
     use_skills: true
     enable_agent_task_planning: true
     organize_workspace: true

**Agent workflow:**

1. Use ``file_search`` skill to find all usages
2. Store decisions in ``memory/`` for context
3. Execute refactoring in ``workspace/``

Multi-Agent Collaboration
--------------------------

.. code-block:: yaml

   # Config: Skills with shared workspace
   coordination:
     use_skills: true
     organize_workspace: true

**Agent collaboration:**

1. Agent 1: Research using external skills, save findings to ``memory/``
2. Agent 2: Read Agent 1's memories from shared reference path (typically ``temp_workspaces/agent1/memory/``)
3. Agent 2: Build upon findings using same skills

.. note::
   The shared reference path is configurable via ``agent_temporary_workspace`` in the orchestrator config. The default is ``temp_workspaces/`` but can be any directory name. Agents see the actual path in their system prompt under "Shared Reference".

See Also
========

* :ref:`user_guide_agent_task_planning` - Task planning without skills
* :ref:`user_guide_custom_tools` - Creating custom MCP tools
* :ref:`user_guide_code_execution` - Command line execution setup
* :ref:`user_guide_file_operations` - Filesystem operations

Examples
========

* ``massgen/configs/skills/skills_basic.yaml`` - Basic skills usage
* ``massgen/configs/skills/skills_with_task_planning.yaml`` - With task planning
* ``massgen/configs/skills/skills_organized_workspace.yaml`` - Organized workspace structure
