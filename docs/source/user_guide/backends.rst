Backends
========

MassGen supports multiple LLM backends, allowing you to leverage different AI models for your agents.

Overview
--------

Backends provide the AI capabilities for agents. Each backend:

* Connects to a specific LLM provider
* Handles API communication
* Manages model-specific parameters
* Provides consistent interface

Available Backends
------------------

OpenAI Backend
~~~~~~~~~~~~~~

Supports OpenAI's GPT models:

.. code-block:: python

   from massgen.backends import OpenAIBackend

   backend = OpenAIBackend(
       model="gpt-4",  # or "gpt-3.5-turbo", "gpt-4-turbo"
       api_key="sk-...",  # Optional, uses env var if not provided
       temperature=0.7,
       max_tokens=2000,
       top_p=1.0,
       frequency_penalty=0.0,
       presence_penalty=0.0,
       stream=False
   )

   agent = Agent(name="GPTAgent", backend=backend)

Anthropic Backend
~~~~~~~~~~~~~~~~~

Supports Anthropic's Claude models:

.. code-block:: python

   from massgen.backends import AnthropicBackend

   backend = AnthropicBackend(
       model="claude-3-opus-20240229",  # or "claude-3-sonnet", "claude-3-haiku"
       api_key="sk-ant-...",
       max_tokens=4096,
       temperature=0.7,
       top_p=1.0,
       top_k=40
   )

   agent = Agent(name="ClaudeAgent", backend=backend)

Google Backend
~~~~~~~~~~~~~~

Supports Google's Gemini models:

.. code-block:: python

   from massgen.backends import GoogleBackend

   backend = GoogleBackend(
       model="gemini-pro",  # or "gemini-pro-vision"
       api_key="...",
       temperature=0.8,
       top_p=0.95,
       top_k=40,
       max_output_tokens=2048
   )

   agent = Agent(name="GeminiAgent", backend=backend)

XAI Backend
~~~~~~~~~~~

Supports XAI's Grok models:

.. code-block:: python

   from massgen.backends import XAIBackend

   backend = XAIBackend(
       model="grok-beta",
       api_key="...",
       temperature=0.7,
       max_tokens=2000
   )

   agent = Agent(name="GrokAgent", backend=backend)

Cerebras Backend
~~~~~~~~~~~~~~~~

Supports Cerebras Cloud models:

.. code-block:: python

   from massgen.backends import CerebrasBackend

   backend = CerebrasBackend(
       model="cerebras-gpt",
       api_key="...",
       temperature=0.7,
       max_tokens=2000
   )

   agent = Agent(name="CerebrasAgent", backend=backend)

LMStudio Backend
~~~~~~~~~~~~~~~~

For local models via LMStudio:

.. code-block:: python

   from massgen.backends import LMStudioBackend

   backend = LMStudioBackend(
       base_url="http://localhost:1234",
       model="local-model-name",
       temperature=0.7,
       max_tokens=2000
   )

   agent = Agent(name="LocalAgent", backend=backend)

Backend Configuration
---------------------

Common Parameters
~~~~~~~~~~~~~~~~~

Most backends support these parameters:

* **model**: The specific model to use
* **temperature**: Controls randomness (0.0-2.0)
* **max_tokens**: Maximum response length
* **top_p**: Nucleus sampling parameter
* **api_key**: Authentication key (can use environment variable)

Advanced Configuration
~~~~~~~~~~~~~~~~~~~~~~

**Rate Limiting**

Handle API rate limits:

.. code-block:: python

   backend = OpenAIBackend(
       model="gpt-4",
       rate_limit=60,  # requests per minute
       retry_on_rate_limit=True,
       max_retries=3
   )

**Timeout Configuration**

Set request timeouts:

.. code-block:: python

   backend = AnthropicBackend(
       model="claude-3-opus",
       timeout=30,  # seconds
       connection_timeout=10
   )

**Custom Headers**

Add custom HTTP headers:

.. code-block:: python

   backend = OpenAIBackend(
       model="gpt-4",
       custom_headers={
           "X-Custom-Header": "value"
       }
   )

Choosing the Right Backend
--------------------------

Model Comparison
~~~~~~~~~~~~~~~~

