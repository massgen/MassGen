Advanced Patterns
=================

Sophisticated patterns for complex multi-agent scenarios.

Hierarchical Teams
------------------

.. code-block:: python

   from massgen import Agent, Orchestrator

   # Create team structure
   team_lead = Agent(name="TeamLead", backend=backend)
   
   dev_team = Orchestrator(
       agents=[
           Agent(name="Backend", backend=backend),
           Agent(name="Frontend", backend=backend)
       ],
       coordinator=team_lead
   )

   result = dev_team.run("Build a web application")

Dynamic Agent Creation
----------------------

.. code-block:: python

   from massgen import DynamicOrchestrator

   class AdaptiveOrchestrator(DynamicOrchestrator):
       def create_agents_for_task(self, task):
           # Dynamically create agents based on task
           agents = []
           if "code" in task:
               agents.append(Agent(name="Coder", backend=backend))
           if "review" in task:
               agents.append(Agent(name="Reviewer", backend=backend))
           return agents

   orchestrator = AdaptiveOrchestrator()
   result = orchestrator.run("Code and review a feature")

Consensus Building
------------------

.. code-block:: python

   # Consensus-based decision making
   orchestrator = Orchestrator(
       agents=decision_agents,
       strategy="consensus",
       consensus_threshold=0.8,
       max_rounds=5
   )

   decision = orchestrator.run("Make strategic decision")