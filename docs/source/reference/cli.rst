CLI Reference
=============

MassGen Command Line Interface reference.

Basic Usage
-----------

.. code-block:: bash

   massgen [OPTIONS] ["<your question>"]

**Default Behavior (No Arguments):**

When running ``massgen`` with no arguments, configs are auto-discovered with this priority:

1. ``.massgen/config.yaml`` (project-level config in current directory)
2. ``~/.config/massgen/config.yaml`` (global default config)
3. Launch setup wizard if no config found

**Actions:**

* **First time** (no config exists) → Launches interactive setup wizard
* **After setup** (config exists) → Starts multi-turn conversation mode
* **With question** → Runs single query using discovered config

CLI Parameters
--------------

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Parameter
     - Description
   * - ``--config PATH``
     - Path to YAML configuration file with agent definitions, model parameters, backend parameters and UI settings
   * - ``--backend TYPE``
     - Backend type for quick setup without config file. Options: ``claude``, ``claude_code``, ``gemini``, ``grok``, ``openai``, ``azure_openai``, ``zai``
   * - ``--model NAME``
     - Model name for quick setup (e.g., ``gemini-2.5-flash``, ``gpt-5-nano``). Mutually exclusive with ``--config``
   * - ``--system-message TEXT``
     - System prompt for the agent in quick setup mode. Omitted if ``--config`` is provided
   * - ``--no-display``
     - Disable real-time streaming UI coordination display (fallback to simple text output)
   * - ``--no-logs``
     - Disable real-time logging
   * - ``--debug``
     - Enable debug mode with verbose logging. Debug logs saved to ``agent_outputs/log_{time}/massgen_debug.log``
   * - ``"<your question>"``
     - Optional single-question input. If omitted, MassGen enters interactive chat mode

Examples
--------

Default Configuration Mode
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   # First time: Launch setup wizard
   massgen

   # After setup: Start interactive conversation
   massgen

   # Run single query with default config
   massgen "What is machine learning?"

Quick Single Agent
~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   # Fastest way to test - no config file
   massgen --model claude-3-5-sonnet-latest "What is machine learning?"
   massgen --model gemini-2.5-flash "Explain quantum computing"

With Specific Backend
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   massgen \
     --backend gemini \
     --model gemini-2.5-flash \
     "What are the latest developments in AI?"

Multi-Agent with Config
~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: bash

   # Recommended: Use YAML config for multi-agent
   massgen \
     --config @examples/basic/multi/three_agents_default.yaml \
     "Analyze the pros and cons of renewable energy"

Interactive Mode
~~~~~~~~~~~~~~~~

.. code-block:: bash

   # Omit question to enter interactive chat mode
   massgen --model gemini-2.5-flash

   # Multi-agent interactive
   massgen \
     --config @examples/basic/multi/three_agents_default.yaml

Debug Mode
~~~~~~~~~~

.. code-block:: bash

   massgen \
     --debug \
     --config @examples/basic/multi/three_agents_default.yaml \
     "Your question here"

Disable UI
~~~~~~~~~~

.. code-block:: bash

   # Simple text output instead of rich terminal UI
   massgen \
     --no-display \
     --config config.yaml \
     "Question"

See Also
--------

* :doc:`../quickstart/running-massgen` - Detailed usage examples
* :doc:`yaml_schema` - YAML configuration reference
* :doc:`supported_models` - Available models and backends
