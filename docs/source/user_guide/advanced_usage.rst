Advanced Usage
==============

This guide covers advanced patterns and techniques for building sophisticated multi-agent systems with MassGen.

Advanced Orchestration Patterns
--------------------------------

Hierarchical Orchestration
~~~~~~~~~~~~~~~~~~~~~~~~~~

Create multi-level agent hierarchies:

.. code-block:: python

   from massgen import Agent, Orchestrator

   # Team leads
   research_lead = Agent(name="ResearchLead", backend=backend, role="Research coordinator")
   dev_lead = Agent(name="DevLead", backend=backend, role="Development coordinator")

   # Research team
   research_team = Orchestrator(
       agents=[
           Agent(name="DataAnalyst", backend=backend),
           Agent(name="MarketResearcher", backend=backend)
       ],
       coordinator=research_lead
   )

   # Development team
   dev_team = Orchestrator(
       agents=[
           Agent(name="Backend Dev", backend=backend),
           Agent(name="Frontend Dev", backend=backend)
       ],
       coordinator=dev_lead
   )

   # Master orchestrator
   master = Orchestrator(
       orchestrators=[research_team, dev_team],
       strategy="hierarchical"
   )

   result = master.run("Design and implement a new feature")

Dynamic Agent Creation
~~~~~~~~~~~~~~~~~~~~~~

Create agents dynamically based on task requirements:

.. code-block:: python

   from massgen import DynamicOrchestrator

   class TaskBasedOrchestrator(DynamicOrchestrator):
       def create_agents_for_task(self, task):
           agents = []
           
           if "research" in task.lower():
               agents.append(Agent(name="Researcher", backend=backend))
           
           if "code" in task.lower():
               agents.append(Agent(name="Coder", backend=backend))
           
           if "review" in task.lower():
               agents.append(Agent(name="Reviewer", backend=backend))
           
           return agents

   orchestrator = TaskBasedOrchestrator()
   result = orchestrator.run("Research and code a solution")

Adaptive Strategies
~~~~~~~~~~~~~~~~~~~

Switch strategies based on task characteristics:

.. code-block:: python

   from massgen import AdaptiveOrchestrator

   orchestrator = AdaptiveOrchestrator(
       agents=agents,
       strategy_selector=lambda task: (
           "parallel" if "urgent" in task.lower()
           else "consensus" if "decision" in task.lower()
           else "sequential"
       )
   )

Memory and Context Management
-----------------------------

Shared Memory
~~~~~~~~~~~~~

Implement shared memory across agents:

.. code-block:: python

   from massgen.memory import SharedMemory

   shared_memory = SharedMemory(
       capacity=10000,  # tokens
       persistence=True,
       storage_path="./memory"
   )

   agent1 = Agent(
       name="Agent1",
       backend=backend,
       memory=shared_memory
   )

   agent2 = Agent(
       name="Agent2",
       backend=backend,
       memory=shared_memory
   )

   # Agents can access shared knowledge
   orchestrator = Orchestrator(agents=[agent1, agent2])

Long-term Memory
~~~~~~~~~~~~~~~~

Implement persistent long-term memory:

.. code-block:: python

   from massgen.memory import LongTermMemory

   ltm = LongTermMemory(
       backend="vector_db",  # or "sql", "graph"
       connection_string="...",
       embedding_model="text-embedding-ada-002"
   )

   agent = Agent(
       name="MemoryAgent",
       backend=backend,
       long_term_memory=ltm
   )

   # Agent remembers across sessions
   result = agent.run("What did we discuss last week?")

Context Windows
~~~~~~~~~~~~~~~

Manage context windows efficiently:

.. code-block:: python

   from massgen.memory import ContextManager

   context_manager = ContextManager(
       max_tokens=8000,
       strategy="sliding_window",  # or "summary", "importance"
       compression_ratio=0.5
   )

   agent = Agent(
       name="ContextAgent",
       backend=backend,
       context_manager=context_manager
   )