.. list-table:: Backend Comparison
   :header-rows: 1
   :widths: 20 20 20 20 20

   * - Backend
     - Strength
     - Speed
     - Cost
     - Use Case
   * - GPT-4
     - General tasks
     - Medium
     - High
     - Complex reasoning
   * - Claude 3
     - Long context
     - Medium
     - High
     - Document analysis
   * - Gemini
     - Multimodal
     - Fast
     - Medium
     - Vision + text
   * - Grok
     - Real-time data
     - Fast
     - Medium
     - Current events
   * - Local
     - Privacy
     - Varies
     - Low
     - Sensitive data

Backend Selection Strategy
~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   # Use different backends for different tasks
   research_agent = Agent(
       name="Researcher",
       backend=OpenAIBackend(model="gpt-4"),
       role="Deep research and analysis"
   )

   summary_agent = Agent(
       name="Summarizer",
       backend=AnthropicBackend(model="claude-3-haiku"),
       role="Quick summarization"
   )

   vision_agent = Agent(
       name="VisionAnalyst",
       backend=GoogleBackend(model="gemini-pro-vision"),
       role="Image analysis"
   )

Custom Backends
---------------

Creating a Custom Backend
~~~~~~~~~~~~~~~~~~~~~~~~~

Implement your own backend:

.. code-block:: python

   from massgen.backends import Backend

   class CustomBackend(Backend):
       def __init__(self, **kwargs):
           super().__init__(**kwargs)
           self.client = self._initialize_client()

       def _initialize_client(self):
           # Initialize your API client
           pass

       def generate(self, prompt, **kwargs):
           # Implement generation logic
           response = self.client.complete(prompt, **kwargs)
           return response.text

       def stream_generate(self, prompt, **kwargs):
           # Implement streaming if supported
           for chunk in self.client.stream(prompt, **kwargs):
               yield chunk

Backend Adapters
~~~~~~~~~~~~~~~~

Create adapters for existing APIs:

.. code-block:: python

   from massgen.backends import HTTPBackend

   class CustomAPIBackend(HTTPBackend):
       def __init__(self, api_url, **kwargs):
           super().__init__(base_url=api_url, **kwargs)

       def prepare_request(self, prompt, **kwargs):
           return {
               "endpoint": "/generate",
               "payload": {
                   "text": prompt,
                   "parameters": kwargs
               }
           }

       def parse_response(self, response):
           return response.json()["generated_text"]

Performance Optimization
------------------------

Caching Responses
~~~~~~~~~~~~~~~~~

Enable response caching:

.. code-block:: python

   backend = OpenAIBackend(
       model="gpt-4",
       cache_enabled=True,
       cache_ttl=3600,  # 1 hour
       cache_size=1000  # max entries
   )

Batch Processing
~~~~~~~~~~~~~~~~

Process multiple requests efficiently:

.. code-block:: python

   backend = OpenAIBackend(model="gpt-4")

   prompts = ["Prompt 1", "Prompt 2", "Prompt 3"]
   responses = backend.batch_generate(prompts, batch_size=10)

Load Balancing
~~~~~~~~~~~~~~

Distribute load across multiple API keys:

.. code-block:: python

   from massgen.backends import LoadBalancedBackend

   backend = LoadBalancedBackend(
       backends=[
           OpenAIBackend(api_key="key1"),
           OpenAIBackend(api_key="key2"),
           OpenAIBackend(api_key="key3")
       ],
       strategy="round_robin"  # or "random", "least_loaded"
   )

Error Handling
--------------

Retry Logic
~~~~~~~~~~~

Configure retry behavior:

.. code-block:: python

   backend = OpenAIBackend(
       model="gpt-4",
       max_retries=3,
       retry_delay=1.0,
       exponential_backoff=True,
       retry_on_errors=[429, 500, 502, 503]
   )

Fallback Backends
~~~~~~~~~~~~~~~~~

Set up fallback options:

.. code-block:: python

   from massgen.backends import FallbackBackend

   backend = FallbackBackend(
       primary=OpenAIBackend(model="gpt-4"),
       fallbacks=[
           AnthropicBackend(model="claude-3-opus"),
           GoogleBackend(model="gemini-pro")
       ]
   )

Next Steps
----------

* :doc:`tools` - Enhance agents with tools
* :doc:`mcp_integration` - MCP protocol integration
* :doc:`advanced_usage` - Advanced backend patterns