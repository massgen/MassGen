=================================================
MassGen: Multi-Agent Scaling System for GenAI
=================================================

.. image:: ../../assets/logo.png
   :width: 360
   :align: center
   :alt: MassGen Logo

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

.. image:: ../../assets/massgen-demo.gif
   :width: 800
   :align: center
   :alt: MassGen Demo - Multi-agent collaboration in action
   :target: https://www.youtube.com/watch?v=Dp2oldJJImw

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

      Model Context Protocol support for tools via YAML configuration with planning mode.

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

Latest Features (v0.0.29)
--------------------------

**What's New in v0.0.29:**

.. grid:: 2
   :gutter: 3

   .. grid-item-card:: 🎯 MCP Planning Mode

      New coordination strategy that plans MCP tool usage without execution, preventing irreversible actions during collaboration.

      .. code-block:: bash

         massgen \
           --config @examples/tools/planning/five_agents_filesystem_mcp_planning_mode.yaml \
           "Create a comprehensive project structure"

   .. grid-item-card:: 🛡️ File Operation Safety

      Read-before-delete enforcement ensures agents review files before deletion - no more accidental deletions!

   .. grid-item-card:: 🔧 Enhanced MCP Tool Filtering

      Multi-level filtering with backend-level and per-MCP-server control for precise tool management.

   .. grid-item-card:: 🌟 Gemini Planning Mode Support

      Extended planning mode compatibility to Gemini backend for safer multi-agent collaboration.

**Experience v0.0.29 MCP Planning Mode:**

.. raw:: html

   <p align="center">
     <a href="https://youtu.be/jLrMMEIr118">
       <img src="https://img.youtube.com/vi/jLrMMEIr118/0.jpg" alt="MassGen v0.0.29 MCP Planning Mode Demo" width="600">
     </a>
   </p>

**Try v0.0.29:**

.. code-block:: bash

   # Five agents collaborating with planning mode (no execution during coordination)
   massgen \
     --config @examples/tools/planning/five_agents_filesystem_mcp_planning_mode.yaml \
     "Create a comprehensive project structure with documentation"

   # Test MCP tools with multiple agents
   massgen \
     --config @examples/tools/mcp/five_agents_weather_mcp_test.yaml \
     "Compare weather forecasts for New York, London, and Tokyo"

See all release examples in `Configuration Guide <https://github.com/Leezekun/MassGen/blob/main/@examples/README.md#release-history--examples>`_.

Quick Start
-----------

Get started with MassGen in 3 simple steps:

Step 1: Install
~~~~~~~~~~~~~~~

**Prerequisites:** Python 3.11+

.. code-block:: bash

   git clone https://github.com/Leezekun/MassGen.git
   cd MassGen
   pip install uv
   uv venv

:doc:`See installation options <quickstart/installation>` including global installation with ``uv tool``

Step 2: Set Up API Keys
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   cp .env.example .env
   # Edit .env and add your API key (only one needed to start)

You only need the API key for the model you plan to use first.

Step 3: Run Your First Task
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Hello World - Single Agent:**

.. code-block:: bash

   # Simplest command - uses one model, no config file needed
   massgen --model gemini-2.5-flash "What is 2+2?"

**Expected output:** The agent responds directly with the answer. *This takes ~5 seconds and costs ~$0.001*

**Try Multi-Agent Collaboration:**

Once the single agent works, experience MassGen's power with multiple agents:

.. code-block:: bash

   # Three agents collaborate on the answer
   massgen \
     --config @examples/basic/multi/three_agents_default.yaml \
     "What are the pros and cons of renewable energy?"

**What happens:** You'll see agents discuss, vote, and converge on the best answer. The coordination table shows real-time progress.

.. note::
   **Config file paths:** Examples show ``@examples/...`` which works when you're in the MassGen repo directory. See :doc:`quickstart/running-massgen` for how to use configs from other directories.

**Next Steps:**

* :doc:`quickstart/running-massgen` - More examples and interactive mode
* :doc:`quickstart/configuration` - Create custom agent teams
* :doc:`examples/basic_examples` - Copy-paste ready examples

Supported Models
----------------

**API-based Models:**

* **Claude** (Anthropic): Haiku, Sonnet, Opus series
* **Gemini** (Google): Flash, Pro series with MCP support
* **GPT** (OpenAI): GPT-4, GPT-5 series
* **Grok** (xAI): Grok-3, Grok-4 series
* **Azure OpenAI**: Enterprise deployments
* And many more...

**Local Models:**

* **LM Studio**: Run open-weight models locally
* **vLLM & SGLang**: Unified inference backend

**External Frameworks:**

* **AG2** Agents with code execution capabilities

Core Concepts
-------------

**Configuration-Driven**
   MassGen uses YAML files to configure agents, models, tools, and coordination strategies. No code required!

**CLI-Based**
   Simple command-line interface: ``massgen``

**Multi-Agent Coordination**
   Agents vote for solutions and reach consensus through natural collaboration with real-time visualization.

**Interactive Multi-Turn Mode**
   Have ongoing conversations with your multi-agent team! Session history is preserved in the ``.massgen/sessions/`` directory, allowing you to continue conversations across multiple sessions with full context preservation.

**MCP Tool Integration**
   Extend agent capabilities with Model Context Protocol (MCP) tools via simple YAML configuration. Supports planning mode to prevent irreversible actions during coordination.

**Workspace Isolation & File Operations**
   Each agent gets its own isolated workspace for safe file operations. The ``.massgen/`` directory keeps all MassGen files organized and separate from your project.

**Project Integration**
   Work directly with your existing codebases! Use context paths to grant agents read/write access to specific directories with granular permission control.

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
      * :doc:`user_guide/multi_turn_mode`
      * :doc:`user_guide/file_operations`
      * :doc:`user_guide/backends`
      * :doc:`user_guide/ag2_integration`
      * :doc:`user_guide/mcp_integration`

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

      * :doc:`examples/index`
      * :doc:`examples/basic_examples`

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
   user_guide/multi_turn_mode
   user_guide/file_operations
   user_guide/backends
   user_guide/ag2_integration
   user_guide/mcp_integration
   user_guide/tools
   user_guide/multimodal
   user_guide/logging
   user_guide/advanced_usage

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
   :caption: API Reference

   api/index
   api/agents
   api/orchestrator
   api/backends

.. toctree::
   :maxdepth: 2
   :hidden:
   :caption: Examples

   examples/index
   examples/basic_examples
   examples/case_studies

.. toctree::
   :maxdepth: 2
   :hidden:
   :caption: Development

   development/contributing
   development/writing_configs
   development/architecture
   development/roadmap
   changelog

.. toctree::
   :maxdepth: 2
   :hidden:
   :caption: Project Coordination (For Contributors)

   decisions/index
   rfcs/index
   tracks/index

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
