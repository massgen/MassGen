Your First Agent
================

This guide will help you create your first multi-agent system with MassGen.

Basic Setup
-----------

Import the necessary components:

.. code-block:: python

   from massgen import Agent, Orchestrator
   from massgen.backend import ChatCompletionsBackend

Creating Agents
---------------

Create agents with different backend providers:

.. code-block:: python

   # Create a Claude agent
   claude_agent = Agent(
       name="Claude",
       backend=ChatCompletionsBackend(
           api_key="your-claude-api-key",
           base_url="https://api.anthropic.com/v1",
           model="claude-3-opus-20240229"
       )
   )

   # Create a GPT agent
   gpt_agent = Agent(
       name="GPT",
       backend=ChatCompletionsBackend(
           api_key="your-openai-api-key",
           base_url="https://api.openai.com/v1",
           model="gpt-4"
       )
   )

Setting Up the Orchestrator
---------------------------

Create an orchestrator to manage agent collaboration:

.. code-block:: python

   orchestrator = Orchestrator(
       agents=[claude_agent, gpt_agent],
       strategy="consensus"  # or "sequential", "parallel"
   )

Running Your First Task
-----------------------

Execute a task with your multi-agent system:

.. code-block:: python

   # Simple task
   result = orchestrator.run(
       "Explain quantum computing in simple terms"
   )

   print(result)

Advanced Usage
--------------

Using specialized agents for specific tasks:

.. code-block:: python

   from massgen import SpecializedAgent

   # Create a code specialist
   code_agent = SpecializedAgent(
       name="Coder",
       specialization="code_generation",
       backend=backend
   )

   # Create a research specialist
   research_agent = SpecializedAgent(
       name="Researcher",
       specialization="research",
       backend=backend
   )

Next Steps
----------

* :doc:`configuration` - Learn about advanced configuration options
* :doc:`../user_guide/concepts` - Understand core MassGen concepts
* :doc:`../user_guide/backends` - Explore different backend providers