Custom Agent Behaviors
----------------------

Agent Personalities
~~~~~~~~~~~~~~~~~~~

Define distinct agent personalities:

.. code-block:: python

   from massgen import PersonalityAgent

   creative_agent = PersonalityAgent(
       name="CreativeAgent",
       backend=backend,
       personality={
           "creativity": 0.9,
           "analytical": 0.3,
           "risk_taking": 0.7,
           "detail_oriented": 0.4
       },
       communication_style="informal"
   )

   analytical_agent = PersonalityAgent(
       name="AnalyticalAgent",
       backend=backend,
       personality={
           "creativity": 0.3,
           "analytical": 0.9,
           "risk_taking": 0.2,
           "detail_oriented": 0.8
       },
       communication_style="formal"
   )

Specialized Agents
~~~~~~~~~~~~~~~~~~

Create highly specialized agents:

.. code-block:: python

   from massgen import SpecializedAgent

   class CodeReviewAgent(SpecializedAgent):
       def __init__(self, **kwargs):
           super().__init__(**kwargs)
           self.specialization = "code_review"
           self.review_criteria = [
               "code_quality",
               "performance",
               "security",
               "maintainability"
           ]
       
       def review_code(self, code):
           reviews = {}
           for criterion in self.review_criteria:
               reviews[criterion] = self.evaluate(code, criterion)
           return reviews

   reviewer = CodeReviewAgent(
       name="Reviewer",
       backend=backend
   )

Performance Optimization
------------------------

Parallel Processing
~~~~~~~~~~~~~~~~~~~

Optimize parallel agent execution:

.. code-block:: python

   from massgen import ParallelOrchestrator
   import asyncio

   async def main():
       orchestrator = ParallelOrchestrator(
           agents=agents,
           max_concurrent=10,
           batch_size=5,
           use_thread_pool=True
       )
       
       tasks = ["Task 1", "Task 2", "Task 3", ...]
       results = await orchestrator.batch_process(tasks)
       return results

   results = asyncio.run(main())

Resource Management
~~~~~~~~~~~~~~~~~~~

Manage computational resources:

.. code-block:: python

   from massgen import ResourceManager

   resource_manager = ResourceManager(
       max_tokens_per_minute=100000,
       max_concurrent_requests=20,
       priority_queue=True
   )

   orchestrator = Orchestrator(
       agents=agents,
       resource_manager=resource_manager
   )

   # High priority task
   result = orchestrator.run(
       "Urgent task",
       priority="high"
   )

Caching Strategies
~~~~~~~~~~~~~~~~~~

Implement intelligent caching:

.. code-block:: python

   from massgen.cache import IntelligentCache

   cache = IntelligentCache(
       strategy="semantic",  # Cache based on semantic similarity
       similarity_threshold=0.95,
       ttl=3600,
       max_size=1000
   )

   agent = Agent(
       name="CachedAgent",
       backend=backend,
       cache=cache
   )

Advanced Error Handling
-----------------------

Circuit Breaker Pattern
~~~~~~~~~~~~~~~~~~~~~~~~

Implement circuit breakers:

.. code-block:: python

   from massgen.resilience import CircuitBreaker

   circuit_breaker = CircuitBreaker(
       failure_threshold=5,
       recovery_timeout=60,
       half_open_attempts=3
   )

   agent = Agent(
       name="ResilientAgent",
       backend=backend,
       circuit_breaker=circuit_breaker
   )

Compensation Actions
~~~~~~~~~~~~~~~~~~~~

Define compensation strategies:

.. code-block:: python

   from massgen import CompensatingOrchestrator

   orchestrator = CompensatingOrchestrator(
       agents=agents,
       compensation_map={
           "api_call_failed": lambda: use_cached_data(),
           "agent_timeout": lambda: use_fallback_agent(),
           "consensus_failed": lambda: request_human_input()
       }
   )

