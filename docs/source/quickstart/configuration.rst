Configuration
=============

MassGen provides flexible configuration options for agents, orchestrators, and system behavior.

Agent Configuration
-------------------

Basic Configuration
~~~~~~~~~~~~~~~~~~~

Configure agents with various parameters:

.. code-block:: python

   from massgen import Agent
   from massgen.backends import OpenAIBackend

   agent = Agent(
       name="ExpertAgent",
       backend=OpenAIBackend(
           model="gpt-4",
           temperature=0.7,
           max_tokens=2000
       ),
       role="Domain expert",
       system_prompt="You are an expert in data science...",
       tools=[],
       max_retries=3
   )

Backend-Specific Configuration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Each backend supports specific configuration:

.. code-block:: python

   # OpenAI configuration
   openai_backend = OpenAIBackend(
       model="gpt-4",
       api_key="your-key",  # or use environment variable
       temperature=0.5,
       top_p=0.9,
       frequency_penalty=0.0,
       presence_penalty=0.0
   )

   # Anthropic configuration
   anthropic_backend = AnthropicBackend(
       model="claude-3-opus",
       api_key="your-key",
       max_tokens=4096,
       temperature=0.7
   )

   # Google configuration  
   google_backend = GoogleBackend(
       model="gemini-pro",
       api_key="your-key",
       temperature=0.8,
       top_k=40
   )

Orchestrator Configuration
--------------------------

Configure orchestration behavior:

.. code-block:: python

   from massgen import Orchestrator

   orchestrator = Orchestrator(
       agents=agents,
       strategy="consensus",
       max_rounds=5,
       consensus_threshold=0.75,
       timeout=300,  # seconds
       verbose=True,
       log_level="INFO"
   )

Configuration Files
-------------------

YAML Configuration
~~~~~~~~~~~~~~~~~~

Use YAML files for complex configurations:

.. code-block:: yaml

   # config.yaml
   agents:
     - name: ResearchAgent
       backend:
         type: openai
         model: gpt-4
         temperature: 0.7
       role: Research specialist
       
     - name: AnalysisAgent
       backend:
         type: anthropic
         model: claude-3-opus
         temperature: 0.5
       role: Data analyst

   orchestrator:
     strategy: parallel
     max_rounds: 3
     consensus_threshold: 0.8

Load configuration:

.. code-block:: python

   from massgen import load_config

   config = load_config("config.yaml")
   orchestrator = config.create_orchestrator()

Environment Variables
---------------------

MassGen supports environment variables for sensitive data:

.. code-block:: bash

   # .env file
   MASSGEN_LOG_LEVEL=DEBUG
   MASSGEN_DEFAULT_STRATEGY=consensus
   MASSGEN_TIMEOUT=600
   
   # API Keys
   OPENAI_API_KEY=sk-...
   ANTHROPIC_API_KEY=sk-ant-...
   GOOGLE_API_KEY=...
   XAI_API_KEY=...

Advanced Configuration
----------------------

Custom Prompts
~~~~~~~~~~~~~~

Configure custom system prompts:

.. code-block:: python

   agent = Agent(
       name="CustomAgent",
       backend=backend,
       system_prompt="""
       You are a specialized agent with expertise in {domain}.
       Your responses should be:
       1. Accurate and well-researched
       2. Concise but comprehensive
       3. Include relevant examples
       """.format(domain="machine learning")
   )

Tool Configuration
~~~~~~~~~~~~~~~~~~

Configure tools with specific parameters:

.. code-block:: python

   from massgen.tools import WebSearch, Calculator

   web_search = WebSearch(
       max_results=10,
       timeout=30,
       safe_search=True
   )

   calculator = Calculator(
       precision=10,
       scientific_mode=True
   )

   agent = Agent(
       name="ToolAgent",
       backend=backend,
       tools=[web_search, calculator]
   )

Logging Configuration
~~~~~~~~~~~~~~~~~~~~~

Configure logging behavior:

.. code-block:: python

   import logging
   from massgen import configure_logging

   configure_logging(
       level=logging.DEBUG,
       format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
       output_file='massgen.log'
   )

Performance Tuning
------------------

Optimize for different scenarios:

.. code-block:: python

   # For speed
   fast_config = {
       "strategy": "parallel",
       "max_rounds": 2,
       "timeout": 60,
       "cache_enabled": True
   }

   # For accuracy
   accurate_config = {
       "strategy": "consensus",
       "max_rounds": 5,
       "consensus_threshold": 0.9,
       "verification_enabled": True
   }

   # For cost efficiency
   efficient_config = {
       "strategy": "sequential",
       "max_tokens": 1000,
       "model": "gpt-3.5-turbo",
       "cache_enabled": True
   }

Next Steps
----------

* :doc:`../user_guide/concepts` - Understand core concepts
* :doc:`../user_guide/backends` - Explore backend options
* :doc:`../user_guide/advanced_usage` - Advanced configuration techniques