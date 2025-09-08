Case Studies
============

Real-world applications of MassGen.

Content Generation Pipeline
---------------------------

A complete content generation system using multiple specialized agents.

.. code-block:: python

   from massgen import Agent, Orchestrator
   from massgen.tools import WebSearch, FileWriter

   # Specialized content agents
   researcher = Agent(
       name="ContentResearcher",
       backend=OpenAIBackend(),
       tools=[WebSearch()],
       role="Research topics and gather information"
   )

   writer = Agent(
       name="ContentWriter",
       backend=AnthropicBackend(),
       role="Write engaging content"
   )

   editor = Agent(
       name="ContentEditor",
       backend=GoogleBackend(),
       role="Edit and refine content"
   )

   seo_optimizer = Agent(
       name="SEOOptimizer",
       backend=OpenAIBackend(),
       role="Optimize content for search engines"
   )

   # Content pipeline
   content_pipeline = Orchestrator(
       agents=[researcher, writer, editor, seo_optimizer],
       strategy="sequential"
   )

   article = content_pipeline.run(
       "Create a comprehensive article about quantum computing"
   )

Data Analysis System
--------------------

Multi-agent data analysis with specialized roles.

.. code-block:: python

   from massgen import Agent, Orchestrator
   from massgen.tools import DatabaseQuery, Calculator

   # Data analysis team
   data_collector = Agent(
       name="DataCollector",
       backend=backend,
       tools=[DatabaseQuery()],
       role="Collect and prepare data"
   )

   statistician = Agent(
       name="Statistician",
       backend=backend,
       tools=[Calculator()],
       role="Perform statistical analysis"
   )

   visualizer = Agent(
       name="Visualizer",
       backend=backend,
       role="Create data visualizations"
   )

   interpreter = Agent(
       name="Interpreter",
       backend=backend,
       role="Interpret results and insights"
   )

   # Analysis pipeline
   analysis_system = Orchestrator(
       agents=[data_collector, statistician, visualizer, interpreter],
       strategy="sequential"
   )

   insights = analysis_system.run(
       "Analyze customer behavior patterns from last quarter"
   )

Customer Support System
-----------------------

Intelligent customer support with escalation.

.. code-block:: python

   from massgen import Agent, Orchestrator

   # Support hierarchy
   tier1_agent = Agent(
       name="Tier1Support",
       backend=OpenAIBackend(model="gpt-3.5-turbo"),
       role="Handle basic inquiries"
   )

   tier2_agent = Agent(
       name="Tier2Support",
       backend=OpenAIBackend(model="gpt-4"),
       role="Handle complex issues"
   )

   specialist_agent = Agent(
       name="Specialist",
       backend=AnthropicBackend(model="claude-3-opus"),
       role="Handle specialized technical issues"
   )

   # Support system with escalation
   support_system = Orchestrator(
       agents=[tier1_agent, tier2_agent, specialist_agent],
       strategy="escalation",
       escalation_threshold=0.3  # Confidence threshold
   )

   response = support_system.run(
       customer_query,
       context={"customer_tier": "premium", "history": previous_tickets}
   )