Monitoring and Observability
----------------------------

Distributed Tracing
~~~~~~~~~~~~~~~~~~~

Implement distributed tracing:

.. code-block:: python

   from massgen.observability import Tracer

   tracer = Tracer(
       service_name="massgen",
       endpoint="http://jaeger:14268/api/traces"
   )

   orchestrator = Orchestrator(
       agents=agents,
       tracer=tracer
   )

   with tracer.span("complex_task"):
       result = orchestrator.run("Complex multi-step task")

Metrics Collection
~~~~~~~~~~~~~~~~~~

Collect detailed metrics:

.. code-block:: python

   from massgen.metrics import MetricsCollector

   metrics = MetricsCollector(
       backend="prometheus",
       push_gateway="http://prometheus:9091"
   )

   @metrics.track("task_duration")
   def run_task(orchestrator, task):
       return orchestrator.run(task)

   # Access metrics
   print(metrics.get_metric("task_duration").percentile(95))

Integration Patterns
--------------------

Event-Driven Architecture
~~~~~~~~~~~~~~~~~~~~~~~~~~

Implement event-driven patterns:

.. code-block:: python

   from massgen.events import EventBus, Event

   event_bus = EventBus()

   @event_bus.on("task_completed")
   def handle_completion(event: Event):
       logger.info(f"Task {event.task_id} completed")
       # Trigger next workflow

   orchestrator = Orchestrator(
       agents=agents,
       event_bus=event_bus
   )

   result = orchestrator.run("Task that triggers events")

Microservices Integration
~~~~~~~~~~~~~~~~~~~~~~~~~~

Integrate with microservices:

.. code-block:: python

   from massgen.integration import MicroserviceAgent

   order_agent = MicroserviceAgent(
       name="OrderService",
       backend=backend,
       service_url="http://order-service:8080",
       circuit_breaker=True,
       retry_policy="exponential"
   )

   inventory_agent = MicroserviceAgent(
       name="InventoryService",
       backend=backend,
       service_url="http://inventory-service:8080"
   )

   orchestrator = Orchestrator(agents=[order_agent, inventory_agent])

Testing Strategies
------------------

Unit Testing Agents
~~~~~~~~~~~~~~~~~~~

Test individual agents:

.. code-block:: python

   import pytest
   from massgen.testing import MockBackend, AgentTester

   def test_agent_response():
       mock_backend = MockBackend(
           responses=["Mocked response"]
       )
       
       agent = Agent(
           name="TestAgent",
           backend=mock_backend
       )
       
       tester = AgentTester(agent)
       result = tester.test_response("Test input")
       
       assert "Mocked response" in result

Integration Testing
~~~~~~~~~~~~~~~~~~~

Test agent interactions:

.. code-block:: python

   from massgen.testing import OrchestratorTester

   def test_orchestration():
       tester = OrchestratorTester(
           agents=[agent1, agent2],
           mock_responses={
               "agent1": ["Response 1"],
               "agent2": ["Response 2"]
           }
       )
       
       result = tester.test_orchestration(
           task="Test task",
           expected_interactions=2
       )
       
       assert result.success
       assert len(result.interactions) == 2

Best Practices
--------------

1. **Modular Design**: Keep agents focused on specific responsibilities
2. **Error Recovery**: Always implement fallback mechanisms
3. **Resource Limits**: Set appropriate limits for tokens and requests
4. **Monitoring**: Implement comprehensive monitoring and alerting
5. **Testing**: Test both individual agents and orchestration patterns
6. **Documentation**: Document agent roles and interaction patterns
7. **Security**: Implement proper authentication and data validation
8. **Versioning**: Version your agent configurations and prompts

Next Steps
----------

* :doc:`../api/index` - Complete API reference
* :doc:`../examples/advanced_patterns` - Advanced examples
* :doc:`../development/architecture` - System architecture