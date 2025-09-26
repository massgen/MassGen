.. MassGen documentation master file

=================================================
MassGen: Multi-Agent Scaling System for GenAI
=================================================

.. image:: ../../assets/logo.png
   :width: 360
   :align: center
   :alt: MassGen Logo

|

.. image:: https://img.shields.io/badge/python-3.10+-blue.svg
   :target: https://www.python.org/downloads/
   :alt: Python 3.10+

.. image:: https://img.shields.io/badge/license-Apache%202.0-blue.svg
   :target: https://github.com/Leezekun/MassGen/blob/main/LICENSE
   :alt: License

.. image:: https://img.shields.io/discord/1153072414184452236?color=7289da&label=chat&logo=discord&style=flat-square
   :target: https://discord.massgen.ai
   :alt: Discord

|

**MassGen** is a cutting-edge multi-agent system that leverages the power of collaborative AI to solve complex tasks. It assigns tasks to multiple AI agents who work in parallel, observe each other's progress, and refine their approaches to converge on the best solution.

.. raw:: html

   <div style="text-align: center; margin: 20px 0;">
      <img src="../../assets/massgen-demo.gif" alt="MassGen Demo" style="max-width: 100%; height: auto;">
   </div>

Key Features
------------

.. grid:: 2
   :gutter: 3

   .. grid-item-card:: 🤝 Cross-Model Synergy

      Harness strengths from diverse frontier model-powered agents including Claude, Gemini, GPT, and Grok.

   .. grid-item-card:: ⚡ Parallel Processing

      Multiple agents tackle problems simultaneously with intelligent orchestration.

   .. grid-item-card:: 🔄 Consensus Building

      Natural convergence through collaborative refinement and real-time feedback.

   .. grid-item-card:: 📊 Live Visualization

      See agents' working processes in real-time with rich terminal displays.

Quick Links
-----------

.. grid:: 3
   :gutter: 2

   .. grid-item::

      **Getting Started**

      * :doc:`quickstart/installation`
      * :doc:`quickstart/first_agent`
      * :doc:`quickstart/configuration`

   .. grid-item::

      **User Guide**

      * :doc:`user_guide/concepts`
      * :doc:`user_guide/backends`
      * :doc:`user_guide/tools`

   .. grid-item::

      **Resources**

      * :doc:`api/index`
      * :doc:`examples/index`
      * :doc:`development/contributing`

.. toctree::
   :maxdepth: 2
   :hidden:
   :caption: Getting Started

   quickstart/installation
   quickstart/first_agent
   quickstart/configuration

.. toctree::
   :maxdepth: 2
   :hidden:
   :caption: User Guide

   user_guide/concepts
   user_guide/backends
   user_guide/tools
   user_guide/mcp_integration
   user_guide/advanced_usage

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
   examples/advanced_patterns
   examples/case_studies

.. toctree::
   :maxdepth: 2
   :hidden:
   :caption: Development

   development/contributing
   development/architecture
   development/roadmap
   changelog

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
* Support for LLaMA, Mistral, Qwen, and other models

Installation
------------

.. code-block:: bash

   # Clone the repository
   git clone https://github.com/Leezekun/MassGen.git
   cd MassGen

   # Install dependencies
   pip install uv
   uv venv
   uv pip install -r requirements.txt

   # Configure API keys
   cp .env.example .env
   # Edit .env with your API keys

Quick Example
-------------

.. code-block:: bash

   # Single agent
   uv run python -m massgen.cli --model claude-3-5-sonnet-latest "What is quantum computing?"

   # Multi-agent collaboration
   uv run python -m massgen.cli --config three_agents_default.yaml "Analyze the latest AI trends"

Community
---------

* **GitHub**: `github.com/Leezekun/MassGen <https://github.com/Leezekun/MassGen>`_
* **Discord**: `discord.massgen.ai <https://discord.massgen.ai>`_
* **Issues**: `Report bugs or request features <https://github.com/Leezekun/MassGen/issues>`_

License
-------

MassGen is licensed under the Apache License 2.0. See the `LICENSE <https://github.com/Leezekun/MassGen/blob/main/LICENSE>`_ file for details.

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`