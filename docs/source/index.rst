=================================================
MassGen: Multi-Agent Scaling System for GenAI
=================================================

.. raw:: html

   <img src="_static/images/logo.png" width="360" alt="MassGen Logo" class="theme-image-light">
   <img src="_static/images/logo-dark.png" width="360" alt="MassGen Logo" class="theme-image-dark">

|

.. raw:: html

   <p align="center">
     <a href="https://www.python.org/downloads/">
       <img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+">
     </a>
     <a href="https://github.com/Leezekun/MassGen/blob/main/LICENSE">
       <img src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" alt="License">
     </a>
     <a href="https://discord.massgen.ai">
       <img src="https://img.shields.io/discord/1153072414184452236?color=7289da&label=chat&logo=discord&style=flat-square" alt="Discord">
     </a>
   </p>

|

.. raw:: html

   <p align="center">
     <i>Multi-agent scaling through intelligent collaboration</i>
   </p>

.. raw:: html

   <a href="https://www.youtube.com/watch?v=Dp2oldJJImw" style="display: block; text-align: center;">
     <img src="_static/images/massgen-demo-light.gif" width="800" alt="MassGen Demo - Multi-agent collaboration in action" class="theme-image-light">
     <img src="_static/images/massgen-demo.gif" width="800" alt="MassGen Demo - Multi-agent collaboration in action" class="theme-image-dark">
   </a>

|

MassGen is a cutting-edge multi-agent system that leverages the power of collaborative AI to solve complex tasks. It assigns a task to multiple AI agents who work in parallel, observe each other's progress, and refine their approaches to converge on the best solution to deliver a comprehensive and high-quality result. The power of this "parallel study group" approach is exemplified by advanced systems like xAI's Grok Heavy and Google DeepMind's Gemini Deep Think.

What is MassGen?
-----------------

MassGen assigns your task to multiple AI agents who work in parallel, observe each other's progress, and refine their approaches to converge on the best solution. The system delivers comprehensive, high-quality results by leveraging the collective intelligence of multiple AI models.

**How It Works:**

* **Work in Parallel** - Multiple agents tackle the problem simultaneously, each bringing unique capabilities
* **See Recent Answers** - At each step, agents view the most recent answers from other agents
* **Decide Next Action** - Each agent chooses to provide a new answer or vote for an existing answer
* **Share Workspaces** - When agents provide answers, their workspace is captured so others can review their work
* **Natural Consensus** - Coordination continues until all agents vote, then the agent with most votes presents the final answer

Think of it as a "parallel study group" for AI - inspired by advanced systems like **xAI's Grok Heavy** and **Google DeepMind's Gemini Deep Think**. Agents learn from each other to produce better results than any single agent could achieve alone.

This project extends the classic "multi-agent conversation" idea from `AG2 <https://github.com/ag2ai/ag2>`_ with "threads of thought" and "iterative refinement" concepts presented in `The Myth of Reasoning <https://docs.ag2.ai/latest/docs/blog/2025/04/16/Reasoning/>`_.

Key Features
------------

.. grid:: 2
   :gutter: 3

   .. grid-item-card:: 🤝 Cross-Model Synergy

      Use Claude, Gemini, GPT, Grok, and other models together - each agent can use a different model.

   .. grid-item-card:: ⚡ Parallel Coordination

      Multiple agents work simultaneously with voting and consensus detection.

   .. grid-item-card:: 🛠️ MCP Integration

      Model Context Protocol support for tools via YAML configuration.

   .. grid-item-card:: 🔗 AG2 Framework Support

      Integrate AG2 agents with code execution alongside native MassGen agents.

   .. grid-item-card:: 📊 Live Visualization

      Real-time terminal display showing agents' working processes and coordination.

   .. grid-item-card:: 🔒 File Operation Safety

      Read-before-delete enforcement and workspace isolation for secure file operations.

   .. grid-item-card:: 🔄 Multi-Turn Interactive Mode

      Continue conversations across multiple turns with full context preservation and session management.

   .. grid-item-card:: 📁 Project Integration

      Work directly with your codebase using context paths with granular read/write permissions.

Recent Releases
---------------

**v0.1.0 (October 17, 2025)** - PyPI Package Release

Official PyPI package available for installation via ``pip install massgen`` with comprehensive Sphinx documentation.

**v0.0.32 (October 15, 2025)** - Docker Execution & MCP Refactoring

Docker-based isolated command execution with resource limits. Major MCP architecture simplification for better maintainability.

**v0.0.31 (October 13, 2025)** - Code Execution & Framework Integration

Universal MCP-based command execution across all backends. AG2 framework integration with group chat support. Limited audio/video generation capabilities.

Quick Start
-----------

Get started with MassGen in minutes:

**Install:**

.. code-block:: bash

   pip install massgen

**Option 1: Use the setup wizard (recommended for first time):**

.. code-block:: bash

   # Run without arguments to launch the interactive setup wizard
   massgen

The wizard will guide you through configuring your API keys and creating your first agent team.

After setup, you can:

.. code-block:: bash

   # Run a single query with your configured agents
   massgen "Your question here"

   # Or start an interactive conversation (no prompt needed)
   massgen

**Option 2: Quick single-agent test:**

.. code-block:: bash

   # No config needed - specify model directly
   massgen --model gemini-2.5-flash "What are LLM agents?"

**Option 3: Multi-agent collaboration:**

