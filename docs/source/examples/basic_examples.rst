Basic Examples
==============

Fundamental examples for getting started with MassGen.

Simple Collaboration
--------------------

.. code-block:: python

   from massgen import Agent, Orchestrator
   from massgen.backends import OpenAIBackend, AnthropicBackend

   # Create diverse agents
   researcher = Agent(
       name="Researcher",
       backend=OpenAIBackend(model="gpt-4"),
       role="Research and gather information"
   )

   analyst = Agent(
       name="Analyst",
       backend=AnthropicBackend(model="claude-3-opus"),
       role="Analyze and synthesize data"
   )

   # Orchestrate collaboration
   orchestrator = Orchestrator(agents=[researcher, analyst])
   result = orchestrator.run("Analyze market trends in AI")
   print(result)

Sequential Processing
---------------------

.. code-block:: python

   # Sequential task execution
   orchestrator = Orchestrator(
       agents=[researcher, analyst],
       strategy="sequential"
   )

   result = orchestrator.run(
       "First research the topic, then analyze findings"
   )

Parallel Execution
------------------

.. code-block:: python

   # Parallel task execution
   orchestrator = Orchestrator(
       agents=[agent1, agent2, agent3],
       strategy="parallel"
   )

   result = orchestrator.run(
       "Generate multiple solutions simultaneously"
   )