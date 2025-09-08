Your First Agent
================

This guide will walk you through creating your first multi-agent system with MassGen.

Basic Example
-------------

Here's a simple example that creates multiple agents to collaborate on a task:

.. code-block:: python

   from massgen import Agent, Orchestrator
   from massgen.backends import OpenAIBackend, AnthropicBackend

   # Create agents with different backends
   agent1 = Agent(
       name="ResearchAgent",
       backend=OpenAIBackend(model="gpt-4"),
       role="Research specialist"
   )

   agent2 = Agent(
       name="AnalysisAgent", 
       backend=AnthropicBackend(model="claude-3-opus"),
       role="Data analyst"
   )

   # Create an orchestrator to manage agents
   orchestrator = Orchestrator(agents=[agent1, agent2])

   # Run a collaborative task
   result = orchestrator.run(
       task="Analyze the latest trends in AI development",
       max_rounds=3
   )

   print(result)

Understanding the Components
----------------------------

Agents
~~~~~~

Agents are the core workers in MassGen. Each agent:

* Has a specific role or expertise
* Uses a specific LLM backend
* Can communicate with other agents
* Contributes to solving the overall task

Orchestrator
~~~~~~~~~~~~

The orchestrator manages the collaboration:

* Coordinates agent interactions
* Manages the workflow
* Aggregates results
* Ensures consensus building

Running with Different Strategies
----------------------------------

MassGen supports various orchestration strategies:

.. code-block:: python

   # Parallel execution
   result = orchestrator.run(
       task="Generate creative solutions",
       strategy="parallel"
   )

   # Sequential execution
   result = orchestrator.run(
       task="Step-by-step analysis",
       strategy="sequential"
   )

   # Consensus-based execution
   result = orchestrator.run(
       task="Make a decision",
       strategy="consensus",
       consensus_threshold=0.8
   )

Adding Tools and Capabilities
------------------------------

Enhance your agents with tools:

.. code-block:: python

   from massgen.tools import WebSearch, Calculator

   agent = Agent(
       name="ResearchAgent",
       backend=OpenAIBackend(),
       tools=[WebSearch(), Calculator()],
       role="Research specialist with web access"
   )

Monitoring Progress
-------------------

MassGen provides real-time visualization of agent collaboration:

.. code-block:: python

   # Enable verbose output
   orchestrator = Orchestrator(
       agents=[agent1, agent2],
       verbose=True
   )

   # Watch agents work in real-time
   result = orchestrator.run(task="Complex problem solving")

Next Steps
----------

* :doc:`configuration` - Configure agents and orchestrators
* :doc:`../user_guide/backends` - Explore different LLM backends
* :doc:`../user_guide/tools` - Learn about available tools
* :doc:`../examples/basic_examples` - See more examples