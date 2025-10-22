Examples
========

Practical examples demonstrating MassGen capabilities.

.. toctree::
   :maxdepth: 2
   :caption: Example Categories

   basic_examples
   advanced_patterns

Quick Start Examples
--------------------

Simple Multi-Agent Task
~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from massgen import Agent, Orchestrator
   from massgen.backends import OpenAIBackend

   # Create agents
   agents = [
       Agent("Agent1", OpenAIBackend()),
       Agent("Agent2", OpenAIBackend())
   ]

   # Run task
   orchestrator = Orchestrator(agents)
   result = orchestrator.run("Solve a problem")

More Examples
-------------

* :doc:`basic_examples` - Fundamental patterns
* :doc:`advanced_patterns` - Complex scenarios