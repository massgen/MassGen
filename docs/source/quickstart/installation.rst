Installation
============

This guide will help you install MassGen and get started with multi-agent orchestration.

Requirements
------------

* Python 3.10 or higher
* pip package manager
* API keys for the LLM providers you want to use

Installation Methods
--------------------

Using pip
~~~~~~~~~

Install MassGen directly from PyPI:

.. code-block:: bash

   pip install massgen

From Source
~~~~~~~~~~~

Clone the repository and install in development mode:

.. code-block:: bash

   git clone https://github.com/Leezekun/MassGen.git
   cd MassGen
   pip install -e .

Installing Documentation Dependencies
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To build the documentation locally:

.. code-block:: bash

   pip install massgen[docs]
   # or
   pip install -r docs/requirements-docs.txt

Setting Up API Keys
--------------------

MassGen supports multiple LLM providers. Set up your API keys as environment variables:

.. code-block:: bash

   export OPENAI_API_KEY="your-openai-key"
   export ANTHROPIC_API_KEY="your-anthropic-key"
   export GOOGLE_API_KEY="your-google-key"
   export XAI_API_KEY="your-xai-key"

Or create a `.env` file in your project root:

.. code-block:: text

   OPENAI_API_KEY=your-openai-key
   ANTHROPIC_API_KEY=your-anthropic-key
   GOOGLE_API_KEY=your-google-key
   XAI_API_KEY=your-xai-key

Verifying Installation
----------------------

Verify that MassGen is installed correctly:

.. code-block:: bash

   python -c "import massgen; print(massgen.__version__)"

Next Steps
----------

* :doc:`first_agent` - Create your first multi-agent system
* :doc:`configuration` - Learn about configuration options
* :doc:`../user_guide/concepts` - Understand MassGen's core concepts