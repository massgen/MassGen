==========
Python API
==========

MassGen provides a simple, async-first Python API for programmatic usage. This allows you to integrate MassGen's multi-agent capabilities directly into your Python applications.

.. note::
   **For Contributors:** Looking for internal API documentation? See :doc:`../api/index` for developer API reference of classes and modules.

.. note::
   MassGen is inherently asynchronous, so the API is naturally async. Use ``asyncio`` for sync contexts.

.. warning::
   **Python API Status:** The Python API is currently in early development. Only basic functionality is available through the ``massgen.run()`` function. More comprehensive programmatic APIs (agent creation, orchestrator control, streaming, callbacks, etc.) are planned for future releases. For now, use the CLI for advanced features or see :doc:`../api/index` for internal APIs.

Quick Start
===========

Basic Usage
-----------

The simplest way to use MassGen from Python:

.. code-block:: python

   import asyncio
   import massgen

   async def main():
       # Quick single-agent query
       result = await massgen.run(
           query="What is machine learning?",
           model="gpt-5-mini"
       )
       print(result['final_answer'])

   # Run from sync context
   asyncio.run(main())

That's it! MassGen handles all the complexity of backend initialization, agent creation, and orchestration.

API Reference
=============

massgen.run()
-------------

.. py:function:: async def run(query: str, config: str = None, model: str = None, **kwargs) -> dict

   Run a MassGen query asynchronously.

   This is the main entry point for using MassGen programmatically. It's a simple wrapper around
   MassGen's CLI logic, providing the same functionality in a Python-friendly interface.

   :param query: The question or task for the agent(s)
   :type query: str
   :param config: Config file path or @examples/NAME (optional)
   :type config: str, optional
   :param model: Quick single-agent mode with model name (optional)
   :type model: str, optional
   :param \\**kwargs: Additional configuration options
   :type \\**kwargs: dict
   :return: Dictionary with 'final_answer' and metadata
   :rtype: dict

   **Return Value:**

   The function returns a dictionary with the following structure:

   .. code-block:: python

      {
          'final_answer': str,      # The generated answer
          'config_used': str,       # Path to config that was used
      }

   **Example:**

   .. code-block:: python

      result = await massgen.run(
          query="Explain quantum computing",
          model="gemini-2.5-flash"
      )
      print(result['final_answer'])
      print(f"Used config: {result['config_used']}")

Usage Patterns
==============

Single Agent Mode
-----------------

For simple queries with a single agent:

.. code-block:: python

   import asyncio
   import massgen

   async def single_agent_query():
       result = await massgen.run(
           query="What are the benefits of renewable energy?",
           model="gpt-5-mini"
       )
       return result['final_answer']

   answer = asyncio.run(single_agent_query())
   print(answer)

**Supported Models:**

- OpenAI: ``gpt-5``, ``gpt-5-mini``, ``gpt-5-nano``, ``gpt-4o``, ``o1``
- Anthropic: ``claude-sonnet-4``, ``claude-opus-4``
- Google: ``gemini-2.5-flash``, ``gemini-2.5-pro``, ``gemini-2.0-flash``
- xAI: ``grok-4``, ``grok-4-fast-reasoning``

See :doc:`supported_models` for the complete list.

Multi-Agent with Configuration
-------------------------------

For complex queries requiring multiple agents:

.. code-block:: python

   import asyncio
   import massgen

   async def multi_agent_research():
       result = await massgen.run(
           query="Compare renewable energy sources with analysis",
           config="@examples/research_team"
       )
       return result

   result = asyncio.run(multi_agent_research())
   print(result['final_answer'])
   print(f"Config: {result['config_used']}")

**Built-in Example Configurations:**

Use the ``@examples/`` prefix to access built-in configurations:

- ``@examples/basic_single`` - Single agent configuration
- ``@examples/basic_multi`` - Three-agent basic setup
- ``@examples/research_team`` - Research-focused agents with web search
- ``@examples/coding_team`` - Code generation with multiple agents

List all available examples:

.. code-block:: bash

   massgen --list-examples

Default Configuration
---------------------

Use your default configuration (from the setup wizard):

.. code-block:: python

   import asyncio
   import massgen

   async def use_default_config():
       # No config or model specified - uses ~/.config/massgen/config.yaml
       result = await massgen.run(
           query="Analyze the impact of AI on healthcare"
       )
       return result['final_answer']

   answer = asyncio.run(use_default_config())
   print(answer)

Custom Configuration Files
---------------------------

Use your own YAML configuration files:

.. code-block:: python

   import asyncio
   import massgen

   async def custom_config():
       result = await massgen.run(
           query="Your question",
           config="./my-agents.yaml"  # Relative path
       )
       return result

   # Or absolute path
   async def custom_config_abs():
       result = await massgen.run(
           query="Your question",
           config="/path/to/my-agents.yaml"
       )
       return result

