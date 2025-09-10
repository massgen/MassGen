Configuration
=============

MassGen supports multiple configuration methods to set up your API keys and customize agent behavior.

Environment Variables
---------------------

The recommended way to configure API keys is through environment variables. Create a `.env` file in your project root:

.. code-block:: bash

   # OpenAI
   OPENAI_API_KEY=your-openai-api-key
   
   # Anthropic Claude
   ANTHROPIC_API_KEY=your-anthropic-api-key
   
   # Google Gemini
   GOOGLE_API_KEY=your-google-api-key
   
   # xAI Grok
   XAI_API_KEY=your-xai-api-key
   
   # Cerebras
   CEREBRAS_API_KEY=your-cerebras-api-key

Configuration File
------------------

Create a `config.yaml` file for more detailed configuration:

.. code-block:: yaml

   agents:
     - name: Claude
       backend: claude
       model: claude-3-opus-20240229
       temperature: 0.7
       max_tokens: 4096
     
     - name: GPT
       backend: openai
       model: gpt-4
       temperature: 0.8
       max_tokens: 4096
     
     - name: Gemini
       backend: gemini
       model: gemini-pro
       temperature: 0.9
   
   orchestrator:
     strategy: consensus
     max_rounds: 5
     timeout: 300

Loading Configuration
---------------------

Load configuration in your code:

.. code-block:: python

   from massgen import load_config
   import os
   from dotenv import load_dotenv
   
   # Load environment variables
   load_dotenv()
   
   # Load configuration file
   config = load_config("config.yaml")
   
   # Create agents from configuration
   agents = config.create_agents()

Backend-Specific Configuration
-------------------------------

OpenAI-Compatible Backends
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   backend = ChatCompletionsBackend(
       api_key=os.getenv("OPENAI_API_KEY"),
       base_url="https://api.openai.com/v1",
       model="gpt-4",
       temperature=0.7,
       max_tokens=4096
   )

Claude Backend
~~~~~~~~~~~~~~

.. code-block:: python

   from massgen.backend import ClaudeBackend
   
   backend = ClaudeBackend(
       api_key=os.getenv("ANTHROPIC_API_KEY"),
       model="claude-3-opus-20240229",
       max_tokens=4096
   )

Gemini Backend
~~~~~~~~~~~~~~

.. code-block:: python

   from massgen.backend import GeminiBackend
   
   backend = GeminiBackend(
       api_key=os.getenv("GOOGLE_API_KEY"),
       model="gemini-pro",
       temperature=0.9
   )

Advanced Settings
-----------------

Orchestration Strategies
~~~~~~~~~~~~~~~~~~~~~~~~

Configure different orchestration strategies:

.. code-block:: python

   # Sequential processing
   orchestrator = Orchestrator(agents=agents, strategy="sequential")
   
   # Parallel processing
   orchestrator = Orchestrator(agents=agents, strategy="parallel")
   
   # Consensus building
   orchestrator = Orchestrator(agents=agents, strategy="consensus")

Logging Configuration
~~~~~~~~~~~~~~~~~~~~~

Configure logging for debugging:

.. code-block:: python

   import logging
   
   logging.basicConfig(
       level=logging.INFO,
       format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
   )

Next Steps
----------

* :doc:`../user_guide/concepts` - Deep dive into MassGen concepts
* :doc:`../user_guide/backends` - Explore all available backends
* :doc:`../examples/index` - See complete examples