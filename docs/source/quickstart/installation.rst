============
Installation
============

Prerequisites
=============

MassGen requires **Python 3.11 or higher**. You can check your Python version with:

.. code-block:: bash

   python --version

If you need to install or upgrade Python, visit `python.org/downloads <https://www.python.org/downloads/>`_.

Core Installation
=================

There are two ways to install MassGen:

Installation Methods
--------------------

**Method 1: Local Installation** (simpler, works in MassGen directory)

.. code-block:: bash

   # Clone the repository
   git clone https://github.com/Leezekun/MassGen.git
   cd MassGen

   # Install uv (fast Python package installer)
   pip install uv

   # Create virtual environment
   uv venv

**Method 2: Global Installation with uv tool** (recommended for multi-directory usage)

.. code-block:: bash

   # Clone the repository
   git clone https://github.com/Leezekun/MassGen.git
   cd MassGen

   # Install uv (if you don't have it)
   pip install uv

   # Install MassGen as a global tool in editable mode
   uv tool install -e .

Why Use uv tool Installation?
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``uv tool`` installation method provides significant benefits:

.. grid:: 2
   :gutter: 3

   .. grid-item-card:: 🔒 Isolated Environment

      Creates an isolated Python environment with no conflicts with your system Python or other projects.

   .. grid-item-card:: 🌍 Global Access

      Available from any directory - use MassGen wherever you need it.

   .. grid-item-card:: 🔄 Live Development

      Editable mode (``-e .``) means changes are reflected immediately without reinstalling.

   .. grid-item-card:: ⚡ Easy Updates

      Simply run ``git pull`` to get the latest features (editable mode automatically uses new code).

   .. grid-item-card:: 🧹 Clean Uninstall

      Remove completely with ``uv tool uninstall massgen`` when needed.

   .. grid-item-card:: 📦 Dependency Management

      uv handles all dependencies efficiently and reliably.

How to Use Each Method
----------------------

**If you installed with Method 1 (Local):**

.. code-block:: bash

   # Always run from the MassGen directory
   cd /path/to/MassGen
   uv run python -m massgen.cli --model gemini-2.5-flash "Your question"
   uv run python -m massgen.cli --config massgen/configs/basic/multi/three_agents_default.yaml

**If you installed with Method 2 (Global uv tool):**

.. code-block:: bash

   # Run from anywhere!
   cd ~/my-project
   uv tool run massgen --model gemini-2.5-flash "Your question"
   uv tool run massgen --config /absolute/path/to/config.yaml

   # Or with local config in your project
   uv tool run massgen --config ./my-agents.yaml

Optional Dependencies
=====================

AG2 Framework Integration
--------------------------

If you want to use AG2 agents alongside native MassGen agents, install the external dependencies:

.. code-block:: bash

   uv pip install -e ".[external]"

This is **only required** if you plan to use AG2 configuration files.

Optional CLI Tools
==================

Enhanced Capabilities
---------------------

Install these optional tools for enhanced MassGen capabilities:

Claude Code CLI
~~~~~~~~~~~~~~~

Advanced coding assistant with comprehensive development tools:

.. code-block:: bash

   npm install -g @anthropic-ai/claude-code

LM Studio
~~~~~~~~~

Local model inference for running open-weight models:

**For MacOS/Linux:**

.. code-block:: bash

   sudo ~/.lmstudio/bin/lms bootstrap

**For Windows:**

.. code-block:: bash

   cmd /c %USERPROFILE%/.lmstudio/bin/lms.exe bootstrap

Multi-Turn Filesystem Setup
============================

Understanding the .massgen Directory
------------------------------------

When you work with MassGen using multi-turn conversations or file operations, MassGen automatically creates a clean, organized directory structure:

.. code-block:: text

   your-project/
   ├── .massgen/                          # All MassGen state
   │   ├── sessions/                      # Multi-turn conversation history
   │   │   └── session_20240101_143022/
   │   │       ├── turn_1/                # Results from turn 1
   │   │       ├── turn_2/                # Results from turn 2
   │   │       └── SESSION_SUMMARY.txt    # Human-readable summary
   │   ├── workspaces/                    # Agent working directories
   │   │   ├── agent1/                    # Individual agent workspaces
   │   │   └── agent2/
   │   ├── snapshots/                     # Workspace snapshots for coordination
   │   └── temp_workspaces/               # Previous turn results for context
   ├── your-project-files/
   └── ...

Benefits of .massgen Organization
----------------------------------

.. grid:: 2
   :gutter: 3

   .. grid-item-card:: 🧹 Clean Projects

      All MassGen files are contained in a single ``.massgen/`` directory, keeping your project organized.

   .. grid-item-card:: 📝 Easy .gitignore

      Simply add ``.massgen/`` to your ``.gitignore`` file to exclude all MassGen working files from version control.

   .. grid-item-card:: 🚚 Portable

      Move or delete the ``.massgen/`` directory without affecting your project files.

   .. grid-item-card:: 💬 Session Persistence

      Multi-turn conversation history is preserved across sessions for continuity.

Configuration Auto-Organization
--------------------------------

MassGen automatically organizes configuration paths under ``.massgen/``:

.. code-block:: yaml

   orchestrator:
     # You specify simple names - MassGen organizes under .massgen/
     snapshot_storage: "snapshots"         # → .massgen/snapshots/
     session_storage: "sessions"           # → .massgen/sessions/
     agent_temporary_workspace: "temp"     # → .massgen/temp/

   agents:
     - backend:
         cwd: "workspace1"                 # → .massgen/workspaces/workspace1/

This keeps your configuration clean while maintaining organized project structure.

Verification Steps
==================

After installation, verify MassGen is correctly installed:

.. code-block:: bash

   # For local installation
   uv run python -m massgen.cli --help

   # For global uv tool installation
   uv tool run massgen --help

You should see the MassGen CLI help message with all available options.

Quick Test
----------

Try a simple single-agent query to verify everything works:

.. code-block:: bash

   # Replace with your preferred model
   uv run python -m massgen.cli --model gemini-2.5-flash "What is MassGen?"

Next Steps
==========

Now that you have MassGen installed, you're ready to:

1. :doc:`running-massgen` - Learn how to run MassGen with different configurations
2. :doc:`configuration` - Configure API keys and customize settings
3. :doc:`../user_guide/multi_turn_mode` - Explore multi-turn interactive conversations
4. :doc:`../user_guide/file_operations` - Learn about file operations and workspace management

Troubleshooting
===============

Python Version Issues
---------------------

If you encounter Python version errors:

.. code-block:: bash

   # Check your Python version
   python --version

   # If below 3.11, install a newer version from python.org
   # Then create a new virtual environment with the correct Python

uv Installation Issues
----------------------

If ``uv`` installation fails:

.. code-block:: bash

   # Try upgrading pip first
   pip install --upgrade pip

   # Then install uv
   pip install uv

Permission Issues
-----------------

If you encounter permission errors during installation:

.. code-block:: bash

   # On MacOS/Linux, you might need to use sudo for global installations
   sudo npm install -g @anthropic-ai/claude-code

   # Or use --user flag for pip
   pip install --user uv

For more help, visit our `GitHub Issues <https://github.com/Leezekun/MassGen/issues>`_ or join our `Discord community <https://discord.massgen.ai>`_.
