Installation
============

Prerequisites
-------------

MassGen requires Python 3.10 or higher. You can check your Python version with:

.. code-block:: bash

   python --version

Installation Methods
--------------------

Using pip
~~~~~~~~~

Install MassGen from PyPI:

.. code-block:: bash

   pip install massgen

For development with all optional dependencies:

.. code-block:: bash

   pip install massgen[all]

Using uv
~~~~~~~~

For faster installation with uv:

.. code-block:: bash

   uv add massgen

From Source
~~~~~~~~~~~

Clone the repository and install:

.. code-block:: bash

   git clone https://github.com/Leezekun/MassGen.git
   cd MassGen
   pip install -e .

Verifying Installation
----------------------

After installation, verify MassGen is correctly installed:

.. code-block:: bash

   massgen --version

Next Steps
----------

* :doc:`first_agent` - Create your first multi-agent system
* :doc:`configuration` - Configure API keys and settings