.. code-block:: bash

   # Use a built-in configuration
   massgen --config @examples/basic/multi/three_agents_default \
     "What are the pros and cons of renewable energy?"

Watch agents discuss, vote, and converge on the best answer in real-time!

**Ready to dive deeper?**

* :doc:`quickstart/installation` - Complete installation guide and setup wizard
* :doc:`quickstart/running-massgen` - Learn all the ways to run MassGen
* :doc:`quickstart/configuration` - Create custom agent teams
* :doc:`examples/basic_examples` - Copy-paste ready examples

Supported Models
----------------

MassGen supports a wide range of AI models across different providers:

**API-based Models:**

* **Claude** (Anthropic): Haiku, Sonnet, Opus series
* **Gemini** (Google): Flash, Pro series with MCP support
* **GPT** (OpenAI): GPT-4, GPT-5 series
* **Grok** (xAI): Grok-3, Grok-4 series
* **Azure OpenAI**: Enterprise deployments
* And :doc:`many more <reference/supported_models>`...

**Local Models:**

* **LM Studio**: Run open-weight models locally
* **vLLM & SGLang**: Unified inference backend

**External Frameworks:**

* **AG2** Agents with code execution capabilities

.. tip::
   **Choosing the right backend?** Different models have different strengths. See the complete **Backend Capabilities Matrix** in :doc:`user_guide/backends` to understand which features (web search, code execution, file operations, etc.) are available for each model.

Core Concepts
-------------

**Simple CLI Interface**
   Get started with just ``massgen`` - install via pip, run the interactive setup wizard, and you're ready to go.

**Multi-Agent Coordination**
   Multiple agents work in parallel, observe each other's progress, and reach consensus through natural collaboration with real-time visualization.

**Interactive Multi-Turn Mode**
   Have ongoing conversations with your multi-agent team! Session history is preserved in the ``.massgen/sessions/`` directory, allowing you to continue conversations across multiple sessions with full context preservation.

**Flexible Model Support**
   Use Claude, Gemini, GPT, Grok, and more - each agent can use a different model. Mix and match models for optimal results.

**MCP Tool Integration**
   Extend agent capabilities with Model Context Protocol (MCP) tools. Supports planning mode to prevent irreversible actions during coordination.

**Workspace Isolation & File Operations**
   Each agent gets its own isolated workspace for safe file operations. The ``.massgen/`` directory keeps all MassGen files organized and separate from your project.

**Project Integration**
   Work directly with your existing codebases! Use context paths to grant agents read/write access to specific directories with granular permission control.

**Configuration**
   After using the setup wizard, customize your agent teams via YAML configuration files for advanced scenarios.

Documentation Sections
----------------------

.. grid:: 3
   :gutter: 2

   .. grid-item::

      **Getting Started**

      * :doc:`quickstart/installation`
      * :doc:`quickstart/running-massgen`
      * :doc:`quickstart/configuration`

   .. grid-item::

      **User Guide**

      * :doc:`user_guide/concepts`
      * :doc:`user_guide/backends`
      * :doc:`user_guide/tools`
      * :doc:`user_guide/file_operations`
      * :doc:`user_guide/multi_turn_mode`
      * :doc:`user_guide/ag2_integration`

   .. grid-item::

      **Reference**

      * :doc:`reference/python_api`
      * :doc:`reference/cli`
      * :doc:`reference/yaml_schema`
      * :doc:`reference/configuration_examples`
      * :doc:`reference/supported_models`
      * :doc:`reference/timeouts`

   .. grid-item::

      **Examples**

      * :doc:`examples/case_studies`
      * :doc:`examples/basic_examples`
      * :doc:`examples/advanced_patterns`

   .. grid-item::

      **Development**

      * :doc:`development/contributing`
      * :doc:`development/architecture`
      * :doc:`development/roadmap`

.. toctree::
   :maxdepth: 2
   :hidden:
   :caption: Getting Started

   quickstart/installation
   quickstart/running-massgen
   quickstart/configuration

.. toctree::
   :maxdepth: 2
   :hidden:
   :caption: User Guide

   user_guide/concepts
   user_guide/backends
   user_guide/tools
   user_guide/file_operations
   user_guide/multi_turn_mode
   user_guide/multimodal
   user_guide/ag2_integration
   user_guide/logging

.. toctree::
   :maxdepth: 2
   :hidden:
   :caption: Reference

   reference/python_api
   reference/cli
   reference/yaml_schema
   reference/configuration_examples
   reference/timeouts
   reference/supported_models
   glossary

.. toctree::
   :maxdepth: 2
   :hidden:
   :caption: Examples

   examples/case_studies
   examples/basic_examples
   examples/advanced_patterns
   examples/available_configs

.. toctree::
   :maxdepth: 2
   :hidden:
   :caption: Development

   development/contributing
   development/writing_configs
   development/architecture
   development/roadmap
   changelog
   api/index

Community
---------

* **GitHub**: `github.com/Leezekun/MassGen <https://github.com/Leezekun/MassGen>`_
* **Discord**: `discord.massgen.ai <https://discord.massgen.ai>`_
* **Issues**: `Report bugs or request features <https://github.com/Leezekun/MassGen/issues>`_

License
-------

MassGen is licensed under the Apache License 2.0. See the `LICENSE <https://github.com/Leezekun/MassGen/blob/main/LICENSE>`_ file for details.

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