Named Configurations
--------------------

Use named configurations from ``~/.config/massgen/agents/``:

.. code-block:: python

   import asyncio
   import massgen

   async def named_config():
       # Looks for ~/.config/massgen/agents/research-team.yaml
       result = await massgen.run(
           query="Research question",
           config="research-team"  # No .yaml extension needed
       )
       return result

   answer = asyncio.run(named_config())
   print(answer)

Advanced Usage
==============

Async/Await Patterns
--------------------

Since MassGen is async-native, you can integrate it into async applications:

.. code-block:: python

   import asyncio
   import massgen

   async def process_multiple_queries():
       # Run multiple queries concurrently
       queries = [
           "What is AI?",
           "Explain machine learning",
           "Define neural networks"
       ]

       tasks = [
           massgen.run(query=q, model="gpt-5-mini")
           for q in queries
       ]

       results = await asyncio.gather(*tasks)

       for query, result in zip(queries, results):
           print(f"Q: {query}")
           print(f"A: {result['final_answer']}\n")

   asyncio.run(process_multiple_queries())

Integration with FastAPI
------------------------

MassGen works seamlessly with FastAPI:

.. code-block:: python

   from fastapi import FastAPI
   import massgen

   app = FastAPI()

   @app.post("/query")
   async def handle_query(question: str, model: str = "gpt-5-mini"):
       result = await massgen.run(
           query=question,
           model=model
       )
       return {
           "question": question,
           "answer": result['final_answer'],
           "config": result['config_used']
       }

   # Run with: uvicorn myapp:app

Integration with Jupyter Notebooks
-----------------------------------

MassGen works great in Jupyter notebooks:

.. code-block:: python

   # In a Jupyter cell
   import massgen

   # Jupyter handles the event loop for you
   result = await massgen.run(
       query="Explain photosynthesis",
       model="gemini-2.5-flash"
   )

   print(result['final_answer'])

   # Or create an explicit async cell
   async def research_query():
       return await massgen.run(
           query="Compare programming paradigms",
           config="@examples/research_team"
       )

   result = await research_query()
   print(result['final_answer'])

Error Handling
--------------

Handle errors gracefully:

.. code-block:: python

   import asyncio
   import massgen

   async def safe_query():
       try:
           result = await massgen.run(
               query="Your question",
               model="gpt-5-mini"
           )
           return result['final_answer']

       except ValueError as e:
           print(f"Configuration error: {e}")
           # E.g., config not found, no API key

       except Exception as e:
           print(f"Unexpected error: {e}")
           return None

   answer = asyncio.run(safe_query())

Common Errors
=============

No Configuration Found
----------------------

.. code-block:: python

   ValueError: No config specified and no default config found.
   Run `massgen --init` to create a default configuration.

**Solution:** Run the setup wizard to create a default config:

.. code-block:: bash

   massgen --init

Or specify a config explicitly:

.. code-block:: python

   result = await massgen.run(query="...", config="@examples/basic_multi")

API Key Not Found
-----------------

If you see API key errors, ensure your keys are configured:

1. Set environment variables:

   .. code-block:: bash

      export OPENAI_API_KEY="sk-..."
      export ANTHROPIC_API_KEY="sk-ant-..."

2. Or create ``~/.config/massgen/.env``:

   .. code-block:: bash

      OPENAI_API_KEY=sk-...
      ANTHROPIC_API_KEY=sk-ant-...

Config Not Found
----------------

.. code-block:: python

   ConfigurationError: Configuration file not found: my-config

**Solution:** Check the config path exists, or use ``@examples/`` for built-in configs.

Best Practices
==============

1. **Use Async/Await Properly**

   .. code-block:: python

      # Good
      result = await massgen.run(query="...")

      # Bad (won't work)
      result = massgen.run(query="...")  # Missing await

2. **Handle Errors**

   Always wrap API calls in try/except blocks for production code.

3. **Reuse Configurations**

   Create named configurations for common use cases:

   .. code-block:: python

      # Save to ~/.config/massgen/agents/research.yaml
      # Then reuse:
      result = await massgen.run(query="...", config="research")

4. **Use Single-Agent Mode for Simple Queries**

   For straightforward questions, single-agent mode is faster:

   .. code-block:: python

      result = await massgen.run(
          query="Quick question",
          model="gpt-5-mini"  # Fast and cheap
      )

5. **Use Multi-Agent Mode for Complex Analysis**

   For research, comparison, or analysis:

   .. code-block:: python

      result = await massgen.run(
          query="Compare X and Y",
          config="@examples/research_team"
      )

See Also
========

- :doc:`../quickstart/installation` - Installation and setup
- :doc:`../quickstart/configuration` - Configuration file format
- :doc:`cli` - Command-line interface reference
- :doc:`supported_models` - Supported models and backends
- :doc:`yaml_schema` - YAML configuration schema
